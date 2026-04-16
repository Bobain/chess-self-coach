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
    {
        "game_id": "NTDuong0106_129903530743",
        "brilliant_indices": [],
        "great_indices": [67, 75],  # 34.b Qb2, 38.b Qxe1+
        "notes": {
            26: "14.w axb5 — not great, other",
            33: "17.b Nd7 — not great, other",
            67: "34.b Qb2 — great",
            75: "38.b Qxe1+ — great (not detected by classifier)",
        },
    },
    {
        "game_id": "melb123456789_130673436141",
        "brilliant_indices": [],
        "great_indices": [34, 53, 60],  # 18.w Ne6+, 27.b Qxf2+, 31.w Qe7+
        "notes": {
            34: "18.w Ne6+ — great (not detected by classifier)",
            53: "27.b Qxf2+ — great",
            58: "30.w Qe6+ — not great, other",
            60: "31.w Qe7+ — great",
        },
    },
    {
        "game_id": "najshajs_165191804886",
        "brilliant_indices": [],
        "great_indices": [30, 41, 70],  # 16.w g3, 21.b Nxc4, 36.w Bg6+
        "notes": {
            30: "16.w g3 — great (not detected by classifier)",
            34: "18.w Bxc5 — not great, other",
            41: "21.b Nxc4 — great (not detected by classifier)",
            45: "23.b Qxd4 — not great, other",
            64: "33.w f4 — not great, other",
            68: "35.w f5 — not great, other",
            70: "36.w Bg6+ — great (not detected by classifier)",
        },
    },
    {
        "game_id": "piotr_123321_165233427906",
        "brilliant_indices": [],
        "great_indices": [14, 25, 29, 33, 52, 63],  # 8.w dxe5, 13.b Nxd5, 15.b cxd6, 17.b Rxd6, 27.w Rxb8+, 32.b Nd5+
        "notes": {
            14: "8.w dxe5 — great (not detected by classifier)",
            25: "13.b Nxd5 — great (not detected by classifier)",
            29: "15.b cxd6 — great (not detected by classifier)",
            33: "17.b Rxd6 — great",
            52: "27.w Rxb8+ — great (not detected by classifier)",
            58: "30.w Kd2 — not great, other",
            63: "32.b Nd5+ — great",
            77: "39.b f4 — not great, other",
        },
    },
    {
        "game_id": "LuisMarciel_165644144456",
        "brilliant_indices": [],
        "great_indices": [40, 53, 83, 94, 100, 102],  # 21.w Ng4, 27.b Rxg4, 42.b Rxc3, 48.w Rb5, 51.w Rxa5, 52.w Rb5
        "notes": {
            40: "21.w Ng4 — great",
            53: "27.b Rxg4 — great (not detected by classifier)",
            58: "30.w Kf2 — not great, other",
            83: "42.b Rxc3 — great",
            94: "48.w Rb5 — great",
            100: "51.w Rxa5 — great (not detected by classifier)",
            102: "52.w Rb5 — great (not detected by classifier)",
        },
    },
    {
        "game_id": "KlausFischer_165660451248",
        "brilliant_indices": [],
        "great_indices": [34, 54],  # 18.w exf5, 28.w Qf4
        "notes": {
            26: "14.w Bxf6 — not great, other",
            31: "16.b Rg8 — not great, other",
            34: "18.w exf5 — great (not detected by classifier)",
            54: "28.w Qf4 — great",
        },
    },
    {
        "game_id": "tg010176_165858096522",
        "brilliant_indices": [],
        "great_indices": [17, 33],  # 9.b Nxf3+, 17.b Bf4
        "notes": {
            17: "9.b Nxf3+ — great",
            31: "16.b gxf6 — not great, other",
            33: "17.b Bf4 — great (not detected by classifier)",
            37: "19.b Kh8 — not great, other",
        },
    },
    {
        "game_id": "Tasoulinga_165939820182",
        "brilliant_indices": [],
        "great_indices": [18, 22, 53, 73, 74, 75, 81, 103],  # 10.w e4, 12.w Qa4+, 27.b exd5, 37.b Ra6, 38.w Rc1, 38.b Bc4, 41.b Bxd7, 52.b Rg1
        "notes": {
            15: "8.b e6 — not great, other",
            18: "10.w e4 — great (not detected by classifier)",
            22: "12.w Qa4+ — great (not detected by classifier)",
            42: "22.w Rb1 — not great, other",
            53: "27.b exd5 — great (not detected by classifier)",
            73: "37.b Ra6 — great (not detected by classifier)",
            74: "38.w Rc1 — great (not detected by classifier)",
            75: "38.b Bc4 — great (not detected by classifier)",
            77: "39.b Rxc6 — not great, other",
            81: "41.b Bxd7 — great (not detected by classifier)",
            103: "52.b Rg1 — great",
        },
    },
    {
        "game_id": "Tarek25b_166027839420",
        "brilliant_indices": [],
        "great_indices": [25, 86, 90, 103, 122],  # 13.b Bg4, 44.w Kg2, 46.w Kg3, 52.b e4, 62.w Rxe1
        "notes": {
            23: "12.b e5 — not great, other",
            25: "13.b Bg4 — great (not detected by classifier)",
            86: "44.w Kg2 — great (not detected by classifier)",
            90: "46.w Kg3 — great (not detected by classifier)",
            97: "49.b Rf4 — not great, other",
            101: "51.b Kd4 — not great, other",
            103: "52.b e4 — great (not detected by classifier)",
            108: "55.w h5 — not great, other",
            122: "62.w Rxe1 — great (not detected by classifier)",
        },
    },
    {
        "game_id": "abhi1146_120857473938",
        "brilliant_indices": [],
        "great_indices": [9, 26, 71, 82, 88],  # 5.b b5, 14.w Bxg7, 36.b Ke7, 42.w Nxf4+, 45.w Qb5+
        "notes": {
            9: "b5 — great",
            26: "Bxg7 — great",
            71: "Ke7 — great",
            82: "Nxf4+ — great",
            88: "Qb5+ — great",
        },
    },
    {
        "game_id": "surangart_125132968589",
        "brilliant_indices": [],
        "great_indices": [17, 31],  # 9.b Bh2+, 16.b Qh4
        "notes": {
            17: "Bh2+ — great, deflection sacrifice",
            31: "Qh4 — great",
        },
    },
    {
        "game_id": "primocorti_125144956051",
        "brilliant_indices": [],
        "great_indices": [42, 44, 47],  # 22.w Kh2, 23.w Qg6+, 24.b Rf6
        "notes": {
            42: "Kh2 — great",
            44: "Qg6+ — great",
            47: "Rf6 — great",
        },
    },
    {
        "game_id": "D_03_125140734975",
        "brilliant_indices": [],
        "great_indices": [40, 61],  # 21.w Rd1, 31.b Nf4+
        "notes": {
            40: "Rd1 — great",
            61: "Nf4+ — great",
        },
    },
    {
        "game_id": "eban0406_121031441578",
        "brilliant_indices": [],
        "great_indices": [13, 20],  # 7.b bxc4, 11.w Qf3
        "notes": {
            13: "bxc4 — great",
            20: "Qf3 — great",
        },
    },
    {
        "game_id": "ibra_matador_121721706228",
        "brilliant_indices": [],
        "great_indices": [14],  # 8.w Bxe7
        "notes": {
            14: "Bxe7 — great",
        },
    },
    {
        "game_id": "michifuramirez_121720638400",
        "brilliant_indices": [],
        "great_indices": [36, 46],  # 19.w Nxc5, 24.w Nc5
        "notes": {
            36: "Nxc5 — great",
            46: "Nc5 — great",
        },
    },
    {
        "game_id": "T-j7d_129471808169",
        "brilliant_indices": [],
        "great_indices": [10, 24],  # 6.w Bxc4, 13.w Nc7
        "notes": {
            10: "Bxc4 — great",
            24: "Nc7 — great",
        },
    },
    {
        "game_id": "BogdanM55_165680289350",
        "brilliant_indices": [34],  # 18.w Nxf5
        "great_indices": [30, 36],  # 16.w Nd6, 19.w Be4
        "notes": {
            30: "Nd6 — great",
            34: "Nxf5 — brilliant",
            36: "Be4 — great",
        },
    },
    {
        "game_id": "JARVIS42AI_166054148592",
        "brilliant_indices": [],
        "great_indices": [47, 59, 72, 75, 81, 83, 85, 128, 131],
        "notes": {
            47: "Nf4+ — great",
            59: "Kf6 — great",
            72: "fxg4+ — great",
            75: "Kg6 — great",
            81: "Kh4 — great",
            83: "Kh3 — great",
            85: "Kg2 — great",
            128: "Qa3+ — great",
            131: "Kd6 — great",
        },
    },
    {
        "game_id": "Silverstormer_166049060862",
        "brilliant_indices": [52],  # 27.w Rxd5
        "great_indices": [],
        "notes": {
            52: "Rxd5 — brilliant",
        },
    },
    {
        "game_id": "ekostrenkov_166493950346",
        "brilliant_indices": [46],  # 24.w Nd6
        "great_indices": [21, 29, 36, 39, 42],  # 11.b bxc5, 15.b Nxe5, 19.w Nb5, 20.b Bxe5, 22.w fxe5
        "notes": {
            21: "bxc5 — great",
            29: "Nxe5 — great",
            36: "Nb5 — great",
            39: "Bxe5 — great",
            42: "fxe5 — great",
            46: "Nd6 — brilliant",
        },
    },
    {
        "game_id": "Has101010_125083720203",
        "brilliant_indices": [],
        "great_indices": [],
        "notes": {},
    },
    {
        "game_id": "shivauttangi_125080133625",
        "brilliant_indices": [],
        "great_indices": [19],  # 10.b Bg4
        "notes": {
            19: "Bg4 — great",
        },
    },
    {
        "game_id": "ishu_2008_125069377731",
        "brilliant_indices": [],
        "great_indices": [47, 51, 54, 59],  # 24.b Bf6, 26.b Bxb2, 28.w g3, 30.b f5
        "notes": {
            47: "Bf6 — great",
            51: "Bxb2 — great",
            54: "g3 — great",
            59: "f5 — great",
        },
    },
    {
        "game_id": "Andre_Scobling_120850950366",
        "brilliant_indices": [],
        "great_indices": [31],  # 16.b Bh5
        "notes": {
            31: "Bh5 — great",
        },
    },
    {
        "game_id": "robbbbinn_120846767896",
        "brilliant_indices": [],
        "great_indices": [16, 24],  # 9.w Nbd2, 13.w a3
        "notes": {
            16: "Nbd2 — great",
            24: "a3 — great",
        },
    },
    {
        "game_id": "uncleben2047_125149797899",
        "brilliant_indices": [],
        "great_indices": [],
        "notes": {},
    },
    {
        "game_id": "zhangchenrui0324_125243345725",
        "brilliant_indices": [],
        "great_indices": [62],  # 32.w Qxc7+
        "notes": {
            62: "Qxc7+ — great",
        },
    },
    {
        "game_id": "1jbd_125241591367",
        "brilliant_indices": [],
        "great_indices": [35, 43, 47, 52],  # 18.b Qc5+, 22.b Nxf6, 24.b Re2, 27.w Kg1
        "notes": {
            35: "Qc5+ — great",
            43: "Nxf6 — great",
            47: "Re2 — great",
            52: "Kg1 — great",
        },
    },
    {
        "game_id": "SendFeetPicsPleasee_120856975142",
        "brilliant_indices": [],
        "great_indices": [23, 41, 45, 68, 90, 104, 106],  # 12.b Nc6, 21.b Bc6, 23.b Bb5, 35.w Nd6+, 46.w bxc3+, 53.w Nc1, 54.w Ne2
        "notes": {
            23: "Nc6 — great",
            41: "Bc6 — great",
            45: "Bb5 — great",
            68: "Nd6+ — great",
            90: "bxc3+ — great",
            104: "Nc1 — great",
            106: "Ne2 — great",
        },
    },
    {
        "game_id": "maheshpadar_125299145887",
        "brilliant_indices": [],
        "great_indices": [12, 23],  # 7.w Nc3, 12.b Nc2+
        "notes": {
            12: "Nc3 — great",
            23: "Nc2+ — great",
        },
    },
    {
        "game_id": "darnelb18_120923590182",
        "brilliant_indices": [],
        "great_indices": [36],  # 19.w Kh1
        "notes": {
            36: "Kh1 — great",
        },
    },
    {
        "game_id": "Alisher_MU_125488161759",
        "brilliant_indices": [],
        "great_indices": [43],  # 22.b Rxe1+
        "notes": {
            43: "Rxe1+ — great",
        },
    },
    {
        "game_id": "Elvenleos_121048021572",
        "brilliant_indices": [],
        "great_indices": [11, 44],  # 6.b Qxg5, 23.w Bxg5
        "notes": {
            11: "Qxg5 — great",
            44: "Bxg5 — great",
        },
    },
    {
        "game_id": "Alexey_Yazykov_121658696144",
        "brilliant_indices": [],
        "great_indices": [36],  # 19.w Bxf4
        "notes": {
            36: "Bxf4 — great",
        },
    },
    {
        "game_id": "kairrox_121746547822",
        "brilliant_indices": [],
        "great_indices": [20, 82],  # 11.w e5, 42.w Rxg6+
        "notes": {
            20: "e5 — great",
            82: "Rxg6+ — great",
        },
    },
    {
        "game_id": "Sorokivskiy_129151372945",
        "brilliant_indices": [],
        "great_indices": [50, 53, 65, 67],  # 26.w Qxc6, 27.b Ne6, 33.b Nb6, 34.b Nd5+
        "notes": {
            50: "Qxc6 — great",
            53: "Ne6 — great",
            65: "Nb6 — great",
            67: "Nd5+ — great",
        },
    },
    {
        "game_id": "Meidinah_129128566291",
        "brilliant_indices": [],
        "great_indices": [35, 39, 44, 48, 53],  # 18.b Ne5, 20.b Qg6, 23.w Bxd3, 25.w Nf6+, 27.b Qb1#
        "notes": {
            35: "Ne5 — great",
            39: "Qg6 — great",
            44: "Bxd3 — great",
            48: "Nf6+ — great",
            53: "Qb1# — great",
        },
    },
    {
        "game_id": "QB1Kenobi_129468234191",
        "brilliant_indices": [],
        "great_indices": [16, 28],  # 9.w Rxd1, 15.w Nxe5
        "notes": {
            16: "Rxd1 — great",
            28: "Nxe5 — great",
        },
    },
    {
        "game_id": "Appolon74_129806993755",
        "brilliant_indices": [],
        "great_indices": [31],  # 16.b Nxd3
        "notes": {
            31: "Nxd3 — great",
        },
    },
    {
        "game_id": "cosmos158_130354892009",
        "brilliant_indices": [],
        "great_indices": [27, 31, 54, 60, 95],  # 14.b Nxf3+, 16.b Bd4+, 28.w e6, 31.w Rf8, 48.b g3
        "notes": {
            27: "Nxf3+ — great",
            31: "Bd4+ — great",
            54: "e6 — great",
            60: "Rf8 — great",
            95: "g3 — great",
        },
    },
    {
        "game_id": "Hamigway_165149396424",
        "brilliant_indices": [],
        "great_indices": [28, 41, 43],  # 15.w Qxc8, 21.b Bxg2, 22.b Nd5
        "notes": {
            28: "Qxc8 — great",
            41: "Bxg2 — great",
            43: "Nd5 — great",
        },
    },
    {
        "game_id": "haritjokro_165148151382",
        "brilliant_indices": [],
        "great_indices": [11, 29, 46, 48, 50],  # 6.b Nd5, 15.b a6, 24.w Bc5, 25.w Be4, 26.w Rc1
        "notes": {
            11: "Nd5 — great",
            29: "a6 — great",
            46: "Bc5 — great",
            48: "Be4 — great",
            50: "Rc1 — great",
        },
    },
    {
        "game_id": "lindblad1234_165175761796",
        "brilliant_indices": [],
        "great_indices": [3, 22, 27, 56, 59, 72],  # 2.b dxe4, 12.w Qh5+, 14.b exd5, 29.w Qd7+, 30.b Qxh4, 37.w Qe6+
        "notes": {
            3: "dxe4 — great",
            22: "Qh5+ — great",
            27: "exd5 — great",
            56: "Qd7+ — great",
            59: "Qxh4 — great",
            72: "Qe6+ — great",
        },
    },
    {
        "game_id": "Peorael_165225961362",
        "brilliant_indices": [],
        "great_indices": [18, 79],  # 10.w e4, 40.b Bxc4
        "notes": {
            18: "e4 — great",
            79: "Bxc4 — great",
        },
    },
    {
        "game_id": "IGINO51_165628312728",
        "brilliant_indices": [],
        "great_indices": [41, 48],  # 21.b Qxf5, 25.w Bxf3
        "notes": {
            41: "Qxf5 — great",
            48: "Bxf3 — great",
        },
    },
    {
        "game_id": "sidoye_165965658898",
        "brilliant_indices": [],
        "great_indices": [27, 36, 45, 49, 51],  # 14.b Be6, 19.w Bxc3, 23.b Nxa4, 25.b Rb8, 26.b Rb2
        "notes": {
            27: "Be6 — great",
            36: "Bxc3 — great",
            45: "Nxa4 — great",
            49: "Rb8 — great",
            51: "Rb2 — great",
        },
    },
    {
        "game_id": "demojayso_166032676560",
        "brilliant_indices": [],
        "great_indices": [22, 35],  # 12.w d6, 18.b Qxd1
        "notes": {
            22: "d6 — great",
            35: "Qxd1 — great",
        },
    },
    {
        "game_id": "Ramadan0099_166067143160",
        "brilliant_indices": [],
        "great_indices": [49, 77, 81, 97, 99, 103, 107],  # 25.b Qc6+, 39.b g5, 41.b g6, 49.b Kf8, 50.b Kf7, 52.b Kf7, 54.b Kf7
        "notes": {
            49: "Qc6+ — great",
            77: "g5 — great",
            81: "g6 — great",
            97: "Kf8 — great",
            99: "Kf7 — great",
            103: "Kf7 — great",
            107: "Kf7 — great",
        },
    },
    {
        "game_id": "NirwanSaranga2006_166267979194",
        "brilliant_indices": [],
        "great_indices": [27, 46],  # 14.b Qd7, 24.w Rh4
        "notes": {
            27: "Qd7 — great",
            46: "Rh4 — great",
        },
    },
    {
        "game_id": "DaGangsta65_166532052878",
        "brilliant_indices": [],
        "great_indices": [56],  # 29.w Qxf2
        "notes": {
            56: "Qxf2 — great",
        },
    },
    {
        "game_id": "LordCalcifur_166552416748",
        "brilliant_indices": [],
        "great_indices": [15, 29, 67],  # 8.b hxg5, 15.b Ne4, 34.b Kf8
        "notes": {
            15: "hxg5 — great",
            29: "Ne4 — great",
            67: "Kf8 — great",
        },
    },
    {
        "game_id": "PrengPergjoni_120849931720",
        "brilliant_indices": [],
        "great_indices": [41, 46],  # 21.b Qa5, 24.w exf6
        "notes": {
            41: "Qa5 — great",
            46: "exf6 — great",
        },
    },
    {
        "game_id": "Michaeluuw_125132354459",
        "brilliant_indices": [],
        "great_indices": [17, 43, 45],  # 9.b dxe5, 22.b Rb8, 23.b Rb5
        "notes": {
            17: "dxe5 — great",
            43: "Rb8 — great",
            45: "Rb5 — great",
        },
    },
    {
        "game_id": "shanmugasundaramganapathy_121694718318",
        "brilliant_indices": [],
        "great_indices": [15],  # 8.b Nxe3
        "notes": {
            15: "Nxe3 — great",
        },
    },
    {
        "game_id": "Alex-Master1951_129134628603",
        "brilliant_indices": [41],  # 21.b O-O
        "great_indices": [25, 45],  # 13.b Rxa6, 23.b Bb4+
        "notes": {
            41: "O-O — brilliant",
            25: "Rxa6 — great",
            45: "Bb4+ — great",
        },
    },
    {
        "game_id": "KrzychuBogus123_129310364027",
        "brilliant_indices": [],
        "great_indices": [24, 38],  # 13.w Bxe7, 20.w Rd2
        "notes": {
            24: "Bxe7 — great",
            38: "Rd2 — great",
        },
    },
    {
        "game_id": "July27_1914_129728360695",
        "brilliant_indices": [24],  # 13.w Nxg5
        "great_indices": [32, 39],  # 17.w Qxg4+, 20.b Nxd4
        "notes": {
            24: "Nxg5 — brilliant",
            32: "Qxg4+ — great",
            39: "Nxd4 — great",
        },
    },
    {
        "game_id": "Onegentlesoul_165649893790",
        "brilliant_indices": [],
        "great_indices": [64, 63, 69],  # 33.w Qf4+, 32.b Be6, 35.b Be6
        "notes": {
            64: "Qf4+ — great",
            63: "Be6 — great",
            69: "Be6 — great",
        },
    },
    {
        "game_id": "ACDRAGON777_166016258776",
        "brilliant_indices": [],
        "great_indices": [112],  # 57.w Bd3+
        "notes": {
            112: "Bd3+ — great",
        },
    },
    {
        "game_id": "T1602T_166267448056",
        "brilliant_indices": [],
        "great_indices": [38],  # 20.w Qxb7
        "notes": {
            38: "Qxb7 — great",
        },
    },
    {
        "game_id": "Marekzkoz_166536046244",
        "brilliant_indices": [],
        "great_indices": [],
        "notes": {},
    },
    {
        "game_id": "JuanAdo22_166615409160",
        "brilliant_indices": [10],  # 6.w Nxf7
        "great_indices": [12],  # 7.w Bg6+
        "notes": {
            10: "Nxf7 — brilliant, knight sacrifice exploiting h6 weakness",
            12: "Bg6+ — great, bishop sacrifice forcing Kxg6 then Qxd8",
        },
    },
    {
        "game_id": "BijayGorkhali_125300372607",
        "brilliant_indices": [],
        "great_indices": [24, 49],  # 13.w Qc3, 25.b Rh8
        "notes": {
            24: "Qc3 — great",
            49: "Rh8 — great",
        },
    },
    {
        "game_id": "shantanutanajijadhav_121719505484",
        "brilliant_indices": [],
        "great_indices": [12, 32, 38],  # 7.w f4, 17.w axb4, 20.w Kxc2
        "notes": {
            12: "f4 — great",
            32: "axb4 — great",
            38: "Kxc2 — great",
        },
    },
    {
        "game_id": "Buffalloman_166048620794",
        "brilliant_indices": [],
        "great_indices": [11, 34, 36],  # 6.b Bxf3, 18.w exd6, 19.w Re5+
        "notes": {
            11: "Bxf3 — great",
            34: "exd6 — great",
            36: "Re5+ — great",
        },
    },
    {
        "game_id": "brewok007_166269757202",
        "brilliant_indices": [],
        "great_indices": [16, 58, 68, 86],  # 9.w Ne5, 30.w b6, 35.w a6, 44.w Rxf7
        "notes": {
            16: "Ne5 — great",
            58: "b6 — great",
            68: "a6 — great",
            86: "Rxf7 — great",
        },
    },
    {
        "game_id": "lapulsaqk_166679850834",
        "brilliant_indices": [],
        "great_indices": [56, 83],  # 29.w Kg2, 42.b Rxf2+
        "notes": {
            56: "Kg2 — great",
            83: "Rxf2+ — great",
        },
    },
    {
        "game_id": "m_reza_68_166706303302",
        "brilliant_indices": [],
        "great_indices": [45],  # 23.b Bxe5+
        "notes": {
            45: "Bxe5+ — great",
        },
    },
    {
        "game_id": "Vega2603_125068778235",
        "brilliant_indices": [],
        "great_indices": [24, 31, 33, 35],  # 13.w Bxf6, 16.b a4, 17.b b5, 18.b Qc6
        "notes": {
            24: "Bxf6 — great",
            31: "a4 — great",
            33: "b5 — great",
            35: "Qc6 — great",
        },
    },
    {
        "game_id": "MisterMoltisanti_121108381224",
        "brilliant_indices": [],
        "great_indices": [26],  # 14.w dxe6
        "notes": {
            26: "dxe6 — great",
        },
    },
    {
        "game_id": "Devl213_130014558787",
        "brilliant_indices": [],
        "great_indices": [17, 27, 63, 65],  # 9.b Qxb2, 14.b Qxc1, 32.b Kc7, 33.b Rd7
        "notes": {
            17: "Qxb2 — great",
            27: "Qxc1 — great",
            63: "Kc7 — great",
            65: "Rd7 — great",
        },
    },
    {
        "game_id": "zhyxs_166023796044",
        "brilliant_indices": [31],  # 16.b Rfe8
        "great_indices": [18, 24, 26, 30, 33, 35],  # 10.w Ne2, 13.w Nxd4, 14.w Rd1, 16.w Rf4, 17.b Qd3, 18.b Rad8
        "notes": {
            18: "Ne2 — great",
            24: "Nxd4 — great",
            26: "Rd1 — great",
            30: "Rf4 — great",
            31: "Rfe8 — brilliant",
            33: "Qd3 — great",
            35: "Rad8 — great",
        },
    },
    {
        "game_id": "Soldier_XVII_166160698244",
        "brilliant_indices": [],
        "great_indices": [21],  # 11.b Nf2
        "notes": {
            21: "Nf2 — great",
        },
    },
    {
        "game_id": "Muhammad_Salah_85_166712719180",
        "brilliant_indices": [],
        "great_indices": [25, 57],  # 13.b f5, 29.b dxe6
        "notes": {
            25: "f5 — great",
            57: "dxe6 — great",
        },
    },
    {
        "game_id": "Abdallah_youssef_166978769074",
        "brilliant_indices": [],
        "great_indices": [35, 45],  # 18.b Kf7, 23.b Kc7
        "notes": {
            35: "Kf7 — great",
            45: "Kc7 — great",
        },
    },
    {
        "game_id": "cosmostronomer_166966697026",
        "brilliant_indices": [],
        "great_indices": [42],  # 22.w Nxh4
        "notes": {
            42: "Nxh4 — great",
        },
    },
    {
        "game_id": "jose0981827_125143129675",
        "brilliant_indices": [],
        "great_indices": [29, 39],  # 15.b Ba6, 20.b Bc5+
        "notes": {
            29: "Ba6 — great",
            39: "Bc5+ — great",
        },
    },
    {
        "game_id": "piyuh22_121628443886",
        "brilliant_indices": [],
        "great_indices": [18, 27],  # 10.w Bxd5, 14.b Nxf3+
        "notes": {
            18: "Bxd5 — great",
            27: "Nxf3+ — great",
        },
    },
    {
        "game_id": "Moonstaars_121681793850",
        "brilliant_indices": [],
        "great_indices": [19, 23],  # 10.b Qe7, 12.b Nb4
        "notes": {
            19: "Qe7 — great",
            23: "Nb4 — great",
        },
    },
    {
        "game_id": "handi14_129317557287",
        "brilliant_indices": [],
        "great_indices": [17, 29, 35, 52],  # 9.b Nxc3, 15.b Bxf3, 18.b b6, 27.w Re7+
        "notes": {
            17: "Nxc3 — great",
            29: "Bxf3 — great",
            35: "b6 — great",
            52: "Re7+ — great",
        },
    },
    {
        "game_id": "BornWild10_130589457291",
        "brilliant_indices": [],
        "great_indices": [49],  # 25.b Nf3+
        "notes": {
            49: "Nf3+ — great",
        },
    },
    {
        "game_id": "MrNov37_945393651",
        "brilliant_indices": [56],  # 29.w Nh5
        "great_indices": [14, 58, 60],  # 8.w Nxc3, 30.w Qg2+, 31.w Qg7+
        "notes": {
            14: "Nxc3 — great",
            56: "Nh5 — brilliant",
            58: "Qg2+ — great",
            60: "Qg7+ — great",
        },
    },
    {
        "game_id": "TignoRboda_166788097780",
        "brilliant_indices": [],
        "great_indices": [45, 61],  # 23.b c6, 31.b Bd1+
        "notes": {
            45: "c6 — great",
            61: "Bd1+ — great",
        },
    },
    {
        "game_id": "gschwandner_125079545561",
        "brilliant_indices": [],
        "great_indices": [23, 34, 36, 41],  # 12.b d5, 18.w a3, 19.w b4, 21.b Nb3
        "notes": {
            23: "d5 — great",
            34: "a3 — great",
            36: "b4 — great",
            41: "Nb3 — great",
        },
    },
    {
        "game_id": "AbDoU3232_125074131347",
        "brilliant_indices": [],
        "great_indices": [23],  # 12.b g5
        "notes": {
            23: "g5 — great",
        },
    },
    {
        "game_id": "Muhendisemilyo_125140156527",
        "brilliant_indices": [],
        "great_indices": [14],  # 8.w Nxc6
        "notes": {
            14: "Nxc6 — great",
        },
    },
    {
        "game_id": "NithiSri10_120859893796",
        "brilliant_indices": [],
        "great_indices": [41, 49],  # 21.b a5, 25.b Nxd4
        "notes": {
            41: "a5 — great",
            49: "Nxd4 — great",
        },
    },
    {
        "game_id": "hhjnfyh_120857413442",
        "brilliant_indices": [],
        "great_indices": [12, 28],  # 7.w Bxd3, 15.w Qe2
        "notes": {
            12: "Bxd3 — great",
            28: "Qe2 — great",
        },
    },
    {
        "game_id": "SiAkiSiaosi84_120857226380",
        "brilliant_indices": [],
        "great_indices": [6],  # 4.w Qa4+
        "notes": {
            6: "Qa4+ — great",
        },
    },
    {
        "game_id": "KirorOwO_120856516390",
        "brilliant_indices": [],
        "great_indices": [12],  # 7.w Nc7+
        "notes": {
            12: "Nc7+ — great",
        },
    },
]
