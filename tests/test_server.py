"""Tests for the FastAPI backend server."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import chess
import chess.engine
from fastapi.testclient import TestClient

from chess_self_coach import server
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


# --- /training_data.json ---


def test_training_data_served():
    """GET /training_data.json returns 200 + valid JSON when file exists."""
    resp = client.get("/training_data.json")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, (dict, list))


def test_training_data_missing(tmp_path):
    """GET /training_data.json returns 404 when file is absent."""
    with patch.object(server, "_project_root", tmp_path):
        resp = client.get("/training_data.json")
    assert resp.status_code == 404


# --- /api/train/stats ---


def test_train_stats_returns_data(tmp_path):
    """GET /api/train/stats returns stats when training data exists."""
    data = {
        "generated": "2026-03-16T00:00:00Z",
        "positions": [
            {"category": "blunder", "game": {"source": "lichess"}},
            {"category": "mistake", "game": {"source": "chess.com"}},
            {"category": "blunder", "game": {"source": "lichess"}},
        ],
    }
    (tmp_path / "training_data.json").write_text(json.dumps(data))
    with patch.object(server, "_project_root", tmp_path):
        resp = client.get("/api/train/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["by_category"] == {"blunder": 2, "mistake": 1}
    assert body["by_source"] == {"lichess": 2, "chess.com": 1}
    assert body["generated"] == "2026-03-16T00:00:00Z"


def test_train_stats_missing_data(tmp_path):
    """GET /api/train/stats returns 404 when no training data."""
    with patch.object(server, "_project_root", tmp_path):
        resp = client.get("/api/train/stats")
    assert resp.status_code == 404


# --- /api/pgn/validate ---


_TEST_PGN = """\
[Event "Test Chapter"]
[Site "?"]
[Result "*"]

1. e4 {Italian Game (ECO C50). THEORY: main line.} e5 {Plan: develop pieces.} *
"""


def test_pgn_validate_returns_results(tmp_path):
    """POST /api/pgn/validate returns validation results for PGN files."""
    (tmp_path / "test.pgn").write_text(_TEST_PGN)
    with patch.object(server, "_project_root", tmp_path):
        resp = client.post("/api/pgn/validate")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["files"]) == 1
    assert body["files"][0]["file"] == "test.pgn"
    assert len(body["files"][0]["chapters"]) == 1
    assert body["files"][0]["chapters"][0]["name"] == "Test Chapter"


def test_pgn_validate_no_files(tmp_path):
    """POST /api/pgn/validate returns 404 when no PGN files exist."""
    with patch.object(server, "_project_root", tmp_path):
        resp = client.post("/api/pgn/validate")
    assert resp.status_code == 404


# --- Port scanner ---


def test_port_scanner_finds_available():
    """_find_available_port() returns an int in the expected range."""
    port = server._find_available_port()
    assert isinstance(port, int)
    assert 8000 <= port <= 8010


# --- Crash recovery ---


def test_bestmove_crash_recovery():
    """Engine restart after EngineTerminatedError returns 200."""
    # Mock result from the restarted engine
    mock_result = MagicMock()
    mock_result.move = chess.Move.from_uci("e2e4")

    # First call raises EngineTerminatedError, second succeeds
    crashed_engine = MagicMock()
    crashed_engine.play.side_effect = chess.engine.EngineTerminatedError()

    restarted_engine = MagicMock()
    restarted_engine.play.return_value = mock_result

    original_engine = server._engine
    original_sf_path = server._sf_path
    try:
        server._engine = crashed_engine
        server._sf_path = "/usr/bin/stockfish"  # just needs to be truthy

        with patch(
            "chess.engine.SimpleEngine.popen_uci",
            return_value=restarted_engine,
        ):
            resp = client.post(
                "/api/stockfish/bestmove",
                json={"fen": chess.STARTING_FEN, "depth": 5},
            )

        assert resp.status_code == 200
        assert resp.json()["bestmove"] == "e2e4"
    finally:
        server._engine = original_engine
        server._sf_path = original_sf_path
