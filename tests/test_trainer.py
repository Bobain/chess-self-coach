"""Tests for trainer.py pure functions."""

from __future__ import annotations

import chess

from chess_self_coach.constants import (
    BLUNDER_THRESHOLD,
    INACCURACY_THRESHOLD,
    MISTAKE_THRESHOLD,
)
from chess_self_coach.trainer import (
    classify_mistake,
    format_score_cp,
    time_pressure_context,
    generate_explanation,
)


# --- classify_mistake ---


def test_classify_blunder():
    assert classify_mistake(250) == "blunder"


def testclassify_mistake_category():
    assert classify_mistake(150) == "mistake"


def test_classify_inaccuracy():
    assert classify_mistake(75) == "inaccuracy"


def test_classify_ok():
    assert classify_mistake(30) is None


def test_classify_boundary_blunder():
    assert classify_mistake(BLUNDER_THRESHOLD) == "blunder"


def test_classify_boundary_mistake():
    assert classify_mistake(MISTAKE_THRESHOLD) == "mistake"


def test_classify_boundary_inaccuracy():
    assert classify_mistake(INACCURACY_THRESHOLD) == "inaccuracy"


def test_classify_just_below_inaccuracy():
    assert classify_mistake(INACCURACY_THRESHOLD - 1) is None


# --- format_score_cp ---


def testformat_score_cp_positive():
    assert format_score_cp(150) == "+1.50"


def testformat_score_cp_negative():
    assert format_score_cp(-75) == "-0.75"


def testformat_score_cp_zero():
    assert format_score_cp(0) == "+0.00"


def testformat_score_cp_none():
    assert format_score_cp(None) == "+0.00"


# --- generate_explanation ---


def test_explanation_basic():
    """Basic explanation includes move, category, and best move."""
    board = chess.Board()  # starting position
    result = generate_explanation(board, "a3", "e4", 50, "inaccuracy")
    assert "You played a3" in result
    assert "inaccuracy" in result
    assert "e4" in result


def test_explanation_capture():
    """Explanation mentions missed capture."""
    # Position where Bxf7+ is possible
    board = chess.Board("r1bqkbnr/pppppppp/2n5/4P3/2B5/8/PPP2PPP/RNBQK1NR w KQkq - 0 4")
    result = generate_explanation(board, "d3", "Bxf7+", 200, "blunder")
    assert "capturing" in result or "pawn" in result


def test_explanation_invalid_best_san():
    """Graceful fallback when best_san can't be parsed."""
    board = chess.Board()
    result = generate_explanation(board, "e4", "INVALID", 100, "mistake")
    assert "A better move was INVALID" in result


# --- time_pressure_context ---


def test_time_pressure_none():
    """No clock data returns empty string."""
    assert time_pressure_context(None, None) == ""


def test_time_pressure_severe():
    """Under 2 minutes with opponent having much more time."""
    result = time_pressure_context(90, 420)  # 1.5min vs 7min
    assert "severe time pressure" in result
    assert "1min" in result or "2min" in result


def test_time_pressure_low():
    """Under 2 minutes without large opponent advantage."""
    result = time_pressure_context(60, 90)  # 1min vs 1.5min
    assert "time pressure" in result
    assert "severe" not in result


def test_time_advantage():
    """Player has significantly more time than opponent."""
    result = time_pressure_context(600, 300)  # 10min vs 5min
    assert "more time" in result
    assert "could have taken longer" in result


def test_time_neutral():
    """Similar clocks, no time pressure."""
    result = time_pressure_context(600, 500)  # 10min vs 8min
    assert result == ""
