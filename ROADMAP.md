# Roadmap

## Legend
- [x] Done (CLI + PWA)
- [c] CLI done, PWA pending (needs API endpoint + menu item)
- [>] Now — being implemented
- [ ] Not started

"Next feature" = first `[ ]` item scanning top-to-bottom.

## Definition of Done
An item is [x] when ALL applicable criteria are met:
- **API endpoint**: returns correct JSON, error cases return proper HTTP status, unit test in test_server.py
- **Menu → PWA**: menu click triggers API, result displayed in PWA, E2E test with app_url fixture
- **Refactor** (extract function, etc.): existing tests still pass, CLI behavior unchanged
- **Infrastructure** (wiring pattern, SSE runner): reusable, tested in isolation, documented by first usage
- **UX design phase**: written decision document (GitHub issue or CONTRIBUTING.md section)
- **Long-running ops**: POST returns 202 + job_id, GET streams SSE, job errors return detail

## 1. Backend Foundation — DONE
- [x] FastAPI server (dynamic serving, no temp dir)
- [x] GET /api/status — mode detection
- [x] POST /api/stockfish/bestmove — native SF + crash recovery + asyncio.Lock
- [x] Stockfish + app version check at startup
- [x] Port conflict handling (scan 8000-8010)

## 2. PWA Menu & Mode Detection — DONE
- [x] Hamburger menu skeleton (top-left)
- [x] Mode detection via /api/status
- [x] Hide demo banner in [app] mode
- [x] "Analyzing..." thinking indicator (both modes)
- [x] Native Stockfish API for opponent response (with WASM fallback)
- [x] Analysis depth setting (18 [app], 12 [demo], configurable)

## 3. Expose CLI → PWA (shared infrastructure)

### 3a. Menu wiring pattern + instant endpoints
- [x] Add E2E app_url fixture: FastAPI server for [App] mode testing (pwa_url stays for [Demo])
- [x] Establish menu → API → CLI wiring pattern (first end-to-end item)
- [x] train --stats (CLI: print_stats) ← quickest win, proves the pattern
- [x] Extract get_stats_data() from print_stats (returns dict, CLI unchanged)
- [x] GET /api/train/stats — stats in PWA (dashboard or menu item)
- [x] Unit + E2E tests for /api/train/stats
- [x] validate (CLI: validate_pgn) ← instant, no SSE needed
- [x] POST /api/pgn/validate — trigger from menu
- [x] status (CLI: show_status) ← instant
- [x] Extract get_status_data() from show_status (returns dict, CLI unchanged)
- [x] GET /api/pgn/status — trigger from menu
- [x] cleanup (CLI: cleanup_study) ← fast
- [x] POST /api/pgn/cleanup — trigger from menu

### 3b. SSE job runner + "Analyse latest games" — DONE
- [x] ⚠️ UX DESIGN PHASE: "Analyse latest games" button runs `train --prepare` in background.
      Individual commands (import, analyze, push, pull) deferred to future design phase.
- [x] Generic SSE job runner (POST starts job → 202, GET streams progress via SSE)
- [x] train --prepare (CLI: prepare_training_data with --games, --depth, --engine, --fresh)
- [x] POST /api/train/prepare + GET /api/jobs/{id}/events (SSE)
- [x] PWA "Analyse latest games" menu item + progress modal
- [x] Two-phase analysis pipeline: Phase 1 (collection: SF + Tablebase + Opening Explorer) → Phase 2 (derivation: filter + explain)
- [x] analysis_data.json: full per-move data with maximum granularity (all SF info, full PV, tablebase, opening explorer)
- [x] training_data.json derived from analysis_data.json (re-runnable without Stockfish via `--derive`)
- [x] Single multi-threaded Stockfish (N-1 threads + configurable hash) instead of N × 1-thread workers
- [x] Analysis settings modal in PWA: threads, hash, depth/time limits, games count
- [x] CLI: `--derive`, `--threads`, `--hash`, `--reanalyze-all` flags; `--games` default changed to 10
- [x] API: GET/POST /api/analysis/settings, POST /api/analysis/start, POST /api/train/derive
- [x] Lichess Opening Explorer integration: theory departure detection (stops querying when move leaves known theory)
- [x] analysis_duration_s per game for ETA estimation
- [x] Incremental: analyze only unanalyzed games; reanalyze-all skips same-settings games

**Current behavior** (v0.4.x):
The button opens an Analysis Settings modal where the user configures:
- Stockfish threads (auto = N-1 CPUs) and hash (default 1GB)
- Depth/time limits per piece-count bracket (4 configurable rows)
- Number of games to analyze (default 10)
Then POSTs to `POST /api/analysis/start` which:
1. Fetches recent rated games (Lichess + Chess.com)
2. Filters: skip already-analyzed (or same-settings if reanalyze-all)
3. Phase 1: Stockfish + Lichess Tablebase + Opening Explorer per move, writes `analysis_data.json` after each game
4. Phase 2: `annotate_and_derive()` filters mistakes, generates explanations, writes `training_data.json`

**Next priority:**
- [ ] import/analyze/push/pull → individual PWA buttons (needs own design phase)

### 3c. Game Review & Analysis UI — HIGH PRIORITY

Chess.com-quality game review experience in both [demo] and [app].
Data source: `analysis_data.json` (full per-move analysis from Phase 1).
All rendering is client-side JS — no backend needed → works in [demo] with sample data.

#### 3c-i. Game review page — full-game navigation (foundation)
- [ ] "Review games" menu item (visible in both [demo] and [app])
- [ ] Game selector: list analyzed games with opponent, date, result, opening
- [ ] Move list panel: algebraic notation, clickable to jump to position
- [ ] Board updates to show position at selected move (reuse Chessground)
- [ ] Keyboard navigation: ← → (prev/next move), Home/End (first/last)
- [ ] Auto-play button with configurable speed
- [ ] [Demo] loads sample `analysis_data.json`; [App] loads real data
- [ ] E2E test: navigate game moves, verify board position changes

#### 3c-ii. Eval bar + score chart
- [ ] Vertical eval bar next to board (white fill = White advantage, black = Black)
- [ ] Numeric display: centipawn value or "M3" for mate
- [ ] Smooth CSS transition on move changes
- [ ] Score chart below board: eval curve over all moves (Canvas, no external lib)
- [ ] Click on chart point → jump to that move
- [ ] E2E test: eval bar reflects position, chart clickable

#### 3c-iii. Move classifications + accuracy + board arrows
- [ ] Color-coded moves in move list:
      Brilliant (!!) / Great (!) / Best / Excellent / Good / Book /
      Inaccuracy (?!) / Mistake (?) / Blunder (??) / Missed Win
- [ ] Classification algorithm: cp_loss thresholds (extend existing `_classify_mistake()`)
- [ ] Accuracy score per player: CAPS-like formula from per-move cp_loss
- [ ] Game summary panel: accuracy %, classification counts per player, opening name
- [ ] Chessground arrows: green = best move, red/orange = played mistake
- [ ] E2E test: move colors match classifications, accuracy displayed

#### 3c-iv. Engine lines + opening info
- [ ] Top PV line displayed for selected move (from `pv_san` in analysis_data.json)
- [ ] Opening name + ECO code at top of move list
- [ ] Theory departure indicator (move where player left known openings)
- [ ] Depth indicator (from `depth` field)
- [ ] E2E test: PV line shown, opening name correct

### 3d. Legacy cleanup — old parallel analysis pipeline — DONE
The old parallel pipeline was removed. `trainer.py` now contains only explanation/context
generation, move classification, and training data utilities. Analysis lives in `analysis.py`.

**Removed from trainer.py:** `prepare_training_data()`, `extract_mistakes()`,
`_analyze_game_worker()`, `ProcessPoolExecutor` usage, `_determine_player_color()`,
`_load_existing_training_data()`, `_build_output()`, `TrainingInterrupted`,
`_atomic_write_json()`, `_score_to_cp()`, `_detect_source()`, `_get_opponent()`,
`_make_position_id()`.

**Removed from server.py:** `_run_job()`, `POST /api/train/prepare`.

**Tests migrated:** `test_resume.py` now tests `analyze_games()` (cancel, malformed games,
player-not-found, error recovery). `test_server.py` now tests `/api/analysis/start`.

**Kept in trainer.py** (used by Phase 2 + CLI):
- `generate_explanation()`, `_generate_context()`, `_time_pressure_context()`
- `compute_cp_loss()`, `_classify_mistake()`, `_format_score_cp()`, `_format_cp_loss_human()`
- `_detect_game_phase()`, `_describe_advantage()`, `_analysis_limit()` (used by `analyze.py`)
- `print_stats()`, `get_stats_data()`, `refresh_explanations()`
- Threshold constants: `BLUNDER_THRESHOLD`, `MISTAKE_THRESHOLD`, `INACCURACY_THRESHOLD`

### 3e. Interrupt resilience & data recovery
- [x] Interrupt button + incremental atomic writes (crash-safe pipeline)
- [ ] Legacy data migration: load training_data.json from older versions
      (different fields, missing SRS, etc.) — reuse what can be reused

## 4. Chess Prep — New features

### 4a. About modal (quick win) — DONE
- [x] About modal: app name, version, GitHub link, SF version (in [app] mode)
- [x] Click handler for `#nav-about`
- [x] Works in [demo] (static info) and [app] (version from /api/status)

### 4b. Coaching journal viewer — DONE
- [x] GET /api/coaching/topics — list topic files from coaching/topics/
- [x] GET /api/coaching/topics/{slug} — read one topic (return markdown)
- [x] PWA: journal browser modal (list → detail view, plain text rendering)
- [x] Menu item: "Coaching journal" (nav-app-only)

### 4c. PGN viewer
- [ ] ⚠️ UX DESIGN PHASE: interactive board + move tree, or read-only text view?
- [ ] GET /api/pgn/files/{name} — read one PGN file
- [ ] PWA: PGN viewer modal with chessboard (reuse chessground)
- [ ] Menu item: "View PGN" (nav-app-only)

### 4d. Repertoire explorer + Opening quiz (needs UX design phase)
- [ ] ⚠️ UX DESIGN PHASE: tree rendering, drill mode, scoring
- [ ] Repertoire explorer: interactive variation tree from PGN
- [ ] Opening quiz: drill correct moves from repertoire lines
- [ ] May depend on 5b (TBD after design phase)

## 5. Settings & Configuration

### 5a. Settings UI (no backend needed) — DONE
- [x] Move settings into hamburger menu (replace gear icon)
- [x] Display Stockfish version in About/menu header

### 5b. Backend config — DONE
- [x] Config API — GET/POST /api/config (players + analysis fields)
- [x] Edit config from PWA (usernames, depth, threshold)
Note: GET /api/config/status removed — already covered by GET /api/pgn/status
(has_token, stockfish.available/version).

## Dependency diagram

```
Section 1 (Backend) ← DONE
     │
     ▼
Section 2 (Menu + Mode detection) ← DONE
     │
     ├──► Section 3a (instant endpoints) ← DONE
     │         │
     │         ▼ (pattern established)
     │    Section 3b (SSE + full analysis pipeline) ← DONE
     │         │
     │         ├──► Section 3c (Game Review & Analysis UI) ← HIGH PRIORITY, NEXT
     │         │
     │         ▼
     │    Section 3d (Legacy cleanup) ← DONE
     │         │
     │         ▼
     │    Section 3e (Interrupt resilience + data recovery)
     │
     ├──► Section 5a (Settings UI) ← DONE
     │
     ├──► Section 4a (About modal) ← independent, no API needed for [demo]
     │
     ├──► Section 4b (Coaching journal) ← needs 2 new API endpoints
     │         │
     │         ▼ (API pattern reused)
     │    Section 4c (PGN viewer) ← needs API + UX design
     │         │
     │         ▼ (PGN parsing reused)
     │    Section 4d (Repertoire + quiz) ← needs UX design phase, may need 5b
     │
     └──► Section 5b (Config API) ← low priority, parallel with 4a-4c
```


## Dormant code (Coming soon features)

When features moved to the "Coming soon" submenu (v0.3.4), their frontend wiring was removed
but the code was kept for future reactivation. **Decision needed** for each: re-activate UI or delete code.

### Dead frontend code (JS + HTML + CSS)
- **JS functions** (`pwa/app.js`): `showValidate()`, `showProjectStatus()`, `showCleanup()`, `showJournal()`, `showJournalTopic()`, `showModalWithData()` helper
- **HTML modals** (`pwa/index.html`): `#validate-modal`, `#status-modal`, `#cleanup-modal`, `#journal-modal`, `#journal-back` button
- **CSS classes** (`pwa/style.css`): `.validate-*`, `.status-*`, `.journal-*`

### Backend endpoints with no UI
These are functional and tested but unreachable from the PWA:
- `POST /api/pgn/validate` — validates PGN files in project
- `GET /api/pgn/status` — project status (config, Stockfish, training data)
- `POST /api/pgn/cleanup` — removes duplicate/invalid studies
- `GET /api/coaching/topics` + `GET /api/coaching/topics/{slug}` — coaching journal reader
- `GET /api/train/stats` — training stats (replaced client-side by Raw data summary)

## Existing but undocumented features
These are implemented and working but not tracked as roadmap items:
- Tablebase integration (≤7 pieces, Lichess API)
- Incremental training data merge (preserves SRS progress)
- Time pressure context analysis (uses clock data)
- Pedagogical filtering (skips already-won/lost positions)
- Lichess study auto-discovery in setup wizard
- Multiline deviation analysis in import
- update command (self-update via pipx — redundant with startup check, not tracked)
- train --refresh-explanations (dev: regenerate without re-analyzing)
- train --fresh (dev: discard existing data)
