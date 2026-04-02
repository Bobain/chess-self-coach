"""Local Lichess cloud evaluation database.

Downloads the full Lichess cloud eval export (369M positions, ~20 GB
compressed) and stores it in a local SQLite database for instant lookups
without API rate limits.

The database replaces calls to the Lichess cloud-eval API for positions
that have pre-computed Stockfish analysis at depth 50-70.

Export source: https://database.lichess.org/lichess_db_eval.jsonl.zst
Format: JSONL with 4-field FEN keys and nested eval arrays.
"""

from __future__ import annotations

import io
import json
import logging
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any, cast

import requests
import zstandard

_log = logging.getLogger(__name__)

_DOWNLOAD_URL = "https://database.lichess.org/lichess_db_eval.jsonl.zst"

_DEFAULT_DIR = Path.home() / ".local" / "share" / "chess-self-coach"
_DEFAULT_DB = _DEFAULT_DIR / "cloud_eval.db"

_BATCH_SIZE = 50_000

# Search paths, checked in order
_SEARCH_PATHS = [
    _DEFAULT_DB,
]

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS cloud_eval (
    fen TEXT PRIMARY KEY,
    evals TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;
"""


def _short_fen(fen: str) -> str:
    """Strip halfmove clock and fullmove counter from a FEN string.

    The Lichess cloud eval DB uses 4-field FENs (pieces, side, castling, ep).
    Standard FENs have 6 fields. This function normalises to 4 fields.

    Args:
        fen: FEN string (4 or 6 fields).

    Returns:
        4-field FEN string.
    """
    parts = fen.split()
    return " ".join(parts[:4])


def find_cloud_eval_db(config: dict[str, Any] | None = None) -> Path | None:
    """Find the local cloud eval SQLite database.

    Args:
        config: Optional config dict. Reads config["cloud_eval_db"]["path"] first.

    Returns:
        Path to the database file, or None if not found.
    """
    candidates: list[Path] = []

    if config:
        custom = config.get("cloud_eval_db", {}).get("path")
        if custom:
            candidates.append(Path(custom).expanduser())

    candidates.extend(_SEARCH_PATHS)

    for path in candidates:
        if path.is_file():
            return path
    return None


def lookup_cloud_eval(
    fen: str,
    multi_pv: int = 1,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Look up a position in the local cloud eval database.

    Translates the DB format (``line`` field) to the API format (``moves``
    field) so the result is a drop-in replacement for the API response.

    Args:
        fen: FEN string of the position (4 or 6 fields).
        multi_pv: Minimum number of principal variations required.
        config: Optional config dict for custom DB path.

    Returns:
        API-compatible dict ``{fen, depth, knodes, pvs}`` or None if
        the position is not in the database.
    """
    db_path = find_cloud_eval_db(config)
    if db_path is None:
        return None

    short = _short_fen(fen)

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT evals FROM cloud_eval WHERE fen = ?", (short,)
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        _log.warning("    cloud_eval_db: SQLite error for %s", short)
        return None

    if row is None:
        return None

    evals: list[dict[str, Any]] = json.loads(row[0])
    if not evals:
        return None

    # Select best entry: highest depth with >= multi_pv PVs
    best: dict[str, Any] | None = None
    for entry in evals:
        pvs = entry.get("pvs", [])
        if len(pvs) >= multi_pv:
            if best is None or entry.get("depth", 0) > best.get("depth", 0):
                best = entry

    # Fall back to highest-depth entry regardless of PV count
    if best is None:
        best = max(evals, key=lambda e: e.get("depth", 0))

    # Translate DB format -> API format: "line" -> "moves"
    pvs = []
    for pv in best.get("pvs", []):
        translated = dict(pv)
        if "line" in translated:
            translated["moves"] = translated.pop("line")
        pvs.append(translated)

    return {
        "fen": short,
        "depth": best.get("depth"),
        "knodes": best.get("knodes"),
        "pvs": pvs,
    }


def download_cloud_eval_db(
    target_dir: Path | None = None,
    on_progress: Callable[[int, float], None] | None = None,
) -> Path:
    """Download and import the Lichess cloud eval database.

    Streams the compressed JSONL export directly into SQLite without
    writing an intermediate file to disk.

    The import is interruptible: each batch of rows is committed, so a
    re-run resumes where it left off (INSERT OR REPLACE).

    Args:
        target_dir: Directory for the SQLite file. Defaults to
            ``/media/bobain/DATA/chess-self-coach/``.
        on_progress: Optional callback(row_count, elapsed_seconds) called
            after each batch is committed.

    Returns:
        Path to the created database file.

    Raises:
        requests.RequestException: If the download fails.
    """
    if target_dir is None:
        target_dir = _DEFAULT_DIR

    target_dir.mkdir(parents=True, exist_ok=True)
    db_path = target_dir / "cloud_eval.db"

    _log.info("Downloading cloud eval DB from %s", _DOWNLOAD_URL)
    _log.info("Target: %s", db_path)

    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA)
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA journal_mode = WAL")

    t0 = time.time()
    row_count = 0
    batch: list[tuple[str, str]] = []

    try:
        resp = requests.get(_DOWNLOAD_URL, stream=True, timeout=30)
        resp.raise_for_status()

        dctx = zstandard.ZstdDecompressor()
        reader = dctx.stream_reader(cast(IO[bytes], resp.raw))
        text_reader = io.TextIOWrapper(reader, encoding="utf-8")

        for line in text_reader:
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            fen = record.get("fen", "")
            evals = record.get("evals", [])
            if not fen or not evals:
                continue

            batch.append((fen, json.dumps(evals, separators=(",", ":"))))

            if len(batch) >= _BATCH_SIZE:
                conn.executemany(
                    "INSERT OR REPLACE INTO cloud_eval (fen, evals) VALUES (?, ?)",
                    batch,
                )
                conn.commit()
                row_count += len(batch)
                batch.clear()
                if on_progress:
                    on_progress(row_count, time.time() - t0)

        # Flush remaining rows
        if batch:
            conn.executemany(
                "INSERT OR REPLACE INTO cloud_eval (fen, evals) VALUES (?, ?)",
                batch,
            )
            conn.commit()
            row_count += len(batch)
            batch.clear()
            if on_progress:
                on_progress(row_count, time.time() - t0)

    finally:
        # Write metadata
        elapsed = time.time() - t0
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("row_count", str(row_count)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("imported_at", time.strftime("%Y-%m-%dT%H:%M:%S")),
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("import_seconds", f"{elapsed:.0f}"),
        )
        conn.commit()
        conn.execute("PRAGMA optimize")
        conn.close()

    _log.info("Import complete: %d positions in %.0fs", row_count, elapsed)
    return db_path


def cloud_eval_db_status(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Report status of the local cloud eval database.

    Args:
        config: Optional config dict for custom path lookup.

    Returns:
        Dict with path, found, row_count, size_mb.
    """
    path = find_cloud_eval_db(config)
    if path is None:
        return {"path": None, "found": False, "row_count": 0, "size_mb": 0}

    size_mb = round(path.stat().st_size / (1024 * 1024), 1)

    # Read row count from metadata if available
    row_count = 0
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT value FROM metadata WHERE key = 'row_count'"
            ).fetchone()
            if row:
                row_count = int(row[0])
        finally:
            conn.close()
    except sqlite3.Error:
        pass

    return {
        "path": str(path),
        "found": True,
        "row_count": row_count,
        "size_mb": size_mb,
    }
