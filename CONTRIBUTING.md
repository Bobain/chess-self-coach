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

## Coding Guidelines

See [`.claude/CLAUDE.md`](.claude/CLAUDE.md) for detailed guidelines:
- **Karpathy Principles** — Think before coding, simplicity first, surgical changes, goal-driven execution
- **E2E Testing** — No silent errors, test with real data, always capture console

---

## Chess Context

### Player
- Level: ~1000 Elo chess.com rapid (15+10), ~700 estimated FIDE
- Lichess: [bobainbobain](https://lichess.org/@/bobainbobain)
- Chess.com: [Tonigor1982](https://www.chess.com/member/Tonigor1982)
- Target depth: essentials (5-6 moves + common deviations)

### Lichess Studies
- [Whites - Queen's Gambit](https://lichess.org/study/ucjmuish)
- [Black vs e4 - Scandinavian](https://lichess.org/study/IoJ5waZo)
- [Black vs d4 - Slav](https://lichess.org/study/x3z4bEQ6)

### Repertoire
- **White**: Queen's Gambit (1.d4 2.c4) — Harrwitz Attack (5.Bf4) vs QGD
- **Black vs 1.e4**: Modern Scandinavian (1...d5 2.exd5 Nf6) — Fianchetto setup (...g6/...Bg7)
- **Black vs 1.d4**: Slav Defense (1...d5 2...c6) — Czech Variation (...dxc4, ...Bf5 BEFORE e6)
- **Black vs London**: Anti-London with immediate ...c5

### PGN Files
Located in `pgn/`. Two versions per opening:
- `*_annote.pgn` — Annotated reference version (comments, variation names, theory markers)
- `*.pgn` — Working copy (may contain Stockfish annotations)

### PGN Format
- Each `[Event "Variation name (ECO)"]` = one chapter
- `[Orientation "white"]` or `"black"` = board orientation
- Variations in parentheses `(...)`
- Comments in braces `{...}`
- Stockfish annotations: `{[%eval +0.32]}` (added by CLI or Lichess)

### MANDATORY Comment Conventions

#### Names and references
- Always use the **official name** of the opening/variation (e.g., "Czech Variation", "Harrwitz Attack")
- Include the **ECO code** when known (e.g., ECO D17, ECO B01)
- Mention **elite players** who use the line (e.g., "played by Carlsen, Kramnik")

#### Theoretical status
- Mark **THEORY:** when a move is the theoretical consensus
- Indicate if a line is **modern** or **historical**
- Note when a move is **inferior** or **rare** according to theory
- Flag cases where **in practice** results differ from theory

#### Pedagogical explanations
- Explain the **WHY** of each move, not just name it
- Indicate the **plan** after the last move of each line (e.g., "Plan: O-O, Rc1, c-file pressure")
- Flag **traps** with TRAP or WARNING + full explanation
- Mark **TYPICAL MISTAKE** to avoid at the player's level
- Mention **transpositions** when a line joins another

### 2-Zone Workflow

```
Zone 1: Local Files      →  Zone 2: Lichess Study
  (CLI prepares + analyzes)    (source of truth + interactive study)
  *_annote.pgn                 → Chessdriller (drill)
```

#### Zone 1 → Zone 2: Preparation → Publication
1. CLI/Claude creates/modifies `*_annote.pgn` files locally
2. ALL comment conventions must be followed
3. Theory verified via web search (variation names, consensus, players)
4. `chess-self-coach validate` to check annotations
5. `chess-self-coach analyze` for Stockfish validation
6. `chess-self-coach push` to publish to Lichess Study

#### Zone 2: Interactive study
1. Lichess Study = **source of truth**
2. User studies interactively on Lichess (play moves, engine analysis)
3. `chess-self-coach pull` to sync changes back to local

#### Optional: En-Croissant
En-Croissant is a desktop chess GUI for offline visual review of PGN files.
Not required — Lichess Study provides the same functionality online.
If used: **NEVER** write to a file open in En-Croissant → write conflict guaranteed.

### Coaching Journal (MANDATORY)

After EVERY chess theory discussion (Q&A about openings, style, move choices, repertoire decisions):
1. Create or update a topic file in `coaching/topics/YYYY-MM-DD-slug.md`
2. Update `coaching/INDEX.md` with the new entry (categorized by opening)
3. This is **AUTOMATIC** — do NOT wait for the user to ask

### UI Documentation
- Step-by-step UI guides are in `guides/`
- These guides are **evolutionary**: marked `[TO CONFIRM]` until validated by user
- NEVER affirm a UI workflow without user validation
