"""Command-line interface for chess-self-coach.

Entry point for the CLI. Dispatches to subcommands: analyze, validate, import, setup, push, pull, status, train.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from chess_self_coach import __version__


def main(argv: list[str] | None = None) -> None:
    """Main CLI entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).
    """
    parser = argparse.ArgumentParser(
        prog="chess-self-coach",
        description="Manage a chess opening repertoire: Stockfish analysis + Lichess Study sync.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- analyze ---
    p_analyze = subparsers.add_parser(
        "analyze",
        help="Analyze a PGN file with Stockfish and add [%%eval] annotations",
    )
    p_analyze.add_argument("pgn_file", help="Path to the PGN file to analyze")
    p_analyze.add_argument(
        "--depth",
        type=int,
        default=18,
        help="Stockfish analysis depth (default: 18)",
    )
    p_analyze.add_argument(
        "--threshold",
        type=float,
        default=1.0,
        help="Score swing threshold for blunder detection (default: 1.0)",
    )
    p_analyze.add_argument(
        "--engine",
        type=str,
        default=None,
        help="Path to the Stockfish binary (overrides config.json)",
    )
    p_analyze.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite the original file instead of creating *_analyzed.pgn",
    )

    # --- setup ---
    subparsers.add_parser(
        "setup",
        help="Interactive setup: verify auth, find studies, configure config.json",
    )

    # --- update ---
    subparsers.add_parser(
        "update",
        help="Update chess-self-coach to the latest version",
    )

    # --- push ---
    p_push = subparsers.add_parser(
        "push",
        help="Push a local PGN file to its mapped Lichess study",
    )
    p_push.add_argument("pgn_file", help="Path to the PGN file to push")
    p_push.add_argument(
        "--no-replace",
        action="store_true",
        dest="no_replace",
        help="Append chapters instead of replacing (default: replace all existing chapters)",
    )

    # --- pull ---
    p_pull = subparsers.add_parser(
        "pull",
        help="Pull the latest PGN from a Lichess study to a local file",
    )
    p_pull.add_argument("pgn_file", help="PGN filename to pull (used to look up study mapping)")
    p_pull.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite the local file instead of creating *_from_lichess.pgn",
    )

    # --- cleanup ---
    p_cleanup = subparsers.add_parser(
        "cleanup",
        help="Remove empty default chapters (e.g. 'Chapter 1') from Lichess studies",
    )
    p_cleanup.add_argument(
        "pgn_file",
        nargs="?",
        default=None,
        help="PGN file to clean up (default: all configured studies)",
    )

    # --- validate ---
    p_validate = subparsers.add_parser(
        "validate",
        help="Validate PGN annotations against mandatory conventions",
    )
    p_validate.add_argument("pgn_file", help="Path to the PGN file to validate")

    # --- import ---
    p_import = subparsers.add_parser(
        "import",
        help="Import games from Lichess/chess.com and analyze deviations from repertoire",
    )
    p_import.add_argument("username", help="Lichess username")
    p_import.add_argument(
        "--chesscom",
        type=str,
        default=None,
        help="Chess.com username (to also fetch games from chess.com)",
    )
    p_import.add_argument(
        "--max",
        type=int,
        default=100,
        dest="max_games",
        help="Maximum number of games to fetch per source (default: 100)",
    )

    # --- status ---
    subparsers.add_parser(
        "status",
        help="Show sync status of all repertoire files",
    )

    # --- train ---
    p_train = subparsers.add_parser(
        "train",
        help="Training mode: extract mistakes from games and drill with spaced repetition",
    )
    p_train.add_argument(
        "--prepare",
        action="store_true",
        help="Analyze games and export training_data.json",
    )
    p_train.add_argument(
        "--serve",
        action="store_true",
        help="Open the training PWA in the browser",
    )
    p_train.add_argument(
        "--stats",
        action="store_true",
        help="Show training progress statistics",
    )
    p_train.add_argument(
        "--games",
        type=int,
        default=20,
        help="Maximum games to fetch per source (default: 20)",
    )
    p_train.add_argument(
        "--depth",
        type=int,
        default=18,
        help="Stockfish analysis depth (default: 18)",
    )
    p_train.add_argument(
        "--engine",
        type=str,
        default=None,
        help="Path to the Stockfish binary (overrides config.json)",
    )
    p_train.add_argument(
        "--refresh-explanations",
        action="store_true",
        dest="refresh_explanations",
        help="[Dev] Regenerate explanations without re-running Stockfish",
    )
    p_train.add_argument(
        "--fresh",
        action="store_true",
        help="[Dev] Discard existing training data and start from scratch",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        _launch_server()
        return

    if args.command == "analyze":
        from chess_self_coach.analyze import analyze_pgn

        try:
            analyze_pgn(
                args.pgn_file,
                depth=args.depth,
                threshold=args.threshold,
                engine_path=args.engine,
                in_place=args.in_place,
            )
        except FileNotFoundError as e:
            print(f"  {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "setup":
        from chess_self_coach.lichess import setup

        setup()

    elif args.command == "update":
        from chess_self_coach.updater import update

        update()

    elif args.command == "push":
        from chess_self_coach.config import load_lichess_token

        if not load_lichess_token(required=False):
            print("Lichess token required for push. Set LICHESS_API_TOKEN in .env", file=sys.stderr)
            sys.exit(1)
        from chess_self_coach.lichess import push_pgn

        try:
            push_pgn(args.pgn_file, replace=not args.no_replace)
        except FileNotFoundError as e:
            print(f"  {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "pull":
        from chess_self_coach.config import load_lichess_token

        if not load_lichess_token(required=False):
            print("Lichess token required for pull. Set LICHESS_API_TOKEN in .env", file=sys.stderr)
            sys.exit(1)
        from chess_self_coach.lichess import pull_pgn

        pull_pgn(args.pgn_file, in_place=args.in_place)

    elif args.command == "cleanup":
        from chess_self_coach.config import load_lichess_token

        if not load_lichess_token(required=False):
            print("Lichess token required for cleanup. Set LICHESS_API_TOKEN in .env", file=sys.stderr)
            sys.exit(1)
        from chess_self_coach.lichess import cleanup_study
        from chess_self_coach.config import load_config, get_study_mapping

        config = load_config()
        studies = config.get("studies", {})

        if args.pgn_file:
            pgn_name = Path(args.pgn_file).name
            mapping = get_study_mapping(config, pgn_name)
            total = cleanup_study(mapping["study_id"], mapping.get("study_name", ""))
        else:
            total = 0
            for pgn_file, info in studies.items():
                study_id = info.get("study_id", "")
                if study_id.startswith("STUDY_ID"):
                    continue
                total += cleanup_study(study_id, info.get("study_name", pgn_file))

        if total == 0:
            print("  ✓ No empty default chapters found")
        else:
            print(f"\n  ✓ Cleaned up {total} empty chapter(s) total")

    elif args.command == "validate":
        from chess_self_coach.validate import print_report, validate_pgn

        try:
            results = validate_pgn(args.pgn_file)
        except FileNotFoundError as e:
            print(f"  {e}", file=sys.stderr)
            sys.exit(1)
        has_errors = print_report(results)
        if has_errors:
            sys.exit(1)

    elif args.command == "import":
        from chess_self_coach.importer import import_games

        import_games(
            args.username,
            chesscom=args.chesscom,
            max_games=args.max_games,
        )

    elif args.command == "status":
        from chess_self_coach.status import show_status

        show_status()

    elif args.command == "train":
        from chess_self_coach.trainer import (
            prepare_training_data,
            print_stats,
        )

        if args.refresh_explanations:
            from chess_self_coach.trainer import refresh_explanations

            refresh_explanations()
        elif args.prepare:
            try:
                prepare_training_data(
                    max_games=args.games,
                    depth=args.depth,
                    engine_path=args.engine,
                    fresh=args.fresh,
                )
            except (FileNotFoundError, RuntimeError) as e:
                print(f"  {e}", file=sys.stderr)
                sys.exit(1)
        elif args.serve:
            print("  Tip: you can now just run `chess-self-coach` directly.\n")
            _launch_server()
        elif args.stats:
            print_stats()
        else:
            print("Usage: chess-self-coach train [--prepare|--serve|--stats]")
            print("Run 'chess-self-coach train -h' for details.")


def _launch_server() -> None:
    """Check for updates and start the FastAPI server."""
    from chess_self_coach.updater import check_update

    available, latest = check_update()
    if available:
        answer = input(
            f"  Version {latest} available (current: {__version__}). "
            "Update now? [y/N] ",
        )
        if answer.strip().lower() == "y":
            from chess_self_coach.updater import update

            update()
            print("  Please re-run: chess-self-coach")
            sys.exit(0)

    from chess_self_coach.updater import check_stockfish_update

    sf_available, sf_installed, sf_latest = check_stockfish_update()
    if sf_available:
        print(
            f"  Stockfish update: {sf_latest} available (current: {sf_installed}).\n"
            "  Update with: sudo apt install stockfish  (Linux) or  brew upgrade stockfish  (macOS)\n"
        )

    from chess_self_coach.server import run_server

    run_server()


if __name__ == "__main__":
    main()
