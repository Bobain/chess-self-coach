"""Tests for trainer.py pure functions."""

from __future__ import annotations

import io

import chess
import chess.engine
import chess.pgn

from chess_opening_prep.trainer import (
    BLUNDER_THRESHOLD,
    INACCURACY_THRESHOLD,
    MISTAKE_THRESHOLD,
    _classify_mistake,
    _detect_source,
    _determine_player_color,
    _format_score_cp,
    _make_position_id,
    _score_to_cp,
    compute_cp_loss,
    generate_explanation,
)


# --- Helper ---


def _make_game(pgn_text: str) -> chess.pgn.Game:
    """Parse a PGN string into a Game object."""
    return chess.pgn.read_game(io.StringIO(pgn_text))


# --- _score_to_cp ---


def test_score_to_cp_positive():
    """Positive centipawn score from white's perspective."""
    score = chess.engine.PovScore(chess.engine.Cp(150), chess.WHITE)
    assert _score_to_cp(score) == 150


def test_score_to_cp_negative():
    """Negative centipawn score from white's perspective."""
    score = chess.engine.PovScore(chess.engine.Cp(-100), chess.WHITE)
    assert _score_to_cp(score) == -100


def test_score_to_cp_mate_positive():
    """Positive mate score returns sentinel value."""
    score = chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE)
    assert _score_to_cp(score) == 10000


def test_score_to_cp_mate_negative():
    """Negative mate score returns negative sentinel value."""
    score = chess.engine.PovScore(chess.engine.Mate(-2), chess.WHITE)
    assert _score_to_cp(score) == -10000


def test_score_to_cp_black_perspective():
    """Score from black's POV is converted to white's perspective."""
    score = chess.engine.PovScore(chess.engine.Cp(200), chess.BLACK)
    assert _score_to_cp(score) == -200


# --- compute_cp_loss ---


def test_cp_loss_white_loses_advantage():
    """White had +100, now +20: lost 80cp."""
    assert compute_cp_loss(100, 20, chess.WHITE) == 80


def test_cp_loss_white_gains():
    """White had +100, now +150: gained (negative loss)."""
    assert compute_cp_loss(100, 150, chess.WHITE) == -50


def test_cp_loss_black_loses_advantage():
    """Eval was -100 (good for black), now -20: black lost 80cp."""
    assert compute_cp_loss(-100, -20, chess.BLACK) == 80


def test_cp_loss_black_gains():
    """Eval was -100, now -150: black gained (negative loss)."""
    assert compute_cp_loss(-100, -150, chess.BLACK) == -50


def test_cp_loss_zero():
    """No change in position means zero loss."""
    assert compute_cp_loss(50, 50, chess.WHITE) == 0


# --- _classify_mistake ---


def test_classify_blunder():
    assert _classify_mistake(250) == "blunder"


def test_classify_mistake_category():
    assert _classify_mistake(150) == "mistake"


def test_classify_inaccuracy():
    assert _classify_mistake(75) == "inaccuracy"


def test_classify_ok():
    assert _classify_mistake(30) is None


def test_classify_boundary_blunder():
    assert _classify_mistake(BLUNDER_THRESHOLD) == "blunder"


def test_classify_boundary_mistake():
    assert _classify_mistake(MISTAKE_THRESHOLD) == "mistake"


def test_classify_boundary_inaccuracy():
    assert _classify_mistake(INACCURACY_THRESHOLD) == "inaccuracy"


def test_classify_just_below_inaccuracy():
    assert _classify_mistake(INACCURACY_THRESHOLD - 1) is None


# --- _format_score_cp ---


def test_format_score_cp_positive():
    assert _format_score_cp(150) == "+1.50"


def test_format_score_cp_negative():
    assert _format_score_cp(-75) == "-0.75"


def test_format_score_cp_zero():
    assert _format_score_cp(0) == "+0.00"


def test_format_score_cp_none():
    assert _format_score_cp(None) == "+0.00"


# --- generate_explanation ---


def test_explanation_basic():
    """Basic explanation includes move, category, and best move."""
    board = chess.Board()  # starting position
    result = generate_explanation(board, "a3", "e4", 50, "inaccuracy")
    assert "You played a3" in result
    assert "inaccuracy" in result
    assert "e4" in result


def test_explanation_capture():
    """Explanation mentions missed capture."""
    # Position where Bxf7+ is possible
    board = chess.Board("r1bqkbnr/pppppppp/2n5/4P3/2B5/8/PPP2PPP/RNBQK1NR w KQkq - 0 4")
    result = generate_explanation(board, "d3", "Bxf7+", 200, "blunder")
    assert "capturing" in result or "pawn" in result


def test_explanation_invalid_best_san():
    """Graceful fallback when best_san can't be parsed."""
    board = chess.Board()
    result = generate_explanation(board, "e4", "INVALID", 100, "mistake")
    assert "A better move was INVALID" in result


# --- _make_position_id ---


def test_position_id_deterministic():
    """Same inputs produce same ID."""
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    id1 = _make_position_id(fen, "e4")
    id2 = _make_position_id(fen, "e4")
    assert id1 == id2


def test_position_id_different_moves():
    """Different moves produce different IDs."""
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    id1 = _make_position_id(fen, "e4")
    id2 = _make_position_id(fen, "d4")
    assert id1 != id2


def test_position_id_length():
    """ID is 12 hex characters."""
    pid = _make_position_id("fen", "e4")
    assert len(pid) == 12
    assert all(c in "0123456789abcdef" for c in pid)


# --- _determine_player_color ---


def test_determine_color_white():
    game = _make_game('[White "testuser"]\n[Black "opponent"]\n\n1. e4 e5 *')
    assert _determine_player_color(game, "testuser", None) == chess.WHITE


def test_determine_color_black():
    game = _make_game('[White "opponent"]\n[Black "testuser"]\n\n1. e4 e5 *')
    assert _determine_player_color(game, "testuser", None) == chess.BLACK


def test_determine_color_chesscom():
    game = _make_game('[White "opponent"]\n[Black "ChesscomUser"]\n\n1. e4 e5 *')
    assert _determine_player_color(game, "lichessuser", "chesscomuser") == chess.BLACK


def test_determine_color_not_found():
    game = _make_game('[White "other1"]\n[Black "other2"]\n\n1. e4 e5 *')
    assert _determine_player_color(game, "testuser", None) is None


def test_determine_color_case_insensitive():
    game = _make_game('[White "TestUser"]\n[Black "opponent"]\n\n1. e4 e5 *')
    assert _determine_player_color(game, "testuser", None) == chess.WHITE


# --- _detect_source ---


def test_detect_source_lichess():
    game = _make_game('[Site "https://lichess.org/abc123"]\n\n1. e4 *')
    assert _detect_source(game) == "lichess"


def test_detect_source_chesscom():
    game = _make_game('[Site "https://www.chess.com/game/live/12345"]\n\n1. e4 *')
    assert _detect_source(game) == "chess.com"


def test_detect_source_unknown():
    game = _make_game('[Site "unknown"]\n\n1. e4 *')
    assert _detect_source(game) == "unknown"
