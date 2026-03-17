"""Training mode: extract mistakes from games, generate explanations, export drill data.

Analyzes the player's games with Stockfish, finds positions where significant
centipawn losses occurred, generates rule-based explanations, and exports
a JSON file for the PWA drill interface.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
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


def _score_to_cp(score: chess.engine.PovScore) -> tuple[int | None, bool]:
    """Convert a PovScore to centipawns from white's perspective.

    Args:
        score: Engine PovScore.

    Returns:
        Tuple of (centipawns from white perspective, is_mate).
    """
    white = score.white()
    if white.is_mate():
        mate = white.mate()
        return (_MATE_CP if mate > 0 else -_MATE_CP), True
    return white.score(), False


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


def _format_cp_loss_human(cp_loss: int, was_mate: bool = False) -> str:
    """Format centipawn loss for human display.

    Args:
        cp_loss: Centipawn loss value.
        was_mate: True if the score before the move was a forced mate.

    Returns human-readable loss string.
    """
    if cp_loss >= _MATE_CP or was_mate:
        return "a forced mate"
    pawns = cp_loss / 100.0
    if pawns == int(pawns):
        return f"{int(pawns)} pawn{'s' if int(pawns) != 1 else ''}"
    return f"{pawns:.1f} pawns"


def generate_explanation(
    board: chess.Board,
    actual_san: str,
    best_san: str,
    cp_loss: int,
    category: str,
    was_mate: bool = False,
    score_after_cp: int | None = None,
) -> str:
    """Generate a rule-based explanation for a mistake.

    Detects basic patterns: missed captures, missed checks/checkmates,
    hanging pieces, stalemate. Falls back to a generic template.

    Args:
        board: Board position BEFORE the move was played.
        actual_san: The move the player made (SAN).
        best_san: The best move according to Stockfish (SAN).
        cp_loss: Centipawn loss.
        category: Mistake category string.
        was_mate: True if the position before was a forced mate.
        score_after_cp: Score after the move (white perspective), for context.

    Returns:
        Explanation string.
    """
    score_after_is_mate = score_after_cp is not None and abs(score_after_cp) >= _MATE_CP

    # Build opening sentence with appropriate phrasing
    if was_mate and score_after_cp is not None and abs(score_after_cp) < 50:
        parts = [f"You played {actual_san} ({category}). You had a forced mate but threw it away — the game is now a draw."]
    elif was_mate:
        parts = [f"You played {actual_san} ({category}). You had a forced mate but lost it."]
    elif score_after_is_mate:
        parts = [f"You played {actual_san} ({category}). This allowed your opponent to force checkmate."]
    else:
        loss_str = _format_cp_loss_human(cp_loss)
        parts = [f"You played {actual_san} ({category}, lost {loss_str})."]

    # Analyze the actual move for immediate stalemate detection
    board_after_actual = None
    try:
        actual_move = board.parse_san(actual_san)
        board_after_actual = board.copy()
        board_after_actual.push(actual_move)
        if board_after_actual.is_stalemate():
            parts.append("This leads to stalemate (draw)!")
    except ValueError:
        pass

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
    if board_after_actual:
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

    return " ".join(parts)


def _generate_context(
    category: str,
    cp_loss: int,
    was_mate: bool,
    score_after_cp: int | None,
) -> str:
    """Generate a short context sentence shown BEFORE the player answers.

    Tells the player what went wrong with their move, to frame the exercise.
    """
    score_after_is_mate = score_after_cp is not None and abs(score_after_cp) >= _MATE_CP

    if was_mate and score_after_cp is not None and abs(score_after_cp) < 50:
        return "Your move threw away a winning position and led to a draw."
    if was_mate:
        return "Your move threw away a forced mate."
    if score_after_is_mate:
        return "Your move allowed your opponent to force checkmate."
    if cp_loss >= _MATE_CP:
        return "Your move allowed your opponent to force checkmate."

    pawns = cp_loss / 100.0
    if pawns >= 5:
        return f"Your move lost a decisive advantage ({pawns:.1f} pawns)."
    if pawns >= 2:
        return f"Your move lost significant material ({pawns:.1f} pawns)."
    if pawns >= 1:
        return f"Your move lost about {pawns:.1f} pawns of advantage."
    return f"Your move was slightly inaccurate ({pawns:.1f} pawns)."


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

        score_cp, is_mate = _score_to_cp(score)
        best_move = pv[0] if pv else None

        # Convert PV to SAN (up to 5 moves)
        pv_san = []
        pv_board = board.copy()
        for move in pv[:5]:
            try:
                pv_san.append(pv_board.san(move))
                pv_board.push(move)
            except (ValueError, AssertionError):
                break

        positions.append({
            "fen": board.fen(),
            "turn": board.turn,
            "score_cp": score_cp,
            "is_mate": is_mate,
            "best_san": board.san(best_move) if best_move else None,
            "actual_san": board.san(actual_move),
            "pv": pv_san,
        })
        node = next_node

    # Score the final position (needed for last move's cp_loss)
    board = node.board()
    info = engine.analyse(board, chess.engine.Limit(depth=depth))
    score = info.get("score")
    if score:
        score_cp, is_mate = _score_to_cp(score)
        positions.append({
            "fen": board.fen(),
            "turn": board.turn,
            "score_cp": score_cp,
            "is_mate": is_mate,
            "best_san": None,
            "actual_san": None,
            "pv": [],
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

        # Skip if the played move delivers checkmate
        board = chess.Board(pos["fen"])
        try:
            actual_move = board.parse_san(pos["actual_san"])
            board.push(actual_move)
            if board.is_checkmate():
                continue
        except ValueError:
            pass

        cp_loss = compute_cp_loss(
            pos["score_cp"], next_pos["score_cp"], pos["turn"]
        )

        if cp_loss < min_cp_loss:
            continue

        category = _classify_mistake(cp_loss)
        if category is None or not pos["best_san"]:
            continue

        was_mate = pos.get("is_mate", False)
        score_after_cp = next_pos["score_cp"]
        board = chess.Board(pos["fen"])
        explanation = generate_explanation(
            board, pos["actual_san"], pos["best_san"], cp_loss, category,
            was_mate=was_mate,
            score_after_cp=score_after_cp,
        )
        context = _generate_context(category, cp_loss, was_mate, score_after_cp)

        mistakes.append({
            "id": _make_position_id(pos["fen"], pos["actual_san"]),
            "fen": pos["fen"],
            "player_color": "white" if player_color == chess.WHITE else "black",
            "player_move": pos["actual_san"],
            "best_move": pos["best_san"],
            "context": context,
            "score_before": _format_score_cp(pos["score_cp"]),
            "score_after": _format_score_cp(next_pos["score_cp"]),
            "cp_loss": cp_loss,
            "category": category,
            "explanation": explanation,
            "acceptable_moves": [pos["best_san"]],
            "pv": pos.get("pv", []),
            "game": {
                "id": game.headers.get("Site", ""),
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


def _physical_core_count() -> int:
    """Return the number of physical CPU cores.

    Reads /proc/cpuinfo on Linux, falls back to os.cpu_count() // 2.
    """
    try:
        cores = set()
        with open("/proc/cpuinfo") as f:
            physical_id = core_id = None
            for line in f:
                if line.startswith("physical id"):
                    physical_id = line.split(":")[1].strip()
                elif line.startswith("core id"):
                    core_id = line.split(":")[1].strip()
                    if physical_id is not None:
                        cores.add((physical_id, core_id))
        if cores:
            return len(cores)
    except OSError:
        pass
    return os.cpu_count() // 2 or 1


def _analyze_game_worker(
    pgn_str: str,
    sf_path_str: str,
    depth: int,
    player_color: chess.Color,
    idx: int,
    total: int,
    label: str,
) -> tuple[int, int, str, list[dict], float]:
    """Worker function for parallel game analysis.

    Each worker opens its own Stockfish instance, analyzes one game,
    and returns the results. Designed for ProcessPoolExecutor.
    """
    game = chess.pgn.read_game(io.StringIO(pgn_str))
    engine = chess.engine.SimpleEngine.popen_uci(sf_path_str)
    try:
        start = time.time()
        mistakes = extract_mistakes(game, engine, depth, player_color)
        elapsed = time.time() - start
    finally:
        engine.quit()
    return idx, total, label, mistakes, elapsed


def _load_existing_training_data(path: Path) -> dict | None:
    """Load existing training_data.json if it exists."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError):
        return None


def prepare_training_data(
    *,
    max_games: int = 20,
    depth: int = 18,
    engine_path: str | None = None,
    fresh: bool = False,
) -> None:
    """Fetch games, analyze with Stockfish, extract mistakes, export training JSON.

    By default, merges with existing training data (incremental mode).
    Only new games are analyzed. SRS progress is preserved.

    Args:
        max_games: Maximum games to fetch per source.
        depth: Stockfish analysis depth.
        engine_path: Override path to Stockfish binary.
        fresh: If True, discard existing data and start from scratch.
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

    root = _find_project_root()
    output_path = root / "training_data.json"

    # Load existing data (incremental mode)
    existing_data = None if fresh else _load_existing_training_data(output_path)
    existing_game_ids: set[str] = set()
    existing_positions: dict[str, dict] = {}  # id -> position (preserves SRS)
    if existing_data:
        for pos in existing_data.get("positions", []):
            existing_positions[pos["id"]] = pos
            game_id = pos.get("game", {}).get("id", "")
            if game_id:
                existing_game_ids.add(game_id)
        if existing_game_ids:
            print(f"  Loaded {len(existing_positions)} existing position(s) from {len(existing_game_ids)} game(s)")

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

    # Filter out already-analyzed games
    new_games = []
    for game in all_games:
        game_id = game.headers.get("Site", "")
        if game_id and game_id in existing_game_ids:
            continue
        new_games.append(game)

    skipped = len(all_games) - len(new_games)
    if skipped:
        print(f"  Skipped {skipped} already-analyzed game(s)")

    if not new_games:
        print("  No new games to analyze.")
        if existing_data:
            print(f"  Existing training data unchanged ({len(existing_positions)} positions)")
        return

    # Analyze new games
    workers = _physical_core_count()
    workers = min(workers, len(new_games))
    print(f"\n  Analyzing {len(new_games)} new game(s) with Stockfish (depth {depth}, {workers} workers)...")
    print("  This may take several minutes...\n")
    all_mistakes: list[dict] = []

    tasks = []
    for i, game in enumerate(new_games):
        player_color = _determine_player_color(game, lichess_user, chesscom_user)
        if player_color is None:
            continue
        white = game.headers.get("White", "?")
        black = game.headers.get("Black", "?")
        exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        pgn_str = game.accept(exporter)
        tasks.append((pgn_str, str(sf_path), depth, player_color, i + 1, len(new_games), f"{white} vs {black}"))

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_analyze_game_worker, *t): t for t in tasks}
        done_count = 0
        total_tasks = len(tasks)
        wall_start = time.time()
        for future in as_completed(futures):
            idx, total, label, mistakes, elapsed = future.result()
            done_count += 1
            all_mistakes.extend(mistakes)

            wall_elapsed = time.time() - wall_start
            avg_per_game = wall_elapsed / done_count
            remaining = avg_per_game * (total_tasks - done_count)
            eta_min, eta_sec = divmod(int(remaining), 60)
            eta_str = f"{eta_min}m{eta_sec:02d}s" if eta_min else f"{eta_sec}s"

            print(
                f"  [{done_count}/{total_tasks}] {label}... "
                f"{len(mistakes)} mistake(s) ({elapsed:.1f}s) "
                f"— ETA {eta_str}"
            )

    # Merge new positions with existing (preserve SRS data)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_count = 0
    for m in all_mistakes:
        if m["id"] in existing_positions:
            continue  # already exists, keep the one with SRS progress
        m["srs"] = {
            "interval": 0,
            "ease": 2.5,
            "next_review": today,
            "history": [],
        }
        existing_positions[m["id"]] = m
        new_count += 1

    # Sort: blunders first, then by cp_loss descending
    severity = {"blunder": 0, "mistake": 1, "inaccuracy": 2}
    all_positions = sorted(
        existing_positions.values(),
        key=lambda m: (severity.get(m["category"], 3), -m["cp_loss"]),
    )

    # Build and write output
    training_data = {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "player": {
            "lichess": lichess_user,
            "chesscom": chesscom_user or "",
        },
        "positions": all_positions,
    }
    with open(output_path, "w") as f:
        json.dump(training_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    total = len(all_positions)
    print(f"\n  Training data exported: {output_path}")
    print(f"  Total positions: {total} ({new_count} new)")
    blunders = sum(1 for m in all_positions if m["category"] == "blunder")
    mistake_count = sum(1 for m in all_positions if m["category"] == "mistake")
    inaccuracies = sum(1 for m in all_positions if m["category"] == "inaccuracy")
    print(f"    Blunders: {blunders}")
    print(f"    Mistakes: {mistake_count}")
    print(f"    Inaccuracies: {inaccuracies}")


def refresh_explanations() -> None:
    """Regenerate explanations in training_data.json without re-running Stockfish.

    Reads existing positions, rebuilds explanations using generate_explanation(),
    and writes back. SRS progress and all other fields are preserved.
    """
    root = _find_project_root()
    data_path = root / "training_data.json"

    if not data_path.exists():
        print("No training data found. Run: chess-self-coach train --prepare", file=sys.stderr)
        sys.exit(1)

    with open(data_path) as f:
        data = json.load(f)

    positions = data.get("positions", [])
    updated = 0
    for pos in positions:
        board = chess.Board(pos["fen"])
        # Parse scores to cp
        score_before_str = pos.get("score_before", "+0.00")
        score_after_str = pos.get("score_after", "+0.00")
        try:
            score_before_cp = int(float(score_before_str) * 100)
        except (ValueError, TypeError):
            score_before_cp = None
        try:
            score_after_cp = int(float(score_after_str) * 100)
        except (ValueError, TypeError):
            score_after_cp = None

        was_mate = score_before_cp is not None and abs(score_before_cp) >= _MATE_CP

        new_explanation = generate_explanation(
            board, pos["player_move"], pos["best_move"],
            pos["cp_loss"], pos["category"],
            was_mate=was_mate, score_after_cp=score_after_cp,
        )
        new_context = _generate_context(
            pos["category"], pos["cp_loss"], was_mate, score_after_cp,
        )
        if new_explanation != pos.get("explanation") or new_context != pos.get("context"):
            pos["explanation"] = new_explanation
            pos["context"] = new_context
            updated += 1

    with open(data_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"  Refreshed {updated}/{len(positions)} explanation(s) in {data_path}")


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
