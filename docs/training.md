# Training & Analysis Modes

Review your own games, drill the correct moves with spaced repetition, and analyze full games with chess.com-quality review.

The PWA has two modes, toggled via the header: **Training** (find the better move) and **Analysis** (game review).

## Training mode

### How it works

```
PREPARATION (your PC, once)              DRILL (browser, daily)
┌─────────────────────────────┐         ┌──────────────────────────────┐
│ chess-self-coach train      │         │ PWA in browser               │
│           --prepare         │  JSON   │                              │
│                             │ ─────→  │ 1. Shows your mistake        │
│ 1. Fetches your games       │         │ 2. "Find a better move"      │
│    (Lichess + chess.com)    │         │ 3. You drag a piece          │
│ 2. Stockfish analyzes each  │         │ 4. Correct → explanation     │
│    position (depth 18)      │         │ 5. Wrong → unlimited retries  │
│ 3. Finds blunders/mistakes  │         │ 6. Spaced repetition (SM-2)  │
│ 4. Generates explanations   │         │ 7. Progress in localStorage  │
│ 5. Exports training_data.json         │                              │
└─────────────────────────────┘         └──────────────────────────────┘
```

## Quick start

```bash
# 1. Prepare training data
chess-self-coach train --prepare --games 10

# 2. Open the training interface
chess-self-coach train --serve

# 3. Check your stats
chess-self-coach train --stats
```

## Architecture

The training mode has **no backend**. All drill logic runs in the browser:

| Component | Role | Technology |
|-----------|------|------------|
| **Preparation** (CLI) | Fetch games, Stockfish analysis, mistake extraction | Python + python-chess |
| **Board** | Interactive chess board (drag & drop) | [chessground](https://github.com/lichess-org/chessground) (Lichess) |
| **Move validation** | Verify legality, convert to SAN notation | [chess.js](https://github.com/jhlywa/chess.js) |
| **SRS scheduler** | Spaced repetition (SM-2 algorithm) | Vanilla JS |
| **Progress storage** | Persist review state across sessions | localStorage |
| **Offline support** | Cache assets for offline use | Service Worker |

## Mistake categories

| Category | Centipawn loss | Description |
|----------|--------------|-------------|
| **Blunder** | ≥ 200 cp | Hanging a piece, missing mate |
| **Mistake** | 100–199 cp | Missing a tactic, poor exchange |
| **Inaccuracy** | 50–99 cp | Passive move when active was available |

## SM-2 Spaced Repetition

The scheduler uses the SM-2 algorithm (same as Anki):

- **New position**: shown immediately
- **Correct**: interval increases (1d → 3d → 7d → 18d → ...)
- **Wrong**: interval resets to 1 day, ease factor decreases
- **Mastered**: interval ≥ 7 days, position is retired from active review

## Data format

See `training_data.json` for the full schema. Each position contains:

- `fen` — board position
- `player_move` — the mistake the player made
- `best_move` — what Stockfish recommends
- `explanation` — rule-based explanation of why
- `acceptable_moves` — list of moves accepted as correct
- `game` — source game metadata (opponent, date, opening)

---

## Analysis mode

### Game review

Click **Analysis** in the header toggle to enter game review mode. This provides chess.com-quality analysis of your games.

```
GAME SELECTOR                          GAME REVIEW
┌──────────────────────────┐          ┌──────────────────────────────────────┐
│ L  vs Opponent1  2026-03 │          │ White vs Black  1-0                  │
│ W  vs Opponent2  2026-03 │   →      ├─────┬───────────────┬───────────────┤
│ D  vs Opponent3  2026-03 │          │Eval │               │ Accuracy: 87% │
│ ...                      │          │ bar │   Board       │ ★3 !5 ?!2 ?1 │
│                          │          │     │               │ 1. e4    e5   │
│  (click to review)       │          │     │               │ 2. Nf3   Nc6  │
│                          │          │     │               │ (scrollable)  │
└──────────────────────────┘          ├─────┴───────────────┴───────────────┤
                                      │ [Score chart — click to navigate]   │
                                      ├────────────────────────────────────┤
                                      │ |<  <  ▶  >  >|      ⇆ flip      │
                                      └────────────────────────────────────┘
```

### Features

- **Game selector**: list of analyzed games with W/D/L result, opponent, date, opening
- **Move list**: two-column grid with classification dots (colored by category)
- **Eval bar**: sigmoid-mapped vertical bar showing white/black advantage
- **Score chart**: interactive Canvas eval curve, click to jump to any move
- **Board arrows**: green = best move, red = played mistake
- **PV line**: engine best continuation with depth
- **Accuracy**: CAPS-like per-player accuracy percentage
- **Auto-play**: play through the game at 1 move/second
- **Keyboard navigation**: Arrow Left/Right, Home/End

### Move classifications

Uses a win probability model (chess.com-style): `winProb(cp) = 1 / (1 + 10^(-cp/400))`.

| Category   | Expected points lost | Color   | Symbol |
|------------|---------------------|---------|--------|
| Best       | ≤ 0.00              | #96bc4b | ★      |
| Excellent  | ≤ 0.02              | #96bc4b | !      |
| Good       | ≤ 0.05              | #95b776 |        |
| Book       | (opening explorer)  | #a88764 | ♗      |
| Inaccuracy | ≤ 0.10              | #f7c631 | ?!     |
| Mistake    | ≤ 0.20              | #e6912a | ?      |
| Blunder    | > 0.20              | #ca3431 | ??     |
| Missed Win | (had mate)          | #ca3431 | ×      |

### Data source

Analysis mode reads `analysis_data.json` (full per-move analysis from the pipeline). In [demo] mode, a sample file is bundled. In [app] mode, served fresh via `GET /analysis_data.json`.
