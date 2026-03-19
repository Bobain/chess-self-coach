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
- [c] validate (CLI: validate_pgn) ← instant, no SSE needed
- [ ] POST /api/pgn/validate — trigger from menu
- [c] status (CLI: show_status) ← instant
- [ ] Extract get_status_data() from show_status (returns dict, CLI unchanged)
- [ ] GET /api/pgn/status — trigger from menu
- [c] cleanup (CLI: cleanup_study) ← fast
- [ ] POST /api/pgn/cleanup — trigger from menu

### 3b. SSE job runner + long-running endpoints
- [ ] ⚠️ UX DESIGN PHASE: before implementing individual endpoints, design a unified
      user workflow. The CLI has many separate commands (import → analyze → push → pull
      → validate → cleanup) but the PWA user should NOT have to click 4 buttons to get
      their prep ready in ChessDriller. Design a simplified workflow together first.
- [ ] Generic SSE job runner (POST starts job → 202, GET streams progress via SSE)
- [c] train --prepare (CLI: prepare_training_data with --games, --depth, --engine, --fresh)
- [ ] POST /api/train/prepare + GET /api/jobs/{id}/progress (SSE)
- [c] import (CLI: import_games with --chesscom, --max)
- [ ] POST /api/games/import + SSE progress
- [c] analyze (CLI: analyze_pgn with --depth, --threshold, --engine, --in-place)
- [ ] POST /api/pgn/analyze + SSE progress
- [c] push (CLI: push_pgn with --no-replace)
- [ ] POST /api/pgn/push + SSE progress
- [c] pull (CLI: pull_pgn with --in-place)
- [ ] POST /api/pgn/pull + SSE progress

## 4. Chess Prep — New features
- [ ] Coaching journal viewer (browse coaching/topics/)
- [ ] PGN viewer/editor in PWA
- [ ] Repertoire explorer (interactive tree)
- [ ] Opening quiz mode (drill repertoire lines)

## 5. Settings & Configuration

### 5a. Settings UI (no backend needed)
- [ ] Move settings into hamburger menu (replace gear icon)
- [ ] Display Stockfish version in About/menu header

### 5b. Backend config (needs API endpoints)
- [ ] GET /api/config/status — token configured? SF version?
- [ ] Settings sync API — localStorage ↔ backend config.json
- [ ] Edit config from PWA (usernames, token, SF path)

## Dependency diagram

```
Section 1 (Backend) ← DONE
     │
     ▼
Section 2 (Menu + Mode detection) ← DONE
     │
     ├──► Section 3a (instant endpoints) ← wiring pattern
     │         │
     │         ▼ (pattern established)
     │    Section 3b (SSE job runner + long ops)
     │
     ├──► Section 5a (Settings UI) ← independent, localStorage only
     │
     └──► Section 5b (Config API) ← after 3a (same endpoint pattern)
               │
               ▼
          Section 4 (New features: journal, PGN viewer, quiz)
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
