"""Tests for trainer.py pure functions."""

from __future__ import annotations

import chess

from chess_self_coach.constants import (
    BLUNDER_THRESHOLD,
    INACCURACY_THRESHOLD,
    MISTAKE_THRESHOLD,
)
from chess_self_coach.trainer import (
    _analysis_limit,
    _classify_mistake,
    _format_score_cp,
    _time_pressure_context,
    compute_cp_loss,
    generate_explanation,
)


# --- compute_cp_loss ---


def test_cp_loss_white_loses_advantage():
    """White had +100, now +20: lost 80cp."""
    assert compute_cp_loss(100, 20, chess.WHITE) == 80


def test_cp_loss_white_gains():
    """White had +100, now +150: gained (negative loss)."""
    assert compute_cp_loss(100, 150, chess.WHITE) == -50


def test_cp_loss_black_loses_advantage():
    """Eval was -100 (good for black), now -20: black lost 80cp."""
    assert compute_cp_loss(-100, -20, chess.BLACK) == 80


def test_cp_loss_black_gains():
    """Eval was -100, now -150: black gained (negative loss)."""
    assert compute_cp_loss(-100, -150, chess.BLACK) == -50


def test_cp_loss_zero():
    """No change in position means zero loss."""
    assert compute_cp_loss(50, 50, chess.WHITE) == 0


# --- _classify_mistake ---


def test_classify_blunder():
    assert _classify_mistake(250) == "blunder"


def test_classify_mistake_category():
    assert _classify_mistake(150) == "mistake"


def test_classify_inaccuracy():
    assert _classify_mistake(75) == "inaccuracy"


def test_classify_ok():
    assert _classify_mistake(30) is None


def test_classify_boundary_blunder():
    assert _classify_mistake(BLUNDER_THRESHOLD) == "blunder"


def test_classify_boundary_mistake():
    assert _classify_mistake(MISTAKE_THRESHOLD) == "mistake"


def test_classify_boundary_inaccuracy():
    assert _classify_mistake(INACCURACY_THRESHOLD) == "inaccuracy"


def test_classify_just_below_inaccuracy():
    assert _classify_mistake(INACCURACY_THRESHOLD - 1) is None


# --- _format_score_cp ---


def test_format_score_cp_positive():
    assert _format_score_cp(150) == "+1.50"


def test_format_score_cp_negative():
    assert _format_score_cp(-75) == "-0.75"


def test_format_score_cp_zero():
    assert _format_score_cp(0) == "+0.00"


def test_format_score_cp_none():
    assert _format_score_cp(None) == "+0.00"


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


# --- _analysis_limit ---


def test_analysis_limit_kings_and_pawns():
    """King+pawns endgame (<=7 pieces) gets maximum time."""
    board = chess.Board("8/4k3/8/8/8/3K4/4P3/8 w - - 0 1")  # K+P vs K
    limit = _analysis_limit(board, 18)
    assert limit.time == 10.0
    assert limit.depth == 60


def test_analysis_limit_pure_endgame():
    """Endgame with pieces (<=7) gets high time."""
    board = chess.Board("8/4k3/8/8/8/3K4/4R3/8 w - - 0 1")  # K+R vs K
    limit = _analysis_limit(board, 18)
    assert limit.time == 10.0
    assert limit.depth == 50


def test_analysis_limit_late_middlegame():
    """8-12 pieces gets moderate time."""
    # 10 pieces: 2K + 2R + 2B + 4P
    board = chess.Board("r1b1k3/8/8/8/8/8/4PP2/R1B1K3 w - - 0 1")
    assert len(board.piece_map()) <= 12
    assert len(board.piece_map()) > 7
    limit = _analysis_limit(board, 18)
    assert limit.time == 10.0
    assert limit.depth == 40


def test_analysis_limit_opening():
    """Many pieces (>12) uses default depth with time cap."""
    board = chess.Board()  # Starting position, 32 pieces
    limit = _analysis_limit(board, 18)
    assert limit.time == 10.0
    assert limit.depth == 18


# --- _time_pressure_context ---


def test_time_pressure_none():
    """No clock data returns empty string."""
    assert _time_pressure_context(None, None) == ""


def test_time_pressure_severe():
    """Under 2 minutes with opponent having much more time."""
    result = _time_pressure_context(90, 420)  # 1.5min vs 7min
    assert "severe time pressure" in result
    assert "1min" in result or "2min" in result


def test_time_pressure_low():
    """Under 2 minutes without large opponent advantage."""
    result = _time_pressure_context(60, 90)  # 1min vs 1.5min
    assert "time pressure" in result
    assert "severe" not in result


def test_time_advantage():
    """Player has significantly more time than opponent."""
    result = _time_pressure_context(600, 300)  # 10min vs 5min
    assert "more time" in result
    assert "could have taken longer" in result


def test_time_neutral():
    """Similar clocks, no time pressure."""
    result = _time_pressure_context(600, 500)  # 10min vs 8min
    assert result == ""
