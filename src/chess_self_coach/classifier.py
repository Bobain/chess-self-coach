"""Move classification: assign categories (brilliant, great, best, etc.) to each move.

Pre-computes classifications using analysis_data.json + tactics_data.json.
Output: classifications_data.json, read by the PWA (no runtime classification).

Categories: book, brilliant, great, best, excellent, good, inaccuracy, mistake, blunder, miss.
"""

from __future__ import annotations

import json
import logging
import math
import multiprocessing
from pathlib import Path

from chess_self_coach import worker_count
from chess_self_coach.config import (
    analysis_data_path,
    classifications_data_path,
    tactics_data_path,
)
from chess_self_coach.io import atomic_write_json

_log = logging.getLogger(__name__)

# ── Classification symbols and colors (match JS output) ──

CATEGORIES = {
    "book":       {"s": "\u2657", "co": "#a88764"},
    "brilliant":  {"s": "!!",     "co": "#1baca6"},
    "great":      {"s": "!",      "co": "#5c9ced"},
    "best":       {"s": "\u2605", "co": "#96bc4b"},
    "excellent":  {"s": "\u2191", "co": "#96bc4b"},
    "good":       {"s": "\u2713", "co": "#95b776"},
    "inaccuracy": {"s": "?!",     "co": "#f7c631"},
    "mistake":    {"s": "?",      "co": "#e6912a"},
    "blunder":    {"s": "??",     "co": "#ca3431"},
    "miss":       {"s": "\u00d7", "co": "#e06666"},
}


def _win_prob(cp: int, sign: int) -> float:
    """Win probability from centipawn score (logistic model)."""
    return 1.0 / (1.0 + math.pow(10, -cp * sign / 400))


def classify_move(
    move: dict,
    player_color: str,
    prev_move: dict | None,
    tactics: dict | None = None,
) -> dict | None:
    """Classify a single move.

    Args:
        move: Move data from analysis_data.json.
        player_color: 'white' or 'black'.
        prev_move: Previous move data (opponent's), or None.
        tactics: Pre-computed tactical motifs for this move from tactics_data.json.

    Returns:
        Dict with 'c' (category), 's' (symbol), 'co' (color), or None if unclassifiable.
    """
    # Book moves
    is_book = move.get("in_opening", False)
    if is_book:
        eb = move.get("eval_before", {})
        ea = move.get("eval_after", {})
        if eb.get("score_cp") is None or ea.get("score_cp") is None:
            return {"c": "book", **CATEGORIES["book"]}

    eval_before = move.get("eval_before", {})
    eval_after = move.get("eval_after", {})

    if eval_before.get("score_cp") is None or eval_after.get("score_cp") is None:
        return None

    # Mate detection
    if eval_before.get("is_mate") and eval_before.get("mate_in") is not None:
        mate_in = eval_before["mate_in"]
        mate_for_player = (mate_in > 0) if player_color == "white" else (mate_in < 0)
        if mate_for_player:
            if eval_after.get("is_mate") and eval_after.get("mate_in") is not None:
                if eval_after["mate_in"] == 0:
                    return {"c": "best", **CATEGORIES["best"]}
                still_mate = (eval_after["mate_in"] > 0) if player_color == "white" else (eval_after["mate_in"] < 0)
                if not still_mate:
                    return {"c": "miss", **CATEGORIES["miss"]}
            else:
                return {"c": "miss", **CATEGORIES["miss"]}

    # Win probability model
    sign = 1 if player_color == "white" else -1
    wp_before = _win_prob(eval_before["score_cp"], sign)
    wp_after = _win_prob(eval_after["score_cp"], sign)
    epl_lost = wp_before - wp_after
    is_opening = move.get("in_opening", False)

    # Brilliant detection
    if epl_lost < -0.005 and wp_before > 0.20 and wp_before < 0.95 and not is_opening:
        # isSacrifice: use pre-computed tactic if available
        is_sacrifice = (tactics or {}).get("isSacrifice", False)
        # Fallback: check if the JS isSacrifice would have fired
        # (move is best move + opponent recaptures in PV + material loss)
        if not is_sacrifice and tactics is None:
            is_sacrifice = _is_sacrifice_fallback(move)
        if is_sacrifice:
            return {"c": "brilliant", **CATEGORIES["brilliant"]}

    # Great detection
    if epl_lost <= 0.02 and not is_opening and prev_move:
        peb = prev_move.get("eval_before", {})
        pea = prev_move.get("eval_after", {})
        if (peb.get("score_cp") is not None and pea.get("score_cp") is not None
                and not peb.get("is_mate") and not pea.get("is_mate")):
            opp_sign = -sign
            opp_wp_before = _win_prob(peb["score_cp"], opp_sign)
            opp_wp_after = _win_prob(pea["score_cp"], opp_sign)
            opp_epl = opp_wp_before - opp_wp_after
            if opp_epl >= 0.15:
                return {"c": "great", **CATEGORIES["great"]}

    # Miss detection
    if not is_opening and epl_lost > 0.05 and prev_move:
        is_missed = (tactics or {}).get("isMissedCapture", False)
        if not is_missed and tactics is None:
            is_missed = _is_missed_capture_fallback(move)
        if is_missed:
            peb = prev_move.get("eval_before", {})
            pea = prev_move.get("eval_after", {})
            if (peb.get("score_cp") is not None and pea.get("score_cp") is not None
                    and not peb.get("is_mate") and not pea.get("is_mate")):
                opp_sign = -sign
                opp_epl = _win_prob(peb["score_cp"], opp_sign) - _win_prob(pea["score_cp"], opp_sign)
                if opp_epl >= 0.15:
                    return {"c": "miss", **CATEGORIES["miss"]}

    # Standard EPL thresholds
    if epl_lost <= 0:
        return {"c": "best", **CATEGORIES["best"]}
    if epl_lost <= 0.02:
        return {"c": "excellent", **CATEGORIES["excellent"]}
    if epl_lost <= 0.05:
        return {"c": "good", **CATEGORIES["good"]}
    if epl_lost <= 0.10:
        return {"c": "inaccuracy", **CATEGORIES["inaccuracy"]}
    if epl_lost <= 0.20:
        return {"c": "mistake", **CATEGORIES["mistake"]}
    return {"c": "blunder", **CATEGORIES["blunder"]}


def _is_sacrifice_fallback(move: dict) -> bool:
    """Simplified sacrifice detection without tactics_data (fallback)."""
    eb = move.get("eval_before", {})
    pv = eb.get("pv_uci", [])
    if not pv or len(pv) < 3 or not eb.get("best_move_uci"):
        return False
    if move.get("move_uci") != eb["best_move_uci"]:
        return False
    # Check if opponent recaptures on same square
    our_dest = move["move_uci"][2:4]
    if len(pv) > 1 and pv[1][2:4] == our_dest:
        return True
    return False


def _is_missed_capture_fallback(move: dict) -> bool:
    """Simplified missed capture detection without tactics_data (fallback)."""
    eb = move.get("eval_before", {})
    if not eb.get("best_move_uci") or not eb.get("best_move_san"):
        return False
    if move.get("move_uci") == eb["best_move_uci"]:
        return False
    return "x" in (eb.get("best_move_san") or "")


# ══════════════════════════════════════════════════════════════════════════════


def _classify_game(args: tuple[str, dict, list[dict] | None]) -> tuple[str, list[dict | None]]:
    """Classify all moves of one game. For multiprocessing."""
    game_id, game_data, game_tactics = args
    moves = game_data.get("moves", [])
    player_color = game_data.get("player_color", "white")
    # Determine player color from headers
    headers = game_data.get("headers", {})

    results: list[dict | None] = []
    for i, move in enumerate(moves):
        side = move.get("side", "white" if i % 2 == 0 else "black")
        prev_move = moves[i - 1] if i > 0 else None
        tactics = game_tactics[i] if game_tactics and i < len(game_tactics) else None
        result = classify_move(move, side, prev_move, tactics)
        results.append(result)

    return game_id, results


def run_classification(
    analysis_path: Path | None = None,
    tactics_path: Path | None = None,
    output_path: Path | None = None,
) -> None:
    """Run classification on all games, output classifications_data.json."""
    import time

    if analysis_path is None:
        analysis_path = analysis_data_path()
    if tactics_path is None:
        tactics_path = tactics_data_path()
    if output_path is None:
        output_path = classifications_data_path()

    if not analysis_path.exists():
        print(f"  No analysis data at {analysis_path}")
        return

    with open(analysis_path) as f:
        analysis = json.load(f)

    # Load tactics (optional — classifier works without it via fallbacks)
    tactics_by_game: dict[str, list[dict]] = {}
    if tactics_path.exists():
        with open(tactics_path) as f:
            tactics_data = json.load(f)
        tactics_by_game = tactics_data.get("games", {})
        print(f"  Loaded tactics for {len(tactics_by_game)} games")
    else:
        print("  No tactics data — using fallback detection")

    games = analysis.get("games", {})
    total_moves = sum(len(g.get("moves", [])) for g in games.values())
    n_workers = worker_count()

    print(f"  Classifying {len(games)} games, {total_moves} moves, {n_workers} workers")
    t0 = time.monotonic()

    # Prepare args for multiprocessing
    args = [
        (game_id, game_data, tactics_by_game.get(game_id))
        for game_id, game_data in games.items()
    ]

    with multiprocessing.Pool(processes=n_workers) as pool:
        results = pool.map(_classify_game, args)

    # Build output
    classifications: dict[str, list[dict | None]] = {}
    for game_id, move_classes in results:
        classifications[game_id] = move_classes

    output = {"version": "1.0", "games": classifications}
    atomic_write_json(output_path, output)

    elapsed = time.monotonic() - t0
    print(f"  Done in {elapsed:.1f}s → {output_path} ({output_path.stat().st_size / 1024:.0f} KB)")
