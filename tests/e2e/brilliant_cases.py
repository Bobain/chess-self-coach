"""Move classification ground truth from real games.

For each game, we define which moves are brilliant (!!) or great (!).
All other moves are implicitly 'other'. Tests classify every move and
compute per-class precision/recall/F1 and macro F1.

These games were selected because the current classifier detects at
least one potential brilliant move in each. The user validates/corrects
each label manually.

To add a new game:
1. Extract its moves to fixtures/brilliant_ground_truth.json
2. Add an entry to GAMES with the brilliant/great move indices
3. Run tests — the classification log will update automatically
"""

from __future__ import annotations

GAMES: list[dict] = [
    {
        "game_id": "DDDestryer_166363391518",
        "brilliant_indices": [64],  # 33.w Rxe3 — tactical trap
        "great_indices": [],
        "notes": {
            64: "Rxe3 — tactical trap, wins knight via Qxg7# mate threat",
        },
    },
    {
        "game_id": "promisedumbor_166265019284",
        "brilliant_indices": [],  # 34.b Na4 — TO VALIDATE
        "great_indices": [],
        "notes": {
            67: "Na4 — candidate !! (to validate)",
        },
    },
    {
        "game_id": "benoit_delhaye_942151399",
        "brilliant_indices": [],  # 19.b Rxf3 — TO VALIDATE
        "great_indices": [],
        "notes": {
            37: "Rxf3 — candidate !! (to validate)",
        },
    },
    {
        "game_id": "sergilomidze_131014798331",
        "brilliant_indices": [],  # 38.b Rxd5 — TO VALIDATE
        "great_indices": [],
        "notes": {
            75: "Rxd5 — candidate !! (to validate)",
        },
    },
    {
        "game_id": "TangguhPamungkas_130171218361",
        "brilliant_indices": [],  # 8.b Bxe5 — TO VALIDATE
        "great_indices": [],
        "notes": {
            15: "Bxe5 — candidate !! (to validate)",
        },
    },
    {
        "game_id": "FernandoPegoraro1179_130019922303",
        "brilliant_indices": [],  # 15.w Bxh7 — TO VALIDATE
        "great_indices": [],
        "notes": {
            28: "Bxh7 — candidate !! (to validate)",
        },
    },
    {
        "game_id": "cdorseth_129923989297",
        "brilliant_indices": [],  # 14.w Rxc3 — TO VALIDATE
        "great_indices": [],
        "notes": {
            26: "Rxc3 — candidate !! (to validate)",
        },
    },
    {
        "game_id": "aghfghfc_129832849465",
        "brilliant_indices": [],  # 21.b Nxe3 — TO VALIDATE
        "great_indices": [],
        "notes": {
            41: "Nxe3 — candidate !! (to validate)",
        },
    },
    {
        "game_id": "jeetb_129814196657",
        "brilliant_indices": [],  # 24.w Qxd5 — TO VALIDATE
        "great_indices": [],
        "notes": {
            46: "Qxd5 — candidate !! (to validate)",
        },
    },
    {
        "game_id": "elmariopoh_129124961669",
        "brilliant_indices": [],  # 12.b Qxg1 — TO VALIDATE
        "great_indices": [],
        "notes": {
            23: "Qxg1 — candidate !! (to validate)",
        },
    },
    {
        "game_id": "Rafffryn_121736582686",
        "brilliant_indices": [],  # 30.b Rxa4 — TO VALIDATE
        "great_indices": [],
        "notes": {
            59: "Rxa4 — candidate !! (to validate)",
        },
    },
]
