"""Shared test fixtures for chess-opening-prep."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the tests/fixtures/ directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project structure with config.json, .env, and pgn/.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        Path to the temporary project root.
    """
    # config.json
    config = {
        "stockfish": {
            "path": "/usr/games/stockfish",
            "expected_version": "Stockfish 18",
            "fallback_path": "/usr/games/stockfish",
        },
        "analysis": {"default_depth": 18, "blunder_threshold": 1.0},
        "studies": {
            "repertoire_blancs_gambit_dame_annote.pgn": {
                "study_id": "abc123",
                "study_name": "Whites - Queen's Gambit",
            },
        },
    }
    (tmp_path / "config.json").write_text(json.dumps(config, indent=2))

    # .env
    (tmp_path / ".env").write_text("LICHESS_API_TOKEN=lip_test_token_12345\n")

    # pgn directory
    (tmp_path / "pgn").mkdir()

    return tmp_path
