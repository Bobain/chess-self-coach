"""Game cache: fetch games from APIs and cache locally for later analysis.

Decouples game fetching (fast, API-only) from Stockfish analysis (slow).
The cache stores raw PGN text so games can be deserialized on demand.
"""

from __future__ import annotations

import io
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import chess.pgn

from chess_self_coach.config import _find_project_root

_log = logging.getLogger(__name__)

CACHE_FILENAME = "fetched_games.json"


@dataclass
class GameSummary:
    """Summary of a game for the game list UI.

    Attributes:
        game_id: Unique game identifier (URL from PGN headers).
        white: White player name.
        black: Black player name.
        player_color: Color the player was playing ("white" or "black").
        result: Game result ("1-0", "0-1", "1/2-1/2").
        date: Game date string (YYYY.MM.DD).
        opening: Opening name if known.
        move_count: Number of half-moves in the game.
        source: Platform ("lichess" or "chess.com").
        analyzed: Whether the game has been analyzed with Stockfish.
    """

    game_id: str
    white: str
    black: str
    player_color: str
    result: str
    date: str
    opening: str
    move_count: int
    source: str
    analyzed: bool

    def to_dict(self) -> dict:
        """Serialize to dict for JSON API response."""
        return asdict(self)


def _game_id_from_headers(game: chess.pgn.Game) -> str:
    """Extract a unique game ID from PGN headers.

    Args:
        game: Parsed PGN game.

    Returns:
        Game URL (Link or Site header), or empty string.
    """
    gid = game.headers.get("Link", game.headers.get("Site", ""))
    return "" if gid == "?" else gid


def _detect_source(game_id: str) -> str:
    """Detect the platform from the game URL.

    Args:
        game_id: Game URL.

    Returns:
        "lichess", "chess.com", or "unknown".
    """
    if "lichess.org" in game_id:
        return "lichess"
    if "chess.com" in game_id:
        return "chess.com"
    return "unknown"


def _determine_player_color(
    game: chess.pgn.Game, lichess_user: str, chesscom_user: str | None
) -> str | None:
    """Determine which color the player was playing.

    Args:
        game: Parsed PGN game.
        lichess_user: Lichess username.
        chesscom_user: Optional chess.com username.

    Returns:
        "white", "black", or None if player not found.
    """
    white = game.headers.get("White", "").lower()
    black = game.headers.get("Black", "").lower()

    for username in [lichess_user.lower(), (chesscom_user or "").lower()]:
        if not username:
            continue
        if username == white:
            return "white"
        if username == black:
            return "black"
    return None


def _game_to_summary(
    game: chess.pgn.Game, game_id: str, player_color: str, analyzed: bool = False
) -> GameSummary:
    """Convert a chess.pgn.Game to a GameSummary.

    Args:
        game: Parsed PGN game.
        game_id: Unique game identifier.
        player_color: "white" or "black".
        analyzed: Whether analysis data exists for this game.

    Returns:
        GameSummary with extracted metadata.
    """
    # Count moves
    move_count = 0
    node = game
    while node.variations:
        node = node.variation(0)
        move_count += 1

    opening = game.headers.get("Opening", game.headers.get("ECO", ""))

    return GameSummary(
        game_id=game_id,
        white=game.headers.get("White", "?"),
        black=game.headers.get("Black", "?"),
        player_color=player_color,
        result=game.headers.get("Result", "*"),
        date=game.headers.get("Date", ""),
        opening=opening,
        move_count=move_count,
        source=_detect_source(game_id),
        analyzed=analyzed,
    )


def _game_to_pgn_text(game: chess.pgn.Game) -> str:
    """Serialize a chess.pgn.Game to PGN text.

    Args:
        game: Parsed PGN game.

    Returns:
        PGN string with headers and moves.
    """
    exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
    return game.accept(exporter)


def fetch_and_cache_games(
    lichess_user: str,
    chesscom_user: str | None,
    max_games: int = 200,
) -> list[GameSummary]:
    """Fetch games from Lichess and chess.com, cache locally.

    Args:
        lichess_user: Lichess username.
        chesscom_user: Optional chess.com username.
        max_games: Maximum games to fetch per source.

    Returns:
        List of GameSummary for all fetched games.
    """
    from chess_self_coach.importer import fetch_chesscom_games, fetch_lichess_games

    # Fetch more than requested to account for duplicates already in cache
    existing_cache = load_game_cache()
    cached_count = len(existing_cache.get("games", {}))
    fetch_count = max_games + cached_count

    all_games: list[chess.pgn.Game] = []
    if lichess_user:
        all_games.extend(fetch_lichess_games(lichess_user, fetch_count))
    if chesscom_user:
        all_games.extend(fetch_chesscom_games(chesscom_user, fetch_count))

    root = _find_project_root()
    cache_path = root / CACHE_FILENAME

    # Merge with existing cache (preserve previously fetched games)
    cache_games: dict[str, dict] = dict(existing_cache.get("games", {}))
    new_count = 0

    summaries: list[GameSummary] = []

    for game in all_games:
        game_id = _game_id_from_headers(game)
        if not game_id or game_id in cache_games:
            continue

        player_color = _determine_player_color(game, lichess_user, chesscom_user)
        if player_color is None:
            continue

        pgn_text = _game_to_pgn_text(game)
        summary = _game_to_summary(game, game_id, player_color)

        cache_games[game_id] = {
            "pgn": pgn_text,
            "headers": dict(game.headers),
            "player_color": player_color,
            "move_count": summary.move_count,
            "source": summary.source,
        }
        summaries.append(summary)
        new_count += 1

    # Also build summaries for existing cached games (so API returns all)
    for game_id, entry in existing_cache.get("games", {}).items():
        if any(s.game_id == game_id for s in summaries):
            continue
        summaries.append(GameSummary(
            game_id=game_id,
            white=entry.get("headers", {}).get("White", "?"),
            black=entry.get("headers", {}).get("Black", "?"),
            date=entry.get("headers", {}).get("Date", ""),
            result=entry.get("headers", {}).get("Result", "*"),
            player_color=entry.get("player_color", "white"),
            opening=entry.get("headers", {}).get("Opening", ""),
            move_count=entry.get("move_count", 0),
            source=entry.get("source", ""),
            analyzed=False,
        ))

    # Write merged cache
    cache_data = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "games": cache_games,
    }
    with open(cache_path, "w") as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    _log.info("Cached %d games (%d new) to %s", len(cache_games), new_count, cache_path)
    return summaries


def load_game_cache() -> dict:
    """Load the fetched games cache.

    Returns:
        Cache dict with 'fetched_at' and 'games' keys, or empty structure.
    """
    root = _find_project_root()
    cache_path = root / CACHE_FILENAME
    if not cache_path.exists():
        return {"fetched_at": None, "games": {}}
    try:
        with open(cache_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        _log.warning("Failed to load game cache from %s", cache_path)
        return {"fetched_at": None, "games": {}}


def get_cached_game(game_id: str) -> chess.pgn.Game | None:
    """Deserialize a single game from the cache.

    Args:
        game_id: Game URL identifier.

    Returns:
        Parsed chess.pgn.Game, or None if not in cache.
    """
    cache = load_game_cache()
    entry = cache.get("games", {}).get(game_id)
    if entry is None:
        return None

    pgn_io = io.StringIO(entry["pgn"])
    return chess.pgn.read_game(pgn_io)


def get_unified_game_list(limit: int = 20) -> list[GameSummary]:
    """Merge fetched games cache with analysis data into a unified list.

    Analysis data takes precedence (richer info, marked as analyzed).
    Sorted by date descending, capped at limit.

    Args:
        limit: Maximum number of games to return.

    Returns:
        List of GameSummary, most recent first.
    """
    from chess_self_coach.analysis import load_analysis_data

    root = _find_project_root()

    # Load analysis data
    analysis_data = load_analysis_data(root / "analysis_data.json")
    analyzed_games = analysis_data.get("games", {})
    player_info = analysis_data.get("player", {})
    lichess_user = player_info.get("lichess", "")
    chesscom_user = player_info.get("chesscom")

    # Load cache
    cache = load_game_cache()
    cached_games = cache.get("games", {})

    # If no player info from analysis, try config
    if not lichess_user and not chesscom_user:
        try:
            from chess_self_coach.config import load_config

            config = load_config()
            players = config.get("players", {})
            lichess_user = players.get("lichess", "")
            chesscom_user = players.get("chesscom")
        except Exception:
            pass

    # Build unified list: analyzed games first, then cached-only
    seen: set[str] = set()
    summaries: list[GameSummary] = []

    # Analyzed games
    for game_id, game_data in analyzed_games.items():
        seen.add(game_id)
        headers = game_data.get("headers", {})
        player_color = game_data.get("player_color", "white")
        moves = game_data.get("moves", [])

        opening = ""
        for m in moves:
            oe = m.get("opening_explorer")
            if oe and oe.get("moves"):
                for om in oe["moves"]:
                    if om and (om.get("opening") or {}).get("name") and om.get("uci") == m.get(
                        "move_uci"
                    ):
                        opening = om["opening"]["name"]
                        break
                if opening:
                    break

        summaries.append(
            GameSummary(
                game_id=game_id,
                white=headers.get("white", headers.get("White", "?")),
                black=headers.get("black", headers.get("Black", "?")),
                player_color=player_color,
                result=headers.get("result", headers.get("Result", "*")),
                date=headers.get("date", headers.get("Date", "")),
                opening=opening or headers.get("opening", headers.get("Opening", "")),
                move_count=len(moves),
                source=_detect_source(game_id),
                analyzed=True,
            )
        )

    # Cached-only games (not yet analyzed)
    for game_id, entry in cached_games.items():
        if game_id in seen:
            continue
        seen.add(game_id)
        headers = entry.get("headers", {})
        summaries.append(
            GameSummary(
                game_id=game_id,
                white=headers.get("White", "?"),
                black=headers.get("Black", "?"),
                player_color=entry.get("player_color", "white"),
                result=headers.get("Result", "*"),
                date=headers.get("Date", ""),
                opening=headers.get("Opening", headers.get("ECO", "")),
                move_count=entry.get("move_count", 0),
                source=entry.get("source", _detect_source(game_id)),
                analyzed=False,
            )
        )

    # Sort by date descending
    summaries.sort(key=lambda s: s.date, reverse=True)
    return summaries[:limit]
