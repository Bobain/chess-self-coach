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
from collections.abc import Callable
from typing import Any

import requests

_log = logging.getLogger(__name__)

_URL = "https://lichess.org/api/cloud-eval"

_TIMEOUT = 10.0

# Delay between consecutive requests to avoid saturating the API.
# Lichess cloud-eval is meant for "a few positions here and there", not batch use.
_RATE_LIMIT_DELAY = 1.0

# Exponential backoff for transient errors (429, 5xx, network).
_BACKOFF_BASE = 60.0   # seconds — Lichess recommends ≥1 min wait after 429
_BACKOFF_MAX = 7680.0  # 128 minutes — raise error if still failing after this

# Timestamp of the last request, for rate limiting.
_last_request_time: float = 0.0


class RateLimitExhaustedError(Exception):
    """Raised when the API rate limit persists after maximum backoff (128 min)."""


def query_cloud_eval(
    fen: str,
    multi_pv: int = 1,
    on_wait: Callable[[int, float], None] | None = None,
    log_label: str = "",
) -> dict[str, Any] | None:
    """Query the Lichess Cloud database for a position.

    Retries on transient errors (429, 5xx, network) with exponential backoff
    up to 128 minutes. Raises RateLimitExhaustedError if still failing after
    a retry at max backoff. Only returns None for a genuine cache miss (404).

    Args:
        fen: FEN string of the position to query.
        multi_pv: Number of principal variations to request.
        on_wait: Optional callback(attempt, delay_seconds) called before
            each retry sleep, so callers can surface the wait to the UI.
        log_label: Optional prefix for log messages (e.g. "[ply 12 after] ")
            to identify which step triggered the query.

    Returns:
        API response dict with {fen, knodes, depth, pvs[]} or None if
        the position is not in the database (404).

    Raises:
        RateLimitExhaustedError: If rate limit persists after max backoff.
    """
    global _last_request_time
    params = {"fen": fen, "multiPv": multi_pv}
    attempt = 0
    at_max_count = 0

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
                    "    cloud %s%s → hit (%.0fms, depth=%s)",
                    log_label, fen[:40], (time.time() - t0) * 1000,
                    result.get("depth"),
                )
                return result

            if resp.status_code == 404:
                _log.info(
                    "    cloud %s%s → miss/404 (%.0fms)",
                    log_label, fen[:40], (time.time() - t0) * 1000,
                )
                return None

            # Transient error (429, 5xx, etc.) — retry with backoff
            delay = min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_MAX)
            if delay >= _BACKOFF_MAX:
                at_max_count += 1
                if at_max_count > 1:
                    msg = f"Cloud eval rate limit exhausted after {attempt + 1} retries (fen={fen[:40]})"
                    _log.error("    %s", msg)
                    raise RateLimitExhaustedError(msg)
            retry_after = resp.headers.get("Retry-After", "?")
            _log.warning(
                "    cloud %s%s → HTTP %d (Retry-After: %s), retrying in %.0fs (attempt %d)",
                log_label, fen[:40], resp.status_code, retry_after, delay,
                attempt + 1,
            )
            if on_wait:
                on_wait(attempt + 1, delay)
            time.sleep(delay)
            attempt += 1

        except (requests.RequestException, ValueError) as exc:
            delay = min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_MAX)
            if delay >= _BACKOFF_MAX:
                at_max_count += 1
                if at_max_count > 1:
                    msg = f"Cloud eval rate limit exhausted after {attempt + 1} retries (fen={fen[:40]})"
                    _log.error("    %s", msg)
                    raise RateLimitExhaustedError(msg) from exc
            _log.warning(
                "    cloud %s%s → %s, retrying in %.0fs (attempt %d)",
                log_label, fen[:40], exc, delay, attempt + 1,
            )
            if on_wait:
                on_wait(attempt + 1, delay)
            time.sleep(delay)
            attempt += 1
