"""Configuration loading for chess-self-coach.

Loads config.json (Stockfish path, player usernames) and .env (Lichess token).
Every error produces a clear message with the exact command to fix it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

from dotenv import load_dotenv

# Resolve project root: walk up from cwd to find pyproject.toml,
# or fall back to cwd. Data files live under DATA_DIR.
_THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = _THIS_DIR.parent.parent  # src/chess_self_coach -> src -> root

DATA_DIR = "data"

CONFIG_FILE = "config.json"
CONFIG_EXAMPLE_FILE = "config.example.json"
ANALYSIS_DATA_FILE = "analysis_data.json"
TRAINING_DATA_FILE = "training_data.json"
FETCHED_GAMES_FILE = "fetched_games.json"
TACTIC_DATA_FILE = "tactic_data.json"

ENV_FILE = ".env"

# Default Stockfish paths (checked in order)
_SF_SEARCH_PATHS = [
    Path.home()
    / ".local/share/org.encroissant.app/engines/stockfish/stockfish-ubuntu-x86-64-avx2",
    Path("/usr/games/stockfish"),
]


def _find_project_root() -> Path:
    """Find the project root by looking for pyproject.toml, walking up from cwd."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return cwd


def data_dir() -> Path:
    """Return the data directory path.

    Returns:
        Path to the data/ directory in the project root.
    """
    return _find_project_root() / DATA_DIR


def config_path() -> Path:
    """Return the path to config.json.

    Returns:
        Path to data/config.json.
    """
    return data_dir() / CONFIG_FILE


def analysis_data_path() -> Path:
    """Return the path to analysis_data.json.

    Returns:
        Path to data/analysis_data.json.
    """
    return data_dir() / ANALYSIS_DATA_FILE


def training_data_path() -> Path:
    """Return the path to training_data.json.

    Returns:
        Path to data/training_data.json.
    """
    return data_dir() / TRAINING_DATA_FILE


def fetched_games_path() -> Path:
    """Return the path to fetched_games.json.

    Returns:
        Path to data/fetched_games.json.
    """
    return data_dir() / FETCHED_GAMES_FILE


def tactic_data_path() -> Path:
    """Return the path to tactic_data.json.

    Returns:
        Path to data/tactic_data.json.
    """
    return data_dir() / TACTIC_DATA_FILE


def error_exit(message: str, hint: str | None = None, debug_cmd: str | None = None) -> NoReturn:
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
    """Load config.json from the data directory.

    Returns:
        Parsed config dictionary.

    Raises:
        SystemExit: If config.json is missing or invalid.
    """
    cfg = config_path()

    if not cfg.exists():
        # Migration hint: detect old location at project root
        root = _find_project_root()
        old_path = root / CONFIG_FILE
        if old_path.exists():
            error_exit(
                "config.json found at old location (project root).",
                hint=f"Move it to the data directory:\n"
                f"  mkdir -p {root / DATA_DIR}\n"
                f"  mv {old_path} {cfg}",
            )
        error_exit(
            "config.json not found.",
            hint=f"Run 'chess-self-coach setup' to create it,\n"
            f"  or copy {root / DATA_DIR / CONFIG_EXAMPLE_FILE} to {cfg}",
        )

    try:
        with open(cfg) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        error_exit(
            f"config.json is not valid JSON: {e}",
            hint=f"Check the syntax in {cfg}",
        )


def save_config(config: dict[str, Any]) -> None:
    """Write config back to config.json atomically.

    Args:
        config: The config dictionary to save.
    """
    from chess_self_coach.io import atomic_write_json

    cfg = config_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(cfg, config, pretty=True)
    print(f"  Config saved to {cfg}")


def load_lichess_token(required: bool = True) -> str | None:
    """Load the Lichess API token from .env or environment.

    Args:
        required: If True, exit on missing token. If False, return None.

    Returns:
        The API token string, or None if not found and not required.

    Raises:
        SystemExit: If required=True and no token is found or it looks invalid.
    """
    root = _find_project_root()
    env_path = root / ENV_FILE

    # Load .env if it exists
    if env_path.exists():
        load_dotenv(env_path)

    token = os.environ.get("LICHESS_API_TOKEN", "").strip()

    if not token:
        if not required:
            return None
        error_exit(
            "Lichess API token not found.",
            hint=(
                "1. Create a token at: https://lichess.org/account/oauth/token/create\n"
                "  2. Save it:\n"
                f'     echo "LICHESS_API_TOKEN=lip_your_token_here" > {env_path}'
            ),
            debug_cmd='curl -H "Authorization: Bearer lip_your_token" https://lichess.org/api/account',
        )

    if not token.startswith("lip_"):
        if not required:
            return None
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
        path = sf_config.get("path", "")
        if path and path != "auto":
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
            "  - Or specify the path: chess-self-coach analyze --engine /path/to/stockfish file.pgn"
        ),
    )


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
