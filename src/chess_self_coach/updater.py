"""Self-update mechanism for chess-self-coach."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.request


def check_update() -> tuple[bool, str | None]:
    """Check PyPI for a newer version.

    Returns:
        Tuple of (update_available, latest_version). On network error,
        returns (False, None) — never crashes.
    """
    from chess_self_coach import __version__

    try:
        resp = urllib.request.urlopen(
            "https://pypi.org/pypi/chess-self-coach/json", timeout=3,
        )
        data = json.loads(resp.read())
        latest = data["info"]["version"]
        # Compare as tuples to detect only newer versions
        def _parse_ver(v: str) -> tuple[int, ...]:
            return tuple(int(x) for x in v.split("."))
        return (_parse_ver(latest) > _parse_ver(__version__)), latest
    except Exception:
        return False, None


def check_stockfish_update() -> tuple[bool, str | None, str | None]:
    """Check GitHub for a newer Stockfish release.

    Compares the locally installed Stockfish version against the latest
    GitHub release of official-stockfish/Stockfish.

    Returns:
        Tuple of (update_available, installed_version, latest_version).
        On any error, returns (False, None, None) — never crashes.
    """
    from chess_self_coach.config import find_stockfish, check_stockfish_version

    try:
        sf_path = find_stockfish()
    except SystemExit:
        return False, None, None

    installed = check_stockfish_version(sf_path)
    # installed is like "Stockfish 18" or "Stockfish 17"
    installed_num = installed.replace("Stockfish", "").strip()

    try:
        resp = urllib.request.urlopen(
            "https://api.github.com/repos/official-stockfish/Stockfish/releases/latest",
            timeout=3,
        )
        data = json.loads(resp.read())
        tag = data.get("tag_name", "")
        # Tags are like "sf_17", "sf_18", or "stockfish-18"
        latest_num = tag.replace("sf_", "").replace("stockfish-", "").strip()
        if not latest_num or not installed_num:
            return False, installed, None
        return latest_num > installed_num, installed, f"Stockfish {latest_num}"
    except Exception:
        return False, installed, None


def _get_installed_version() -> str:
    """Get the currently installed version after update."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", "from chess_self_coach import __version__; print(__version__)"],
            capture_output=True, text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def update() -> None:
    """Update chess-self-coach to the latest version via uv, pipx, or pip."""
    tools = [
        ("uv", ["uv", "tool", "upgrade", "chess-self-coach"]),
        ("pipx", ["pipx", "upgrade", "chess-self-coach"]),
        ("pip", [sys.executable, "-m", "pip", "install", "--upgrade", "chess-self-coach"]),
    ]
    for name, cmd in tools:
        if not shutil.which(cmd[0]):
            continue
        print(f"Updating via {name}...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            installed = _get_installed_version()
            print(f"\n✓ Updated to v{installed}!")
            return
        # Tool found but failed — try next one
        print(f"{name} failed, trying next method...")

    print("Update failed: no working package manager found.", file=sys.stderr)
    sys.exit(1)
