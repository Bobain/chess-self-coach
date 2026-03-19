"""Tests for the FastAPI backend server."""

from __future__ import annotations

import chess
from fastapi.testclient import TestClient

from chess_self_coach.server import app


client = TestClient(app)


# --- /api/status ---


def test_status_endpoint():
    """/api/status returns mode, version, and stockfish_version."""
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "app"
    assert "version" in data
    assert "stockfish_version" in data


# --- /api/stockfish/bestmove ---


def test_bestmove_valid_fen():
    """Valid FEN returns a legal UCI move."""
    resp = client.post(
        "/api/stockfish/bestmove",
        json={"fen": chess.STARTING_FEN, "depth": 5},
    )
    # May be 200 (Stockfish available) or 503 (not installed)
    if resp.status_code == 200:
        data = resp.json()
        assert "bestmove" in data
        move_str = data["bestmove"]
        # Verify it's a legal move
        board = chess.Board()
        move = chess.Move.from_uci(move_str)
        assert move in board.legal_moves, f"{move_str} is not legal"
    else:
        assert resp.status_code == 503


def test_bestmove_invalid_fen():
    """Invalid FEN returns 400."""
    resp = client.post(
        "/api/stockfish/bestmove",
        json={"fen": "not a valid fen", "depth": 5},
    )
    # 400 (invalid FEN) or 503 (no Stockfish)
    assert resp.status_code in (400, 503)


def test_bestmove_missing_fields():
    """Missing fen field returns 422 (Pydantic validation)."""
    resp = client.post("/api/stockfish/bestmove", json={"depth": 5})
    assert resp.status_code == 422


def test_bestmove_depth_too_high():
    """Depth exceeding max (30) returns 422."""
    resp = client.post(
        "/api/stockfish/bestmove",
        json={"fen": chess.STARTING_FEN, "depth": 50},
    )
    assert resp.status_code == 422


def test_bestmove_depth_zero():
    """Depth below min (1) returns 422."""
    resp = client.post(
        "/api/stockfish/bestmove",
        json={"fen": chess.STARTING_FEN, "depth": 0},
    )
    assert resp.status_code == 422


# --- Static files ---


def test_static_index_served():
    """GET / returns the PWA HTML."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Chess Self-Coach" in resp.text


def test_sw_version_injected():
    """GET /sw.js returns content with __VERSION__ replaced."""
    resp = client.get("/sw.js")
    assert resp.status_code == 200
    assert "__VERSION__" not in resp.text
    assert "chess-self-coach-" in resp.text


def test_api_not_cached_by_sw():
    """sw.js excludes /api/ paths from caching."""
    resp = client.get("/sw.js")
    assert resp.status_code == 200
    assert "/api/" in resp.text
