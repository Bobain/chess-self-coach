# Roadmap

## Legend
- [x] Done (CLI + PWA)
- [c] CLI done, PWA pending (needs API endpoint + menu item)
- [>] Now — being implemented
- [ ] Not started

"Next feature" = first `[ ]` item scanning top-to-bottom.

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

## 3. Training Pipeline (expose CLI → PWA)
- [c] train --prepare (CLI: prepare_training_data with --games, --depth, --engine, --fresh)
- [ ] POST /api/train/prepare — trigger from menu
- [ ] GET /api/train/progress — SSE real-time progress
- [c] import (CLI: import_games with --chesscom, --max)
- [ ] POST /api/games/import — trigger from menu
- [c] train --stats (CLI: print_stats)
- [ ] Training stats in PWA (dashboard or menu item)

## 4. Chess Prep — expose CLI → PWA
- [c] push (CLI: push_pgn with --no-replace)
- [c] pull (CLI: pull_pgn with --in-place)
- [c] analyze (CLI: analyze_pgn with --depth, --threshold, --engine, --in-place)
- [c] validate (CLI: validate_pgn)
- [c] cleanup (CLI: cleanup_study)
- [c] status (CLI: show_status)
- [ ] API endpoints for each command
- [ ] Menu items for each command

## 5. Settings & Configuration
- [ ] Settings sync API — localStorage ↔ backend config.json
- [ ] Move settings into hamburger menu
- [ ] Edit config from PWA (usernames, token, SF path)
- [ ] Display Stockfish version in About

## 6. Chess Prep — New features
- [ ] Coaching journal viewer (browse coaching/topics/)
- [ ] PGN viewer/editor in PWA
- [ ] Repertoire explorer (interactive tree)
- [ ] Opening quiz mode (drill repertoire lines)

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
