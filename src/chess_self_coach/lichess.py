"""Lichess Study integration — setup, push, and pull subcommands.

Uses the berserk library (official Lichess Python client) to import/export
PGN content to/from Lichess Studies.
"""

from __future__ import annotations

import json
import re
import sys
import webbrowser
from pathlib import Path

import berserk
import requests

from chess_self_coach.config import (
    error_exit,
    load_config,
    load_lichess_token,
    save_config,
    _find_project_root,
)


def _get_client() -> berserk.Client:
    """Create an authenticated berserk client.

    Returns:
        Authenticated berserk Client.

    Raises:
        SystemExit: If auth fails.
    """
    token = load_lichess_token()
    session = berserk.TokenSession(token)
    client = berserk.Client(session=session)

    # Verify auth
    try:
        account = client.account.get()
        username = account.get("username", "unknown")
        print(f"  Authenticated as: {username}")
        return client
    except berserk.exceptions.ResponseError as e:
        error_exit(
            f"Lichess authentication failed: {e}",
            hint="Your token may be invalid or expired.\n"
            "  Regenerate at: https://lichess.org/account/oauth/token/create",
            debug_cmd=(
                "curl -s -H 'Authorization: Bearer $LICHESS_API_TOKEN' "
                "https://lichess.org/api/account | python3 -m json.tool"
            ),
        )


def _get_chapters(study_id: str, token: str) -> list[dict[str, str]]:
    """List all chapters in a study with their IDs and names.

    Parses the exported PGN headers to extract chapter metadata,
    since berserk doesn't expose a chapter listing endpoint.

    Args:
        study_id: The Lichess study ID.
        token: Lichess API token.

    Returns:
        List of dicts with 'id', 'name', and 'has_moves' keys.
    """
    resp = requests.get(
        f"https://lichess.org/api/study/{study_id}.pgn",
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code != 200:
        return []

    chapters = []
    current: dict[str, str] = {}
    has_moves = False

    for line in resp.text.splitlines():
        if line.startswith('[ChapterName "'):
            current["name"] = line.split('"')[1]
        elif line.startswith("[ChapterURL "):
            match = re.search(r"/study/\w+/(\w+)", line)
            if match:
                current["id"] = match.group(1)
        elif line.strip() and not line.startswith("[") and line.strip() != "*":
            has_moves = True
        elif line == "" and current.get("id"):
            current["has_moves"] = str(has_moves)
            chapters.append(current)
            current = {}
            has_moves = False

    # Flush last chapter
    if current.get("id"):
        current["has_moves"] = str(has_moves)
        chapters.append(current)

    return chapters


def _delete_chapter(study_id: str, chapter_id: str, token: str) -> bool:
    """Delete a chapter from a Lichess study.

    Args:
        study_id: The Lichess study ID.
        chapter_id: The chapter ID to delete.
        token: Lichess API token.

    Returns:
        True if deletion succeeded (HTTP 204), False otherwise.
    """
    resp = requests.delete(
        f"https://lichess.org/api/study/{study_id}/{chapter_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.status_code == 204


def cleanup_study(study_id: str, study_name: str = "") -> int:
    """Remove empty default chapters (e.g. 'Chapter 1') from a study.

    Lichess auto-creates an empty 'Chapter 1' when a study is created.
    After importing PGN, this leaves a stale empty chapter. This function
    detects and removes such chapters.

    Args:
        study_id: The Lichess study ID.
        study_name: Display name for logging.

    Returns:
        Number of chapters deleted.
    """
    token = load_lichess_token()
    chapters = _get_chapters(study_id, token)

    deleted = 0
    for ch in chapters:
        name = ch.get("name", "")
        has_moves = ch.get("has_moves") == "True"

        # Delete chapters that look like Lichess defaults: named "Chapter N" with no moves
        if re.match(r"^Chapter \d+$", name) and not has_moves:
            if _delete_chapter(study_id, ch["id"], token):
                label = study_name or study_id
                print(f"  🗑 Deleted empty chapter '{name}' from {label}")
                deleted += 1

    return deleted


_TOKEN_GUIDE_FR = """
    Guide de creation du token Lichess :

    1. Ouvrez : https://lichess.org/account/oauth/token/create
       (si vous n'avez pas de compte, creez-en un d'abord sur lichess.org)

    2. Donnez un nom au token, par exemple : "chess-self-coach"

    3. Cochez les permissions suivantes :
       [ ] Lire les etudes privees (study:read)
       [ ] Creer/modifier/supprimer les etudes (study:write)

    4. Cliquez sur "Soumettre"

    5. IMPORTANT : copiez le token (il commence par "lip_")
       Il ne sera plus visible apres !
"""

_TOKEN_GUIDE_EN = """
    Lichess token creation guide:

    1. Open: https://lichess.org/account/oauth/token/create
       (if you don't have an account, create one first at lichess.org)

    2. Give the token a name, e.g.: "chess-self-coach"

    3. Check these permissions:
       [ ] Read private studies and broadcasts (study:read)
       [ ] Create, update, delete studies and broadcasts (study:write)

    4. Click "Submit"

    5. IMPORTANT: copy the token (starts with "lip_")
       It won't be shown again!
"""


def _guided_token_creation() -> str | None:
    """Guide the user through Lichess token creation with bilingual instructions.

    Returns:
        The token string, or None if the user cancels.
    """
    print("\n    Choose language / Choisissez la langue :")
    print("      1. Francais")
    print("      2. English")
    lang = input("    > ").strip()

    if lang == "1":
        print(_TOKEN_GUIDE_FR)
        prompt = "    6. Collez le token ici (ou Entree pour annuler) : "
    else:
        print(_TOKEN_GUIDE_EN)
        prompt = "    6. Paste the token here (or Enter to cancel): "

    try:
        webbrowser.open("https://lichess.org/account/oauth/token/create")
    except Exception:
        pass

    token = input(prompt).strip()
    if not token:
        return None

    if not token.startswith("lip_"):
        print("    ✗ Token should start with 'lip_'. Please try again.")
        return None

    # Save to .env
    root = _find_project_root()
    env_path = root / ".env"
    env_path.write_text(f"LICHESS_API_TOKEN={token}\n")
    print(f"    ✓ Token saved to {env_path}")

    return token


def setup() -> None:
    """Interactive setup: verify auth, find studies, configure config.json.

    Guides the user through connecting their Lichess account and mapping
    PGN files to Lichess Studies.
    """
    print("\n🔧 chess-self-coach setup\n")

    # Step 1: Check Stockfish
    print("Step 1: Checking Stockfish...")
    from chess_self_coach.config import find_stockfish, check_stockfish_version

    try:
        config = load_config()
    except SystemExit:
        config = {
            "stockfish": {
                "path": str(
                    Path.home()
                    / ".local/share/org.encroissant.app/engines/stockfish"
                    / "stockfish-ubuntu-x86-64-avx2"
                ),
                "expected_version": "Stockfish 18",
                "fallback_path": "/usr/games/stockfish",
            },
            "analysis": {"default_depth": 18, "blunder_threshold": 1.0},
            "studies": {},
        }

    sf_path = find_stockfish(config)
    version = check_stockfish_version(sf_path, config.get("stockfish", {}).get("expected_version"))
    print(f"  Found {version} at {sf_path}")

    # Step 2: Game platforms (at least one required)
    print("\nStep 2: Game platforms (at least one required)")
    players = config.get("players", {})
    username = None
    client = None

    # Lichess (optional)
    print("\n  Lichess:")
    token = load_lichess_token(required=False)
    if token:
        try:
            client = _get_client()
            account = client.account.get()
            username = account["username"]
            players["lichess"] = username
            print(f"    ✓ Token verified: {username}")
        except Exception as e:
            print(f"    ✗ Token invalid: {e}")
            players.pop("lichess", None)
    else:
        print("\n    With a Lichess account, you unlock:")
        print("      ★ Perfect endgame analysis — Lichess tablebase gives mathematically")
        print("        exact results (Win/Draw/Loss) for positions with ≤ 7 pieces")
        print("      ★ Sync your repertoire to Lichess Studies (push/pull)")
        print("      ★ Study interactively on Lichess with built-in Stockfish")
        print("      ★ Drill with Chessdriller (spaced repetition from your Studies)")
        setup_token = input("\n    Would you like to set up a Lichess token? [y/N] ").strip().lower()
        if setup_token == "y":
            token = _guided_token_creation()
            if token:
                try:
                    session = berserk.TokenSession(token)
                    client = berserk.Client(session=session)
                    account = client.account.get()
                    username = account["username"]
                    players["lichess"] = username
                    print(f"\n    ✓ Token verified: {username}")
                except Exception as e:
                    print(f"\n    ✗ Token invalid: {e}")
                    players.pop("lichess", None)
                    client = None
            else:
                players.pop("lichess", None)
        else:
            players.pop("lichess", None)

    # Chess.com (optional)
    print("\n  Chess.com:")
    current_chesscom = players.get("chesscom", "")
    if current_chesscom:
        print(f"    Currently configured: {current_chesscom}")
        change = input("    Change it? [y/N] ").strip().lower()
        if change == "y":
            current_chesscom = ""
    if not current_chesscom:
        chesscom_input = input("    Enter your chess.com username (optional, press Enter to skip): ").strip()
        if chesscom_input:
            players["chesscom"] = chesscom_input
            current_chesscom = chesscom_input
            print(f"    ✓ Chess.com: {chesscom_input}")
        else:
            players.pop("chesscom", None)
            current_chesscom = ""

    # Validate: at least one platform
    lichess_user = players.get("lichess", "")
    chesscom_user = players.get("chesscom", "")
    if not lichess_user and not chesscom_user:
        print("\n  ✗ Error: at least one platform (Lichess or chess.com) is required.")
        print("    - For Lichess: create a token at https://lichess.org/account/oauth/token/create")
        print('    - Then: echo "LICHESS_API_TOKEN=lip_..." > .env')
        print("    - For chess.com: re-run setup and enter your username")
        sys.exit(1)

    # Summary
    platforms = []
    if lichess_user:
        platforms.append(f"Lichess ({lichess_user})")
    if chesscom_user:
        platforms.append(f"chess.com ({chesscom_user})")
    print(f"\n  ✓ Configured: {' + '.join(platforms)}")

    config["players"] = players

    # Step 3: Lichess Studies (only if Lichess is configured)
    if client and username:
        print("\nStep 3: Looking for existing Lichess studies...")

        studies = []
        try:
            resp = requests.get(
                f"https://lichess.org/api/study/by/{username}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/x-ndjson"},
                stream=True,
            )
            if resp.status_code == 200:
                for line in resp.iter_lines():
                    if line:
                        studies.append(json.loads(line))
        except Exception:
            studies = []

        expected_studies = {
            "repertoire_blancs_gambit_dame_annote.pgn": "Whites - Queen's Gambit",
            "repertoire_noirs_vs_e4_scandinave_annote.pgn": "Black vs e4 - Scandinavian",
            "repertoire_noirs_vs_d4_slave_annote.pgn": "Black vs d4 - Slav",
        }

        studies_config = config.get("studies", {})

        if studies:
            print(f"  Found {len(studies)} study/studies on your account:")
            for study in studies:
                study_name = study.get("name", "Unnamed")
                study_id = study.get("id", "???")
                print(f"    - {study_name} (id: {study_id})")

            for pgn_file, expected_name in expected_studies.items():
                if pgn_file in studies_config and not studies_config[pgn_file].get(
                    "study_id", ""
                ).startswith("STUDY_ID"):
                    print(f"  ✓ {pgn_file} already configured")
                    continue

                matched = None
                for study in studies:
                    study_name = study.get("name", "")
                    if expected_name.lower() in study_name.lower():
                        matched = study
                        break

                if matched:
                    studies_config[pgn_file] = {
                        "study_id": matched["id"],
                        "study_name": matched["name"],
                    }
                    print(f"  ✓ Auto-matched {pgn_file} → {matched['name']} ({matched['id']})")
                else:
                    studies_config[pgn_file] = {
                        "study_id": "STUDY_ID_HERE",
                        "study_name": expected_name,
                    }
                    print(f"  ✗ No match for {pgn_file} (expected: '{expected_name}')")
        else:
            print("  No studies found on your account.")
            for pgn_file, expected_name in expected_studies.items():
                studies_config[pgn_file] = {
                    "study_id": "STUDY_ID_HERE",
                    "study_name": expected_name,
                }

        config["studies"] = studies_config

        missing = [
            (pgn, info["study_name"])
            for pgn, info in studies_config.items()
            if info.get("study_id", "").startswith("STUDY_ID")
        ]

        if missing:
            print(f"\n  {len(missing)} study/studies need to be created on Lichess:")
            for pgn, name in missing:
                print(f"    - {name} (for {pgn})")
            print("\n  Opening Lichess study page in your browser...")
            try:
                webbrowser.open("https://lichess.org/study")
            except Exception:
                print("  Could not open browser. Go to: https://lichess.org/study")
            print(
                "\n  After creating the studies, run 'chess-self-coach setup' again\n"
                "  to auto-detect them, or edit config.json manually."
            )
        else:
            print("\n  ✓ All studies configured!")
    else:
        print("\nStep 3: Lichess Studies (skipped — no Lichess account)")

    save_config(config)
    print("\n✓ Setup complete.\n")


def _clear_study(study_id: str, token: str) -> int:
    """Delete ALL chapters from a study, leaving it empty for a fresh import.

    Lichess requires at least one chapter, but we'll immediately import new ones
    after clearing. We delete all except the last one, import, then delete that one.

    Args:
        study_id: The Lichess study ID.
        token: Lichess API token.

    Returns:
        Number of chapters deleted.
    """
    chapters = _get_chapters(study_id, token)
    if not chapters:
        return 0

    # Delete all chapters except the last (Lichess requires at least 1)
    deleted = 0
    for ch in chapters[:-1]:
        if _delete_chapter(study_id, ch["id"], token):
            deleted += 1

    return deleted


def push_pgn(pgn_path: str | Path, *, replace: bool = True) -> None:
    """Push a local PGN file to its mapped Lichess study.

    By default, replaces all existing chapters (deletes old, imports new).
    Use --no-replace to append without deleting.

    Args:
        pgn_path: Path to the PGN file.
        replace: If True (default), delete existing chapters before importing.
    """
    pgn_path = Path(pgn_path)
    if not pgn_path.exists():
        print(f"❌ File not found: {pgn_path}", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    from chess_self_coach.config import get_study_mapping

    mapping = get_study_mapping(config, pgn_path.name)
    study_id = mapping["study_id"]
    study_name = mapping.get("study_name", study_id)

    client = _get_client()
    token = load_lichess_token()

    pgn_content = pgn_path.read_text()

    print(f"\n  Pushing {pgn_path.name} → Lichess study '{study_name}'...")

    # Step 1: Clear existing chapters (keep last one as placeholder)
    if replace:
        chapters_before = _get_chapters(study_id, token)
        if chapters_before:
            last_chapter_id = chapters_before[-1]["id"]
            cleared = _clear_study(study_id, token)
            if cleared:
                print(f"  Cleared {cleared} old chapter(s)")
        else:
            last_chapter_id = None
    else:
        last_chapter_id = None

    # Step 2: Import new PGN
    try:
        result = client.studies.import_pgn(
            study_id, study_name, pgn_content
        )
        print(f"\n  ✓ Import successful!")
        print(f"  Study URL: https://lichess.org/study/{study_id}")
        if isinstance(result, list):
            print(f"  Chapters imported: {len(result)}")
            for chapter in result:
                name = chapter.get("name", "Unnamed")
                print(f"    - {name}")
    except berserk.exceptions.ResponseError as e:
        error_exit(
            f"Failed to import PGN to Lichess: {e}",
            hint=f"Check that study '{study_name}' (id: {study_id}) exists\n"
            f"  and your token has study:write scope.",
        )

    # Step 3: Delete the leftover placeholder chapter from step 1
    if replace and last_chapter_id:
        if _delete_chapter(study_id, last_chapter_id, token):
            print(f"  Cleaned up placeholder chapter")

    # Also clean up any empty default chapters (e.g. "Chapter 1")
    cleanup_study(study_id, study_name)


def pull_pgn(pgn_path: str | Path, *, in_place: bool = False) -> None:
    """Pull the latest PGN from a Lichess study to a local file.

    Args:
        pgn_path: Path to the PGN file (used to look up the study mapping).
        in_place: If True, overwrite the file. Otherwise write to *_from_lichess.pgn.
    """
    pgn_path = Path(pgn_path)
    config = load_config()
    from chess_self_coach.config import get_study_mapping

    mapping = get_study_mapping(config, pgn_path.name)
    study_id = mapping["study_id"]
    study_name = mapping.get("study_name", study_id)

    client = _get_client()

    print(f"\n  Pulling Lichess study '{study_name}' → local...")

    try:
        pgn_data = client.studies.export(study_id)

        # berserk returns a generator of strings for study export
        if hasattr(pgn_data, "__iter__") and not isinstance(pgn_data, str):
            pgn_text = "\n".join(pgn_data)
        else:
            pgn_text = str(pgn_data)

        if in_place:
            output_path = pgn_path
        else:
            output_path = pgn_path.with_name(
                pgn_path.stem + "_from_lichess" + pgn_path.suffix
            )

        output_path.write_text(pgn_text)

        # Count chapters (games)
        chapter_count = pgn_text.count('[Event "')
        print(f"  ✓ Downloaded {chapter_count} chapter(s)")
        print(f"  Output: {output_path}")

    except berserk.exceptions.ResponseError as e:
        error_exit(
            f"Failed to export study from Lichess: {e}",
            hint=f"Check that study '{study_name}' (id: {study_id}) exists\n"
            f"  and your token has study:read scope.",
        )
