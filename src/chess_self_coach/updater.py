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
        return (latest != __version__), latest
    except Exception:
        return False, None


def update() -> None:
    """Update chess-self-coach to the latest version via pipx or pip."""
    if shutil.which("pipx"):
        print("Updating via pipx...")
        result = subprocess.run(
            ["pipx", "upgrade", "chess-self-coach"],
            capture_output=True,
            text=True,
        )
        print(result.stdout.strip())
        if result.returncode != 0:
            print(f"Update failed: {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Updating via pip...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "chess-self-coach"],
            check=True,
        )
    print("\n✓ Update complete!")
