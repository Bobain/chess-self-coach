Analyze classification errors across the full ground truth dataset using per-position chess analysis, find common patterns, and derive improved rules for the !! and ! classifier.

**Goal**: maximize regularized score = macro_F1 - 0.10 × complexity / 50. Rules must be simple and explainable to a 1200 ELO player. NO OVERFITTING.

**Macro F1 definition**: computed globally (all TP/FP/FN aggregated across ALL games, not per-game averages) for 2 classes: `brilliant` and `great`. F1 is calculated per class, then macro F1 = (F1_brilliant + F1_great) / 2. F1_other is excluded because it's ~0.97 constant (95% of moves are "other") and double-counts errors already penalized by F1_brilliant and F1_great (FP_great = FN_other).

## Step 1: Collect data + BEFORE score

Run `/collect-classifier-data` to get all TP/FP/FN moves with enriched features.

This outputs:
- `/tmp/classifier_data.json` — all !! and ! classified moves with features
- Feature statistics printed to stdout (median/mean per TP/FP/FN for each feature)
- `/tmp/batch_*.txt` — human-readable batches for agent analysis

**Features available per move** (computed by `collect_classifier_data.py`):
- **Win probability**: `wp_before`, `wp_after`, `epl_lost`, `wp_gain`, `opp_epl`
- **Centipawn**: `cp_gain` (raw cp change from player's perspective)
- **Move properties**: `is_sacrifice` (from JS `isSacrifice()`), `is_recapture`, `is_capture`, `is_check`, `is_promotion`, `piece_moved`, `pv_len`
- **Context**: `prev_classification`, `in_opening`, `is_best`

Also note the BEFORE baseline: macro F1, complexity breakdown, regularized score (from the test).

## Step 2: Feature analysis (data-driven)

**Before launching agents, analyze the feature statistics yourself.** The collection script prints distributions per TP/FP/FN for each feature. Look for:

1. **Separating features**: features where TP and FP/FN have very different distributions (e.g. "FP great have median opp_epl=0.03, TP great have median opp_epl=0.25" → the threshold 0.15 is too low)
2. **Unused signals**: features that strongly correlate with ground truth but are NOT in the current classifier (e.g. `pv_len`, `cp_gain`, `piece_moved`)
3. **Threshold tuning**: existing thresholds that could be tightened or relaxed based on the data
4. **Feature combinations**: two features that together separate TP from FP better than either alone

Write a summary of findings BEFORE proposing rules. This is the feature engineering step.

## Step 3: Per-position chess analysis (parallel agents)

Read `/tmp/classifier_data.json`. Launch general-purpose agents in parallel to analyze FN and FP moves.

**Focus on errors**: agents should analyze FP and FN moves, not TP (TP already works). For each error:
- FP: why this is NOT really !! or ! — what makes it routine despite high metrics
- FN: why this SHOULD be !! or ! — what signal the classifier is missing

Each move includes all features listed above. The agent should identify which features could distinguish this error from correct classifications.

**Batching**: ~10-15 positions per agent, mixing FP and FN.

## Step 4: Rule derivation

Combine the feature statistics (Step 2) with the chess analysis (Step 3) to derive rules.

**Feature engineering first**: can an existing threshold be adjusted? Can a new feature (already computed) be added to an existing rule? These are cheaper than new rules.

Requirements:
- **Explainable**: a 1200 ELO player must understand why a move is !/!!
- **General**: must apply to chess in general, not our specific games
- **No overfitting**: reject rules that only help 2-3 positions
- **Data-backed**: every rule must be justified by the feature statistics, not just chess intuition

For each proposed rule:
- The rule in plain language
- Pseudocode
- **Feature evidence**: which features separate TP from FP/FN, with numbers
- Expected FN reduction and FP change (count specific moves affected)
- **Complexity cost**: thresholds + conditions + helpers. Complexity is computed by `_count_classifier_complexity()` in `tests/e2e/test_review.py`:
  - **Zone analyzed**: only the code from the start of `classifyMove()` up to and including the last `return { category: 'brilliant'` or `return { category: 'great'` — NOT the miss/best/excellent/etc. code after it.
  - **Thresholds**: unique numeric constants in comparisons (e.g. `>= 0.15`, `< -0.005`). Integers ≤ 2 are excluded (loop indices). Reusing an existing threshold costs 0.
  - **Conditions**: only RULE conditions count — `if()` statements containing numeric comparisons, function calls, or domain keywords (`isOpening`, `is_mate`, `isRecapture`, etc.). Pure null/type GUARDS (`if (!prevMove || score_cp == null)`) are NOT counted — they are defensive boilerplate, not classification logic.
  - **Helpers**: functions called from the brilliant/great zone (e.g. `isSacrifice`, `winProb`). Discovered dynamically, not hardcoded.
  - **Total** = thresholds + rule_conditions + helpers. Removing a redundant condition REDUCES complexity and improves the score.
- **Expected score impact**: will regularized score improve? A rule adding 5 conditions for 0.01 F1 gain will LOWER the score.

Present rules to the user for validation before implementing.

## Step 5: Implementation

After user approval:
1. Update `classifyMove()` in `pwa/app.js`
2. Run `uv run pytest tests/e2e/test_review.py -v` — all tests must pass
3. Run `uv run pytest tests/e2e/test_review.py::test_classification_macro_f1_regression -v -s -n0` for AFTER metrics
4. Print BEFORE/AFTER comparison table:
   ```
   | Metric              | BEFORE | AFTER | Delta |
   |---------------------|--------|-------|-------|
   | Macro F1            |        |       |       |
   | Thresholds          |        |       |       |
   | Conditions          |        |       |       |
   | Helpers             |        |       |       |
   | Total complexity    |        |       |       |
   | Penalty             |        |       |       |
   | Regularized score   |        |       |       |
   ```
5. **AUTOMATIC ROLLBACK**: If regularized score decreases OR macro F1 decreases OR tests fail → immediately `git checkout pwa/app.js`. Do NOT try to fix forward. Report failure with the table showing why.
6. Only if score strictly improves: commit with before/after scores in message.

## Important rules

- NEVER use a Python proxy of the classifier. The `/collect-classifier-data` skill uses `window._classifyMove` via Playwright.
- **BOTH SIDES**: all moves from both players are analyzed.
- **NO OVERFITTING**: every rule must be a general chess principle.
- **ROLLBACK ON REGRESSION**: revert immediately, analyze, try different approach.
- Pay special attention to !! — rare, each error matters more.
