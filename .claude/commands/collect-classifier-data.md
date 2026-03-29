Collect all !! and ! classified moves (TP, FP, FN) with 3-move context using the real JS classifier via Playwright. Outputs to `/tmp/classifier_data.json`.

## Step 1: Run the collection script

```bash
uv run python3 scripts/collect_classifier_data.py
```

This script uses Playwright to load `http://localhost:8000` and calls `window._classifyMove` on every move in every ground truth game. It compares predictions against labels and saves all TP/FP/FN with 3-move context.

**Requires**: the dev server running on localhost:8000 (`uv run chess-self-coach serve`).

## Step 2: Get the BEFORE baseline score

```bash
uv run pytest tests/e2e/test_review.py::test_classification_macro_f1_regression -v -s -n0
```

Print the BEFORE baseline: macro F1, complexity breakdown, regularized score.
