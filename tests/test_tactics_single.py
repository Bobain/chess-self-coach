"""Tests for analyze_game_tactics() — per-game tactical analysis."""

from __future__ import annotations

import json
from pathlib import Path

from chess_self_coach.tactics import analyze_game_tactics


def _make_game_data() -> dict:
    """Minimal game data with two moves that have valid FENs."""
    return {
        "moves": [
            {
                "fen_before": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "move_uci": "e2e4",
                "eval_before": {"pv_uci": ["e2e4", "e7e5"], "best_move_uci": "e2e4"},
            },
            {
                "fen_before": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                "move_uci": "e7e5",
                "eval_before": {"pv_uci": ["e7e5", "g1f3"], "best_move_uci": "e7e5"},
            },
        ]
    }


def test_analyze_game_tactics_returns_motifs(tmp_path: Path):
    """Returns a list of motif dicts, one per move."""
    output = tmp_path / "tactics_data.json"
    game_data = _make_game_data()

    motifs = analyze_game_tactics("g1", game_data, output_path=output)

    assert len(motifs) == 2
    assert isinstance(motifs[0], dict)
    assert isinstance(motifs[1], dict)


def test_analyze_game_tactics_writes_file(tmp_path: Path):
    """Writes tactics_data.json with the game's motifs."""
    output = tmp_path / "tactics_data.json"
    game_data = _make_game_data()

    analyze_game_tactics("g1", game_data, output_path=output)

    assert output.exists()
    data = json.loads(output.read_text())
    assert "g1" in data["games"]
    assert len(data["games"]["g1"]) == 2


def test_analyze_game_tactics_incremental(tmp_path: Path):
    """Updating one game preserves other games in the file."""
    output = tmp_path / "tactics_data.json"

    # Pre-existing data for another game
    existing = {"version": "1.0", "games": {"old_game": [{"isFork": True}]}}
    output.write_text(json.dumps(existing))

    game_data = _make_game_data()
    analyze_game_tactics("new_game", game_data, output_path=output)

    data = json.loads(output.read_text())
    assert "old_game" in data["games"]  # Preserved
    assert "new_game" in data["games"]  # Added
    assert data["games"]["old_game"] == [{"isFork": True}]


def test_analyze_game_tactics_overwrites_same_game(tmp_path: Path):
    """Re-analyzing the same game replaces its tactics data."""
    output = tmp_path / "tactics_data.json"

    existing = {"version": "1.0", "games": {"g1": [{"old": True}]}}
    output.write_text(json.dumps(existing))

    game_data = _make_game_data()
    motifs = analyze_game_tactics("g1", game_data, output_path=output)

    data = json.loads(output.read_text())
    assert data["games"]["g1"] == motifs  # Replaced, not appended
    assert "old" not in str(data["games"]["g1"])
