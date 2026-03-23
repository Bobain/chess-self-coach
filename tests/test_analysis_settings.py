"""Tests for analysis.py — AnalysisSettings, I/O, and settings matching."""

from __future__ import annotations

import json
from pathlib import Path

from chess_self_coach.analysis import (
    AnalysisSettings,
    load_analysis_data,
    save_analysis_data,
    settings_match,
)
from chess_self_coach.constants import ANALYSIS_LIMITS


# --- AnalysisSettings.from_config ---


def test_from_config_empty():
    """Empty config uses all defaults."""
    s = AnalysisSettings.from_config({})
    assert s.threads == 0  # auto
    assert s.hash_mb == 1024
    assert s.limits == ANALYSIS_LIMITS


def test_from_config_explicit():
    """Explicit values override defaults."""
    config = {
        "analysis_engine": {
            "threads": 4,
            "hash_mb": 2048,
            "limits": {"default": {"depth": 22}},
        }
    }
    s = AnalysisSettings.from_config(config)
    assert s.threads == 4
    assert s.hash_mb == 2048
    assert s.limits == {"default": {"depth": 22}}


def test_from_config_auto_threads():
    """'auto' string resolves to 0 (auto)."""
    config = {"analysis_engine": {"threads": "auto"}}
    s = AnalysisSettings.from_config(config)
    assert s.threads == 0


def test_resolved_threads():
    """resolved_threads returns actual count for auto, or explicit value."""
    s_auto = AnalysisSettings(threads=0)
    assert s_auto.resolved_threads >= 1

    s_explicit = AnalysisSettings(threads=4)
    assert s_explicit.resolved_threads == 4


# --- to_dict ---


def test_to_dict_round_trip():
    """to_dict produces a JSON-serializable dict with resolved threads."""
    s = AnalysisSettings(threads=4, hash_mb=512, limits={"default": {"depth": 10}})
    d = s.to_dict()
    assert d["threads"] == 4
    assert d["hash_mb"] == 512
    assert d["limits"] == {"default": {"depth": 10}}
    # Must be JSON-serializable
    json.dumps(d)


# --- settings_match ---


def test_settings_match_identical():
    """Identical settings match."""
    d1 = AnalysisSettings(threads=4, hash_mb=1024).to_dict()
    d2 = AnalysisSettings(threads=4, hash_mb=1024).to_dict()
    assert settings_match(d1, d2)


def test_settings_match_different_threads():
    """Different thread count → no match."""
    d1 = AnalysisSettings(threads=4, hash_mb=1024).to_dict()
    d2 = AnalysisSettings(threads=8, hash_mb=1024).to_dict()
    assert not settings_match(d1, d2)


def test_settings_match_different_hash():
    """Different hash → no match."""
    d1 = AnalysisSettings(threads=4, hash_mb=1024).to_dict()
    d2 = AnalysisSettings(threads=4, hash_mb=2048).to_dict()
    assert not settings_match(d1, d2)


def test_settings_match_different_limits():
    """Different limits → no match."""
    d1 = AnalysisSettings(threads=4, limits={"default": {"depth": 18}}).to_dict()
    d2 = AnalysisSettings(threads=4, limits={"default": {"depth": 22}}).to_dict()
    assert not settings_match(d1, d2)


# --- load_analysis_data / save_analysis_data ---


def test_load_analysis_data_missing(tmp_path: Path):
    """Missing file returns empty structure."""
    data = load_analysis_data(tmp_path / "missing.json")
    assert data["version"] == "1.0"
    assert data["games"] == {}


def test_load_analysis_data_invalid_json(tmp_path: Path):
    """Invalid JSON returns empty structure."""
    path = tmp_path / "bad.json"
    path.write_text("not json")
    data = load_analysis_data(path)
    assert data["version"] == "1.0"
    assert data["games"] == {}


def test_save_and_load_round_trip(tmp_path: Path):
    """save then load preserves data."""
    path = tmp_path / "analysis_data.json"
    data = {
        "version": "1.0",
        "player": {"lichess": "test"},
        "games": {"game1": {"moves": []}},
    }
    save_analysis_data(data, path)
    loaded = load_analysis_data(path)
    assert loaded["player"]["lichess"] == "test"
    assert "game1" in loaded["games"]
