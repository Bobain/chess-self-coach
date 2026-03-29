Find games that need labeling for the classification ground truth (!! and ! moves), present them interactively for the user to label, and update the test fixtures.

Argument: $ARGUMENTS is the minimum number of ! (great) moves to include a game. Default: 4. Games with ≥1 !! are always included regardless of this threshold.

## Step 1: Find candidates using the REAL JS classifier

Run a Python+Playwright script that:
- Loads `analysis_data.json` and the existing ground truth from `tests/e2e/classification_cases.py`
- Starts a Playwright browser, loads `http://localhost:8000` (the real PWA)
- For EACH game not already in the ground truth:
  - Calls `window._classifyMove(m, side, prevMove)` on every move (the REAL classifier)
  - Counts brilliant (!!) and great (!) moves
- Filters: games with ≥1 brilliant OR ≥N great (N from $ARGUMENTS, default 4)
- **Game ID matching**: `analysis_data.json` uses URLs like `https://www.chess.com/game/live/123456`, ground truth uses `opponent_123456`. Extract the numeric ID from the URL and match against existing `game_id` values to avoid duplicates.
- Sorts: games with !! first, then by date (oldest first)
- Prints summary: "Found X candidates (Y with !!, Z with ≥N !)"

If no candidates found, inform the user and stop.

## Step 2: Process each game

For each candidate game, from oldest to newest (!! games first):

1. Show game info: White vs Black, date, result, player color, number of moves
2. Show ONLY the moves classified as !! or ! in a table:
   ```
   Idx  Move#  Move      Category  cp before→after  PV (first 5 moves)
   ```
3. Ask the user: "Which indices are !! and which are ! ?" — the user will respond with something like "idx 36 is !!, idx 38 is !" or "aucun coup !! ni !" (= all other)
4. Any move not mentioned by the user is considered "other" (not !! or !)

## Step 3: Update fixtures

After the user labels a game:

1. Extract moves from `analysis_data.json` in the simplified format used by the ground truth:
   - `fen_before`, `move_san`, `move_uci`, `side`, `in_opening`
   - `eval_before`: only `score_cp, is_mate, mate_in, best_move_uci, pv_uci, pv_san`
   - `eval_after`: only `score_cp, is_mate, mate_in`
2. Build `game_id` as `opponent_numericId` (extract numeric ID from URL, opponent from headers)
3. Append to `tests/e2e/fixtures/classification_ground_truth.json`
4. Append entry to `tests/e2e/classification_cases.py` GAMES list with `brilliant_indices`, `great_indices`, and `notes`

## Step 4: Test and commit (after each game)

1. Run `uv run pytest tests/e2e/test_review.py::test_classification_macro_f1_regression -v`
2. If test passes: commit with message "Add {opponent} game to classification ground truth ({N} total)"
3. If test fails: report the error, do NOT commit

## Important rules

- NEVER use a Python proxy of the classifier. ALWAYS use `window._classifyMove` via Playwright.
- **BOTH SIDES**: classify and count !! and ! for BOTH players (not just the user). A brilliant move by the opponent counts too. The ground truth covers all moves in the game regardless of which side played them.
- Only show !! and ! moves to the user. ×, ?, ?!, ??, blunder, miss etc. are irrelevant for this labeling task.
- Any move not explicitly labeled by the user is "other".
- Process !! games before !-only games.
- Commit after each game, not in batch.
