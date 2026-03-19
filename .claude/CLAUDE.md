# Chess Self-Coach

## Code Guidelines

All code, comments, docstrings, error messages, and logs must be in **English**.

### Karpathy Principles

Behavioral guidelines to reduce common LLM coding mistakes, derived from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876). These bias toward caution over speed — for trivial tasks, use judgment.

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

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

### Code Style

- **Docstrings**: Required on every module, class, and function (Google style).
- **Type hints**: Use `from __future__ import annotations` and type all function signatures.
- **Formatting**: Follow PEP 8. Use `ruff` if available.
- **Commits**: Commit at each logical step — don't accumulate changes. Each commit = one self-contained unit.

---

## Architecture: Demo vs Application

The PWA has identical features everywhere (Stockfish WASM runs in the browser). The only difference is the data source:

- **Demo** (`[demo]`): GitHub Pages, sample `training_data.json`. Shows what the app can do.
- **Application** (`[app]`): Installed via one-liner. Python CLI generates `training_data.json` from YOUR games (fetch + native Stockfish batch analysis).

**Critical constraint**: never break the `[demo]`. All JS must work without a backend.

Full architecture table: see CONTRIBUTING.md § Architecture.

---

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

- The `console_errors` fixture in `tests/e2e/conftest.py` is `autouse=True` — it automatically captures all browser console messages and JS errors for every test.
- Tests fail automatically if any JS error is detected.
- All console output is printed in pytest `-v` output for debugging.
- NEVER run Playwright tests without console capture. If writing a standalone debug script, always attach `page.on('console')` and `page.on('pageerror')` listeners.
- Use `console_errors["messages"]` in assertions to verify that specific JS code paths were executed (e.g., `assert "[showFeedback]" in log_text`).

### JavaScript: Always Add Console Logs in Key Functions

- Every user-facing function (`showFeedback`, `handleMove`, `showPosition`, etc.) MUST have `console.log` at entry with its key parameters.
- Every branch (correct/wrong/error) MUST log which path was taken.
- Every DOM lookup that could fail MUST log whether the element was found or null.
- These logs are essential for debugging in the browser console — without them, failures are invisible.
- This is NOT optional debug code to remove later. It stays permanently.

### Playwright: Annotated Screenshots for UI Communication

- When showing a UI element to the user, **generate an annotated screenshot** with Playwright instead of describing it in text.
- Technique: `page.evaluate()` injects a canvas overlay, draws a red arrow pointing to the element, then `page.screenshot()` captures the result.
- Use `page.locator('#element').bounding_box()` to get the element's position for the arrow.
- Save to `~/Screenshots/` and read the file to show the user.
- This avoids miscommunication ("where is it?") and saves debugging time.

### Service Worker: Network-First for Local Assets

- The PWA service worker MUST use **network-first** for same-origin assets (always serve fresh files from server, cache as offline fallback).
- **Cache-first** is only for CDN resources (which never change).
- `server.py` serves files dynamically (no temp dir) — the SW must fetch fresh files, not serve stale cache.
- Lesson: `skipWaiting()` + `clients.claim()` are NOT enough to invalidate cache-first responses from the old SW's fetch handler.

---

## ROADMAP Maintenance

The ROADMAP is a living document. Re-evaluate it at these triggers:
- **After completing a sub-section** (e.g., 3a done → review before starting 3b)
- **When hitting unexpected complexity** that changes priorities or reveals new dependencies
- **When the user asks** (`/plan` or "réévalue la roadmap")

A review checks: dependency ordering still correct? New gaps? DoD still clear? Priorities still make sense?

---

## Chess Context

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for chess-specific context: player profile, repertoire, PGN conventions, 2-zone workflow, and coaching journal rules.
