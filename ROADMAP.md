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

### 3b. SSE job runner + "Analyse latest games" — DONE
- [x] ⚠️ UX DESIGN PHASE: "Analyse latest games" button runs `train --prepare` in background.
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

### 3c. Game Review & Analysis UI — DONE

Chess.com-quality game review experience in both [demo] and [app].
Data source: `analysis_data.json` (full per-move analysis from Phase 1).
All rendering is client-side JS — no backend needed → works in [demo] with sample data.

#### 3c-i. Game review page — full-game navigation (foundation)
- [x] Mode toggle `[Training | Analysis]` in header (replaces menu item)
- [x] Game selector: list analyzed games with opponent, date, result (W/D/L badge), opening
- [x] Move list panel: two-column grid, clickable to jump to position
- [x] Second Chessground instance (`reviewCg`) — read-only, no conflicts with training board
- [x] Keyboard navigation: ← → (prev/next move), Home/End (first/last)
- [x] Auto-play button (1 move/second, play/pause toggle)
- [x] Flip board button
- [x] Back button returns to game selector
- [x] [Demo] loads sample `analysis_data.json`; [App] serves fresh via `GET /analysis_data.json`
- [x] `deploy.yml` copies `analysis_data.json` to `site/train/`
- [x] E2E tests: mode toggle, game list, move navigation, keyboard, auto-play, flip, back (18 tests)

#### 3c-ii. Eval bar + score chart
- [x] Vertical eval bar next to board (sigmoid mapping, white fill = White advantage)
- [x] Numeric display: "+0.32" for cp, "M3" for mate, "Book" for opening moves
- [x] Smooth CSS transition (`height 0.3s ease`)
- [x] Score chart below board: Canvas eval curve, area fill (white/black gradient)
- [x] Click on chart → jump to that move
- [x] Colored dots at mistakes/blunders on chart
- [x] Current ply vertical cursor line
- [x] Responsive resize handling
- [x] E2E tests: eval bar updates, chart renders, chart click navigates

#### 3c-iii. Move classifications + accuracy + board arrows
- [x] Win probability model: `winProb(cp) = 1/(1+10^(-cp/400))`
- [x] Color-coded classification dots in move list:
      Best (★) / Excellent (!) / Good / Book (♗) /
      Inaccuracy (?!) / Mistake (?) / Blunder (??) / Missed Win (×)
- [x] Both players' moves classified (needed for opponent accuracy)
- [x] CAPS-like accuracy per player: `avg(min(wpAfter/wpBefore, 1)) × 100`
- [x] Game summary panel: accuracy %, classification count badges per player
- [x] Chessground arrows: green = best move, red = played mistake
- [x] E2E tests: classification dots present, accuracy percentages shown

#### 3c-iv. Engine lines + opening info
- [x] PV line displayed for selected move (from `pv_san`, truncated to 8 moves + depth)
- [x] Opening name + ECO code at top of move list (from `opening_explorer` data)
- [x] Theory departure indicator (left border marker on first non-book move)
- [x] E2E test: PV line shown for analyzed moves

**Skipped for now**: Brilliant/Great classifications (require multi-move sacrifice detection).

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

### 4c. PGN viewer
- [ ] ⚠️ UX DESIGN PHASE: interactive board + move tree, or read-only text view?
- [ ] GET /api/pgn/files/{name} — read one PGN file
- [ ] PWA: PGN viewer modal with chessboard (reuse chessground)
- [ ] Menu item: "View PGN" (nav-app-only)

## 5. Settings & Configuration

### 5a. Settings UI (no backend needed) — DONE
- [x] Move settings into hamburger menu (replace gear icon)
- [x] Display Stockfish version in About/menu header

### 5b. Backend config — DONE
- [x] Config API — GET/POST /api/config (players + analysis fields)
- [x] Edit config from PWA (usernames, depth, threshold)
Note: GET /api/config/status removed — already covered by GET /api/pgn/status
(has_token, stockfish.available/version).

## 6. UX Improvements

Source: [docs/ux/recommendations.md](docs/ux/recommendations.md) (generated by `ux-auditor` agent).
Chess.com reference: [docs/ux/chess-com-reference.md](docs/ux/chess-com-reference.md).

Promoted items from audit:

*(Run the ux-auditor agent to populate)*

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
     │         ├──► Section 3c (Game Review & Analysis UI) ← DONE
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
     ├──► Section 4c (PGN viewer) ← needs API + UX design
     │
     └──► Section 5b (Config API) ← low priority, parallel with 4c

Section 6 (UX Improvements) ← independent, parallel with all sections
     └──► Driven by ux-auditor agent output
```


## Cleanup TODO

- [ ] Remove "Coming soon" submenu from PWA nav — only "Project status" remains, not worth a submenu. Either promote it to a regular nav item or remove it entirely.
- [x] Show fetched-but-unanalyzed games in game list — PWA now fetches `/api/games` in [app] mode and appends unanalyzed games (greyed out, "Not analyzed" badge, selectable for batch analysis).
- [ ] Simplify settings/config UX — **audit findings (2026-03-24)**:

  **Problem: 3 separate modals, overlapping concerns, jargon labels**

  The app has three config/settings surfaces that confuse every persona:

  1. **"Settings" modal** (both modes, nav-settings): `Positions per session`, `Analysis depth`, `Difficulty` — stored in localStorage.
  2. **"Edit config" modal** (app-only, nav-config): `Lichess username`, `Chess.com username`, `Default analysis depth`, `Blunder threshold (cp)` — stored in config.json via `POST /api/config`.
  3. **"Analysis Settings" modal** (app-only, nav-refresh): `Threads`, `Hash (MB)`, 4 depth/time limit rows (K+P endgame / Endgame / Late middle / Default), `Games to analyze` — stored in config.json via `POST /api/analysis/settings`.

  **Specific issues:**

  - **"Analysis depth" appears in 2 places** with different meanings: Settings modal controls WASM Stockfish depth for live training (browser), while Edit config's "Default analysis depth" controls batch analysis depth (backend). A user changing one expects the other to change too.
  - **"Blunder threshold (cp)"** in Edit config is opaque — a ~1000 Elo player does not know what centipawns are or what "1.0" means. No tooltip, no explanation, no slider with human-readable labels.
  - **Analysis Settings modal is overwhelming**: 4 rows of depth/time limits by piece-count bracket (kings\_pawns\_le7, pieces\_le7, pieces\_le12, default) with raw numeric inputs. Labels like "K+P endgame" and "Late middle" are engine jargon. A beginner (Leo) would close this modal immediately. Even a grinder (Samir) just wants "fast/balanced/deep" presets.
  - **"Threads" and "Hash (MB)"** are system-level engine settings that 99% of users should never touch. No explanation of what they do or what the defaults mean.
  - **Menu naming is inconsistent**: "Settings" for training preferences, "Edit config" for account/analysis config, "Refresh games" opens "Analysis Settings". The mental model is unclear.
  - **No save confirmation in Settings modal**: closing the modal saves silently. Edit config has a "Save" button. Analysis Settings modal's "Start analysis" both saves AND starts a job — surprising.
  - **"Reset Progress" is a destructive button** with the same visual weight as "Close" in the Settings modal. It's red, but it's in the same row with no undo.

  **Proposed fix (3 tiers):**

  **Quick win**: Add descriptions/tooltips to all fields. Add "Accuracy" label to percentage. Add `title` attributes to "Blunder threshold", "Threads", "Hash". Replace "K+P endgame" with "King + Pawns only (7 or fewer pieces)".

  **Medium**: Merge "Settings" and "Edit config" into one "Settings" modal with sections: "Account" (usernames), "Training" (session size, difficulty), "Analysis" (depth, threshold with human labels). Move "Reset Progress" to a separate danger zone with confirmation.

  **Major**: Replace Analysis Settings 4-row depth/time grid with 3 presets: "Quick (shallow, ~30s/game)", "Balanced (default, ~2min/game)", "Deep (thorough, ~5min/game)" with an "Advanced" toggle that reveals the raw numbers. Hide threads/hash behind "Advanced" too.

## Existing but undocumented features
These are implemented and working but not tracked as roadmap items:
- Tablebase integration (≤7 pieces, Lichess API)
- Incremental training data merge (preserves SRS progress)
- Time pressure context analysis (uses clock data)
- Pedagogical filtering (skips already-won/lost positions)
- update command (self-update via pipx — redundant with startup check, not tracked)
- train --refresh-explanations (dev: regenerate without re-analyzing)
- train --fresh (dev: discard existing data)
