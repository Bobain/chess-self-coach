Find games that need labeling for the classification ground truth (!! and ! moves), present them interactively for the user to label, and update the test fixtures.

Argument: $ARGUMENTS is the minimum number of ! (great) moves to include a game. Default: 4. Games with >=1 !! are always included regardless of this threshold.

## Step 1: Find candidates using the Python classifier

Run a Python script that:
- Loads `data/analysis_data.json`, `data/tactics_data.json`, and the existing ground truth from `tests/e2e/classification_cases.py`
- Uses the Python classifier (`classifier.py`) to classify every move of each game not already in the ground truth
- Counts brilliant (!!) and great (!) moves
- Filters: games with >=1 brilliant OR >=N great (N from $ARGUMENTS, default 4)
- **Game ID matching**: `data/analysis_data.json` uses URLs like `https://www.chess.com/game/live/123456`, ground truth uses `opponent_123456`. Extract the numeric ID from the URL and match against existing `game_id` values to avoid duplicates.
- Sorts: games with !! first, then by date (oldest first)
- Prints summary: "Found X candidates (Y with !!, Z with >=N !)"

If no candidates found, inform the user and stop.

## Step 2: Process each game

For each candidate game, from oldest to newest (!! games first):

1. Show game info: White vs Black, date, result, player color, number of moves
2. Give the user the **game URL** (the full URL from analysis_data.json, e.g. https://www.chess.com/game/live/123456) so they can review the game themselves
3. Wait for the user's response. The user will review the game on chess.com and reply with the list of !! and ! moves using move numbers, e.g. "9.b Bh2+ is !, 15.w Nxe6 is !!" or "aucun coup !! ni !" (= all other)
4. **Map the user's move numbers to indices**: use the moves array from analysis_data.json to find the index for each move number. Move 1.w = index 0, move 1.b = index 1, move 2.w = index 2, etc. General formula: index = (move_number - 1) * 2 + (1 if black else 0). Verify the SAN matches what the user said.
5. Any move not mentioned by the user is considered "other" (not !! or !)

## Step 3: Update fixtures

After the user labels a game:

1. Extract moves from `data/analysis_data.json` in the simplified format used by the ground truth:
   - `fen_before`, `move_san`, `move_uci`, `side`, `in_opening`
   - `eval_before`: only `score_cp, is_mate, mate_in, best_move_uci, pv_uci, pv_san`
   - `eval_after`: only `score_cp, is_mate, mate_in`
2. Build `game_id` as `opponent_numericId` (extract numeric ID from URL, opponent from headers)
3. Append to `tests/e2e/fixtures/classification_ground_truth.json`
4. Append entry to `tests/e2e/classification_cases.py` GAMES list with `brilliant_indices`, `great_indices`, and `notes`

## Step 4: Test and commit (after each game)

1. Run `uv run pytest tests/test_classifier.py::test_classifier_score_regression -v`
2. If test passes: commit with message "Add {opponent} game to classification ground truth ({N} total)"
3. If test fails: report the error, do NOT commit

## Important rules

- Use the Python classifier (`from chess_self_coach.classifier import classify_move`) — NOT JS.
- **BOTH SIDES**: classify and count !! and ! for BOTH players (not just the user). A brilliant move by the opponent counts too. The ground truth covers all moves in the game regardless of which side played them.
- Only show !! and ! moves to the user. Other categories are irrelevant for this labeling task.
- Any move not explicitly labeled by the user is "other".
- Process !! games before !-only games.
- Commit after each game, not in batch.
