"""Lichess Cloud Eval API client.

Queries the Lichess cloud evaluation database for pre-computed Stockfish
evaluations. Opening positions have near-perfect coverage at depth 50-70,
making this much faster than running Stockfish locally.

API: https://lichess.org/api#tag/Analysis
"""

from __future__ import annotations

import logging
import time

import requests

_log = logging.getLogger(__name__)

_URL = "https://lichess.org/api/cloud-eval"

_TIMEOUT = 10.0

_RATE_LIMIT_DELAY = 0.1


def query_cloud_eval(fen: str, multi_pv: int = 1) -> dict | None:
    """Query the Lichess Cloud Eval for a position.

    Args:
        fen: FEN string of the position to query.
        multi_pv: Number of principal variations to request.

    Returns:
        API response dict with {fen, knodes, depth, pvs[]} or None if
        the position is not in the database or the API is unavailable.
    """
    params = {"fen": fen, "multiPv": multi_pv}
    t0 = time.time()

    try:
        resp = requests.get(_URL, params=params, timeout=_TIMEOUT)
        if resp.status_code == 200:
            result = resp.json()
            _log.info(
                "    cloud_eval %s → hit (%.0fms, depth=%s)",
                fen[:40], (time.time() - t0) * 1000, result.get("depth"),
            )
            return result
        if resp.status_code == 429:
            time.sleep(1.0)
            resp = requests.get(_URL, params=params, timeout=_TIMEOUT)
            if resp.status_code == 200:
                result = resp.json()
                _log.info(
                    "    cloud_eval %s → hit after 429 retry (%.0fms, depth=%s)",
                    fen[:40], (time.time() - t0) * 1000, result.get("depth"),
                )
                return result
    except (requests.RequestException, ValueError):
        pass

    _log.info(
        "    cloud_eval %s → miss (%.0fms)",
        fen[:40], (time.time() - t0) * 1000,
    )
    return None
