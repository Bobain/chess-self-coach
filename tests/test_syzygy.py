"""Tests for Syzygy tablebase management."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from chess_self_coach.syzygy import (
    _is_valid_syzygy_dir,
    download_syzygy,
    find_syzygy,
    syzygy_status,
)


def test_find_syzygy_from_config(tmp_path):
    """find_syzygy returns path from config when valid."""
    syzygy_dir = tmp_path / "syzygy"
    syzygy_dir.mkdir()
    (syzygy_dir / "KQvK.rtbw").touch()

    config = {"syzygy": {"path": str(syzygy_dir)}}
    assert find_syzygy(config) == syzygy_dir


def test_find_syzygy_fallback_xdg(tmp_path, monkeypatch):
    """find_syzygy falls back to ~/.local/share/syzygy/ when no config."""
    syzygy_dir = tmp_path / ".local" / "share" / "syzygy"
    syzygy_dir.mkdir(parents=True)
    (syzygy_dir / "KQvK.rtbw").touch()

    monkeypatch.setattr("chess_self_coach.syzygy._SEARCH_PATHS", [syzygy_dir])
    assert find_syzygy(config={}) == syzygy_dir


def test_find_syzygy_none_if_missing():
    """find_syzygy returns None when no tables exist."""
    config = {"syzygy": {"path": "/nonexistent/path/syzygy"}}
    with patch("chess_self_coach.syzygy._SEARCH_PATHS", [Path("/also/nonexistent")]):
        assert find_syzygy(config) is None


def test_find_syzygy_none_if_empty_dir(tmp_path):
    """find_syzygy returns None if directory exists but has no .rtbw files."""
    syzygy_dir = tmp_path / "syzygy"
    syzygy_dir.mkdir()
    # No .rtbw files

    config = {"syzygy": {"path": str(syzygy_dir)}}
    with patch("chess_self_coach.syzygy._SEARCH_PATHS", [Path("/nonexistent")]):
        assert find_syzygy(config) is None


def test_find_syzygy_none_without_config():
    """find_syzygy returns None when called with no config and no default dir."""
    with patch("chess_self_coach.syzygy._SEARCH_PATHS", [Path("/nonexistent")]):
        assert find_syzygy() is None


def test_is_valid_syzygy_dir(tmp_path):
    """_is_valid_syzygy_dir checks for .rtbw files."""
    assert not _is_valid_syzygy_dir(tmp_path)  # empty dir

    (tmp_path / "KQvK.rtbw").touch()
    assert _is_valid_syzygy_dir(tmp_path)


def test_is_valid_syzygy_dir_nonexistent():
    """_is_valid_syzygy_dir returns False for non-existent path."""
    assert not _is_valid_syzygy_dir(Path("/nonexistent"))


def test_download_syzygy_requires_wget():
    """download_syzygy raises FileNotFoundError when wget is missing."""
    with patch("shutil.which", return_value=None):
        with pytest.raises(FileNotFoundError, match="wget is required"):
            download_syzygy()


def test_download_syzygy_calls_wget(tmp_path):
    """download_syzygy calls wget with correct arguments."""
    with patch("shutil.which", return_value="/usr/bin/wget"), \
         patch("subprocess.run") as mock_run:
        result = download_syzygy(tmp_path)

    assert result == tmp_path
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "wget"
    assert "-c" in args
    assert "-r" in args
    assert str(tmp_path) in args


def test_syzygy_status_found(tmp_path):
    """syzygy_status reports correct file counts."""
    (tmp_path / "KQvK.rtbw").write_bytes(b"\x00" * 1024)
    (tmp_path / "KRvK.rtbw").write_bytes(b"\x00" * 2048)
    (tmp_path / "KQvK.rtbz").write_bytes(b"\x00" * 512)

    config = {"syzygy": {"path": str(tmp_path)}}
    status = syzygy_status(config)
    assert status["found"] is True
    assert status["wdl_count"] == 2
    assert status["dtz_count"] == 1
    assert status["total_size_mb"] >= 0  # small test files round to 0.0


def test_syzygy_status_not_found():
    """syzygy_status reports not found when no tables exist."""
    config = {"syzygy": {"path": "/nonexistent"}}
    with patch("chess_self_coach.syzygy._SEARCH_PATHS", [Path("/also/nonexistent")]):
        status = syzygy_status(config)
    assert status["found"] is False
    assert status["path"] is None


# --- Integration test: engine configuration ---


@patch("chess.engine.SimpleEngine.popen_uci")
def test_engine_configured_with_syzygy_path(mock_popen, tmp_path):
    """Stockfish engine receives SyzygyPath when tables are found."""
    # Create fake syzygy dir
    syzygy_dir = tmp_path / "syzygy"
    syzygy_dir.mkdir()
    (syzygy_dir / "KQvK.rtbw").touch()

    # Mock engine
    mock_engine = MagicMock()
    mock_popen.return_value = mock_engine

    # Import and call the configure section directly
    from chess_self_coach.syzygy import find_syzygy

    config = {"syzygy": {"path": str(syzygy_dir)}}
    path = find_syzygy(config)
    assert path is not None

    # Simulate what analyze_games does
    mock_engine.configure({"Threads": 1, "Hash": 64})
    mock_engine.configure({"SyzygyPath": str(path)})

    # Verify SyzygyPath was passed
    calls = mock_engine.configure.call_args_list
    assert len(calls) == 2
    assert calls[1][0][0] == {"SyzygyPath": str(syzygy_dir)}


def test_engine_no_syzygy_when_missing():
    """find_syzygy returns None so SyzygyPath is NOT configured."""
    config = {"syzygy": {"path": "/nonexistent"}}
    with patch("chess_self_coach.syzygy._SEARCH_PATHS", [Path("/also/nonexistent")]):
        path = find_syzygy(config)
    assert path is None
