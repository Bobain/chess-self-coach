"""Full game analysis: collect raw data from Stockfish, tablebase, and opening explorer.

Phase 1 collects all per-move evaluation data and stores it in analysis_data.json.
Phase 2 annotates moves and derives training_data.json from the raw data.

This decoupling allows re-running Phase 2 (cheap) without re-running Phase 1 (expensive).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time as _time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.engine
import chess.pgn

from chess_self_coach import worker_count
from chess_self_coach.cloud_eval import query_cloud_eval
from chess_self_coach.config import _find_project_root
from chess_self_coach.constants import (
    ANALYSIS_LIMITS,
    ANALYSIS_TIME_LIMIT,
    DOMINATED_POSITION_CP,
    ENDGAME_PIECES_MAX,
    MATE_CP,
    MAX_PV_MOVES,
    MIDDLEGAME_PIECES_MAX,
)
from chess_self_coach.tablebase import (
    MAX_PIECES,
    TablebaseResult,
    probe_position_full,
    tablebase_context,
    tablebase_explanation,
)

_log = logging.getLogger(__name__)


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
    limits: dict[str, dict[str, float | int]] = field(
        default_factory=lambda: dict(ANALYSIS_LIMITS)
    )

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
            limits=section.get("limits", dict(ANALYSIS_LIMITS)),
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
        _log.warning("Corrupted analysis_data.json, returning empty structure")
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
    if kings_and_pawns and piece_count <= ENDGAME_PIECES_MAX:
        lim = limits.get("kings_pawns_le7", {})
    elif piece_count <= ENDGAME_PIECES_MAX:
        lim = limits.get("pieces_le7", {})
    elif piece_count <= MIDDLEGAME_PIECES_MAX:
        lim = limits.get("pieces_le12", {})
    else:
        lim = limits.get("default", {})

    depth = int(lim["depth"]) if "depth" in lim else None
    # Always enforce a time cap — use config value or fall back to ANALYSIS_TIME_LIMIT
    time = float(lim.get("time", ANALYSIS_TIME_LIMIT))
    return (
        chess.engine.Limit(depth=depth, time=time)
        if lim
        else chess.engine.Limit(depth=18)
    )


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
        assert mate is not None  # guaranteed by is_mate()
        cp = MATE_CP if mate > 0 else -MATE_CP
        return cp, True, mate
    return white.score(), False, None


def _extract_eval(info: chess.engine.InfoDict, board: chess.Board) -> dict:
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
            "score_cp": None,
            "is_mate": False,
            "mate_in": None,
            "depth": None,
            "seldepth": None,
            "nodes": None,
            "nps": None,
            "time_ms": None,
            "tbhits": None,
            "hashfull": None,
            "pv_san": [],
            "pv_uci": [],
            "best_move_san": None,
            "best_move_uci": None,
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
    cp = MATE_CP if tier == "WIN" else (-MATE_CP if tier == "LOSS" else 0)
    if board_turn == chess.BLACK:
        cp = -cp

    best_move_data = tb_data.get("moves", [{}])[0] if tb_data.get("moves") else {}
    return {
        "score_cp": cp,
        "is_mate": tier != "DRAW" and tb_data.get("dtm") is not None,
        "mate_in": tb_data.get("dtm"),
        "depth": None,
        "seldepth": None,
        "nodes": None,
        "nps": None,
        "time_ms": None,
        "tbhits": None,
        "hashfull": None,
        "pv_san": [best_move_data.get("san")] if best_move_data.get("san") else [],
        "pv_uci": [best_move_data.get("uci")] if best_move_data.get("uci") else [],
        "best_move_san": best_move_data.get("san"),
        "best_move_uci": best_move_data.get("uci"),
    }


def _cloud_eval_to_eval(cloud_data: dict, board: chess.Board) -> dict:
    """Convert Lichess Cloud Eval API response to our standard eval dict.

    Args:
        cloud_data: Response from query_cloud_eval() with {fen, depth, knodes, pvs[]}.
        board: Board position (for PV UCI-to-SAN conversion).

    Returns:
        Dict matching the _extract_eval() structure.
    """
    pv_entry = cloud_data.get("pvs", [{}])[0]

    # Score: cp is from White's perspective in the API
    score_cp = pv_entry.get("cp")
    is_mate = False
    mate_in = None
    if "mate" in pv_entry:
        mate_in = pv_entry["mate"]
        is_mate = True
        score_cp = MATE_CP if mate_in > 0 else -MATE_CP

    # PV: space-separated UCI moves
    pv_uci_str = pv_entry.get("moves", "")
    pv_uci = pv_uci_str.split() if pv_uci_str else []

    # Convert PV to SAN
    pv_san: list[str] = []
    pv_board = board.copy()
    for uci in pv_uci:
        try:
            move = chess.Move.from_uci(uci)
            pv_san.append(pv_board.san(move))
            pv_board.push(move)
        except (ValueError, AssertionError):
            break

    best_uci = pv_uci[0] if pv_uci else None
    best_san = pv_san[0] if pv_san else None

    return {
        "score_cp": score_cp,
        "is_mate": is_mate,
        "mate_in": mate_in,
        "depth": cloud_data.get("depth"),
        "seldepth": None,
        "nodes": None,
        "nps": None,
        "time_ms": None,
        "tbhits": None,
        "hashfull": None,
        "pv_san": pv_san,
        "pv_uci": pv_uci,
        "best_move_san": best_san,
        "best_move_uci": best_uci,
    }


def collect_game_data(
    game: chess.pgn.Game,
    engine: chess.engine.SimpleEngine,
    player_color: chess.Color,
    settings: AnalysisSettings,
    lichess_token: str | None = None,
    game_id: str = "",
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
        game_id: Unique game identifier. Passed to engine.analyse() so python-chess
            sends ucinewgame between different games (hash table reset).

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
        if is_promotion and actual_move.promotion is not None:
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

        # --- Opening Explorer: determine if move is in opening theory ---
        explorer_data = explorer_results[ply] if ply < len(explorer_results) else None
        in_opening = False
        if explorer_data is not None:
            known_moves_uci = {m["uci"] for m in explorer_data.get("moves", [])}
            in_opening = actual_move.uci() in known_moves_uci

        # --- Eval: board_after_fen needed by both branches ---
        board_after_fen = board_after.fen()

        # --- Eval source + eval_before / eval_after ---
        if in_opening:
            # Opening book move: use Lichess Cloud Eval (fast), fall back to Stockfish
            # eval_source is set below based on actual evaluation provider

            # eval_before
            t0 = _time.time()
            if cached_eval is not None:
                eval_before = cached_eval
                _eb_src = "cache"
            else:
                cloud = query_cloud_eval(board.fen())
                if cloud:
                    eval_before = _cloud_eval_to_eval(cloud, board)
                    _eb_src = "cloud_eval"
                else:
                    info = engine.analyse(
                        board,
                        _analysis_limit_from_settings(board, limits),
                        game=game_id,
                    )
                    eval_before = _extract_eval(info, board)
                    _eb_src = "sf_fallback"
            eval_before_ms = (_time.time() - t0) * 1000

            # eval_after
            t0 = _time.time()
            cloud_after = query_cloud_eval(board_after_fen)
            if cloud_after:
                eval_after = _cloud_eval_to_eval(cloud_after, board_after)
                _ea_src = "cloud_eval"
            else:
                info_after = engine.analyse(
                    board_after,
                    _analysis_limit_from_settings(board_after, limits),
                    game=game_id,
                )
                eval_after = _extract_eval(info_after, board_after)
                _ea_src = "sf_fallback"
            eval_after_ms = (_time.time() - t0) * 1000

            eval_source = "cloud_eval" if _ea_src == "cloud_eval" else "stockfish"

            _log.info(
                "  ply %d %s: opening — before=%s(%.0fms cp=%s) after=%s(%.0fms cp=%s)",
                ply + 1,
                board.san(actual_move),
                _eb_src,
                eval_before_ms,
                eval_before.get("score_cp"),
                _ea_src,
                eval_after_ms,
                eval_after.get("score_cp"),
            )

            cached_eval = eval_after
            cached_tb = None
            cp_loss = 0
            tb_before_stored = None
            tb_after_stored = None
        else:
            tb_before = None
            eval_source = "stockfish"

            # eval_before (+ tablebase probe)
            t0 = _time.time()
            if piece_count <= MAX_PIECES:
                tb_before = probe_position_full(board.fen())

            if cached_eval is not None:
                eval_before = cached_eval
                _eb_src = "cache"
                if cached_tb is not None:
                    tb_before = cached_tb
                    eval_source = (
                        "tablebase"
                        if cached_eval.get("depth") is None
                        else "stockfish+tablebase"
                    )
            elif tb_before:
                eval_before = _tb_to_eval(tb_before, board.turn)
                eval_source = "tablebase"
                _eb_src = "tablebase"
            else:
                info = engine.analyse(
                    board, _analysis_limit_from_settings(board, limits), game=game_id
                )
                eval_before = _extract_eval(info, board)
                _eb_src = "stockfish"
                if tb_before:
                    eval_source = "stockfish+tablebase"
            eval_before_ms = (_time.time() - t0) * 1000

            # --- Eval after actual move (will be cached as eval_before for next ply) ---
            t0 = _time.time()
            pc_after = len(board_after.piece_map())
            tb_after = None

            if pc_after <= MAX_PIECES:
                tb_after = probe_position_full(board_after_fen)

            if tb_after:
                eval_after = _tb_to_eval(tb_after, board_after.turn)
                cached_eval = eval_after
                cached_tb = tb_after
                _ea_src = "tablebase"
            else:
                info_after = engine.analyse(
                    board_after,
                    _analysis_limit_from_settings(board_after, limits),
                    game=game_id,
                )
                eval_after = _extract_eval(info_after, board_after)
                cached_eval = eval_after
                cached_tb = None
                _ea_src = "stockfish"
            eval_after_ms = (_time.time() - t0) * 1000

            # --- cp_loss ---
            cp_loss = 0
            before_cp = eval_before.get("score_cp")
            after_cp = eval_after.get("score_cp")
            if before_cp is not None and after_cp is not None:
                # If the player delivered checkmate, cp_loss is 0 by definition
                best_uci = eval_before.get("best_move_uci", "")
                if best_uci and actual_move == chess.Move.from_uci(best_uci):
                    cp_loss = 0
                elif board.turn == chess.WHITE:
                    cp_loss = max(0, before_cp - after_cp)
                else:
                    cp_loss = max(0, after_cp - before_cp)

            _log.info(
                "  ply %d %s: %s — before=%s(%.0fms cp=%s) after=%s(%.0fms cp=%s) cp_loss=%d",
                ply + 1,
                board.san(actual_move),
                eval_source,
                _eb_src,
                eval_before_ms,
                eval_before.get("score_cp"),
                _ea_src,
                eval_after_ms,
                eval_after.get("score_cp"),
                cp_loss,
            )

            # --- Tablebase: store full responses ---
            tb_before_stored = tb_before
            tb_after_stored = tb_after

        # --- Build move dict ---
        move_dict = {
            "ply": ply + 1,
            "fen_before": board.fen(),
            "fen_after": board_after_fen,
            "move_san": board.san(actual_move),
            "move_uci": actual_move.uci(),
            "side": side,
            "eval_source": eval_source,
            "in_opening": in_opening,
            "eval_before": eval_before,
            "eval_after": eval_after,
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
            "timing_ms": {
                "eval_before": round(eval_before_ms, 1),
                "eval_after": round(eval_after_ms, 1),
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
    source = (
        "lichess"
        if "lichess.org" in game_id
        else ("chess.com" if "chess.com" in game_id else "unknown")
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
    game_ids: list[str] | None = None,
    max_games: int = 10,
    reanalyze_all: bool = False,
    settings: AnalysisSettings | None = None,
    engine_path: str | None = None,
    on_progress: Callable[[dict], None] | None = None,
    cancel: threading.Event | None = None,
) -> None:
    """Fetch games, analyze with Stockfish + APIs, write analysis_data.json.

    Phase 1 orchestrator: sequential analysis with one multi-threaded Stockfish.
    Caller is responsible for invoking annotate_and_derive() (Phase 2) afterwards.

    Args:
        game_ids: Specific game IDs to analyze from the cache. When set,
            skips the fetch phase and reads from fetched_games.json.
            When None or empty, fetches from APIs (original behavior).
        max_games: Maximum total games in the dataset (default: 10).
        reanalyze_all: If True, re-analyze games (skip only same-settings).
        settings: Override analysis settings. None = load from config.
        engine_path: Override path to Stockfish binary.
        on_progress: Optional callback for structured progress events.
        cancel: Threading event for cancellation.
    """
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

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

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

    # --- Load games: from cache (game_ids) or from APIs (fetch) ---
    new_games: list[tuple[chess.pgn.Game, str, chess.Color]] = []

    if game_ids:
        # Load specific games from cache (no API fetch needed)
        from chess_self_coach.game_cache import get_cached_game, load_game_cache

        print(f"\n  Loading {len(game_ids)} game(s) from cache...")
        _emit({"phase": "fetch", "message": "Loading from cache...", "percent": 5})

        cache = load_game_cache()
        cached_games = cache.get("games", {})

        for gid in game_ids:
            if gid in existing_games and not reanalyze_all:
                print(f"  Skipped (already analyzed): {gid}")
                continue

            entry = cached_games.get(gid)
            if entry is None:
                print(f"  Warning: game not in cache, skipping: {gid}")
                continue

            game = get_cached_game(gid)
            if game is None:
                continue

            player_color_str = entry.get("player_color", "white")
            player_color = chess.WHITE if player_color_str == "white" else chess.BLACK
            new_games.append((game, gid, player_color))

        _emit(
            {
                "phase": "fetch",
                "message": f"{len(new_games)} game(s) to analyze",
                "percent": 10,
            }
        )
    else:
        # Original behavior: fetch from APIs
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
        reanalyzed = 0
        skipped = 0
        for game in all_games:
            game_id = game.headers.get("Link", game.headers.get("Site", ""))
            if game_id == "?":
                game_id = ""

            white = game.headers.get("White", "?")
            black = game.headers.get("Black", "?")
            if white == "?" and black == "?":
                continue

            player_color = _determine_player_color(game, lichess_user, chesscom_user)
            if player_color is None:
                continue

            is_reanalysis = False
            if game_id and game_id in existing_games:
                if not reanalyze_all:
                    skipped += 1
                    continue
                stored_settings = existing_games[game_id].get("settings", {})
                if settings_match(stored_settings, settings_dict):
                    skipped += 1
                    continue
                is_reanalysis = True

            new_games.append((game, game_id, player_color))
            if is_reanalysis:
                reanalyzed += 1

        if skipped:
            print(f"  Skipped {skipped} already-analyzed game(s)")

        new_games.sort(
            key=lambda t: t[0].headers.get("Date", "0000.00.00"),
            reverse=True,
        )
        cap = max(0, max_games - len(existing_games)) + reanalyzed
        new_games = new_games[:cap]

        _emit(
            {
                "phase": "fetch",
                "message": f"Found {len(all_games)} game(s) ({len(new_games)} to analyze)",
                "percent": 10,
            }
        )

    if not new_games:
        print("  No new games to analyze.")
        _emit({"phase": "done", "message": "No new games.", "percent": 100})
        return

    # Open Stockfish (one instance, multi-threaded)
    threads = settings.resolved_threads
    hash_mb = settings.hash_mb
    print(
        f"\n  Analyzing {len(new_games)} game(s) with Stockfish ({threads} threads, {hash_mb}MB hash)..."
    )
    print("  This may take several minutes...\n")

    engine = chess.engine.SimpleEngine.popen_uci(str(sf_path))
    engine.configure({"Threads": threads, "Hash": hash_mb})

    # Syzygy endgame tablebases
    from chess_self_coach.syzygy import find_syzygy

    syzygy_path = find_syzygy(config)
    if not syzygy_path:
        engine.quit()
        raise RuntimeError(
            "Syzygy endgame tablebases (3-5 pieces) not found.\n"
            "  Install with: chess-self-coach syzygy download"
        )
    engine.configure({"SyzygyPath": str(syzygy_path)})
    _log.info("Syzygy tablebases: %s", syzygy_path)

    try:
        wall_start = _time.time()
        done_count = 0
        total_tasks = len(new_games)
        _emit({"phase": "analyze", "message": f"Analyzing 0/{total_tasks}", "percent": 15, "current": 0, "total": total_tasks})

        for game, game_id, player_color in new_games:
            done_count += 1
            white = game.headers.get("White", "?")
            black = game.headers.get("Black", "?")
            label = f"{white} vs {black}"

            start = _time.time()
            try:
                game_data = collect_game_data(
                    game,
                    engine,
                    player_color,
                    settings,
                    lichess_token,
                    game_id=game_id,
                )
            except Exception as exc:
                print(f"  [{done_count}/{total_tasks}] Error analyzing {label}: {exc}")
                continue

            elapsed = _time.time() - start

            # Store analysis duration for ETA estimation
            game_data["analysis_duration_s"] = round(elapsed, 1)

            # Per-game summary
            _moves = game_data["moves"]
            _opening = [m for m in _moves if m["eval_source"] == "opening_explorer"]
            _other = [m for m in _moves if m["eval_source"] != "opening_explorer"]
            _log.info(
                "Game %d/%d: %s — %d moves in %.1fs",
                done_count,
                total_tasks,
                label,
                len(_moves),
                elapsed,
            )
            if _opening:
                _op_ms = sum(
                    m["timing_ms"]["eval_before"] + m["timing_ms"]["eval_after"]
                    for m in _opening
                )
                _log.info("  Opening: %d moves in %.1fs", len(_opening), _op_ms / 1000)
            if _other:
                _ot_ms = sum(
                    m["timing_ms"]["eval_before"] + m["timing_ms"]["eval_after"]
                    for m in _other
                )
                _src_counts: dict[str, int] = {}
                for m in _other:
                    s = m["eval_source"]
                    _src_counts[s] = _src_counts.get(s, 0) + 1
                _src_str = ", ".join(f"{k}: {v}" for k, v in _src_counts.items())
                _log.info(
                    "  Non-opening: %d moves (%s) in %.1fs",
                    len(_other),
                    _src_str,
                    _ot_ms / 1000,
                )

            # Store in analysis data
            store_id = game_id or f"unknown_{done_count}"
            existing_data.setdefault("games", {})[store_id] = game_data
            existing_data["player"] = {
                "lichess": lichess_user,
                "chesscom": chesscom_user or "",
            }

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
            _emit(
                {
                    "phase": "analyze",
                    "message": f"Analyzing {done_count}/{total_tasks}: {label}",
                    "percent": pct,
                    "current": done_count,
                    "total": total_tasks,
                }
            )

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
    _emit(
        {
            "phase": "done",
            "message": f"Analysis complete. {total_games} games.",
            "percent": 100,
        }
    )


# ---------------------------------------------------------------------------
# Phase 2: Annotation + training data derivation
# ---------------------------------------------------------------------------


def annotate_and_derive(
    analysis_path: Path | None = None,
    output_path: Path | None = None,
    min_cp_loss: int = 50,
) -> None:
    """Derive training_data.json from analysis_data.json (Phase 2).

    Reads the raw analysis data, filters for player mistakes, generates
    explanations, and writes training_data.json. Can be re-run cheaply
    without re-running Stockfish.

    Args:
        analysis_path: Path to analysis_data.json. Defaults to project root.
        output_path: Path to training_data.json. Defaults to project root.
        min_cp_loss: Minimum centipawn loss to include (default: 50 = inaccuracy).
    """
    import hashlib

    from chess_self_coach.config import _find_project_root, load_config
    from chess_self_coach.trainer import (
        _classify_mistake,
        _format_score_cp,
        _generate_context,
        _time_pressure_context,
        generate_explanation,
    )

    root = _find_project_root()
    if analysis_path is None:
        analysis_path = root / "analysis_data.json"
    if output_path is None:
        output_path = root / "training_data.json"

    # Load analysis data
    analysis_data = load_analysis_data(analysis_path)
    games = analysis_data.get("games", {})
    if not games:
        print("  No analysis data found. Run analysis first.")
        return

    # Load existing training data (to preserve SRS state)
    existing_positions: dict[str, dict] = {}
    if output_path.exists():
        try:
            with open(output_path) as f:
                existing_td = json.load(f)
            for pos in existing_td.get("positions", []):
                existing_positions[pos["id"]] = pos
        except (json.JSONDecodeError, KeyError):
            pass

    # Process each game
    positions: dict[str, dict] = {}
    analyzed_game_ids: set[str] = set()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for game_id, game_data in games.items():
        analyzed_game_ids.add(game_id)
        player_color = game_data.get("player_color", "white")
        moves = game_data.get("moves", [])
        headers = game_data.get("headers", {})

        game_info = {
            "id": game_id,
            "source": headers.get("source", "unknown"),
            "opponent": (
                headers.get("black", "?")
                if player_color == "white"
                else headers.get("white", "?")
            ),
            "date": headers.get("date", "?"),
            "result": headers.get("result", "*"),
            "opening": headers.get("opening", "?"),
        }

        for move_data in moves:
            # Only look at the player's moves
            if move_data["side"] != player_color:
                continue

            cp_loss = move_data.get("cp_loss", 0)
            if cp_loss < min_cp_loss:
                continue

            category = _classify_mistake(cp_loss)
            if category is None:
                continue

            # Extract scores
            eval_before = move_data.get("eval_before", {})
            eval_after = move_data.get("eval_after", {})

            score_before_cp = eval_before.get("score_cp")
            score_after_cp = eval_after.get("score_cp")

            # Pedagogical filter: skip already-lost or already-won
            if score_before_cp is not None and score_after_cp is not None:
                player_cp = (
                    score_before_cp if player_color == "white" else -score_before_cp
                )
                player_cp_after = (
                    score_after_cp if player_color == "white" else -score_after_cp
                )
                is_mate = eval_before.get("is_mate", False)
                if (
                    player_cp < -DOMINATED_POSITION_CP
                    and player_cp_after < -DOMINATED_POSITION_CP
                    and not is_mate
                ):
                    continue  # Already lost
                if (
                    player_cp > DOMINATED_POSITION_CP
                    and player_cp_after > DOMINATED_POSITION_CP
                ):
                    continue  # Already won

            was_mate = eval_before.get("is_mate", False)
            fen = move_data.get("fen_before", "")
            actual_san = move_data.get("move_san", "")
            best_san = eval_before.get("best_move_san", "")

            # Skip if the player already played the best move
            if best_san and actual_san == best_san:
                continue

            # Generate explanation
            board = chess.Board(fen) if fen else chess.Board()
            explanation = generate_explanation(
                board,
                actual_san,
                best_san or actual_san,
                cp_loss,
                category,
                was_mate=was_mate,
                score_after_cp=score_after_cp,
            )

            # Generate context
            context = _generate_context(
                category,
                cp_loss,
                was_mate,
                score_after_cp,
                fen=fen,
                score_before_cp=score_before_cp,
                player_color=player_color,
            )

            # Override with tablebase-specific text for endgame positions
            tb_before_raw = move_data.get("tablebase_before")
            tb_after_raw = move_data.get("tablebase_after")
            if tb_before_raw:
                tb_res_before = TablebaseResult(
                    category=tb_before_raw["category"],
                    dtz=tb_before_raw.get("dtz"),
                    dtm=tb_before_raw.get("dtm"),
                    best_move=None,
                )
                piece_count = move_data.get("board", {}).get("piece_count", 0)
                context = tablebase_context(
                    tb_res_before, piece_count, player_color
                )
                if tb_after_raw:
                    tb_res_after = TablebaseResult(
                        category=tb_after_raw["category"],
                        dtz=tb_after_raw.get("dtz"),
                        dtm=tb_after_raw.get("dtm"),
                        best_move=None,
                    )
                    explanation = tablebase_explanation(
                        tb_res_before, tb_res_after, actual_san, best_san
                    )

            # Time pressure context
            clock = move_data.get("clock", {})
            time_ctx = _time_pressure_context(
                clock.get("player"), clock.get("opponent")
            )
            if time_ctx:
                context = f"{context} {time_ctx}"

            # PV (from eval_before)
            pv = eval_before.get("pv_san", [])

            # Position ID
            pos_id_data = f"{fen}:{actual_san}"
            pos_id = hashlib.sha256(pos_id_data.encode()).hexdigest()[:12]

            # Build position dict
            pos = {
                "id": pos_id,
                "fen": fen,
                "player_color": player_color,
                "player_move": actual_san,
                "best_move": best_san or actual_san,
                "context": context,
                "score_before": _format_score_cp(score_before_cp),
                "score_after": _format_score_cp(score_after_cp),
                "score_after_best": _format_score_cp(score_before_cp),
                "cp_loss": cp_loss,
                "category": category,
                "explanation": explanation,
                "acceptable_moves": [best_san] if best_san else [],
                "pv": pv[:MAX_PV_MOVES] if not was_mate else pv,
                "game": game_info,
                "clock": {
                    "player": clock.get("player"),
                    "opponent": clock.get("opponent"),
                },
            }

            # Tablebase data
            tb_before = move_data.get("tablebase_before")
            tb_after = move_data.get("tablebase_after")
            if tb_before or tb_after:
                tb_data = {}
                if tb_before:
                    tb_data["before"] = {
                        "category": tb_before.get("category"),
                        "dtm": tb_before.get("dtm"),
                        "dtz": tb_before.get("dtz"),
                    }
                if tb_after:
                    tb_data["after"] = {
                        "category": tb_after.get("category"),
                        "dtm": tb_after.get("dtm"),
                        "dtz": tb_after.get("dtz"),
                    }
                if tb_before and tb_after:
                    tier_before = tb_before.get("tier", "DRAW")
                    tier_after = tb_after.get("tier", "DRAW")
                    tb_data["transition"] = f"{tier_before} → {tier_after}"
                pos["tablebase"] = tb_data

            # Preserve SRS state from existing training data
            if pos_id in existing_positions:
                pos["srs"] = existing_positions[pos_id].get(
                    "srs",
                    {
                        "interval": 0,
                        "ease": 2.5,
                        "next_review": today,
                        "history": [],
                    },
                )
            else:
                pos["srs"] = {
                    "interval": 0,
                    "ease": 2.5,
                    "next_review": today,
                    "history": [],
                }

            positions[pos_id] = pos

    # Build output
    config = load_config()
    players = config.get("players", {})
    lichess_user = players.get("lichess", "")
    chesscom_user = players.get("chesscom", "")

    severity = {"blunder": 0, "mistake": 1, "inaccuracy": 2}
    sorted_positions = sorted(
        positions.values(),
        key=lambda m: (severity.get(m["category"], 3), -m["cp_loss"]),
    )

    training_data = {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "player": {"lichess": lichess_user, "chesscom": chesscom_user},
        "positions": sorted_positions,
        "analyzed_game_ids": sorted(analyzed_game_ids),
    }

    _atomic_write_json(output_path, training_data)
    print(f"  Training data derived: {output_path}")
    print(f"  Total positions: {len(sorted_positions)} (from {len(games)} games)")
