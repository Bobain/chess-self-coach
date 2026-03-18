# Chess Opening Repertoire

## Player
- Level: ~1000 Elo chess.com rapid (15+10), ~700 estimated FIDE
- Lichess: [bobainbobain](https://lichess.org/@/bobainbobain)
- Chess.com: [Tonigor1982](https://www.chess.com/member/Tonigor1982)
- Target depth: essentials (5-6 moves + common deviations)

## Lichess Studies
- [Whites - Queen's Gambit](https://lichess.org/study/ucjmuish)
- [Black vs e4 - Scandinavian](https://lichess.org/study/IoJ5waZo)
- [Black vs d4 - Slav](https://lichess.org/study/x3z4bEQ6)

## Chessdriller
- [chessdriller.org](https://chessdriller.org/) — login via Lichess OAuth
- Reads directly from the Lichess Studies above
- Daily drill with spaced repetition

## Repertoire
- **White**: Queen's Gambit (1.d4 2.c4) — Harrwitz Attack (5.Bf4) vs QGD
- **Black vs 1.e4**: Modern Scandinavian (1...d5 2.exd5 Nf6) — Fianchetto setup (...g6/...Bg7)
- **Black vs 1.d4**: Slav Defense (1...d5 2...c6) — Czech Variation (...dxc4, ...Bf5 BEFORE e6)
- **Black vs London**: Anti-London with immediate ...c5

## CLI Tool: chess-self-coach

### Commands
- `chess-self-coach analyze <file>` — Stockfish analysis with [%eval] annotations
- `chess-self-coach validate <file>` — Lint PGN annotations against mandatory conventions
- `chess-self-coach import <username>` — Import games from Lichess/chess.com, detect deviations
- `chess-self-coach setup` — Interactive setup (auth, studies, config)
- `chess-self-coach push <file>` — Push PGN to Lichess study
- `chess-self-coach pull <file>` — Pull PGN from Lichess study
- `chess-self-coach cleanup [file]` — Remove empty default chapters from Lichess studies
- `chess-self-coach status` — Show sync state of all files
- `chess-self-coach train --prepare [--games N] [--depth 18]` — Analyze games, extract mistakes, export training_data.json
- `chess-self-coach train --serve` — Open the training PWA in the browser
- `chess-self-coach train --stats` — Show training progress statistics

### Configuration
- `config.json` — Study IDs, Stockfish path, player usernames (gitignored, user-specific)
- `config.example.json` — Template for new users (committed)
- `.env` — Lichess API token (gitignored)
- `.env.example` — Template for new users (committed)
- Dependencies: `uv sync`

## PGN Files
Located in `pgn/`. Two versions per opening:
- `*_annote.pgn` — Annotated reference version (comments, variation names, theory markers)
- `*.pgn` — Working copy (may contain Stockfish annotations)

### Structure
- `repertoire_blancs_gambit_dame_annote.pgn` — 7 chapters: QGD (Harrwitz), QGA, Slav (Czech), Nimzo-Indian (Rubinstein), Albin (Lasker Trap), Budapest (Rubinstein/Fajarowicz), Dutch
- `repertoire_noirs_vs_e4_scandinave_annote.pgn` — 6 chapters: Marshall Fianchetto (4.c4 Nb6), 4.Nf3, 3.Nf3, Icelandic Gambit, 2.e5 (Advance), 2.Nc3/d3
- `repertoire_noirs_vs_d4_slave_annote.pgn` — 6 chapters: Classical Czech, Exchange, Anti-London, Transpositions, Passive moves, English Opening (1.c4)

## PGN Format
- Each `[Event "Variation name (ECO)"]` = one chapter
- `[Orientation "white"]` or `"black"` = board orientation
- Variations in parentheses `(...)`
- Comments in braces `{...}`
- Stockfish annotations: `{[%eval +0.32]}` (added by CLI or Lichess)

## MANDATORY Comment Conventions

### Names and references
- Always use the **official name** of the opening/variation (e.g., "Czech Variation", "Harrwitz Attack")
- Include the **ECO code** when known (e.g., ECO D17, ECO B01)
- Mention **elite players** who use the line (e.g., "played by Carlsen, Kramnik")

### Theoretical status
- Mark **THEORY:** when a move is the theoretical consensus
- Indicate if a line is **modern** or **historical**
- Note when a move is **inferior** or **rare** according to theory
- Flag cases where **in practice** results differ from theory

### Pedagogical explanations
- Explain the **WHY** of each move, not just name it
- Indicate the **plan** after the last move of each line (e.g., "Plan: O-O, Rc1, c-file pressure")
- Flag **traps** with TRAP or WARNING + full explanation
- Mark **TYPICAL MISTAKE** to avoid at the player's level
- Mention **transpositions** when a line joins another

## 2-Zone Workflow

```
Zone 1: Local Files      →  Zone 2: Lichess Study
  (CLI prepares + analyzes)    (source of truth + interactive study)
  *_annote.pgn                 → Chessdriller (drill)
```

### Zone 1 → Zone 2: Preparation → Publication
1. CLI/Claude creates/modifies `*_annote.pgn` files locally
2. ALL comment conventions must be followed
3. Theory verified via web search (variation names, consensus, players)
4. `chess-self-coach validate` to check annotations
5. `chess-self-coach analyze` for Stockfish validation
6. `chess-self-coach push` to publish to Lichess Study

### Zone 2: Interactive study
1. Lichess Study = **source of truth**
2. User studies interactively on Lichess (play moves, engine analysis)
3. Lichess has Stockfish 18 NNUE running in the browser
4. `chess-self-coach pull` to sync changes back to local

### Zone 2 → Drill
1. Chessdriller connects directly to Lichess studies
2. See `guides/guide_chessdriller.md` for steps
3. Daily drill with spaced repetition

### Optional: En-Croissant
En-Croissant is a desktop chess GUI that can be used for offline visual review of PGN files.
It is NOT required — Lichess Study provides the same functionality online.
If used, note:
- **NEVER** write to a file open in En-Croissant → write conflict guaranteed
- Always **close the file** in En-Croissant before running CLI commands
- En-Croissant modifies PGN continuously (adding evals, reformatting headers)

## Coaching Journal (MANDATORY)

After EVERY chess theory discussion (Q&A about openings, style, move choices, repertoire decisions):
1. Create or update a topic file in `coaching/topics/YYYY-MM-DD-slug.md`
2. Update `coaching/INDEX.md` with the new entry (categorized by opening)
3. This is **AUTOMATIC** — do NOT wait for the user to ask
4. Format: frontmatter (date, topic, opening, eco, status) + Question + Discussion + Actions Taken + Key Takeaways
5. If the discussion leads to PGN changes, document those in "Actions Taken"
6. Update "Principles Learned" in INDEX.md when a pattern emerges across multiple discussions

## UI Documentation
- Step-by-step UI guides are in `guides/`
- These guides are **evolutionary**: marked `[TO CONFIRM]` until validated by user
- NEVER affirm a UI workflow without user validation
- When guiding the user, ask them to describe what they see to update the guides

## Code Guidelines

All code, comments, docstrings, error messages, and logs must be in **English**.

### Karpathy Principles

Behavioral guidelines to reduce common LLM coding mistakes. These bias toward caution over speed — for trivial tasks, use judgment.

#### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

#### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

#### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

#### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## E2E Testing & Silent Errors

Rules learned from debugging the "See moves" link (hours lost to silent failures and fake-passing tests).

### No Silent Errors — EVER

- **JavaScript**: NEVER use `if (el)` guards that silently skip logic. If `getElementById` returns null, it's a bug — throw an explicit error or `console.error()` so it's visible.
- **Python**: NEVER use bare `except: pass`. Always log or re-raise.
- **General**: A function that fails silently is worse than one that crashes. Crashes are debuggable; silent failures waste hours.

### E2E Tests Must Use Real Data

- **NEVER test only with simplified fixtures**. Always include at least one test that runs against the real `training_data.json` (the production data).
- Fixtures are useful for unit-like e2e tests (known positions, predictable moves). But a separate "production smoke test" must verify the real data path.
- The "See moves" bug passed all fixture tests but failed in production because fixtures were missing `game.id` fields.

### Playwright Tests: Always Capture Console

- **Always** attach console and error listeners when running Playwright tests:
  ```python
  console_msgs = []
  page.on('console', lambda msg: console_msgs.append(f'[{msg.type}] {msg.text}'))
  page.on('pageerror', lambda exc: console_msgs.append(f'[ERROR] {exc}'))
  ```
- After each test action, check for errors: `assert not [m for m in console_msgs if 'error' in m.lower()]`
- This catches JS errors that would otherwise be invisible in headless mode.

### Service Worker: Network-First for Local Assets

- The PWA service worker MUST use **network-first** for same-origin assets (always serve fresh files from server, cache as offline fallback).
- **Cache-first** is only for CDN resources (which never change).
- `serve_pwa()` creates a temp dir on each launch — the SW must fetch fresh files, not serve stale cache.
- Lesson: `skipWaiting()` + `clients.claim()` are NOT enough to invalidate cache-first responses from the old SW's fetch handler.
