"""Tests for analyze.py pure functions."""

from __future__ import annotations

import chess.engine

from chess_self_coach.analyze import (
    _add_annotation_to_comment,
    _extract_score_value,
    _format_score,
    _has_annotation,
)


# --- _format_score ---


def test_format_score_positive():
    """Positive centipawn score formats correctly."""
    score = chess.engine.PovScore(chess.engine.Cp(123), chess.WHITE)
    result = _format_score(score, chess.WHITE)
    assert result == "[%eval +1.23]"


def test_format_score_negative():
    """Negative centipawn score formats correctly."""
    score = chess.engine.PovScore(chess.engine.Cp(-45), chess.WHITE)
    result = _format_score(score, chess.WHITE)
    assert result == "[%eval -0.45]"


def test_format_score_zero():
    """Zero centipawn score formats correctly."""
    score = chess.engine.PovScore(chess.engine.Cp(0), chess.WHITE)
    result = _format_score(score, chess.WHITE)
    assert result == "[%eval +0.00]"


def test_format_score_mate_positive():
    """Positive mate score formats correctly."""
    score = chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE)
    result = _format_score(score, chess.WHITE)
    assert result == "[%eval #+3]"


def test_format_score_mate_negative():
    """Negative mate score formats correctly."""
    score = chess.engine.PovScore(chess.engine.Mate(-5), chess.WHITE)
    result = _format_score(score, chess.WHITE)
    assert result == "[%eval #-5]"


# --- _has_annotation ---


def test_has_annotation_true():
    """Comment with score annotation is detected."""
    assert _has_annotation("[%eval +0.32] Some comment") is True


def test_has_annotation_false():
    """Comment without annotation is not detected."""
    assert _has_annotation("Some comment without annotation") is False


def test_has_annotation_no_eval():
    """Empty comment has no annotation."""
    assert _has_annotation("") is False


# --- _add_annotation_to_comment ---


def test_add_annotation_to_comment_empty():
    """Adding annotation to empty comment returns annotation + space."""
    result = _add_annotation_to_comment("", "[%eval +0.32]")
    assert result == "[%eval +0.32] "


def test_add_annotation_to_comment_with_text():
    """Adding annotation to existing comment prepends it."""
    result = _add_annotation_to_comment("Existing comment", "[%eval +0.32]")
    assert result == "[%eval +0.32] Existing comment"


# --- _extract_score_value ---


def test_extract_score_value_positive():
    """Extracts positive score from annotation."""
    result = _extract_score_value("[%eval +1.50] Good move")
    assert result == 1.50


def test_extract_score_value_negative():
    """Extracts negative score from annotation."""
    result = _extract_score_value("[%eval -0.75] Dubious")
    assert result == -0.75


def test_extract_score_value_mate_returns_none():
    """Mate scores return None (not a numeric value)."""
    result = _extract_score_value("[%eval #+3] Mate in 3")
    assert result is None


def test_extract_score_value_malformed():
    """Malformed or missing annotation returns None."""
    result = _extract_score_value("No annotation here")
    assert result is None
