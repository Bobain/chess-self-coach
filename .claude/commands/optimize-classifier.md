Iteratively optimize the !! and ! classifier using fast simulation + parallel worktree validation.

**Goal**: maximize regularized score = macro_F1 - 0.10 * complexity / 50. Rules must be simple and explainable to a 1200 ELO player. NO OVERFITTING.

**Macro F1**: (F1_brilliant + F1_great) / 2, computed globally (aggregate TP/FP/FN across ALL games). F1_other excluded.

**Classifier location**: `src/chess_self_coach/classifier.py` → `classify_move()` function.
**Tactics data**: `data/tactics_data.json` — 40 pre-computed tactical motifs per move (forks, pins, mate threats, etc.).
**Scoring function**: `from chess_self_coach.classifier import score_classifier` — callable standalone, no pytest needed.

**Limits**: max 20 worktree attempts (5 iterations x 4 parallel). Stop early if best score hasn't improved for 2 consecutive iterations.

---

## Step 1: Collect data + BEFORE baseline

Run `/collect-classifier-data` to get `/tmp/classifier_data.json` with enriched features + tactical motifs.

Then get the BEFORE baseline score:
```bash
uv run python3 -c "from chess_self_coach.classifier import score_classifier; score_classifier()"
```

Record in `/tmp/optimizer_state.md`:
- BEFORE score, macro_f1, complexity breakdown
- Feature statistics summary (key separating features between TP/FP/FN)
- Tactical motif correlations (which motifs distinguish TP from FP)

## Step 2: Fast simulation — sweep thresholds in Python

Read `/tmp/classifier_data.json`. For each tunable threshold in `classify_move()`, simulate the effect across a range using the exact feature values per move. Compute simulated F1 and score for each variant.

**Available features per move** (from collector + tactics_data.json):
- **Win probability**: `wp_before`, `wp_after`, `epl_lost`, `wp_gain`, `opp_epl`
- **Move properties**: `is_sacrifice`, `is_recapture`, `is_capture`, `is_check`, `piece_moved`, `pv_len`
- **Tactical motifs (on-move)**: `isFork`, `createsPin`, `isSkewer`, `createsMateThreat`, `isBackRankThreat`, `isKingSafetyDegradation`, `isSeventhRankInvasion`, `isTrappedPiece`, `isDesperado`, `isHangingCapture`, etc.
- **Tactical motifs (in PV)**: same motifs detected in the best line (3 moves deep)
- **Context**: `prev_classification`, `in_opening`

## Step 3: Generate 4 hypotheses

From simulation results AND accumulated learnings, pick the **4 most promising** changes to `classify_move()` in `classifier.py`.

**Categories** (one from each when possible):
1. **Threshold tune**: change a numeric threshold
2. **New tactical condition**: use a motif from tactics_data (e.g. `if tactics.get("isFork"): return great`)
3. **New detection path**: add a rule for FN moves the classifier misses
4. **Simplify**: remove a condition to reduce complexity

Each hypothesis must be a **single, targeted change** in early iterations.

## Step 4: Parallel worktree validation

Launch **4 Agent calls in a single message** with `isolation: "worktree"`. Each agent:

1. Edits `src/chess_self_coach/classifier.py` — the `classify_move()` function
2. Runs: `uv run python3 -c "from chess_self_coach.classifier import score_classifier; r=score_classifier(); print(r)"`
3. Reports the result in structured format

**Agent prompt must include**: the EXACT current code of `classify_move()` + the specific edit to make.

## Step 5: Collect results + extract learnings

Parse results, record in `/tmp/optimizer_state.md`, update cumulative learnings (WORKS / DOESN'T WORK / NEUTRAL).

**Clean up all worktrees and branches** after each iteration.

## Step 6: Combine winners (later iterations only)

Combine individually-proven improvements.

## Step 7: Iterate or stop

**Stop conditions**: 20 attempts reached, or best score stale for 2 iterations.

## Step 8: Apply best result

Apply diff to `classifier.py` on `dev`. Then regenerate:
```bash
uv run python3 -c "from chess_self_coach.classifier import run_classification; run_classification()"
uv run pytest tests/test_classifier.py -v
```

Commit with BEFORE/AFTER scores.

## Complexity reference

Complexity is computed by `count_complexity()` in `classifier.py`:
- **Zone**: from start of `classify_move()` to last return of 'brilliant' or 'great'
- **Thresholds**: unique numeric constants in comparisons (integers <= 2 excluded)
- **Conditions**: `if` with numeric comparisons, function calls, or domain keywords. Guards excluded.
- **Helpers**: functions called from the zone. Flat cost: 1 point per helper (internals NOT counted).
- **Total** = thresholds + conditions + helpers

## Important rules

- All testing in **disposable worktrees** — `dev` is NEVER modified until Step 8
- **Clean up ALL worktrees** after each iteration
- Use the **Python classifier** (`classifier.py`) — NOT JS
- **Scoring**: call `score_classifier()` directly — no pytest needed for hypothesis testing
- **Tactical motifs available**: the classifier receives `tactics` dict with 40+ pre-computed motifs from `tactics_data.json`
- **BOTH SIDES**: all moves from both players are classified
- **NO OVERFITTING**: every rule must be a general chess principle
- **Single changes first**: early iterations test one change at a time
