# chess-opening-prep

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

CLI to manage a chess opening repertoire: Stockfish analysis + Lichess Study sync.

Automates the workflow between local PGN files, Stockfish engine analysis, and Lichess Studies for spaced-repetition drilling via [Chessdriller](https://chessdriller.org/).

## Openings Covered

| Color | Opening | Key Variation |
|-------|---------|--------------|
| White | Queen's Gambit (1.d4 2.c4) | Harrwitz Attack (5.Bf4) vs QGD |
| Black vs 1.e4 | Modern Scandinavian (1...d5 2.exd5 Nf6) | Fianchetto setup (...g6/...Bg7) |
| Black vs 1.d4 | Slav Defense (1...d5 2...c6) | Czech Variation (...dxc4, ...Bf5 BEFORE e6) |
| Black vs London | Anti-London with immediate ...c5 | |

## Prerequisites & Account Setup

### 1. Lichess Account

1. Create an account at [lichess.org/signup](https://lichess.org/signup) (free)
2. Create an API token:
   - Go to [lichess.org/account/oauth/token/create](https://lichess.org/account/oauth/token/create)
   - **Token description**: `chess-opening-prep`
   - Under **STUDIES & BROADCASTS**, check:
     - "Read private studies and broadcasts" (`study:read`)
     - "Create, update, delete studies and broadcasts" (`study:write`)
   - Do NOT check any other scopes
   - Click **Submit** — copy the token immediately (shown only once, starts with `lip_`)
3. Test your token:
   ```bash
   curl -H "Authorization: Bearer lip_your_token" https://lichess.org/api/account
   ```

### 2. Chessdriller

1. Go to [chessdriller.org](https://chessdriller.org/)
2. Log in with your Lichess account (OAuth — no separate account needed)
3. Chessdriller reads directly from your Lichess Studies — no additional configuration

### 3. Stockfish

The CLI uses Stockfish for position analysis. It searches for Stockfish in this order:
1. Path specified in `config.json`
2. System Stockfish (`/usr/games/stockfish` or in `$PATH`)
3. Custom path via `--engine` flag

To install system Stockfish: `sudo apt install stockfish`

### 4. En-Croissant (Optional)

[En-Croissant](https://encroissant.org/) is a desktop chess GUI for offline visual review of PGN files. It is **not required** — Lichess Study provides the same interactive study features online.

If used, note that En-Croissant modifies PGN files while they're open — always close files before running CLI commands.

## Installation

```bash
# From PyPI
pip install chess-opening-prep

# From source (development)
git clone https://github.com/Bobain/chess-opening-prep.git
cd chess-opening-prep
uv venv && uv sync
```

## Configuration

```bash
# Save your Lichess token
echo "LICHESS_API_TOKEN=lip_your_token_here" > .env

# Run interactive setup (verifies auth, finds studies, configures config.json)
chess-opening-prep setup
```

## CLI Reference

### `chess-opening-prep analyze <file.pgn>`

Analyze a PGN file with Stockfish. Adds `[%eval]` annotations in standard PGN format.

```bash
chess-opening-prep analyze pgn/repertoire_blancs_gambit_dame_annote.pgn
chess-opening-prep analyze pgn/repertoire_blancs_gambit_dame_annote.pgn --depth 12
chess-opening-prep analyze pgn/repertoire_blancs_gambit_dame_annote.pgn --in-place
```

Options:
- `--depth N` — Analysis depth (default: 18)
- `--threshold N` — Score swing for blunder detection (default: 1.0)
- `--engine PATH` — Override Stockfish binary path
- `--in-place` — Overwrite original file (default: writes to `*_analyzed.pgn`)

### `chess-opening-prep setup`

Interactive setup wizard. Verifies Lichess authentication, finds existing studies, and configures `config.json`.

### `chess-opening-prep push <file.pgn>`

Push a local PGN file to its mapped Lichess study. Automatically cleans up empty default chapters.

```bash
chess-opening-prep push pgn/repertoire_blancs_gambit_dame_annote.pgn
```

### `chess-opening-prep pull <file.pgn>`

Pull the latest PGN from a Lichess study to a local file.

```bash
chess-opening-prep pull pgn/repertoire_blancs_gambit_dame_annote.pgn
chess-opening-prep pull pgn/repertoire_blancs_gambit_dame_annote.pgn --in-place
```

### `chess-opening-prep cleanup [file.pgn]`

Remove empty default chapters (e.g. "Chapter 1") from Lichess studies. Runs automatically after `push`.

```bash
chess-opening-prep cleanup                                              # all studies
chess-opening-prep cleanup pgn/repertoire_blancs_gambit_dame_annote.pgn # one study
```

### `chess-opening-prep status`

Show sync status of all repertoire files, Stockfish availability, and Lichess configuration.

## Workflow

```
Zone 1: Local Files           →  Zone 2: Lichess Study
  (CLI prepares + analyzes)        (source of truth + interactive study)
  *_annote.pgn                     → Chessdriller (spaced-repetition drill)

  chess-opening-prep                chess-opening-prep
  analyze                           push / pull
```

## PGN File Structure

Two versions per opening:
- `*_annote.pgn` — Annotated reference version with comments, variation names, theoretical notes
- `*.pgn` — Working copy (may contain Stockfish annotations)

## Tool Versions

| Tool | Version | Notes |
|------|---------|-------|
| Stockfish | 18 | System package is v16; v18 available via En-Croissant or direct download |
| python-chess | >=1.11.0 | PGN parsing + UCI protocol |
| berserk | >=0.14.0 | Official Lichess Python client |
| Python | >=3.12 | Required |

## Using with Claude Code (Optional)

If you use [Claude Code](https://claude.ai/claude-code), slash commands are available:
- `/analyze` — Run Stockfish analysis
- `/push-lichess` — Push to Lichess study
- `/pull-lichess` — Pull from Lichess study
- `/sync-status` — Show sync status

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for code guidelines (Karpathy principles).

## License

[MIT](LICENSE)
