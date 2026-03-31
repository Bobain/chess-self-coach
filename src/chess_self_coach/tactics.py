"""Tactical motif detection for chess moves.

Analyzes positions using python-chess to detect forks, pins, skewers,
mate threats, and other tactical/positional patterns. Results are stored
in tactic_data.json for use by the classifier and training pipeline.

Run: chess-self-coach train --tactics (or call run_tactical_analysis())
"""

from __future__ import annotations

import json
import logging
import multiprocessing
from pathlib import Path

import chess

from chess_self_coach import worker_count
from chess_self_coach.config import analysis_data_path, tactic_data_path
from chess_self_coach.io import atomic_write_json

_log = logging.getLogger(__name__)

PIECE_VALUES = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0,
}

# ── Shared utilities ──


def _play_move(fen: str, uci: str) -> tuple[chess.Board, chess.Move] | None:
    """Play a UCI move on a board, return (board_after, move) or None."""
    try:
        board = chess.Board(fen)
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            return None
        board.push(move)
        return board, move
    except (ValueError, IndexError):
        return None


def _valuable_attackers(board: chess.Board, square: chess.Square, by_color: chess.Color) -> list[chess.Square]:
    """Squares of pieces of `by_color` attacking `square`."""
    return list(board.attackers(by_color, square))


def _piece_val(board: chess.Board, sq: chess.Square) -> int:
    """Value of piece on square, 0 if empty."""
    p = board.piece_at(sq)
    return PIECE_VALUES.get(p.piece_type, 0) if p else 0


# ── Group 1: Tactical core ──


def is_fork(board: chess.Board, move: chess.Move) -> bool:
    """Piece attacks 2+ enemy pieces worth >= 3 after the move."""
    to = move.to_square
    piece = board.piece_at(to)
    if not piece:
        return False
    attacker_color = piece.color
    opp = not attacker_color
    attacked = board.attacks(to)
    valuable_targets = 0
    for sq in attacked:
        target = board.piece_at(sq)
        if target and target.color == opp and PIECE_VALUES.get(target.piece_type, 0) >= 3:
            valuable_targets += 1
    return valuable_targets >= 2


def creates_pin(board: chess.Board, move: chess.Move) -> bool:
    """Move creates an absolute or relative pin."""
    mover_color = board.piece_at(move.to_square).color if board.piece_at(move.to_square) else None
    if mover_color is None:
        return False
    opp = not mover_color
    # Check all opponent pieces for pins
    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        if p and p.color == opp and p.piece_type != chess.KING:
            if board.is_pinned(opp, sq):
                return True
    return False


def is_skewer(board: chess.Board, move: chess.Move) -> bool:
    """Attack through a valuable piece to a lesser one behind."""
    to = move.to_square
    piece = board.piece_at(to)
    if not piece or piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return False
    opp = not piece.color
    # Scan rays from the moved piece
    if piece.piece_type == chess.BISHOP:
        dirs = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    elif piece.piece_type == chess.ROOK:
        dirs = [(0, 1), (0, -1), (1, 0), (-1, 0)]
    else:
        dirs = [(1, 1), (1, -1), (-1, 1), (-1, -1), (0, 1), (0, -1), (1, 0), (-1, 0)]

    f, r = chess.square_file(to), chess.square_rank(to)
    for df, dr in dirs:
        ray = []
        cf, cr = f + df, r + dr
        while 0 <= cf < 8 and 0 <= cr < 8:
            sq = chess.square(cf, cr)
            p = board.piece_at(sq)
            if p:
                ray.append((sq, p))
                if len(ray) >= 2:
                    break
            cf += df
            cr += dr
        if len(ray) == 2 and ray[0][1].color == opp and ray[1][1].color == opp:
            v0 = PIECE_VALUES.get(ray[0][1].piece_type, 0)
            v1 = PIECE_VALUES.get(ray[1][1].piece_type, 0)
            if v0 > v1:
                return True
    return False


def is_discovered_attack(board_before: chess.Board, board_after: chess.Board, move: chess.Move) -> bool:
    """Moving piece reveals an attack from a piece behind it."""
    mover_color = board_before.piece_at(move.from_square).color if board_before.piece_at(move.from_square) else None
    if mover_color is None:
        return False
    opp = not mover_color
    # Check if any friendly piece (other than the mover) now attacks new enemy pieces
    for sq in chess.SQUARES:
        p = board_after.piece_at(sq)
        if not p or p.color != mover_color or sq == move.to_square:
            continue
        if p.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            continue
        attacks_after = board_after.attacks(sq)
        attacks_before = board_before.attacks(sq)
        new_attacks = attacks_after - attacks_before
        for target_sq in new_attacks:
            target = board_after.piece_at(target_sq)
            if target and target.color == opp and PIECE_VALUES.get(target.piece_type, 0) >= 3:
                return True
    return False


def is_discovered_check(board_after: chess.Board, move: chess.Move) -> bool:
    """Discovered attack that gives check (checking piece != moved piece)."""
    if not board_after.is_check():
        return False
    opp = not board_after.turn  # side that just moved
    king_sq = board_after.king(board_after.turn)
    if king_sq is None:
        return False
    # Check if the moved piece directly attacks the king
    if king_sq in board_after.attacks(move.to_square):
        return False  # Direct check, not discovered
    return True


def is_double_check(board_after: chess.Board, move: chess.Move) -> bool:
    """Both the moved piece and a revealed piece give check."""
    if not board_after.is_check():
        return False
    king_sq = board_after.king(board_after.turn)
    if king_sq is None:
        return False
    checkers = board_after.attackers(not board_after.turn, king_sq)
    return len(checkers) >= 2


def creates_mate_threat(board_after: chess.Board) -> bool:
    """After the move, player has mate in 1 in at least one line."""
    # It's opponent's turn. For each opponent move, check if we have a mate reply.
    for opp_move in list(board_after.legal_moves)[:8]:  # Limit for perf
        test = board_after.copy()
        test.push(opp_move)
        for our_move in test.legal_moves:
            test2 = test.copy()
            test2.push(our_move)
            if test2.is_checkmate():
                return True
    return False


def is_back_rank_threat(board_after: chess.Board) -> bool:
    """Threatens back rank mate."""
    mover_color = not board_after.turn  # side that just moved
    opp = board_after.turn
    back_rank = 0 if opp == chess.WHITE else 7
    king_sq = board_after.king(opp)
    if king_sq is None or chess.square_rank(king_sq) != back_rank:
        return False
    # Check if our rook/queen attacks the back rank toward the king
    for sq in chess.SQUARES:
        p = board_after.piece_at(sq)
        if p and p.color == mover_color and p.piece_type in (chess.ROOK, chess.QUEEN):
            if king_sq in board_after.attacks(sq):
                return True
    return False


def is_smothered_mate(board_after: chess.Board, move: chess.Move) -> bool:
    """Knight delivers mate with king boxed by own pieces."""
    if not board_after.is_checkmate():
        return False
    piece = board_after.piece_at(move.to_square)
    if not piece or piece.piece_type != chess.KNIGHT:
        return False
    king_sq = board_after.king(board_after.turn)
    if king_sq is None:
        return False
    # All adjacent squares must have friendly pieces
    for adj in chess.SQUARES:
        if chess.square_distance(king_sq, adj) == 1:
            p = board_after.piece_at(adj)
            if not p or p.color != board_after.turn:
                return False
    return True


def is_trapped_piece(board_after: chess.Board) -> bool:
    """Enemy piece worth >= 3 has no safe squares."""
    mover_color = not board_after.turn
    opp = board_after.turn
    for sq in chess.SQUARES:
        p = board_after.piece_at(sq)
        if not p or p.color != opp or PIECE_VALUES.get(p.piece_type, 0) < 3:
            continue
        # Check if this piece has any safe move
        has_safe = False
        for target in board_after.attacks(sq):
            if not board_after.is_attacked_by(mover_color, target):
                has_safe = True
                break
        if not has_safe:
            return True
    return False


def is_removal_of_defender(board_before: chess.Board, board_after: chess.Board, move: chess.Move) -> bool:
    """Captures a piece that was defending another."""
    if not board_before.is_capture(move):
        return False
    captured_sq = move.to_square
    mover_color = board_before.piece_at(move.from_square).color
    opp = not mover_color
    # What was the captured piece defending?
    before_piece = board_before.piece_at(captured_sq)
    if not before_piece:
        return False
    defended_before = board_before.attacks(captured_sq)
    for def_sq in defended_before:
        target = board_before.piece_at(def_sq)
        if not target or target.color != opp:
            continue
        # After capture, is this piece now undefended and attacked?
        if board_after.is_attacked_by(mover_color, def_sq) and not board_after.is_attacked_by(opp, def_sq):
            return True
    return False


def is_desperado(board_before: chess.Board, move: chess.Move) -> bool:
    """Doomed piece captures to inflict maximum damage."""
    if not board_before.is_capture(move):
        return False
    piece = board_before.piece_at(move.from_square)
    if not piece or PIECE_VALUES.get(piece.piece_type, 0) < 3:
        return False
    # Was the piece attacked (doomed)?
    return board_before.is_attacked_by(not piece.color, move.from_square)


# ── Group 2: Checks & Mates ──


def is_checkmate(board_after: chess.Board) -> bool:
    """Move delivers checkmate."""
    return board_after.is_checkmate()


def is_check(board_after: chess.Board) -> bool:
    """Move gives check."""
    return board_after.is_check()


def destroys_castling(board_before: chess.Board, board_after: chess.Board) -> bool:
    """Forces opponent to lose castling rights."""
    mover_color = board_before.turn
    opp = not mover_color
    before_rights = board_before.has_queenside_castling_rights(opp) or board_before.has_kingside_castling_rights(opp)
    after_rights = board_after.has_queenside_castling_rights(opp) or board_after.has_kingside_castling_rights(opp)
    return before_rights and not after_rights


def is_windmill(board_before: chess.Board, pv_uci: list[str]) -> bool:
    """PV shows repeated discovered checks (>= 2)."""
    if len(pv_uci) < 5:
        return False
    try:
        board = board_before.copy()
        disc_checks = 0
        for i, uci in enumerate(pv_uci[:8]):
            m = chess.Move.from_uci(uci)
            if m not in board.legal_moves:
                break
            board.push(m)
            if i % 2 == 0 and board.is_check():
                disc_checks += 1
        return disc_checks >= 2
    except (ValueError, IndexError):
        return False


def is_perpetual_check(board_before: chess.Board, pv_uci: list[str]) -> bool:
    """PV shows 3+ consecutive checks from our side."""
    if len(pv_uci) < 5:
        return False
    try:
        board = board_before.copy()
        consecutive = 0
        for i, uci in enumerate(pv_uci[:10]):
            m = chess.Move.from_uci(uci)
            if m not in board.legal_moves:
                break
            board.push(m)
            if i % 2 == 0 and board.is_check():
                consecutive += 1
            elif i % 2 == 0:
                break
        return consecutive >= 3
    except (ValueError, IndexError):
        return False


# ── Group 3: Pawn structure ──


def creates_passed_pawn(board_after: chess.Board, move: chess.Move) -> bool:
    """Pawn move creates a passed pawn."""
    piece = board_after.piece_at(move.to_square)
    if not piece or piece.piece_type != chess.PAWN:
        return False
    f = chess.square_file(move.to_square)
    r = chess.square_rank(move.to_square)
    opp = not piece.color
    direction = 1 if piece.color == chess.WHITE else -1
    # Check ranks ahead for enemy pawns on same or adjacent files
    for check_f in range(max(0, f - 1), min(8, f + 2)):
        check_r = r + direction
        while 0 <= check_r < 8:
            sq = chess.square(check_f, check_r)
            p = board_after.piece_at(sq)
            if p and p.piece_type == chess.PAWN and p.color == opp:
                return False
            check_r += direction
    return True


def is_promotion(move: chess.Move) -> bool:
    """Pawn promotes."""
    return move.promotion is not None


def is_underpromotion(move: chess.Move) -> bool:
    """Promotes to non-queen."""
    return move.promotion is not None and move.promotion != chess.QUEEN


def is_pawn_break(board_before: chess.Board, move: chess.Move) -> bool:
    """Pawn captures another pawn."""
    piece = board_before.piece_at(move.from_square)
    if not piece or piece.piece_type != chess.PAWN:
        return False
    return board_before.is_capture(move) and board_before.piece_at(move.to_square) is not None and board_before.piece_at(move.to_square).piece_type == chess.PAWN


def is_en_passant(board_before: chess.Board, move: chess.Move) -> bool:
    """En passant capture."""
    return board_before.is_en_passant(move)


# ── Group 4: Positional ──


def is_outpost(board_after: chess.Board, move: chess.Move) -> bool:
    """Piece on square not attackable by enemy pawns, in opponent's half."""
    piece = board_after.piece_at(move.to_square)
    if not piece or piece.piece_type in (chess.PAWN, chess.KING):
        return False
    f = chess.square_file(move.to_square)
    r = chess.square_rank(move.to_square)
    opp = not piece.color
    direction = 1 if opp == chess.WHITE else -1
    for adj_f in [f - 1, f + 1]:
        if adj_f < 0 or adj_f >= 8:
            continue
        check_r = r + direction
        while 0 <= check_r < 8:
            p = board_after.piece_at(chess.square(adj_f, check_r))
            if p and p.piece_type == chess.PAWN and p.color == opp:
                return False
            check_r += direction
    in_opp_half = r >= 4 if piece.color == chess.WHITE else r <= 3
    return in_opp_half


def is_centralization(move: chess.Move) -> bool:
    """Piece moves to d4/d5/e4/e5."""
    return move.to_square in (chess.D4, chess.D5, chess.E4, chess.E5)


def is_seventh_rank_invasion(board_after: chess.Board, move: chess.Move) -> bool:
    """Rook or queen reaches 7th/2nd rank."""
    piece = board_after.piece_at(move.to_square)
    if not piece or piece.piece_type not in (chess.ROOK, chess.QUEEN):
        return False
    seventh = 6 if piece.color == chess.WHITE else 1
    return chess.square_rank(move.to_square) == seventh


def is_open_file_control(board_after: chess.Board, move: chess.Move) -> bool:
    """Rook/queen on file with no own pawns."""
    piece = board_after.piece_at(move.to_square)
    if not piece or piece.piece_type not in (chess.ROOK, chess.QUEEN):
        return False
    f = chess.square_file(move.to_square)
    for r in range(8):
        p = board_after.piece_at(chess.square(f, r))
        if p and p.piece_type == chess.PAWN and p.color == piece.color:
            return False
    return True


def is_king_safety_degradation(board_before: chess.Board, board_after: chess.Board) -> bool:
    """Weakens opponent king shelter (pawn shield reduced)."""
    opp = board_before.turn  # opponent is the one NOT moving; but after push, turn flips
    # Actually: mover = board_before.turn, opp = not mover
    mover = board_before.turn
    opp = not mover
    king_sq = board_after.king(opp)
    if king_sq is None:
        return False
    kr = chess.square_rank(king_sq)
    kf = chess.square_file(king_sq)
    shield_rank = kr + (1 if opp == chess.WHITE else -1)
    if shield_rank < 0 or shield_rank > 7:
        return False
    before_pawns = after_pawns = 0
    for df in range(-1, 2):
        nf = kf + df
        if nf < 0 or nf >= 8:
            continue
        sq = chess.square(nf, shield_rank)
        pb = board_before.piece_at(sq)
        if pb and pb.piece_type == chess.PAWN and pb.color == opp:
            before_pawns += 1
        pa = board_after.piece_at(sq)
        if pa and pa.piece_type == chess.PAWN and pa.color == opp:
            after_pawns += 1
    return after_pawns < before_pawns


# ── Group 5: Material ──


def is_exchange_sacrifice(board_before: chess.Board, move: chess.Move) -> bool:
    """Rook given for minor piece."""
    piece = board_before.piece_at(move.from_square)
    captured = board_before.piece_at(move.to_square)
    if not piece or not captured:
        return False
    return piece.piece_type == chess.ROOK and captured.piece_type in (chess.KNIGHT, chess.BISHOP)


def is_queen_sacrifice(board_before: chess.Board, board_after: chess.Board, move: chess.Move) -> bool:
    """Queen moves to attacked square."""
    piece = board_before.piece_at(move.from_square)
    if not piece or piece.piece_type != chess.QUEEN:
        return False
    return board_after.is_attacked_by(not piece.color, move.to_square)


def is_hanging_capture(board_before: chess.Board, move: chess.Move) -> bool:
    """Captures an undefended piece."""
    if not board_before.is_capture(move):
        return False
    captured = board_before.piece_at(move.to_square)
    if not captured or PIECE_VALUES.get(captured.piece_type, 0) < 1:
        return False
    return not board_before.is_attacked_by(captured.color, move.to_square)


# ── Group 6: Special ──


def is_stalemate_trap(board_after: chess.Board) -> bool:
    """Creates stalemate."""
    return board_after.is_stalemate()


def is_quiet_move(board_before: chess.Board, move: chess.Move, best_uci: str | None) -> bool:
    """Non-check, non-capture that is the engine's best."""
    if board_before.is_capture(move):
        return False
    board_after = board_before.copy()
    board_after.push(move)
    if board_after.is_check():
        return False
    return best_uci is not None and move.uci() == best_uci


def is_clearance(board_before: chess.Board, board_after: chess.Board, move: chess.Move) -> bool:
    """Moves a piece to clear a line for another."""
    mover_color = board_before.turn
    for sq in chess.SQUARES:
        p = board_after.piece_at(sq)
        if not p or p.color != mover_color or sq == move.to_square:
            continue
        if p.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            continue
        before_n = len(board_before.attacks(sq))
        after_n = len(board_after.attacks(sq))
        if after_n > before_n:
            return True
    return False


def is_xray_attack(board_after: chess.Board, move: chess.Move) -> bool:
    """Attacks through a friendly piece to an enemy piece behind."""
    piece = board_after.piece_at(move.to_square)
    if not piece or piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return False
    to = move.to_square
    f, r = chess.square_file(to), chess.square_rank(to)
    if piece.piece_type == chess.BISHOP:
        dirs = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    elif piece.piece_type == chess.ROOK:
        dirs = [(0, 1), (0, -1), (1, 0), (-1, 0)]
    else:
        dirs = [(1, 1), (1, -1), (-1, 1), (-1, -1), (0, 1), (0, -1), (1, 0), (-1, 0)]

    opp = not piece.color
    for df, dr in dirs:
        ray = []
        cf, cr = f + df, r + dr
        while 0 <= cf < 8 and 0 <= cr < 8:
            sq = chess.square(cf, cr)
            p = board_after.piece_at(sq)
            if p:
                ray.append(p)
            if len(ray) >= 2:
                break
            cf += df
            cr += dr
        if len(ray) == 2 and ray[0].color == piece.color and ray[1].color == opp:
            if PIECE_VALUES.get(ray[1].piece_type, 0) >= 3:
                return True
    return False


def is_piece_activity(board_before: chess.Board, board_after: chess.Board, move: chess.Move) -> bool:
    """Piece gains significant mobility (>= 3 new attacks)."""
    piece = board_before.piece_at(move.from_square)
    if not piece or piece.piece_type in (chess.PAWN, chess.KING):
        return False
    before_n = len(board_before.attacks(move.from_square))
    after_n = len(board_after.attacks(move.to_square))
    return after_n >= before_n + 3


def is_castling(board_before: chess.Board, move: chess.Move) -> bool:
    """Castling move."""
    return board_before.is_castling(move)


# ══════════════════════════════════════════════════════════════════════════════
# Main analysis: analyze all moves of one game
# ══════════════════════════════════════════════════════════════════════════════


def analyze_move(move_data: dict) -> dict:
    """Analyze tactical motifs for a single move. Returns dict of booleans."""
    fen = move_data.get("fen_before", "")
    uci = move_data.get("move_uci", "")
    if not fen or not uci:
        return {}

    result = _play_move(fen, uci)
    if not result:
        return {}
    board_after, move = result
    board_before = chess.Board(fen)
    eb = move_data.get("eval_before", {})
    pv_uci = eb.get("pv_uci", [])
    best_uci = eb.get("best_move_uci")

    motifs: dict[str, bool] = {}
    try:
        motifs["isFork"] = is_fork(board_after, move)
        motifs["createsPin"] = creates_pin(board_after, move)
        motifs["isSkewer"] = is_skewer(board_after, move)
        motifs["isDiscoveredAttack"] = is_discovered_attack(board_before, board_after, move)
        motifs["isDiscoveredCheck"] = is_discovered_check(board_after, move)
        motifs["isDoubleCheck"] = is_double_check(board_after, move)
        motifs["createsMateThreat"] = creates_mate_threat(board_after)
        motifs["isBackRankThreat"] = is_back_rank_threat(board_after)
        motifs["isSmotheredMate"] = is_smothered_mate(board_after, move)
        motifs["isTrappedPiece"] = is_trapped_piece(board_after)
        motifs["isRemovalOfDefender"] = is_removal_of_defender(board_before, board_after, move)
        motifs["isDesperado"] = is_desperado(board_before, move)
        motifs["isCheckmate"] = is_checkmate(board_after)
        motifs["isCheck"] = is_check(board_after)
        motifs["destroysCastling"] = destroys_castling(board_before, board_after)
        motifs["isWindmill"] = is_windmill(board_before, pv_uci)
        motifs["isPerpetualCheck"] = is_perpetual_check(board_before, pv_uci)
        motifs["createsPassedPawn"] = creates_passed_pawn(board_after, move)
        motifs["isPromotion"] = is_promotion(move)
        motifs["isUnderpromotion"] = is_underpromotion(move)
        motifs["isPawnBreak"] = is_pawn_break(board_before, move)
        motifs["isEnPassant"] = is_en_passant(board_before, move)
        motifs["isOutpost"] = is_outpost(board_after, move)
        motifs["isCentralization"] = is_centralization(move)
        motifs["isSeventhRankInvasion"] = is_seventh_rank_invasion(board_after, move)
        motifs["isOpenFileControl"] = is_open_file_control(board_after, move)
        motifs["isKingSafetyDegradation"] = is_king_safety_degradation(board_before, board_after)
        motifs["isExchangeSacrifice"] = is_exchange_sacrifice(board_before, move)
        motifs["isQueenSacrifice"] = is_queen_sacrifice(board_before, board_after, move)
        motifs["isHangingCapture"] = is_hanging_capture(board_before, move)
        motifs["isStalemateTrap"] = is_stalemate_trap(board_after)
        motifs["isQuietMove"] = is_quiet_move(board_before, move, best_uci)
        motifs["isClearance"] = is_clearance(board_before, board_after, move)
        motifs["isXrayAttack"] = is_xray_attack(board_after, move)
        motifs["isPieceActivity"] = is_piece_activity(board_before, board_after, move)
        motifs["isCastling"] = is_castling(board_before, move)
    except Exception as e:
        _log.debug("Motif analysis error for %s %s: %s", fen[:20], uci, e)

    # PV lookahead: run motifs on our moves in the PV (up to 3 of our moves)
    pv_motifs: dict[str, int] = {}  # motif_name → PV depth where first found
    if pv_uci and len(pv_uci) >= 2:
        try:
            pv_board = chess.Board(fen)
            mover_turn = pv_board.turn
            our_move_count = 0
            for pv_i, pv_uci_str in enumerate(pv_uci[:6]):
                pv_move = chess.Move.from_uci(pv_uci_str)
                if pv_move not in pv_board.legal_moves:
                    break
                is_our_move = pv_board.turn == mover_turn
                pv_board.push(pv_move)
                if is_our_move and pv_i > 0:
                    our_move_count += 1
                    if our_move_count > 3:
                        break
                    # Run key tactical helpers on this PV position
                    pv_before = chess.Board(pv_board.fen())
                    pv_before.pop()  # undo to get before state
                    for name, fn in [
                        ("isFork", lambda: is_fork(pv_board, pv_move)),
                        ("createsPin", lambda: creates_pin(pv_board, pv_move)),
                        ("isSkewer", lambda: is_skewer(pv_board, pv_move)),
                        ("isBackRankThreat", lambda: is_back_rank_threat(pv_board)),
                        ("createsMateThreat", lambda: creates_mate_threat(pv_board)),
                        ("isCheckmate", lambda: is_checkmate(pv_board)),
                        ("isCheck", lambda: is_check(pv_board)),
                        ("isTrappedPiece", lambda: is_trapped_piece(pv_board)),
                        ("isSeventhRankInvasion", lambda: is_seventh_rank_invasion(pv_board, pv_move)),
                        ("isKingSafetyDegradation", lambda: is_king_safety_degradation(pv_before, pv_board)),
                    ]:
                        if name not in pv_motifs:
                            try:
                                if fn():
                                    pv_motifs[name] = pv_i
                            except Exception:
                                pass
        except Exception:
            pass

    motifs["_pv"] = pv_motifs  # type: ignore[assignment]
    return motifs


def _analyze_game(game_item: tuple[str, dict]) -> tuple[str, list[dict]]:
    """Analyze all moves of one game. For multiprocessing."""
    game_id, game_data = game_item
    moves = game_data.get("moves", [])
    return game_id, [analyze_move(m) for m in moves]


def run_tactical_analysis(analysis_path: Path | None = None, output_path: Path | None = None) -> None:
    """Run tactical motif analysis on all games, output to tactic_data.json."""
    import time

    if analysis_path is None:
        analysis_path = analysis_data_path()
    if output_path is None:
        output_path = tactic_data_path()

    if not analysis_path.exists():
        print(f"  No analysis data at {analysis_path}")
        return

    with open(analysis_path) as f:
        analysis = json.load(f)

    games = analysis.get("games", {})
    total_moves = sum(len(g.get("moves", [])) for g in games.values())
    n_workers = worker_count()

    print(f"  Tactical analysis: {len(games)} games, {total_moves} moves, {n_workers} workers")
    t0 = time.monotonic()

    game_items = list(games.items())

    with multiprocessing.Pool(processes=n_workers) as pool:
        results = pool.map(_analyze_game, game_items)

    tactic_data: dict[str, list[dict]] = {}
    for game_id, motifs_list in results:
        tactic_data[game_id] = motifs_list

    output = {"version": "1.0", "games": tactic_data}
    atomic_write_json(output_path, output, compact=True)

    elapsed = time.monotonic() - t0
    print(f"  Done in {elapsed:.1f}s → {output_path} ({output_path.stat().st_size / 1024:.0f} KB)")
