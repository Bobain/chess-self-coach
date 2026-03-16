"""Tests for validate.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from chess_self_coach.validate import validate_pgn


def test_validate_well_annotated(fixtures_dir):
    """well_annotated.pgn should have no errors."""
    results = validate_pgn(fixtures_dir / "well_annotated.pgn")
    assert len(results) > 0
    for chapter in results:
        assert len(chapter["errors"]) == 0


def test_validate_badly_annotated(fixtures_dir):
    """badly_annotated.pgn should have errors (empty chapter — no comments)."""
    results = validate_pgn(fixtures_dir / "badly_annotated.pgn")
    assert len(results) > 0
    has_error = any(chapter["errors"] for chapter in results)
    assert has_error


def test_validate_partial(fixtures_dir):
    """mini.pgn should have warnings for missing annotations."""
    results = validate_pgn(fixtures_dir / "mini.pgn")
    assert len(results) > 0
    # mini.pgn has no comments, so it should be flagged as empty_chapter (error)
    # or have warnings if it has bare moves
    has_issues = any(chapter["errors"] or chapter["warnings"] for chapter in results)
    assert has_issues


def test_validate_nonexistent_file():
    """Validating a nonexistent file should exit with error."""
    with pytest.raises(SystemExit):
        validate_pgn("/nonexistent/path/to/file.pgn")
