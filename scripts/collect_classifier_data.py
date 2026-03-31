"""Collect all !! and ! classified moves (TP/FP/FN) with features + tactical motifs.

Pure Python — uses classifier.py + tactics_data.json directly (no Playwright).
Outputs to /tmp/classifier_data.json.

Usage: uv run python3 scripts/collect_classifier_data.py
"""

from __future__ import annotations

import json
import math
import pathlib
import time

from chess_self_coach.classifier import classify_move
from chess_self_coach.config import tactics_data_path


def wp(cp: int, sign: int) -> float:
    """Win probability from centipawn score."""
    return 1 / (1 + math.pow(10, -cp * sign / 400))


def fmt_move(moves: list[dict], idx: int) -> dict | None:
    """Format a move with its eval context."""
    if idx < 0 or idx >= len(moves):
        return None
    m = moves[idx]
    eb = m.get("eval_before", {})
    ea = m.get("eval_after", {})
    san = m.get("move_san", "?")
    is_capture = "x" in san
    is_check = "+" in san or "#" in san
    piece_moved = san[0] if san and san[0].isupper() else "P"

    return {
        "label": f"{(idx // 2) + 1}.{'w' if idx % 2 == 0 else 'b'}",
        "san": san,
        "fen": m.get("fen_before", ""),
        "cp_b": eb.get("score_cp"),
        "cp_a": ea.get("score_cp"),
        "is_mate": eb.get("is_mate", False),
        "mate_in": eb.get("mate_in"),
        "best": eb.get("best_move_san", "?"),
        "best_uci": eb.get("best_move_uci"),
        "is_best": m.get("move_uci") == eb.get("best_move_uci"),
        "pv": " ".join(eb.get("pv_san", [])[:6]),
        "pv_len": len(eb.get("pv_uci", [])),
        "is_capture": is_capture,
        "is_check": is_check,
        "piece_moved": piece_moved,
    }


def main() -> None:
    """Collect classification data using Python classifier + tactics."""
    t0 = time.monotonic()

    gt_path = pathlib.Path("tests/e2e/fixtures/classification_ground_truth.json")
    with open(gt_path) as f:
        gt_data = json.load(f)

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "cases", "tests/e2e/classification_cases.py"
    )
    assert spec and spec.loader
    cases_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cases_mod)
    GAMES = cases_mod.GAMES  # type: ignore[attr-defined]

    gt_by_id = {g["game_id"]: g for g in gt_data["games"]}
    results: dict[str, list[dict]] = {"brilliant": [], "great": []}

    # Load tactics data
    tactics_by_game: dict[str, list[dict]] = {}
    tp = tactics_data_path()
    if tp.exists():
        with open(tp) as f:
            tactics_by_game = json.load(f).get("games", {})

    for game_gt in GAMES:
        gid = game_gt["game_id"]
        gt_game = gt_by_id.get(gid)
        if not gt_game:
            continue
        moves = gt_game["moves"]
        brilliant_set = set(game_gt.get("brilliant_indices", []))
        great_set = set(game_gt.get("great_indices", []))

        # Find matching tactics by numeric ID in URL
        num_id = gid.split("_")[-1]
        game_tactics = None
        for url, tac in tactics_by_game.items():
            if num_id in url:
                game_tactics = tac
                break

        # Classify all moves
        classified = []
        for i, m in enumerate(moves):
            side = m.get("side", "white" if i % 2 == 0 else "black")
            prev = moves[i - 1] if i > 0 else None
            tact = game_tactics[i] if game_tactics and i < len(game_tactics) else None
            cls = classify_move(m, side, prev, tact)
            classified.append(cls)

        # Collect TP/FP/FN
        for i, (m, cls) in enumerate(zip(moves, classified)):
            predicted = cls["c"] if cls else "other"
            if predicted not in ("brilliant", "great"):
                predicted = "other"
            expected = (
                "brilliant" if i in brilliant_set
                else "great" if i in great_set
                else "other"
            )
            if expected == "other" and predicted == "other":
                continue

            side = "white" if i % 2 == 0 else "black"
            sign = 1 if side == "white" else -1

            opp_epl = None
            if i > 0:
                prev = moves[i - 1]
                peb = prev.get("eval_before", {})
                pea = prev.get("eval_after", {})
                if (peb.get("score_cp") is not None and pea.get("score_cp") is not None
                        and not peb.get("is_mate") and not pea.get("is_mate")):
                    opp_sign = -sign
                    opp_epl = round(wp(peb["score_cp"], opp_sign) - wp(pea["score_cp"], opp_sign), 4)

            eb = m.get("eval_before", {})
            ea = m.get("eval_after", {})
            wp_b = wp_a = epl = wp_gain = cp_gain = None
            if eb.get("score_cp") is not None and not eb.get("is_mate"):
                wp_b = round(wp(eb["score_cp"], sign), 4)
                if ea.get("score_cp") is not None and not ea.get("is_mate"):
                    wp_a = round(wp(ea["score_cp"], sign), 4)
                    epl = round(wp_b - wp_a, 4)
                    wp_gain = round(wp_a - wp_b, 4)
                    cp_gain = (ea["score_cp"] - eb["score_cp"]) * sign

            status = (
                "TP" if expected == predicted
                else ("FN" if expected in ("brilliant", "great") else "FP")
            )
            cat = "brilliant" if "brilliant" in (expected, predicted) else "great"

            # Previous move classification
            prev_cls = classified[i - 1] if i > 0 else None
            prev_classification = prev_cls["c"] if prev_cls else "other"
            if prev_classification not in (
                "brilliant", "great", "best", "excellent",
                "good", "miss", "inaccuracy", "mistake", "blunder",
            ):
                prev_classification = "other"

            is_recapture = False
            if i > 0 and moves[i - 1].get("move_uci") and m.get("move_uci"):
                is_recapture = moves[i - 1]["move_uci"][2:4] == m["move_uci"][2:4]

            # Tactical motifs
            motifs = game_tactics[i] if game_tactics and i < len(game_tactics) else {}

            move_fmt = fmt_move(moves, i)
            results[cat].append({
                "game": gid[:30],
                "idx": i,
                "status": status,
                "predicted": predicted,
                "expected": expected,
                "wp_before": wp_b,
                "wp_after": wp_a,
                "epl_lost": epl,
                "wp_gain": wp_gain,
                "cp_gain": cp_gain,
                "opp_epl": opp_epl,
                "is_sacrifice": motifs.get("isSacrifice", False),
                "is_recapture": is_recapture,
                "is_capture": move_fmt.get("is_capture") if move_fmt else None,
                "is_check": move_fmt.get("is_check") if move_fmt else None,
                "piece_moved": move_fmt.get("piece_moved") if move_fmt else None,
                "pv_len": move_fmt.get("pv_len") if move_fmt else None,
                "prev_classification": prev_classification,
                "in_opening": m.get("in_opening", False),
                "motifs_on_move": {k: v for k, v in motifs.items() if k != "_pv" and v is True},
                "motifs_in_pv": motifs.get("_pv", {}),
                "has_tactic": any(v is True for k, v in motifs.items() if k != "_pv"),
                "before": fmt_move(moves, i - 1),
                "move": move_fmt,
                "after": fmt_move(moves, i + 1),
            })

    elapsed = time.monotonic() - t0
    print(f"Collected in {elapsed:.1f}s (pure Python, no Playwright)")

    for cat in ("brilliant", "great"):
        entries = results[cat]
        tp_n = sum(1 for e in entries if e["status"] == "TP")
        fp_n = sum(1 for e in entries if e["status"] == "FP")
        fn_n = sum(1 for e in entries if e["status"] == "FN")
        print(f"{cat}: TP={tp_n} FP={fp_n} FN={fn_n} (total {len(entries)} moves)")

    out = pathlib.Path("/tmp/classifier_data.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    total = sum(len(v) for v in results.values())
    print(f"\nSaved to {out} ({total} moves)")

    # === Feature statistics ===
    print("\n=== FEATURE STATISTICS (TP vs FP vs FN) ===")

    numeric_features = ["wp_before", "wp_after", "epl_lost", "wp_gain", "cp_gain", "opp_epl", "pv_len"]
    boolean_features = ["is_sacrifice", "is_recapture", "is_capture", "is_check", "in_opening"]

    for cat in ("brilliant", "great"):
        print(f"\n{'='*60}")
        print(f"  {cat.upper()}")
        print(f"{'='*60}")

        by_status: dict[str, list[dict]] = {"TP": [], "FP": [], "FN": []}
        for e in results[cat]:
            by_status[e["status"]].append(e)

        for feat in numeric_features:
            print(f"\n  {feat}:")
            for status in ("TP", "FP", "FN"):
                vals = sorted([e[feat] for e in by_status[status] if e.get(feat) is not None])
                if not vals:
                    print(f"    {status}: (no data)")
                    continue
                med = vals[len(vals) // 2]
                avg = sum(vals) / len(vals)
                print(f"    {status} (n={len(vals):>3}): med={med:>8.4f}  avg={avg:>8.4f}  [{vals[0]:.4f} .. {vals[-1]:.4f}]")

        for feat in boolean_features:
            print(f"\n  {feat}:")
            for status in ("TP", "FP", "FN"):
                entries = by_status[status]
                if not entries:
                    continue
                true_count = sum(1 for e in entries if e.get(feat))
                pct = 100 * true_count / len(entries) if entries else 0
                print(f"    {status} (n={len(entries):>3}): {true_count:>3}/{len(entries)} = {pct:>5.1f}%")

    # === Tactical motif analysis ===
    print("\n\n=== TACTICAL MOTIF ANALYSIS ===")

    for cat in ("brilliant", "great"):
        print(f"\n{'='*60}")
        print(f"  {cat.upper()} — TACTICAL MOTIFS")
        print(f"{'='*60}")

        by_status: dict[str, list[dict]] = {"TP": [], "FP": [], "FN": []}
        for e in results[cat]:
            by_status[e["status"]].append(e)

        print(f"\n  has_tactic:")
        for status in ("TP", "FP", "FN"):
            entries = by_status[status]
            if not entries:
                continue
            has = sum(1 for e in entries if e.get("has_tactic"))
            pct = 100 * has / len(entries)
            print(f"    {status} (n={len(entries):>3}): {has:>3}/{len(entries)} = {pct:>5.1f}%")

        # Per-motif on-move
        motif_names: set[str] = set()
        for entries in by_status.values():
            for e in entries:
                motif_names.update(e.get("motifs_on_move", {}).keys())

        if motif_names:
            print(f"\n  Per-motif (on-move, % True):")
            for name in sorted(motif_names):
                parts = []
                for status in ("TP", "FP", "FN"):
                    entries = by_status[status]
                    if not entries:
                        continue
                    has = sum(1 for e in entries if e.get("motifs_on_move", {}).get(name))
                    if has > 0:
                        parts.append(f"{status}={has}/{len(entries)}({100*has/len(entries):.0f}%)")
                if parts:
                    print(f"    {name:30s} {' '.join(parts)}")


if __name__ == "__main__":
    main()
