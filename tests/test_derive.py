"""Tests for annotate_and_derive() — Phase 2 training data derivation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from chess_self_coach.analysis import annotate_and_derive


def _make_analysis_data(
    cp_loss: int = 250,
    score_before_cp: int = 50,
    score_after_cp: int = -200,
    player_color: str = "white",
    side: str = "white",
) -> dict:
    """Create minimal analysis_data with one game and one move."""
    return {
        "version": "1.0",
        "player": {"lichess": "testplayer", "chesscom": ""},
        "games": {
            "https://lichess.org/test123": {
                "headers": {
                    "white": "TestPlayer",
                    "black": "Opponent",
                    "date": "2026.03.20",
                    "result": "0-1",
                    "opening": "Sicilian Defense",
                    "source": "lichess",
                    "link": "https://lichess.org/test123",
                },
                "player_color": player_color,
                "analyzed_at": "2026-03-20T10:00:00Z",
                "analysis_duration_s": 5.0,
                "settings": {"threads": 1, "hash_mb": 64, "limits": {"default": {"depth": 5}}},
                "moves": [
                    {
                        "ply": 1,
                        "fen_before": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                        "fen_after": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                        "move_san": "e4",
                        "move_uci": "e2e4",
                        "side": side,
                        "eval_source": "stockfish",
                        "eval_before": {
                            "score_cp": score_before_cp,
                            "is_mate": False,
                            "mate_in": None,
                            "depth": 5,
                            "seldepth": 8,
                            "nodes": 10000,
                            "nps": 100000,
                            "time_ms": 100,
                            "tbhits": 0,
                            "hashfull": 10,
                            "pv_san": ["d4", "d5", "c4"],
                            "pv_uci": ["d2d4", "d7d5", "c2c4"],
                            "best_move_san": "d4",
                            "best_move_uci": "d2d4",
                        },
                        "eval_after": {
                            "score_cp": score_after_cp,
                            "is_mate": False,
                            "mate_in": None,
                            "depth": 5,
                            "seldepth": 8,
                            "nodes": 10000,
                            "nps": 100000,
                            "time_ms": 100,
                            "tbhits": 0,
                            "hashfull": 10,
                            "pv_san": [],
                            "pv_uci": [],
                            "best_move_san": None,
                            "best_move_uci": None,
                        },
                        "eval_after_best": {
                            "score_cp": score_before_cp,
                            "is_mate": False,
                            "mate_in": None,
                        },
                        "tablebase_before": None,
                        "tablebase_after": None,
                        "opening_explorer": None,
                        "cp_loss": cp_loss,
                        "board": {
                            "piece_count": 32,
                            "is_check": False,
                            "is_capture": False,
                            "is_castling": False,
                            "is_en_passant": False,
                            "is_promotion": False,
                            "promoted_to": None,
                            "legal_moves_count": 20,
                        },
                        "clock": {"player": 600.0, "opponent": 600.0, "time_spent": None},
                    },
                ],
            },
        },
    }


@patch("chess_self_coach.config.load_config", return_value={"players": {"lichess": "testplayer", "chesscom": ""}})
def test_derive_produces_training_data(mock_config, tmp_path: Path):
    """Derives training_data.json with correct schema from analysis_data."""
    analysis_path = tmp_path / "analysis_data.json"
    output_path = tmp_path / "training_data.json"

    analysis_path.write_text(json.dumps(_make_analysis_data(cp_loss=250)))

    annotate_and_derive(analysis_path=analysis_path, output_path=output_path)

    assert output_path.exists()
    td = json.loads(output_path.read_text())

    assert td["version"] == "1.0"
    assert "generated" in td
    assert td["player"]["lichess"] == "testplayer"
    assert len(td["positions"]) == 1
    assert "https://lichess.org/test123" in td["analyzed_game_ids"]

    pos = td["positions"][0]
    assert pos["category"] == "blunder"
    assert pos["cp_loss"] == 250
    assert pos["player_move"] == "e4"
    assert pos["best_move"] == "d4"
    assert "srs" in pos
    assert pos["game"]["id"] == "https://lichess.org/test123"


@patch("chess_self_coach.config.load_config", return_value={"players": {"lichess": "testplayer", "chesscom": ""}})
def test_derive_filters_below_threshold(mock_config, tmp_path: Path):
    """Moves with cp_loss below threshold are excluded."""
    analysis_path = tmp_path / "analysis_data.json"
    output_path = tmp_path / "training_data.json"

    analysis_path.write_text(json.dumps(_make_analysis_data(cp_loss=30)))

    annotate_and_derive(analysis_path=analysis_path, output_path=output_path, min_cp_loss=50)

    td = json.loads(output_path.read_text())
    assert len(td["positions"]) == 0


@patch("chess_self_coach.config.load_config", return_value={"players": {"lichess": "testplayer", "chesscom": ""}})
def test_derive_skips_opponent_moves(mock_config, tmp_path: Path):
    """Only the player's moves are considered for mistakes."""
    analysis_path = tmp_path / "analysis_data.json"
    output_path = tmp_path / "training_data.json"

    # Player is white, but the move is black's
    analysis_path.write_text(json.dumps(_make_analysis_data(
        cp_loss=300, player_color="white", side="black"
    )))

    annotate_and_derive(analysis_path=analysis_path, output_path=output_path)

    td = json.loads(output_path.read_text())
    assert len(td["positions"]) == 0


@patch("chess_self_coach.config.load_config", return_value={"players": {"lichess": "testplayer", "chesscom": ""}})
def test_derive_preserves_srs_state(mock_config, tmp_path: Path):
    """SRS state from existing training_data.json is preserved."""
    analysis_path = tmp_path / "analysis_data.json"
    output_path = tmp_path / "training_data.json"

    analysis_path.write_text(json.dumps(_make_analysis_data(cp_loss=250)))

    # Create existing training data with SRS state
    import hashlib

    pos_id = hashlib.sha256(
        b"rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1:e4"
    ).hexdigest()[:12]

    existing_td = {
        "version": "1.0",
        "positions": [{
            "id": pos_id,
            "srs": {
                "interval": 3,
                "ease": 2.3,
                "next_review": "2026-03-25",
                "history": [{"date": "2026-03-20", "correct": True}],
            },
        }],
    }
    output_path.write_text(json.dumps(existing_td))

    annotate_and_derive(analysis_path=analysis_path, output_path=output_path)

    td = json.loads(output_path.read_text())
    assert len(td["positions"]) == 1
    srs = td["positions"][0]["srs"]
    assert srs["interval"] == 3
    assert srs["ease"] == 2.3
    assert len(srs["history"]) == 1


@patch("chess_self_coach.config.load_config", return_value={"players": {"lichess": "testplayer", "chesscom": ""}})
def test_derive_skips_already_lost(mock_config, tmp_path: Path):
    """Positions where player is already badly losing are skipped."""
    analysis_path = tmp_path / "analysis_data.json"
    output_path = tmp_path / "training_data.json"

    # Player (white) is at -600 before and -800 after — already lost
    analysis_path.write_text(json.dumps(_make_analysis_data(
        cp_loss=200, score_before_cp=-600, score_after_cp=-800,
    )))

    annotate_and_derive(analysis_path=analysis_path, output_path=output_path)

    td = json.loads(output_path.read_text())
    assert len(td["positions"]) == 0


@patch("chess_self_coach.config.load_config", return_value={"players": {"lichess": "testplayer", "chesscom": ""}})
def test_derive_classifies_correctly(mock_config, tmp_path: Path):
    """Move classification thresholds work correctly."""
    analysis_path = tmp_path / "analysis_data.json"
    output_path = tmp_path / "training_data.json"

    # Inaccuracy (50-99)
    analysis_path.write_text(json.dumps(_make_analysis_data(
        cp_loss=75, score_before_cp=50, score_after_cp=-25,
    )))
    annotate_and_derive(analysis_path=analysis_path, output_path=output_path)
    td = json.loads(output_path.read_text())
    assert td["positions"][0]["category"] == "inaccuracy"

    # Mistake (100-199)
    analysis_path.write_text(json.dumps(_make_analysis_data(
        cp_loss=150, score_before_cp=50, score_after_cp=-100,
    )))
    annotate_and_derive(analysis_path=analysis_path, output_path=output_path)
    td = json.loads(output_path.read_text())
    assert td["positions"][0]["category"] == "mistake"

    # Blunder (200+)
    analysis_path.write_text(json.dumps(_make_analysis_data(
        cp_loss=300, score_before_cp=50, score_after_cp=-250,
    )))
    annotate_and_derive(analysis_path=analysis_path, output_path=output_path)
    td = json.loads(output_path.read_text())
    assert td["positions"][0]["category"] == "blunder"
