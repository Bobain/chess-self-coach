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

### 3b. SSE job runner + long-running endpoints
- [x] ⚠️ UX DESIGN PHASE: "Refresh training" button runs `train --prepare` in background.
      Individual commands (import, analyze, push, pull) deferred to future design phase.
- [x] Generic SSE job runner (POST starts job → 202, GET streams progress via SSE)
- [x] train --prepare (CLI: prepare_training_data with --games, --depth, --engine, --fresh)
- [x] POST /api/train/prepare + GET /api/jobs/{id}/events (SSE)
- [x] PWA "Refresh training" menu item + progress modal
- Deferred to future design phase:
  - import/analyze/push/pull → individual PWA buttons (needs own design phase)
  - `--games N` → future PWA setting (default 20)
  - `--fresh` → future "Force re-analysis" option
  - `--engine /path` → future config setting

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
     │    Section 3b (SSE job runner + long ops) ← DONE
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
