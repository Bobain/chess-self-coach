"""Tests for tablebase.py — WDL classification, context, and explanation."""

from __future__ import annotations

import chess

from chess_self_coach.tablebase import (
    TablebaseResult,
    tablebase_context,
    tablebase_cp_loss,
    tablebase_explanation,
)


def _tb(category: str, dtz: int | None = None, dtm: int | None = None) -> TablebaseResult:
    """Shortcut to create a TablebaseResult."""
    return TablebaseResult(category=category, dtz=dtz, dtm=dtm, best_move=None)


# --- tablebase_cp_loss ---


def test_classify_win_to_draw():
    """Win -> Draw is a blunder (300cp)."""
    assert tablebase_cp_loss(_tb("win"), _tb("draw"), chess.WHITE) == 300


def test_classify_win_to_loss():
    """Win -> Loss is a severe blunder (600cp)."""
    assert tablebase_cp_loss(_tb("win"), _tb("loss"), chess.WHITE) == 600


def test_classify_draw_to_loss():
    """Draw -> Loss is a blunder (300cp)."""
    assert tablebase_cp_loss(_tb("draw"), _tb("loss"), chess.WHITE) == 300


def test_classify_win_to_win():
    """Win -> Win is acceptable (0cp)."""
    assert tablebase_cp_loss(_tb("win", dtz=5), _tb("win", dtz=40), chess.WHITE) == 0


def test_classify_draw_to_draw():
    """Draw -> Draw is acceptable (0cp)."""
    assert tablebase_cp_loss(_tb("draw"), _tb("draw"), chess.WHITE) == 0


def test_classify_loss_to_loss():
    """Loss -> Loss is acceptable (0cp)."""
    assert tablebase_cp_loss(_tb("loss"), _tb("loss"), chess.WHITE) == 0


def test_classify_loss_to_draw():
    """Loss -> Draw (opponent blundered) is acceptable (0cp)."""
    assert tablebase_cp_loss(_tb("loss"), _tb("draw"), chess.WHITE) == 0


def test_classify_cursed_win_treated_as_draw():
    """cursed-win is grouped with DRAW tier."""
    assert tablebase_cp_loss(_tb("win"), _tb("cursed-win"), chess.WHITE) == 300


def test_classify_blessed_loss_treated_as_draw():
    """blessed-loss is grouped with DRAW tier."""
    assert tablebase_cp_loss(_tb("blessed-loss"), _tb("loss"), chess.WHITE) == 300


def test_classify_black_perspective():
    """Black's perspective is flipped: API 'loss' for Black means side-to-move loses."""
    # From API: before=loss (Black is losing), after=draw
    # From Black's perspective: before=WIN (opponent losing), after=DRAW
    # This is a blunder for Black? No — the API categories are already from
    # side-to-move perspective. We flip to normalize.
    # before=loss -> flipped to WIN, after=draw -> stays DRAW -> WIN->DRAW = 300
    assert tablebase_cp_loss(_tb("loss"), _tb("draw"), chess.BLACK) == 300


# --- format_verdict ---


def test_format_verdict_win_with_dtm():
    assert _tb("win", dtm=23).format_verdict() == "win, mate in 23"


def test_format_verdict_draw():
    assert _tb("draw").format_verdict() == "draw"


def test_format_verdict_loss_with_dtz():
    assert _tb("loss", dtz=-15).format_verdict() == "loss (DTZ 15)"


# --- tablebase_context ---


def test_context_text_win():
    ctx = tablebase_context(_tb("win", dtm=23), 5, "white")
    assert "Tablebase" in ctx
    assert "theoretical win" in ctx
    assert "5 pieces" in ctx
    assert "playing as White" in ctx


def test_context_text_draw():
    ctx = tablebase_context(_tb("draw"), 4, "black")
    assert "theoretical draw" in ctx
    assert "playing as Black" in ctx


# --- tablebase_explanation ---


def test_explanation_win_to_draw():
    exp = tablebase_explanation(_tb("win", dtm=23), _tb("draw"), "Kd4", "Ke4")
    assert "theoretical win" in exp
    assert "Kd4" in exp
    assert "draw" in exp
    assert "Ke4" in exp


def test_explanation_no_best_move():
    exp = tablebase_explanation(_tb("draw"), _tb("loss"), "Kf3", None)
    assert "Kf3" in exp
    assert "loss" in exp


# --- Perspective correctness (bug regression tests) ---
# Position: 8/p7/1P6/P1k4K/6p1/8/7P/8 b - - 0 44
# White has advanced pawns (a5+b6), Black is LOST. API: category="loss".
# Mirror: 8/7p/8/6P1/p1K4k/1p6/P7/8 w - - 0 44
# Same position, colors swapped. White is LOST. API: category="loss".


import pytest
from chess_self_coach.tablebase import probe_position


@pytest.mark.network
def test_probe_black_losing():
    """API correctly reports Black is losing (side-to-move perspective)."""
    result = probe_position("8/p7/1P6/P1k4K/6p1/8/7P/8 b - - 0 44")
    assert result is not None, "API should return a result for 7-piece position"
    assert result.tier == "LOSS", (
        f"Black is losing but API returned tier={result.tier} "
        f"(category={result.category})"
    )


@pytest.mark.network
def test_probe_white_losing_mirror():
    """Mirrored position: API correctly reports White is losing."""
    result = probe_position("8/7p/8/6P1/p1K4k/1p6/P7/8 w - - 0 44")
    assert result is not None, "API should return a result for 7-piece position"
    assert result.tier == "LOSS", (
        f"White is losing but API returned tier={result.tier} "
        f"(category={result.category})"
    )


@pytest.mark.network
def test_probe_symmetry():
    """Both positions are symmetrical — same tier from side-to-move perspective."""
    black_result = probe_position("8/p7/1P6/P1k4K/6p1/8/7P/8 b - - 0 44")
    white_result = probe_position("8/7p/8/6P1/p1K4k/1p6/P7/8 w - - 0 44")
    assert black_result is not None and white_result is not None
    assert black_result.tier == white_result.tier == "LOSS"


def test_context_black_losing_says_difficult():
    """When Black is losing (API: loss), context must say 'difficult', not 'winning'."""
    tb = _tb("loss", dtz=2)
    ctx = tablebase_context(tb, 7, "black")
    assert "difficult" in ctx, f"Black is losing but context says: {ctx}"
    assert "winning" not in ctx


def test_context_black_winning_says_winning():
    """When Black is winning (API: win), context must say 'winning'."""
    tb = _tb("win", dtz=-10)
    ctx = tablebase_context(tb, 7, "black")
    assert "winning" in ctx, f"Black is winning but context says: {ctx}"


def test_cp_loss_black_loss_to_win_is_blunder():
    """Black LOSS→WIN (side-to-move): after flip = WIN→LOSS = 600cp blunder."""
    cp = tablebase_cp_loss(_tb("loss"), _tb("win"), chess.BLACK)
    assert cp == 600, f"Expected 600 cp_loss for flipped WIN→LOSS, got {cp}"


def test_cp_loss_white_win_to_loss_is_blunder():
    """White WIN→LOSS (no flip needed): 600cp blunder."""
    cp = tablebase_cp_loss(_tb("win"), _tb("loss"), chess.WHITE)
    assert cp == 600, f"Expected 600 cp_loss for WIN→LOSS, got {cp}"
