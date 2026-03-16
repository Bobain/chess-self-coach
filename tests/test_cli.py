"""Tests for cli.py."""

from __future__ import annotations

import pytest

from chess_self_coach.cli import main


def test_cli_help():
    """--help exits with code 0."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def test_cli_version():
    """--version shows version and exits 0."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0


def test_cli_no_command(capsys):
    """No command prints help and exits 0."""
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "chess-self-coach" in captured.out


def test_cli_validate_present(capsys):
    """'validate' appears in help output."""
    with pytest.raises(SystemExit):
        main(["--help"])
    captured = capsys.readouterr()
    assert "validate" in captured.out


def test_cli_import_present(capsys):
    """'import' appears in help output."""
    with pytest.raises(SystemExit):
        main(["--help"])
    captured = capsys.readouterr()
    assert "import" in captured.out
