"""Training mode: extract mistakes from games, generate explanations, export drill data.

Analyzes the player's games with Stockfish, finds positions where significant
centipawn losses occurred, generates rule-based explanations, and exports
a JSON file for the PWA drill interface.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.engine
import chess.pgn

from chess_self_coach import worker_count
from chess_self_coach.config import (
    _find_project_root,
    check_stockfish_version,
    find_stockfish,
    load_config,
)
from chess_self_coach.importer import fetch_chesscom_games, fetch_lichess_games
from chess_self_coach.tablebase import (
    MAX_PIECES,
    TablebaseResult,
    probe_position,
    tablebase_context,
    tablebase_cp_loss,
    tablebase_explanation,
)

# Centipawn loss thresholds
BLUNDER_THRESHOLD = 200
MISTAKE_THRESHOLD = 100
INACCURACY_THRESHOLD = 50

# Sentinel for mate scores (centipawns)
_MATE_CP = 10000


def _analysis_limit(board: chess.Board, default_depth: int) -> chess.engine.Limit:
    """Adaptive analysis limit: deeper search for endgames.

    King+pawns endgames get the most time — these are highly instructive
    and Stockfish NNUE is weakest here (opposition, zugzwang, key squares).
    For positions <= 7 pieces, this is mainly a fallback when the Lichess
    tablebase API is unavailable.
    """
    piece_count = len(board.piece_map())
    kings_and_pawns_only = all(
        p.piece_type in (chess.KING, chess.PAWN) for p in board.piece_map().values()
    )
    if kings_and_pawns_only and piece_count <= 7:
        return chess.engine.Limit(time=6.0, depth=60)
    if piece_count <= 7:
        return chess.engine.Limit(time=5.0, depth=50)
    if piece_count <= 12:
        return chess.engine.Limit(time=4.0, depth=40)
    return chess.engine.Limit(depth=default_depth)


def _score_to_cp(score: chess.engine.PovScore) -> tuple[int | None, bool]:
    """Convert a PovScore to centipawns from white's perspective.

    Args:
        score: Engine PovScore.

    Returns:
        Tuple of (centipawns from white perspective, is_mate).
    """
    white = score.white()
    if white.is_mate():
        mate = white.mate()
        return (_MATE_CP if mate > 0 else -_MATE_CP), True
    return white.score(), False


def _format_score_cp(cp: int | None) -> str:
    """Format centipawn value as score string like '+0.32'."""
    if cp is None:
        return "+0.00"
    value = cp / 100.0
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}"


def compute_cp_loss(
    before_white_cp: int, after_white_cp: int, side_to_move: chess.Color
) -> int:
    """Compute centipawn loss for the player who made the move.

    Args:
        before_white_cp: Score before the move (white perspective, centipawns).
        after_white_cp: Score after the move (white perspective, centipawns).
        side_to_move: Color of the player who made the move.

    Returns:
        Centipawn loss (positive = bad for the mover).
    """
    if side_to_move == chess.WHITE:
        return before_white_cp - after_white_cp
    return after_white_cp - before_white_cp


def _classify_mistake(cp_loss: int) -> str | None:
    """Classify a move by centipawn loss.

    Returns:
        Category string or None if the move is acceptable.
    """
    if cp_loss >= BLUNDER_THRESHOLD:
        return "blunder"
    if cp_loss >= MISTAKE_THRESHOLD:
        return "mistake"
    if cp_loss >= INACCURACY_THRESHOLD:
        return "inaccuracy"
    return None


def _format_cp_loss_human(cp_loss: int, was_mate: bool = False) -> str:
    """Format centipawn loss for human display.

    Args:
        cp_loss: Centipawn loss value.
        was_mate: True if the score before the move was a forced mate.

    Returns human-readable loss string.
    """
    if cp_loss >= _MATE_CP or was_mate:
        return "a forced mate"
    pawns = cp_loss / 100.0
    if pawns >= 5:
        return "a decisive advantage"
    if pawns == int(pawns):
        return f"{int(pawns)} pawn{'s' if int(pawns) != 1 else ''}"
    return f"{pawns:.1f} pawns"


def generate_explanation(
    board: chess.Board,
    actual_san: str,
    best_san: str,
    cp_loss: int,
    category: str,
    was_mate: bool = False,
    score_after_cp: int | None = None,
) -> str:
    """Generate a rule-based explanation for a mistake.

    Detects basic patterns: missed captures, missed checks/checkmates,
    hanging pieces, stalemate. Falls back to a generic template.

    Args:
        board: Board position BEFORE the move was played.
        actual_san: The move the player made (SAN).
        best_san: The best move according to Stockfish (SAN).
        cp_loss: Centipawn loss.
        category: Mistake category string.
        was_mate: True if the position before was a forced mate.
        score_after_cp: Score after the move (white perspective), for context.

    Returns:
        Explanation string.
    """
    score_after_is_mate = score_after_cp is not None and abs(score_after_cp) >= _MATE_CP

    # Build opening sentence with appropriate phrasing
    if was_mate and score_after_cp is not None and abs(score_after_cp) < 50:
        parts = [f"You played {actual_san} ({category}). You had a forced mate but threw it away — the game is now a draw."]
    elif was_mate:
        parts = [f"You played {actual_san} ({category}). You had a forced mate but lost it."]
    elif score_after_is_mate:
        parts = [f"You played {actual_san} ({category}). This allowed your opponent to force checkmate."]
    else:
        loss_str = _format_cp_loss_human(cp_loss)
        parts = [f"You played {actual_san} ({category}, lost {loss_str})."]

    # Analyze the actual move for immediate stalemate detection
    board_after_actual = None
    try:
        actual_move = board.parse_san(actual_san)
        board_after_actual = board.copy()
        board_after_actual.push(actual_move)
        if board_after_actual.is_stalemate():
            parts.append("This leads to stalemate (draw)!")
    except ValueError:
        pass

    try:
        best_move = board.parse_san(best_san)
    except ValueError:
        parts.append(f"A better move was {best_san}.")
        return " ".join(parts)

    # Check if best move delivers checkmate
    board_after_best = board.copy()
    board_after_best.push(best_move)
    if board_after_best.is_checkmate():
        parts.append(f"{best_san} was checkmate!")
        return " ".join(parts)

    # Check if best move captures a piece
    if board.is_capture(best_move):
        captured_piece = board.piece_at(best_move.to_square)
        if captured_piece is None:
            parts.append(f"{best_san} wins a pawn (en passant).")
        else:
            piece_name = chess.piece_name(captured_piece.piece_type)
            parts.append(f"You missed capturing the {piece_name} with {best_san}.")
    else:
        parts.append(f"A better move was {best_san}.")

    # Check if best move gives check
    if board_after_best.is_check():
        parts.append(f"{best_san} also gives check.")

    # Check if the actual move hangs a piece
    if board_after_actual:
        moving_piece = board.piece_at(actual_move.from_square)
        if moving_piece:
            attacked = board_after_actual.is_attacked_by(
                not board.turn, actual_move.to_square
            )
            defended = board_after_actual.is_attacked_by(
                board.turn, actual_move.to_square
            )
            if attacked and not defended:
                piece_name = chess.piece_name(moving_piece.piece_type)
                sq_name = chess.square_name(actual_move.to_square)
                parts.append(f"Your {piece_name} on {sq_name} is left undefended.")

    return " ".join(parts)


def _detect_game_phase(fen: str) -> str:
    """Detect game phase from FEN based on piece count."""
    pieces = fen.split(" ")[0]
    # Count non-pawn, non-king pieces (minor + major)
    major_minor = sum(1 for c in pieces if c in "qrbnQRBN")
    if major_minor >= 8:
        return "Opening"
    if major_minor >= 3:
        return "Middlegame"
    return "Endgame"


def _describe_advantage(score_before_cp: int | None, player_color: str) -> str:
    """Describe who has the advantage before the move."""
    if score_before_cp is None:
        return ""
    # Convert to player perspective
    player_cp = score_before_cp if player_color == "white" else -score_before_cp
    if player_cp > 200:
        return "you had a strong advantage"
    if player_cp > 50:
        return "you had a slight advantage"
    if player_cp > -50:
        return "the position was roughly equal"
    if player_cp > -200:
        return "you were slightly worse"
    return "you were in a difficult position"


def _time_pressure_context(
    player_clock: float | None, opponent_clock: float | None,
) -> str:
    """Generate time pressure context string, or empty if not relevant.

    Args:
        player_clock: Player's remaining time in seconds, or None.
        opponent_clock: Opponent's remaining time in seconds, or None.
    """
    if player_clock is None:
        return ""

    p_min = player_clock / 60

    if p_min < 2:
        if opponent_clock and opponent_clock / 60 > p_min * 2:
            o_min = opponent_clock / 60
            return (
                f"You were under severe time pressure "
                f"({p_min:.0f}min left vs {o_min:.0f}min for your opponent)."
            )
        return f"You were under time pressure ({p_min:.0f}min remaining)."

    if opponent_clock and player_clock > opponent_clock * 1.5:
        o_min = opponent_clock / 60
        return (
            f"You had more time ({p_min:.0f}min vs {o_min:.0f}min) "
            f"and could have taken longer on this move."
        )

    return ""


def _generate_context(
    category: str,
    cp_loss: int,
    was_mate: bool,
    score_after_cp: int | None,
    fen: str = "",
    score_before_cp: int | None = None,
    player_color: str = "white",
) -> str:
    """Generate a short context sentence shown BEFORE the player answers.

    Includes game phase, advantage context, and what went wrong.
    """
    score_after_is_mate = score_after_cp is not None and abs(score_after_cp) >= _MATE_CP

    phase = _detect_game_phase(fen) if fen else ""
    color_label = f"playing as {player_color.capitalize()}"
    advantage = _describe_advantage(score_before_cp, player_color) if score_before_cp is not None else ""
    if phase and advantage:
        prefix = f"{phase}, {color_label}, {advantage}."
    elif phase:
        prefix = f"{phase}, {color_label}."
    else:
        prefix = f"{color_label.capitalize()}."

    if was_mate and score_after_cp is not None and abs(score_after_cp) < 50:
        return f"{prefix} Your move threw away a winning position and led to a draw."
    if was_mate:
        return f"{prefix} Your move threw away a forced mate."
    if score_after_is_mate:
        return f"{prefix} Your move allowed your opponent to force checkmate."
    if cp_loss >= _MATE_CP:
        return f"{prefix} Your move allowed your opponent to force checkmate."

    pawns = cp_loss / 100.0
    if pawns >= 5:
        return f"{prefix} Your move lost a decisive advantage."
    if pawns >= 2:
        return f"{prefix} Your move lost significant material ({pawns:.1f} pawns)."
    if pawns >= 1:
        return f"{prefix} Your move cost about {pawns:.1f} pawns."
    return f"{prefix} Your move was inaccurate ({pawns:.1f} pawns)."


def _make_position_id(fen: str, actual_san: str) -> str:
    """Generate a stable short ID for a position + move combination."""
    data = f"{fen}:{actual_san}"
    return hashlib.sha256(data.encode()).hexdigest()[:12]


def _determine_player_color(
    game: chess.pgn.Game, lichess_user: str, chesscom_user: str | None
) -> chess.Color | None:
    """Determine which color the player was playing.

    Args:
        game: Parsed PGN game.
        lichess_user: Lichess username.
        chesscom_user: Optional chess.com username.

    Returns:
        chess.WHITE, chess.BLACK, or None if player not found.
    """
    white = game.headers.get("White", "").lower()
    black = game.headers.get("Black", "").lower()

    for username in [lichess_user.lower(), (chesscom_user or "").lower()]:
        if not username:
            continue
        if username == white:
            return chess.WHITE
        if username == black:
            return chess.BLACK

    return None


def _detect_source(game: chess.pgn.Game) -> str:
    """Detect whether a game is from Lichess or chess.com."""
    site = game.headers.get("Site", "").lower()
    if "lichess.org" in site:
        return "lichess"
    if "chess.com" in site:
        return "chess.com"
    return "unknown"


def _get_opponent(game: chess.pgn.Game, player_color: chess.Color) -> str:
    """Get the opponent's name from game headers."""
    if player_color == chess.WHITE:
        return game.headers.get("Black", "?")
    return game.headers.get("White", "?")


def extract_mistakes(
    game: chess.pgn.Game,
    engine: chess.engine.SimpleEngine,
    depth: int,
    player_color: chess.Color,
    min_cp_loss: int = INACCURACY_THRESHOLD,
) -> list[dict]:
    """Extract mistake positions from a single game.

    Runs Stockfish on every mainline position, computes centipawn loss
    for each of the player's moves, and returns positions above the threshold.

    Args:
        game: Parsed PGN game.
        engine: Running Stockfish engine.
        depth: Analysis depth.
        player_color: Which color the player was.
        min_cp_loss: Minimum cp loss to include (default: 50).

    Returns:
        List of mistake dicts ready for training_data.json.
    """
    # Build list of position data for each mainline node
    positions = []
    node = game

    while node.variations:
        board = node.board()
        next_node = node.variations[0]
        actual_move = next_node.move
        piece_count = len(board.piece_map())

        # Extract clock data (seconds remaining after this move)
        player_clock = next_node.clock()
        opponent_clock = None
        if next_node.variations:
            opponent_clock = next_node.variations[0].clock()

        # Priority: tablebase for endgame positions (<= 7 pieces)
        tb_result = None
        if piece_count <= MAX_PIECES:
            tb_result = probe_position(board.fen())

        if tb_result:
            # Tablebase: perfect result, no Stockfish needed
            # Use a synthetic score_cp for compatibility with the rest of the pipeline
            tier = tb_result.tier
            score_cp = _MATE_CP if tier == "WIN" else (-_MATE_CP if tier == "LOSS" else 0)
            if board.turn == chess.BLACK:
                score_cp = -score_cp
            positions.append({
                "fen": board.fen(),
                "turn": board.turn,
                "score_cp": score_cp,
                "is_mate": False,
                "best_san": tb_result.best_move,
                "actual_san": board.san(actual_move),
                "pv": [tb_result.best_move] if tb_result.best_move else [],
                "tb": tb_result,
                "score_after_best_cp": None,
                "player_clock": player_clock,
                "opponent_clock": opponent_clock,
            })
        else:
            # Stockfish: adaptive depth
            info = engine.analyse(board, _analysis_limit(board, depth))
            score = info.get("score")
            pv = info.get("pv", [])

            if score is None:
                node = next_node
                continue

            score_cp, is_mate = _score_to_cp(score)
            best_move = pv[0] if pv else None

            # Analyze position after best move (for accurate eval display)
            # Uses adaptive depth + tablebase probe if ≤7 pieces
            score_after_best_cp = None
            if best_move:
                board_after_best = board.copy()
                board_after_best.push(best_move)
                pc_after = len(board_after_best.piece_map())
                tb_after_best = probe_position(board_after_best.fen()) if pc_after <= MAX_PIECES else None
                if tb_after_best:
                    tier = tb_after_best.tier
                    score_after_best_cp = _MATE_CP if tier == "WIN" else (-_MATE_CP if tier == "LOSS" else 0)
                    if board_after_best.turn == chess.BLACK:
                        score_after_best_cp = -score_after_best_cp
                else:
                    info_after_best = engine.analyse(
                        board_after_best, _analysis_limit(board_after_best, depth),
                    )
                    score_ab = info_after_best.get("score")
                    if score_ab:
                        score_after_best_cp, _ = _score_to_cp(score_ab)

            # Convert PV to SAN (up to 10 moves, or full line if mate found)
            pv_limit = len(pv) if is_mate else 10
            pv_san = []
            pv_board = board.copy()
            for move in pv[:pv_limit]:
                try:
                    pv_san.append(pv_board.san(move))
                    pv_board.push(move)
                except (ValueError, AssertionError):
                    break

            positions.append({
                "fen": board.fen(),
                "turn": board.turn,
                "score_cp": score_cp,
                "is_mate": is_mate,
                "best_san": board.san(best_move) if best_move else None,
                "actual_san": board.san(actual_move),
                "pv": pv_san,
                "tb": None,
                "score_after_best_cp": score_after_best_cp,
                "player_clock": player_clock,
                "opponent_clock": opponent_clock,
            })
        node = next_node

    # Score the final position (needed for last move's cp_loss)
    board = node.board()
    piece_count = len(board.piece_map())
    tb_result = None
    if piece_count <= MAX_PIECES:
        tb_result = probe_position(board.fen())

    if tb_result:
        tier = tb_result.tier
        score_cp = _MATE_CP if tier == "WIN" else (-_MATE_CP if tier == "LOSS" else 0)
        if board.turn == chess.BLACK:
            score_cp = -score_cp
        positions.append({
            "fen": board.fen(),
            "turn": board.turn,
            "score_cp": score_cp,
            "is_mate": False,
            "best_san": None,
            "actual_san": None,
            "pv": [],
            "tb": tb_result,
        })
    else:
        info = engine.analyse(board, _analysis_limit(board, depth))
        score = info.get("score")
        if score:
            score_cp, is_mate = _score_to_cp(score)
            positions.append({
                "fen": board.fen(),
                "turn": board.turn,
                "score_cp": score_cp,
                "is_mate": is_mate,
                "best_san": None,
                "actual_san": None,
                "pv": [],
                "tb": None,
            })

    # Find the player's mistakes
    mistakes = []
    game_info = {
        "id": game.headers.get("Link", game.headers.get("Site", "")),
        "source": _detect_source(game),
        "opponent": _get_opponent(game, player_color),
        "date": game.headers.get("Date", "?"),
        "result": game.headers.get("Result", "*"),
        "opening": game.headers.get(
            "Opening", game.headers.get("Event", "?")
        ),
    }

    for i in range(len(positions) - 1):
        pos = positions[i]
        next_pos = positions[i + 1]

        # Only the player's moves
        if pos["turn"] != player_color:
            continue

        if pos["score_cp"] is None or next_pos["score_cp"] is None:
            continue

        # Skip if the played move delivers checkmate
        board = chess.Board(pos["fen"])
        try:
            actual_move = board.parse_san(pos["actual_san"])
            board.push(actual_move)
            if board.is_checkmate():
                continue
        except ValueError:
            pass

        # Determine cp_loss, context, and explanation based on source
        tb_before: TablebaseResult | None = pos.get("tb")
        tb_after: TablebaseResult | None = next_pos.get("tb")

        if tb_before and tb_after:
            # Both positions resolved by tablebase — use WDL transition
            cp_loss = tablebase_cp_loss(tb_before, tb_after, pos["turn"])
            if cp_loss < min_cp_loss:
                continue
            category = _classify_mistake(cp_loss)
            if category is None or not pos["best_san"]:
                continue
            if pos["actual_san"] == pos["best_san"]:
                continue

            piece_count = len(chess.Board(pos["fen"]).piece_map())
            p_color = "white" if player_color == chess.WHITE else "black"
            context = tablebase_context(tb_before, piece_count, p_color)
            explanation = tablebase_explanation(
                tb_before, tb_after, pos["actual_san"], pos["best_san"],
            )
            # Convert from side-to-move perspective to player perspective
            tier_before = tb_before.tier
            tier_after = tb_after.tier
            if player_color == chess.BLACK:
                _flip = {"WIN": "LOSS", "LOSS": "WIN", "DRAW": "DRAW"}
                tier_before = _flip[tier_before]
                tier_after = _flip[tier_after]
            score_before = f"TB:{tier_before.lower()}"
            score_after = f"TB:{tier_after.lower()}"
            score_after_best = score_before  # Best move preserves TB verdict
            tb_data = {
                "before": {"category": tb_before.category, "dtm": tb_before.dtm, "dtz": tb_before.dtz},
                "after": {"category": tb_after.category, "dtm": tb_after.dtm, "dtz": tb_after.dtz},
                "transition": f"{tb_before.tier} → {tb_after.tier}",
            }
        else:
            # Standard Stockfish analysis
            cp_loss = compute_cp_loss(
                pos["score_cp"], next_pos["score_cp"], pos["turn"]
            )
            if cp_loss < min_cp_loss:
                continue
            category = _classify_mistake(cp_loss)
            if category is None or not pos["best_san"]:
                continue
            if pos["actual_san"] == pos["best_san"]:
                continue

            # Pedagogical filter: skip positions already lost (no learning value)
            player_cp = pos["score_cp"] if player_color == chess.WHITE else -pos["score_cp"]
            player_cp_after = next_pos["score_cp"] if player_color == chess.WHITE else -next_pos["score_cp"]
            if player_cp < -500 and player_cp_after < -500 and not pos.get("is_mate", False):
                continue
            # Pedagogical filter: skip positions already won (no learning value)
            if player_cp > 500 and player_cp_after > 500:
                continue

            was_mate = pos.get("is_mate", False)
            score_after_cp = next_pos["score_cp"]
            board = chess.Board(pos["fen"])
            explanation = generate_explanation(
                board, pos["actual_san"], pos["best_san"], cp_loss, category,
                was_mate=was_mate,
                score_after_cp=score_after_cp,
            )
            p_color = "white" if player_color == chess.WHITE else "black"
            context = _generate_context(
                category, cp_loss, was_mate, score_after_cp,
                fen=pos["fen"], score_before_cp=pos["score_cp"], player_color=p_color,
            )
            score_before = _format_score_cp(pos["score_cp"])
            score_after = _format_score_cp(next_pos["score_cp"])
            score_after_best = _format_score_cp(pos.get("score_after_best_cp"))
            tb_data = None

        # Append time pressure context if relevant
        time_ctx = _time_pressure_context(
            pos.get("player_clock"), pos.get("opponent_clock"),
        )
        if time_ctx:
            context = f"{context} {time_ctx}"

        player_clk = pos.get("player_clock")
        opponent_clk = pos.get("opponent_clock")

        mistake = {
            "id": _make_position_id(pos["fen"], pos["actual_san"]),
            "fen": pos["fen"],
            "player_color": "white" if player_color == chess.WHITE else "black",
            "player_move": pos["actual_san"],
            "best_move": pos["best_san"],
            "context": context,
            "score_before": score_before,
            "score_after": score_after,
            "score_after_best": score_after_best,
            "cp_loss": cp_loss,
            "category": category,
            "explanation": explanation,
            "acceptable_moves": [pos["best_san"]],
            "pv": pos.get("pv", []),
            "game": game_info,
            "clock": {"player": player_clk, "opponent": opponent_clk} if player_clk is not None else None,
        }
        if tb_data:
            mistake["tablebase"] = tb_data
        mistakes.append(mistake)

    return mistakes



def _analyze_game_worker(
    pgn_str: str,
    sf_path_str: str,
    depth: int,
    player_color: chess.Color,
    idx: int,
    total: int,
    label: str,
) -> tuple[int, int, str, list[dict], float]:
    """Worker function for parallel game analysis.

    Each worker opens its own Stockfish instance, analyzes one game,
    and returns the results. Designed for ProcessPoolExecutor.
    """
    game = chess.pgn.read_game(io.StringIO(pgn_str))
    engine = chess.engine.SimpleEngine.popen_uci(sf_path_str)
    try:
        start = time.time()
        mistakes = extract_mistakes(game, engine, depth, player_color)
        elapsed = time.time() - start
    finally:
        engine.quit()
    return idx, total, label, mistakes, elapsed


def _load_existing_training_data(path: Path) -> dict | None:
    """Load existing training_data.json if it exists."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError):
        return None


class TrainingInterrupted(Exception):
    """Raised when training is cancelled via the interrupt signal."""


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically: temp file, fsync, os.replace."""
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


_SEVERITY = {"blunder": 0, "mistake": 1, "inaccuracy": 2}


def _build_output(
    positions: dict[str, dict],
    lichess_user: str,
    chesscom_user: str,
    analyzed_game_ids: set[str] | None = None,
) -> dict:
    """Build the training_data.json dict from positions map."""
    sorted_pos = sorted(
        positions.values(),
        key=lambda m: (_SEVERITY.get(m["category"], 3), -m["cp_loss"]),
    )
    return {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "player": {"lichess": lichess_user, "chesscom": chesscom_user or ""},
        "positions": sorted_pos,
        "analyzed_game_ids": sorted(analyzed_game_ids) if analyzed_game_ids else [],
    }


def prepare_training_data(
    *,
    max_games: int = 20,
    depth: int = 18,
    engine_path: str | None = None,
    fresh: bool = False,
    on_progress: Callable[[dict], None] | None = None,
    cancel: threading.Event | None = None,
) -> None:
    """Fetch games, analyze with Stockfish, extract mistakes, export training JSON.

    By default, merges with existing training data (incremental mode).
    Only new games are analyzed. SRS progress is preserved.

    Args:
        max_games: Maximum games to fetch per source.
        depth: Stockfish analysis depth.
        engine_path: Override path to Stockfish binary.
        fresh: If True, discard existing data and start from scratch.
        on_progress: Optional callback for structured progress events. When None,
            all existing print() output is preserved unchanged.
    """
    def _emit(event: dict) -> None:
        if on_progress:
            on_progress(event)

    config = load_config()
    players = config.get("players", {})
    lichess_user = players.get("lichess", "")
    chesscom_user = players.get("chesscom")

    if not lichess_user and not chesscom_user:
        raise RuntimeError(
            "No player configured. Run 'chess-self-coach setup' to set your Lichess and/or chess.com username."
        )

    # Find Stockfish
    if engine_path:
        sf_path = Path(engine_path)
        if not sf_path.exists():
            raise FileNotFoundError(f"Engine not found: {sf_path}")
    else:
        sf_path = find_stockfish(config)
        expected = config.get("stockfish", {}).get("expected_version")
        version = check_stockfish_version(sf_path, expected)
        print(f"  Using {version} at {sf_path}")
        _emit({"phase": "init", "message": f"Using {version}"})

    root = _find_project_root()
    output_path = root / "training_data.json"

    # Load existing data (incremental mode)
    existing_data = None if fresh else _load_existing_training_data(output_path)
    existing_game_ids: set[str] = set()
    existing_positions: dict[str, dict] = {}  # id -> position (preserves SRS)
    if existing_data:
        # Primary source: explicit list (handles 0-mistake games)
        for gid in existing_data.get("analyzed_game_ids", []):
            if gid and gid != "?":
                existing_game_ids.add(gid)
        # Fallback: also extract from positions (backward compat with old files)
        for pos in existing_data.get("positions", []):
            existing_positions[pos["id"]] = pos
            game_id = pos.get("game", {}).get("id", "")
            if game_id and game_id != "?":
                existing_game_ids.add(game_id)
        if existing_game_ids:
            print(f"  Loaded {len(existing_positions)} existing position(s) from {len(existing_game_ids)} game(s)")

    # Fetch games
    print("\n  Fetching games...")
    _emit({"phase": "fetch", "message": "Fetching games...", "percent": 5})
    all_games: list[chess.pgn.Game] = []

    if lichess_user:
        lichess_games = fetch_lichess_games(lichess_user, max_games)
        all_games.extend(lichess_games)

    if chesscom_user:
        chesscom_games = fetch_chesscom_games(chesscom_user, max_games)
        all_games.extend(chesscom_games)

    if not all_games:
        print("  No games found.")
        _emit({"phase": "done", "message": "No games found.", "percent": 100})
        return

    # Filter out already-analyzed games
    new_games = []
    for game in all_games:
        game_id = game.headers.get("Link", game.headers.get("Site", ""))
        if game_id and game_id in existing_game_ids:
            continue
        new_games.append(game)

    skipped = len(all_games) - len(new_games)
    if skipped:
        print(f"  Skipped {skipped} already-analyzed game(s)")

    _emit({"phase": "fetch", "message": f"Found {len(all_games)} game(s) ({len(new_games)} new)", "percent": 10})

    if not new_games:
        print("  No new games to analyze.")
        if existing_data:
            print(f"  Existing training data unchanged ({len(existing_positions)} positions)")
        _emit({"phase": "done", "message": f"No new games. {len(existing_positions)} positions unchanged.", "percent": 100})
        return

    # Build analysis tasks (filter games where player is identifiable)
    tasks = []
    task_game_ids: list[str] = []
    skipped_color = 0
    for i, game in enumerate(new_games):
        game_id = game.headers.get("Link", game.headers.get("Site", ""))
        if game_id == "?":
            game_id = ""
        player_color = _determine_player_color(game, lichess_user, chesscom_user)
        if player_color is None:
            white = game.headers.get("White", "?")
            black = game.headers.get("Black", "?")
            print(f"  Skipped {white} vs {black}: player not found in game headers")
            skipped_color += 1
            if game_id:
                existing_game_ids.add(game_id)
            continue
        white = game.headers.get("White", "?")
        black = game.headers.get("Black", "?")
        exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        pgn_str = game.accept(exporter)
        task_game_ids.append(game_id)
        tasks.append((pgn_str, str(sf_path), depth, player_color, i + 1, len(new_games), f"{white} vs {black}"))

    if not tasks:
        if skipped_color:
            print(f"  No analyzable games ({skipped_color} skipped: player not in headers)")
        else:
            print("  No analyzable games.")
        _atomic_write_json(
            output_path,
            _build_output(existing_positions, lichess_user, chesscom_user, existing_game_ids),
        )
        _emit({"phase": "done", "message": f"No analyzable games. {len(existing_positions)} positions unchanged.", "percent": 100})
        return

    workers = worker_count()
    workers = min(workers, len(tasks))
    print(f"\n  Analyzing {len(tasks)} new game(s) with Stockfish (depth {depth}, {workers} workers)...")
    print("  This may take several minutes...\n")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_count = 0
    done_count = 0
    total_tasks = len(tasks)

    pool = ProcessPoolExecutor(max_workers=workers)
    try:
        future_to_gid = {}
        for task, gid in zip(tasks, task_game_ids):
            f = pool.submit(_analyze_game_worker, *task)
            future_to_gid[f] = gid
        wall_start = time.time()
        for future in as_completed(future_to_gid):
            gid = future_to_gid[future]
            done_count += 1
            try:
                idx, total, label, mistakes, elapsed = future.result()
            except Exception as exc:
                print(f"  [{done_count}/{total_tasks}] Error: {exc}")
                continue  # Don't track — will be retried on next run

            # Only track after successful analysis
            if gid:
                existing_game_ids.add(gid)

            # Merge this game's positions immediately (preserve SRS)
            for m in mistakes:
                if m["id"] not in existing_positions:
                    m["srs"] = {
                        "interval": 0,
                        "ease": 2.5,
                        "next_review": today,
                        "history": [],
                    }
                    existing_positions[m["id"]] = m
                    new_count += 1

            # Atomic incremental write — crash-safe
            _atomic_write_json(
                output_path,
                _build_output(existing_positions, lichess_user, chesscom_user, existing_game_ids),
            )

            wall_elapsed = time.time() - wall_start
            avg_per_game = wall_elapsed / done_count
            remaining = avg_per_game * (total_tasks - done_count)
            eta_min, eta_sec = divmod(int(remaining), 60)
            eta_str = f"{eta_min}m{eta_sec:02d}s" if eta_min else f"{eta_sec}s"

            print(
                f"  [{done_count}/{total_tasks}] {label}... "
                f"{len(mistakes)} mistake(s) ({elapsed:.1f}s) "
                f"— ETA {eta_str}"
            )
            # Progress: 15% to 90% spread across analysis tasks
            pct = 15 + int(75 * done_count / total_tasks)
            _emit({
                "phase": "analyze",
                "message": f"Analyzing {done_count}/{total_tasks}: {label}",
                "percent": pct,
                "current": done_count,
                "total": total_tasks,
            })

            # Check cancel signal after each game
            if cancel and cancel.is_set():
                pool.shutdown(wait=False, cancel_futures=True)
                raise TrainingInterrupted(
                    f"Interrupted. Saved {len(existing_positions)} positions "
                    f"({done_count}/{total_tasks} games analyzed)."
                )
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    total = len(existing_positions)
    all_positions = _build_output(existing_positions, lichess_user, chesscom_user, existing_game_ids)["positions"]
    print(f"\n  Training data exported: {output_path}")
    print(f"  Total positions: {total} ({new_count} new)")
    blunders = sum(1 for m in all_positions if m["category"] == "blunder")
    mistake_count = sum(1 for m in all_positions if m["category"] == "mistake")
    inaccuracies = sum(1 for m in all_positions if m["category"] == "inaccuracy")
    print(f"    Blunders: {blunders}")
    print(f"    Mistakes: {mistake_count}")
    print(f"    Inaccuracies: {inaccuracies}")
    _emit({
        "phase": "done",
        "message": f"Done! {total} positions ({blunders} blunders, {mistake_count} mistakes, {inaccuracies} inaccuracies)",
        "percent": 100,
    })


def refresh_explanations() -> None:
    """Regenerate explanations in training_data.json without re-running Stockfish.

    Reads existing positions, rebuilds explanations using generate_explanation(),
    and writes back. SRS progress and all other fields are preserved.
    """
    root = _find_project_root()
    data_path = root / "training_data.json"

    if not data_path.exists():
        print("No training data found. Run: chess-self-coach train --prepare", file=sys.stderr)
        sys.exit(1)

    with open(data_path) as f:
        data = json.load(f)

    positions = data.get("positions", [])

    # Remove invalid positions (player_move == best_move)
    before_count = len(positions)
    positions = [p for p in positions if p["player_move"] != p["best_move"]]
    removed = before_count - len(positions)
    if removed:
        data["positions"] = positions
        print(f"  Removed {removed} invalid position(s) (player_move == best_move)")

    # Remove positions where both moves win or both lose (no learning value)
    def _parse_score_cp(s: str) -> int | None:
        try:
            return int(float(s) * 100)
        except (ValueError, TypeError):
            return None

    before_count = len(positions)
    filtered = []
    for p in positions:
        sb = _parse_score_cp(p.get("score_before", ""))
        sa = _parse_score_cp(p.get("score_after", ""))
        if sb is None or sa is None:
            filtered.append(p)
            continue
        mul = 1 if p.get("player_color") == "white" else -1
        player_before = sb * mul
        player_after = sa * mul
        if player_before > 500 and player_after > 500:
            continue
        if player_before < -500 and player_after < -500:
            continue
        filtered.append(p)
    positions = filtered
    removed_decisive = before_count - len(positions)
    if removed_decisive:
        data["positions"] = positions
        print(f"  Removed {removed_decisive} position(s) already decisive (both win or both lose)")

    # Fix tablebase scores for Black: convert from side-to-move to player perspective
    _tb_flip = {"TB:win": "TB:loss", "TB:loss": "TB:win"}
    tb_fixed = 0
    for pos in positions:
        if "tablebase" not in pos or pos.get("player_color") != "black":
            continue
        for key in ("score_before", "score_after", "score_after_best"):
            val = pos.get(key)
            if val in _tb_flip:
                pos[key] = _tb_flip[val]
                tb_fixed += 1
    if tb_fixed:
        data["positions"] = positions
        print(f"  Fixed {tb_fixed} tablebase score(s) (side-to-move → player perspective)")

    updated = 0
    for pos in positions:
        board = chess.Board(pos["fen"])

        # Skip tablebase-resolved positions — their context/explanation
        # are generated by tablebase_context/tablebase_explanation and
        # cannot be regenerated without re-probing the API.
        if "tablebase" in pos:
            continue

        # Parse scores to cp
        score_before_str = pos.get("score_before", "+0.00")
        score_after_str = pos.get("score_after", "+0.00")
        try:
            score_before_cp = int(float(score_before_str) * 100)
        except (ValueError, TypeError):
            score_before_cp = None
        try:
            score_after_cp = int(float(score_after_str) * 100)
        except (ValueError, TypeError):
            score_after_cp = None

        was_mate = score_before_cp is not None and abs(score_before_cp) >= _MATE_CP

        new_explanation = generate_explanation(
            board, pos["player_move"], pos["best_move"],
            pos["cp_loss"], pos["category"],
            was_mate=was_mate, score_after_cp=score_after_cp,
        )
        new_context = _generate_context(
            pos["category"], pos["cp_loss"], was_mate, score_after_cp,
            fen=pos["fen"], score_before_cp=score_before_cp,
            player_color=pos.get("player_color", "white"),
        )
        # Fix source if "unknown" and game.id hints at the platform
        game = pos.get("game", {})
        game_id = game.get("id", "")
        if game.get("source") == "unknown":
            if "lichess.org" in game_id.lower():
                game["source"] = "lichess"
            elif "chess.com" in game_id.lower():
                game["source"] = "chess.com"

        if new_explanation != pos.get("explanation") or new_context != pos.get("context"):
            pos["explanation"] = new_explanation
            pos["context"] = new_context
            updated += 1

    _atomic_write_json(data_path, data)

    print(f"  Refreshed {updated}/{len(positions)} explanation(s) in {data_path}")
    if updated:
        print("  💡 Run /review-training to verify text quality")


def get_stats_data(project_root: Path) -> dict:
    """Compute training statistics from training_data.json.

    Args:
        project_root: Path to the project root containing training_data.json.

    Returns:
        Dict with keys: generated, total, by_category, by_source.

    Raises:
        FileNotFoundError: If training_data.json does not exist.
    """
    data_path = project_root / "training_data.json"
    if not data_path.exists():
        raise FileNotFoundError(f"No training data at {data_path}")

    with open(data_path) as f:
        data = json.load(f)

    positions = data.get("positions", [])

    categories: dict[str, int] = {}
    for p in positions:
        cat = p.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    sources: dict[str, int] = {}
    for p in positions:
        src = p.get("game", {}).get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1

    return {
        "generated": data.get("generated", "unknown"),
        "total": len(positions),
        "by_category": categories,
        "by_source": sources,
    }


def print_stats() -> None:
    """Show training progress from training_data.json."""
    root = _find_project_root()
    try:
        stats = get_stats_data(root)
    except FileNotFoundError:
        print(
            "No training data found. Run: chess-self-coach train --prepare",
            file=sys.stderr,
        )
        sys.exit(1)

    if stats["total"] == 0:
        print("  No positions in training data.")
        return

    print("\n  Training Data Stats")
    print(f"  Generated: {stats['generated']}")
    print(f"  Total positions: {stats['total']}")

    print("\n  By category:")
    for cat in ["blunder", "mistake", "inaccuracy"]:
        print(f"    {cat.capitalize()}: {stats['by_category'].get(cat, 0)}")

    print("\n  By source:")
    for src, count in sorted(stats["by_source"].items()):
        print(f"    {src}: {count}")
