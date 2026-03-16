"""Stockfish analysis of PGN files.

Walks the full game tree (mainline + variations), adds [%eval] annotations
in standard PGN format, and detects blunders.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import chess
import chess.engine
import chess.pgn

from chess_self_coach.config import check_stockfish_version, find_stockfish, load_config

# Regex to detect existing evaluation annotations
_EVAL_PATTERN = re.compile(r"\[%eval\s+[^\]]+\]")


def _format_score(score: chess.engine.PovScore, turn: chess.Color) -> str:
    """Format an engine score as a standard PGN eval string.

    Args:
        score: The engine's point-of-view score.
        turn: Whose turn it is (chess.WHITE or chess.BLACK).

    Returns:
        Formatted string like "[%eval +0.32]" or "[%eval #-3]".
    """
    relative = score.white()

    if relative.is_mate():
        mate_val = relative.mate()
        sign = "+" if mate_val > 0 else ""
        return f"[%eval #{sign}{mate_val}]"

    cp = relative.score()
    if cp is None:
        return "[%eval 0.00]"
    value = cp / 100.0
    sign = "+" if value >= 0 else ""
    return f"[%eval {sign}{value:.2f}]"


def _has_annotation(comment: str) -> bool:
    """Check if a comment already contains a score annotation."""
    return bool(_EVAL_PATTERN.search(comment))


def _add_annotation_to_comment(comment: str, annotation: str) -> str:
    """Add score annotation to a comment, preserving existing text.

    Args:
        comment: Existing comment (may be empty).
        annotation: The annotation string to add (e.g. "[%eval +0.32]").

    Returns:
        Updated comment with annotation prepended.
    """
    if not comment.strip():
        return f"{annotation} "
    return f"{annotation} {comment}"


def _extract_score_value(comment: str) -> float | None:
    """Extract the numeric score value from an existing annotation.

    Args:
        comment: Comment string that may contain [%eval ...].

    Returns:
        Score as float (white perspective), or None if not parseable.
    """
    match = _EVAL_PATTERN.search(comment)
    if not match:
        return None
    text = match.group()
    try:
        val = text.split()[1].rstrip("]")
        if val.startswith("#"):
            return None
        return float(val)
    except (IndexError, ValueError):
        return None


def _analyze_node(
    node: chess.pgn.GameNode,
    engine: chess.engine.SimpleEngine,
    depth: int,
    threshold: float,
    prev_score: float | None,
    stats: dict,
) -> None:
    """Recursively analyze a game node and all its variations.

    Args:
        node: Current game node.
        engine: Running Stockfish engine.
        depth: Analysis depth.
        threshold: Score swing threshold for blunder detection.
        prev_score: Previous position's score (white perspective).
        stats: Mutable dict tracking analysis statistics.
    """
    board = node.board()
    current_score = prev_score

    # Analyze this position if no existing annotation
    if not _has_annotation(node.comment):
        info = engine.analyse(board, chess.engine.Limit(depth=depth))
        score = info.get("score")
        if score:
            annotation = _format_score(score, board.turn)
            node.comment = _add_annotation_to_comment(node.comment, annotation)
            stats["analyzed"] += 1

            # Track score for blunder detection
            white_score = score.white()
            if not white_score.is_mate() and white_score.score() is not None:
                current_score = white_score.score() / 100.0
    else:
        stats["skipped"] += 1
        current_score = _extract_score_value(node.comment) or current_score

    # Blunder detection: large score swing
    if prev_score is not None and current_score is not None:
        swing = abs(current_score - prev_score)
        if swing >= threshold:
            parent_move = ""
            if node.parent and node.move:
                parent_move = f" (after {node.parent.board().san(node.move)})"
            print(
                f"  ⚠ Blunder detected{parent_move}: "
                f"score {prev_score:+.2f} → {current_score:+.2f} "
                f"(swing {swing:.2f})",
                file=sys.stderr,
            )
            stats["blunders"] += 1

    # Recurse into all variations
    for variation in node.variations:
        _analyze_node(variation, engine, depth, threshold, current_score, stats)


def analyze_pgn(
    pgn_path: str | Path,
    *,
    depth: int = 18,
    threshold: float = 1.0,
    engine_path: str | None = None,
    in_place: bool = False,
) -> None:
    """Analyze a PGN file with Stockfish and add score annotations.

    Walks every game and every variation in the PGN, adds [%eval] annotations
    in standard PGN format, skips positions that already have annotations.

    Args:
        pgn_path: Path to the PGN file.
        depth: Stockfish analysis depth (default: 18).
        threshold: Score swing threshold for blunder detection (default: 1.0).
        engine_path: Override path to the Stockfish binary.
        in_place: If True, overwrite the original file. Otherwise write to *_analyzed.pgn.
    """
    pgn_path = Path(pgn_path)
    if not pgn_path.exists():
        print(f"❌ File not found: {pgn_path}", file=sys.stderr)
        sys.exit(1)

    # Find Stockfish
    if engine_path:
        sf_path = Path(engine_path)
        if not sf_path.exists():
            print(f"❌ Engine not found: {sf_path}", file=sys.stderr)
            sys.exit(1)
    else:
        config = load_config()
        sf_path = find_stockfish(config)
        expected = config.get("stockfish", {}).get("expected_version")
        version = check_stockfish_version(sf_path, expected)
        print(f"  Using {version} at {sf_path}")

    # Determine output path
    if in_place:
        output_path = pgn_path
    else:
        output_path = pgn_path.with_name(
            pgn_path.stem.replace("_annote", "_analyzed") + pgn_path.suffix
        )
        if output_path == pgn_path:
            output_path = pgn_path.with_name(pgn_path.stem + "_analyzed" + pgn_path.suffix)

    stats = {"analyzed": 0, "skipped": 0, "blunders": 0, "games": 0}
    start_time = time.time()

    # Parse all games
    games = []
    with open(pgn_path) as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            games.append(game)

    print(f"  Found {len(games)} game(s) in {pgn_path.name}")

    engine = chess.engine.SimpleEngine.popen_uci(str(sf_path))
    try:
        for i, game in enumerate(games):
            event = game.headers.get("Event", f"Game {i + 1}")
            print(f"  Analyzing: {event}...")
            _analyze_node(game, engine, depth, threshold, None, stats)
            stats["games"] += 1
    finally:
        engine.quit()

    # Write output
    with open(output_path, "w") as f:
        for i, game in enumerate(games):
            if i > 0:
                f.write("\n")
            print(game, file=f, end="\n\n")

    elapsed = time.time() - start_time
    print(f"\n  Done in {elapsed:.1f}s")
    print(f"  Positions analyzed: {stats['analyzed']}")
    print(f"  Positions skipped (already had annotation): {stats['skipped']}")
    if stats["blunders"]:
        print(f"  ⚠ Blunders detected: {stats['blunders']}")
    print(f"  Output: {output_path}")
