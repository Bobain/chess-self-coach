Iteratively optimize the !! and ! classifier using parallel worktree experiments. Each iteration tests 4 hypotheses in isolated git worktrees, collects real scores, extracts learnings, and uses them to generate better hypotheses.

**Goal**: maximize regularized score = macro_F1 - 0.10 * complexity / 50. Rules must be simple and explainable to a 1200 ELO player. NO OVERFITTING.

**Macro F1**: (F1_brilliant + F1_great) / 2, computed globally (aggregate TP/FP/FN across ALL games). F1_other excluded (redundant, double-counts errors).

**Limits**: max 20 total attempts (5 iterations x 4 parallel). Stop early if best score hasn't improved for 2 consecutive iterations.

---

## Step 1: Collect data + BEFORE baseline

Run `/collect-classifier-data` to get `/tmp/classifier_data.json` with enriched features.

Then run the regression test for the BEFORE baseline:
```bash
uv run pytest tests/e2e/test_review.py::test_classification_macro_f1_regression -v -s -n0
```

Record in `/tmp/optimizer_state.md`:
- BEFORE score, macro_f1, complexity breakdown
- Feature statistics summary (key separating features between TP/FP/FN)
- Initial observations and promising directions

## Step 2: Generate 4 hypotheses

Based on feature statistics AND accumulated learnings from previous iterations, generate **4 distinct hypotheses**. Each hypothesis is a small, targeted change to `classifyMove()` in `pwa/app.js`.

For each hypothesis, write in `/tmp/optimizer_state.md`:
- Plain language description
- Pseudocode of the change
- Which FP/FN it targets
- Estimated complexity cost

**Diversity**: the 4 hypotheses should explore different directions:
- One might tune an existing threshold
- One might add a new condition to reduce FP
- One might add a new detection path to recover FN
- One might simplify (remove conditions) to reduce complexity

## Step 3: Parallel worktree experiments

Launch **4 Agent calls in a single message** with `isolation: "worktree"`. Each agent receives:

```
You are testing a classifier optimization hypothesis in an isolated worktree.

HYPOTHESIS: {description + pseudocode}

INSTRUCTIONS:
1. Edit `pwa/app.js` — modify the `classifyMove()` function according to the hypothesis above.
   Only modify code between the brilliant detection section and the last `return { category: 'great'` line.

2. Run the test:
   uv run pytest tests/e2e/test_review.py::test_classification_macro_f1_regression -v -s -n0

3. Parse the GLOBAL CLASSIFICATION SUMMARY from stdout and report EXACTLY this format:

RESULT:
hypothesis: {one-line description}
score: {regularized score}
macro_f1: {macro F1}
brilliant_tp: {N} brilliant_fp: {N} brilliant_fn: {N} brilliant_f1: {F1}
great_tp: {N} great_fp: {N} great_fn: {N} great_f1: {F1}
complexity: {N} (thresholds: {N}, conditions: {N}, helpers: {N})
status: {improved|regressed|error}
diff:
{the git diff of pwa/app.js}
END_RESULT

If the test errors or times out, report status: error with the error message.
```

**Important**: all 4 agents must be launched in the SAME message for true parallelism.

## Step 4: Collect results + extract learnings

After all 4 agents complete:

1. Parse each agent's RESULT block
2. Record all 4 results in `/tmp/optimizer_state.md` under the current iteration
3. **Synthesize learnings** — for each result, note:
   - Did it improve or regress? By how much?
   - Which FP/FN were affected? (compare TP/FP/FN to baseline)
   - Was the complexity tradeoff worth it?
   - What general principle does this teach? (e.g. "raising oppEpl threshold loses more TP than it removes FP")
4. Update the **cumulative learnings** section:
   - "WORKS": changes that improved score (keep exploring this direction)
   - "DOESN'T WORK": changes that regressed (avoid in future iterations)
   - "NEUTRAL": changes with no significant effect
   - "PROMISING BUT COSTLY": good F1 improvement but too much complexity

## Step 5: Iterate or stop

**Stop conditions** (any of):
- 20 total attempts reached (5 iterations done)
- Best score hasn't improved for 2 consecutive iterations (8 attempts)
- All 4 attempts in an iteration returned same or worse score

If continuing: go back to Step 2. The new hypotheses MUST be informed by the accumulated learnings — do NOT repeat failed approaches.

## Step 6: Apply best result

Once the loop ends:
1. Find the attempt with the highest score across ALL iterations
2. If it improves over BEFORE baseline:
   - Show BEFORE/AFTER comparison table
   - Show the diff
   - Ask the user for validation
   - If approved: apply the diff to `pwa/app.js` on `dev`, run the full test suite (`uv run pytest tests/e2e/test_review.py -v`), commit with BEFORE/AFTER scores in message
3. If no attempt improved: report this honestly with a summary of what was tried and why nothing worked

## Complexity reference

Complexity is computed by `_count_classifier_complexity()` in `tests/e2e/test_review.py`:
- **Zone**: from start of `classifyMove()` to last `return { category: 'brilliant'` or `'great'`
- **Thresholds**: unique numeric constants in comparisons (integers <= 2 excluded). Reusing an existing threshold costs 0.
- **Conditions**: `if()` with numeric comparisons, function calls, or domain keywords. Null/type guards NOT counted.
- **Helpers**: functions called from the zone (e.g. `isSacrifice`, `winProb`). Flat cost: 1 point per helper (internals NOT counted — a well-named helper encapsulates complexity, it doesn't add it).
- **Total** = thresholds + conditions + helpers

## Important rules

- All testing happens in **disposable worktrees** — `dev` is never modified until Step 6
- All worktrees are cleaned up after each iteration (they are learning branches, not persistent)
- NEVER use a Python proxy of the classifier — the test uses `window._classifyMove` via Playwright
- **BOTH SIDES**: all moves from both players are classified
- **NO OVERFITTING**: every rule must be a general chess principle
- Pay special attention to !! — rare, each error matters disproportionately
