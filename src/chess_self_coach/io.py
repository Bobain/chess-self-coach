"""Shared I/O utilities for chess-self-coach.

Atomic file writes, JSON helpers, and other filesystem operations.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def atomic_write_json(path: Path, data: dict, *, compact: bool = False) -> None:
    """Write JSON atomically: temp file, fsync, os.replace.

    Args:
        path: Target file path.
        data: Dict to serialize as JSON.
        compact: If True, write minified JSON (no indent, no spaces).
    """
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        if compact:
            json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
        else:
            json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)
