"""Tests for the self-update mechanism."""

from __future__ import annotations

import json
from unittest.mock import patch

from chess_self_coach.updater import check_update


def test_check_update_newer_available(monkeypatch):
    """check_update returns True when PyPI has a newer version."""
    fake_response = json.dumps({"info": {"version": "99.0.0"}}).encode()

    class FakeResp:
        def read(self):
            return fake_response

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    with patch("chess_self_coach.updater.urllib.request.urlopen", return_value=FakeResp()):
        available, latest = check_update()

    assert available is True
    assert latest == "99.0.0"


def test_check_update_already_latest(monkeypatch):
    """check_update returns False when versions match."""
    from chess_self_coach import __version__

    fake_response = json.dumps({"info": {"version": __version__}}).encode()

    class FakeResp:
        def read(self):
            return fake_response

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    with patch("chess_self_coach.updater.urllib.request.urlopen", return_value=FakeResp()):
        available, latest = check_update()

    assert available is False
    assert latest == __version__


def test_check_update_network_error():
    """check_update returns (False, None) on network failure — never crashes."""
    with patch(
        "chess_self_coach.updater.urllib.request.urlopen",
        side_effect=OSError("Network unreachable"),
    ):
        available, latest = check_update()

    assert available is False
    assert latest is None
