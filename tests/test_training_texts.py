"""Validation tests for training_data.json texts.

Scans training data and verifies that all user-facing texts are correct,
coherent, and sufficiently informative. Skipped if training data doesn't exist.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

TRAINING_DATA_PATH = Path(__file__).parent.parent / "training_data.json"


@pytest.fixture(scope="module")
def positions():
    """Load positions from training_data.json, skip if not present."""
    if not TRAINING_DATA_PATH.exists():
        pytest.skip("training_data.json not found (run train --prepare first)")
    with open(TRAINING_DATA_PATH) as f:
        data = json.load(f)
    return data.get("positions", [])


def test_no_unknown_source(positions):
    """Every position must have a known source (lichess or chess.com)."""
    unknown = [p for p in positions if p["game"]["source"] == "unknown"]
    assert not unknown, (
        f"{len(unknown)} position(s) have source 'unknown': "
        f"{[p['game'].get('id', p['id']) for p in unknown[:5]]}"
    )


def test_no_excessive_pawn_loss_in_text(positions):
    """Explanations should not mention pawn counts > 50 (sign of a mate bug)."""
    pattern = re.compile(r"(\d+\.?\d*)\s*pawns?")
    bad = []
    for p in positions:
        for field in ("explanation", "context"):
            text = p.get(field, "")
            for match in pattern.finditer(text):
                value = float(match.group(1))
                if value > 50:
                    bad.append((p["id"], field, text[:80]))
    assert not bad, f"{len(bad)} text(s) with >50 pawns: {bad[:3]}"


def test_context_not_empty(positions):
    """Every position must have a non-empty context."""
    missing = [p["id"] for p in positions if not p.get("context")]
    assert not missing, f"{len(missing)} position(s) have empty context"


def test_pv_has_moves(positions):
    """Every position should have at least 1 move in the principal variation."""
    empty_pv = [p["id"] for p in positions if not p.get("pv")]
    assert not empty_pv, f"{len(empty_pv)} position(s) have empty PV"


def test_no_question_marks_in_game_info(positions):
    """Opponent and date should not be '?' placeholders."""
    bad = []
    for p in positions:
        game = p.get("game", {})
        if game.get("opponent") == "?":
            bad.append((p["id"], "opponent"))
        if game.get("date") == "?":
            bad.append((p["id"], "date"))
    assert not bad, f"{len(bad)} position(s) with '?' in game info: {bad[:5]}"


def test_cp_loss_matches_category(positions):
    """cp_loss must be consistent with the category classification."""
    thresholds = {"blunder": 200, "mistake": 100, "inaccuracy": 50}
    bad = []
    for p in positions:
        category = p["category"]
        cp_loss = p["cp_loss"]
        min_cp = thresholds.get(category, 0)
        if cp_loss < min_cp:
            bad.append((p["id"], category, cp_loss))
    assert not bad, f"{len(bad)} position(s) with mismatched cp_loss/category: {bad[:5]}"
