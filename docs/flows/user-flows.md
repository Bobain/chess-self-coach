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

    Note over PWA: Game list is the default view
    PWA->>PWA: Fetch analysis_data.json
    PWA->>U: Show game list (analyzed + cached games)

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

- **Game list**: default view, shows all games (analyzed + cached). Cards showing opponent, date, result (W/D/L badge), opening name, move count. Analyzed games also show accuracy % and classification badges. All games have checkboxes for (re-)analysis; selecting an already-analyzed game auto-sets `reanalyze_all`.
- **Training**: accessible via hamburger menu → "Training" (all positions) or per-game "Train" button in review.
- **Move classifications**: win probability model — `winProb(cp) = 1/(1+10^(-cp/400))`, thresholds: Best ≤0, Excellent ≤0.02, Good ≤0.05, Inaccuracy ≤0.10, Mistake ≤0.20, Blunder >0.20. Special: Brilliant (piece sacrifice value >2 + EPL ≤0.02 + wpBefore >0.05 and <0.95 + not opening theory + PV ≥3 moves).
- **Eval bar**: sigmoid mapping, 50% at equal, smooth CSS transition. For book moves (no Stockfish eval), derives approximate cp from opening explorer win/draw/loss stats. Shows "M3" for mate.
- **Score chart**: Canvas, click to jump to any move, colored dots at brilliant/mistakes/blunders.
- **Board arrows**: `reviewCg.set({drawable: {autoShapes: [...]}})` — green for best move, red for played mistake.
- **Keyboard**: ArrowLeft/Right, Home/End. Active only in analysis view.
- **Flip board**: toggles `reviewOrientation` on the second Chessground instance.

---

## Analyze selected games (app mode)

User selects games from the game list, triggers Stockfish analysis on selected games, and generates training positions.

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

    U->>PWA: Select games (checkboxes) + click "Analyze selected"
    PWA->>API: POST /api/analysis/start {game_ids, reanalyze_all}
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

- **Settings modal**: unified modal with Training, Accounts, Analysis (presets: Quick/Balanced/Deep + Advanced toggle), and Danger zone sections.
- **Two-phase pipeline**: Phase 1 collects raw data (expensive), Phase 2 derives training data (cheap, re-runnable via `chess-self-coach train --derive`).
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
    SF_WARN -->|Yes| SYZ
    WARN --> SYZ

    subgraph "Syzygy tablebases"
        SYZ[Check Syzygy tables]
        SYZ --> SYZ_FOUND{Found?}
        SYZ_FOUND -->|Yes| PLAT
        SYZ_FOUND -->|No| SYZ_DL{Download ~1 GB?}
        SYZ_DL -->|Yes| SYZ_OK[Download tables]
        SYZ_DL -->|No| PLAT
        SYZ_OK --> PLAT
    end

    subgraph "Game platforms (need ≥ 1)"
        PLAT[Configure platforms]
        PLAT --> LI_USER[Prompt Lichess username]
        LI_USER --> LI_HAS{Username provided?}
        LI_HAS -->|Yes| LI_TOK[Prompt API token]
        LI_HAS -->|No| CC
        LI_TOK --> CC

        CC[Prompt Chess.com username]
        CC --> PLAT_CHECK{At least 1 platform?}
        PLAT_CHECK -->|No| PLAT_ERR[Exit: need at least one]
    end

    PLAT_CHECK -->|Yes| SAVE[Write config.json + .env]
    SAVE --> DONE[Setup complete]
```

### Key details

- **Stockfish search order**: config path → fallback path → En-Croissant default → `/usr/games/stockfish` → `$PATH`.
- **Token handling**: prompted via CLI input, saved to `.env` file. No API validation during setup.
- **Idempotent**: re-running setup merges with existing config (updates players/analysis).

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
        CFG["stockfish: {path, version}<br/>analysis: {depth, threshold}<br/>analysis_engine: {threads, hash_mb, limits}<br/>players: {lichess, chesscom}"]
    end

    subgraph "PWA (app mode only)"
        SHOW["Open Settings modal"] --> FETCH["GET /api/config<br/>GET /api/analysis/settings"]
        FETCH --> MODAL["Unified Settings modal<br/>(Training, Accounts, Analysis, Danger zone)"]
        MODAL --> SAVE_BTN[Save]
        SAVE_BTN --> POST["POST /api/config<br/>POST /api/analysis/settings"]
        POST --> MERGE["Merge players + analysis<br/>Update analysis_engine<br/>Preserve stockfish"]
    end

    WRITE --> CFG
    CFG --> SHOW
    MERGE --> CFG
```

### Key details

- **CLI creates** the full config: stockfish, analysis, players.
- **PWA edits** only `players` and `analysis` fields (stockfish is CLI-managed).
- **Merge strategy**: server loads full config, overwrites only the editable fields, writes back.
- **Format**: JSON with 2-space indent, `ensure_ascii=False`.
