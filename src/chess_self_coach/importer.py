"""Game import and deviation analysis.

Fetches games from Lichess and chess.com, compares them against the
local repertoire PGN files, and reports where players deviated.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import berserk
import chess
import chess.pgn

from chess_self_coach.config import (
    _find_project_root,
    error_exit,
    load_config,
    load_lichess_token,
)


def find_deviation(game_moves: list[str], repertoire_moves: list[str]) -> int | None:
    """Compare a game's moves against repertoire, return the index where they diverge.

    Args:
        game_moves: List of SAN move strings from the played game.
        repertoire_moves: List of SAN move strings from the repertoire line.

    Returns:
        The index of the first differing move, or None if the game doesn't
        match the opening at all (first move different).
    """
    if not game_moves or not repertoire_moves:
        return None

    # If the very first move differs, this repertoire line doesn't apply
    if game_moves[0] != repertoire_moves[0]:
        return None

    min_len = min(len(game_moves), len(repertoire_moves))
    for i in range(min_len):
        if game_moves[i] != repertoire_moves[i]:
            return i

    # Game followed repertoire for all overlapping moves
    # If game is longer, deviation is at the end of repertoire
    if len(game_moves) > len(repertoire_moves):
        return len(repertoire_moves)

    # Game is same length or shorter — no deviation within repertoire scope
    return None


def _extract_mainline_sans(game: chess.pgn.Game) -> list[str]:
    """Extract mainline moves as SAN strings from a parsed game.

    Args:
        game: Parsed PGN game.

    Returns:
        List of SAN move strings.
    """
    moves = []
    node = game
    while node.variations:
        next_node = node.variations[0]
        if next_node.move:
            moves.append(node.board().san(next_node.move))
        node = next_node
    return moves


def _extract_all_lines(game: chess.pgn.Game) -> list[list[str]]:
    """Extract all lines (mainline + variations) as lists of SAN strings.

    Args:
        game: Parsed PGN game.

    Returns:
        List of move-string lists, one per line through the game tree.
    """
    lines: list[list[str]] = []

    def _walk(node: chess.pgn.GameNode, moves_so_far: list[str]) -> None:
        if not node.variations:
            if moves_so_far:
                lines.append(list(moves_so_far))
            return
        for variation in node.variations:
            san = node.board().san(variation.move)
            _walk(variation, moves_so_far + [san])

    _walk(game, [])
    return lines


def match_game_to_repertoire(
    game: chess.pgn.Game,
    repertoire_games: list[chess.pgn.Game],
) -> tuple[chess.pgn.Game | None, int | None]:
    """Find which repertoire chapter matches this game, and where it diverges.

    Tries all lines (mainline + variations) in each repertoire chapter.
    Returns the chapter with the longest matching prefix and the deviation point.

    Args:
        game: A played game.
        repertoire_games: List of parsed repertoire games (chapters).

    Returns:
        (matching_repertoire_game, deviation_index) or (None, None).
    """
    game_moves = _extract_mainline_sans(game)
    if not game_moves:
        return None, None

    best_match: chess.pgn.Game | None = None
    best_deviation: int | None = None
    best_match_length = 0

    for rep_game in repertoire_games:
        rep_lines = _extract_all_lines(rep_game)
        for rep_moves in rep_lines:
            dev = find_deviation(game_moves, rep_moves)

            if dev is None and game_moves[0] == rep_moves[0]:
                # Game follows this line completely — check match length
                match_len = min(len(game_moves), len(rep_moves))
                if match_len > best_match_length:
                    best_match_length = match_len
                    best_match = rep_game
                    best_deviation = None
            elif dev is not None and dev > best_match_length:
                best_match_length = dev
                best_match = rep_game
                best_deviation = dev

    return best_match, best_deviation


def fetch_lichess_games(username: str, max_games: int = 100) -> list[chess.pgn.Game]:
    """Fetch rated rapid+ games from Lichess.

    Args:
        username: Lichess username.
        max_games: Maximum number of games to fetch.

    Returns:
        List of parsed chess.pgn.Game objects.

    Raises:
        SystemExit: If fetching fails.
    """
    token = load_lichess_token()
    session = berserk.TokenSession(token)
    client = berserk.Client(session=session)

    games = []
    try:
        exported = client.games.export_by_player(
            username,
            max=max_games,
            rated=True,
            perf_type="rapid,classical,correspondence",
            as_pgn=True,
        )

        pgn_text = "".join(exported) if hasattr(exported, "__iter__") else str(exported)
        pgn_io = io.StringIO(pgn_text)

        while True:
            game = chess.pgn.read_game(pgn_io)
            if game is None:
                break
            games.append(game)

        print(f"  Fetched {len(games)} game(s) from Lichess for {username}")
    except berserk.exceptions.ResponseError as e:
        error_exit(
            f"Failed to fetch Lichess games: {e}",
            hint=f"Check that username '{username}' exists on Lichess.",
        )

    return games


def fetch_chesscom_games(username: str, max_games: int = 100) -> list[chess.pgn.Game]:
    """Fetch rated rapid+ games from chess.com public API.

    Uses the chessdotcom package (installed as chess.com) to access
    the chess.com public API.

    Args:
        username: Chess.com username.
        max_games: Maximum number of games to fetch.

    Returns:
        List of parsed chess.pgn.Game objects.

    Raises:
        SystemExit: If fetching fails.
    """
    try:
        from chessdotcom import get_player_game_archives
    except ImportError:
        error_exit(
            "chess.com package not installed.",
            hint="Install it with: uv add chess.com",
        )

    games = []
    try:
        archives = get_player_game_archives(username)
        archive_urls = archives.json.get("archives", [])

        # Process most recent archives first
        for archive_url in reversed(archive_urls):
            if len(games) >= max_games:
                break

            from chessdotcom import get_player_games_by_month_via_archive

            month_data = get_player_games_by_month_via_archive(archive_url)
            month_games = month_data.json.get("games", [])

            for game_data in reversed(month_games):
                if len(games) >= max_games:
                    break

                time_class = game_data.get("time_class", "")
                rated = game_data.get("rated", False)

                if not rated or time_class not in ("rapid", "classical", "daily"):
                    continue

                pgn_text = game_data.get("pgn", "")
                if pgn_text:
                    game = chess.pgn.read_game(io.StringIO(pgn_text))
                    if game:
                        games.append(game)

        print(f"  Fetched {len(games)} game(s) from chess.com for {username}")
    except Exception as e:
        error_exit(
            f"Failed to fetch chess.com games: {e}",
            hint=f"Check that username '{username}' exists on chess.com.",
        )

    return games


def _load_repertoire(repertoire_path: Path) -> list[chess.pgn.Game]:
    """Load all games from a repertoire PGN file.

    Args:
        repertoire_path: Path to the repertoire PGN file.

    Returns:
        List of parsed games.
    """
    games = []
    with open(repertoire_path) as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            games.append(game)
    return games


def analyze_deviations(
    games: list[chess.pgn.Game],
    repertoire_path: Path,
) -> dict:
    """Analyze games against repertoire, return deviation statistics.

    Args:
        games: List of played games.
        repertoire_path: Path to the repertoire PGN file.

    Returns:
        Dict mapping chapter names to deviation info:
        {chapter_name: {deviation_move: {count, games, ...}}}
    """
    repertoire_games = _load_repertoire(repertoire_path)
    if not repertoire_games:
        print(f"  No chapters found in {repertoire_path}", file=sys.stderr)
        return {}

    stats: dict[str, dict] = {}

    for game in games:
        match, dev_idx = match_game_to_repertoire(game, repertoire_games)
        if match is None:
            continue

        chapter_name = match.headers.get("Event", "Unnamed")
        if chapter_name not in stats:
            stats[chapter_name] = {}

        if dev_idx is not None:
            game_moves = _extract_mainline_sans(game)
            dev_move = game_moves[dev_idx] if dev_idx < len(game_moves) else "end"
            key = f"move {dev_idx + 1}: {dev_move}"

            if key not in stats[chapter_name]:
                stats[chapter_name][key] = {"count": 0, "games": []}

            stats[chapter_name][key]["count"] += 1
            game_id = game.headers.get("Site", "unknown")
            stats[chapter_name][key]["games"].append(game_id)

    return stats


def import_games(
    username: str,
    *,
    chesscom: str | None = None,
    masters: bool = False,
    max_games: int = 100,
    enrich: bool = False,
) -> None:
    """Main import entry point. Fetches games, analyzes deviations, optionally enriches PGN.

    Args:
        username: Lichess username.
        chesscom: Optional chess.com username to also fetch from.
        masters: If True, also query the Lichess masters database.
        max_games: Maximum games to fetch per source.
        enrich: If True, add deviation info to repertoire PGN comments.
    """
    print(f"\n  Importing games for {username}...")

    all_games: list[chess.pgn.Game] = []

    # Fetch from Lichess
    lichess_games = fetch_lichess_games(username, max_games)
    all_games.extend(lichess_games)

    # Optionally fetch from chess.com
    if chesscom:
        chesscom_games = fetch_chesscom_games(chesscom, max_games)
        all_games.extend(chesscom_games)

    if not all_games:
        print("  No games found.")
        return

    # Find repertoire files
    root = _find_project_root()
    config = load_config()
    studies = config.get("studies", {})

    for pgn_file in studies:
        pgn_path = root / "pgn" / pgn_file
        if not pgn_path.exists():
            continue

        print(f"\n  Analyzing against {pgn_file}...")
        deviations = analyze_deviations(all_games, pgn_path)

        if not deviations:
            print("    No matching games found for this repertoire.")
            continue

        for chapter_name, dev_info in deviations.items():
            print(f"\n    {chapter_name}:")
            for move_key, data in sorted(dev_info.items()):
                count = data["count"]
                print(f"      {move_key} ({count} time{'s' if count > 1 else ''})")

    print(f"\n  Total games analyzed: {len(all_games)}")
