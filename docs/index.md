# chess-self-coach

CLI to manage a chess opening repertoire: Stockfish analysis + Lichess Study sync.

## Overview

chess-self-coach automates the workflow between:

1. **Local PGN files** — annotated opening repertoire
2. **Stockfish 18** — engine analysis and blunder detection
3. **Lichess Studies** — online study platform (source of truth)
4. **Chessdriller** — spaced-repetition drilling from Lichess Studies

## Openings Covered

| Color | Opening | Key Variation |
|-------|---------|--------------|
| White | Queen's Gambit (1.d4 2.c4) | Harrwitz Attack (5.Bf4) vs QGD |
| Black vs 1.e4 | Modern Scandinavian (1...d5 2.exd5 Nf6) | Fianchetto setup |
| Black vs 1.d4 | Slav Defense (1...d5 2...c6) | Czech Variation |

## Quick Start

```bash
pip install chess-self-coach
chess-self-coach setup
chess-self-coach status
```

See the [Setup Guide](setup.md) for detailed instructions.
