Analyze classification errors across the full ground truth dataset using per-position chess analysis, find common patterns, and derive improved rules for the !! and ! classifier.

**Goal**: maximize regularized score = macro_F1 - 0.10 × complexity / 50. Rules must be simple and explainable to a 1200 ELO player. NO OVERFITTING.

**Macro F1 definition**: computed globally (all TP/FP/FN aggregated across ALL games, not per-game averages) for 3 classes: `brilliant`, `great`, and `other` (any move that is neither !! nor !). F1 is calculated per class, then macro F1 = (F1_brilliant + F1_great + F1_other) / 3. Note: F1_other is typically ~0.97 because 95% of moves are "other" and most are correctly classified. The lever for improvement is F1_brilliant (~0.67) and F1_great (~0.49). Reducing FP great hurts F1_other too (FP great = FN other), so there's a trade-off.

## Step 1: Collect data + BEFORE score

Run `/collect-classifier-data` to get all TP/FP/FN moves with 3-move context.

This outputs `/tmp/classifier_data.json` with all !! and ! classified moves (by the REAL JS classifier via Playwright), their ground truth labels, and Stockfish evaluations.

Also note the BEFORE baseline: macro F1, complexity breakdown, regularized score.

## Step 2: Per-position chess analysis with parallel agents

Read `/tmp/classifier_data.json`. Launch `chess-position-analyst` agents in parallel (use `subagent_type` from the `.claude/agents/` directory).

**Batching**: group moves into batches of ~10-15 positions per agent to balance parallelism and context. Each batch should mix TP, FP, and FN to give the agent perspective on what works vs what doesn't.

Each agent receives the batch of moves with full context and must analyze each position individually, explaining:
- TP: why the classification is correct (what chess principle)
- FP: why this is NOT really !! or ! (what makes it routine)
- FN: why this SHOULD be !! or ! (what the algorithm misses)

Each move includes `prev_move_class` — the classifier's category for the opponent's preceding move (blunder, mistake, inaccuracy, etc.). This is a key signal: exploiting a blunder (??) is different from finding a great move independently. A move that follows a blunder is a punishment (potentially !), not a discovery (!!).

For each move, the agent returns: chess analysis, key principle, and quantitative signal.

## Step 3: Pattern synthesis

Collect all agent analyses. Group them:

**For !! moves**: what principles do TP brilliant share? What makes FP brilliant incorrect? What makes FN brilliant special?

**For ! moves**: what principles do TP great share? What makes FP great incorrect? What makes FN great special?

Find COMMON patterns — principles that appear across multiple positions, not one-off explanations. These patterns become candidate rules.

## Step 4: Rule derivation

From the common patterns, derive quantitative rules. Requirements:
- **Explainable**: a 1200 ELO player must understand why a move is !/!!
- **General**: must apply to chess in general, not our specific games
- **No overfitting**: reject rules that only help 2-3 positions
- **Quantitative**: must use available data (eval, PV, material, oppEPL, eplLost, wpBefore, is_best, is_capture, is_check)

For each proposed rule:
- The rule in plain language
- Pseudocode
- Expected FN reduction and FP change
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
