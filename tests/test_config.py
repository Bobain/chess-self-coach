"""Tests for config.py functions."""

from __future__ import annotations

import pytest

from chess_self_coach.config import (
    load_config,
    load_lichess_token,
)


def test_load_config_valid(tmp_project, monkeypatch):
    """Valid config.json is loaded correctly."""
    monkeypatch.setattr("chess_self_coach.config._find_project_root", lambda: tmp_project)
    config = load_config()
    assert "stockfish" in config


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
