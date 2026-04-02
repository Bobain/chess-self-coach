"""Lichess Cloud Evaluation API client.

Queries the Lichess cloud database for pre-computed Stockfish analysis.
Opening positions have near-perfect coverage at depth 50-70,
making this much faster than running Stockfish locally.

Transient errors (429, 5xx, timeouts) are retried with exponential backoff.
Only a genuine 404 (position not in database) returns None.

API: https://lichess.org/api#tag/Analysis
"""

from __future__ import annotations

import logging
import time

import requests

_log = logging.getLogger(__name__)

_URL = "https://lichess.org/api/cloud-eval"

_TIMEOUT = 10.0

# Delay between consecutive requests to avoid saturating the API.
_RATE_LIMIT_DELAY = 0.1

# Exponential backoff for transient errors (429, 5xx, network).
_BACKOFF_BASE = 2.0   # seconds — doubles each retry: 2, 4, 8, 16, 32, 64...
_BACKOFF_MAX = 120.0   # cap at 2 minutes between retries

# Timestamp of the last request, for rate limiting.
_last_request_time: float = 0.0


def query_cloud_eval(fen: str, multi_pv: int = 1) -> dict | None:
    """Query the Lichess Cloud database for a position.

    Retries indefinitely on transient errors (429, 5xx, network) with
    exponential backoff. Only returns None for a genuine cache miss (404).

    Args:
        fen: FEN string of the position to query.
        multi_pv: Number of principal variations to request.

    Returns:
        API response dict with {fen, knodes, depth, pvs[]} or None if
        the position is not in the database (404).
    """
    global _last_request_time
    params = {"fen": fen, "multiPv": multi_pv}
    attempt = 0

    while True:
        # Rate limit: wait between consecutive requests
        since_last = time.time() - _last_request_time
        if since_last < _RATE_LIMIT_DELAY:
            time.sleep(_RATE_LIMIT_DELAY - since_last)

        t0 = time.time()
        try:
            _last_request_time = time.time()
            resp = requests.get(_URL, params=params, timeout=_TIMEOUT)

            if resp.status_code == 200:
                result = resp.json()
                _log.info(
                    "    cloud %s → hit (%.0fms, depth=%s)",
                    fen[:40], (time.time() - t0) * 1000, result.get("depth"),
                )
                return result

            if resp.status_code == 404:
                _log.info(
                    "    cloud %s → miss/404 (%.0fms)",
                    fen[:40], (time.time() - t0) * 1000,
                )
                return None

            # Transient error (429, 5xx, etc.) — retry with backoff
            delay = min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_MAX)
            _log.warning(
                "    cloud %s → HTTP %d, retrying in %.0fs (attempt %d)",
                fen[:40], resp.status_code, delay, attempt + 1,
            )
            time.sleep(delay)
            attempt += 1

        except (requests.RequestException, ValueError) as exc:
            delay = min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_MAX)
            _log.warning(
                "    cloud %s → %s, retrying in %.0fs (attempt %d)",
                fen[:40], exc, delay, attempt + 1,
            )
            time.sleep(delay)
            attempt += 1
