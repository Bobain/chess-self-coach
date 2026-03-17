Iterative review loop: refresh explanations, validate texts, fix issues, repeat until stable. Max 10 iterations.

For each iteration (1 to 10):

**Step 1 — Refresh explanations:**
Run `uv run chess-self-coach train --refresh-explanations`. Note how many were updated.

**Step 2 — Mechanical tests:**
Run `uv run pytest tests/test_training_texts.py -v`. If any test fails:
- Fix the root cause in `src/chess_self_coach/trainer.py` (the generation code, NOT the test)
- Go back to Step 1 (the fix may affect other positions)

**Step 3 — Semantic review:**
Run `uv run python3 scripts/review_texts.py`. If exit code 1 (issues found):
- If systemic (pattern across multiple positions): fix `_generate_context()` or `generate_explanation()` in trainer.py
- If data bug: fix the root cause in the generation code
- Go back to Step 1

**Step 4 — Stability confirmation:**
If no issues found in Step 2 and Step 3:
- Run a FINAL `uv run chess-self-coach train --refresh-explanations`
- Run a FINAL `uv run pytest tests/test_training_texts.py -v`
- If both pass with 0 changes: declare **STABLE**
- If anything changed: go back to Step 1

**Step 5 — Cleanup:**
Run `rm -f .pending-review-training` to clear the marker.
Report: number of iterations, fixes applied, final position count, test results.
