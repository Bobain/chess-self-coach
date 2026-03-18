"""Validation tests for training_data.json texts.

Scans training data and verifies that all user-facing texts are correct,
coherent, and sufficiently informative. Skipped if training data doesn't exist.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import chess
import pytest

TRAINING_DATA_PATH = Path(__file__).parent.parent / "training_data.json"


@pytest.fixture(scope="module")
def positions():
    """Load positions from training_data.json, skip if not present."""
    if not TRAINING_DATA_PATH.exists():
        pytest.skip("training_data.json not found (run train --prepare first)")
    with open(TRAINING_DATA_PATH) as f:
        data = json.load(f)
    return data.get("positions", [])


def test_no_unknown_source(positions):
    """Every position must have a known source (lichess or chess.com)."""
    unknown = [p for p in positions if p["game"]["source"] == "unknown"]
    assert not unknown, (
        f"{len(unknown)} position(s) have source 'unknown': "
        f"{[p['game'].get('id', p['id']) for p in unknown[:5]]}"
    )


def test_no_excessive_pawn_loss_in_text(positions):
    """Explanations should not mention pawn counts > 20 (sign of a display bug)."""
    pattern = re.compile(r"(\d+\.?\d*)\s*pawns?")
    bad = []
    for p in positions:
        for field in ("explanation", "context"):
            text = p.get(field, "")
            for match in pattern.finditer(text):
                value = float(match.group(1))
                if value > 20:
                    bad.append((p["id"], field, text[:80]))
    assert not bad, f"{len(bad)} text(s) with >50 pawns: {bad[:3]}"


def test_context_not_empty(positions):
    """Every position must have a non-empty context."""
    missing = [p["id"] for p in positions if not p.get("context")]
    assert not missing, f"{len(missing)} position(s) have empty context"


def test_pv_has_moves(positions):
    """Every position should have at least 1 move in the principal variation."""
    empty_pv = [p["id"] for p in positions if not p.get("pv")]
    assert not empty_pv, f"{len(empty_pv)} position(s) have empty PV"


def test_no_question_marks_in_game_info(positions):
    """Opponent and date should not be '?' placeholders."""
    bad = []
    for p in positions:
        game = p.get("game", {})
        if game.get("opponent") == "?":
            bad.append((p["id"], "opponent"))
        if game.get("date") == "?":
            bad.append((p["id"], "date"))
    assert not bad, f"{len(bad)} position(s) with '?' in game info: {bad[:5]}"


def test_player_move_differs_from_best(positions):
    """Player move and best move must be different."""
    dupes = [p["id"] for p in positions if p["player_move"] == p["best_move"]]
    assert not dupes, f"{len(dupes)} position(s) where player_move == best_move: {dupes[:5]}"


def test_game_id_is_url(positions):
    """Game ID should be a valid URL (for hyperlink in PWA)."""
    bad = [
        p["id"] for p in positions
        if not p.get("game", {}).get("id", "").startswith("http")
    ]
    assert not bad, (
        f"{len(bad)} position(s) have non-URL game.id: "
        f"{[p['game'].get('id', '') for p in positions if p['id'] in bad[:5]]}"
    )


def test_cp_loss_matches_category(positions):
    """cp_loss must be consistent with the category classification."""
    thresholds = {"blunder": 200, "mistake": 100, "inaccuracy": 50}
    bad = []
    for p in positions:
        category = p["category"]
        cp_loss = p["cp_loss"]
        min_cp = thresholds.get(category, 0)
        if cp_loss < min_cp:
            bad.append((p["id"], category, cp_loss))
    assert not bad, f"{len(bad)} position(s) with mismatched cp_loss/category: {bad[:5]}"


# --- Board coherence tests ---


def test_player_color_valid(positions):
    """player_color must be 'white' or 'black'."""
    bad = [p["id"] for p in positions if p["player_color"] not in ("white", "black")]
    assert not bad, f"{len(bad)} position(s) with invalid player_color"


def test_fen_side_to_move_matches_player_color(positions):
    """The FEN side-to-move must match player_color."""
    bad = []
    for p in positions:
        fen_turn = p["fen"].split()[1]
        expected = "w" if p["player_color"] == "white" else "b"
        if fen_turn != expected:
            bad.append((p["id"], p["player_color"], fen_turn))
    assert not bad, (
        f"{len(bad)} position(s) where FEN turn != player_color: {bad[:5]}"
    )


def test_player_move_is_legal(positions):
    """player_move must be a legal move in the FEN position."""
    bad = []
    for p in positions:
        board = chess.Board(p["fen"])
        try:
            board.parse_san(p["player_move"])
        except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError):
            bad.append((p["id"], p["player_move"], p["fen"][:40]))
    assert not bad, f"{len(bad)} position(s) with illegal player_move: {bad[:5]}"


def test_best_move_is_legal(positions):
    """best_move must be a legal move in the FEN position."""
    bad = []
    for p in positions:
        board = chess.Board(p["fen"])
        try:
            board.parse_san(p["best_move"])
        except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError):
            bad.append((p["id"], p["best_move"], p["fen"][:40]))
    assert not bad, f"{len(bad)} position(s) with illegal best_move: {bad[:5]}"


def test_board_has_two_kings(positions):
    """Every FEN must have exactly one white king and one black king."""
    bad = []
    for p in positions:
        board = chess.Board(p["fen"])
        white_kings = len(board.pieces(chess.KING, chess.WHITE))
        black_kings = len(board.pieces(chess.KING, chess.BLACK))
        if white_kings != 1 or black_kings != 1:
            bad.append((p["id"], white_kings, black_kings))
    assert not bad, f"{len(bad)} position(s) with wrong king count: {bad[:5]}"
