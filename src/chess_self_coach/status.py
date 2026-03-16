"""Status overview of the chess opening repertoire.

Shows local file status, Stockfish availability, and Lichess study configuration.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import chess.pgn

from chess_self_coach.config import (
    _find_project_root,
    check_stockfish_version,
    find_stockfish,
    load_config,
)


def _count_chapters(pgn_path: Path) -> int:
    """Count the number of games (chapters) in a PGN file.

    Args:
        pgn_path: Path to the PGN file.

    Returns:
        Number of games found.
    """
    count = 0
    try:
        with open(pgn_path) as f:
            while chess.pgn.read_game(f) is not None:
                count += 1
    except Exception:
        pass
    return count


def _format_timestamp(path: Path) -> str:
    """Format the last modification time of a file.

    Args:
        path: Path to the file.

    Returns:
        Human-readable timestamp or "missing".
    """
    if not path.exists():
        return "missing"
    mtime = os.path.getmtime(path)
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


def show_status() -> None:
    """Display the current status of all repertoire files and integrations."""
    print("\n📊 chess-self-coach status\n")

    root = _find_project_root()
    pgn_dir = root / "pgn"

    # Load config
    try:
        config = load_config()
    except SystemExit:
        print("  ❌ config.json not found. Run 'chess-self-coach setup' first.\n")
        return

    # Stockfish check
    print("Stockfish:")
    try:
        sf_path = find_stockfish(config)
        expected = config.get("stockfish", {}).get("expected_version")
        version = check_stockfish_version(sf_path, expected)
        print(f"  ✓ {version} at {sf_path}")
    except SystemExit:
        print("  ❌ Not found (run 'chess-self-coach setup')")

    # Lichess token check
    print("\nLichess token:")
    token = os.environ.get("LICHESS_API_TOKEN", "")
    if not token:
        from dotenv import load_dotenv
        env_path = root / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            token = os.environ.get("LICHESS_API_TOKEN", "")

    if token:
        print(f"  ✓ Found (lip_...{token[-4:]})")
    else:
        print("  ❌ Not configured (see .env.example)")

    # PGN files status
    print("\nPGN files:")
    studies = config.get("studies", {})

    header = f"  {'File':<50} {'Modified':<18} {'Chapters':>8}  {'Study'}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for pgn_file, study_info in studies.items():
        pgn_path = pgn_dir / pgn_file
        modified = _format_timestamp(pgn_path)
        chapters = _count_chapters(pgn_path) if pgn_path.exists() else 0
        study_id = study_info.get("study_id", "")

        if study_id.startswith("STUDY_ID"):
            study_display = "⚠ NOT CONFIGURED"
        else:
            study_display = f"✓ {study_id}"

        print(f"  {pgn_file:<50} {modified:<18} {chapters:>8}  {study_display}")

    # Suggestions
    print("\nSuggested actions:")
    suggestions = []

    if not token:
        suggestions.append("  - Create a Lichess token: chess-self-coach setup")

    for pgn_file, study_info in studies.items():
        study_id = study_info.get("study_id", "")
        if study_id.startswith("STUDY_ID"):
            suggestions.append(f"  - Configure study for {pgn_file}: chess-self-coach setup")
            break

    for pgn_file in studies:
        pgn_path = pgn_dir / pgn_file
        if pgn_path.exists():
            # Check if file has unannotated positions
            with open(pgn_path) as f:
                content = f.read()
            if "[%eval" not in content:
                suggestions.append(
                    f"  - Analyze {pgn_file}: chess-self-coach analyze pgn/{pgn_file}"
                )

    if not suggestions:
        suggestions.append("  ✓ Everything looks good!")

    for s in suggestions:
        print(s)

    print()
