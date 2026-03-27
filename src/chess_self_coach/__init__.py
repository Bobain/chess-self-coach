"""Chess Self-Coach — learn from your chess mistakes.

Fetches your games, analyzes them with Stockfish, and trains you
on the correct moves with spaced repetition.
"""

from __future__ import annotations

import os

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("chess-self-coach")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"


def worker_count() -> int:
    """Return the number of parallel workers: cpu_count - 1, minimum 1."""
    return max((os.cpu_count() or 1) - 1, 1)
