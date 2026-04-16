---
name: optimize-classifier-cv
description: Use when optimizing `src/chess_self_coach/classifier.py`, the serialized `great_xgb` model, or the `!!`/`!` move labels. Keeps the existing regularized score unchanged, separates rule tuning from ML tuning, and enforces game-level cross-validation without label leakage before applying any classifier change.
---

# Optimize Classifier CV

Use this skill when the user wants to improve move classification quality, revisit `/optimize-classifier`, reduce classifier overfitting, or compare candidate classifier changes.

Read [references/repo-reality-check.md](references/repo-reality-check.md) before making optimization decisions.

## Non-negotiables

- Keep the production metric unchanged:
  - `macro_F1 = (F1_brilliant + F1_great) / 2`
  - `score = macro_F1 - 0.10 * complexity / 50`
- Treat `src/chess_self_coach/classifier.py` as the source of truth.
- Use whole games as the split unit for validation.
- Do not accept a change only because it improves the full-fit `score_classifier()` result.
- Keep rules explainable to a club player. Reject narrow pattern memorization.

## Workflow

### 1. Map the current stack

Read the current code paths before changing anything:

- `src/chess_self_coach/classifier.py`
- `scripts/sweep_classifier.py`
- `scripts/train_classifier_ml.py`
- `scripts/collect_classifier_data.py`
- `tests/test_classifier.py`
- `tests/e2e/classification_cases.py`
- `tests/e2e/fixtures/classification_ground_truth.json`

If docs or old slash commands disagree with code, trust the code and call out the drift explicitly.

### 2. Record the baseline

Run these first:

```bash
uv run python3 -c "from chess_self_coach.classifier import score_classifier; print(score_classifier(verbose=True))"
uv run python3 scripts/collect_classifier_data.py
```

Capture:

- full-fit regularized score
- macro F1
- brilliant F1
- great F1
- complexity
- obvious TP / FP / FN patterns from `/tmp/classifier_data.json`

### 3. Choose the right optimization path

Use the error pattern to decide the lane:

- **Rule lane**: `DEFAULT_CONFIG`, brilliant logic, miss logic, complexity budget, motif gating
- **ML lane**: `great_xgb` features, threshold, training procedure, serialization
- **Hybrid lane**: when a rule change and an ML change interact materially

Default bias:

- If the problem is mostly `great` false positives / false negatives, start with `scripts/train_classifier_ml.py`.
- If the problem is mostly brilliant or miss behavior, start with `scripts/sweep_classifier.py`.
- If the current sweep finds an apparent win, treat it as a candidate generator, not as proof.

### 4. Enforce honest cross-validation

A held-out game must not influence:

- motif selection
- threshold selection
- model fitting
- threshold calibration
- feature decisions justified only by that held-out game's labels

Use this discipline:

- **Rule tuning**:
  - search candidate configs on training folds only
  - apply the selected config to the held-out game
  - aggregate held-out TP / FP / FN across all outer folds
- **ML tuning**:
  - train without the held-out game
  - generate out-of-fold probabilities for held-out games only
  - choose the classification threshold from training-fold logic or from aggregated out-of-fold predictions, never from full-fit predictions

Important:

- `score_classifier()` is the comparable production metric, but it is full-fit.
- `scripts/sweep_classifier.py` contains useful search logic, but its `logo_validate()` is a robustness check, not a fully honest out-of-fold evaluation.
- `scripts/train_classifier_ml.py` already contains the closest thing to honest LOGO evaluation in the repo for the `great` model. Reuse it before inventing a new ML loop.

If repeated honest evaluation is needed and no reusable helper exists, write a small deterministic script first instead of simulating folds manually in shell one-liners.

### 5. Optimize in the smallest useful step

Order of preference:

1. threshold or motif adjustment with the existing structure
2. model threshold or feature refinement
3. structural classifier changes

Do not jump to structural rewrites when a threshold, motif, or model-threshold change could explain the error pattern.

### 6. Accept or reject candidates

Prefer a candidate only when the evidence is coherent:

- honest out-of-fold score improves, or macro F1 improves with acceptable complexity
- full-fit score does not contradict the holdout result
- full-fit vs holdout divergence stays small enough to trust the result
- the chess rationale is generalizable
- the change is minimal relative to the gain

Useful default heuristics:

- improvement below `0.005` is usually noise unless it removes a clearly bad FP cluster
- `|full_fit - holdout| > 0.03` is an overfitting warning
- brilliant metrics are noisy because the label count is small

### 7. Apply and verify

After choosing a winner:

```bash
uv run python3 -c "from chess_self_coach.classifier import score_classifier; print(score_classifier(verbose=True))"
uv run python3 -c "from chess_self_coach.classifier import run_classification; run_classification()"
uv run pytest tests/test_classifier.py -v
```

If the classifier behavior changed materially, also run the broader targeted checks that touch the same path.

## What To Report

When presenting results, always include:

- baseline full-fit score
- candidate full-fit score
- honest holdout score
- complexity before / after
- main TP / FP / FN shifts
- whether the change was rule, ML, or hybrid
- whether the win looks robust or likely overfit

Use a short table when comparing multiple candidates.

## Avoid

- optimizing against `score_classifier()` alone
- calling old slash-command prose authoritative when the code disagrees
- mixing rule and ML wins into one patch before measuring them separately
- promoting a config just because the sweep ranked it first
- adding chess motifs with no general tactical meaning
- increasing complexity without a measurable holdout benefit
