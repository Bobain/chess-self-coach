Review training data for correctness, context quality, and pedagogical value.

Read `training_data.json` and analyze each position for:

1. **Correctness**: Verify that `player_move` and `best_move` are valid SAN moves in the given FEN. Check that the explanation is factually accurate.

2. **Sufficient context**: The `context` field must help a ~1000 Elo player understand the situation BEFORE they try to find the better move. Good context includes:
   - Game phase (opening/middlegame/endgame)
   - Who has the advantage and by how much
   - What went wrong (material loss, allowed checkmate, drew from winning position, etc.)
   - Example good: "Middlegame, you were slightly worse. Your move gave your opponent a decisive advantage."
   - Example bad: "Your move was slightly inaccurate (0.5 pawns)." (no game phase, no context)

3. **Explanation quality**: After the player answers, the explanation should clearly state:
   - What was wrong with the played move
   - Why the best move is better
   - Any tactical pattern (missed capture, missed check, hanging piece, stalemate)

4. **Anomalies**: Flag any "unknown" sources, empty fields, suspicious pawn counts (>50), or missing PV lines.

For each issue found:
- If it's a **systemic pattern** (same type of bad context across many positions): propose a fix to `generate_context()` or `generate_explanation()` in `src/chess_self_coach/trainer.py`, apply it, then run `uv run chess-self-coach train --refresh-explanations` to update all positions.
- If it's a **data bug** (wrong source, missing field): fix the root cause in the code that generates the data.
- After any code changes, run `uv run pytest tests/test_training_texts.py -v` to verify.

Sample 10-20 positions across different categories (blunders, mistakes, inaccuracies) and different score ranges. Don't check all 150+ positions — focus on finding patterns.
