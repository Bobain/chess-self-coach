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

import re
import textwrap

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


# ══════════════════════════════════════════════════════════════════════════════
# Scoring: evaluate classifier quality against ground truth
# ══════════════════════════════════════════════════════════════════════════════

COMPLEXITY_LAMBDA = 0.10
COMPLEXITY_BUDGET = 50
MIN_SCORE = 0.38


def _compute_f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """Compute precision, recall, F1."""
    if tp == 0:
        return 0.0, 0.0, 0.0
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    f1 = 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def count_complexity() -> tuple[int, int, int, int]:
    """Count complexity of the Python classify_move() function.

    Parses the source code of classify_move() to count thresholds,
    rule conditions, and helper function calls — same methodology as
    the JS counter but applied to Python source.

    Returns:
        (n_thresholds, n_conditions, n_helpers, total).
    """
    import inspect
    source = inspect.getsource(classify_move)

    # Find the brilliant/great zone: from start to last "brilliant" or "great" return
    lines = source.split("\n")
    last_bg_line = 0
    for i, line in enumerate(lines):
        if '"brilliant"' in line or '"great"' in line:
            last_bg_line = i
    bg_zone = "\n".join(lines[: last_bg_line + 1])

    # Count thresholds: numeric literals in comparisons
    thresholds: set[str] = set()
    for t in re.findall(r"[<>=!]=?\s*(-?\d+\.\d+)", bg_zone):
        thresholds.add(t)
    for t in re.findall(r"[<>=!]=?\s*(-?\d+)(?!\.\d)", bg_zone):
        if abs(int(t)) > 2:
            thresholds.add(t)

    # Count rule conditions: if statements with numeric comparisons or function calls
    conditions = 0
    for m in re.finditer(r"\bif\b\s", bg_zone):
        # Extract the condition line
        line_start = bg_zone.rfind("\n", 0, m.start()) + 1
        line_end = bg_zone.find(":", m.end())
        if line_end < 0:
            continue
        cond = bg_zone[m.end():line_end]
        has_numeric = bool(re.search(r"[<>=!]=?\s*-?\d", cond))
        has_call = bool(re.search(r"\b[a-z_]\w+\(", cond))
        has_domain = bool(re.search(r"is_mate|is_opening|is_book|is_sacrifice|is_missed", cond))
        # Exclude pure null/None guards
        is_guard = bool(re.search(r"is None|is not None|\.get\(", cond)) and not has_numeric and not has_call
        if (has_numeric or has_call or has_domain) and not is_guard:
            conditions += 1

    # Count helper functions called (functions defined in this module, called in zone)
    defined_funcs = set(re.findall(r"^def\s+([a-z_]\w+)", source, re.MULTILINE))
    called_funcs = set(re.findall(r"\b([a-z_]\w+)\s*\(", bg_zone))
    helpers = called_funcs & defined_funcs - {"classify_move"}
    n_helpers = len(helpers)

    total = len(thresholds) + conditions + n_helpers
    return len(thresholds), conditions, n_helpers, total


def score_classifier(
    ground_truth_path: Path | None = None,
    classifications_path: Path | None = None,
    verbose: bool = True,
) -> dict:
    """Score the classifier against ground truth.

    Computes per-class TP/FP/FN, macro F1, complexity, and regularized score.
    Can be called standalone (by /optimize-classifier) or from tests.

    Args:
        ground_truth_path: Path to classification_ground_truth.json.
        classifications_path: Path to classifications_data.json.
        verbose: Print detailed results.

    Returns:
        Dict with keys: brilliant, great, macro_f1, complexity, penalty, score.
    """
    import importlib.util

    # Load ground truth cases
    cases_path = Path(__file__).parent.parent.parent / "tests" / "e2e" / "classification_cases.py"
    spec = importlib.util.spec_from_file_location("cases", str(cases_path))
    assert spec and spec.loader
    cases_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cases_mod)
    games_gt = cases_mod.GAMES  # type: ignore[attr-defined]

    # Load ground truth moves
    if ground_truth_path is None:
        ground_truth_path = Path(__file__).parent.parent.parent / "tests" / "e2e" / "fixtures" / "classification_ground_truth.json"
    with open(ground_truth_path) as f:
        gt_data = json.load(f)
    gt_by_id = {g["game_id"]: g for g in gt_data["games"]}

    # Load pre-computed classifications OR classify on the fly
    if classifications_path is None:
        classifications_path = classifications_data_path()

    # Load tactics for on-the-fly classification
    tactics_by_game: dict[str, list[dict]] = {}
    tp = tactics_data_path()
    if tp.exists():
        with open(tp) as f:
            tactics_by_game = json.load(f).get("games", {})

    # Use pre-computed if available, otherwise classify on the fly
    pre_computed: dict[str, list[dict | None]] = {}
    if classifications_path.exists():
        with open(classifications_path) as f:
            pre_computed = json.load(f).get("games", {})

    total_brilliant = {"tp": 0, "fp": 0, "fn": 0}
    total_great = {"tp": 0, "fp": 0, "fn": 0}
    total_moves = 0

    for game_gt in games_gt:
        gid = game_gt["game_id"]
        gt_game = gt_by_id.get(gid)
        if not gt_game:
            continue
        moves = gt_game["moves"]
        brilliant_set = set(game_gt.get("brilliant_indices", []))
        great_set = set(game_gt.get("great_indices", []))
        total_moves += len(moves)

        # Get classifications for this game
        game_url = None
        for url in pre_computed:
            # Match by numeric ID in the URL
            num_id = gid.split("_")[-1]
            if num_id in url:
                game_url = url
                break

        if game_url and game_url in pre_computed:
            classifications = pre_computed[game_url]
        else:
            # Classify on the fly
            game_tactics = tactics_by_game.get(gid) or [None] * len(moves)
            classifications = []
            for i, m in enumerate(moves):
                side = m.get("side", "white" if i % 2 == 0 else "black")
                prev = moves[i - 1] if i > 0 else None
                tact = game_tactics[i] if i < len(game_tactics) else None
                classifications.append(classify_move(m, side, prev, tact))

        # Compare to ground truth
        for i, cls in enumerate(classifications):
            predicted = cls["c"] if cls else "other"
            if predicted not in ("brilliant", "great"):
                predicted = "other"
            expected = (
                "brilliant" if i in brilliant_set
                else "great" if i in great_set
                else "other"
            )

            for cat, expected_cat, stats in [
                ("brilliant", "brilliant", total_brilliant),
                ("great", "great", total_great),
            ]:
                if expected == expected_cat and predicted == expected_cat:
                    stats["tp"] += 1
                elif predicted == expected_cat and expected != expected_cat:
                    stats["fp"] += 1
                elif expected == expected_cat and predicted != expected_cat:
                    stats["fn"] += 1

    # Compute F1
    _, _, brilliant_f1 = _compute_f1(total_brilliant["tp"], total_brilliant["fp"], total_brilliant["fn"])
    _, _, great_f1 = _compute_f1(total_great["tp"], total_great["fp"], total_great["fn"])
    macro_f1 = (brilliant_f1 + great_f1) / 2

    # Complexity
    n_thresholds, n_conditions, n_helpers, complexity = count_complexity()
    penalty = COMPLEXITY_LAMBDA * complexity / COMPLEXITY_BUDGET
    score = macro_f1 - penalty

    result = {
        "brilliant": {**total_brilliant, "f1": brilliant_f1},
        "great": {**total_great, "f1": great_f1},
        "macro_f1": macro_f1,
        "complexity": complexity,
        "n_thresholds": n_thresholds,
        "n_conditions": n_conditions,
        "n_helpers": n_helpers,
        "penalty": penalty,
        "score": score,
        "total_moves": total_moves,
        "n_games": len(games_gt),
    }

    if verbose:
        print(f"\n{'='*60}")
        print(f"CLASSIFICATION SCORE ({result['n_games']} games, {total_moves} moves)")
        print(f"  Brilliant: TP={total_brilliant['tp']} FP={total_brilliant['fp']} FN={total_brilliant['fn']} F1={brilliant_f1:.3f}")
        print(f"  Great:     TP={total_great['tp']} FP={total_great['fp']} FN={total_great['fn']} F1={great_f1:.3f}")
        print(f"  Macro F1={macro_f1:.3f}")
        print(f"  Complexity: {complexity} ({n_thresholds} thresholds + {n_conditions} conditions + {n_helpers} helpers)")
        print(f"  Penalty: -{penalty:.3f} (lambda={COMPLEXITY_LAMBDA}, budget={COMPLEXITY_BUDGET})")
        print(f"  Regularized score={score:.3f} (threshold={MIN_SCORE})")
        print(f"{'='*60}")

    return result
