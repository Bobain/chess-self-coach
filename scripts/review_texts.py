"""Semantic review of training_data.json texts.

Samples 15 positions and checks for correctness, context quality, and anomalies.
Used by /rloop command. Exit code 0 = all clean, 1 = issues found.
"""

import json
import re
import sys

import chess


def main():
    with open("training_data.json") as f:
        data = json.load(f)

    sample = data["positions"]
    issues = []

    for p in sample:
        board = chess.Board(p["fen"])
        try:
            board.parse_san(p["player_move"])
        except ValueError:
            issues.append(("INVALID_PLAYER", p["id"], p["player_move"]))
        try:
            board.parse_san(p["best_move"])
        except ValueError:
            issues.append(("INVALID_BEST", p["id"], p["best_move"]))
        if p["player_move"] == p["best_move"]:
            issues.append(("DUPE", p["id"], p["player_move"]))

        ctx = p.get("context", "")
        if not any(ph in ctx for ph in ["Opening", "Middlegame", "Endgame"]):
            issues.append(("NO_PHASE", p["id"], ctx[:60]))
        if not any(
            a in ctx
            for a in [
                "advantage", "equal", "worse", "difficult",
                "winning", "draw", "checkmate", "forced mate",
            ]
        ):
            issues.append(("NO_ADV", p["id"], ctx[:60]))

        expl = p.get("explanation", "")
        if p["best_move"] not in expl:
            issues.append(("NO_BEST", p["id"], p["best_move"]))

        for field in ("context", "explanation"):
            for m in re.finditer(r"(\d+\.?\d*)\s*pawns?", p.get(field, "")):
                if float(m.group(1)) > 20:
                    issues.append(("EXCESS", p["id"], m.group(0)))

        if p["game"]["source"] == "unknown":
            issues.append(("UNKNOWN", p["id"], ""))

    print(f"Reviewed {len(sample)} positions. Issues: {len(issues)}")
    for t, pid, d in issues:
        print(f"  [{t}] {pid}: {d}")
    if not issues:
        print("  All clean!")

    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
