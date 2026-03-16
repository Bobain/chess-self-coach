"""Training mode: extract mistakes from games, generate explanations, export drill data.

Analyzes the player's games with Stockfish, finds positions where significant
centipawn losses occurred, generates rule-based explanations, and exports
a JSON file for the PWA drill interface.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.engine
import chess.pgn

from chess_self_coach.config import (
    _find_project_root,
    check_stockfish_version,
    find_stockfish,
    load_config,
)
from chess_self_coach.importer import fetch_chesscom_games, fetch_lichess_games

# Centipawn loss thresholds
BLUNDER_THRESHOLD = 200
MISTAKE_THRESHOLD = 100
INACCURACY_THRESHOLD = 50

# Sentinel for mate scores (centipawns)
_MATE_CP = 10000


def _score_to_cp(score: chess.engine.PovScore) -> int | None:
    """Convert a PovScore to centipawns from white's perspective.

    Args:
        score: Engine PovScore.

    Returns:
        Centipawns (white perspective), or None if unavailable.
    """
    white = score.white()
    if white.is_mate():
        mate = white.mate()
        return _MATE_CP if mate > 0 else -_MATE_CP
    return white.score()


def _format_score_cp(cp: int | None) -> str:
    """Format centipawn value as score string like '+0.32'."""
    if cp is None:
        return "+0.00"
    value = cp / 100.0
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}"


def compute_cp_loss(
    before_white_cp: int, after_white_cp: int, side_to_move: chess.Color
) -> int:
    """Compute centipawn loss for the player who made the move.

    Args:
        before_white_cp: Score before the move (white perspective, centipawns).
        after_white_cp: Score after the move (white perspective, centipawns).
        side_to_move: Color of the player who made the move.

    Returns:
        Centipawn loss (positive = bad for the mover).
    """
    if side_to_move == chess.WHITE:
        return before_white_cp - after_white_cp
    return after_white_cp - before_white_cp


def _classify_mistake(cp_loss: int) -> str | None:
    """Classify a move by centipawn loss.

    Returns:
        Category string or None if the move is acceptable.
    """
    if cp_loss >= BLUNDER_THRESHOLD:
        return "blunder"
    if cp_loss >= MISTAKE_THRESHOLD:
        return "mistake"
    if cp_loss >= INACCURACY_THRESHOLD:
        return "inaccuracy"
    return None


def generate_explanation(
    board: chess.Board,
    actual_san: str,
    best_san: str,
    cp_loss: int,
    category: str,
) -> str:
    """Generate a rule-based explanation for a mistake.

    Detects basic patterns: missed captures, missed checks/checkmates,
    hanging pieces. Falls back to a generic template.

    Args:
        board: Board position BEFORE the move was played.
        actual_san: The move the player made (SAN).
        best_san: The best move according to Stockfish (SAN).
        cp_loss: Centipawn loss.
        category: Mistake category string.

    Returns:
        Explanation string.
    """
    parts = [f"You played {actual_san} ({category}, -{cp_loss} cp)."]

    try:
        best_move = board.parse_san(best_san)
    except ValueError:
        parts.append(f"A better move was {best_san}.")
        return " ".join(parts)

    # Check if best move delivers checkmate
    board_after_best = board.copy()
    board_after_best.push(best_move)
    if board_after_best.is_checkmate():
        parts.append(f"{best_san} was checkmate!")
        return " ".join(parts)

    # Check if best move captures a piece
    if board.is_capture(best_move):
        captured_piece = board.piece_at(best_move.to_square)
        if captured_piece is None:
            # En passant
            parts.append(f"{best_san} wins a pawn (en passant).")
        else:
            piece_name = chess.piece_name(captured_piece.piece_type)
            parts.append(f"You missed capturing the {piece_name} with {best_san}.")
    else:
        parts.append(f"A better move was {best_san}.")

    # Check if best move gives check
    if board_after_best.is_check():
        parts.append(f"{best_san} also gives check.")

    # Check if the actual move hangs a piece
    try:
        actual_move = board.parse_san(actual_san)
        board_after_actual = board.copy()
        board_after_actual.push(actual_move)
        moving_piece = board.piece_at(actual_move.from_square)
        if moving_piece:
            attacked = board_after_actual.is_attacked_by(
                not board.turn, actual_move.to_square
            )
            defended = board_after_actual.is_attacked_by(
                board.turn, actual_move.to_square
            )
            if attacked and not defended:
                piece_name = chess.piece_name(moving_piece.piece_type)
                sq_name = chess.square_name(actual_move.to_square)
                parts.append(f"Your {piece_name} on {sq_name} is left undefended.")
    except ValueError:
        pass

    return " ".join(parts)


def _make_position_id(fen: str, actual_san: str) -> str:
    """Generate a stable short ID for a position + move combination."""
    data = f"{fen}:{actual_san}"
    return hashlib.sha256(data.encode()).hexdigest()[:12]


def _determine_player_color(
    game: chess.pgn.Game, lichess_user: str, chesscom_user: str | None
) -> chess.Color | None:
    """Determine which color the player was playing.

    Args:
        game: Parsed PGN game.
        lichess_user: Lichess username.
        chesscom_user: Optional chess.com username.

    Returns:
        chess.WHITE, chess.BLACK, or None if player not found.
    """
    white = game.headers.get("White", "").lower()
    black = game.headers.get("Black", "").lower()

    for username in [lichess_user.lower(), (chesscom_user or "").lower()]:
        if not username:
            continue
        if username == white:
            return chess.WHITE
        if username == black:
            return chess.BLACK

    return None


def _detect_source(game: chess.pgn.Game) -> str:
    """Detect whether a game is from Lichess or chess.com."""
    site = game.headers.get("Site", "")
    if "lichess.org" in site:
        return "lichess"
    if "chess.com" in site:
        return "chess.com"
    return "unknown"


def _get_opponent(game: chess.pgn.Game, player_color: chess.Color) -> str:
    """Get the opponent's name from game headers."""
    if player_color == chess.WHITE:
        return game.headers.get("Black", "?")
    return game.headers.get("White", "?")


def extract_mistakes(
    game: chess.pgn.Game,
    engine: chess.engine.SimpleEngine,
    depth: int,
    player_color: chess.Color,
    min_cp_loss: int = INACCURACY_THRESHOLD,
) -> list[dict]:
    """Extract mistake positions from a single game.

    Runs Stockfish on every mainline position, computes centipawn loss
    for each of the player's moves, and returns positions above the threshold.

    Args:
        game: Parsed PGN game.
        engine: Running Stockfish engine.
        depth: Analysis depth.
        player_color: Which color the player was.
        min_cp_loss: Minimum cp loss to include (default: 50).

    Returns:
        List of mistake dicts ready for training_data.json.
    """
    # Build list of (fen, turn, score_cp, best_san, actual_san) for each position
    positions = []
    node = game

    while node.variations:
        board = node.board()
        next_node = node.variations[0]
        actual_move = next_node.move

        info = engine.analyse(board, chess.engine.Limit(depth=depth))
        score = info.get("score")
        pv = info.get("pv", [])

        if score is None:
            node = next_node
            continue

        score_cp = _score_to_cp(score)
        best_move = pv[0] if pv else None

        positions.append({
            "fen": board.fen(),
            "turn": board.turn,
            "score_cp": score_cp,
            "best_san": board.san(best_move) if best_move else None,
            "actual_san": board.san(actual_move),
        })
        node = next_node

    # Score the final position (needed for last move's cp_loss)
    board = node.board()
    info = engine.analyse(board, chess.engine.Limit(depth=depth))
    score = info.get("score")
    if score:
        positions.append({
            "fen": board.fen(),
            "turn": board.turn,
            "score_cp": _score_to_cp(score),
            "best_san": None,
            "actual_san": None,
        })

    # Find the player's mistakes
    mistakes = []
    for i in range(len(positions) - 1):
        pos = positions[i]
        next_pos = positions[i + 1]

        # Only the player's moves
        if pos["turn"] != player_color:
            continue

        if pos["score_cp"] is None or next_pos["score_cp"] is None:
            continue

        cp_loss = compute_cp_loss(
            pos["score_cp"], next_pos["score_cp"], pos["turn"]
        )

        if cp_loss < min_cp_loss:
            continue

        category = _classify_mistake(cp_loss)
        if category is None or not pos["best_san"]:
            continue

        board = chess.Board(pos["fen"])
        explanation = generate_explanation(
            board, pos["actual_san"], pos["best_san"], cp_loss, category
        )

        mistakes.append({
            "id": _make_position_id(pos["fen"], pos["actual_san"]),
            "fen": pos["fen"],
            "player_color": "white" if player_color == chess.WHITE else "black",
            "player_move": pos["actual_san"],
            "best_move": pos["best_san"],
            "score_before": _format_score_cp(pos["score_cp"]),
            "score_after": _format_score_cp(next_pos["score_cp"]),
            "cp_loss": cp_loss,
            "category": category,
            "explanation": explanation,
            "acceptable_moves": [pos["best_san"]],
            "game": {
                "source": _detect_source(game),
                "opponent": _get_opponent(game, player_color),
                "date": game.headers.get("Date", "?"),
                "result": game.headers.get("Result", "*"),
                "opening": game.headers.get(
                    "Opening", game.headers.get("Event", "?")
                ),
            },
        })

    return mistakes


def prepare_training_data(
    *,
    max_games: int = 20,
    depth: int = 18,
    engine_path: str | None = None,
) -> None:
    """Fetch games, analyze with Stockfish, extract mistakes, export training JSON.

    Args:
        max_games: Maximum games to fetch per source.
        depth: Stockfish analysis depth.
        engine_path: Override path to Stockfish binary.
    """
    config = load_config()
    players = config.get("players", {})
    lichess_user = players.get("lichess", "")
    chesscom_user = players.get("chesscom")

    if not lichess_user:
        print(
            "No Lichess username in config.json (players.lichess)", file=sys.stderr
        )
        sys.exit(1)

    # Find Stockfish
    if engine_path:
        sf_path = Path(engine_path)
        if not sf_path.exists():
            print(f"Engine not found: {sf_path}", file=sys.stderr)
            sys.exit(1)
    else:
        sf_path = find_stockfish(config)
        expected = config.get("stockfish", {}).get("expected_version")
        version = check_stockfish_version(sf_path, expected)
        print(f"  Using {version} at {sf_path}")

    # Fetch games
    print("\n  Fetching games...")
    all_games: list[chess.pgn.Game] = []

    lichess_games = fetch_lichess_games(lichess_user, max_games)
    all_games.extend(lichess_games)

    if chesscom_user:
        chesscom_games = fetch_chesscom_games(chesscom_user, max_games)
        all_games.extend(chesscom_games)

    if not all_games:
        print("  No games found.")
        return

    # Analyze each game
    print(f"\n  Analyzing {len(all_games)} game(s) with Stockfish (depth {depth})...")
    print("  This may take several minutes...\n")
    all_mistakes: list[dict] = []

    engine = chess.engine.SimpleEngine.popen_uci(str(sf_path))
    try:
        for i, game in enumerate(all_games):
            player_color = _determine_player_color(game, lichess_user, chesscom_user)
            if player_color is None:
                continue

            white = game.headers.get("White", "?")
            black = game.headers.get("Black", "?")
            print(
                f"  [{i + 1}/{len(all_games)}] {white} vs {black}...",
                end="",
                flush=True,
            )

            start = time.time()
            mistakes = extract_mistakes(game, engine, depth, player_color)
            elapsed = time.time() - start

            print(f" {len(mistakes)} mistake(s) ({elapsed:.1f}s)")
            all_mistakes.extend(mistakes)
    finally:
        engine.quit()

    # Deduplicate by position ID (same mistake in multiple games)
    seen: set[str] = set()
    unique_mistakes: list[dict] = []
    for m in all_mistakes:
        if m["id"] not in seen:
            seen.add(m["id"])
            unique_mistakes.append(m)

    # Sort: blunders first, then by cp_loss descending
    severity = {"blunder": 0, "mistake": 1, "inaccuracy": 2}
    unique_mistakes.sort(
        key=lambda m: (severity.get(m["category"], 3), -m["cp_loss"])
    )

    # Add initial SRS data
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for m in unique_mistakes:
        m["srs"] = {
            "interval": 0,
            "ease": 2.5,
            "next_review": today,
            "history": [],
        }

    # Build and write output
    training_data = {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "player": {
            "lichess": lichess_user,
            "chesscom": chesscom_user or "",
        },
        "positions": unique_mistakes,
    }

    root = _find_project_root()
    output_path = root / "training_data.json"
    with open(output_path, "w") as f:
        json.dump(training_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\n  Training data exported: {output_path}")
    print(f"  Total positions: {len(unique_mistakes)}")
    blunders = sum(1 for m in unique_mistakes if m["category"] == "blunder")
    mistake_count = sum(1 for m in unique_mistakes if m["category"] == "mistake")
    inaccuracies = sum(1 for m in unique_mistakes if m["category"] == "inaccuracy")
    print(f"    Blunders: {blunders}")
    print(f"    Mistakes: {mistake_count}")
    print(f"    Inaccuracies: {inaccuracies}")


def print_stats() -> None:
    """Show training progress from training_data.json."""
    root = _find_project_root()
    data_path = root / "training_data.json"

    if not data_path.exists():
        print(
            "No training data found. Run: chess-self-coach train --prepare",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(data_path) as f:
        data = json.load(f)

    positions = data.get("positions", [])
    if not positions:
        print("  No positions in training data.")
        return

    print("\n  Training Data Stats")
    print(f"  Generated: {data.get('generated', '?')}")
    print(f"  Total positions: {len(positions)}")

    # By category
    categories: dict[str, int] = {}
    for p in positions:
        cat = p.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    print("\n  By category:")
    for cat in ["blunder", "mistake", "inaccuracy"]:
        print(f"    {cat.capitalize()}: {categories.get(cat, 0)}")

    # By source
    sources: dict[str, int] = {}
    for p in positions:
        src = p.get("game", {}).get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1

    print("\n  By source:")
    for src, count in sorted(sources.items()):
        print(f"    {src}: {count}")


def serve_pwa() -> None:
    """Start a local HTTP server and open the training PWA in the browser.

    Copies PWA files + training data to a temp directory and injects the
    project version into the service worker cache name. Source files are
    never modified.
    """
    import http.server
    import shutil
    import tempfile
    import threading
    import webbrowser

    from chess_self_coach import __version__

    root = _find_project_root()
    pwa_src = root / "pwa"

    if not pwa_src.exists():
        print("PWA directory not found at pwa/", file=sys.stderr)
        sys.exit(1)

    # Copy PWA files to a temp directory (never modify source files)
    serve_dir = Path(tempfile.mkdtemp(prefix="chess-self-coach-"))
    for f in pwa_src.iterdir():
        if f.is_file() and f.name != "training_data.json":
            shutil.copy2(f, serve_dir / f.name)

    # Inject version into service worker
    sw_path = serve_dir / "sw.js"
    sw_text = sw_path.read_text()
    sw_path.write_text(sw_text.replace("__VERSION__", __version__))

    # Copy training data
    data_path = root / "training_data.json"
    if data_path.exists():
        shutil.copy2(data_path, serve_dir / "training_data.json")
        print("  Copied training_data.json")
    else:
        print(
            "  Warning: No training_data.json found. Run --prepare first.",
            file=sys.stderr,
        )

    port = 8000

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(serve_dir), **kw)

        def log_message(self, format, *args):
            pass  # suppress request logs

    server = http.server.HTTPServer(("localhost", port), Handler)
    url = f"http://localhost:{port}"
    print(f"  Serving PWA at {url} (v{__version__})")
    print("  Press Ctrl+C to stop\n")

    threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.shutdown()
        shutil.rmtree(serve_dir, ignore_errors=True)
