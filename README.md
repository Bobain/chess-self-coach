# Chess Self-Coach

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Learn from your own mistakes.** Chess Self-Coach fetches your games from Lichess and chess.com, finds your blunders with Stockfish and Lichess tablebases, and drills you on the correct moves with spaced repetition.

**[Static demo](https://bobain.github.io/chess-self-coach/train/)** | **[Documentation](https://bobain.github.io/chess-self-coach/docs/)** | **[Landing page](https://bobain.github.io/chess-self-coach/)**

## How It Works

```
YOUR GAMES                    STOCKFISH ANALYSIS              TRAINING
┌───────────────────┐        ┌───────────────────┐        ┌───────────────────┐
│ Lichess + chess.com│  ───→  │ Parallel analysis  │  ───→  │ Find the Better   │
│ 20 recent games    │        │ adaptive, parallel │        │ Move (PWA)        │
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
- **Wrong move?** Stockfish shows how the opponent punishes it, then Retry
- **After answering**: explanation, best line (playable), link to the original game
- **Spaced repetition**: positions come back until mastered (intra-session + SM-2)
- **Give up**: permanently dismiss positions you don't want to review

### Mistake categories

| Category | Centipawn loss | Example |
|----------|--------------|---------|
| Blunder | >= 200 cp | Hanging a piece, allowing checkmate |
| Mistake | 100-199 cp | Missing a tactic, losing material |
| Inaccuracy | 50-99 cp | Passive move when active was better |

Endgame positions (≤ 7 pieces) are resolved by the [Lichess tablebase API](https://tablebase.lichess.ovh/) with mathematically exact Win/Draw/Loss verdicts — no Stockfish heuristics needed.

## Installation

### One-liner (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/Bobain/chess-self-coach/main/install.sh | bash
```

Installs Stockfish, Python, pipx, and chess-self-coach. Then run the setup wizard:

```bash
chess-self-coach setup
```

**Supported platforms**: macOS (Homebrew), Ubuntu/Debian (apt).

### Manual installation

```bash
# 1. Install Stockfish
sudo apt install stockfish  # or: brew install stockfish

# 2. Install chess-self-coach
pipx install chess-self-coach

# 3. Run the interactive setup wizard
chess-self-coach setup
```

### Update

```bash
chess-self-coach update
```

### Setup wizard

The `setup` command will:
1. Find Stockfish on your system
2. Guide you through **Lichess token creation** (bilingual FR/EN, step by step)
3. Ask for your **chess.com username** (for importing games)
4. Auto-detect your Lichess Studies

## CLI Reference

### Training (main feature)

```bash
# Fetch your games and analyze with Stockfish
chess-self-coach train --prepare                    # 20 games, adaptive depth, parallel
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
| [/chess-self-coach/train/](https://bobain.github.io/chess-self-coach/train/) | Static demo |
| [/chess-self-coach/docs/](https://bobain.github.io/chess-self-coach/docs/) | Documentation |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for code guidelines.

## License

[MIT](LICENSE)
