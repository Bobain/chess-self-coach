"""Brilliant move classification ground truth from real games.

For each game, we define which moves are truly brilliant. All other
moves are implicitly true negatives. Tests classify every move and
compute TP/FP/TN/FN + F1 score.

To add a new game:
1. Extract its moves to fixtures/brilliant_ground_truth.json
2. Add an entry to GAMES with the brilliant move indices
3. Run tests — the F1 log will update automatically
"""

from __future__ import annotations

GAMES: list[dict] = [
    {
        "game_id": "DDDestryer_166363391518",
        "brilliant_indices": [64],  # move 33w Rxe3 (tactical trap)
        "notes": {
            2: "c4 Queen's Gambit — routine opening gambit, not brilliant",
            47: "Bxe6 — favorable recapture chain, not a sacrifice",
            64: "Rxe3 — tactical trap, wins knight via Qxg7# mate threat",
        },
    },
    {
        "game_id": "adit_yehh_166462966860",
        "brilliant_indices": [],  # no brilliant moves in this game
        "notes": {},
    },
    {
        "game_id": "PerritoLoco12_166446936234",
        "brilliant_indices": [],  # no brilliant moves in this game
        "notes": {
            2: "c4 Queen's Gambit — same FP pattern as DDDestryer",
        },
    },
    {
        "game_id": "mahmutyardim_166408702408",
        "brilliant_indices": [],  # no brilliant moves in this game
        "notes": {},
    },
    {
        "game_id": "FarshadDabest_166398619608",
        "brilliant_indices": [],  # no brilliant moves in this game
        "notes": {},
    },
    {
        "game_id": "Jhonalexismina_166305403436",
        "brilliant_indices": [],  # no brilliant moves in this game
        "notes": {},
    },
    {
        "game_id": "StarLight-S2_166265771230",
        "brilliant_indices": [],  # no brilliant moves in this game
        "notes": {
            9: "c5 — standard positional pawn push vs London/Réti, not a sacrifice",
        },
    },
    {
        "game_id": "Xpolash_166334588890",
        "brilliant_indices": [],  # no brilliant moves in this game
        "notes": {
            52: "Rxe6 — trapped rook, 'sacrifice' only minimizes losses (not a tactical advantage)",
        },
    },
    {
        "game_id": "Ansaar98_166442353784",
        "brilliant_indices": [],  # no brilliant moves in this game
        "notes": {},
    },
]
