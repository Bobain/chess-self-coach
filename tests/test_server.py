"""Tests for the FastAPI backend server."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
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


# --- /api/analysis/start ---


def _reset_job():
    """Reset the global job state for test isolation."""
    server._current_job = None


def test_analysis_start_returns_202():
    """POST /api/analysis/start returns 202 + job_id."""
    _reset_job()

    def fake_analyze(**kwargs):
        on_progress = kwargs.get("on_progress")
        if on_progress:
            on_progress({"phase": "done", "message": "Done!", "percent": 100})

    with patch("chess_self_coach.analysis.analyze_games", fake_analyze):
        resp = client.post("/api/analysis/start", json={"max_games": 5})

    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert len(data["job_id"]) == 8

    # Wait for job to finish
    time.sleep(0.2)
    _reset_job()


def test_analysis_start_rejects_concurrent():
    """Second POST returns 409 while a job is running."""
    _reset_job()
    import asyncio

    # Set up a fake running job
    server._current_job = {
        "id": "fakejob1",
        "status": "running",
        "queue": asyncio.Queue(),
        "cancel": threading.Event(),
    }

    resp = client.post("/api/analysis/start", json={"max_games": 5})
    assert resp.status_code == 409

    _reset_job()


def test_job_events_stream():
    """GET /api/jobs/{id}/events returns SSE content-type."""
    _reset_job()
    import asyncio

    queue = asyncio.Queue()
    queue.put_nowait({"phase": "init", "message": "Starting"})
    queue.put_nowait(None)  # End sentinel

    server._current_job = {
        "id": "testjob1",
        "status": "running",
        "queue": queue,
        "cancel": threading.Event(),
    }

    resp = client.get("/api/jobs/testjob1/events")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "Starting" in resp.text

    _reset_job()


def test_job_events_not_found():
    """GET /api/jobs/{id}/events returns 404 for unknown job."""
    _reset_job()
    resp = client.get("/api/jobs/nonexistent/events")
    assert resp.status_code == 404


def test_job_cancel_sets_event():
    """POST /api/jobs/{id}/cancel sets the cancel event."""
    _reset_job()
    import asyncio

    cancel = threading.Event()
    server._current_job = {
        "id": "canceljob1",
        "status": "running",
        "queue": asyncio.Queue(),
        "cancel": cancel,
    }

    resp = client.post("/api/jobs/canceljob1/cancel")
    assert resp.status_code == 202
    assert cancel.is_set()

    _reset_job()


def test_job_cancel_not_found():
    """POST /api/jobs/{id}/cancel returns 404 for unknown job."""
    _reset_job()
    resp = client.post("/api/jobs/nonexistent/cancel")
    assert resp.status_code == 404


def test_job_cancel_not_running():
    """POST /api/jobs/{id}/cancel returns 409 if job is not running."""
    _reset_job()
    import asyncio

    server._current_job = {
        "id": "donejob1",
        "status": "done",
        "queue": asyncio.Queue(),
        "cancel": threading.Event(),
    }

    resp = client.post("/api/jobs/donejob1/cancel")
    assert resp.status_code == 409

    _reset_job()


# --- /api/coaching/topics ---


def test_coaching_topics_lists_files(tmp_path):
    """GET /api/coaching/topics returns topic summaries from coaching/topics/."""
    topics_dir = tmp_path / "coaching" / "topics"
    topics_dir.mkdir(parents=True)
    (topics_dir / "2026-03-15-test-topic.md").write_text(
        "---\ndate: 2026-03-15\ntopic: Test topic\nstatus: resolved\n---\n\nBody text."
    )

    original = server._project_root
    server._project_root = tmp_path
    try:
        resp = client.get("/api/coaching/topics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["topics"]) == 1
        assert data["topics"][0]["slug"] == "2026-03-15-test-topic"
        assert data["topics"][0]["topic"] == "Test topic"
        assert data["topics"][0]["status"] == "resolved"
    finally:
        server._project_root = original


def test_coaching_topics_empty():
    """GET /api/coaching/topics returns empty list when no coaching dir."""
    original = server._project_root
    server._project_root = Path("/nonexistent")
    try:
        resp = client.get("/api/coaching/topics")
        assert resp.status_code == 200
        assert resp.json()["topics"] == []
    finally:
        server._project_root = original


def test_coaching_topic_detail(tmp_path):
    """GET /api/coaching/topics/{slug} returns the topic content."""
    topics_dir = tmp_path / "coaching" / "topics"
    topics_dir.mkdir(parents=True)
    content = "---\ndate: 2026-03-15\ntopic: Test\nstatus: active\n---\n\n## Body"
    (topics_dir / "2026-03-15-test.md").write_text(content)

    original = server._project_root
    server._project_root = tmp_path
    try:
        resp = client.get("/api/coaching/topics/2026-03-15-test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "2026-03-15-test"
        assert "## Body" in data["content"]
    finally:
        server._project_root = original


def test_coaching_topic_not_found():
    """GET /api/coaching/topics/{slug} returns 404 for unknown slug."""
    resp = client.get("/api/coaching/topics/nonexistent")
    assert resp.status_code == 404


# --- /api/config ---


def test_get_config(tmp_path):
    """GET /api/config returns players and analysis sections."""
    config = {
        "stockfish": {"path": "/usr/bin/stockfish"},
        "players": {"lichess": "testuser", "chesscom": "testcom"},
        "analysis": {"default_depth": 18, "blunder_threshold": 1.0},
        "studies": {},
    }
    (tmp_path / "config.json").write_text(json.dumps(config))

    original = server._project_root
    server._project_root = tmp_path
    try:
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["players"]["lichess"] == "testuser"
        assert data["analysis"]["default_depth"] == 18
        # stockfish and studies should NOT be exposed
        assert "stockfish" not in data
        assert "studies" not in data
    finally:
        server._project_root = original


def test_get_config_no_file():
    """GET /api/config returns 404 when config.json is missing."""
    original = server._project_root
    server._project_root = Path("/nonexistent")
    try:
        resp = client.get("/api/config")
        assert resp.status_code == 404
    finally:
        server._project_root = original


def test_update_config(tmp_path):
    """POST /api/config updates players and analysis, preserves other fields."""
    config = {
        "stockfish": {"path": "/usr/bin/stockfish"},
        "players": {"lichess": "old", "chesscom": "old"},
        "analysis": {"default_depth": 18, "blunder_threshold": 1.0},
        "studies": {"test.pgn": {"study_id": "abc"}},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    original = server._project_root
    server._project_root = tmp_path
    try:
        resp = client.post("/api/config", json={
            "players": {"lichess": "newuser", "chesscom": "newcom"},
            "analysis": {"default_depth": 12, "blunder_threshold": 0.5},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["players"]["lichess"] == "newuser"
        assert data["analysis"]["default_depth"] == 12

        # Verify file was written and other fields preserved
        saved = json.loads(config_path.read_text())
        assert saved["stockfish"]["path"] == "/usr/bin/stockfish"
        assert saved["studies"]["test.pgn"]["study_id"] == "abc"
        assert saved["players"]["lichess"] == "newuser"
    finally:
        server._project_root = original


def test_update_config_partial(tmp_path):
    """POST /api/config with only players keeps analysis unchanged."""
    config = {
        "players": {"lichess": "old", "chesscom": "old"},
        "analysis": {"default_depth": 18, "blunder_threshold": 1.0},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    original = server._project_root
    server._project_root = tmp_path
    try:
        resp = client.post("/api/config", json={
            "players": {"lichess": "newuser", "chesscom": "old"},
        })
        assert resp.status_code == 200

        saved = json.loads(config_path.read_text())
        assert saved["players"]["lichess"] == "newuser"
        assert saved["analysis"]["default_depth"] == 18  # unchanged
    finally:
        server._project_root = original
