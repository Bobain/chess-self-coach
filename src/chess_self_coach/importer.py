"""Game fetching from Lichess and chess.com."""

from __future__ import annotations

import io
import logging
import sys

import berserk
import chess
import chess.pgn

from chess_self_coach.config import error_exit, load_lichess_token


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
            clocks=True,
        )

        pgn_text = "".join(exported) if hasattr(exported, "__iter__") else str(exported)
        pgn_io = io.StringIO(pgn_text)

        # Suppress chess.pgn parse errors (variant games produce illegal SAN warnings)
        chess_logger = logging.getLogger("chess.pgn")
        old_level = chess_logger.level
        chess_logger.setLevel(logging.CRITICAL)

        skipped_variants = 0
        while True:
            game = chess.pgn.read_game(pgn_io)
            if game is None:
                break
            variant = game.headers.get("Variant", "Standard")
            if variant != "Standard":
                site = game.headers.get("Site", "?")
                print(f"  ⚠ Skipping {variant} game: {site}", file=sys.stderr)
                skipped_variants += 1
                continue
            games.append(game)

        chess_logger.setLevel(old_level)

        msg = f"  Fetched {len(games)} game(s) from Lichess for {username}"
        if skipped_variants:
            msg += f" ({skipped_variants} variant game(s) excluded)"
        print(msg)
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

    from chessdotcom import Client as ChesscomClient

    ChesscomClient.request_config["headers"]["User-Agent"] = (
        "chess-self-coach (github.com/Bobain/chess-self-coach)"
    )

    games = []
    try:
        archives = get_player_game_archives(username)
        archive_urls = archives.json.get("archives", [])

        # Process most recent archives first
        from chessdotcom import get_player_games_by_month

        for archive_url in reversed(archive_urls):
            if len(games) >= max_games:
                break

            # Extract year/month from archive URL: .../YYYY/MM
            parts = archive_url.rstrip("/").split("/")
            year, month = parts[-2], parts[-1]
            month_data = get_player_games_by_month(username, year, month)
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
