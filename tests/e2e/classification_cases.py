"""Move classification ground truth from real games.

For each game, we define which moves are brilliant (!!) or great (!).
All other moves are implicitly 'other'. Tests classify every move and
compute per-class precision/recall/F1 and macro F1.

To add a new game:
1. Extract its moves to fixtures/classification_ground_truth.json
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
    {
        "game_id": "nugomira_125299724951",
        "brilliant_indices": [],
        "great_indices": [27, 36],  # 14.b dxe4, 19.w Bxe6+
        "notes": {
            27: "14.b dxe4 — great, captures after opponent error c3",
            36: "19.w Bxe6+ — great, not brilliant (already winning +313cp)",
        },
    },
    {
        "game_id": "qkrtjdbf_125404778455",
        "brilliant_indices": [36],  # 19.w Nxe6
        "great_indices": [38],  # 20.w Bxf5
        "notes": {
            36: "19.w Nxe6 — brilliant sacrifice",
            38: "20.w Bxf5 — great, follows up the sacrifice",
        },
    },
    {
        "game_id": "Galafr_121671787502",
        "brilliant_indices": [],
        "great_indices": [],
        "notes": {
            29: "15.b Rxe5 — not brilliant, other",
        },
    },
    {
        "game_id": "tusharpanda_120991163310",
        "brilliant_indices": [],
        "great_indices": [35, 49, 51, 69, 71, 83],  # 18.b fxe3, 25.b Nxe3, 26.b Qb6, 35.b Rxc4, 36.b Qd4, 42.b Bd6
        "notes": {
            35: "18.b fxe3 — great",
            47: "24.b Kg7 — not great, other",
            49: "25.b Nxe3 — great",
            51: "26.b Qb6 — great (not detected by classifier)",
            69: "35.b Rxc4 — great",
            71: "36.b Qd4 — great",
            83: "42.b Bd6 — great (not detected by classifier)",
            97: "49.b Kc4 — not great, other",
        },
    },
    {
        "game_id": "priyadarshi_123_130248687713",
        "brilliant_indices": [],
        "great_indices": [24, 27, 35, 37, 40, 46, 51, 55, 58, 72],
        "notes": {
            24: "13.w Nxf6+ — great",
            27: "14.b Qxe3+ — great",
            35: "18.b Qxh3+ — great",
            37: "19.b Rg8+ — great",
            40: "21.w Ke1 — great",
            46: "24.w Qxf7+ — great",
            51: "26.b Qxg6 — great",
            55: "28.b Nxa1 — great",
            58: "30.w Bc4+ — great",
            61: "31.b Rf2 — not great, other",
            72: "37.w Nd3 — great",
        },
    },
    {
        "game_id": "jjyong_928_166354857372",
        "brilliant_indices": [],
        "great_indices": [51, 56, 61, 64],  # 26.b Rd1+, 29.w Ke2, 31.b Rc2+, 33.w Kg2
        "notes": {
            27: "14.b c5 — not great, other",
            51: "26.b Rd1+ — great",
            56: "29.w Ke2 — great",
            61: "31.b Rc2+ — great",
            64: "33.w Kg2 — great",
        },
    },
    {
        "game_id": "alfaromeo00_120864711832",
        "brilliant_indices": [],
        "great_indices": [30],  # 16.w Bxh6
        "notes": {
            21: "11.b Bb7 — not great, other",
            30: "16.w Bxh6 — great",
            44: "23.w Ng3 — not great, other",
        },
    },
    {
        "game_id": "James11e_120858977974",
        "brilliant_indices": [],
        "great_indices": [38],  # 20.w Nxf5
        "notes": {
            20: "11.w cxd5 — not great, other",
            24: "13.w Bc2 — not great, other",
            38: "20.w Nxf5 — great",
        },
    },
    {
        "game_id": "farees23556_125351974269",
        "brilliant_indices": [],
        "great_indices": [9],  # 5.b Nc6
        "notes": {
            9: "5.b Nc6 — great (not detected by classifier)",
            24: "13.w c4 — not great, other",
            29: "15.b Nxc3 — not great, other",
            31: "16.b Nc2+ — not great, other",
        },
    },
    {
        "game_id": "MCH13_125306368759",
        "brilliant_indices": [],
        "great_indices": [32],  # 17.w a5
        "notes": {
            27: "14.b Kxa7 — not great, other",
            32: "17.w a5 — great",
            54: "28.w a7+ — not great, other",
            57: "29.b Nxb5 — not great, other",
        },
    },
    {
        "game_id": "edulof_120905678788",
        "brilliant_indices": [],
        "great_indices": [25, 56],  # 13.b Nxg4, 29.w Qxh6+
        "notes": {
            25: "13.b Nxg4 — great (not detected by classifier)",
            35: "18.b Nh5 — not great, other",
            53: "27.b Rxd2 — not great, other",
            56: "29.w Qxh6+ — great",
        },
    },
    {
        "game_id": "lukestephenkeen1_121039204652",
        "brilliant_indices": [],
        "great_indices": [49, 51, 96],  # 25.b Kg7, 26.b Rfd8, 49.w Kxe2
        "notes": {
            25: "13.b Nc5 — not great, other",
            38: "20.w Qxh6 — not great, other",
            49: "25.b Kg7 — great",
            51: "26.b Rfd8 — great",
            96: "49.w Kxe2 — great (not detected by classifier)",
        },
    },
    {
        "game_id": "miki19751975_121467758236",
        "brilliant_indices": [],
        "great_indices": [35, 39, 42, 47],  # 18.b Bc5, 20.b Bxf2+, 22.w Nxb2, 24.b Bxa1
        "notes": {
            35: "18.b Bc5 — great",
            39: "20.b Bxf2+ — great",
            42: "22.w Nxb2 — great (not detected by classifier)",
            47: "24.b Bxa1 — great",
        },
    },
    {
        "game_id": "sujalpotghan_121654941186",
        "brilliant_indices": [],
        "great_indices": [15, 16, 21, 28, 38, 69],  # 8.b dxe4, 9.w Qxd8, 11.b Nxf2, 15.w Be3, 20.w Rxd8, 35.b Rxb2
        "notes": {
            15: "8.b dxe4 — great",
            16: "9.w Qxd8 — great (not detected by classifier)",
            21: "11.b Nxf2 — great",
            26: "14.w Nc3 — not great, other",
            28: "15.w Be3 — great (not detected by classifier)",
            38: "20.w Rxd8 — great (not detected by classifier)",
            69: "35.b Rxb2 — great",
        },
    },
    {
        "game_id": "stefanmoesch_121654332362",
        "brilliant_indices": [],
        "great_indices": [34, 48, 59, 63, 66, 69, 75],  # 18.w Rxd5, 25.w Qxc8+, 30.b Qxg7, 32.b Kh4, 34.w Rxb5, 35.b Qa2+, 38.b Qf2#
        "notes": {
            34: "18.w Rxd5 — great",
            48: "25.w Qxc8+ — great (not detected by classifier)",
            59: "30.b Qxg7 — great (not detected by classifier)",
            63: "32.b Kh4 — great",
            66: "34.w Rxb5 — great",
            69: "35.b Qa2+ — great (not detected by classifier)",
            75: "38.b Qf2# — great (not detected by classifier)",
        },
    },
    {
        "game_id": "YUSFAZAD12_121737277726",
        "brilliant_indices": [],
        "great_indices": [56, 61, 62, 81],  # 29.w Qxf7+, 31.b Qa1+, 32.w Rf1, 41.b Rxd2
        "notes": {
            20: "11.w Bd3 — not great, other",
            56: "29.w Qxf7+ — great",
            61: "31.b Qa1+ — great",
            62: "32.w Rf1 — great (not detected by classifier)",
            81: "41.b Rxd2 — great",
        },
    },
    {
        "game_id": "danial_zinou_121735581108",
        "brilliant_indices": [],
        "great_indices": [8, 10, 12, 18, 39, 44, 54],  # 5.w Bd2, 6.w Nc3, 7.w Rb1, 10.w Nxc7+, 20.b Qh5, 23.w c4, 28.w Rxd7+
        "notes": {
            8: "5.w Bd2 — great (not detected by classifier)",
            10: "6.w Nc3 — great (not detected by classifier)",
            12: "7.w Rb1 — great (not detected by classifier)",
            18: "10.w Nxc7+ — great (not detected by classifier)",
            39: "20.b Qh5 — great",
            41: "21.b Qxb5 — not great, other",
            44: "23.w c4 — great",
            54: "28.w Rxd7+ — great (not detected by classifier)",
        },
    },
    {
        "game_id": "Republikaner95_129548018835",
        "brilliant_indices": [],
        "great_indices": [12, 53, 76, 79, 92],  # 7.w Nxb4, 27.b Rxb5, 39.w Kxe4, 40.b Kf5, 47.w Kh6
        "notes": {
            12: "7.w Nxb4 — great (not detected by classifier)",
            38: "20.w Nxd5 — not great, other",
            49: "25.b Rb4 — not great, other",
            53: "27.b Rxb5 — great (not detected by classifier)",
            71: "36.b h5 — not great, other",
            76: "39.w Kxe4 — great (not detected by classifier)",
            79: "40.b Kf5 — great",
            92: "47.w Kh6 — great (not detected by classifier)",
        },
    },
    {
        "game_id": "April_Incandenza_129308541535",
        "brilliant_indices": [],
        "great_indices": [28, 33, 45, 51],  # 15.w Bxd5, 17.b Qxd2, 23.b Nb4, 26.b axb3
        "notes": {
            28: "15.w Bxd5 — great",
            33: "17.b Qxd2 — great (not detected by classifier)",
            45: "23.b Nb4 — great (not detected by classifier)",
            48: "25.w Rc1 — not great, other",
            51: "26.b axb3 — great (not detected by classifier)",
            57: "29.b c4 — not great, other",
            60: "31.w Ke2 — not great, other",
        },
    },
    {
        "game_id": "badlanshunty_129817210961",
        "brilliant_indices": [44],  # 23.w Ng5
        "great_indices": [15, 34, 37],  # 8.b Nbd7, 18.w Kb2, 19.b Qc3+
        "notes": {
            15: "8.b Nbd7 — great",
            29: "15.b Bxh6 — not great, other",
            34: "18.w Kb2 — great",
            37: "19.b Qc3+ — great",
            44: "23.w Ng5 — brilliant (not detected by classifier)",
        },
    },
]
