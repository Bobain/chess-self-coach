"""Tests for config.py functions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chess_self_coach.config import (
    get_study_mapping,
    load_config,
    load_lichess_token,
)


def test_load_config_valid(tmp_project, monkeypatch):
    """Valid config.json is loaded correctly."""
    monkeypatch.setattr("chess_self_coach.config._find_project_root", lambda: tmp_project)
    config = load_config()
    assert "stockfish" in config
    assert "studies" in config


def test_load_config_missing(tmp_path, monkeypatch):
    """Missing config.json triggers SystemExit."""
    monkeypatch.setattr("chess_self_coach.config._find_project_root", lambda: tmp_path)
    with pytest.raises(SystemExit):
        load_config()


def test_load_config_invalid_json(tmp_project, monkeypatch):
    """Invalid JSON in config.json triggers SystemExit."""
    monkeypatch.setattr("chess_self_coach.config._find_project_root", lambda: tmp_project)
    (tmp_project / "config.json").write_text("{invalid json!!!")
    with pytest.raises(SystemExit):
        load_config()


def test_load_lichess_token_valid(tmp_project, monkeypatch):
    """Valid .env with lip_ token is loaded correctly."""
    monkeypatch.setattr("chess_self_coach.config._find_project_root", lambda: tmp_project)
    # Clear any existing env var to avoid interference
    monkeypatch.delenv("LICHESS_API_TOKEN", raising=False)
    token = load_lichess_token()
    assert token.startswith("lip_")


def test_load_lichess_token_missing(tmp_path, monkeypatch):
    """Missing .env with no env var triggers SystemExit."""
    monkeypatch.setattr("chess_self_coach.config._find_project_root", lambda: tmp_path)
    monkeypatch.delenv("LICHESS_API_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        load_lichess_token()


def test_load_lichess_token_bad_prefix(tmp_project, monkeypatch):
    """Token without lip_ prefix triggers SystemExit."""
    monkeypatch.setattr("chess_self_coach.config._find_project_root", lambda: tmp_project)
    monkeypatch.delenv("LICHESS_API_TOKEN", raising=False)
    (tmp_project / ".env").write_text("LICHESS_API_TOKEN=bad_prefix_token\n")
    with pytest.raises(SystemExit):
        load_lichess_token()


def test_get_study_mapping_found(tmp_project, monkeypatch):
    """Configured study mapping is returned correctly."""
    monkeypatch.setattr("chess_self_coach.config._find_project_root", lambda: tmp_project)
    config = load_config()
    mapping = get_study_mapping(config, "repertoire_blancs_gambit_dame_annote.pgn")
    assert mapping["study_id"] == "abc123"
    assert mapping["study_name"] == "Whites - Queen's Gambit"


def test_get_study_mapping_not_configured(tmp_project, monkeypatch):
    """Study with STUDY_ID_HERE triggers SystemExit."""
    monkeypatch.setattr("chess_self_coach.config._find_project_root", lambda: tmp_project)
    config = load_config()
    config["studies"]["test.pgn"] = {
        "study_id": "STUDY_ID_HERE",
        "study_name": "Test",
    }
    with pytest.raises(SystemExit):
        get_study_mapping(config, "test.pgn")
