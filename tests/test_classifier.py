"""Tests for the Python move classifier.

Ports the JS-based classification tests to pure Python.
Tests classify_move() directly — no Playwright, no browser.
"""

from __future__ import annotations

from chess_self_coach.classifier import classify_move, score_classifier, MIN_SCORE


# --- Checkmate classification ---


def test_checkmate_classified_as_best_black():
    """Checkmate delivered by black must be 'best'."""
    move = {
        "eval_before": {"score_cp": -10000, "is_mate": True, "mate_in": -1},
        "eval_after": {"score_cp": -10000, "is_mate": True, "mate_in": 0},
    }
    result = classify_move(move, "black", None)
    assert result is not None
    assert result["c"] == "best"


def test_checkmate_classified_as_best_white():
    """Checkmate delivered by white must be 'best'."""
    move = {
        "eval_before": {"score_cp": 10000, "is_mate": True, "mate_in": 1},
        "eval_after": {"score_cp": 10000, "is_mate": True, "mate_in": 0},
    }
    result = classify_move(move, "white", None)
    assert result is not None
    assert result["c"] == "best"


# --- Brilliant detection ---


def test_sacrifice_is_brilliant():
    """A sacrifice (material loss in PV chain) is brilliant when it improves position."""
    move = {
        "fen_before": "r1bqk2r/pppp1ppp/2n2n2/4p3/1bB1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
        "move_uci": "d2d4",
        "move_san": "d4",
        "eval_before": {
            "score_cp": 50, "is_mate": False, "mate_in": None,
            "best_move_uci": "d2d4",
            "pv_uci": ["d2d4", "e5d4", "e4e5", "d4d3"],
        },
        "eval_after": {"score_cp": 60, "is_mate": False, "mate_in": None},
        "in_opening": False,
    }
    tactics = {"isSacrifice": True}
    result = classify_move(move, "white", None, tactics)
    assert result is not None
    assert result["c"] == "brilliant"


def test_non_sacrifice_not_brilliant():
    """Best move that isn't a sacrifice should NOT be brilliant."""
    move = {
        "eval_before": {"score_cp": 50, "is_mate": False, "mate_in": None, "best_move_uci": "e2e4"},
        "eval_after": {"score_cp": 60, "is_mate": False, "mate_in": None},
        "move_uci": "e2e4",
        "in_opening": False,
    }
    tactics = {"isSacrifice": False}
    result = classify_move(move, "white", None, tactics)
    assert result is not None
    assert result["c"] != "brilliant"


def test_sacrifice_in_dominating_position_not_brilliant():
    """Sacrifice when already dominating (wpBefore > 0.95) is not brilliant."""
    move = {
        "eval_before": {"score_cp": 800, "is_mate": False, "mate_in": None, "best_move_uci": "d2d4"},
        "eval_after": {"score_cp": 850, "is_mate": False, "mate_in": None},
        "move_uci": "d2d4",
        "in_opening": False,
    }
    tactics = {"isSacrifice": True}
    result = classify_move(move, "white", None, tactics)
    assert result is None or result["c"] != "brilliant"


# --- Great detection ---


def test_response_to_blunder_is_great():
    """A good response to opponent's blunder (oppEpl >= 0.15) is great."""
    # Opponent (black) blunders: was ahead (-200cp), now behind (+200cp)
    prev_move = {
        "eval_before": {"score_cp": -200, "is_mate": False, "mate_in": None},
        "eval_after": {"score_cp": 200, "is_mate": False, "mate_in": None},
    }
    # White responds well: maintains the advantage
    move = {
        "eval_before": {"score_cp": 200, "is_mate": False, "mate_in": None},
        "eval_after": {"score_cp": 195, "is_mate": False, "mate_in": None},
        "in_opening": False,
    }
    result = classify_move(move, "white", prev_move)
    assert result is not None
    assert result["c"] == "great"


# --- Miss detection ---


def test_missed_capture_is_miss():
    """Missing a capture after opponent blunder is classified as miss."""
    # Opponent (black) blunders: was ahead, now behind
    prev_move = {
        "eval_before": {"score_cp": -300, "is_mate": False, "mate_in": None},
        "eval_after": {"score_cp": 300, "is_mate": False, "mate_in": None},
    }
    # White misses the winning capture
    move = {
        "eval_before": {
            "score_cp": 300, "is_mate": False, "mate_in": None,
            "best_move_uci": "e4d5", "best_move_san": "exd5",
        },
        "eval_after": {"score_cp": 100, "is_mate": False, "mate_in": None},
        "move_uci": "a2a3",
        "in_opening": False,
    }
    tactics = {"isMissedCapture": True}
    result = classify_move(move, "white", prev_move, tactics)
    assert result is not None
    assert result["c"] == "miss"


def test_missed_positional_not_miss():
    """Missing a positional move (not a capture) is NOT classified as miss."""
    prev_move = {
        "eval_before": {"score_cp": 0, "is_mate": False, "mate_in": None},
        "eval_after": {"score_cp": -200, "is_mate": False, "mate_in": None},
    }
    move = {
        "eval_before": {
            "score_cp": 200, "is_mate": False, "mate_in": None,
            "best_move_uci": "e4e5", "best_move_san": "e5",
        },
        "eval_after": {"score_cp": 50, "is_mate": False, "mate_in": None},
        "move_uci": "a2a3",
        "in_opening": False,
    }
    tactics = {"isMissedCapture": False}
    result = classify_move(move, "white", prev_move, tactics)
    assert result is None or result["c"] != "miss"


# --- EPL thresholds ---


def test_epl_thresholds():
    """Verify EPL-based classification thresholds."""
    for cp_after, expected in [
        (55, "best"),       # epl_lost <= 0
        (45, "excellent"),  # epl_lost <= 0.02
        (30, "good"),       # epl_lost <= 0.05
        (0, "inaccuracy"),  # epl_lost <= 0.10
        (-50, "mistake"),   # epl_lost <= 0.20
        (-200, "blunder"),  # epl_lost > 0.20
    ]:
        move = {
            "eval_before": {"score_cp": 50, "is_mate": False, "mate_in": None},
            "eval_after": {"score_cp": cp_after, "is_mate": False, "mate_in": None},
            "in_opening": False,
        }
        result = classify_move(move, "white", None)
        assert result is not None, f"cp_after={cp_after} returned None"
        assert result["c"] == expected, f"cp_after={cp_after}: got '{result['c']}', expected '{expected}'"


# --- Regression test (score) ---


def test_classifier_score_regression():
    """Regularized score must not drop below threshold."""
    result = score_classifier(verbose=True)
    assert result["score"] >= MIN_SCORE, (
        f"Regularized score {result['score']:.3f} dropped below {MIN_SCORE}"
    )
