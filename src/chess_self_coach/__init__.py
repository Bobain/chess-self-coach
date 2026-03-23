"""Chess Opening Prep — CLI to manage a chess opening repertoire.

Automates Stockfish analysis of PGN files and synchronization
with Lichess Studies for spaced-repetition drilling via Chessdriller.
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
    return max(os.cpu_count() - 1, 1)
