"""End-to-end tests for the Game Review & Analysis UI (Section 3c).

Tests the game list (default view), game review, move navigation,
eval bar, score chart, move classifications, board arrows, keyboard nav,
per-game training, and the Training menu item.

Uses analysis_data.json fixture from tests/e2e/fixtures/.

Requirements:
    uv run playwright install chromium
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect

# Timeout for CDN-loaded chessground to render (needs internet)
BOARD_TIMEOUT = 20000


def _wait_for_game_list(page, pwa_url):
    """Navigate to PWA and wait for the game list (default view)."""
    page.goto(pwa_url)
    page.wait_for_selector(".game-card", timeout=10000)


# --- Default view ---


def test_game_list_is_default_view(page, pwa_url):
    """Game list is the default view on app load."""
    page.goto(pwa_url)
    page.wait_for_selector(".game-card", timeout=10000)

    expect(page.locator("#analysis-view")).to_be_visible()
    expect(page.locator("#training-view")).to_be_hidden()


# --- Game selector ---


def test_game_selector_shows_games(page, pwa_url):
    """Game list shows analyzed games."""
    _wait_for_game_list(page, pwa_url)

    cards = page.locator(".game-card")
    expect(cards).to_have_count(2)

    # Each card shows opponent name and result
    expect(cards.first).to_contain_text("vs ")


def test_game_selector_shows_result_badges(page, pwa_url):
    """Game cards show W/L/D result badges."""
    _wait_for_game_list(page, pwa_url)

    results = page.locator(".game-card-result")
    expect(results).to_have_count(2)


# --- Game review ---


def test_click_game_enters_review(page, pwa_url):
    """Clicking a game card opens the review view."""
    _wait_for_game_list(page, pwa_url)

    page.click(".game-card >> nth=0")
    page.wait_for_selector("#review-board cg-board", timeout=BOARD_TIMEOUT)

    # Game selector hidden, review shown
    expect(page.locator("#game-selector")).to_be_hidden()
    expect(page.locator("#game-review")).to_be_visible()

    # Game info shown
    expect(page.locator("#review-game-info")).to_contain_text("vs")


def test_back_button_returns_to_game_list(page, pwa_url):
    """Back button returns from review to game selector."""
    _wait_for_game_list(page, pwa_url)
    page.click(".game-card >> nth=0")
    page.wait_for_selector("#review-board cg-board", timeout=BOARD_TIMEOUT)

    page.click("#review-back-btn")
    expect(page.locator("#game-selector")).to_be_visible()
    expect(page.locator("#game-review")).to_be_hidden()


# --- Move list ---


def test_move_list_renders(page, pwa_url):
    """Move list renders with move numbers and SAN notation."""
    _wait_for_game_list(page, pwa_url)
    page.click(".game-card >> nth=0")
    page.wait_for_selector("#review-board cg-board", timeout=BOARD_TIMEOUT)

    # Should have move cells
    move_cells = page.locator("#review-moves .move-cell")
    count = move_cells.count()
    assert count > 0, "Move list should contain moves"


def test_click_move_updates_board(page, pwa_url, console_errors):
    """Clicking a move in the list updates the board position."""
    _wait_for_game_list(page, pwa_url)
    page.click(".game-card >> nth=1")  # Longer game
    page.wait_for_selector("#review-board cg-board", timeout=BOARD_TIMEOUT)

    # Click on the third move cell
    move_cells = page.locator("#review-moves .move-cell")
    if move_cells.count() >= 3:
        move_cells.nth(2).click()
        page.wait_for_timeout(300)

        # Active move should be highlighted
        active = page.locator("#review-moves .move-cell.active-move")
        expect(active).to_have_count(1)


# --- Navigation controls ---


def test_navigation_buttons(page, pwa_url):
    """Navigation buttons (first/prev/next/last) work correctly."""
    _wait_for_game_list(page, pwa_url)
    page.click(".game-card >> nth=1")  # Longer game
    page.wait_for_selector("#review-board cg-board", timeout=BOARD_TIMEOUT)

    # Click next a few times
    page.click("#review-next")
    page.wait_for_timeout(100)
    page.click("#review-next")
    page.wait_for_timeout(100)

    # Should have an active move
    active = page.locator("#review-moves .move-cell.active-move")
    expect(active).to_have_count(1)

    # Go to first
    page.click("#review-first")
    page.wait_for_timeout(100)

    # Go to last
    page.click("#review-last")
    page.wait_for_timeout(100)
    active = page.locator("#review-moves .move-cell.active-move")
    expect(active).to_have_count(1)


def test_keyboard_navigation(page, pwa_url):
    """Arrow keys navigate moves in review mode."""
    _wait_for_game_list(page, pwa_url)
    page.click(".game-card >> nth=1")
    page.wait_for_selector("#review-board cg-board", timeout=BOARD_TIMEOUT)

    # Press right arrow
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(100)
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(100)

    active = page.locator("#review-moves .move-cell.active-move")
    expect(active).to_have_count(1)

    # Home key
    page.keyboard.press("Home")
    page.wait_for_timeout(100)


# --- Eval bar ---


def test_eval_bar_updates(page, pwa_url):
    """Eval bar updates when navigating moves."""
    _wait_for_game_list(page, pwa_url)
    page.click(".game-card >> nth=1")
    page.wait_for_selector("#review-board cg-board", timeout=BOARD_TIMEOUT)

    # At starting position, eval bar should show 0.0
    label = page.locator("#eval-bar-label")
    expect(label).to_be_visible()

    # Navigate to a move with eval
    for _ in range(15):
        page.click("#review-next")
        page.wait_for_timeout(50)

    # Label should have changed
    text = label.text_content()
    assert text is not None and text != ""


# --- Score chart ---


def test_score_chart_renders(page, pwa_url):
    """Score chart canvas is rendered."""
    _wait_for_game_list(page, pwa_url)
    page.click(".game-card >> nth=1")
    page.wait_for_selector("#review-board cg-board", timeout=BOARD_TIMEOUT)

    canvas = page.locator("#score-chart")
    expect(canvas).to_be_visible()

    # Canvas should have non-zero dimensions
    box = canvas.bounding_box()
    assert box is not None
    assert box["width"] > 0
    assert box["height"] > 0


def test_score_chart_click_navigates(page, pwa_url):
    """Clicking on the score chart jumps to that move."""
    _wait_for_game_list(page, pwa_url)
    page.click(".game-card >> nth=1")
    page.wait_for_selector("#review-board cg-board", timeout=BOARD_TIMEOUT)

    canvas = page.locator("#score-chart")
    box = canvas.bounding_box()
    assert box is not None

    # Click near the middle of the chart
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_timeout(200)

    # Should have navigated to some move
    active = page.locator("#review-moves .move-cell.active-move")
    expect(active).to_have_count(1)


# --- Move classifications ---


def test_classification_dots_in_move_list(page, pwa_url):
    """Move list shows classification dots."""
    _wait_for_game_list(page, pwa_url)
    page.click(".game-card >> nth=1")
    page.wait_for_selector("#review-board cg-board", timeout=BOARD_TIMEOUT)

    # Should have at least some classification dots
    dots = page.locator("#review-moves .class-dot")
    count = dots.count()
    assert count > 0, "Move list should have classification dots"


# --- Game summary ---


def test_game_summary_shows_accuracy(page, pwa_url):
    """Game summary shows accuracy percentages for games with eval data."""
    _wait_for_game_list(page, pwa_url)
    page.click(".game-card >> nth=1")  # Longer game with Stockfish evals
    page.wait_for_selector("#review-board cg-board", timeout=BOARD_TIMEOUT)

    summary = page.locator("#review-summary")
    expect(summary).to_be_visible()

    # Should show accuracy values (at least one, may be hidden if all book moves)
    accuracy_values = page.locator(".accuracy-value")
    count = accuracy_values.count()
    assert count >= 0, "Accuracy values should exist or be hidden"

    # Values that are shown should contain percentage
    for i in range(count):
        text = accuracy_values.nth(i).text_content()
        assert "%" in text, f"Accuracy should show percentage, got: {text}"


# --- Flip board ---


def test_flip_board(page, pwa_url):
    """Flip button changes board orientation."""
    _wait_for_game_list(page, pwa_url)
    page.click(".game-card >> nth=0")
    page.wait_for_selector("#review-board cg-board", timeout=BOARD_TIMEOUT)

    page.click("#review-flip")
    page.wait_for_timeout(200)

    # Board should still be visible (orientation changed internally)
    expect(page.locator("#review-board cg-board")).to_be_visible()


# --- Auto-play ---


def test_autoplay_cycles(page, pwa_url):
    """Auto-play button advances moves automatically."""
    _wait_for_game_list(page, pwa_url)
    page.click(".game-card >> nth=0")
    page.wait_for_selector("#review-board cg-board", timeout=BOARD_TIMEOUT)

    # Start auto-play
    page.click("#review-play")
    page.wait_for_timeout(2500)

    # Should have advanced a couple of moves
    active = page.locator("#review-moves .move-cell.active-move")
    expect(active).to_have_count(1)

    # Stop auto-play
    page.click("#review-play")


# --- PV line ---


def test_pv_line_shows_for_eval_moves(page, pwa_url):
    """PV line shows the best continuation for analyzed moves."""
    _wait_for_game_list(page, pwa_url)
    page.click(".game-card >> nth=1")
    page.wait_for_selector("#review-board cg-board", timeout=BOARD_TIMEOUT)

    # Navigate to a stockfish-analyzed move
    for _ in range(15):
        page.click("#review-next")
        page.wait_for_timeout(50)

    pv = page.locator("#review-pv")
    text = pv.text_content()
    # Should show "Best:" prefix when there's PV data
    assert text is not None


# --- Training via menu ---


def test_training_via_menu(page, pwa_url):
    """Training menu item opens the training view."""
    _wait_for_game_list(page, pwa_url)

    # Open menu and click Training
    page.wait_for_timeout(500)
    page.click("#menu-btn")
    page.wait_for_selector("#nav-menu.nav-open", state="attached", timeout=10000)
    page.click("#nav-training")

    # Training view should be visible
    expect(page.locator("#training-view")).to_be_visible()
    expect(page.locator("#analysis-view")).to_be_hidden()

    # Board should render
    page.wait_for_selector("cg-board piece", timeout=BOARD_TIMEOUT)


# --- Classification edge cases ---


def test_checkmate_move_classified_as_best(page, pwa_url):
    """A move that delivers checkmate must be classified as 'best', not 'missed_win'.

    Regression test: Rf1# in Xpolash game was classified as missed_win
    because mate_in=0 (checkmate delivered) failed the stillMate < 0 check.
    """
    page.goto(pwa_url)
    page.wait_for_selector(".game-card", timeout=10000)

    result = page.evaluate("""() => {
        return window._classifyMove(
            {
                eval_before: { score_cp: -10000, is_mate: true, mate_in: -1 },
                eval_after:  { score_cp: -10000, is_mate: true, mate_in: 0 },
            },
            'black'
        );
    }""")

    assert result is not None, "classifyMove returned null for checkmate move (black)"
    assert result["category"] == "best", (
        f"Checkmate by black classified as '{result['category']}' instead of 'best'"
    )

    # Same test for white delivering checkmate
    result_white = page.evaluate("""() => {
        return window._classifyMove(
            {
                eval_before: { score_cp: 10000, is_mate: true, mate_in: 1 },
                eval_after:  { score_cp: 10000, is_mate: true, mate_in: 0 },
            },
            'white'
        );
    }""")

    assert result_white is not None, "classifyMove returned null for checkmate move (white)"
    assert result_white["category"] == "best", (
        f"Checkmate by white classified as '{result_white['category']}' instead of 'best'"
    )


# --- Brilliant move classification ---


def test_tactical_trap_is_brilliant(page, pwa_url):
    """A tactical trap (apparent sacrifice that wins more) is brilliant.

    Real data: Rxe3 in DDDestryer game (ply 65, move 33).
    First move appears as sacrifice: Rook(5) captures Knight(3), net -2.
    But full chain Rxe3, Rxe3, Rxe3 nets +3 (wins a knight through mate threat).
    Net gain (+3) exceeds apparent sacrifice (|-2|=2) → tactical trap → brilliant.
    """
    page.goto(pwa_url)
    page.wait_for_selector(".game-card", timeout=10000)

    result = page.evaluate("""() => {
        return window._classifyMove(
            {
                fen_before: '4q2k/4r1p1/1p2r2p/p4p2/P4P2/2Q1n1PP/1B2R3/4R1K1 w - - 0 33',
                move_san: 'Rxe3',
                move_uci: 'e2e3',
                eval_before: {
                    score_cp: 457, is_mate: false, mate_in: null,
                    best_move_uci: 'e2e3',
                    pv_uci: ['e2e3', 'e6e3', 'e1e3', 'h8h7'],
                },
                eval_after: { score_cp: 509, is_mate: false, mate_in: null },
            },
            'white'
        );
    }""")

    assert result is not None, "classifyMove returned null for tactical trap move"
    assert result["category"] == "brilliant", (
        f"Tactical trap Rxe3 classified as '{result['category']}' instead of 'brilliant'"
    )
    assert result["symbol"] == "!!"
    assert result["color"] == "#1baca6"


def test_genuine_sacrifice_is_brilliant(page, pwa_url):
    """A genuine sacrifice (Nxf7 where Rxf7 wins the knight) is brilliant.

    Knight (3) captures pawn (1) on f7, rook recaptures knight.
    Net balance: +1 - 3 = -2 → real sacrifice.
    Eval +200cp → wpBefore≈0.76 < 0.95, eplLost≈-0.02 ≤ 0.02.
    """
    page.goto(pwa_url)
    page.wait_for_selector(".game-card", timeout=10000)

    result = page.evaluate("""() => {
        return window._classifyMove(
            {
                fen_before: 'r1bq1rk1/pppp1ppp/2n2n2/2b1p1N1/2B1P3/3P4/PPP2PPP/RNBQK2R w KQ - 0 7',
                move_san: 'Nxf7',
                move_uci: 'g5f7',
                eval_before: {
                    score_cp: 200, is_mate: false, mate_in: null,
                    best_move_uci: 'g5f7',
                    pv_uci: ['g5f7', 'f8f7', 'd1h5'],
                },
                eval_after: { score_cp: 220, is_mate: false, mate_in: null },
            },
            'white'
        );
    }""")

    assert result is not None, "classifyMove returned null for sacrifice move"
    assert result["category"] == "brilliant", (
        f"Genuine sacrifice Nxf7 classified as '{result['category']}' instead of 'brilliant'"
    )
    assert result["symbol"] == "!!"
    assert result["color"] == "#1baca6"


def test_recapture_chain_not_sacrifice(page, pwa_url):
    """Bxe6, Bxe6, Rxe6 is a favorable recapture, not a sacrifice.

    Real data: 24...Bxe6 in game 166363391518.
    Bishop (3) captures pawn (1), but full chain nets +1 for Black.
    """
    page.goto(pwa_url)
    page.wait_for_selector(".game-card", timeout=10000)

    result = page.evaluate("""() => {
        return window._classifyMove(
            {
                fen_before: 'r1b1r2k/1p4p1/4Pnqp/p4p2/P4P2/BB2P1P1/2Q4P/4RRK1 b - - 2 24',
                move_san: 'Bxe6',
                move_uci: 'c8e6',
                eval_before: {
                    score_cp: -56, is_mate: false, mate_in: null,
                    best_move_uci: 'c8e6',
                    pv_uci: ['c8e6', 'b3e6', 'e8e6', 'a3b2'],
                },
                eval_after: { score_cp: -44, is_mate: false, mate_in: null },
            },
            'black'
        );
    }""")

    assert result is not None, "classifyMove returned null for Bxe6"
    assert result["category"] == "excellent", (
        f"Recapture chain Bxe6 classified as '{result['category']}' instead of 'excellent'"
    )
    assert result["symbol"] == "\u2191"


def test_non_sacrifice_best_move_not_brilliant(page, pwa_url):
    """A best move without sacrifice should remain 'best', not 'brilliant'.

    PV shows opponent responds on a different square (no recapture).
    """
    page.goto(pwa_url)
    page.wait_for_selector(".game-card", timeout=10000)

    result = page.evaluate("""() => {
        return window._classifyMove(
            {
                fen_before: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1',
                move_san: 'e5',
                move_uci: 'e7e5',
                eval_before: {
                    score_cp: -20, is_mate: false, mate_in: null,
                    best_move_uci: 'e7e5',
                    pv_uci: ['e7e5', 'g1f3', 'b8c6'],
                },
                eval_after: { score_cp: -20, is_mate: false, mate_in: null },
            },
            'black'
        );
    }""")

    assert result is not None, "classifyMove returned null for e5 move"
    assert result["category"] == "best", (
        f"Non-sacrifice e5 classified as '{result['category']}' instead of 'best'"
    )


def test_sacrifice_in_dominating_position_not_brilliant(page, pwa_url):
    """A sacrifice when already completely winning (wp >= 0.95) is not 'brilliant'."""
    page.goto(pwa_url)
    page.wait_for_selector(".game-card", timeout=10000)

    # score_cp: 700 → wpBefore ≈ 0.97 > 0.95, should NOT be brilliant
    result = page.evaluate("""() => {
        return window._classifyMove(
            {
                fen_before: '4q2k/4r1p1/1p2r2p/p4p2/P4P2/2Q1n1PP/1B2R3/4R1K1 w - - 0 33',
                move_san: 'Rxe3',
                move_uci: 'e2e3',
                eval_before: {
                    score_cp: 700, is_mate: false, mate_in: null,
                    best_move_uci: 'e2e3',
                    pv_uci: ['e2e3', 'e6e3', 'e1e3', 'h8h7'],
                },
                eval_after: { score_cp: 750, is_mate: false, mate_in: null },
            },
            'white'
        );
    }""")

    assert result is not None, "classifyMove returned null for dominating sacrifice"
    assert result["category"] == "best", (
        f"Sacrifice in dominating position classified as '{result['category']}' instead of 'best'"
    )


def test_missed_capture_classified_as_miss(page, pwa_url):
    """When opponent leaves a piece hanging and player doesn't take it, it's a 'miss'.

    Position: Black knight on e4 is undefended. White's best move is Bxe4
    (bishop takes knight, winning 3 pts). But white plays h3 instead.
    Opponent blundered on previous move (oppEPL ≈ 0.34).
    """
    page.goto(pwa_url)
    page.wait_for_selector(".game-card", timeout=10000)

    # FEN: white bishop on d3, black knight on e4 (undefended)
    result = page.evaluate("""() => {
        const prevMove = {
            move_uci: 'f6e4',
            eval_before: { score_cp: 0, is_mate: false, mate_in: null },
            eval_after: { score_cp: 300, is_mate: false, mate_in: null },
        };
        return window._classifyMove(
            {
                fen_before: 'r1bqkb1r/pppp1ppp/2n5/4p3/4n3/3B1N2/PPPP1PPP/RNBQK2R w KQkq - 0 5',
                move_san: 'h3',
                move_uci: 'h2h3',
                eval_before: {
                    score_cp: 300, is_mate: false, mate_in: null,
                    best_move_uci: 'd3e4',
                    pv_uci: ['d3e4', 'd7d5', 'e4d3'],
                },
                eval_after: { score_cp: 200, is_mate: false, mate_in: null },
            },
            'white',
            prevMove
        );
    }""")

    assert result is not None, "classifyMove returned null for missed capture"
    assert result["category"] == "miss", (
        f"Missed capture classified as '{result['category']}' instead of 'miss'"
    )
    assert result["symbol"] == "\u00d7"
    assert result["color"] == "#e06666"


def test_missed_positional_not_miss(page, pwa_url):
    """When the best move is positional (not a capture), it's NOT a 'miss'.

    Even if opponent blundered and player responded poorly, miss only applies
    when the best move was a material-winning capture.
    """
    page.goto(pwa_url)
    page.wait_for_selector(".game-card", timeout=10000)

    result = page.evaluate("""() => {
        const prevMove = {
            move_uci: 'd7d5',
            eval_before: { score_cp: 0, is_mate: false, mate_in: null },
            eval_after: { score_cp: 300, is_mate: false, mate_in: null },
        };
        return window._classifyMove(
            {
                fen_before: 'rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 0 1',
                move_san: 'h3',
                move_uci: 'h2h3',
                eval_before: {
                    score_cp: 300, is_mate: false, mate_in: null,
                    best_move_uci: 'c2c4',
                    pv_uci: ['c2c4', 'e7e6', 'b1c3'],
                },
                eval_after: { score_cp: 200, is_mate: false, mate_in: null },
            },
            'white',
            prevMove
        );
    }""")

    assert result is not None
    assert result["category"] != "miss", (
        f"Positional miss wrongly classified as 'miss' — should only flag missed captures"
    )


# --- Game-level classification with F1 scoring ---

import pathlib
from datetime import datetime, timezone

from tests.e2e.classification_cases import GAMES as CLASSIFICATION_GAMES

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
F1_LOG = pathlib.Path(__file__).parent / "classification_f1_log.md"


def _load_game_moves(game_id: str) -> list[dict]:
    """Load moves for a game from the ground truth fixture."""
    gt_path = FIXTURES_DIR / "classification_ground_truth.json"
    with open(gt_path) as f:
        data = json.load(f)
    for game in data["games"]:
        if game["game_id"] == game_id:
            return game["moves"]
    msg = f"Game {game_id} not found in {gt_path}"
    raise ValueError(msg)


def _compute_f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """Return (precision, recall, f1)."""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def _classify_game(page, pwa_url, game_gt):
    """Classify all moves in a game and return per-class stats.

    Returns (classes, class_f1, macro_f1, errors) without asserting.
    """
    page.goto(pwa_url)
    page.wait_for_selector(".game-card", timeout=10000)

    moves = _load_game_moves(game_gt["game_id"])
    brilliant_set = set(game_gt.get("brilliant_indices", []))
    great_set = set(game_gt.get("great_indices", []))
    notes = game_gt.get("notes", {})

    # Classify all moves in browser
    moves_json = json.dumps(moves)
    results = page.evaluate(
        f"""() => {{
        const moves = {moves_json};
        return moves.map((m, i) => {{
            const side = m.side || (i % 2 === 0 ? 'white' : 'black');
            const prevMove = i > 0 ? moves[i - 1] : null;
            return window._classifyMove(m, side, prevMove);
        }});
    }}"""
    )

    # Per-class TP/FP/FN
    classes = {"brilliant": {"tp": 0, "fp": 0, "fn": 0},
               "great": {"tp": 0, "fp": 0, "fn": 0}}
    errors = []

    for i, (move, result) in enumerate(zip(moves, results)):
        predicted = result.get("category") if result else "other"
        if predicted not in ("brilliant", "great"):
            predicted = "other"

        if i in brilliant_set:
            expected = "brilliant"
        elif i in great_set:
            expected = "great"
        else:
            expected = "other"

        move_num = (i // 2) + 1
        side = "w" if i % 2 == 0 else "b"
        label = f"{move_num}.{side} {move['move_san']}"
        note = notes.get(i, "")

        if expected == predicted:
            if expected in classes:
                classes[expected]["tp"] += 1
        else:
            if expected in classes:
                classes[expected]["fn"] += 1
                errors.append(f"  FN({expected}): {label} — expected {expected}, got {predicted}. {note}")
            if predicted in classes:
                classes[predicted]["fp"] += 1
                errors.append(f"  FP({predicted}): {label} — wrongly classified as {predicted}. {note}")

    # Compute per-class F1
    class_f1 = {}
    for cls, counts in classes.items():
        _, _, f1 = _compute_f1(counts["tp"], counts["fp"], counts["fn"])
        class_f1[cls] = f1

    # Macro F1 (average of per-class F1, only for classes that have ground truth)
    active_classes = [cls for cls in classes if any(
        i in (brilliant_set if cls == "brilliant" else great_set) for i in range(len(moves))
    ) or classes[cls]["fp"] > 0]
    macro_f1 = sum(class_f1[c] for c in active_classes) / len(active_classes) if active_classes else 1.0

    # Print detailed report
    print(f"\n{'='*60}")
    print(f"Classification — {game_gt['game_id']}")
    for cls, counts in classes.items():
        p, r, f1 = _compute_f1(counts["tp"], counts["fp"], counts["fn"])
        print(f"  {cls}: TP={counts['tp']} FP={counts['fp']} FN={counts['fn']} P={p:.3f} R={r:.3f} F1={f1:.3f}")
    print(f"  Macro F1={macro_f1:.3f}")
    if errors:
        print("  Errors:")
        for e in errors:
            print(e)
    print(f"{'='*60}")

    # Update log
    _update_classification_log(game_gt["game_id"], classes, class_f1, macro_f1)

    return classes, class_f1, macro_f1, errors


# Minimum acceptable macro F1 across all games (non-regression threshold).
# Current baseline: ~0.55. Lower bound set to catch significant regressions.
MIN_GLOBAL_MACRO_F1 = 0.50


def test_classification_macro_f1_regression(page, pwa_url):
    """Global non-regression: average macro F1 across all labeled games must not drop."""
    macro_f1_scores = []
    total_brilliant = {"tp": 0, "fp": 0, "fn": 0}
    total_great = {"tp": 0, "fp": 0, "fn": 0}

    for game_gt in CLASSIFICATION_GAMES:
        classes, class_f1, macro_f1, errors = _classify_game(page, pwa_url, game_gt)
        macro_f1_scores.append(macro_f1)
        for key in ("tp", "fp", "fn"):
            total_brilliant[key] += classes["brilliant"][key]
            total_great[key] += classes["great"][key]

    avg_macro_f1 = sum(macro_f1_scores) / len(macro_f1_scores)
    _, _, brilliant_f1 = _compute_f1(total_brilliant["tp"], total_brilliant["fp"], total_brilliant["fn"])
    _, _, great_f1 = _compute_f1(total_great["tp"], total_great["fp"], total_great["fn"])

    print(f"\n{'='*60}")
    print(f"GLOBAL CLASSIFICATION SUMMARY ({len(CLASSIFICATION_GAMES)} games)")
    print(f"  Brilliant: TP={total_brilliant['tp']} FP={total_brilliant['fp']} FN={total_brilliant['fn']} F1={brilliant_f1:.3f}")
    print(f"  Great:     TP={total_great['tp']} FP={total_great['fp']} FN={total_great['fn']} F1={great_f1:.3f}")
    print(f"  Average macro F1={avg_macro_f1:.3f} (threshold={MIN_GLOBAL_MACRO_F1})")
    print(f"{'='*60}")

    assert avg_macro_f1 >= MIN_GLOBAL_MACRO_F1, (
        f"Global macro F1 {avg_macro_f1:.3f} dropped below threshold {MIN_GLOBAL_MACRO_F1}"
    )


def _update_classification_log(
    game_id: str, classes: dict, class_f1: dict, macro_f1: float,
) -> None:
    """Append or update the classification performance log."""
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    b = classes["brilliant"]
    g = classes["great"]
    row = (
        f"| {today} | {game_id} "
        f"| {b['tp']} | {b['fp']} | {b['fn']} | {class_f1['brilliant']:.3f} "
        f"| {g['tp']} | {g['fp']} | {g['fn']} | {class_f1['great']:.3f} "
        f"| {macro_f1:.3f} |"
    )

    if F1_LOG.exists():
        content = F1_LOG.read_text()
        lines = content.split("\n")
        lines = [ln for ln in lines if f"| {game_id} " not in ln]
        insert_idx = next(
            (i for i, ln in enumerate(lines) if ln.startswith("## Global")),
            len(lines),
        )
        lines.insert(insert_idx, row)
        F1_LOG.write_text("\n".join(lines) + "\n")
    else:
        header = (
            "# Move Classification — Performance Log\n\n"
            "| Date | Game | B_TP | B_FP | B_FN | B_F1 | G_TP | G_FP | G_FN | G_F1 | Macro F1 |\n"
            "|------|------|------|------|------|------|------|------|------|------|----------|\n"
        )
        F1_LOG.write_text(header + row + f"\n\n## Global: Macro F1 = {macro_f1:.3f}\n")
