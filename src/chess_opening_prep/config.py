"""Configuration loading for chess-opening-prep.

Loads config.json (study mappings, Stockfish path) and .env (Lichess token).
Every error produces a clear message with the exact command to fix it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Resolve project root: walk up from this file to find config.json,
# or fall back to cwd.
_THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = _THIS_DIR.parent.parent  # src/chess_opening_prep -> src -> root

CONFIG_FILE = "config.json"
ENV_FILE = ".env"
ENV_EXAMPLE = ".env.example"

# Default Stockfish paths (checked in order)
_SF_SEARCH_PATHS = [
    Path.home()
    / ".local/share/org.encroissant.app/engines/stockfish/stockfish-ubuntu-x86-64-avx2",
    Path("/usr/games/stockfish"),
]


def _find_project_root() -> Path:
    """Find the project root by looking for config.json, walking up from cwd."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / CONFIG_FILE).exists():
            return parent
    return cwd


def error_exit(message: str, hint: str | None = None, debug_cmd: str | None = None) -> None:
    """Print a formatted error and exit.

    Args:
        message: What went wrong.
        hint: How to fix it.
        debug_cmd: A shell command the user can run to debug.
    """
    print(f"\n❌ {message}", file=sys.stderr)
    if hint:
        print(f"\n  How to fix:\n  {hint}", file=sys.stderr)
    if debug_cmd:
        print(f"\n  To debug manually:\n    {debug_cmd}", file=sys.stderr)
    print(file=sys.stderr)
    sys.exit(1)


def load_config() -> dict[str, Any]:
    """Load config.json from the project root.

    Returns:
        Parsed config dictionary.

    Raises:
        SystemExit: If config.json is missing or invalid.
    """
    root = _find_project_root()
    config_path = root / CONFIG_FILE

    if not config_path.exists():
        error_exit(
            "config.json not found.",
            hint=f"Run 'chess-opening-prep setup' to create it,\n"
            f"  or copy config.json.example to {config_path}",
        )

    try:
        with open(config_path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        error_exit(
            f"config.json is not valid JSON: {e}",
            hint=f"Check the syntax in {config_path}",
        )
    return {}  # unreachable, keeps type checker happy


def save_config(config: dict[str, Any]) -> None:
    """Write config back to config.json.

    Args:
        config: The config dictionary to save.
    """
    root = _find_project_root()
    config_path = root / CONFIG_FILE
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  Config saved to {config_path}")


def load_lichess_token() -> str:
    """Load the Lichess API token from .env or environment.

    Returns:
        The API token string.

    Raises:
        SystemExit: If no token is found or it looks invalid.
    """
    root = _find_project_root()
    env_path = root / ENV_FILE

    # Load .env if it exists
    if env_path.exists():
        load_dotenv(env_path)

    token = os.environ.get("LICHESS_API_TOKEN", "").strip()

    if not token:
        error_exit(
            "Lichess API token not found.",
            hint=(
                "1. Create a token at: https://lichess.org/account/oauth/token/create\n"
                '     - Check "Read private studies and broadcasts" (study:read)\n'
                '     - Check "Create, update, delete studies and broadcasts" (study:write)\n'
                "  2. Save it:\n"
                f'     echo "LICHESS_API_TOKEN=lip_your_token_here" > {env_path}'
            ),
            debug_cmd='curl -H "Authorization: Bearer lip_your_token" https://lichess.org/api/account',
        )

    if not token.startswith("lip_"):
        error_exit(
            f"Lichess token looks invalid (expected 'lip_...' prefix, got '{token[:8]}...').",
            hint="Regenerate your token at https://lichess.org/account/oauth/token/create",
        )

    return token


def find_stockfish(config: dict[str, Any] | None = None) -> Path:
    """Find a working Stockfish binary.

    Search order: config.json path → common install locations → system → $PATH.

    Args:
        config: Optional loaded config dict.

    Returns:
        Path to the Stockfish binary.

    Raises:
        SystemExit: If no Stockfish binary is found.
    """
    candidates: list[Path] = []

    # From config
    if config:
        sf_config = config.get("stockfish", {})
        if path := sf_config.get("path"):
            candidates.append(Path(path))
        if fallback := sf_config.get("fallback_path"):
            candidates.append(Path(fallback))

    # Default search paths
    candidates.extend(_SF_SEARCH_PATHS)

    # $PATH lookup
    sf_in_path = shutil.which("stockfish")
    if sf_in_path:
        candidates.append(Path(sf_in_path))

    # Test each candidate
    tested = []
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
        tested.append(f"  - {candidate} ({'exists' if candidate.exists() else 'not found'})")

    error_exit(
        "Stockfish not found.",
        hint=(
            "Paths tested:\n"
            + "\n".join(tested)
            + "\n\n  To fix:\n"
            "  - Install Stockfish: sudo apt install stockfish\n"
            "  - Or specify the path: chess-opening-prep analyze --engine /path/to/stockfish file.pgn"
        ),
    )
    return Path()  # unreachable


def check_stockfish_version(sf_path: Path, expected: str | None = None) -> str:
    """Check the Stockfish version and warn if it doesn't match expected.

    Args:
        sf_path: Path to the Stockfish binary.
        expected: Expected version string (e.g. "Stockfish 18").

    Returns:
        The detected version string.
    """
    try:
        result = subprocess.run(
            [str(sf_path)],
            input="uci\nquit\n",
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            if line.startswith("id name "):
                version = line[len("id name ") :]
                if expected and expected not in version:
                    print(
                        f"  ⚠ Warning: Expected {expected}, found {version}",
                        file=sys.stderr,
                    )
                return version
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"  ⚠ Warning: Could not check Stockfish version: {e}", file=sys.stderr)

    return "unknown"


def get_study_mapping(config: dict[str, Any], pgn_file: str) -> dict[str, str]:
    """Get the Lichess study mapping for a PGN file.

    Args:
        config: Loaded config dictionary.
        pgn_file: PGN filename (e.g. "repertoire_blancs_gambit_dame_annote.pgn").

    Returns:
        Dict with 'study_id' and 'study_name' keys.

    Raises:
        SystemExit: If the file has no study mapping configured.
    """
    studies = config.get("studies", {})
    mapping = studies.get(pgn_file)

    if not mapping or mapping.get("study_id", "").startswith("STUDY_ID"):
        error_exit(
            f"No Lichess study configured for '{pgn_file}'.",
            hint="Run 'chess-opening-prep setup' to configure study mappings.",
        )

    return mapping
