"""Brilliant move classification test cases from real games.

Enrich this list with real game data as we discover true positives,
false positives, and false negatives. Each case uses real positions
and engine evaluations copied from analysis_data.json.

Fields:
    id: Short identifier for the test case.
    description: Why this case matters.
    expected: "brilliant" if the move SHOULD be brilliant, anything else
              (e.g. "best", "excellent") if it should NOT be.
    move_data: Dict matching the shape expected by window._classifyMove().
    player_color: The color of the side that played the move.
"""

from __future__ import annotations

CASES: list[dict] = [
    # --- False positives (currently classified as brilliant but shouldn't be) ---
    {
        "id": "c4_queens_gambit",
        "description": (
            "2. c4 (Queen's Gambit) — standard opening move, pawn offered on c4. "
            "dxc4 recaptures in PV. This is a well-known gambit, not a brilliant "
            "sacrifice. Net material: -1 pawn (real gambit), but too routine to "
            "be brilliant."
        ),
        "expected": "not_brilliant",
        "player_color": "white",
        "move_data": {
            "fen_before": "rnbqkbnr/ppp1pppp/8/3p4/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 0 2",
            "move_san": "c4",
            "move_uci": "c2c4",
            "eval_before": {
                "score_cp": 27,
                "is_mate": False,
                "mate_in": None,
                "best_move_uci": "c2c4",
                "pv_uci": [
                    "c2c4", "d5c4", "g1f3", "g8f6", "e2e3",
                    "c7c5", "f1c4", "e7e6", "e1h1", "a7a6",
                ],
            },
            "eval_after": {"score_cp": 22, "is_mate": False, "mate_in": None},
        },
    },
    {
        "id": "Bxe6_recapture_chain",
        "description": (
            "24...Bxe6 — Bishop captures pawn, opponent bishop recaptures. "
            "PV truncated to 2 moves but full sequence is Bxe6, Bxe6, Rxe6 "
            "netting +1 pawn for Black. Favorable recapture, not a sacrifice."
        ),
        "expected": "not_brilliant",
        "player_color": "black",
        "move_data": {
            "fen_before": "r1b1r2k/1p4p1/4Pnqp/p4p2/P4P2/BB2P1P1/2Q4P/4RRK1 b - - 2 24",
            "move_san": "Bxe6",
            "move_uci": "c8e6",
            "eval_before": {
                "score_cp": -53,
                "is_mate": False,
                "mate_in": None,
                "best_move_uci": "c8e6",
                "pv_uci": ["c8e6", "b3e6"],
            },
            "eval_after": {"score_cp": -44, "is_mate": False, "mate_in": None},
        },
    },
    # --- True positives (correctly classified as brilliant) ---
    {
        "id": "Rxe3_tactical_trap",
        "description": (
            "33. Rxe3 — Rook captures knight, appears to sacrifice (Rook > Knight) "
            "but full exchange Rxe3, Rxe3, Rxe3 wins a whole knight (+3) because "
            "opponent can't continue recapturing due to Qxg7# mate threat. "
            "Tactical trap: apparent sacrifice -2, net gain +3."
        ),
        "expected": "brilliant",
        "player_color": "white",
        "move_data": {
            "fen_before": "4q2k/4r1p1/1p2r2p/p4p2/P4P2/2Q1n1PP/1B2R3/4R1K1 w - - 0 33",
            "move_san": "Rxe3",
            "move_uci": "e2e3",
            "eval_before": {
                "score_cp": 464,
                "is_mate": False,
                "mate_in": None,
                "best_move_uci": "e2e3",
                "pv_uci": ["e2e3", "e6e3", "e1e3", "h8h7"],
            },
            "eval_after": {"score_cp": 515, "is_mate": False, "mate_in": None},
        },
    },
]
