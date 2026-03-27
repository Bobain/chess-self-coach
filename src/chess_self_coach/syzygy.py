"""Syzygy endgame tablebase management.

Download, locate, and validate local Syzygy tablebases (3-5 pieces)
for use by Stockfish via the SyzygyPath UCI option.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_MIRROR = "http://tablebase.sesse.net/syzygy/3-4-5/"
_DEFAULT_DIR = Path.home() / ".local" / "share" / "syzygy"

# Search paths, checked in order
_SEARCH_PATHS = [
    _DEFAULT_DIR,
    Path("/usr/share/syzygy"),
]


def find_syzygy(config: dict | None = None) -> Path | None:
    """Find a directory containing Syzygy tablebase files.

    Args:
        config: Optional config dict. Reads config["syzygy"]["path"] first.

    Returns:
        Path to a directory with .rtbw files, or None if not found.
    """
    candidates: list[Path] = []

    if config:
        custom = config.get("syzygy", {}).get("path")
        if custom:
            candidates.append(Path(custom).expanduser())

    candidates.extend(_SEARCH_PATHS)

    for path in candidates:
        if _is_valid_syzygy_dir(path):
            return path
    return None


def _is_valid_syzygy_dir(path: Path) -> bool:
    """Check if a directory contains at least one .rtbw file.

    Args:
        path: Directory to check.

    Returns:
        True if path is a directory containing .rtbw files.
    """
    if not path.is_dir():
        return False
    return any(path.glob("*.rtbw"))


def download_syzygy(target_dir: Path | None = None) -> Path:
    """Download 3-5 piece Syzygy tablebases (~1 GB).

    Args:
        target_dir: Where to store tables. Defaults to ~/.local/share/syzygy/.

    Returns:
        Path to the download directory.

    Raises:
        FileNotFoundError: If wget is not installed.
        subprocess.CalledProcessError: If download fails.
    """
    if target_dir is None:
        target_dir = _DEFAULT_DIR

    if not shutil.which("wget"):
        raise FileNotFoundError(
            "wget is required to download Syzygy tables.\n"
            "  Install with: sudo apt install wget  (Linux) or  brew install wget  (macOS)"
        )

    target_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "wget", "-c", "-r", "-np", "-nH", "--cut-dirs=2",
            "-e", "robots=off", "-A", "*.rtbw,*.rtbz",
            "-P", str(target_dir),
            _MIRROR,
        ],
        check=True,
    )

    return target_dir


def syzygy_status(config: dict | None = None) -> dict:
    """Report status of local Syzygy tablebases.

    Args:
        config: Optional config dict for custom path lookup.

    Returns:
        Dict with path, found (bool), wdl_count, dtz_count, total_size_mb.
    """
    path = find_syzygy(config)
    if path is None:
        return {"path": None, "found": False, "wdl_count": 0, "dtz_count": 0, "total_size_mb": 0}

    wdl_files = list(path.glob("*.rtbw"))
    dtz_files = list(path.glob("*.rtbz"))
    total_bytes = sum(f.stat().st_size for f in wdl_files + dtz_files)

    return {
        "path": str(path),
        "found": True,
        "wdl_count": len(wdl_files),
        "dtz_count": len(dtz_files),
        "total_size_mb": round(total_bytes / (1024 * 1024), 1),
    }
