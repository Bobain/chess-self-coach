"""Tests for tablebase.py — WDL classification, context, and explanation."""

from __future__ import annotations

from chess_self_coach.tablebase import (
    TablebaseResult,
    tablebase_context,
    tablebase_explanation,
)


def _tb(category: str, dtz: int | None = None, dtm: int | None = None) -> TablebaseResult:
    """Shortcut to create a TablebaseResult."""
    return TablebaseResult(category=category, dtz=dtz, dtm=dtm, best_move=None)


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


# --- probe_position_full ---


from unittest.mock import MagicMock, patch

from chess_self_coach.tablebase import probe_position_full


@patch("chess_self_coach.tablebase.requests.get")
def test_probe_position_full_returns_complete_data(mock_get: MagicMock):
    """Returns full API response including all moves."""
    api_data = {
        "category": "win",
        "dtz": -20,
        "dtm": -20,
        "precise_dtz": -20,
        "dtw": None,
        "dtc": None,
        "checkmate": False,
        "stalemate": False,
        "moves": [
            {"uci": "h1h7", "san": "Rh7", "category": "loss", "dtz": -20, "dtm": -20},
        ],
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = api_data
    mock_get.return_value = mock_resp

    result = probe_position_full("4k3/8/8/8/8/8/8/4K2R w K - 0 1")
    assert result is not None
    assert result["category"] == "win"
    assert result["tier"] == "WIN"
    assert len(result["moves"]) == 1
    assert result["moves"][0]["san"] == "Rh7"


@patch("chess_self_coach.tablebase.requests.get")
def test_probe_position_full_too_many_pieces(mock_get: MagicMock):
    """Returns None for positions with more than 7 pieces."""
    result = probe_position_full("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
    assert result is None
    mock_get.assert_not_called()
