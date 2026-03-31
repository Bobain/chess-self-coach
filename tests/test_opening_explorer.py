"""Tests for opening_explorer.py — API client and theory departure detection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from chess_self_coach.opening_explorer import (
    ExplorerAPIError,
    query_opening,
    query_opening_sequence,
)


def _mock_response(data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    return resp


# --- query_opening ---


@patch("chess_self_coach.opening_explorer.requests.get")
def test_query_opening_returns_data(mock_get: MagicMock):
    """Successful query returns the full response."""
    api_data = {
        "opening": {"eco": "B00", "name": "King's Pawn Game"},
        "white": 100, "draws": 50, "black": 80,
        "moves": [
            {"san": "e5", "uci": "e7e5", "white": 40, "draws": 20, "black": 30},
        ],
    }
    mock_get.return_value = _mock_response(api_data)

    result = query_opening("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1", "token")
    assert result is not None
    assert result["opening"]["eco"] == "B00"
    assert len(result["moves"]) == 1


@patch("chess_self_coach.opening_explorer.requests.get")
def test_query_opening_zero_games_returns_none(mock_get: MagicMock):
    """Position with zero games is treated as not in database."""
    api_data = {"opening": None, "white": 0, "draws": 0, "black": 0, "moves": []}
    mock_get.return_value = _mock_response(api_data)

    result = query_opening("some/fen", "token")
    assert result is None


@patch("chess_self_coach.opening_explorer.requests.get")
def test_query_opening_api_error_raises(mock_get: MagicMock):
    """API error raises ExplorerAPIError (never silently returns None)."""
    mock_get.return_value = _mock_response({}, status_code=500)

    with pytest.raises(ExplorerAPIError, match="API unavailable"):
        query_opening("some/fen", "token")


@patch("chess_self_coach.opening_explorer.requests.get")
def test_query_opening_network_error_raises(mock_get: MagicMock):
    """Network error raises ExplorerAPIError (never silently returns None)."""
    import requests

    mock_get.side_effect = requests.ConnectionError("timeout")

    with pytest.raises(ExplorerAPIError, match="API unavailable"):
        query_opening("some/fen", "token")


# --- query_opening_sequence ---


@patch("chess_self_coach.opening_explorer.query_opening")
@patch("chess_self_coach.opening_explorer.time.sleep")
def test_sequence_stops_at_departure(mock_sleep: MagicMock, mock_query: MagicMock):
    """Stops querying after both Masters and Lichess depart."""
    # Position 1: e4 is in Masters, move e5 is known
    masters_resp1 = {
        "opening": {"eco": "B00", "name": "King's Pawn"},
        "white": 100, "draws": 50, "black": 80,
        "moves": [{"uci": "e7e5", "san": "e5"}],
    }
    # Position 2: after e5, Masters has d4 but NOT Nf6 → masters departure
    masters_resp2 = {
        "opening": {"eco": "C20", "name": "King's Pawn Game"},
        "white": 50, "draws": 20, "black": 30,
        "moves": [{"uci": "d2d4", "san": "d4"}],
    }
    # Position 2 Lichess fallback: also doesn't have Nf6 → lichess departure
    lichess_resp2 = {
        "opening": {"eco": "C20", "name": "King's Pawn Game"},
        "white": 5000, "draws": 2000, "black": 3000,
        "moves": [{"uci": "d2d4", "san": "d4"}],
    }

    # Masters called for pos1, Masters called for pos2, Lichess called for pos2
    mock_query.side_effect = [masters_resp1, masters_resp2, lichess_resp2]

    fens_and_moves = [
        ("startpos_fen", "e7e5"),
        ("after_e5_fen", "g8f6"),  # Nf6 not in either database → both depart
        ("after_nf6_fen", "d2d4"),  # Should not be queried
    ]

    results = query_opening_sequence(fens_and_moves, "token")
    assert len(results) == 3
    assert results[0] is not None
    assert results[0]["_source"] == "masters"
    assert results[1] is None  # Both departed, move not found
    assert results[2] is None  # Past departure: not queried
    assert mock_query.call_count == 3  # Masters x2 + Lichess x1


@patch("chess_self_coach.opening_explorer.query_opening")
@patch("chess_self_coach.opening_explorer.time.sleep")
def test_sequence_lichess_fallback(mock_sleep: MagicMock, mock_query: MagicMock):
    """Lichess provides data when Masters departs but move is in Lichess."""
    masters_resp = {
        "opening": {"eco": "B00"}, "white": 100, "draws": 50, "black": 80,
        "moves": [{"uci": "e7e5", "san": "e5"}],
    }
    # Masters doesn't know d7d5 but Lichess does
    lichess_resp = {
        "opening": {"eco": "C20"}, "white": 5000, "draws": 2000, "black": 3000,
        "moves": [{"uci": "d7d5", "san": "d5"}],
    }

    mock_query.side_effect = [masters_resp, None, lichess_resp]

    fens_and_moves = [
        ("fen1", "e7e5"),  # Masters match
        ("fen2", "d7d5"),  # Masters=None → departed, Lichess has d5
    ]

    results = query_opening_sequence(fens_and_moves, "token")
    assert results[0]["_source"] == "masters"
    assert results[1]["_source"] == "lichess"


@patch("chess_self_coach.opening_explorer.query_opening")
@patch("chess_self_coach.opening_explorer.time.sleep")
def test_sequence_stops_when_api_returns_none(mock_sleep: MagicMock, mock_query: MagicMock):
    """Stops querying when both endpoints return None (position not in any database)."""
    mock_query.side_effect = [
        # Pos1 Masters: has e7e5
        {"opening": None, "white": 100, "draws": 50, "black": 80, "moves": [{"uci": "e7e5"}]},
        # Pos2 Masters: None (not in database)
        None,
        # Pos2 Lichess: also None
        None,
    ]

    fens_and_moves = [
        ("fen1", "e7e5"),
        ("fen2", "d7d5"),
        ("fen3", "g1f3"),
    ]

    results = query_opening_sequence(fens_and_moves, "token")
    assert results[0] is not None
    assert results[1] is None
    assert results[2] is None
    assert mock_query.call_count == 3  # Masters x2 + Lichess x1
