# Data flows

How data moves through the system.

## Data lifecycle

How training data flows from chess platforms to the player's practice sessions.

![Data lifecycle flow](images/data-lifecycle.svg)

```mermaid
flowchart LR
    subgraph Sources
        LI[Lichess API]
        CC[Chess.com API]
    end

    subgraph "Phase 1 — Collection"
        IMP[Importer<br/>fetch games]
        SF[Stockfish 18<br/>N-1 threads, 1GB hash]
        TB[Lichess Tablebase<br/>≤7 pieces]
        OE[Lichess Opening Explorer<br/>theory detection]
    end

    subgraph Storage
        AD[data/analysis_data.json<br/>all moves, max granularity]
        TAC[data/tactics_data.json<br/>40 tactical motifs per move]
        TD[data/training_data.json<br/>filtered mistakes]
        LS[localStorage<br/>SRS state per position]
    end

    subgraph "Phase 1b — Tactical analysis"
        TACT[tactics.py<br/>forks, pins, mates...<br/>parallel, python-chess]
    end

    subgraph "Phase 2 — Derivation"
        DER[annotate_and_derive<br/>filter + explain]
    end

    subgraph "PWA — Training mode"
        SEL[Session selector<br/>SM-2 priority]
        QUIZ[Quiz interface<br/>board + feedback]
    end

    subgraph "PWA — Analysis mode"
        GSEL[Game selector]
        REV[Game review<br/>eval bar + score chart<br/>+ classifications]
    end

    LI --> IMP
    CC --> IMP
    IMP --> SF
    IMP --> TB
    IMP --> OE
    SF --> AD
    TB --> AD
    OE --> AD
    AD --> TACT
    TACT --> TAC
    AD --> DER
    DER --> TD
    TD --> SEL
    LS --> SEL
    SEL --> QUIZ
    QUIZ --> LS
    AD --> GSEL
    GSEL --> REV
```

### Two-layer data model

| File | Content | Used by |
|------|---------|---------|
| `analysis_data.json` | All moves, all evals, per game | Tactical analysis + Phase 2 derivation + Analysis mode |
| `tactics_data.json` | 40 tactical motifs per move (forks, pins, mates...) | Classifier optimization |
| `training_data.json` | Filtered mistakes (unchanged schema) | App + Demo |

Phase 2 can be re-run cheaply without re-running Stockfish (`chess-self-coach train --derive`).

### analysis_data.json structure (per game, per move)

```
{
  version, player,
  games: {
    "<game_url>": {
      headers, player_color, analyzed_at, analysis_duration_s, settings,
      moves: [
        { ply, fen_before, fen_after, move_san, move_uci, side,
          eval_source, in_opening, eval_before: {score_cp, is_mate, depth, seldepth, nodes, nps, time_ms, pv_san, ...},
          eval_after: {...}, eval_after_best: {score_cp, is_mate, mate_in},
          tablebase_before, tablebase_after,
          opening_explorer: {opening: {eco, name}, moves: [{san, white, draws, black}]},
          cp_loss, board: {piece_count, is_check, is_capture, ...},
          clock: {player, opponent, time_spent} }
      ]
    }
  }
}
```

### training_data.json structure (unchanged)

```
{
  version, generated, player: {lichess, chesscom},
  positions: [
    { id, fen, player_color, player_move, best_move,
      context, score_before, score_after, cp_loss, category,
      explanation, acceptable_moves, pv,
      game: { id, source, opponent, date, result },
      clock: { player, opponent },
      srs: { interval, ease, next_review, history } }
  ],
  analyzed_game_ids: [...]
}
```

### localStorage SRS state

```
train_srs: {
  "<position_id>": {
    interval, ease, repetitions, next_review,
    history: [{ date, correct, dismissed? }]
  }
}
```

---

## SRS (Spaced Repetition) algorithm

The SM-2 variant used for scheduling position reviews.

![SRS algorithm flow](images/srs-algorithm.svg)

```mermaid
stateDiagram-v2
    [*] --> New: Position created
    New --> Learning: First review (interval=1d)
    Learning --> Learning: Wrong (interval=1d, ease↓)
    Learning --> Learning: Correct (interval×ease)
    Learning --> Mastered: interval ≥ 7d
    Mastered --> Learning: Overdue + wrong
    New --> Dismissed: "Give up"
    Learning --> Dismissed: "Give up"
    Dismissed --> [*]: interval=99999d<br/>Never shown again
```

| Outcome | Effect |
|---------|--------|
| Correct (1st rep) | interval = 1 day |
| Correct (2nd rep) | interval = 3 days |
| Correct (3rd+ rep) | interval = interval × ease |
| Wrong | interval = 1 day, repetitions = 0 |
| Ease adjustment | ease += 0.1 − (5−q)(0.08 + (5−q)×0.02), min 1.3 |
