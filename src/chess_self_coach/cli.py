"""Command-line interface for chess-self-coach.

Entry point for the CLI. Dispatches to subcommands: setup, train, update, syzygy.
"""

from __future__ import annotations

import argparse
import sys

from chess_self_coach import __version__


def main(argv: list[str] | None = None) -> None:
    """Main CLI entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).
    """
    parser = argparse.ArgumentParser(
        prog="chess-self-coach",
        description="Learn from your chess mistakes: Stockfish analysis + spaced repetition training.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- setup ---
    subparsers.add_parser(
        "setup",
        help="Interactive setup: verify Stockfish, configure game platforms",
    )

    # --- update ---
    subparsers.add_parser(
        "update",
        help="Update chess-self-coach to the latest version",
    )

    # --- syzygy ---
    p_syzygy = subparsers.add_parser(
        "syzygy",
        help="Manage Syzygy endgame tablebases",
    )
    p_syzygy.add_argument(
        "action",
        choices=["download", "status"],
        help="download: fetch 3-5 piece tables (~1 GB). status: show installed tables.",
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
        "--derive",
        action="store_true",
        help="Re-derive training_data.json from analysis_data.json (no Stockfish needed)",
    )
    p_train.add_argument(
        "--games",
        type=int,
        default=10,
        help="Maximum games to analyze (default: 10)",
    )
    p_train.add_argument(
        "--depth",
        type=int,
        default=18,
        help="Stockfish analysis depth (default: 18)",
    )
    p_train.add_argument(
        "--threads",
        type=int,
        default=None,
        help="Stockfish threads (default: auto = CPU count - 1)",
    )
    p_train.add_argument(
        "--hash",
        type=int,
        default=None,
        dest="hash_mb",
        help="Stockfish hash table size in MB (default: 1024)",
    )
    p_train.add_argument(
        "--reanalyze-all",
        action="store_true",
        dest="reanalyze_all",
        help="Re-analyze all games (skip only those with identical settings)",
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

    if args.command == "setup":
        _setup()

    elif args.command == "update":
        from chess_self_coach.updater import update

        update()

    elif args.command == "syzygy":
        from chess_self_coach.syzygy import download_syzygy, syzygy_status

        if args.action == "download":
            try:
                path = download_syzygy()
                print(f"  ✓ Syzygy tables downloaded to {path}")
            except (FileNotFoundError, Exception) as e:
                print(f"  ❌ {e}", file=sys.stderr)
                sys.exit(1)
        elif args.action == "status":
            from chess_self_coach.config import load_config

            config = load_config()
            status = syzygy_status(config)
            if status["found"]:
                print(f"  Path: {status['path']}")
                print(f"  WDL files: {status['wdl_count']}")
                print(f"  DTZ files: {status['dtz_count']}")
                print(f"  Total size: {status['total_size_mb']} MB")
            else:
                print("  No Syzygy tables found.")
                print("  Download with: chess-self-coach syzygy download")

    elif args.command == "train":
        if args.derive:
            from chess_self_coach.analysis import annotate_and_derive

            try:
                annotate_and_derive()
            except (FileNotFoundError, RuntimeError) as e:
                print(f"  {e}", file=sys.stderr)
                sys.exit(1)
        elif args.refresh_explanations:
            from chess_self_coach.trainer import refresh_explanations

            refresh_explanations()
        elif args.prepare:
            from chess_self_coach.analysis import AnalysisSettings, analyze_games

            # Build settings from config, with CLI overrides
            from chess_self_coach.config import load_config

            config = load_config()
            settings = AnalysisSettings.from_config(config)
            if args.threads is not None:
                settings.threads = args.threads
            if args.hash_mb is not None:
                settings.hash_mb = args.hash_mb

            try:
                analyze_games(
                    max_games=args.games,
                    reanalyze_all=args.reanalyze_all,
                    settings=settings,
                    engine_path=args.engine,
                )
            except (FileNotFoundError, RuntimeError) as e:
                print(f"  {e}", file=sys.stderr)
                sys.exit(1)
        elif args.serve:
            print("  Tip: you can now just run `chess-self-coach` directly.\n")
            _launch_server()
        elif args.stats:
            from chess_self_coach.trainer import print_stats

            print_stats()
        else:
            print("Usage: chess-self-coach train [--prepare|--derive|--serve|--stats]")
            print("Run 'chess-self-coach train -h' for details.")


def _setup() -> None:
    """Interactive setup: Stockfish, Syzygy, game platforms."""
    from chess_self_coach.config import (
        check_stockfish_version,
        config_path,
        find_stockfish,
        load_config,
        save_config,
    )

    print("\n  === Chess Self-Coach Setup ===\n")

    # Step 1: Stockfish
    print("  Step 1: Stockfish engine")
    try:
        sf_path = find_stockfish()
        version = check_stockfish_version(sf_path)
        print(f"  ✓ Found: {sf_path} ({version})\n")
    except SystemExit:
        return

    # Step 1b: Syzygy tablebases
    print("  Step 2: Syzygy endgame tablebases")
    try:
        from chess_self_coach.syzygy import find_syzygy

        syzygy_path = find_syzygy()
        print(f"  ✓ Found: {syzygy_path}\n")
    except FileNotFoundError:
        answer = input("  Syzygy tables not found. Download (~1 GB)? [y/N] ")
        if answer.strip().lower() == "y":
            from chess_self_coach.syzygy import download_syzygy

            try:
                syzygy_path = download_syzygy()
                print(f"  ✓ Downloaded to {syzygy_path}\n")
            except Exception as e:
                print(f"  ⚠ Download failed: {e}. You can retry later.\n")

    # Step 2: Game platforms
    print("  Step 3: Game platforms (at least one required)\n")

    lichess_user = input("  Lichess username (leave empty to skip): ").strip()
    lichess_token = None
    if lichess_user:
        print(
            "\n  A Lichess API token is needed to fetch your games.\n"
            "  Create one at: https://lichess.org/account/oauth/token/create\n"
        )
        lichess_token = input("  Lichess API token (lip_...): ").strip()

    chesscom_user = input("\n  Chess.com username (leave empty to skip): ").strip()

    if not lichess_user and not chesscom_user:
        print("\n  ❌ At least one platform is required.")
        sys.exit(1)

    # Write config
    cfg = config_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    try:
        config = load_config()
    except SystemExit:
        config = {}

    config["stockfish"] = {"path": str(sf_path)}
    players: dict[str, str] = {}
    if lichess_user:
        players["lichess"] = lichess_user
    if chesscom_user:
        players["chesscom"] = chesscom_user
    config["players"] = players

    # Remove legacy studies section if present
    config.pop("studies", None)

    save_config(config)

    # Write .env if token provided
    if lichess_token:
        from chess_self_coach.config import _find_project_root

        env_path = _find_project_root() / ".env"
        with open(env_path, "w") as f:
            f.write(f"LICHESS_API_TOKEN={lichess_token}\n")
        print(f"\n  ✓ Token saved to {env_path}")
    print("\n  Setup complete! Run 'chess-self-coach train --prepare' to start.\n")


def _launch_server() -> None:
    """Check for updates and start the FastAPI server."""
    from chess_self_coach.updater import check_update

    available, _pypi_ver = check_update()
    if available:
        answer = input(
            f"  Update available (current: v{__version__}). "
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
