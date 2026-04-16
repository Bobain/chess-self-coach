# Repo Reality Check

Read this before optimizing the classifier.

## Current production stack

- `src/chess_self_coach/classifier.py` is **hybrid**:
  - brilliant and miss detection are rule-based
  - great detection uses the serialized XGBoost model when available
- `data/models/great_xgb.json` and `data/models/great_xgb_meta.json` are already part of production behavior
- `score_classifier()` is the canonical production metric

## Ground truth and labels

- Labels live in:
  - `tests/e2e/classification_cases.py`
  - `tests/e2e/fixtures/classification_ground_truth.json`
- Scoring is game-aggregated TP / FP / FN over only:
  - `brilliant`
  - `great`
- `other` is excluded from macro F1

## Important drift vs older docs

- `.claude/commands/optimize-classifier.md` still describes an older, more rule-centric workflow
- `scripts/sweep_classifier.py` no longer matches the old four-phase description exactly
- docs still describe a simpler great-move rule path, while production now uses XGBoost for `great`

When docs disagree with code, trust the code.

## Honest validation vs current helpers

- `scripts/sweep_classifier.py` is useful for candidate generation
- its `logo_validate()` excludes one game from scoring the remaining dataset
- that is **not** the same as training on `N-1` games and predicting the held-out game
- treat it as a stability / divergence signal, not as final evidence

- `scripts/train_classifier_ml.py` performs a true leave-one-game-out loop for the `great` model:
  - train on `N-1` games
  - predict the held-out game
  - aggregate out-of-fold probabilities
  - sweep threshold on those out-of-fold predictions

## Practical implications

- Rule tuning and ML tuning should be evaluated separately first
- A good full-fit score with a weak holdout score is not a win
- If a rule change only helps after seeing the held-out labels, it is leakage
- If a motif only rescues one labeled game and has no general chess meaning, reject it

## Commands worth keeping handy

```bash
uv run python3 -c "from chess_self_coach.classifier import score_classifier; print(score_classifier(verbose=True))"
uv run python3 scripts/collect_classifier_data.py
uv run python3 scripts/sweep_classifier.py
uv run python3 scripts/train_classifier_ml.py
uv run python3 -c "from chess_self_coach.classifier import run_classification; run_classification()"
uv run pytest tests/test_classifier.py -v
```
