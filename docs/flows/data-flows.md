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

    subgraph Backend
        IMP[Importer<br/>fetch games]
        SF[Stockfish 18<br/>analyze positions]
        TR[Trainer<br/>extract mistakes]
    end

    subgraph Storage
        TD[training_data.json<br/>positions + game metadata]
        LS[localStorage<br/>SRS state per position]
    end

    subgraph PWA
        SEL[Session selector<br/>SM-2 priority]
        QUIZ[Quiz interface<br/>board + feedback]
    end

    LI --> IMP
    CC --> IMP
    IMP --> SF
    SF --> TR
    TR --> TD
    TD --> SEL
    LS --> SEL
    SEL --> QUIZ
    QUIZ --> LS
```

### training_data.json structure

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
