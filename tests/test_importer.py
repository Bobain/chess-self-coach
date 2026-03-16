"""Tests for importer.py pure functions."""

from __future__ import annotations

import io

import chess.pgn

from chess_self_coach.importer import find_deviation, match_game_to_repertoire


def _make_game(pgn_text: str) -> chess.pgn.Game:
    """Helper: parse a PGN string into a Game object."""
    return chess.pgn.read_game(io.StringIO(pgn_text))


def test_find_deviation_at_move_3():
    """Game diverges from repertoire at move 3."""
    game_moves = ["e4", "e5", "Nf3", "Nc6", "Bc4"]
    rep_moves = ["e4", "e5", "Nf3", "Nc6", "Bb5"]
    result = find_deviation(game_moves, rep_moves)
    assert result == 4  # index 4 = move 5 (0-indexed), both sides' 3rd unique move


def test_find_deviation_no_match():
    """Game has completely different opening — returns None."""
    game_moves = ["d4", "d5", "c4"]
    rep_moves = ["e4", "e5", "Nf3"]
    result = find_deviation(game_moves, rep_moves)
    assert result is None


def test_find_deviation_identical():
    """Game follows repertoire exactly — returns None (no deviation)."""
    game_moves = ["e4", "e5", "Nf3", "Nc6", "Bb5"]
    rep_moves = ["e4", "e5", "Nf3", "Nc6", "Bb5"]
    result = find_deviation(game_moves, rep_moves)
    assert result is None


def test_match_game_to_repertoire_found():
    """Game matches a repertoire chapter."""
    game = _make_game('[Event "My Game"]\n\n1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5 *\n')
    rep = _make_game('[Event "QGD"]\n\n1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Nf3 Be7 *\n')

    match, dev_idx = match_game_to_repertoire(game, [rep])
    assert match is not None
    assert match.headers["Event"] == "QGD"
    assert dev_idx is not None
    # Deviation at move 4 by White (Bg5 vs Nf3), which is index 6
    assert dev_idx == 6


def test_match_game_to_repertoire_no_match():
    """No repertoire chapter matches the game."""
    game = _make_game('[Event "My Game"]\n\n1. e4 c5 2. Nf3 d6 *\n')
    rep = _make_game('[Event "QGD"]\n\n1. d4 d5 2. c4 e6 *\n')

    match, dev_idx = match_game_to_repertoire(game, [rep])
    assert match is None
    assert dev_idx is None
