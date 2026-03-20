"""E2E tests for interrupt/resume: game ID tracking and incremental analysis."""

from __future__ import annotations

import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import chess.pgn
import pytest

from chess_self_coach.trainer import TrainingInterrupted, prepare_training_data


# --- Helpers ---


def _make_pgn_game(game_id: str, white: str, black: str) -> chess.pgn.Game:
    """Create a minimal PGN game with Link header for tracking."""
    pgn = (
        f'[Event "Test"]\n'
        f'[Site "{game_id}"]\n'
        f'[Link "{game_id}"]\n'
        f'[White "{white}"]\n'
        f'[Black "{black}"]\n'
        f'[Result "1-0"]\n'
        f"\n"
        f"1. e4 e5 2. Nf3 Nc6 1-0"
    )
    return chess.pgn.read_game(io.StringIO(pgn))


def _extract_game_id(pgn_str: str) -> str:
    """Extract game ID from PGN string, matching real worker behavior."""
    game = chess.pgn.read_game(io.StringIO(pgn_str))
    if game is None:
        return ""
    return game.headers.get("Link", game.headers.get("Site", ""))


def _fake_worker_with_mistakes(
    pgn_str, sf_path_str, depth, player_color, idx, total, label,
):
    """Mock worker returning one fake mistake position."""
    game_id = _extract_game_id(pgn_str)
    position_id = f"pos_{label.replace(' ', '_')}"
    mistakes = [
        {
            "id": position_id,
            "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
            "player_color": "white",
            "player_move": "a3",
            "best_move": "d4",
            "cp_loss": 150,
            "category": "mistake",
            "context": "test",
            "explanation": "test",
            "acceptable_moves": ["d4"],
            "pv": ["d4"],
            "score_before": "+0.50",
            "score_after": "-1.00",
            "score_after_best": "+0.50",
            "game": {
                "id": game_id,
                "source": "lichess",
                "opponent": "opp",
                "date": "2026-01-01",
                "result": "1-0",
                "opening": "Test",
            },
        }
    ]
    return idx, total, label, mistakes, 0.01


def _fake_worker_no_mistakes(
    pgn_str, sf_path_str, depth, player_color, idx, total, label,
):
    """Mock worker returning zero mistakes."""
    return idx, total, label, [], 0.01


@pytest.fixture()
def project_dir(tmp_path):
    """Create a minimal project dir with config.json."""
    config = {
        "players": {"lichess": "testplayer", "chesscom": ""},
        "stockfish": {"path": "/fake/stockfish"},
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    return tmp_path


def _common_patches(project_dir, fetch_games, worker_fn):
    """Return a dict of patches shared by all resume tests.

    Keys are attribute names on chess_self_coach.trainer (for patch.multiple).
    """
    return {
        "ProcessPoolExecutor": ThreadPoolExecutor,
        "_analyze_game_worker": worker_fn,
        "load_config": lambda: json.loads(
            (project_dir / "config.json").read_text()
        ),
        "find_stockfish": lambda _: Path("/fake/stockfish"),
        "check_stockfish_version": lambda *a: "Stockfish 18",
        "_find_project_root": lambda: project_dir,
        "fetch_lichess_games": lambda *a: fetch_games,
        "fetch_chesscom_games": lambda *a: [],
    }


def _read_output(project_dir: Path) -> dict:
    """Read the training_data.json from project dir."""
    return json.loads((project_dir / "training_data.json").read_text())


# --- Tests ---


def test_resume_skips_tracked_games(project_dir):
    """Games already in analyzed_game_ids are not re-analyzed."""
    # Pre-populate with 2 tracked games
    initial = {
        "version": "1.0",
        "generated": "2026-01-01T00:00:00Z",
        "player": {"lichess": "testplayer", "chesscom": ""},
        "positions": [],
        "analyzed_game_ids": ["https://lichess.org/game1", "https://lichess.org/game2"],
    }
    (project_dir / "training_data.json").write_text(json.dumps(initial))

    games = [
        _make_pgn_game("https://lichess.org/game1", "testplayer", "opp1"),
        _make_pgn_game("https://lichess.org/game2", "testplayer", "opp2"),
        _make_pgn_game("https://lichess.org/game3", "testplayer", "opp3"),
    ]

    call_log = []

    def tracking_worker(*args):
        call_log.append(args[6])  # label
        return _fake_worker_with_mistakes(*args)

    patches = _common_patches(project_dir, games, tracking_worker)
    with patch.multiple("chess_self_coach.trainer", **patches):
        prepare_training_data()

    # Only game3 should have been analyzed
    assert len(call_log) == 1
    assert "opp3" in call_log[0]

    # All 3 games tracked
    output = _read_output(project_dir)
    assert "https://lichess.org/game1" in output["analyzed_game_ids"]
    assert "https://lichess.org/game2" in output["analyzed_game_ids"]
    assert "https://lichess.org/game3" in output["analyzed_game_ids"]


def test_zero_mistake_games_tracked(project_dir):
    """Games with 0 mistakes are tracked and not re-analyzed on next run."""
    games = [_make_pgn_game("https://lichess.org/clean1", "testplayer", "opp1")]

    call_count = []

    def counting_worker(*args):
        call_count.append(1)
        return _fake_worker_no_mistakes(*args)

    patches = _common_patches(project_dir, games, counting_worker)

    # First run: game analyzed, 0 mistakes
    with patch.multiple("chess_self_coach.trainer", **patches):
        prepare_training_data()

    assert len(call_count) == 1
    output = _read_output(project_dir)
    assert "https://lichess.org/clean1" in output["analyzed_game_ids"]
    assert output["positions"] == []

    # Second run: game should be skipped
    call_count.clear()
    with patch.multiple("chess_self_coach.trainer", **patches):
        prepare_training_data()

    assert len(call_count) == 0  # Worker not called


def test_player_not_found_logged_and_tracked(project_dir, capsys):
    """Games where player is not found are logged and tracked."""
    games = [
        _make_pgn_game("https://lichess.org/unknown1", "stranger", "alien"),
    ]

    call_count = []

    def counting_worker(*args):
        call_count.append(1)
        return _fake_worker_no_mistakes(*args)

    patches = _common_patches(project_dir, games, counting_worker)

    with patch.multiple("chess_self_coach.trainer", **patches):
        prepare_training_data()

    # Worker should NOT have been called
    assert len(call_count) == 0

    # Log should mention the skip
    captured = capsys.readouterr()
    assert "player not found in game headers" in captured.out

    # Game ID should be tracked
    output = _read_output(project_dir)
    assert "https://lichess.org/unknown1" in output["analyzed_game_ids"]

    # Second run: game skipped entirely (not even fetched as "new")
    call_count.clear()
    with patch.multiple("chess_self_coach.trainer", **patches):
        prepare_training_data()

    assert len(call_count) == 0


def test_interrupt_resume_continues(project_dir):
    """After interrupt, resume analyzes only remaining games."""
    games = [
        _make_pgn_game("https://lichess.org/g1", "testplayer", "opp1"),
        _make_pgn_game("https://lichess.org/g2", "testplayer", "opp2"),
        _make_pgn_game("https://lichess.org/g3", "testplayer", "opp3"),
    ]

    cancel = threading.Event()
    games_done = []

    def interruptible_worker(*args):
        games_done.append(args[6])  # label
        return _fake_worker_with_mistakes(*args)

    patches = _common_patches(project_dir, games, interruptible_worker)

    # First run: interrupt after 1st game via cancel event
    # We need to set cancel AFTER at least one game finishes.
    # Since ThreadPoolExecutor may process all 3 quickly, we use a worker
    # that sets cancel on the 2nd call.
    call_count = [0]

    def worker_with_interrupt(*args):
        call_count[0] += 1
        result = _fake_worker_with_mistakes(*args)
        if call_count[0] == 1:
            cancel.set()
        return result

    patches_run1 = _common_patches(project_dir, games, worker_with_interrupt)

    with pytest.raises(TrainingInterrupted):
        with patch.multiple("chess_self_coach.trainer", **patches_run1):
            prepare_training_data(cancel=cancel)

    # Partial data should be saved
    output1 = _read_output(project_dir)
    assert len(output1["analyzed_game_ids"]) >= 1
    assert len(output1["positions"]) >= 1

    # Second run: remaining games analyzed
    call_log_run2 = []

    def tracking_worker_run2(*args):
        call_log_run2.append(args[6])
        return _fake_worker_with_mistakes(*args)

    patches_run2 = _common_patches(project_dir, games, tracking_worker_run2)
    with patch.multiple("chess_self_coach.trainer", **patches_run2):
        prepare_training_data()

    output2 = _read_output(project_dir)
    # All 3 games should now be tracked
    assert set(output2["analyzed_game_ids"]) == {
        "https://lichess.org/g1",
        "https://lichess.org/g2",
        "https://lichess.org/g3",
    }
    # Only remaining games should have been analyzed in run 2
    assert len(call_log_run2) < 3


def test_backward_compat_no_analyzed_game_ids(project_dir):
    """Old JSON without analyzed_game_ids still works via position fallback."""
    # Old-format JSON: no analyzed_game_ids field
    old_data = {
        "version": "1.0",
        "generated": "2026-01-01T00:00:00Z",
        "player": {"lichess": "testplayer", "chesscom": ""},
        "positions": [
            {
                "id": "existing_pos_1",
                "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                "player_color": "white",
                "player_move": "a3",
                "best_move": "d4",
                "cp_loss": 200,
                "category": "mistake",
                "context": "test",
                "explanation": "test",
                "acceptable_moves": ["d4"],
                "pv": ["d4"],
                "score_before": "+0.50",
                "score_after": "-1.50",
                "score_after_best": "+0.50",
                "game": {
                    "id": "https://lichess.org/old1",
                    "source": "lichess",
                    "opponent": "opp",
                    "date": "2025-12-01",
                    "result": "1-0",
                    "opening": "Test",
                },
                "srs": {"interval": 3, "ease": 2.5, "next_review": "2026-01-04", "history": []},
            }
        ],
    }
    (project_dir / "training_data.json").write_text(json.dumps(old_data))

    games = [
        _make_pgn_game("https://lichess.org/old1", "testplayer", "opp_old"),
        _make_pgn_game("https://lichess.org/new1", "testplayer", "opp_new"),
    ]

    call_log = []

    def tracking_worker(*args):
        call_log.append(args[6])
        return _fake_worker_with_mistakes(*args)

    patches = _common_patches(project_dir, games, tracking_worker)
    with patch.multiple("chess_self_coach.trainer", **patches):
        prepare_training_data()

    # old1 should be skipped (position-based fallback), only new1 analyzed
    assert len(call_log) == 1
    assert "opp_new" in call_log[0]

    # Output should now have analyzed_game_ids
    output = _read_output(project_dir)
    assert "https://lichess.org/old1" in output["analyzed_game_ids"]
    assert "https://lichess.org/new1" in output["analyzed_game_ids"]

    # SRS from old position should be preserved
    old_pos = [p for p in output["positions"] if p["id"] == "existing_pos_1"]
    assert len(old_pos) == 1
    assert old_pos[0]["srs"]["interval"] == 3
