# User flows

Interactive workflows visible to the player.

## Training session (PWA)

The core user-facing flow: the player practices positions extracted from their own games.

![Training session flow](images/training-session.svg)

```mermaid
sequenceDiagram
    participant U as Player
    participant PWA as Browser (PWA)
    participant LS as localStorage
    participant SF as Stockfish WASM

    PWA->>PWA: Load training_data.json
    PWA->>LS: Load SRS state (train_srs)
    PWA->>PWA: selectPositions(positions, count)<br/>Priority: overdue → new → learning
    loop Each position
        PWA->>U: Show board + context prompt
        U->>PWA: Make a move
        alt Correct move
            PWA->>U: ✓ Feedback + explanation
            PWA->>LS: updateSRS(correct=true)
        else Wrong move
            PWA->>U: "Not quite. Try again."
            PWA->>SF: getStockfishBestMove(fen)
            SF-->>PWA: Opponent response (UCI)
            PWA->>U: Animate opponent move + Retry button
            Note over U,PWA: Player can retry<br/>unlimited times or<br/>click "Give up"
        end
        U->>PWA: Click Next
    end
    PWA->>U: Session summary (X/Y correct)
```

### Key details

- **Position selection** uses SM-2 spaced repetition: overdue positions first, then new (blunders prioritized), then learning (interval < 7 days). Mastered positions are skipped.
- **Intra-session repetition**: a correct first attempt reinserts the position 5 slots later for confirmation. A wrong answer reinserts 3 slots later.
- **Dismiss** ("Give up on this lesson") sets interval to 99999 days — the position never appears again.
- **SRS state** is stored per position ID in `localStorage` key `train_srs`.

---

## Game review (Analysis mode, PWA)

The player reviews full games move-by-move with eval visualization. Available in both [demo] and [app] modes.

![Game review flow](images/game-review.svg)

```mermaid
sequenceDiagram
    participant U as Player
    participant PWA as Browser (PWA)

    U->>PWA: Click "Analysis" in mode toggle
    PWA->>PWA: Fetch analysis_data.json
    PWA->>U: Show game selector (list of games)

    U->>PWA: Click a game card
    PWA->>PWA: classifyAllMoves() — win probability model
    PWA->>PWA: computeAccuracy() — per player
    PWA->>U: Show review: board + eval bar + move list + score chart

    loop Navigate moves
        alt Click move / Arrow key / Auto-play
            U->>PWA: Navigate to ply N
            PWA->>PWA: goToMove(N)
            PWA->>U: Update board (FEN + lastMove)
            PWA->>U: Update eval bar (sigmoid)
            PWA->>U: Update arrows (green=best, red=mistake)
            PWA->>U: Update PV line + score chart cursor
        end
    end

    U->>PWA: Click "Back"
    PWA->>U: Return to game selector
```

### Key details

- **Mode toggle**: segmented control `[Training | Analysis]` in the header.
- **Game selector**: cards showing opponent, date, result (W/D/L badge), opening name, move count.
- **Move classifications**: win probability model — `winProb(cp) = 1/(1+10^(-cp/400))`, thresholds: Best ≤0, Excellent ≤0.02, Good ≤0.05, Inaccuracy ≤0.10, Mistake ≤0.20, Blunder >0.20.
- **Eval bar**: sigmoid mapping, 50% at equal, smooth CSS transition. Shows "Book" for opening moves, "M3" for mate.
- **Score chart**: Canvas, click to jump to any move, colored dots at mistakes/blunders.
- **Board arrows**: `reviewCg.set({drawable: {autoShapes: [...]}})` — green for best move, red for played mistake.
- **Keyboard**: ArrowLeft/Right, Home/End. Active only in analysis view.
- **Flip board**: toggles `reviewOrientation` on the second Chessground instance.

---

## Analyse latest games (app mode)

Fetches recent games, runs full analysis (Stockfish + APIs), and generates training positions.

![Analyse latest games flow](images/analyse-games.svg)

```mermaid
sequenceDiagram
    participant U as Player
    participant PWA as Browser
    participant API as FastAPI server
    participant SF as Stockfish (native)
    participant TB as Lichess Tablebase
    participant OE as Lichess Opening Explorer
    participant L as Lichess API
    participant C as Chess.com API

    U->>PWA: Click "Analyse latest games"
    PWA->>API: GET /api/analysis/settings
    API-->>PWA: {threads, hash_mb, limits}
    PWA->>U: Show Analysis Settings modal

    U->>PWA: Adjust settings + click "Start analysis"
    PWA->>API: POST /api/analysis/settings (save)
    PWA->>API: POST /api/analysis/start {max_games, reanalyze_all}
    API-->>PWA: 202 + job_id
    PWA->>API: GET /api/jobs/{id}/events (SSE)

    API->>API: Load existing analysis_data.json

    par Fetch games
        API->>L: Fetch recent rated games
        API->>C: Fetch recent rated games
    end

    API->>API: Filter: skip already-analyzed<br/>(or same-settings if reanalyze_all)

    Note over API,SF: Phase 1 — Collection (1 SF, N-1 threads)

    loop Each new game (sequential)
        API->>OE: Query opening positions<br/>(stop at theory departure)
        OE-->>API: Opening name + move popularity

        loop Each position in game
            alt ≤7 pieces
                API->>TB: Tablebase probe
                TB-->>API: WDL + all moves + DTM/DTZ
            end
            API->>SF: engine.analyse() (adaptive depth)
            SF-->>API: Full eval (score, PV, depth, nodes, time...)
        end

        API->>API: Atomic write analysis_data.json
        API-->>PWA: SSE: analyze phase (X/Y, percent)
    end

    Note over API: Phase 2 — Derivation (no Stockfish)
    API->>API: annotate_and_derive()<br/>Filter mistakes → training_data.json

    API-->>PWA: SSE: done (summary)
    PWA->>PWA: Reload training_data.json
    PWA->>PWA: Restart session
    Note over PWA: analysis_data.json also updated<br/>(available for Analysis mode)
```

### Key details

- **Settings modal**: before analysis starts, user configures threads, hash, depth/time limits, and number of games.
- **Two-phase pipeline**: Phase 1 collects raw data (expensive), Phase 2 derives training data (cheap, re-runnable via `POST /api/train/derive`).
- **Engine model**: one Stockfish with N-1 threads + 1GB hash (configurable), sequential game-by-game.
- **Opening Explorer**: queries Lichess API position by position until theory departure (move not in database).
- **Incremental**: only unanalyzed games are processed. `reanalyze_all` skips only same-settings games.
- **Crash safety**: atomic write of `analysis_data.json` after each game. Resumable on interruption.
- **Thresholds**: blunder ≥ 200cp, mistake ≥ 100cp, inaccuracy ≥ 50cp.
- **Interrupt**: user can click interrupt → `POST /api/jobs/{id}/cancel` → saves progress so far.

---

## Setup wizard (CLI)

Interactive CLI flow that configures the application for first use.

![Setup wizard flow](images/setup-wizard.svg)

```mermaid
flowchart TD
    START[chess-self-coach setup] --> SF_FIND[Find Stockfish binary]
    SF_FIND --> SF_CHECK{Found?}
    SF_CHECK -->|No| SF_ERR[Exit: tested paths + install hint]
    SF_CHECK -->|Yes| SF_VER[Check version]
    SF_VER --> SF_WARN{Matches expected?}
    SF_WARN -->|No| WARN[Warning: version mismatch]
    SF_WARN -->|Yes| PLAT
    WARN --> PLAT

    subgraph "Game platforms (need ≥ 1)"
        PLAT[Configure platforms]
        PLAT --> LI{Lichess?}
        LI -->|Yes| LI_TOK{Token in .env?}
        LI_TOK -->|Yes| LI_VAL[Validate token via API]
        LI_TOK -->|No| LI_GUIDE[Guided token creation<br/>Open browser → save .env]
        LI_GUIDE --> LI_VAL
        LI_VAL -->|Valid| LI_OK[Store Lichess username]
        LI_VAL -->|Invalid| LI_REGEN[Exit: regeneration link]
        LI -->|No| CC
        LI_OK --> CC

        CC{Chess.com?}
        CC -->|Yes| CC_USER[Prompt username → store]
        CC -->|No| PLAT_CHECK
        CC_USER --> PLAT_CHECK

        PLAT_CHECK{At least 1 platform?}
        PLAT_CHECK -->|No| PLAT_ERR[Exit: need at least one]
    end

    PLAT_CHECK -->|Yes| STUDIES{Lichess configured?}
    STUDIES -->|No| SAVE
    STUDIES -->|Yes| STUDY_FETCH[Fetch user's studies]
    STUDY_FETCH --> STUDY_MAP[Auto-match studies by name]
    STUDY_MAP --> STUDY_MISS{Unmatched studies?}
    STUDY_MISS -->|Yes| STUDY_CREATE[Open browser → create studies]
    STUDY_MISS -->|No| SAVE
    STUDY_CREATE --> SAVE

    SAVE[Write config.json] --> DONE[Setup complete]
```

### Key details

- **Stockfish search order**: config path → fallback path → En-Croissant default → `/usr/games/stockfish` → `$PATH`.
- **Token validation**: must start with `lip_` prefix, verified against Lichess API.
- **Study mapping**: auto-matches local PGN filenames against Lichess study names (case-insensitive substring).
- **Idempotent**: re-running setup merges with existing config (preserves studies, updates players/analysis).

---

## Config management

How configuration is created via CLI and edited via PWA.

![Config management flow](images/config-management.svg)

```mermaid
flowchart LR
    subgraph "CLI (setup)"
        SETUP[chess-self-coach setup] --> WRITE[Write config.json]
    end

    subgraph "config.json"
        CFG["stockfish: {path, version}<br/>analysis: {depth, threshold}<br/>analysis_engine: {threads, hash_mb, limits}<br/>players: {lichess, chesscom}<br/>studies: {pgn → study_id}"]
    end

    subgraph "PWA (app mode only)"
        SHOW[GET /api/config] --> MODAL[Config modal]
        MODAL --> SAVE_BTN[Save]
        SAVE_BTN --> POST[POST /api/config]
        POST --> MERGE[Merge players + analysis<br/>Preserve stockfish + studies]
        SHOW2[GET /api/analysis/settings] --> MODAL2[Analysis Settings modal]
        MODAL2 --> SAVE2[POST /api/analysis/settings]
        SAVE2 --> MERGE2[Update analysis_engine]
    end

    WRITE --> CFG
    CFG --> SHOW
    MERGE --> CFG
```

### Key details

- **CLI creates** the full config: stockfish, analysis, players, studies.
- **PWA edits** only `players` and `analysis` fields (stockfish and studies are CLI-managed).
- **Merge strategy**: server loads full config, overwrites only the editable fields, writes back.
- **Format**: JSON with 2-space indent, `ensure_ascii=False`.
