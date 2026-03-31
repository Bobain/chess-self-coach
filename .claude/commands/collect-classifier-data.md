Collect all !! and ! classified moves (TP, FP, FN) with features + tactical motifs. Pure Python (no Playwright). Outputs to `/tmp/classifier_data.json`.

## Step 1: Run the collection script

```bash
uv run python3 scripts/collect_classifier_data.py
```

This script uses the Python classifier (`classifier.py`) + pre-computed tactics (`data/tactics_data.json`) to classify all ground truth moves and compare against labels. No server needed.

## Step 2: Regenerate classifications (after any classifier change)

```bash
uv run python3 -c "from chess_self_coach.classifier import run_classification; run_classification()"
```

Regenerates `data/classifications_data.json` from `data/analysis_data.json` + `data/tactics_data.json`. Takes ~1s for 361 games.

## Step 3: Get the BEFORE baseline score

```bash
uv run python3 -c "from chess_self_coach.classifier import score_classifier; score_classifier()"
```

Prints: macro F1, complexity breakdown, regularized score. Can be called standalone (no pytest needed).
