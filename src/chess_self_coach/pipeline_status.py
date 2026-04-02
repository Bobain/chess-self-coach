"""Pipeline status tracking for per-game analysis consistency.

Tracks which downstream phases (tactics, classification, training) have been
completed for each analyzed game.  Allows crash recovery: on restart, any
game with incomplete phases is repaired before new analysis begins.

Status file: ``data/pipeline_status.json``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chess_self_coach.config import data_dir
from chess_self_coach.io import atomic_write_json

PIPELINE_STATUS_FILE = "pipeline_status.json"


def pipeline_status_path() -> Path:
    """Return the path to pipeline_status.json."""
    return data_dir() / PIPELINE_STATUS_FILE


def load_pipeline_status(path: Path | None = None) -> dict[str, Any]:
    """Load pipeline status from disk.

    Returns:
        Dict with ``{"games": {game_id: {analyzed_at, tactics, classification, training}}}``.
    """
    if path is None:
        path = pipeline_status_path()
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {"games": {}}


def save_pipeline_status(status: dict[str, Any], path: Path | None = None) -> None:
    """Atomically save pipeline status to disk."""
    if path is None:
        path = pipeline_status_path()
    atomic_write_json(path, status)


def mark_analyzed(status: dict[str, Any], game_id: str, analyzed_at: str) -> None:
    """Mark a game as freshly analyzed, invalidating all downstream phases.

    Called after ``collect_game_data()`` saves new analysis data.  Resets
    tactics/classification/training flags to False since the analysis has
    changed and derivatives are now stale.
    """
    status.setdefault("games", {})[game_id] = {
        "analyzed_at": analyzed_at,
        "tactics": False,
        "classification": False,
        "training": False,
    }


def mark_phase_done(status: dict[str, Any], game_id: str, phase: str) -> None:
    """Mark a downstream phase as completed for a game.

    Args:
        status: The pipeline status dict (mutated in place).
        game_id: Game identifier.
        phase: One of ``"tactics"``, ``"classification"``, ``"training"``.
    """
    game_status = status.get("games", {}).get(game_id)
    if game_status is not None:
        game_status[phase] = True


def get_incomplete_games(status: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return games that have incomplete downstream phases.

    Returns:
        List of ``(game_id, game_status_dict)`` for games where at least
        one of tactics/classification/training is False.
    """
    result = []
    for game_id, game_status in status.get("games", {}).items():
        if not (
            game_status.get("tactics")
            and game_status.get("classification")
            and game_status.get("training")
        ):
            result.append((game_id, game_status))
    return result
