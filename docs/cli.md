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
| `--prepare` | off | Fetch games, run full analysis (SF + Opening Explorer + Tablebase), write `data/analysis_data.json` + `data/training_data.json` |
| `--derive` | off | Re-derive `data/training_data.json` from `data/analysis_data.json` (no Stockfish needed, fast) |
| `--serve` | off | Open the training PWA in the browser |
| `--stats` | off | Show training progress statistics |
| `--games N` | 10 | Maximum games to analyze |
| `--depth N` | 18 | Stockfish analysis depth (default bracket for >12 pieces) |
| `--threads N` | auto | Stockfish threads (default: CPU count - 1) |
| `--hash N` | 1024 | Stockfish hash table size in MB |
| `--reanalyze-all` | off | Re-analyze all games (skip only those with identical settings) |
| `--engine PATH` | data/config.json | Override Stockfish binary path |
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

1. **Phase 1 (collection)**: Lichess Opening Explorer (Masters primary, Lichess fallback) + Stockfish eval + Lichess Tablebase for each move. Opening book moves use cloud eval (fast); Stockfish runs from the theory departure onward. Only Masters-confirmed moves are marked as real theory (`in_opening=True`). Results stored in `data/analysis_data.json` (atomic write after each game, crash-safe).
2. **Phase 2 (derivation)**: Filter player mistakes, generate explanations, write `data/training_data.json`.

`--derive` runs Phase 2 only — useful to iterate on thresholds or explanations without re-running Stockfish.

## update

Update chess-self-coach to the latest version.

```bash
chess-self-coach update
```

## setup

Interactive setup wizard.

```bash
chess-self-coach setup
```

Configures Stockfish, Lichess token, chess.com username, and saves `data/config.json`.

## syzygy

Manage Syzygy endgame tablebases (3-5 pieces, ~1 GB).

```bash
chess-self-coach syzygy download    # download tables to ~/.local/share/syzygy/
chess-self-coach syzygy status      # show installed tables info
```

Stockfish uses these tables during search for faster, exact endgame analysis. Tables are also downloaded automatically during `setup` and `install.sh`.

