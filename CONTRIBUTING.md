# Contributing to chess-self-coach

## Development Setup

```bash
git clone https://github.com/Bobain/chess-self-coach.git
cd chess-self-coach
uv venv && uv sync
chess-self-coach --help
```

## Code Style

- **Language**: All code, comments, docstrings, error messages, and logs in English.
- **Docstrings**: Required on every module, class, and function (Google style).
- **Type hints**: Use `from __future__ import annotations` and type all function signatures.
- **Formatting**: Follow PEP 8. Use `ruff` if available.

### Commits

- **Commit at each logical step** — don't accumulate changes. Each commit should be a self-contained, testable unit (a feature, a fix, a refactor).
- Run tests before committing. If tests fail, fix before committing.

## Coding Guidelines

See [`.claude/CLAUDE.md`](.claude/CLAUDE.md) for detailed guidelines:
- **Karpathy Principles** — Think before coding, simplicity first, surgical changes, goal-driven execution
- **E2E Testing** — No silent errors, test with real data, always capture console

---

## Architecture

### Demo vs Application

The PWA detects its mode automatically via `/api/status`. If a FastAPI backend responds, it's [app] mode; otherwise [demo] mode. All JS works without a backend.

| | Demo | Application |
|---|---|---|
| **Distribution** | GitHub Pages | `pipx install` (one-liner) |
| **Launch** | Static hosting | `chess-self-coach` (FastAPI server) |
| **Opponent response engine** | Stockfish WASM (browser) | Native Stockfish (backend API, depth 18) |
| **Analysis depth default** | 12 | 18 |
| **Data** | Sample `training_data.json` + `analysis_data.json` | Generated from your own games |
| **CLI tools** | None | fetch, analyze, train |
| **Menu** | Training, Raw data summary, Settings, About | Training, Refresh games, Edit config, Coming soon ▸, Raw data summary, Settings, About |
| **Default view** | Game list (from analysis_data.json) | Game list (auto-fetched at startup) |

The **demo** showcases the training and analysis interfaces with sample data. Install the app to train on your own games.

The **application** (`chess-self-coach`) starts a FastAPI backend that serves the PWA with API endpoints for native Stockfish analysis. The CLI also fetches games from Lichess/chess.com, runs batch Stockfish analysis (native, depth 18, multi-core), and generates your personal `training_data.json`.

**Critical constraint**: never break the `[demo]`. All JS must work without a backend.

For detailed flow diagrams (training, analysis, CI/CD, Stockfish): see [docs/flows/](docs/flows/).

### Feature Development Protocol

When developing a new feature:
1. **Tag the scope**: use `[demo]`, `[app]`, or `[both]` in discussions and commit messages
2. PWA features are `[both]` by default — they run in the browser, no backend needed
3. CLI/pipeline features are `[app]` only
4. **Feature table**: keep the Architecture table updated with each new feature

### PWA Workflow Design

The PWA provides a game-list-centric workflow:

- **Auto-fetch** at startup: `POST /api/games/fetch` retrieves games from Lichess/chess.com and caches them in `fetched_games.json`
- **Game list** is the default view: shows all games (fetched + analyzed), with checkboxes for batch selection
- **"Analyze selected"** button sends chosen game IDs via `POST /api/analysis/start {game_ids}`
- Progress displayed via **SSE** (Server-Sent Events) in a modal with a step checklist (init → analyze → finalize)
- On completion, reloads data and refreshes the game list with accuracy and classification badges
- **Per-game training**: click "Train" on any analyzed game to drill only that game's mistakes
- **Full training**: accessible via the hamburger menu → "Training" (all positions, spaced repetition)

---

## Chess Context

### Player
- Level: ~1000 Elo chess.com rapid (15+10), ~700 estimated FIDE
- Lichess: [bobainbobain](https://lichess.org/@/bobainbobain)
- Chess.com: [Tonigor1982](https://www.chess.com/member/Tonigor1982)
- Target depth: essentials (5-6 moves + common deviations)

### UI Documentation
- Step-by-step UI guides are in `guides/`
- These guides are **evolutionary**: marked `[TO CONFIRM]` until validated by user
- NEVER affirm a UI workflow without user validation
