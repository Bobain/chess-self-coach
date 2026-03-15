---
date: 2026-03-15
topic: Is En-Croissant necessary in the workflow?
opening: General / Tooling
eco: n/a
status: resolved
---

## Question

En-Croissant was originally Zone 2 of the workflow (validation before Lichess). Now that the CLI does Stockfish analysis and Lichess has SF18 in the browser — is En-Croissant still needed?

## Discussion

With the CLI (`chess-opening-prep analyze`) handling batch Stockfish analysis and Lichess Study providing interactive board + SF18 in browser, En-Croissant's role was questioned step by step:

1. **Stockfish analysis**: CLI does this now (batch mode, depth 18) → En-Croissant not needed
2. **Visual validation**: Lichess Study provides the same interactive board → En-Croissant not needed
3. **Interactive study (playing moves, seeing responses)**: Lichess Study does this with SF18 NNUE in browser → En-Croissant not needed
4. **Annotations/comments UX**: User suspects En-Croissant might have better UX — **undecided**, needs testing

The workflow was simplified from 3 zones to 2:
- Before: Local → En-Croissant → Lichess Study
- After: Local (CLI) → Lichess Study

## Actions Taken

- En-Croissant moved to "Optional" in all documentation (CLAUDE.md, README.md, docs/setup.md)
- Workflow diagram updated to 2 zones
- Code comments cleaned (removed "En-Croissant format" references)
- Committed as v0.1.2

## Key Takeaways

- En-Croissant is optional — Lichess Study replaces it for online use
- The only remaining advantage of En-Croissant: offline review + potentially better annotation UX (unconfirmed)
- If En-Croissant IS used: never write to files it has open (conflict guaranteed)
