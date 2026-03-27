"""Lichess tablebase API client for perfect endgame analysis.

Probes the public Lichess tablebase API (no token required) for positions
with <= 7 pieces. Returns mathematically exact Win/Draw/Loss verdicts
instead of heuristic Stockfish evaluations.

API: https://tablebase.lichess.ovh/standard?fen=<FEN>
Coverage: up to 7 pieces (Syzygy tablebases)
"""

from __future__ import annotations

from dataclasses import dataclass

import chess
import requests

from chess_self_coach.constants import ENDGAME_PIECES_MAX

# API endpoint (public, no auth required)
_API_URL = "https://tablebase.lichess.ovh/standard"

# Request timeout (seconds)
_TIMEOUT = 5.0

# Maximum pieces for tablebase lookup
MAX_PIECES = ENDGAME_PIECES_MAX

# Map API categories to WDL tiers
_CATEGORY_TIERS: dict[str, str] = {
    "win": "WIN",
    "syzygy-win": "WIN",
    "maybe-win": "WIN",
    "draw": "DRAW",
    "cursed-win": "DRAW",
    "blessed-loss": "DRAW",
    "loss": "LOSS",
    "syzygy-loss": "LOSS",
    "maybe-loss": "LOSS",
}

@dataclass
class TablebaseResult:
    """Result from a tablebase probe."""

    category: str
    dtz: int | None
    dtm: int | None
    best_move: str | None

    @property
    def tier(self) -> str:
        """WDL tier: WIN, DRAW, or LOSS."""
        return _CATEGORY_TIERS.get(self.category, "DRAW")

    def format_verdict(self) -> str:
        """Human-readable verdict, e.g. 'win, mate in 23' or 'draw'."""
        tier = self.tier.lower()
        if self.dtm is not None and self.dtm != 0:
            return f"{tier}, mate in {abs(self.dtm)}"
        if self.dtz is not None and self.dtz != 0:
            return f"{tier} (DTZ {abs(self.dtz)})"
        return tier


def probe_position(fen: str) -> TablebaseResult | None:
    """Probe the Lichess tablebase API for a position.

    Args:
        fen: FEN string of the position.

    Returns:
        TablebaseResult if the position has <= 7 pieces and the API responds,
        None otherwise (too many pieces, network error, timeout).
    """
    board = chess.Board(fen)
    if len(board.piece_map()) > MAX_PIECES:
        return None

    try:
        resp = requests.get(_API_URL, params={"fen": fen}, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None

    category = data.get("category")
    if not category or category not in _CATEGORY_TIERS:
        return None

    # Best move from the moves list
    best_move = None
    moves = data.get("moves", [])
    if moves:
        best_move = moves[0].get("san")

    return TablebaseResult(
        category=category,
        dtz=data.get("dtz"),
        dtm=data.get("dtm"),
        best_move=best_move,
    )


def probe_position_full(fen: str) -> dict | None:
    """Probe the Lichess tablebase API and return the complete response.

    Unlike probe_position() which returns a simplified TablebaseResult,
    this returns the raw API response including all legal moves with their
    WDL/DTM/DTZ data — suitable for storing in analysis_data.json.

    Args:
        fen: FEN string of the position.

    Returns:
        Full API response dict (category, dtm, dtz, precise_dtz, dtw, dtc,
        checkmate, stalemate, moves[]) or None if unavailable.
    """
    board = chess.Board(fen)
    if len(board.piece_map()) > MAX_PIECES:
        return None

    try:
        resp = requests.get(_API_URL, params={"fen": fen}, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None

    category = data.get("category")
    if not category or category not in _CATEGORY_TIERS:
        return None

    # Add computed tier for convenience
    data["tier"] = _CATEGORY_TIERS[category]

    return data


def tablebase_context(
    before: TablebaseResult, piece_count: int, player_color: str = "white"
) -> str:
    """Generate context string for a tablebase-resolved position.

    Args:
        before: Tablebase result for the position before the move.
        piece_count: Number of pieces on the board.
        player_color: "white" or "black".

    Returns:
        Context string shown before the player answers.
    """
    verdict = before.format_verdict()
    tier = before.tier
    color_label = f"playing as {player_color.capitalize()}"
    if tier == "WIN":
        advantage = "you had a winning position"
    elif tier == "LOSS":
        advantage = "you were in a difficult position"
    else:
        advantage = "the position was equal"
    return f"Endgame ({piece_count} pieces), {color_label}, {advantage}. Tablebase: theoretical {verdict}."


def tablebase_explanation(
    before: TablebaseResult,
    after: TablebaseResult,
    actual_san: str,
    best_san: str | None,
) -> str:
    """Generate explanation for a tablebase-detected mistake.

    Args:
        before: Tablebase result before the move.
        after: Tablebase result after the move.
        actual_san: The move the player made.
        best_san: The best move according to the tablebase.

    Returns:
        Explanation string.
    """
    verdict_before = before.format_verdict()
    verdict_after = after.format_verdict()

    parts = [f"Tablebase: the position was a theoretical {verdict_before}."]
    parts.append(f"Your move {actual_san} turns it into a {verdict_after}.")

    if best_san:
        parts.append(f"The correct move was {best_san}.")

    return " ".join(parts)
