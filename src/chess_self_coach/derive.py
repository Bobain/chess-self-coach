"""Phase 2: derive training_data.json from raw analysis data.

Reads analysis_data.json (Phase 1 output), filters for player mistakes,
generates explanations, and writes training_data.json. Can be re-run cheaply
without re-running Stockfish.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import chess

from chess_self_coach.analysis import load_analysis_data
from chess_self_coach.config import (
    analysis_data_path,
    load_config,
    training_data_path,
)
from chess_self_coach.constants import DOMINATED_POSITION_CP, MAX_PV_MOVES
from chess_self_coach.io import atomic_write_json
from chess_self_coach.tablebase import (
    TablebaseResult,
    tablebase_context,
    tablebase_explanation,
)
from chess_self_coach.trainer import (
    _classify_mistake,
    _format_score_cp,
    _generate_context,
    _time_pressure_context,
    generate_explanation,
)


def annotate_and_derive(
    analysis_path: Path | None = None,
    output_path: Path | None = None,
    min_cp_loss: int = 50,
) -> None:
    """Derive training_data.json from analysis_data.json (Phase 2).

    Reads the raw analysis data, filters for player mistakes, generates
    explanations, and writes training_data.json. Can be re-run cheaply
    without re-running Stockfish.

    Args:
        analysis_path: Path to analysis_data.json. Defaults to data directory.
        output_path: Path to training_data.json. Defaults to data directory.
        min_cp_loss: Minimum centipawn loss to include (default: 50 = inaccuracy).
    """
    if analysis_path is None:
        analysis_path = analysis_data_path()
    if output_path is None:
        output_path = training_data_path()

    # Load analysis data
    analysis_data = load_analysis_data(analysis_path)
    games = analysis_data.get("games", {})
    if not games:
        print("  No analysis data found. Run analysis first.")
        return

    # Load existing training data (to preserve SRS state)
    existing_positions: dict[str, dict] = {}
    if output_path.exists():
        try:
            with open(output_path) as f:
                existing_td = json.load(f)
            for pos in existing_td.get("positions", []):
                existing_positions[pos["id"]] = pos
        except (json.JSONDecodeError, KeyError):
            pass

    # Process each game
    positions: dict[str, dict] = {}
    analyzed_game_ids: set[str] = set()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for game_id, game_data in games.items():
        analyzed_game_ids.add(game_id)
        player_color = game_data.get("player_color", "white")
        moves = game_data.get("moves", [])
        headers = game_data.get("headers", {})

        game_info = {
            "id": game_id,
            "source": headers.get("source", "unknown"),
            "opponent": (
                headers.get("black", "?")
                if player_color == "white"
                else headers.get("white", "?")
            ),
            "date": headers.get("date", "?"),
            "result": headers.get("result", "*"),
            "opening": headers.get("opening", "?"),
        }

        for move_data in moves:
            # Only look at the player's moves
            if move_data["side"] != player_color:
                continue

            cp_loss = move_data.get("cp_loss", 0)
            if cp_loss < min_cp_loss:
                continue

            category = _classify_mistake(cp_loss)
            if category is None:
                continue

            # Extract scores
            eval_before = move_data.get("eval_before", {})
            eval_after = move_data.get("eval_after", {})

            score_before_cp = eval_before.get("score_cp")
            score_after_cp = eval_after.get("score_cp")

            # Pedagogical filter: skip already-lost or already-won
            if score_before_cp is not None and score_after_cp is not None:
                player_cp = (
                    score_before_cp if player_color == "white" else -score_before_cp
                )
                player_cp_after = (
                    score_after_cp if player_color == "white" else -score_after_cp
                )
                is_mate = eval_before.get("is_mate", False)
                if (
                    player_cp < -DOMINATED_POSITION_CP
                    and player_cp_after < -DOMINATED_POSITION_CP
                    and not is_mate
                ):
                    continue  # Already lost
                if (
                    player_cp > DOMINATED_POSITION_CP
                    and player_cp_after > DOMINATED_POSITION_CP
                ):
                    continue  # Already won

            was_mate = eval_before.get("is_mate", False)
            fen = move_data.get("fen_before", "")
            actual_san = move_data.get("move_san", "")
            best_san = eval_before.get("best_move_san", "")

            # Skip if the player already played the best move
            if best_san and actual_san == best_san:
                continue

            # Generate explanation
            board = chess.Board(fen) if fen else chess.Board()
            explanation = generate_explanation(
                board,
                actual_san,
                best_san or actual_san,
                cp_loss,
                category,
                was_mate=was_mate,
                score_after_cp=score_after_cp,
            )

            # Generate context
            context = _generate_context(
                category,
                cp_loss,
                was_mate,
                score_after_cp,
                fen=fen,
                score_before_cp=score_before_cp,
                player_color=player_color,
            )

            # Override with tablebase-specific text for endgame positions
            tb_before_raw = move_data.get("tablebase_before")
            tb_after_raw = move_data.get("tablebase_after")
            if tb_before_raw:
                tb_res_before = TablebaseResult(
                    category=tb_before_raw["category"],
                    dtz=tb_before_raw.get("dtz"),
                    dtm=tb_before_raw.get("dtm"),
                    best_move=None,
                )
                piece_count = move_data.get("board", {}).get("piece_count", 0)
                context = tablebase_context(
                    tb_res_before, piece_count, player_color
                )
                if tb_after_raw:
                    tb_res_after = TablebaseResult(
                        category=tb_after_raw["category"],
                        dtz=tb_after_raw.get("dtz"),
                        dtm=tb_after_raw.get("dtm"),
                        best_move=None,
                    )
                    explanation = tablebase_explanation(
                        tb_res_before, tb_res_after, actual_san, best_san
                    )

            # Time pressure context
            clock = move_data.get("clock", {})
            time_ctx = _time_pressure_context(
                clock.get("player"), clock.get("opponent")
            )
            if time_ctx:
                context = f"{context} {time_ctx}"

            # PV (from eval_before)
            pv = eval_before.get("pv_san", [])

            # Position ID
            pos_id_data = f"{fen}:{actual_san}"
            pos_id = hashlib.sha256(pos_id_data.encode()).hexdigest()[:12]

            # Build position dict
            pos = {
                "id": pos_id,
                "fen": fen,
                "player_color": player_color,
                "player_move": actual_san,
                "best_move": best_san or actual_san,
                "context": context,
                "score_before": _format_score_cp(score_before_cp),
                "score_after": _format_score_cp(score_after_cp),
                "score_after_best": _format_score_cp(score_before_cp),
                "cp_loss": cp_loss,
                "category": category,
                "explanation": explanation,
                "acceptable_moves": [best_san] if best_san else [],
                "pv": pv[:MAX_PV_MOVES] if not was_mate else pv,
                "game": game_info,
                "clock": {
                    "player": clock.get("player"),
                    "opponent": clock.get("opponent"),
                },
            }

            # Tablebase data
            tb_before = move_data.get("tablebase_before")
            tb_after = move_data.get("tablebase_after")
            if tb_before or tb_after:
                tb_data = {}
                if tb_before:
                    tb_data["before"] = {
                        "category": tb_before.get("category"),
                        "dtm": tb_before.get("dtm"),
                        "dtz": tb_before.get("dtz"),
                    }
                if tb_after:
                    tb_data["after"] = {
                        "category": tb_after.get("category"),
                        "dtm": tb_after.get("dtm"),
                        "dtz": tb_after.get("dtz"),
                    }
                if tb_before and tb_after:
                    tier_before = tb_before.get("tier", "DRAW")
                    tier_after = tb_after.get("tier", "DRAW")
                    tb_data["transition"] = f"{tier_before} → {tier_after}"
                pos["tablebase"] = tb_data

            # Preserve SRS state from existing training data
            if pos_id in existing_positions:
                pos["srs"] = existing_positions[pos_id].get(
                    "srs",
                    {
                        "interval": 0,
                        "ease": 2.5,
                        "next_review": today,
                        "history": [],
                    },
                )
            else:
                pos["srs"] = {
                    "interval": 0,
                    "ease": 2.5,
                    "next_review": today,
                    "history": [],
                }

            positions[pos_id] = pos

    # Build output
    config = load_config()
    players = config.get("players", {})
    lichess_user = players.get("lichess", "")
    chesscom_user = players.get("chesscom", "")

    severity = {"blunder": 0, "mistake": 1, "inaccuracy": 2}
    sorted_positions = sorted(
        positions.values(),
        key=lambda m: (severity.get(m["category"], 3), -m["cp_loss"]),
    )

    training_data = {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "player": {"lichess": lichess_user, "chesscom": chesscom_user},
        "positions": sorted_positions,
        "analyzed_game_ids": sorted(analyzed_game_ids),
    }

    atomic_write_json(output_path, training_data)
    print(f"  Training data derived: {output_path}")
