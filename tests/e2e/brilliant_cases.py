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
        "brilliant_indices": [],
        "great_indices": [67],  # 34.b Na4 — great, not brilliant
        "notes": {
            67: "Na4 — great move, knight exchange in winning position",
        },
    },
    {
        "game_id": "benoit_delhaye_942151399",
        "brilliant_indices": [37],  # 19.b Rxf3
        "great_indices": [49],  # 25.b Bd8
        "notes": {
            37: "Rxf3 — brilliant sacrifice",
            49: "Bd8 — great move",
        },
    },
    {
        "game_id": "sergilomidze_131014798331",
        "brilliant_indices": [],
        "great_indices": [52, 59, 64, 75, 92, 95, 102, 111],
        "notes": {
            52: "27.w Bxa6 — great",
            59: "30.b Rxc2 — great",
            64: "33.w Kxb6 — great",
            75: "38.b Rxd5 — great, not brilliant",
            92: "47.w Rb1 — great",
            95: "48.b Rxa8 — great",
            102: "52.w Rxf1 — great",
            111: "56.b Kg2 — great",
        },
    },
    {
        "game_id": "TangguhPamungkas_130171218361",
        "brilliant_indices": [],
        "great_indices": [14, 36],  # 8.w e5, 19.w Re8#
        "notes": {
            14: "8.w e5 — great",
            15: "8.b Bxe5 — not brilliant, other",
            36: "19.w Re8# — great",
        },
    },
    {
        "game_id": "FernandoPegoraro1179_130019922303",
        "brilliant_indices": [],
        "great_indices": [],
        "notes": {
            28: "Bxh7 — not brilliant, other",
        },
    },
    {
        "game_id": "cdorseth_129923989297",
        "brilliant_indices": [],
        "great_indices": [29, 32, 39],  # 15.b Rxc3, 17.w Qxb7, 20.b Nxb7
        "notes": {
            26: "14.w Rxc3 — not brilliant, other",
            29: "15.b Rxc3 — great",
            32: "17.w Qxb7 — great",
            39: "20.b Nxb7 — great",
        },
    },
    {
        "game_id": "aghfghfc_129832849465",
        "brilliant_indices": [],
        "great_indices": [54],  # 28.w Rf8
        "notes": {
            41: "21.b Nxe3 — not brilliant, other",
            54: "28.w Rf8 — great",
        },
    },
    {
        "game_id": "jeetb_129814196657",
        "brilliant_indices": [],
        "great_indices": [24, 42, 45, 56, 64],  # 13.w dxc5, 22.w Qxc6, 23.b Rf5, 29.w Rd8, 33.w Na7
        "notes": {
            24: "13.w dxc5 — great",
            42: "22.w Qxc6 — great",
            45: "23.b Rf5 — great",
            46: "24.w Qxd5 — not brilliant, other",
            56: "29.w Rd8 — great",
            64: "33.w Na7 — great",
        },
    },
    {
        "game_id": "elmariopoh_129124961669",
        "brilliant_indices": [],
        "great_indices": [19, 40, 48, 51],  # 10.b Qd4, 21.w Nxh8, 25.w Bc6, 26.b Kxd7
        "notes": {
            19: "10.b Qd4 — great",
            23: "12.b Qxg1 — not brilliant, other",
            40: "21.w Nxh8 — great",
            48: "25.w Bc6 — great",
            51: "26.b Kxd7 — great",
        },
    },
    {
        "game_id": "Rafffryn_121736582686",
        "brilliant_indices": [],
        "great_indices": [57, 117],  # 29.b b5, 59.b Kd3
        "notes": {
            57: "29.b b5 — great",
            59: "30.b Rxa4 — not brilliant, other",
            117: "59.b Kd3 — great",
        },
    },
]
