"""Tests for interrupt/resume and incremental behavior of analyze_games()."""

from __future__ import annotations

import io
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import chess
import chess.engine
import chess.pgn
import pytest

from chess_self_coach.analysis import AnalysisInterrupted, AnalysisSettings, analyze_games


# --- Helpers ---


MINI_PGN_TEXT = """\
[Event "Test"]
[White "TestPlayer"]
[Black "Opponent"]
[Result "1-0"]
[Link "https://lichess.org/test123"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 1-0
"""


def _make_game(
    game_id: str = "https://lichess.org/test123",
    white: str = "TestPlayer",
    black: str = "Opponent",
) -> chess.pgn.Game:
    """Create a minimal PGN game with Link header."""
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


SETTINGS = AnalysisSettings(threads=1, hash_mb=64, limits={"default": {"depth": 5}})


# --- Tests ---


@patch("chess_self_coach.syzygy.find_syzygy", return_value=Path("/fake/syzygy"))
@patch("chess_self_coach.analysis.probe_position_full", return_value=None)
@patch("chess.engine.SimpleEngine.popen_uci")
def test_cancel_interrupts_analysis(mock_popen, mock_tb, mock_syz):
    """Setting the cancel event raises AnalysisInterrupted."""
    mock_popen.return_value = _mock_engine()

    cancel = threading.Event()
    games_done = []

    original_collect = None

    def tracking_collect(game, engine, player_color, settings, lichess_token=None, game_id=""):
        games_done.append(1)
        cancel.set()  # Cancel after first game
        return original_collect(game, engine, player_color, settings, lichess_token, game_id=game_id)

    # We need the real collect_game_data for the mock to work
    from chess_self_coach.analysis import collect_game_data as real_collect
    original_collect = real_collect

    games = [
        _make_game("https://lichess.org/g1", "testplayer", "opp1"),
        _make_game("https://lichess.org/g2", "testplayer", "opp2"),
    ]

    with patch("chess_self_coach.config.load_config", return_value={"players": {"lichess": "testplayer"}, "stockfish": {}}), \
         patch("chess_self_coach.config.find_stockfish", return_value=Path("/usr/games/stockfish")), \
         patch("chess_self_coach.config.check_stockfish_version", return_value="Stockfish 18"), \
         patch("chess_self_coach.config.load_lichess_token", return_value=None), \
         patch("chess_self_coach.importer.fetch_lichess_games", return_value=games), \
         patch("chess_self_coach.importer.fetch_chesscom_games", return_value=[]), \
         patch("chess_self_coach.analysis.load_analysis_data", return_value={"version": "1.0", "player": {}, "games": {}}), \
         patch("chess_self_coach.analysis.save_analysis_data"), \
         patch("chess_self_coach.analysis.collect_game_data", side_effect=tracking_collect):

        with pytest.raises(AnalysisInterrupted):
            analyze_games(max_games=5, settings=SETTINGS, cancel=cancel)

    # At least one game should have been analyzed before interrupt
    assert len(games_done) >= 1


@patch("chess_self_coach.syzygy.find_syzygy", return_value=Path("/fake/syzygy"))
@patch("chess_self_coach.analysis.probe_position_full", return_value=None)
@patch("chess.engine.SimpleEngine.popen_uci")
def test_malformed_games_filtered(mock_popen, mock_tb, mock_syz):
    """Games with White:'?' and Black:'?' are silently filtered."""
    mock_popen.return_value = _mock_engine()

    # Malformed game (no player headers)
    malformed = chess.pgn.read_game(io.StringIO("1. e4 e5 2. Nf3 Nc6 1-0"))

    games = [
        _make_game("https://lichess.org/good1", "testplayer", "opp1"),
        malformed,
    ]

    saved_data = {}

    def mock_save(data, path=None):
        saved_data.update(data)

    with patch("chess_self_coach.config.load_config", return_value={"players": {"lichess": "testplayer"}, "stockfish": {}}), \
         patch("chess_self_coach.config.find_stockfish", return_value=Path("/usr/games/stockfish")), \
         patch("chess_self_coach.config.check_stockfish_version", return_value="Stockfish 18"), \
         patch("chess_self_coach.config.load_lichess_token", return_value=None), \
         patch("chess_self_coach.importer.fetch_lichess_games", return_value=games), \
         patch("chess_self_coach.importer.fetch_chesscom_games", return_value=[]), \
         patch("chess_self_coach.analysis.load_analysis_data", return_value={"version": "1.0", "player": {}, "games": {}}), \
         patch("chess_self_coach.analysis.save_analysis_data", side_effect=mock_save):

        analyze_games(max_games=5, settings=SETTINGS)

    # Only good1 should have been analyzed
    assert "games" in saved_data
    assert len(saved_data["games"]) == 1
    assert "https://lichess.org/good1" in saved_data["games"]


@patch("chess_self_coach.syzygy.find_syzygy", return_value=Path("/fake/syzygy"))
@patch("chess_self_coach.analysis.probe_position_full", return_value=None)
@patch("chess.engine.SimpleEngine.popen_uci")
def test_player_not_found_skipped(mock_popen, mock_tb, mock_syz):
    """Games where player is not found in headers are skipped."""
    mock_popen.return_value = _mock_engine()

    games = [
        _make_game("https://lichess.org/unknown1", "stranger", "alien"),
        _make_game("https://lichess.org/good1", "testplayer", "opp1"),
    ]

    saved_data = {}

    def mock_save(data, path=None):
        saved_data.update(data)

    with patch("chess_self_coach.config.load_config", return_value={"players": {"lichess": "testplayer"}, "stockfish": {}}), \
         patch("chess_self_coach.config.find_stockfish", return_value=Path("/usr/games/stockfish")), \
         patch("chess_self_coach.config.check_stockfish_version", return_value="Stockfish 18"), \
         patch("chess_self_coach.config.load_lichess_token", return_value=None), \
         patch("chess_self_coach.importer.fetch_lichess_games", return_value=games), \
         patch("chess_self_coach.importer.fetch_chesscom_games", return_value=[]), \
         patch("chess_self_coach.analysis.load_analysis_data", return_value={"version": "1.0", "player": {}, "games": {}}), \
         patch("chess_self_coach.analysis.save_analysis_data", side_effect=mock_save):

        analyze_games(max_games=5, settings=SETTINGS)

    # Only good1 should have been analyzed (unknown1 skipped)
    assert len(saved_data["games"]) == 1
    assert "https://lichess.org/good1" in saved_data["games"]


@patch("chess_self_coach.syzygy.find_syzygy", return_value=Path("/fake/syzygy"))
@patch("chess_self_coach.analysis.probe_position_full", return_value=None)
@patch("chess.engine.SimpleEngine.popen_uci")
def test_error_in_game_continues(mock_popen, mock_tb, mock_syz):
    """An error in one game doesn't stop analysis of remaining games."""
    mock_popen.return_value = _mock_engine()

    games = [
        _make_game("https://lichess.org/err1", "testplayer", "opp1"),
        _make_game("https://lichess.org/ok1", "testplayer", "opp2"),
    ]

    saved_data = {}
    call_count = {"n": 0}

    def mock_save(data, path=None):
        saved_data.update(data)

    def mock_collect(game, engine, player_color, settings, lichess_token=None, game_id=""):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("Engine crashed")
        # Return minimal valid game data for the second call
        return {
            "headers": {"white": "testplayer", "black": "opp2", "date": "?",
                        "result": "*", "opening": "?", "source": "lichess",
                        "link": "https://lichess.org/ok1"},
            "player_color": "white",
            "analyzed_at": "2026-03-23T00:00:00Z",
            "settings": settings.to_dict(),
            "moves": [],
        }

    with patch("chess_self_coach.config.load_config", return_value={"players": {"lichess": "testplayer"}, "stockfish": {}}), \
         patch("chess_self_coach.config.find_stockfish", return_value=Path("/usr/games/stockfish")), \
         patch("chess_self_coach.config.check_stockfish_version", return_value="Stockfish 18"), \
         patch("chess_self_coach.config.load_lichess_token", return_value=None), \
         patch("chess_self_coach.importer.fetch_lichess_games", return_value=games), \
         patch("chess_self_coach.importer.fetch_chesscom_games", return_value=[]), \
         patch("chess_self_coach.analysis.load_analysis_data", return_value={"version": "1.0", "player": {}, "games": {}}), \
         patch("chess_self_coach.analysis.save_analysis_data", side_effect=mock_save), \
         patch("chess_self_coach.analysis.collect_game_data", side_effect=mock_collect):

        analyze_games(max_games=5, settings=SETTINGS)

    # ok1 should be saved despite err1 failing
    assert "https://lichess.org/ok1" in saved_data.get("games", {})
    # err1 should NOT be in the data (will be retried next run)
    assert "https://lichess.org/err1" not in saved_data.get("games", {})
