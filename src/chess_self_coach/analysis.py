"""Full game analysis: collect raw data from Stockfish, tablebase, and opening explorer.

Phase 1 collects all per-move evaluation data and stores it in analysis_data.json.
Phase 2 annotates moves and derives training_data.json from the raw data.

This decoupling allows re-running Phase 2 (cheap) without re-running Phase 1 (expensive).
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.engine
import chess.pgn

from chess_self_coach import worker_count
from chess_self_coach.config import _find_project_root
from chess_self_coach.opening_explorer import query_opening
from chess_self_coach.tablebase import MAX_PIECES, probe_position_full

# Sentinel for mate scores (centipawns)
_MATE_CP = 10000


# Default analysis limits matching trainer._analysis_limit() hardcoded values
_DEFAULT_LIMITS: dict[str, dict[str, float | int]] = {
    "kings_pawns_le7": {"time": 6.0, "depth": 60},
    "pieces_le7": {"time": 5.0, "depth": 50},
    "pieces_le12": {"time": 4.0, "depth": 40},
    "default": {"depth": 18},
}


@dataclass
class AnalysisSettings:
    """Engine and analysis configuration for full game analysis.

    Attributes:
        threads: Number of Stockfish threads. 0 means auto (cpu_count - 1).
        hash_mb: Stockfish hash table size in megabytes.
        limits: Depth/time limits per piece-count bracket.
    """

    threads: int = 0
    hash_mb: int = 1024
    limits: dict[str, dict[str, float | int]] = field(default_factory=lambda: dict(_DEFAULT_LIMITS))

    @classmethod
    def from_config(cls, config: dict) -> AnalysisSettings:
        """Build settings from a config dict (from config.json).

        Args:
            config: Full config dict. Reads the 'analysis_engine' key.

        Returns:
            AnalysisSettings with values from config, defaults for missing keys.
        """
        section = config.get("analysis_engine", {})
        threads_raw = section.get("threads", "auto")
        if threads_raw == "auto" or threads_raw == 0:
            threads = 0
        else:
            threads = int(threads_raw)
        return cls(
            threads=threads,
            hash_mb=int(section.get("hash_mb", 1024)),
            limits=section.get("limits", dict(_DEFAULT_LIMITS)),
        )

    @property
    def resolved_threads(self) -> int:
        """Actual thread count (resolves 0/auto to cpu_count - 1)."""
        return self.threads if self.threads > 0 else worker_count()

    def to_dict(self) -> dict:
        """Serialize to a dict suitable for JSON storage.

        Returns:
            Dict with threads (resolved to actual count), hash_mb, limits.
        """
        return {
            "threads": self.resolved_threads,
            "hash_mb": self.hash_mb,
            "limits": self.limits,
        }


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically: temp file, fsync, os.replace.

    Args:
        path: Target file path.
        data: Dict to serialize as JSON.
    """
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def load_analysis_data(path: Path | None = None) -> dict:
    """Load analysis_data.json, returning empty structure if not found.

    Args:
        path: Path to analysis_data.json. Defaults to project root.

    Returns:
        Parsed dict with at least {version, player, games}.
    """
    if path is None:
        path = _find_project_root() / "analysis_data.json"
    if not path.exists():
        return {"version": "1.0", "player": {}, "games": {}}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError):
        return {"version": "1.0", "player": {}, "games": {}}


def save_analysis_data(data: dict, path: Path | None = None) -> None:
    """Atomically write analysis_data.json.

    Args:
        data: Full analysis data dict.
        path: Target path. Defaults to project root.
    """
    if path is None:
        path = _find_project_root() / "analysis_data.json"
    data["version"] = "1.0"
    _atomic_write_json(path, data)


def analysis_data_path() -> Path:
    """Return the default path for analysis_data.json.

    Returns:
        Path to analysis_data.json in the project root.
    """
    return _find_project_root() / "analysis_data.json"


def settings_match(stored: dict, current: dict) -> bool:
    """Check if stored analysis settings match current settings.

    Used to skip re-analysis of games already analyzed with identical settings.

    Args:
        stored: Settings dict from a previously analyzed game.
        current: Current settings dict.

    Returns:
        True if settings are equivalent.
    """
    return (
        stored.get("threads") == current.get("threads")
        and stored.get("hash_mb") == current.get("hash_mb")
        and stored.get("limits") == current.get("limits")
    )


# ---------------------------------------------------------------------------
# Phase 1: Raw data collection
# ---------------------------------------------------------------------------


def _analysis_limit_from_settings(
    board: chess.Board, limits: dict[str, dict[str, float | int]]
) -> chess.engine.Limit:
    """Build a chess.engine.Limit from configurable settings.

    Args:
        board: Current board position.
        limits: Limits dict from AnalysisSettings.

    Returns:
        chess.engine.Limit with appropriate depth/time for the position.
    """
    piece_count = len(board.piece_map())
    kings_and_pawns = all(
        p.piece_type in (chess.KING, chess.PAWN) for p in board.piece_map().values()
    )
    if kings_and_pawns and piece_count <= 7:
        lim = limits.get("kings_pawns_le7", {})
    elif piece_count <= 7:
        lim = limits.get("pieces_le7", {})
    elif piece_count <= 12:
        lim = limits.get("pieces_le12", {})
    else:
        lim = limits.get("default", {})

    kwargs: dict[str, float | int] = {}
    if "depth" in lim:
        kwargs["depth"] = int(lim["depth"])
    if "time" in lim:
        kwargs["time"] = float(lim["time"])
    return chess.engine.Limit(**kwargs) if kwargs else chess.engine.Limit(depth=18)


def _score_to_cp(score: chess.engine.PovScore) -> tuple[int | None, bool, int | None]:
    """Convert a PovScore to centipawns from White's perspective.

    Args:
        score: Engine PovScore.

    Returns:
        Tuple of (centipawns, is_mate, mate_in).
        mate_in is positive if White mates, negative if Black mates.
    """
    white = score.white()
    if white.is_mate():
        mate = white.mate()
        cp = _MATE_CP if mate > 0 else -_MATE_CP
        return cp, True, mate
    return white.score(), False, None


def _extract_eval(info: dict, board: chess.Board) -> dict:
    """Extract full evaluation data from a Stockfish info dict.

    Args:
        info: Result from engine.analyse().
        board: Board position that was analyzed (for PV SAN conversion).

    Returns:
        Dict with score_cp, is_mate, mate_in, depth, seldepth, nodes, nps,
        time_ms, tbhits, hashfull, pv_san, pv_uci, best_move_san, best_move_uci.
    """
    score = info.get("score")
    if score is None:
        return {
            "score_cp": None, "is_mate": False, "mate_in": None,
            "depth": None, "seldepth": None, "nodes": None, "nps": None,
            "time_ms": None, "tbhits": None, "hashfull": None,
            "pv_san": [], "pv_uci": [],
            "best_move_san": None, "best_move_uci": None,
        }

    score_cp, is_mate, mate_in = _score_to_cp(score)
    pv = info.get("pv", [])

    # Convert full PV to SAN and UCI
    pv_san: list[str] = []
    pv_uci: list[str] = []
    pv_board = board.copy()
    for move in pv:
        try:
            pv_san.append(pv_board.san(move))
            pv_uci.append(move.uci())
            pv_board.push(move)
        except (ValueError, AssertionError):
            break

    best_move = pv[0] if pv else None
    best_san = board.san(best_move) if best_move else None
    best_uci = best_move.uci() if best_move else None

    # Time: python-chess reports seconds as float, convert to ms
    time_s = info.get("time")
    time_ms = int(time_s * 1000) if time_s is not None else None

    return {
        "score_cp": score_cp,
        "is_mate": is_mate,
        "mate_in": mate_in,
        "depth": info.get("depth"),
        "seldepth": info.get("seldepth"),
        "nodes": info.get("nodes"),
        "nps": info.get("nps"),
        "time_ms": time_ms,
        "tbhits": info.get("tbhits"),
        "hashfull": info.get("hashfull"),
        "pv_san": pv_san,
        "pv_uci": pv_uci,
        "best_move_san": best_san,
        "best_move_uci": best_uci,
    }


def _extract_eval_score_only(info: dict) -> dict:
    """Extract only the score from a Stockfish info dict (for eval_after_best).

    Args:
        info: Result from engine.analyse().

    Returns:
        Dict with score_cp, is_mate, mate_in only.
    """
    score = info.get("score")
    if score is None:
        return {"score_cp": None, "is_mate": False, "mate_in": None}
    score_cp, is_mate, mate_in = _score_to_cp(score)
    return {"score_cp": score_cp, "is_mate": is_mate, "mate_in": mate_in}


def _tb_to_eval(tb_data: dict, board_turn: chess.Color) -> dict:
    """Convert tablebase data to a pseudo eval_before/eval_after dict.

    Args:
        tb_data: Full tablebase response from probe_position_full().
        board_turn: Side to move in the position.

    Returns:
        Dict matching the eval structure (score_cp, is_mate, etc.)
        with null engine-specific fields.
    """
    tier = tb_data.get("tier", "DRAW")
    cp = _MATE_CP if tier == "WIN" else (-_MATE_CP if tier == "LOSS" else 0)
    if board_turn == chess.BLACK:
        cp = -cp

    best_move_data = tb_data.get("moves", [{}])[0] if tb_data.get("moves") else {}
    return {
        "score_cp": cp,
        "is_mate": tier != "DRAW" and tb_data.get("dtm") is not None,
        "mate_in": tb_data.get("dtm"),
        "depth": None, "seldepth": None, "nodes": None, "nps": None,
        "time_ms": None, "tbhits": None, "hashfull": None,
        "pv_san": [best_move_data.get("san")] if best_move_data.get("san") else [],
        "pv_uci": [best_move_data.get("uci")] if best_move_data.get("uci") else [],
        "best_move_san": best_move_data.get("san"),
        "best_move_uci": best_move_data.get("uci"),
    }


def collect_game_data(
    game: chess.pgn.Game,
    engine: chess.engine.SimpleEngine,
    player_color: chess.Color,
    settings: AnalysisSettings,
    lichess_token: str | None = None,
) -> dict:
    """Collect full per-move analysis data for one game (Phase 1).

    Runs Stockfish, Lichess tablebase, and Opening Explorer on every position.
    Stores all raw data with maximum granularity — no filtering, no annotation.

    Args:
        game: Parsed PGN game.
        engine: Running Stockfish engine (already configured with threads/hash).
        player_color: Which color the player was.
        settings: Analysis settings (for limits and storage).
        lichess_token: Lichess API token for Opening Explorer. None to skip.

    Returns:
        Dict with game headers, settings, and moves[] array ready for
        storage in analysis_data.json.
    """
    limits = settings.limits
    moves_data: list[dict] = []

    # Collect all (fen, move_uci) pairs for opening explorer batch query
    fens_and_moves: list[tuple[str, str]] = []
    node = game
    while node.variations:
        board = node.board()
        next_node = node.variations[0]
        fens_and_moves.append((board.fen(), next_node.move.uci()))
        node = next_node

    # Query Opening Explorer for opening-phase positions (stops at departure)
    explorer_results: list[dict | None] = [None] * len(fens_and_moves)
    if lichess_token:
        from chess_self_coach.opening_explorer import query_opening_sequence

        explorer_results = query_opening_sequence(fens_and_moves, lichess_token)

    # Walk through the game and collect eval data for each move
    node = game
    ply = 0
    # Cache: eval_before for current position (reused as eval_after of previous move)
    cached_eval: dict | None = None
    cached_tb: dict | None = None
    prev_player_clock: float | None = None
    prev_opponent_clock: float | None = None

    while node.variations:
        board = node.board()
        next_node = node.variations[0]
        actual_move = next_node.move
        piece_count = len(board.piece_map())
        side = "white" if board.turn == chess.WHITE else "black"

        # --- Board enrichments ---
        board_after = board.copy()
        board_after.push(actual_move)
        is_check = board_after.is_check()
        is_capture = board.is_capture(actual_move)
        is_castling = board.is_castling(actual_move)
        is_en_passant = board.is_en_passant(actual_move)
        is_promotion = actual_move.promotion is not None
        promoted_to = None
        if is_promotion:
            promoted_to = chess.piece_symbol(actual_move.promotion)

        # --- Clock data ---
        player_clock = next_node.clock()
        opponent_clock = None
        if next_node.variations:
            opponent_clock = next_node.variations[0].clock()

        # Compute time spent (difference from previous clock reading for the same side)
        time_spent = None
        if side == ("white" if player_color == chess.WHITE else "black"):
            # Player's move
            if player_clock is not None and prev_player_clock is not None:
                time_spent = prev_player_clock - player_clock
        else:
            # Opponent's move
            if opponent_clock is not None and prev_opponent_clock is not None:
                time_spent = prev_opponent_clock - opponent_clock

        # --- Eval source + eval_before ---
        tb_before = None
        eval_source = "stockfish"

        if piece_count <= MAX_PIECES:
            tb_before = probe_position_full(board.fen())

        if cached_eval is not None:
            eval_before = cached_eval
            if cached_tb is not None:
                tb_before = cached_tb
                eval_source = "tablebase" if cached_eval.get("depth") is None else "stockfish+tablebase"
        elif tb_before:
            eval_before = _tb_to_eval(tb_before, board.turn)
            eval_source = "tablebase"
        else:
            info = engine.analyse(board, _analysis_limit_from_settings(board, limits))
            eval_before = _extract_eval(info, board)
            if tb_before:
                eval_source = "stockfish+tablebase"

        # --- Eval after actual move (will be cached as eval_before for next ply) ---
        board_after_fen = board_after.fen()
        pc_after = len(board_after.piece_map())
        tb_after = None

        if pc_after <= MAX_PIECES:
            tb_after = probe_position_full(board_after_fen)

        if tb_after:
            eval_after = _tb_to_eval(tb_after, board_after.turn)
            cached_eval = eval_after
            cached_tb = tb_after
        else:
            info_after = engine.analyse(
                board_after, _analysis_limit_from_settings(board_after, limits),
            )
            eval_after = _extract_eval(info_after, board_after)
            cached_eval = eval_after
            cached_tb = None

        # --- Eval after best move (only if best differs from actual) ---
        eval_after_best: dict | None = None
        best_uci = eval_before.get("best_move_uci")
        if best_uci and best_uci != actual_move.uci():
            best_move_obj = chess.Move.from_uci(best_uci)
            board_after_best = board.copy()
            board_after_best.push(best_move_obj)
            pc_ab = len(board_after_best.piece_map())
            tb_ab = probe_position_full(board_after_best.fen()) if pc_ab <= MAX_PIECES else None
            if tb_ab:
                eval_after_best = {
                    "score_cp": _tb_to_eval(tb_ab, board_after_best.turn)["score_cp"],
                    "is_mate": _tb_to_eval(tb_ab, board_after_best.turn)["is_mate"],
                    "mate_in": _tb_to_eval(tb_ab, board_after_best.turn)["mate_in"],
                }
            else:
                info_ab = engine.analyse(
                    board_after_best,
                    _analysis_limit_from_settings(board_after_best, limits),
                )
                eval_after_best = _extract_eval_score_only(info_ab)
        elif best_uci and best_uci == actual_move.uci():
            # Best move == actual move: eval_after_best = eval_after
            eval_after_best = {
                "score_cp": eval_after["score_cp"],
                "is_mate": eval_after["is_mate"],
                "mate_in": eval_after.get("mate_in"),
            }

        # --- cp_loss ---
        cp_loss = 0
        before_cp = eval_before.get("score_cp")
        after_cp = eval_after.get("score_cp")
        if before_cp is not None and after_cp is not None:
            if board.turn == chess.WHITE:
                cp_loss = max(0, before_cp - after_cp)
            else:
                cp_loss = max(0, after_cp - before_cp)

        # --- Tablebase: store full responses (remove redundant for after) ---
        tb_before_stored = tb_before
        tb_after_stored = tb_after

        # --- Opening Explorer ---
        explorer_data = explorer_results[ply] if ply < len(explorer_results) else None

        # --- Build move dict ---
        move_dict = {
            "ply": ply + 1,
            "fen_before": board.fen(),
            "fen_after": board_after_fen,
            "move_san": board.san(actual_move),
            "move_uci": actual_move.uci(),
            "side": side,
            "eval_source": eval_source,
            "eval_before": eval_before,
            "eval_after": eval_after,
            "eval_after_best": eval_after_best,
            "tablebase_before": tb_before_stored,
            "tablebase_after": tb_after_stored,
            "opening_explorer": explorer_data,
            "cp_loss": cp_loss,
            "board": {
                "piece_count": piece_count,
                "is_check": is_check,
                "is_capture": is_capture,
                "is_castling": is_castling,
                "is_en_passant": is_en_passant,
                "is_promotion": is_promotion,
                "promoted_to": promoted_to,
                "legal_moves_count": len(list(board.legal_moves)),
            },
            "clock": {
                "player": player_clock,
                "opponent": opponent_clock,
                "time_spent": round(time_spent, 1) if time_spent is not None else None,
            },
        }
        moves_data.append(move_dict)

        # Update state for next iteration
        if side == ("white" if player_color == chess.WHITE else "black"):
            prev_player_clock = player_clock
        else:
            prev_opponent_clock = opponent_clock

        ply += 1
        node = next_node

    # --- Build game-level dict ---
    p_color = "white" if player_color == chess.WHITE else "black"
    game_id = game.headers.get("Link", game.headers.get("Site", ""))
    source = "lichess" if "lichess.org" in game_id else (
        "chess.com" if "chess.com" in game_id else "unknown"
    )

    return {
        "headers": {
            "white": game.headers.get("White", "?"),
            "black": game.headers.get("Black", "?"),
            "date": game.headers.get("Date", "?"),
            "result": game.headers.get("Result", "*"),
            "opening": game.headers.get("Opening", game.headers.get("Event", "?")),
            "source": source,
            "link": game_id,
        },
        "player_color": p_color,
        "analyzed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "settings": settings.to_dict(),
        "moves": moves_data,
    }


# ---------------------------------------------------------------------------
# Phase 1 orchestrator
# ---------------------------------------------------------------------------


class AnalysisInterrupted(Exception):
    """Raised when analysis is cancelled via the interrupt signal."""


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


def analyze_games(
    *,
    max_games: int = 10,
    reanalyze_all: bool = False,
    settings: AnalysisSettings | None = None,
    engine_path: str | None = None,
    on_progress: Callable[[dict], None] | None = None,
    cancel: threading.Event | None = None,
) -> None:
    """Fetch games, analyze with Stockfish + APIs, write analysis_data.json.

    Phase 1 orchestrator: sequential analysis with one multi-threaded Stockfish.
    After collection, calls annotate_and_derive() (Phase 2) to produce training_data.json.

    Args:
        max_games: Maximum games to fetch per source (default: 10).
        reanalyze_all: If True, re-analyze games (skip only same-settings).
        settings: Override analysis settings. None = load from config.
        engine_path: Override path to Stockfish binary.
        on_progress: Optional callback for structured progress events.
        cancel: Threading event for cancellation.
    """
    import time as _time

    from chess_self_coach.config import (
        _find_project_root,
        check_stockfish_version,
        find_stockfish,
        load_config,
        load_lichess_token,
    )
    from chess_self_coach.importer import fetch_chesscom_games, fetch_lichess_games

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

    # Load settings
    if settings is None:
        settings = AnalysisSettings.from_config(config)
    settings_dict = settings.to_dict()

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

    # Load Lichess token for Opening Explorer
    lichess_token = load_lichess_token(required=False)

    root = _find_project_root()
    analysis_path = root / "analysis_data.json"

    # Load existing analysis data
    existing_data = load_analysis_data(analysis_path)
    existing_games = existing_data.get("games", {})

    # Fetch games
    print("\n  Fetching games...")
    _emit({"phase": "fetch", "message": "Fetching games...", "percent": 5})
    all_games: list[chess.pgn.Game] = []

    if lichess_user:
        all_games.extend(fetch_lichess_games(lichess_user, max_games))
    if chesscom_user:
        all_games.extend(fetch_chesscom_games(chesscom_user, max_games))

    if not all_games:
        print("  No games found.")
        _emit({"phase": "done", "message": "No games found.", "percent": 100})
        return

    # Filter games
    new_games: list[tuple[chess.pgn.Game, str, chess.Color]] = []
    skipped = 0
    for game in all_games:
        game_id = game.headers.get("Link", game.headers.get("Site", ""))
        if game_id == "?":
            game_id = ""

        # Skip malformed games
        white = game.headers.get("White", "?")
        black = game.headers.get("Black", "?")
        if white == "?" and black == "?":
            continue

        # Determine player color
        player_color = _determine_player_color(game, lichess_user, chesscom_user)
        if player_color is None:
            continue

        # Check if already analyzed
        if game_id and game_id in existing_games:
            if not reanalyze_all:
                skipped += 1
                continue
            # Re-analyze mode: skip only if settings match
            stored_settings = existing_games[game_id].get("settings", {})
            if settings_match(stored_settings, settings_dict):
                skipped += 1
                continue

        new_games.append((game, game_id, player_color))

    if skipped:
        print(f"  Skipped {skipped} already-analyzed game(s)")

    # Sort by date (most recent first) and take max_games
    new_games.sort(
        key=lambda t: t[0].headers.get("Date", "0000.00.00"),
        reverse=True,
    )
    new_games = new_games[:max_games]

    _emit({
        "phase": "fetch",
        "message": f"Found {len(all_games)} game(s) ({len(new_games)} to analyze)",
        "percent": 10,
    })

    if not new_games:
        print("  No new games to analyze.")
        _emit({"phase": "done", "message": "No new games.", "percent": 100})
        return

    # Open Stockfish (one instance, multi-threaded)
    threads = settings.resolved_threads
    hash_mb = settings.hash_mb
    print(f"\n  Analyzing {len(new_games)} game(s) with Stockfish ({threads} threads, {hash_mb}MB hash)...")
    print("  This may take several minutes...\n")

    engine = chess.engine.SimpleEngine.popen_uci(str(sf_path))
    engine.configure({"Threads": threads, "Hash": hash_mb})

    try:
        wall_start = _time.time()
        done_count = 0
        total_tasks = len(new_games)

        for game, game_id, player_color in new_games:
            done_count += 1
            white = game.headers.get("White", "?")
            black = game.headers.get("Black", "?")
            label = f"{white} vs {black}"

            start = _time.time()
            try:
                game_data = collect_game_data(
                    game, engine, player_color, settings, lichess_token,
                )
            except Exception as exc:
                print(f"  [{done_count}/{total_tasks}] Error analyzing {label}: {exc}")
                continue

            elapsed = _time.time() - start

            # Store analysis duration for ETA estimation
            game_data["analysis_duration_s"] = round(elapsed, 1)

            # Store in analysis data
            store_id = game_id or f"unknown_{done_count}"
            existing_data.setdefault("games", {})[store_id] = game_data
            existing_data["player"] = {"lichess": lichess_user, "chesscom": chesscom_user or ""}

            # Atomic write after each game (crash-safe)
            save_analysis_data(existing_data, analysis_path)

            # Progress
            move_count = len(game_data["moves"])
            wall_elapsed = _time.time() - wall_start
            avg_per_game = wall_elapsed / done_count
            remaining = avg_per_game * (total_tasks - done_count)
            eta_min, eta_sec = divmod(int(remaining), 60)
            eta_str = f"{eta_min}m{eta_sec:02d}s" if eta_min else f"{eta_sec}s"

            print(
                f"  [{done_count}/{total_tasks}] {label}... "
                f"{move_count} moves ({elapsed:.1f}s) — ETA {eta_str}"
            )
            pct = 15 + int(75 * done_count / total_tasks)
            _emit({
                "phase": "analyze",
                "message": f"Analyzing {done_count}/{total_tasks}: {label}",
                "percent": pct,
                "current": done_count,
                "total": total_tasks,
            })

            # Check cancel
            if cancel and cancel.is_set():
                raise AnalysisInterrupted(
                    f"Interrupted. Saved {done_count}/{total_tasks} games."
                )
    finally:
        engine.quit()

    total_games = len(existing_data.get("games", {}))
    print(f"\n  Analysis data saved: {analysis_path}")
    print(f"  Total games analyzed: {total_games}")
    _emit({"phase": "done", "message": f"Analysis complete. {total_games} games.", "percent": 100})
