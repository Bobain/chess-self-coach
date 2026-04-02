"""Tests for pipeline_status — per-game phase tracking and crash recovery."""

from __future__ import annotations

import json
from pathlib import Path

from chess_self_coach.pipeline_status import (
    get_incomplete_games,
    load_pipeline_status,
    mark_analyzed,
    mark_phase_done,
    save_pipeline_status,
)


def test_load_missing_file(tmp_path: Path):
    """Loading from a non-existent path returns empty structure."""
    status = load_pipeline_status(tmp_path / "missing.json")
    assert status == {"games": {}}


def test_round_trip(tmp_path: Path):
    """Save then load preserves data."""
    path = tmp_path / "status.json"
    status = {"games": {"g1": {"analyzed_at": "t1", "tactics": True, "classification": True, "training": True}}}
    save_pipeline_status(status, path)
    loaded = load_pipeline_status(path)
    assert loaded == status


def test_mark_analyzed_resets_flags():
    """mark_analyzed sets analyzed_at and resets all downstream flags."""
    status: dict = {"games": {}}
    mark_analyzed(status, "g1", "2026-04-02T12:00:00Z")

    g1 = status["games"]["g1"]
    assert g1["analyzed_at"] == "2026-04-02T12:00:00Z"
    assert g1["tactics"] is False
    assert g1["classification"] is False
    assert g1["training"] is False


def test_mark_analyzed_overwrites_existing():
    """Re-analyzing a complete game resets all flags."""
    status = {"games": {"g1": {
        "analyzed_at": "old", "tactics": True, "classification": True, "training": True,
    }}}
    mark_analyzed(status, "g1", "new")

    g1 = status["games"]["g1"]
    assert g1["analyzed_at"] == "new"
    assert g1["tactics"] is False
    assert g1["classification"] is False
    assert g1["training"] is False


def test_mark_phase_done():
    """mark_phase_done sets a single phase flag."""
    status: dict = {"games": {}}
    mark_analyzed(status, "g1", "t1")

    mark_phase_done(status, "g1", "tactics")
    assert status["games"]["g1"]["tactics"] is True
    assert status["games"]["g1"]["classification"] is False

    mark_phase_done(status, "g1", "classification")
    assert status["games"]["g1"]["classification"] is True


def test_mark_phase_done_missing_game():
    """mark_phase_done on unknown game is a no-op."""
    status: dict = {"games": {}}
    mark_phase_done(status, "unknown", "tactics")  # Should not raise
    assert "unknown" not in status["games"]


def test_get_incomplete_games():
    """get_incomplete_games returns only games with at least one False flag."""
    status = {"games": {
        "complete": {"analyzed_at": "t", "tactics": True, "classification": True, "training": True},
        "no_tactics": {"analyzed_at": "t", "tactics": False, "classification": True, "training": True},
        "no_training": {"analyzed_at": "t", "tactics": True, "classification": True, "training": False},
        "fresh": {"analyzed_at": "t", "tactics": False, "classification": False, "training": False},
    }}
    incomplete = get_incomplete_games(status)
    ids = {gid for gid, _ in incomplete}
    assert ids == {"no_tactics", "no_training", "fresh"}


def test_get_incomplete_empty():
    """get_incomplete_games on empty status returns empty list."""
    assert get_incomplete_games({"games": {}}) == []
