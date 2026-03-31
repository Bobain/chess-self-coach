Iteratively optimize the !! and ! classifier using automated parameter sweep + optional structural changes.

**Goal**: maximize regularized score = macro_F1 - 0.10 * complexity / 50. Rules must be simple and explainable to a 1200 ELO player. NO OVERFITTING.

**Macro F1**: (F1_brilliant + F1_great) / 2, computed globally (aggregate TP/FP/FN across ALL games). F1_other excluded.

**Classifier location**: `src/chess_self_coach/classifier.py` → `classify_move()` function + `DEFAULT_CONFIG` dict.
**Sweep script**: `scripts/sweep_classifier.py` — automated parameter sweep, ~500 evaluations in ~15s.
**Scoring function**: `from chess_self_coach.classifier import score_classifier` — callable standalone, no pytest needed.

---

## Tier 1: Automated Parameter Sweep

### Step 1: Collect data + BEFORE baseline

Run `/collect-classifier-data` to get `/tmp/classifier_data.json` with enriched features + tactical motifs (useful for interpreting results later).

Then get the BEFORE baseline score:
```bash
uv run python3 -c "from chess_self_coach.classifier import score_classifier; score_classifier()"
```

### Step 2: Run the sweep

```bash
uv run python3 scripts/sweep_classifier.py
```

This runs 4 phases automatically (~15s total):
- **Phase A**: Single-parameter sensitivity — sweeps each threshold + tests each of 34 motifs as brilliant/great trigger
- **Phase B**: Greedy combination — builds the best multi-parameter config from Phase A winners
- **Phase C**: Random perturbation — 200 random variations around Phase B result to catch non-linear interactions
- **Phase D**: LOGO cross-validation — Leave-One-Game-Out on top candidates to detect overfitting

Output: full report to stdout + `/tmp/sweep_results.json`.

### Step 3: Interpret results

Read the sweep report and evaluate:

1. **Score improvement**: Is the delta meaningful (> 0.005)?
2. **LOGO divergence**: Is |full_score - LOGO_score| < 0.03? If not, overfitting risk.
3. **Brilliant stability**: Only 7 labels — any change to brilliant F1 is noisy.
4. **Chess validity**: Does every config change represent a general chess principle?
   - Example GOOD: "Require larger EPL gain for brilliant" → more selective, reduces false positives
   - Example BAD: "Add isEnPassant as great motif" → en passant captures aren't inherently great moves
5. **TP/FP/FN tradeoff**: Losing TP to eliminate FP is good when FP >> FN.

### Step 4: Apply best config

If the sweep found a valid improvement:

1. Update `DEFAULT_CONFIG` in `src/chess_self_coach/classifier.py` with the new values
2. Verify the score matches:
```bash
uv run python3 -c "from chess_self_coach.classifier import score_classifier; score_classifier()"
```
3. Regenerate classifications:
```bash
uv run python3 -c "from chess_self_coach.classifier import run_classification; run_classification()"
```
4. Run tests:
```bash
uv run pytest tests/test_classifier.py -v
```
5. Commit with BEFORE/AFTER scores.

---

## Tier 2: Structural Changes (optional)

Only proceed to Tier 2 if:
- Tier 1 found no improvement OR the score plateaus
- There are clear FN patterns that no threshold/motif change can fix
- The `/tmp/classifier_data.json` shows categories of missed moves requiring new detection logic

### When to use Tier 2

Examine the FN list from `/tmp/classifier_data.json`:
- FN brilliants without `isSacrifice` → needs new brilliant detection path
- FN greats without opponent blunder → needs motif-based great path (but Tier 1 tests this automatically)
- FN with specific tactical patterns → might need new helper functions

### How to execute Tier 2

Launch **up to 4 Agent calls in a single message** with `isolation: "worktree"`. Each agent:

1. Edits `src/chess_self_coach/classifier.py` — the `classify_move()` function or adds helpers
2. Runs: `uv run python3 -c "from chess_self_coach.classifier import score_classifier; r=score_classifier(); print(r)"`
3. Reports the result in structured format

**Agent prompt must include**: the EXACT current code of `classify_move()` + the specific structural change to make.

After all agents complete:
- Compare scores, record learnings
- Apply best structural change to `dev` branch
- Re-run Tier 1 sweep to find optimal thresholds for the new structure
- Commit with BEFORE/AFTER scores

---

## Tunable parameters in DEFAULT_CONFIG

```python
DEFAULT_CONFIG = {
    "brilliant_epl_max": -0.005,        # epl_lost < this → brilliant candidate
    "brilliant_wp_min": 0.20,           # wp_before > this
    "brilliant_wp_max": 0.95,           # wp_before < this
    "brilliant_motifs": ["isSacrifice"],  # motifs that trigger brilliant
    "great_epl_max": 0.02,             # epl_lost <= this
    "great_opp_epl_min": 0.15,         # opp_epl >= this
    "great_filter_recapture": True,     # filter trivial recaptures
    "great_motifs": [],                 # motifs that trigger great (without opp_epl)
    "miss_epl_min": 0.05,              # epl_lost > this
    "miss_opp_epl_min": 0.15,          # opp_epl >= this
}
```

## Complexity reference

Complexity is computed by `count_config_complexity()` (fast, analytical) or `count_complexity()` (regex on source):
- **Thresholds**: numeric parameters in the brilliant/great zone (5 in DEFAULT_CONFIG)
- **Conditions**: base structure conditions + len(brilliant_motifs) + len(great_motifs)
- **Helpers**: fallback functions called from the zone
- **Total** = thresholds + conditions + helpers

## Important rules

- **Tier 1 first**: always run the sweep before attempting structural changes
- Use the **Python classifier** (`classifier.py`) — NOT JS
- **Scoring**: call `score_classifier()` directly — no pytest needed for hypothesis testing
- **NO OVERFITTING**: every rule must be a general chess principle
- **LOGO validation**: check cross-validation divergence before applying any change
- **Brilliant warning**: only 7 labels — brilliant F1 is inherently unstable
