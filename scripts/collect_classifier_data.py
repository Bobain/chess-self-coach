"""Collect all !! and ! classified moves (TP/FP/FN) with 3-move context.

Uses the real JS classifier via Playwright (window._classifyMove).
Outputs to /tmp/classifier_data.json.

Usage: uv run python3 scripts/collect_classifier_data.py
"""

from __future__ import annotations

import json
import pathlib

from playwright.sync_api import sync_playwright


def wp(cp: int, sign: int) -> float:
    """Win probability from centipawn score."""
    return 1 / (1 + 10 ** (-cp * sign / 400))


def fmt_move(moves: list[dict], idx: int) -> dict | None:
    """Format a move with its eval context."""
    if idx < 0 or idx >= len(moves):
        return None
    m = moves[idx]
    eb = m.get("eval_before", {})
    ea = m.get("eval_after", {})
    return {
        "label": f"{(idx // 2) + 1}.{'w' if idx % 2 == 0 else 'b'}",
        "san": m.get("move_san", "?"),
        "fen": m.get("fen_before", ""),
        "cp_b": eb.get("score_cp"),
        "cp_a": ea.get("score_cp"),
        "is_mate": eb.get("is_mate", False),
        "mate_in": eb.get("mate_in"),
        "best": eb.get("best_move_san", "?"),
        "is_best": m.get("move_uci") == eb.get("best_move_uci"),
        "pv": " ".join(eb.get("pv_san", [])[:6]),
    }


def main() -> None:
    """Collect classification data."""
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

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("http://localhost:8000")
        # Wait for full app init: game cards rendered means chess.js is loaded
        page.wait_for_selector(".game-card", timeout=30000)
        # Extra wait for JS init to complete
        page.wait_for_function(
            "() => typeof window._classifyMove === 'function'",
            timeout=10000,
        )

        for game_gt in GAMES:
            gid = game_gt["game_id"]
            gt_game = gt_by_id.get(gid)
            if not gt_game:
                continue
            moves = gt_game["moves"]
            brilliant_set = set(game_gt.get("brilliant_indices", []))
            great_set = set(game_gt.get("great_indices", []))

            moves_json = json.dumps(moves)
            classified = page.evaluate(
                f"""() => {{
                const moves = {moves_json};
                return moves.map((m, i) => {{
                    const side = m.side || (i % 2 === 0 ? 'white' : 'black');
                    const prevMove = i > 0 ? moves[i - 1] : null;
                    const cls = window._classifyMove(m, side, prevMove);
                    return cls ? cls.category : 'other';
                }});
            }}"""
            )

            for i, (m, predicted) in enumerate(zip(moves, classified)):
                if predicted not in ("brilliant", "great"):
                    predicted = "other"
                expected = (
                    "brilliant"
                    if i in brilliant_set
                    else "great"
                    if i in great_set
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
                    if (
                        peb.get("score_cp") is not None
                        and pea.get("score_cp") is not None
                        and not peb.get("is_mate")
                        and not pea.get("is_mate")
                    ):
                        opp_sign = -sign
                        opp_epl = round(
                            wp(peb["score_cp"], opp_sign)
                            - wp(pea["score_cp"], opp_sign),
                            4,
                        )

                eb = m.get("eval_before", {})
                ea = m.get("eval_after", {})
                wp_b = epl = None
                if eb.get("score_cp") is not None and not eb.get("is_mate"):
                    wp_b = round(wp(eb["score_cp"], sign), 4)
                    if ea.get("score_cp") is not None and not ea.get("is_mate"):
                        epl = round(wp_b - wp(ea["score_cp"], sign), 4)

                status = (
                    "TP"
                    if expected == predicted
                    else ("FN" if expected in ("brilliant", "great") else "FP")
                )
                cat = (
                    "brilliant"
                    if "brilliant" in (expected, predicted)
                    else "great"
                )
                results[cat].append(
                    {
                        "game": gid[:30],
                        "idx": i,
                        "status": status,
                        "predicted": predicted,
                        "expected": expected,
                        "wp_before": wp_b,
                        "epl_lost": epl,
                        "opp_epl": opp_epl,
                        "before": fmt_move(moves, i - 1),
                        "move": fmt_move(moves, i),
                        "after": fmt_move(moves, i + 1),
                    }
                )

        browser.close()

    for cat in ("brilliant", "great"):
        entries = results[cat]
        tp = sum(1 for e in entries if e["status"] == "TP")
        fp = sum(1 for e in entries if e["status"] == "FP")
        fn = sum(1 for e in entries if e["status"] == "FN")
        print(
            f"{cat}: TP={tp} FP={fp} FN={fn} (total {len(entries)} moves)"
        )

    # Save full data
    out = pathlib.Path("/tmp/classifier_data.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    total = sum(len(v) for v in results.values())
    print(f"\nSaved to {out} ({total} moves)")

    # Prepare batches for agent analysis (~15 moves each, mixing TP/FP/FN)
    all_moves = []
    for cat in ("brilliant", "great"):
        for entry in results[cat]:
            entry["category"] = cat
            all_moves.append(entry)

    batch_size = 15
    batches = [
        all_moves[i : i + batch_size]
        for i in range(0, len(all_moves), batch_size)
    ]

    batches_out = pathlib.Path("/tmp/classifier_batches.json")
    with open(batches_out, "w") as f:
        json.dump(batches, f, indent=2)
    print(f"Prepared {len(batches)} batches of ~{batch_size} moves → {batches_out}")


if __name__ == "__main__":
    main()
