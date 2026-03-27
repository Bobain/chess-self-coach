"""Tests for opening_explorer.py — API client and theory departure detection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from chess_self_coach.opening_explorer import query_opening, query_opening_sequence


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
def test_query_opening_api_error_returns_none(mock_get: MagicMock):
    """API error returns None."""
    mock_get.return_value = _mock_response({}, status_code=500)

    result = query_opening("some/fen", "token")
    assert result is None


@patch("chess_self_coach.opening_explorer.requests.get")
def test_query_opening_network_error_returns_none(mock_get: MagicMock):
    """Network error returns None."""
    import requests

    mock_get.side_effect = requests.ConnectionError("timeout")
    result = query_opening("some/fen", "token")
    assert result is None


# --- query_opening_sequence ---


@patch("chess_self_coach.opening_explorer.query_opening")
@patch("chess_self_coach.opening_explorer.time.sleep")
def test_sequence_stops_at_departure(mock_sleep: MagicMock, mock_query: MagicMock):
    """Stops querying after the move played is not in the explorer's move list."""
    # Position 1: e4 is in the database, move e5 is known
    resp1 = {
        "opening": {"eco": "B00", "name": "King's Pawn"},
        "white": 100, "draws": 50, "black": 80,
        "moves": [{"uci": "e7e5", "san": "e5"}],
    }
    # Position 2: after e5, d4 is in the database, move Nf6 is NOT known
    resp2 = {
        "opening": {"eco": "C20", "name": "King's Pawn Game"},
        "white": 50, "draws": 20, "black": 30,
        "moves": [{"uci": "d2d4", "san": "d4"}],
    }

    mock_query.side_effect = [resp1, resp2]

    fens_and_moves = [
        ("startpos_fen", "e7e5"),
        ("after_e5_fen", "g8f6"),  # Nf6 not in resp2's moves → departure
        ("after_nf6_fen", "d2d4"),  # Should not be queried
    ]

    results = query_opening_sequence(fens_and_moves, "token")
    assert len(results) == 3
    assert results[0] is not None  # e4 position: in book
    assert results[1] is not None  # after e5: in book (but move departs)
    assert results[2] is None  # past departure: not queried
    assert mock_query.call_count == 2  # Only 2 API calls, not 3


@patch("chess_self_coach.opening_explorer.query_opening")
@patch("chess_self_coach.opening_explorer.time.sleep")
def test_sequence_stops_when_api_returns_none(mock_sleep: MagicMock, mock_query: MagicMock):
    """Stops querying when API returns None (position not in database)."""
    mock_query.side_effect = [
        {"opening": None, "white": 100, "draws": 50, "black": 80, "moves": [{"uci": "e7e5"}]},
        None,  # Not in database → departure
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
    assert mock_query.call_count == 2
