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

## Analyse latest games (app mode)

Fetches recent games, runs Stockfish analysis, and generates training positions.

![Analyse latest games flow](images/analyse-games.svg)

```mermaid
sequenceDiagram
    participant U as Player
    participant PWA as Browser
    participant API as FastAPI server
    participant W as Worker threads
    participant SF as Stockfish (native)
    participant L as Lichess API
    participant C as Chess.com API

    U->>PWA: Click "Analyse latest games"
    PWA->>API: POST /api/train/prepare
    API-->>PWA: 202 + job_id
    PWA->>API: GET /api/jobs/{id}/events (SSE)

    API->>API: Load existing training_data.json<br/>(preserve SRS + analyzed_game_ids)

    par Fetch games
        API->>L: Fetch ≤20 recent rated games
        API->>C: Fetch ≤20 recent rated games
    end

    API->>API: Filter: skip already-analyzed games

    loop Each new game (parallel workers)
        API->>W: Analyze game
        W->>SF: depth-18 analysis per position
        SF-->>W: eval scores
        W-->>API: Positions with cp_loss > threshold
        API-->>PWA: SSE: analyze phase (X/Y, percent)
        API->>API: Atomic write to training_data.json
    end

    API-->>PWA: SSE: done (summary)
    PWA->>PWA: Reload training_data.json
    PWA->>PWA: Restart session
```

### Key details

- **Incremental merge**: only new games are analyzed. Existing positions keep their SRS state.
- **Thresholds**: blunder ≥ 200cp, mistake ≥ 100cp, inaccuracy ≥ 50cp.
- **Parallelism**: N-1 CPU cores (ProcessPoolExecutor).
- **Crash safety**: atomic write after each game — if interrupted, partial results are saved.
- **Interrupt**: user can click the interrupt button → `POST /api/jobs/{id}/cancel` → saves progress so far.
- **Hardcoded defaults** (v0.3.8): 20 games per source, depth 18, no UI to customize.

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
        CFG["stockfish: {path, version}<br/>analysis: {depth, threshold}<br/>players: {lichess, chesscom}<br/>studies: {pgn → study_id}"]
    end

    subgraph "PWA (app mode only)"
        SHOW[GET /api/config] --> MODAL[Config modal]
        MODAL --> SAVE_BTN[Save]
        SAVE_BTN --> POST[POST /api/config]
        POST --> MERGE[Merge players + analysis<br/>Preserve stockfish + studies]
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
