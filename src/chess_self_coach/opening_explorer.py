"""Lichess Opening Explorer API client.

Queries the Lichess opening explorer to identify opening names, ECO codes,
and move popularity statistics for each position. Used during Phase 1 analysis
to detect when players depart from known theory.

API: https://explorer.lichess.ovh/lichess (requires Lichess auth token)
"""

from __future__ import annotations

import time

import requests

# Primary and fallback API endpoints
_PRIMARY_URL = "https://explorer.lichess.ovh/lichess"
_FALLBACK_URL = "https://explorer.lichess.org/lichess"

# Request timeout (seconds)
_TIMEOUT = 10.0

# Delay between requests to respect rate limits (seconds)
_RATE_LIMIT_DELAY = 0.1


def query_opening(fen: str, token: str) -> dict | None:
    """Query the Lichess Opening Explorer for a position.

    Returns the full API response including opening name/ECO, game counts,
    and all continuations with popularity statistics.

    Args:
        fen: FEN string of the position to query.
        token: Lichess API personal access token.

    Returns:
        Dict with {opening, white, draws, black, moves[]} or None if
        the API is unavailable or the position is not in the database.
    """
    headers = {"Authorization": f"Bearer {token}"}
    params = {"variant": "standard", "fen": fen}

    for url in (_PRIMARY_URL, _FALLBACK_URL):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                # Position with zero games is "not in the database"
                total = data.get("white", 0) + data.get("draws", 0) + data.get("black", 0)
                if total == 0:
                    return None
                return data
            if resp.status_code == 429:
                # Rate limited — wait and retry once on the same URL
                time.sleep(1.0)
                resp = requests.get(url, params=params, headers=headers, timeout=_TIMEOUT)
                if resp.status_code == 200:
                    data = resp.json()
                    total = data.get("white", 0) + data.get("draws", 0) + data.get("black", 0)
                    if total == 0:
                        return None
                    return data
        except (requests.RequestException, ValueError):
            continue

    return None


def query_opening_sequence(
    fens_and_moves: list[tuple[str, str]],
    token: str,
) -> list[dict | None]:
    """Query the Opening Explorer for a sequence of positions until theory departure.

    Stops querying as soon as the move actually played is not found in the
    explorer's move list (= departure from known theory). Returns None for
    all subsequent positions.

    Args:
        fens_and_moves: List of (fen_before, move_uci) tuples for each ply.
        token: Lichess API personal access token.

    Returns:
        List of explorer responses (same length as input). None entries mean
        the position was past theory departure or the API was unavailable.
    """
    results: list[dict | None] = []
    departed = False

    for fen, move_uci in fens_and_moves:
        if departed:
            results.append(None)
            continue

        data = query_opening(fen, token)
        if data is None:
            # Position not in database — this IS the departure point
            departed = True
            results.append(None)
            continue

        results.append(data)

        # Check if the move played is in the explorer's move list
        known_moves = {m["uci"] for m in data.get("moves", [])}
        if move_uci not in known_moves:
            departed = True

        time.sleep(_RATE_LIMIT_DELAY)

    return results
