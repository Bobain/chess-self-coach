"""Tests for lichess.py functions."""

from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest

from chess_opening_prep.lichess import _get_chapters, cleanup_study


def test_get_chapters_parses_response(mocker):
    """_get_chapters correctly parses PGN with ChapterName/ChapterURL headers."""
    pgn_response = (
        '[Event "Chapter One"]\n'
        '[ChapterName "Chapter One"]\n'
        '[ChapterURL "https://lichess.org/study/abc123/ch001"]\n'
        '1. e4 e5 *\n'
        '\n'
        '[Event "Chapter Two"]\n'
        '[ChapterName "Chapter Two"]\n'
        '[ChapterURL "https://lichess.org/study/abc123/ch002"]\n'
        '1. d4 d5 *\n'
        '\n'
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = pgn_response
    mocker.patch("chess_opening_prep.lichess.requests.get", return_value=mock_resp)

    chapters = _get_chapters("abc123", "fake_token")

    assert len(chapters) == 2
    assert chapters[0]["name"] == "Chapter One"
    assert chapters[0]["id"] == "ch001"
    assert chapters[0]["has_moves"] == "True"
    assert chapters[1]["name"] == "Chapter Two"
    assert chapters[1]["id"] == "ch002"


def test_cleanup_study_removes_empty(mocker):
    """cleanup_study removes empty 'Chapter 1' chapters."""
    mock_chapters = [
        {"name": "Chapter 1", "id": "ch001", "has_moves": "False"},
        {"name": "Real Chapter", "id": "ch002", "has_moves": "True"},
    ]
    mocker.patch("chess_opening_prep.lichess.load_lichess_token", return_value="lip_fake")
    mocker.patch("chess_opening_prep.lichess._get_chapters", return_value=mock_chapters)
    mocker.patch("chess_opening_prep.lichess._delete_chapter", return_value=True)

    deleted = cleanup_study("abc123", "Test Study")

    assert deleted == 1
    from chess_opening_prep.lichess import _delete_chapter
    _delete_chapter.assert_called_once_with("abc123", "ch001", "lip_fake")


def test_cleanup_study_keeps_real_chapters(mocker):
    """cleanup_study does not delete chapters with actual moves."""
    mock_chapters = [
        {"name": "QGD Harrwitz", "id": "ch001", "has_moves": "True"},
        {"name": "Scandinavian", "id": "ch002", "has_moves": "True"},
    ]
    mocker.patch("chess_opening_prep.lichess.load_lichess_token", return_value="lip_fake")
    mocker.patch("chess_opening_prep.lichess._get_chapters", return_value=mock_chapters)
    mocker.patch("chess_opening_prep.lichess._delete_chapter", return_value=True)

    deleted = cleanup_study("abc123", "Test Study")

    assert deleted == 0
    from chess_opening_prep.lichess import _delete_chapter
    _delete_chapter.assert_not_called()
