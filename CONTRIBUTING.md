# Contributing to chess-self-coach

## Code Guidelines (Karpathy Principles)

All contributions must follow these four principles, derived from [Andrej Karpathy's observations](https://github.com/forrestchang/andrej-karpathy-skills/blob/main/CLAUDE.md) on reducing common coding mistakes.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- If you write 200 lines and it could be 50, rewrite it.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- Every changed line should trace directly to the task at hand.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

- "Add feature X" → write a test, then make it pass.
- "Fix bug Y" → reproduce it first, then fix it.
- For multi-step tasks, state a brief plan with verification for each step.

## Code Style

- **Language**: All code, comments, docstrings, error messages, and logs in English.
- **Docstrings**: Required on every module, class, and function (Google style).
- **Type hints**: Use `from __future__ import annotations` and type all function signatures.
- **Formatting**: Follow PEP 8. Use `ruff` if available.

## PGN Conventions

See `.claude/CLAUDE.md` for PGN annotation conventions (THEORY markers, trap warnings, etc.).

## Development Setup

```bash
git clone https://github.com/Bobain/chess-self-coach.git
cd chess-self-coach
uv venv && uv sync
chess-self-coach --help
```
