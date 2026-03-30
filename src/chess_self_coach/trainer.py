"""Training mode: explanation generation, move classification, and training data utilities.

Pure functions for generating rule-based explanations, classifying mistakes by
centipawn loss, and managing training_data.json (stats, refresh). The heavy
analysis pipeline lives in analysis.py (Phase 1: collection, Phase 2: derivation).
"""

from __future__ import annotations

import json
import sys

import chess

from chess_self_coach.io import atomic_write_json
from chess_self_coach.config import training_data_path
from chess_self_coach.tablebase import (
    TablebaseResult,
    tablebase_context,
    tablebase_explanation,
)
from chess_self_coach.constants import (
    BLUNDER_THRESHOLD,
    DOMINATED_POSITION_CP,
    INACCURACY_THRESHOLD,
    MATE_CP,
    MAX_PV_MOVES,
    MISTAKE_THRESHOLD,
)


def _format_score_cp(cp: int | None) -> str:
    """Format centipawn value as score string like '+0.32'."""
    if cp is None:
        return "+0.00"
    value = cp / 100.0
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}"



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
    if cp_loss >= MATE_CP or was_mate:
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
    score_after_is_mate = score_after_cp is not None and abs(score_after_cp) >= MATE_CP

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
    score_after_is_mate = score_after_cp is not None and abs(score_after_cp) >= MATE_CP

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
    if cp_loss >= MATE_CP:
        return f"{prefix} Your move allowed your opponent to force checkmate."

    pawns = cp_loss / 100.0
    if pawns >= 5:
        return f"{prefix} Your move lost a decisive advantage."
    if pawns >= 2:
        return f"{prefix} Your move lost significant material ({pawns:.1f} pawns)."
    if pawns >= 1:
        return f"{prefix} Your move cost about {pawns:.1f} pawns."
    return f"{prefix} Your move was inaccurate ({pawns:.1f} pawns)."


def refresh_explanations() -> None:
    """Regenerate explanations in training_data.json without re-running Stockfish.

    Reads existing positions, rebuilds explanations using generate_explanation(),
    and writes back. SRS progress and all other fields are preserved.
    """
    data_path = training_data_path()

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
        if player_before > DOMINATED_POSITION_CP and player_after > DOMINATED_POSITION_CP:
            continue
        if player_before < -DOMINATED_POSITION_CP and player_after < -DOMINATED_POSITION_CP:
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

        # Tablebase-resolved positions: regenerate from stored tablebase data
        tb_data = pos.get("tablebase")
        if tb_data:
            tb_before = tb_data.get("before")
            tb_after = tb_data.get("after")
            if tb_before:
                tb_res_before = TablebaseResult(
                    category=tb_before["category"],
                    dtz=tb_before.get("dtz"),
                    dtm=tb_before.get("dtm"),
                    best_move=None,
                )
                new_context = tablebase_context(
                    tb_res_before, len(board.piece_map()),
                    pos.get("player_color", "white"),
                )
                if tb_after:
                    tb_res_after = TablebaseResult(
                        category=tb_after["category"],
                        dtz=tb_after.get("dtz"),
                        dtm=tb_after.get("dtm"),
                        best_move=None,
                    )
                    new_explanation = tablebase_explanation(
                        tb_res_before, tb_res_after,
                        pos["player_move"], pos["best_move"],
                    )
                else:
                    new_explanation = pos.get("explanation", "")
            else:
                continue
        else:
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

            was_mate = score_before_cp is not None and abs(score_before_cp) >= MATE_CP

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

    atomic_write_json(data_path, data)

    print(f"  Refreshed {updated}/{len(positions)} explanation(s) in {data_path}")
    if updated:
        print("  Run /review-training to verify text quality")


def get_stats_data() -> dict:
    """Compute training statistics from training_data.json.

    Returns:
        Dict with keys: generated, total, by_category, by_source.

    Raises:
        FileNotFoundError: If training_data.json does not exist.
    """
    data_path = training_data_path()
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
    try:
        stats = get_stats_data()
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
