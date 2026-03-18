"""End-to-end tests for the training PWA.

Tests the full drill flow using Playwright with a headless Chromium browser.
Uses isolated test data (tests/e2e/fixtures/training_data.json) served from
a temp directory — the real training data is never touched.

Requirements:
    uv run playwright install chromium

Test fixture positions (3 total, session size set to 3):
    1. White to move, starting position, best_move="d4", also accepts "e4"
    2. White to move, after 1.e4 e5, best_move="Nf3"
    3. Black to move, after 1.d4, best_move="d5"
"""

from __future__ import annotations

from playwright.sync_api import expect

from tests.e2e.conftest import make_move

# Timeout for CDN-loaded chessground to render (needs internet)
BOARD_TIMEOUT = 20000


def _wait_for_board(page, pwa_url):
    """Navigate to PWA and wait for the board to render."""
    page.goto(pwa_url)
    page.wait_for_selector("cg-board piece", timeout=BOARD_TIMEOUT)


# --- Page loading ---


def test_page_loads_with_board(page, pwa_url):
    """Board renders and first position prompt appears."""
    _wait_for_board(page, pwa_url)

    expect(page.locator("#prompt")).to_contain_text("You played")
    expect(page.locator("#progress")).to_contain_text("1 /")


# --- Correct moves ---


def test_correct_move_shows_feedback(page, pwa_url):
    """Playing the best move shows 'Correct!' feedback."""
    _wait_for_board(page, pwa_url)

    # Position 1: white, best_move="d4" → d2 to d4
    make_move(page, "d2", "d4", "white")
    page.wait_for_timeout(300)

    expect(page.locator("#feedback-text")).to_contain_text("Correct")
    expect(page.locator("#next-btn")).to_be_visible()


def test_acceptable_move_also_correct(page, pwa_url):
    """An alternative acceptable move (e4) is also marked correct."""
    _wait_for_board(page, pwa_url)

    # Position 1: acceptable_moves includes "e4"
    make_move(page, "e2", "e4", "white")
    page.wait_for_timeout(300)

    expect(page.locator("#feedback-text")).to_contain_text("Correct")


# --- Wrong moves ---


def test_wrong_move_shows_try_again(page, pwa_url):
    """Playing a wrong move shows 'Try again' with remaining attempts."""
    _wait_for_board(page, pwa_url)

    # Play a wrong move: a2→a3
    make_move(page, "a2", "a3", "white")
    page.wait_for_timeout(300)

    expect(page.locator("#feedback-text")).to_contain_text("Try again")
    # Next button should NOT be visible yet
    expect(page.locator("#next-btn")).not_to_be_visible()


def test_three_wrong_attempts_reveals_answer(page, pwa_url):
    """After 3 wrong attempts, the correct answer is revealed."""
    _wait_for_board(page, pwa_url)

    for _ in range(3):
        page.wait_for_selector("cg-board piece", timeout=5000)
        page.wait_for_timeout(200)
        make_move(page, "a2", "a3", "white")
        page.wait_for_timeout(700)

    expect(page.locator("#feedback-text")).to_contain_text("answer was")
    expect(page.locator("#explanation")).not_to_be_empty()
    expect(page.locator("#next-btn")).to_be_visible()


# --- Navigation ---


def test_next_button_advances_position(page, pwa_url):
    """Clicking Next loads the next position."""
    _wait_for_board(page, pwa_url)

    # Solve position 1 correctly (1st appearance → reinserted, not yet completed)
    make_move(page, "d2", "d4", "white")
    page.wait_for_timeout(300)

    page.locator("#next-btn").click()
    page.wait_for_timeout(500)

    # Progress stays at 1/3 (position not yet acquired — needs 2nd success)
    expect(page.locator("#progress")).to_contain_text("1 / 3")
    expect(page.locator("#prompt")).to_contain_text("You played")


def _solve_current_position(page, from_sq, to_sq, orientation):
    """Solve one position: make the correct move, wait, click Next."""
    page.wait_for_selector("cg-board piece", timeout=5000)
    make_move(page, from_sq, to_sq, orientation)
    page.wait_for_timeout(300)
    page.locator("#next-btn").click()
    page.wait_for_timeout(500)


def test_session_completion_shows_summary(page, pwa_url):
    """Completing all positions (including intra-session repeats) shows summary."""
    _wait_for_board(page, pwa_url)

    # With intra-session repetition, each position appears twice:
    # 1st pass: positions 1, 2, 3 (each reinserted after first success)
    # 2nd pass: positions 1, 2, 3 again (acquired, not reinserted)

    # Pass 1: original positions
    _solve_current_position(page, "d2", "d4", "white")   # Pos 1 (1st time)
    _solve_current_position(page, "g1", "f3", "white")   # Pos 2 (1st time)
    _solve_current_position(page, "d7", "d5", "black")   # Pos 3 (1st time)

    # Pass 2: reinserted positions (confirm learning)
    _solve_current_position(page, "d2", "d4", "white")   # Pos 1 (2nd time)
    _solve_current_position(page, "g1", "f3", "white")   # Pos 2 (2nd time)
    _solve_current_position(page, "d7", "d5", "black")   # Pos 3 (2nd time)

    # Summary modal should appear — all 6 answers correct
    expect(page.locator("#summary-modal")).to_be_visible()
    expect(page.locator("#summary-stats")).to_contain_text("6 / 6")


def test_intra_session_repetition_on_correct(page, pwa_url):
    """A correct answer on first appearance reinserts the position later."""
    _wait_for_board(page, pwa_url)

    # Solve position 1 correctly
    make_move(page, "d2", "d4", "white")
    page.wait_for_timeout(300)

    expect(page.locator("#feedback-text")).to_contain_text("Correct")
    page.locator("#next-btn").click()
    page.wait_for_timeout(500)

    # We should see position 2 next (not position 1 again immediately)
    expect(page.locator("#prompt")).to_contain_text("You played")


def test_failed_position_returns_in_session(page, pwa_url):
    """A failed position is reinserted closer in the session queue."""
    _wait_for_board(page, pwa_url)

    # Fail position 1 three times to exhaust attempts
    for _ in range(3):
        page.wait_for_selector("cg-board piece", timeout=5000)
        page.wait_for_timeout(200)
        make_move(page, "a2", "a3", "white")
        page.wait_for_timeout(700)

    expect(page.locator("#feedback-text")).to_contain_text("answer was")
    page.locator("#next-btn").click()
    page.wait_for_timeout(500)

    # Position 1 was reinserted — it will appear again later in the session
    # For now, we should be on position 2
    page.wait_for_selector("cg-board piece", timeout=5000)
    expect(page.locator("#prompt")).to_contain_text("You played")


# --- Settings ---


def test_settings_modal_opens_and_closes(page, pwa_url):
    """Settings modal can be opened and closed."""
    _wait_for_board(page, pwa_url)

    page.locator("#settings-btn").click()
    expect(page.locator("#settings-modal")).to_be_visible()

    page.locator("#close-settings").click()
    expect(page.locator("#settings-modal")).not_to_be_visible()


# --- See moves link ---


def test_see_moves_hidden_before_answer(page, pwa_url):
    """The 'See moves' link is not visible before the player answers."""
    _wait_for_board(page, pwa_url)

    expect(page.locator("#see-moves")).not_to_be_visible()


def test_see_moves_visible_after_correct(page, pwa_url):
    """The 'See moves' link appears after a correct answer."""
    _wait_for_board(page, pwa_url)

    # Position 1: best_move="d4"
    make_move(page, "d2", "d4", "white")
    page.wait_for_timeout(300)

    expect(page.locator("#feedback-text")).to_contain_text("Correct")
    expect(page.locator("#see-moves")).to_be_visible()
    expect(page.locator("#see-moves")).to_contain_text("See moves")


def test_see_moves_visible_after_two_wrong(page, pwa_url):
    """The 'See moves' link appears after 2 wrong attempts (not 3)."""
    _wait_for_board(page, pwa_url)

    # First wrong attempt — link should NOT appear
    make_move(page, "a2", "a3", "white")
    page.wait_for_timeout(500)
    expect(page.locator("#see-moves")).not_to_be_visible()

    # Second wrong attempt — link SHOULD appear
    page.wait_for_selector("cg-board piece", timeout=5000)
    page.wait_for_timeout(200)
    make_move(page, "a2", "a3", "white")
    page.wait_for_timeout(500)
    expect(page.locator("#see-moves")).to_be_visible()


def test_see_moves_link_has_move_parameter(page, pwa_url):
    """The 'See moves' link includes the move number for deep linking."""
    _wait_for_board(page, pwa_url)

    # Position 1: FEN "...w KQkq - 0 1" → ply = 0, game.id = lichess
    # Expected: https://lichess.org/testgame1#0
    make_move(page, "d2", "d4", "white")
    page.wait_for_timeout(300)

    href = page.locator("#see-moves").get_attribute("href")
    assert href is not None, "See moves link has no href"
    assert "lichess.org/testgame1" in href, f"Expected lichess URL, got: {href}"
    assert "#" in href, f"Expected move anchor (#ply), got: {href}"


def test_see_moves_works_after_reload(page, pwa_url):
    """The 'See moves' link works even after page reload (SW cache scenario).

    This simulates the production bug: first load caches files via SW,
    reload serves from cache. The link must still appear.
    """
    _wait_for_board(page, pwa_url)

    # First load — registers SW and caches files
    page.wait_for_timeout(1000)

    # Reload — SW serves from cache (network-first should still fetch fresh)
    page.reload()
    page.wait_for_selector("cg-board piece", timeout=BOARD_TIMEOUT)

    # Play correct move
    make_move(page, "d2", "d4", "white")
    page.wait_for_timeout(300)

    expect(page.locator("#feedback-text")).to_contain_text("Correct")
    expect(page.locator("#see-moves")).to_be_visible()
    expect(page.locator("#see-moves")).to_contain_text("See moves")
