# Chess Self-Coach

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Learn from your own mistakes.** Chess Self-Coach fetches your games from Lichess and chess.com, finds your blunders with Stockfish, and drills you on the correct moves with spaced repetition.

**[Try the training PWA](https://bobain.github.io/chess-self-coach/train/)** | **[Documentation](https://bobain.github.io/chess-self-coach/docs/)** | **[Landing page](https://bobain.github.io/chess-self-coach/)**

## How It Works

```
YOUR GAMES                    STOCKFISH ANALYSIS              TRAINING
┌───────────────────┐        ┌───────────────────┐        ┌───────────────────┐
│ Lichess + chess.com│  ───→  │ Parallel analysis  │  ───→  │ Find the Better   │
│ 20 recent games    │        │ depth 18, 4 cores  │        │ Move (PWA)        │
└───────────────────┘        └───────────────────┘        └───────────────────┘
                                                           • Board position shown
                                                           • Context: phase, advantage
                                                           • Drag the better move
                                                           • Explanation + best line
                                                           • Spaced repetition (SM-2)
                                                           • Link to original game
```

### One command to start

```bash
chess-self-coach train --prepare    # fetch games + Stockfish analysis (~5 min)
chess-self-coach train --serve      # open training in browser
```

### What you see

For each mistake in your games, the trainer shows:
- **Context**: "Middlegame, you had a slight advantage. Your move lost significant material."
- **The position** with material balance (captured pieces)
- **Your task**: find the better move by dragging a piece
- **After answering**: explanation, best line (playable), link to the original game
- **Spaced repetition**: positions come back until mastered (intra-session + SM-2)
- **Give up**: permanently dismiss positions you don't want to review

### Mistake categories

| Category | Centipawn loss | Example |
|----------|--------------|---------|
| Blunder | >= 200 cp | Hanging a piece, allowing checkmate |
| Mistake | 100-199 cp | Missing a tactic, losing material |
| Inaccuracy | 50-99 cp | Passive move when active was better |

## Installation

```bash
# Recommended: install as isolated CLI tool
pipx install chess-self-coach

# Or with pip
pip install chess-self-coach

# From source (development)
git clone https://github.com/Bobain/chess-self-coach.git
cd chess-self-coach
uv venv && uv sync
```

### Prerequisites

- **Python >= 3.12**
- **Stockfish** — `sudo apt install stockfish` (or provide path via `--engine`)
- **Lichess API token** — for fetching your games ([create one here](https://lichess.org/account/oauth/token/create), scopes: `study:read` + `study:write`)

### Configuration

```bash
echo "LICHESS_API_TOKEN=lip_your_token_here" > .env
chess-self-coach setup    # interactive setup: verifies auth, configures config.json
```

## CLI Reference

### Training (main feature)

```bash
# Fetch your games and analyze with Stockfish
chess-self-coach train --prepare                    # 20 games, depth 18, parallel
chess-self-coach train --prepare --games 50         # more games
chess-self-coach train --prepare --depth 12         # faster analysis

# Open the training interface
chess-self-coach train --serve

# Check your stats
chess-self-coach train --stats
```

Incremental by default: only new games are analyzed. Existing positions and your SRS progress are preserved.

```bash
# Developer options
chess-self-coach train --prepare --fresh            # [dev] discard data, start from scratch
chess-self-coach train --refresh-explanations       # [dev] regenerate texts without Stockfish
```

### Repertoire management (secondary)

Also includes tools for managing opening repertoire PGN files synced with Lichess Studies:

```bash
chess-self-coach analyze <file.pgn>     # Stockfish analysis with [%eval] annotations
chess-self-coach push <file.pgn>        # push PGN to Lichess Study
chess-self-coach pull <file.pgn>        # pull from Lichess Study
chess-self-coach cleanup [file.pgn]     # remove empty default chapters
chess-self-coach status                 # sync status of all repertoire files
chess-self-coach setup                  # interactive configuration wizard
```

## Data & Privacy

- Your games are fetched from public APIs (Lichess, chess.com)
- `training_data.json` is stored locally (gitignored)
- Drill progress is in your browser's localStorage
- No server, no account, no tracking

## GitHub Pages

| URL | Content |
|-----|---------|
| [/chess-self-coach/](https://bobain.github.io/chess-self-coach/) | Landing page |
| [/chess-self-coach/train/](https://bobain.github.io/chess-self-coach/train/) | Training PWA |
| [/chess-self-coach/docs/](https://bobain.github.io/chess-self-coach/docs/) | Documentation |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for code guidelines.

## License

[MIT](LICENSE)
