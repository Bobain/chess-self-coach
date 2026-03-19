"""PGN annotation linter.

Checks that PGN files follow the MANDATORY annotation conventions:
opening names, ECO codes, theory markers, traps, plans, and move comments.
"""

from __future__ import annotations

import re
from pathlib import Path

import chess.pgn


# Patterns for convention checks
_ECO_PATTERN = re.compile(r"ECO [A-E]\d{2}")
_THEORY_PATTERN = re.compile(r"THEORY:", re.IGNORECASE)
_TRAP_PATTERN = re.compile(r"\b(TRAP|WARNING)\b", re.IGNORECASE)
_MISTAKE_PATTERN = re.compile(r"TYPICAL MISTAKE", re.IGNORECASE)
_PLAN_PATTERN = re.compile(r"Plan:", re.IGNORECASE)
_EVAL_ONLY_PATTERN = re.compile(r"^\s*\[%eval\s+[^\]]+\]\s*$")

# Known opening/variation keywords (non-exhaustive, used as heuristic)
_OPENING_KEYWORDS = [
    "gambit", "defense", "defence", "attack", "variation", "system",
    "opening", "indian", "sicilian", "french", "caro", "scandinavian",
    "slav", "dutch", "english", "italian", "spanish", "ruy",
    "queen's", "king's", "nimzo", "grunfeld", "catalan",
    "pirc", "alekhine", "petroff", "philidor", "vienna",
    "london", "colle", "torre", "trompowsky", "czech",
    "marshall", "fianchetto", "harrwitz", "rubinstein",
    "exchange", "advance", "classical", "modern",
    "albin", "icelandic", "danish", "evans", "scotch",
]


def _has_opening_name(comments: list[str]) -> bool:
    """Check if any comment mentions a recognizable opening/variation name.

    Args:
        comments: List of comment strings from the chapter.

    Returns:
        True if at least one comment contains an opening name keyword.
    """
    text = " ".join(comments).lower()
    return any(kw in text for kw in _OPENING_KEYWORDS)


def _collect_comments(node: chess.pgn.GameNode) -> list[str]:
    """Recursively collect all comments from a game tree.

    Args:
        node: Root game node.

    Returns:
        List of non-empty comment strings.
    """
    comments = []
    if node.comment and node.comment.strip():
        comments.append(node.comment)
    for variation in node.variations:
        comments.extend(_collect_comments(variation))
    return comments


def _count_uncommented_mainline(game: chess.pgn.Game) -> int:
    """Count mainline moves that lack a comment (ignoring eval-only comments).

    Args:
        game: Parsed PGN game.

    Returns:
        Number of uncommented mainline moves.
    """
    count = 0
    node = game
    while node.variations:
        node = node.variations[0]
        comment = node.comment.strip() if node.comment else ""
        if not comment or _EVAL_ONLY_PATTERN.match(comment):
            count += 1
    return count


def _get_last_mainline_comment(game: chess.pgn.Game) -> str:
    """Get the comment on the last mainline move.

    Args:
        game: Parsed PGN game.

    Returns:
        Comment string (may be empty).
    """
    node = game
    while node.variations:
        node = node.variations[0]
    return node.comment.strip() if node.comment else ""


def validate_pgn(pgn_path: str | Path) -> list[dict]:
    """Validate a PGN file against annotation conventions.

    Checks each chapter (game) for mandatory annotation elements:
    opening names, ECO codes, theory markers, traps, plans, and move comments.

    Args:
        pgn_path: Path to the PGN file to validate.

    Returns:
        List of dicts, one per chapter: {name, errors, warnings, infos}.
    """
    pgn_path = Path(pgn_path)
    if not pgn_path.exists():
        raise FileNotFoundError(f"File not found: {pgn_path}")

    results = []

    with open(pgn_path) as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break

            name = game.headers.get("Event", "Unnamed")
            errors: list[str] = []
            warnings: list[str] = []
            infos: list[str] = []

            comments = _collect_comments(game)
            all_text = " ".join(comments)

            # empty_chapter: no comments at all → error
            if not comments:
                errors.append("empty_chapter: no comments found")
                results.append({
                    "name": name,
                    "errors": errors,
                    "warnings": warnings,
                    "infos": infos,
                })
                continue

            # opening_name: comment mentions an official opening/variation name
            if not _has_opening_name(comments):
                warnings.append(
                    "opening_name: no official opening/variation name found in comments"
                )

            # eco_code: at least one comment references ECO code
            if not _ECO_PATTERN.search(all_text):
                warnings.append("eco_code: no ECO code reference found (e.g. ECO D37)")

            # theory_marker: at least one THEORY: marker
            if _THEORY_PATTERN.search(all_text):
                infos.append("theory_marker: THEORY: marker present")
            else:
                infos.append("theory_marker: no THEORY: marker found")

            # trap_marker: TRAP or WARNING present
            if _TRAP_PATTERN.search(all_text):
                infos.append("trap_marker: TRAP/WARNING marker present")
            else:
                infos.append("trap_marker: no TRAP/WARNING marker found")

            # typical_mistake: TYPICAL MISTAKE present
            if _MISTAKE_PATTERN.search(all_text):
                infos.append("typical_mistake: TYPICAL MISTAKE marker present")
            else:
                infos.append("typical_mistake: no TYPICAL MISTAKE marker found")

            # plan: last mainline move comment contains "Plan:"
            last_comment = _get_last_mainline_comment(game)
            if not _PLAN_PATTERN.search(last_comment):
                warnings.append(
                    "plan: last mainline move comment does not contain 'Plan:'"
                )

            # move_comments: mainline moves should have comments explaining WHY
            uncommented = _count_uncommented_mainline(game)
            if uncommented > 0:
                warnings.append(
                    f"move_comments: {uncommented} mainline move(s) without explanatory comment"
                )

            results.append({
                "name": name,
                "errors": errors,
                "warnings": warnings,
                "infos": infos,
            })

    return results


def print_report(results: list[dict]) -> bool:
    """Print a formatted validation report.

    Args:
        results: Validation results from validate_pgn().

    Returns:
        True if any errors were found.
    """
    has_errors = False

    for chapter in results:
        name = chapter["name"]
        errors = chapter["errors"]
        warnings = chapter["warnings"]
        infos = chapter["infos"]

        status = "ERROR" if errors else "OK" if not warnings else "WARN"
        print(f"\n  [{status}] {name}")

        for e in errors:
            print(f"    ERROR: {e}")
            has_errors = True
        for w in warnings:
            print(f"    WARN:  {w}")
        for i in infos:
            print(f"    INFO:  {i}")

    # Overall summary
    total = len(results)
    error_count = sum(1 for r in results if r["errors"])
    warn_count = sum(1 for r in results if r["warnings"] and not r["errors"])
    ok_count = total - error_count - warn_count

    print(f"\n  Summary: {total} chapter(s) — {ok_count} OK, {warn_count} WARN, {error_count} ERROR")

    return has_errors
