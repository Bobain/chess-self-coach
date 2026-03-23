"""Shared constants for chess analysis engine.

Single source of truth for values used across multiple modules
(analysis.py, trainer.py, tablebase.py, analyze.py).
"""

from __future__ import annotations

# --- Mate score sentinel (centipawns) ---
MATE_CP = 10_000

# --- Piece count thresholds for analysis brackets ---
ENDGAME_PIECES_MAX = 7
MIDDLEGAME_PIECES_MAX = 12

# --- Analysis time/depth limits per bracket ---
ANALYSIS_TIME_LIMIT = 10.0  # seconds, uniform cap for all brackets

ANALYSIS_LIMITS: dict[str, dict[str, float | int]] = {
    "kings_pawns_le7": {"time": ANALYSIS_TIME_LIMIT, "depth": 60},
    "pieces_le7": {"time": ANALYSIS_TIME_LIMIT, "depth": 50},
    "pieces_le12": {"time": ANALYSIS_TIME_LIMIT, "depth": 40},
    "default": {"depth": 18, "time": ANALYSIS_TIME_LIMIT},
}

# --- Centipawn thresholds for error classification ---
BLUNDER_THRESHOLD = 200
MISTAKE_THRESHOLD = 100
INACCURACY_THRESHOLD = 50

# --- Position filtering: skip already-decided positions ---
DOMINATED_POSITION_CP = 500  # |eval| > this → position is already won/lost

# --- PV display limit (non-mate positions) ---
MAX_PV_MOVES = 10
