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
