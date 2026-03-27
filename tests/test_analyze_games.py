"""Tests for analyze_games() orchestrator — Phase 1 runner."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import chess
import chess.engine
import chess.pgn

from chess_self_coach.analysis import (
    AnalysisSettings,
    analyze_games,
)


MINI_PGN_TEXT = """\
[Event "Test"]
[White "TestPlayer"]
[Black "Opponent"]
[Result "1-0"]
[Link "https://lichess.org/test123"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 1-0
"""


def _make_game(pgn_text: str = MINI_PGN_TEXT) -> chess.pgn.Game:
    """Parse a PGN string into a game."""
    return chess.pgn.read_game(io.StringIO(pgn_text))


def _mock_engine():
    """Create a mock Stockfish engine."""
    engine = MagicMock(spec=chess.engine.SimpleEngine)
    call_count = {"n": 0}

    def mock_analyse(board, limit, **kwargs):
        call_count["n"] += 1
        pv = list(board.legal_moves)[:2]
        return {
            "score": chess.engine.PovScore(chess.engine.Cp(20 + call_count["n"]), chess.WHITE),
            "pv": pv,
            "depth": 5,
            "seldepth": 8,
            "nodes": 10000,
            "nps": 100000,
            "time": 0.05,
            "tbhits": 0,
            "hashfull": 10,
        }

    engine.analyse = mock_analyse
    engine.configure = MagicMock()
    engine.quit = MagicMock()
    return engine


# All patches target the source modules (not analysis.py, since imports are lazy)
_COMMON_PATCHES = {
    "chess_self_coach.config.load_config": lambda: {
        "players": {"lichess": "testplayer"},
        "stockfish": {},
    },
    "chess_self_coach.config.find_stockfish": lambda _: Path("/usr/games/stockfish"),
    "chess_self_coach.config.check_stockfish_version": lambda *a: "Stockfish 18",
    "chess_self_coach.config.load_lichess_token": lambda **kw: None,
    "chess_self_coach.importer.fetch_chesscom_games": lambda *a: [],
}


def _apply_patches(extra: dict | None = None):
    """Create a combined context manager for all common patches."""
    from contextlib import ExitStack
    from unittest.mock import patch

    patches = dict(_COMMON_PATCHES)
    if extra:
        patches.update(extra)

    stack = ExitStack()
    mocks = {}
    for target, side_effect in patches.items():
        m = stack.enter_context(patch(target, side_effect=side_effect if callable(side_effect) and not isinstance(side_effect, MagicMock) else None, return_value=side_effect if not callable(side_effect) or isinstance(side_effect, MagicMock) else None))
        mocks[target] = m
    return stack, mocks


@patch("chess_self_coach.syzygy.find_syzygy", return_value=Path("/fake/syzygy"))
@patch("chess_self_coach.analysis.probe_position_full", return_value=None)
@patch("chess.engine.SimpleEngine.popen_uci")
def test_analyze_games_writes_analysis_data(mock_popen, mock_tb, mock_syz, tmp_path):
    """analyze_games produces analysis_data.json with per-game entries."""
    mock_popen.return_value = _mock_engine()

    saved_data = {}

    def mock_save(data, path=None):
        saved_data.update(data)

    with patch("chess_self_coach.config.load_config", return_value={"players": {"lichess": "testplayer"}, "stockfish": {}}), \
         patch("chess_self_coach.config.find_stockfish", return_value=Path("/usr/games/stockfish")), \
         patch("chess_self_coach.config.check_stockfish_version", return_value="Stockfish 18"), \
         patch("chess_self_coach.config.load_lichess_token", return_value=None), \
         patch("chess_self_coach.importer.fetch_lichess_games", return_value=[_make_game()]), \
         patch("chess_self_coach.importer.fetch_chesscom_games", return_value=[]), \
         patch("chess_self_coach.analysis.load_analysis_data", return_value={"version": "1.0", "player": {}, "games": {}}), \
         patch("chess_self_coach.analysis.save_analysis_data", side_effect=mock_save):

        settings = AnalysisSettings(threads=1, hash_mb=64, limits={"default": {"depth": 5}})
        analyze_games(max_games=1, settings=settings)

    assert "games" in saved_data
    assert len(saved_data["games"]) == 1

    game_data = list(saved_data["games"].values())[0]
    assert len(game_data["moves"]) == 5
    assert "analysis_duration_s" in game_data


@patch("chess_self_coach.syzygy.find_syzygy", return_value=Path("/fake/syzygy"))
@patch("chess_self_coach.analysis.probe_position_full", return_value=None)
@patch("chess.engine.SimpleEngine.popen_uci")
def test_analyze_games_incremental_skips_analyzed(mock_popen, mock_tb, mock_syz, tmp_path):
    """Second run skips games already in analysis_data.json."""
    mock_popen.return_value = _mock_engine()

    existing_data = {
        "version": "1.0",
        "player": {"lichess": "testplayer"},
        "games": {
            "https://lichess.org/test123": {
                "settings": {"threads": 1, "hash_mb": 64, "limits": {"default": {"depth": 5}}},
                "moves": [],
            }
        },
    }

    save_called = {"count": 0}

    def mock_save(data, path=None):
        save_called["count"] += 1

    with patch("chess_self_coach.config.load_config", return_value={"players": {"lichess": "testplayer"}, "stockfish": {}}), \
         patch("chess_self_coach.config.find_stockfish", return_value=Path("/usr/games/stockfish")), \
         patch("chess_self_coach.config.check_stockfish_version", return_value="Stockfish 18"), \
         patch("chess_self_coach.config.load_lichess_token", return_value=None), \
         patch("chess_self_coach.importer.fetch_lichess_games", return_value=[_make_game()]), \
         patch("chess_self_coach.importer.fetch_chesscom_games", return_value=[]), \
         patch("chess_self_coach.analysis.load_analysis_data", return_value=existing_data), \
         patch("chess_self_coach.analysis.save_analysis_data", side_effect=mock_save):

        settings = AnalysisSettings(threads=1, hash_mb=64, limits={"default": {"depth": 5}})
        analyze_games(max_games=1, settings=settings)

    # Should not save — game already analyzed with same ID
    assert save_called["count"] == 0


@patch("chess_self_coach.syzygy.find_syzygy", return_value=Path("/fake/syzygy"))
@patch("chess_self_coach.analysis.probe_position_full", return_value=None)
@patch("chess.engine.SimpleEngine.popen_uci")
def test_analyze_games_reanalyze_different_settings(mock_popen, mock_tb, mock_syz, tmp_path):
    """reanalyze_all=True re-analyzes games with different settings."""
    mock_popen.return_value = _mock_engine()

    existing_data = {
        "version": "1.0",
        "player": {"lichess": "testplayer"},
        "games": {
            "https://lichess.org/test123": {
                "settings": {"threads": 1, "hash_mb": 64, "limits": {"default": {"depth": 5}}},
                "moves": [],
            }
        },
    }

    saved_data = {}

    def mock_save(data, path=None):
        saved_data.update(data)

    with patch("chess_self_coach.config.load_config", return_value={"players": {"lichess": "testplayer"}, "stockfish": {}}), \
         patch("chess_self_coach.config.find_stockfish", return_value=Path("/usr/games/stockfish")), \
         patch("chess_self_coach.config.check_stockfish_version", return_value="Stockfish 18"), \
         patch("chess_self_coach.config.load_lichess_token", return_value=None), \
         patch("chess_self_coach.importer.fetch_lichess_games", return_value=[_make_game()]), \
         patch("chess_self_coach.importer.fetch_chesscom_games", return_value=[]), \
         patch("chess_self_coach.analysis.load_analysis_data", return_value=existing_data), \
         patch("chess_self_coach.analysis.save_analysis_data", side_effect=mock_save):

        # Different settings → should re-analyze
        new_settings = AnalysisSettings(threads=4, hash_mb=2048, limits={"default": {"depth": 18}})
        analyze_games(max_games=1, reanalyze_all=True, settings=new_settings)

    assert "games" in saved_data
    game_data = list(saved_data["games"].values())[0]
    # Settings should be the new ones
    assert game_data["settings"]["hash_mb"] == 2048
