Analyze classification errors across the full ground truth dataset, find common patterns via parallel chess analysis agents, and derive improved rules for the !! and ! classifier.

**Goal**: maximize macro F1 without overfitting. Rules must be simple and explainable to a 1200 ELO player.

## Step 1: Collect all classification results

Run the real JS classifier (via Playwright, `window._classifyMove`) on ALL games in `tests/e2e/classification_cases.py` and collect:
- All TP (correctly classified as !! or !)
- All FN (expected !! or ! but classified as other)
- All FP (classified as !! or ! but expected other)
- For each move: idx, move SAN, cp before→after, is_mate, best move, PV (5 moves), oppEPL, eplLost, wpBefore

Also extract the same data for the move BEFORE and the move AFTER each move (the 3-move context window).

Print a summary: TP/FP/FN counts for both brilliant and great, plus current macro F1.

Also compute and display the **current regularized score** BEFORE any changes by running:
`uv run pytest tests/e2e/test_review.py::test_classification_macro_f1_regression -v -s -n0`
This prints: macro F1, complexity breakdown (thresholds + conditions + helpers), penalty, and regularized score. Save these BEFORE values for comparison in Step 5.

## Step 2: Deep chess analysis with 4 parallel agents

Launch 4 specialized agents in parallel. Each receives moves with full 3-move context (move before, the move, move after) including FEN, Stockfish eval, best lines, and PV.

**Agent 1 — Brilliant (all TP/FP/FN !!)**: Analyze ALL brilliant-related moves together (typically few moves). For TP: what makes the current rules work — preserve these patterns. For FP: why the algorithm flags them incorrectly. For FN: what the algorithm misses and how to detect it. Propose fixes for brilliant detection.

**Agent 2 — TP Great**: Analyze all TRUE POSITIVE great moves. What makes the current rules work? What patterns do correctly-detected great moves share? This understanding is essential to ensure new rules/filters don't break existing TP.

**Agent 3 — FP Great**: Analyze all FALSE POSITIVE great moves. Why does the algorithm flag them but the human says they're not great? What distinguishes them from true great moves? Propose filters to eliminate FP without hurting TP.

**Agent 4 — FN Great**: Analyze all FALSE NEGATIVE great moves. Why should these be classified as great? What chess characteristics make them stand out that the current rules miss? Propose new detection rules to catch them.

Each agent must:
- Use Stockfish eval AND their own chess judgment
- Identify COMMON patterns across moves, not individual explanations
- Propose quantitative criteria that could be implemented in code
- Explicitly flag any rule that would be overfitting
- Reference the TP analysis to ensure proposals don't break existing correct classifications
- **Estimate the exact complexity cost** of each proposed rule. Complexity is computed by `_count_classifier_complexity()` in `tests/e2e/test_review.py` which dynamically parses `classifyMove()` and its helper functions in `app.js`:
  - **Thresholds** = unique numeric constants in comparisons (e.g. `>= 0.15`, `< -0.005`). Counted as unique values across all relevant functions. Reusing an existing threshold (e.g. 0.02) costs 0.
  - **Conditions** = number of `if(` statements in the brilliant/great code zone and its helpers
  - **Helpers** = number of functions called from the brilliant/great zone (e.g. isSacrifice, winProb)
  - **Total complexity** = thresholds + conditions + helpers
  - **Regularized score** = macro_F1 - 0.10 × complexity / 50
  - A rule that adds 5 conditions for 0.01 F1 gain will LOWER the score (penalty +0.01 > F1 gain +0.01). Such rules must be rejected or simplified.
  - Removing a redundant condition REDUCES complexity and IMPROVES the score even with no F1 change.

## Step 3: Pattern synthesis

Collect all 4 agent analyses and find convergent themes:
- What do TP great moves have in common? (Agent 2) — these patterns MUST be preserved
- What patterns do FN great moves share that the current rule misses? (Agent 4)
- What patterns do FP great moves share that could filter them out? (Agent 3)
- Do any proposed FP filters risk removing TP? Cross-check Agent 3 proposals against Agent 2 findings
- Is the current oppEPL rule salvageable, or should it be replaced/augmented?
- Are there simpler rules that achieve better F1?
- What fixes does Agent 1 propose for brilliant detection?

## Step 4: Rule derivation

Derive new rules from the synthesis. Requirements:
- **Explainable**: a 1200 ELO player must understand why a move is !/!!
- **General**: rules must apply to chess in general, not our specific games
- **No overfitting**: if a rule only helps on 2-3 specific positions, reject it
- **Quantitative**: rules must use available data (eval, PV, material, oppEPL, eplLost, wpBefore)

Present the proposed rules clearly with:
- The rule in plain language
- The rule in code-like pseudocode
- Expected impact on FN and FP counts
- **Expected complexity cost** (how many new thresholds, conditions, helpers)
- **Expected regularized score impact**: score = macro_F1 - 0.10 × complexity / 50. A rule that adds 10 conditions for 0.01 F1 gain will LOWER the score — reject it.
- Any tradeoffs

Ask the user to validate the proposed rules before implementing.

## Step 5: Implementation

After user approval:
1. Update `classifyMove()` in `pwa/app.js`
2. Run `uv run pytest tests/e2e/test_review.py -v` — all tests must pass
3. Run `uv run pytest tests/e2e/test_review.py::test_classification_macro_f1_regression -v -s -n0` to get the AFTER metrics
4. Print a clear BEFORE/AFTER comparison table:
   ```
   | Metric              | BEFORE | AFTER | Delta |
   |---------------------|--------|-------|-------|
   | Macro F1            |  0.488 | 0.xxx | +x.xx |
   | Thresholds          |     14 |    xx |   +xx |
   | Conditions          |     25 |    xx |   +xx |
   | Helpers             |      2 |    xx |   +xx |
   | Total complexity    |     38 |    xx |   +xx |
   | Penalty             | -0.076 | -x.xx |       |
   | Regularized score   |  0.412 | 0.xxx | +x.xx |
   ```
5. **AUTOMATIC ROLLBACK**: If the regularized score decreases (or if macro F1 decreases, or if tests fail), immediately run `git checkout pwa/app.js` to revert ALL changes. Do NOT attempt to fix or adjust the broken code — revert first, then analyze what went wrong. Report the failure to the user with the BEFORE/AFTER table showing why the score dropped.
6. Only if the regularized score strictly IMPROVES: commit with descriptive message including the before/after regularized scores.

## Important rules

- NEVER use a Python proxy of the classifier. ALWAYS use `window._classifyMove` via Playwright for error collection and scoring.
- **BOTH SIDES**: errors include moves from both players.
- **NO OVERFITTING**: with a larger dataset the risk increases. Every proposed rule must be justified by a general chess principle.
- Pay special attention to !! moves — they are rare and each FN/FP matters more.
- The analysis agents should receive the FULL context: FEN, cp, mate_in, best_move, PV, and the same for the move before and after.
- **ROLLBACK ON REGRESSION**: if ANY implementation attempt lowers the regularized score, revert immediately with `git checkout pwa/app.js`. Never try to "fix forward" — revert first, analyze, then try a different approach.
