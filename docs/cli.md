# CLI Reference

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

## status

Show sync status of all repertoire files.

```bash
chess-self-coach status
```

Displays: file modification times, chapter counts, Stockfish availability, Lichess configuration, and suggested next actions.
