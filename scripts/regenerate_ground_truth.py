"""Regenerate classification_ground_truth.json from analysis_data.json.

Rebuilds every `moves` array in the fixture using the current simplify_move
schema so that the sweep operates on the same feature set as the production
classifier. Labels (brilliant_indices/great_indices) are preserved from the
existing fixture — this only refreshes the move data.

Usage: uv run python scripts/regenerate_ground_truth.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Callable


def _load_simplify_move() -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Load simplify_move from add_ground_truth_game without package hassle."""
    src = Path(__file__).resolve().parent / "add_ground_truth_game.py"
    spec = importlib.util.spec_from_file_location("add_ground_truth_game", src)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.simplify_move  # type: ignore[attr-defined, no-any-return]


simplify_move = _load_simplify_move()


PLAYER = "Tonigor1982"


def main() -> None:
    """Regenerate the ground truth fixture in place."""
    repo = Path(__file__).resolve().parent.parent
    analysis_path = repo / "data" / "analysis_data.json"
    gt_path = repo / "tests" / "e2e" / "fixtures" / "classification_ground_truth.json"

    with open(analysis_path) as f:
        analysis = json.load(f)
    with open(gt_path) as f:
        gt = json.load(f)

    # num_id -> url
    url_by_numid: dict[str, str] = {}
    for url in analysis["games"]:
        num_id = url.rstrip("/").split("/")[-1]
        url_by_numid[num_id] = url

    missing: list[str] = []
    updated = 0
    for entry in gt["games"]:
        num_id = entry["game_id"].split("_")[-1]
        url = url_by_numid.get(num_id)
        if not url:
            missing.append(entry["game_id"])
            continue
        game_data = analysis["games"][url]
        headers = game_data["headers"]
        entry["player_color"] = "white" if headers["white"] == PLAYER else "black"
        entry["moves"] = [simplify_move(m) for m in game_data["moves"]]
        updated += 1

    with open(gt_path, "w") as f:
        json.dump(gt, f, separators=(",", ":"))
        f.write("\n")

    print(f"Regenerated {updated} games in {gt_path}")
    if missing:
        print(f"WARNING: {len(missing)} games have no analysis data:")
        for gid in missing:
            print(f"  {gid}")


if __name__ == "__main__":
    main()
