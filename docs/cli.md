# CLI Reference

!!! note
    The CLI is for **dev and batch operations**. The primary training experience is the [PWA](training.md).

## train

Training mode: extract mistakes from your games and generate training data.

```bash
chess-self-coach train [options]
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--prepare` | off | Fetch games, run full analysis (SF + Opening Explorer + Tablebase), write `analysis_data.json` + `training_data.json` |
| `--derive` | off | Re-derive `training_data.json` from `analysis_data.json` (no Stockfish needed, fast) |
| `--serve` | off | Open the training PWA in the browser |
| `--stats` | off | Show training progress statistics |
| `--games N` | 10 | Maximum games to analyze |
| `--depth N` | 18 | Stockfish analysis depth (default bracket for >12 pieces) |
| `--threads N` | auto | Stockfish threads (default: CPU count - 1) |
| `--hash N` | 1024 | Stockfish hash table size in MB |
| `--reanalyze-all` | off | Re-analyze all games (skip only those with identical settings) |
| `--engine PATH` | config.json | Override Stockfish binary path |
| `--refresh-explanations` | off | [Dev] Regenerate explanations without re-running Stockfish |
| `--fresh` | off | [Dev] Discard existing training data and start from scratch |

### Examples

```bash
# Fetch + analyze 10 games (default) with full pipeline
chess-self-coach train --prepare

# Analyze 5 games with custom engine settings
chess-self-coach train --prepare --games 5 --threads 4 --hash 2048

# Re-derive training data from existing analysis (no Stockfish, fast)
chess-self-coach train --derive

# Re-analyze all games with new settings
chess-self-coach train --prepare --reanalyze-all --threads 8

# Open the training interface
chess-self-coach train --serve

# Check your stats
chess-self-coach train --stats
```

### Two-phase pipeline

`--prepare` runs two phases:

1. **Phase 1 (collection)**: Lichess Opening Explorer + Stockfish eval + Lichess Tablebase for each move. Opening book moves skip Stockfish (eval sourced from explorer); Stockfish runs from the theory departure onward. Results stored in `analysis_data.json` (atomic write after each game, crash-safe).
2. **Phase 2 (derivation)**: Filter player mistakes, generate explanations, write `training_data.json`.

`--derive` runs Phase 2 only — useful to iterate on thresholds or explanations without re-running Stockfish.

## update

Update chess-self-coach to the latest version.

```bash
chess-self-coach update
```

## analyze

Analyze a PGN file with Stockfish and add `[%eval]` annotations.

```bash
chess-self-coach analyze <file.pgn> [options]
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--depth N` | 18 | Stockfish analysis depth |
| `--threshold N` | 1.0 | Score swing threshold for blunder detection |
| `--engine PATH` | config.json | Override Stockfish binary path |
| `--in-place` | off | Overwrite original file (default: `*_analyzed.pgn`) |

### Examples

```bash
# Analyze with default settings (depth 18)
chess-self-coach analyze pgn/repertoire_blancs_gambit_dame_annote.pgn

# Quick analysis at depth 12
chess-self-coach analyze pgn/repertoire_blancs_gambit_dame_annote.pgn --depth 12

# Overwrite original file
chess-self-coach analyze pgn/repertoire_blancs_gambit_dame_annote.pgn --in-place

# Use a specific Stockfish binary
chess-self-coach analyze pgn/repertoire_blancs_gambit_dame_annote.pgn --engine /usr/games/stockfish
```

## setup

Interactive setup wizard.

```bash
chess-self-coach setup
```

Verifies Lichess authentication, finds existing studies, and configures `config.json`.

## push

Push a local PGN file to its mapped Lichess study.

```bash
chess-self-coach push <file.pgn>
```

!!! warning
    Lichess import **adds** chapters. If chapters already exist, duplicates will be created.

## pull

Pull the latest PGN from a Lichess study to a local file.

```bash
chess-self-coach pull <file.pgn> [--in-place]
```

By default, writes to `*_from_lichess.pgn`. Use `--in-place` to overwrite.

## cleanup

Remove empty default chapters (e.g. "Chapter 1") from Lichess studies.

```bash
# Clean up all configured studies
chess-self-coach cleanup

# Clean up a specific study
chess-self-coach cleanup pgn/repertoire_blancs_gambit_dame_annote.pgn
```

Lichess auto-creates an empty "Chapter 1" when a study is created. After importing PGN via `push`, this leaves a stale empty chapter. The `cleanup` command removes these.

!!! note
    `push` runs cleanup automatically after import — you only need this command for manual cleanup.

## syzygy

Manage Syzygy endgame tablebases (3-5 pieces, ~1 GB).

```bash
chess-self-coach syzygy download    # download tables to ~/.local/share/syzygy/
chess-self-coach syzygy status      # show installed tables info
```

Stockfish uses these tables during search for faster, exact endgame analysis. Tables are also downloaded automatically during `setup` and `install.sh`.

## status

Show sync status of all repertoire files.

```bash
chess-self-coach status
```

Displays: file modification times, chapter counts, Stockfish availability, Lichess configuration, and suggested next actions.
