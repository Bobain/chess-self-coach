"""Add a game to the classification ground truth JSON fixture.

Usage: uv run python scripts/add_ground_truth_game.py <URL> <GAME_ID> [BRILLIANT_INDICES] [GREAT_INDICES]

Example:
  uv run python scripts/add_ground_truth_game.py \
    "https://www.chess.com/game/live/125083720203" \
    "Has101010_125083720203" \
    "" \
    "19,31"
"""

from __future__ import annotations

import json
import sys


def main() -> None:
    """Add a game to classification_ground_truth.json."""
    if len(sys.argv) < 3:
        print("Usage: add_ground_truth_game.py <URL> <GAME_ID> [BRILLIANT] [GREAT]")
        sys.exit(1)

    url = sys.argv[1]
    gt_id = sys.argv[2]
    brilliant_str = sys.argv[3] if len(sys.argv) > 3 else ""
    great_str = sys.argv[4] if len(sys.argv) > 4 else ""

    brilliant_indices = [int(x) for x in brilliant_str.split(",") if x.strip()]
    great_indices = [int(x) for x in great_str.split(",") if x.strip()]

    with open("data/analysis_data.json") as f:
        analysis = json.load(f)

    game_data = analysis["games"][url]
    moves = game_data["moves"]

    simplified_moves = []
    for m in moves:
        eb = m.get("eval_before", {})
        ea = m.get("eval_after", {})
        simplified_moves.append({
            "fen_before": m.get("fen_before", ""),
            "move_san": m.get("move_san", ""),
            "move_uci": m.get("move_uci", ""),
            "side": m.get("side", ""),
            "in_opening": m.get("in_opening", False),
            "eval_before": {
                "score_cp": eb.get("score_cp"),
                "is_mate": eb.get("is_mate", False),
                "mate_in": eb.get("mate_in"),
                "best_move_uci": eb.get("best_move_uci"),
                "pv_uci": eb.get("pv_uci", []),
                "pv_san": eb.get("pv_san", []),
            },
            "eval_after": {
                "score_cp": ea.get("score_cp"),
                "is_mate": ea.get("is_mate", False),
                "mate_in": ea.get("mate_in"),
            },
        })

    headers = game_data["headers"]
    player = "Tonigor1982"
    player_color = "white" if headers["white"] == player else "black"

    game_entry = {
        "game_id": gt_id,
        "player_color": player_color,
        "moves": simplified_moves,
    }

    gt_path = "tests/e2e/fixtures/classification_ground_truth.json"
    with open(gt_path) as f:
        gt = json.load(f)

    gt["games"].append(game_entry)

    with open(gt_path, "w") as f:
        json.dump(gt, f, separators=(",", ":"))
        f.write("\n")

    print(f"Added {gt_id} to ground truth ({len(gt['games'])} games total)")
    print(f"Brilliant indices: {brilliant_indices}")
    print(f"Great indices: {great_indices}")


if __name__ == "__main__":
    main()
