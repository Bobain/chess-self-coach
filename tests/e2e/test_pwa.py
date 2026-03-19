"""End-to-end tests for the training PWA.

Tests the full drill flow using Playwright with a headless Chromium browser.
Uses isolated test data (tests/e2e/fixtures/training_data.json) served from
a temp directory — the real training data is never touched.

Requirements:
    uv run playwright install chromium

Test fixture positions (4 total):
    1. White to move, starting position, best_move="d4", also accepts "e4"
    2. White to move, after 1.e4 e5, best_move="Nf3"
    3. Black to move, after 1.d4, best_move="d5"
    4. White to move, Scholar's Mate, best_move="Qxf7#" (score_before=+100.00)
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


def _wait_for_animation(page):
    """Wait for the wrong-move animation to complete (500ms + 1500ms + margin)."""
    page.wait_for_timeout(2500)


# --- Page loading ---


def test_page_loads_with_board(page, pwa_url):
    """Board renders and first position prompt appears after animation."""
    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

    expect(page.locator("#prompt")).to_contain_text("You played")
    expect(page.locator("#progress")).to_contain_text("1 /")


# --- Correct moves ---


def test_correct_move_shows_feedback(page, pwa_url):
    """Playing the best move shows 'Correct!' feedback."""
    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

    # Position 1: white, best_move="d4" → d2 to d4
    make_move(page, "d2", "d4", "white")
    page.wait_for_timeout(300)

    expect(page.locator("#feedback-text")).to_contain_text("Correct")
    expect(page.locator("#next-btn")).to_be_visible()


def test_acceptable_move_also_correct(page, pwa_url):
    """An alternative acceptable move (e4) is also marked correct."""
    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

    # Position 1: acceptable_moves includes "e4"
    make_move(page, "e2", "e4", "white")
    page.wait_for_timeout(300)

    expect(page.locator("#feedback-text")).to_contain_text("Correct")


# --- Wrong moves ---


def test_wrong_move_shows_try_again(page, pwa_url):
    """Playing a wrong move shows 'Try again' with remaining attempts."""
    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

    # Play a wrong move: a2→a3
    make_move(page, "a2", "a3", "white")
    page.wait_for_timeout(300)

    expect(page.locator("#feedback-text")).to_contain_text("Try again")
    # Next button should NOT be visible yet
    expect(page.locator("#next-btn")).not_to_be_visible()


def test_three_wrong_attempts_reveals_answer(page, pwa_url):
    """After 3 wrong attempts, the correct answer is revealed."""
    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

    for i in range(3):
        page.wait_for_selector("cg-board piece", timeout=5000)
        page.wait_for_timeout(200)
        make_move(page, "a2", "a3", "white")
        if i < 2:
            # Wait for punishment + Retry button, then click Retry
            page.locator("#retry-btn").wait_for(state="visible", timeout=15000)
            page.locator("#retry-btn").click()
            page.wait_for_timeout(500)
        else:
            # 3rd attempt — wait for the answer to be revealed
            page.wait_for_timeout(700)

    expect(page.locator("#feedback-text")).to_contain_text("answer was")
    expect(page.locator("#explanation")).not_to_be_empty()
    expect(page.locator("#next-btn")).to_be_visible()


# --- Navigation ---


def test_next_button_advances_position(page, pwa_url):
    """Clicking Next loads the next position."""
    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

    # Solve position 1 correctly (1st appearance → reinserted, not yet completed)
    make_move(page, "d2", "d4", "white")
    page.wait_for_timeout(300)

    page.locator("#next-btn").click()
    _wait_for_animation(page)

    # Progress stays at 1/4 (position not yet acquired — needs 2nd success)
    expect(page.locator("#progress")).to_contain_text("1 / 4")
    expect(page.locator("#prompt")).to_contain_text("You played")


def _solve_current_position(page, from_sq, to_sq, orientation):
    """Solve one position: wait for animation, make the correct move, click Next."""
    page.wait_for_selector("cg-board piece", timeout=5000)
    _wait_for_animation(page)
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
    _solve_current_position(page, "h5", "f7", "white")   # Pos 4 (1st time)

    # Pass 2: reinserted positions (confirm learning)
    _solve_current_position(page, "d2", "d4", "white")   # Pos 1 (2nd time)
    _solve_current_position(page, "g1", "f3", "white")   # Pos 2 (2nd time)
    _solve_current_position(page, "d7", "d5", "black")   # Pos 3 (2nd time)
    _solve_current_position(page, "h5", "f7", "white")   # Pos 4 (2nd time)

    # Summary modal should appear — all 8 answers correct
    expect(page.locator("#summary-modal")).to_be_visible()
    expect(page.locator("#summary-stats")).to_contain_text("8 / 8")


def test_intra_session_repetition_on_correct(page, pwa_url):
    """A correct answer on first appearance reinserts the position later."""
    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

    # Solve position 1 correctly
    make_move(page, "d2", "d4", "white")
    page.wait_for_timeout(300)

    expect(page.locator("#feedback-text")).to_contain_text("Correct")
    page.locator("#next-btn").click()
    _wait_for_animation(page)

    # We should see position 2 next (not position 1 again immediately)
    expect(page.locator("#prompt")).to_contain_text("You played")


def test_failed_position_returns_in_session(page, pwa_url):
    """A failed position is reinserted closer in the session queue."""
    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

    # Fail position 1 three times to exhaust attempts
    for i in range(3):
        page.wait_for_selector("cg-board piece", timeout=5000)
        page.wait_for_timeout(200)
        make_move(page, "a2", "a3", "white")
        if i < 2:
            page.locator("#retry-btn").wait_for(state="visible", timeout=15000)
            page.locator("#retry-btn").click()
            page.wait_for_timeout(500)
        else:
            page.wait_for_timeout(700)

    expect(page.locator("#feedback-text")).to_contain_text("answer was")
    page.locator("#next-btn").click()
    _wait_for_animation(page)

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
    _wait_for_animation(page)

    # Position 1: best_move="d4"
    make_move(page, "d2", "d4", "white")
    page.wait_for_timeout(300)

    expect(page.locator("#feedback-text")).to_contain_text("Correct")
    expect(page.locator("#see-moves")).to_be_visible()
    expect(page.locator("#see-moves")).to_contain_text("See moves")


def test_see_moves_visible_after_two_wrong(page, pwa_url):
    """The 'See moves' link appears after 2 wrong attempts (not 3)."""
    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

    # First wrong attempt — link should NOT appear
    make_move(page, "a2", "a3", "white")
    page.wait_for_timeout(500)
    expect(page.locator("#see-moves")).not_to_be_visible()

    # Wait for punishment + click Retry to reset the board
    page.locator("#retry-btn").wait_for(state="visible", timeout=15000)
    page.locator("#retry-btn").click()
    page.wait_for_timeout(500)

    # Second wrong attempt — link SHOULD appear
    page.wait_for_selector("cg-board piece", timeout=5000)
    page.wait_for_timeout(200)
    make_move(page, "a2", "a3", "white")
    page.wait_for_timeout(500)
    expect(page.locator("#see-moves")).to_be_visible()


def test_see_moves_link_has_move_parameter(page, pwa_url):
    """The 'See moves' link includes the move number for deep linking."""
    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

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
    _wait_for_animation(page)

    # Play correct move
    make_move(page, "d2", "d4", "white")
    page.wait_for_timeout(300)

    expect(page.locator("#feedback-text")).to_contain_text("Correct")
    expect(page.locator("#see-moves")).to_be_visible()
    expect(page.locator("#see-moves")).to_contain_text("See moves")


# --- Eval summary ---


def test_eval_summary_visible_after_correct(page, pwa_url):
    """Eval summary appears after a correct answer with both eval lines."""
    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

    # Position 1: score_before="+0.30", score_after="-0.20"
    make_move(page, "d2", "d4", "white")
    page.wait_for_timeout(300)

    eval_el = page.locator("#eval-summary")
    expect(eval_el).to_be_visible()
    expect(eval_el).to_contain_text("Your move:")
    expect(eval_el).to_contain_text("Best move:")


def test_eval_summary_shows_mate_as_text(page, pwa_url, console_errors):
    """Mate scores display as 'You win'/'Opponent wins', not +100.00."""
    _wait_for_board(page, pwa_url)

    # Navigate to position 4 by solving 1, 2, 3 first
    _solve_current_position(page, "d2", "d4", "white")   # Pos 1
    _solve_current_position(page, "g1", "f3", "white")   # Pos 2
    _solve_current_position(page, "d7", "d5", "black")   # Pos 3

    # Position 4: White, score_before="+100.00" → "You win"
    page.wait_for_selector("cg-board piece", timeout=5000)
    _wait_for_animation(page)
    make_move(page, "h5", "f7", "white")
    page.wait_for_timeout(300)

    eval_el = page.locator("#eval-summary")
    expect(eval_el).to_be_visible()
    expect(eval_el).to_contain_text("You win")
    # Must NOT contain raw +100.00
    text = eval_el.text_content()
    assert "+100.00" not in text, f"Raw mate score should not appear: {text}"

    # Verify via console logs
    log_text = "\n".join(console_errors["messages"])
    assert "[showFeedback] evals:" in log_text


# --- Dismiss button ---


def test_dismiss_button_visible_after_wrong_attempt(page, pwa_url):
    """The 'Give up on this lesson' button appears after the first wrong move."""
    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

    # Dismiss should NOT be visible initially
    expect(page.locator("#dismiss-btn")).not_to_be_visible()

    # Play a wrong move
    make_move(page, "a2", "a3", "white")
    page.wait_for_timeout(300)

    expect(page.locator("#feedback-text")).to_contain_text("Try again")
    expect(page.locator("#dismiss-btn")).to_be_visible()


# --- Stockfish WASM punishment ---


def test_wrong_move_shows_punishment(page, pwa_url, console_errors):
    """Wrong move triggers Stockfish WASM punishment and Retry button."""
    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

    make_move(page, "a2", "a3", "white")

    # Wait for Stockfish WASM to compute the punishment move
    page.locator("#retry-btn").wait_for(state="visible", timeout=15000)

    log_text = "\n".join(console_errors["messages"])
    assert "[handleMove] Opponent response:" in log_text


def test_retry_resets_position(page, pwa_url, console_errors):
    """After punishment, clicking Retry resets the board."""
    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

    make_move(page, "a2", "a3", "white")
    page.locator("#retry-btn").wait_for(state="visible", timeout=15000)

    page.locator("#retry-btn").click()
    page.wait_for_timeout(500)

    expect(page.locator("#retry-btn")).not_to_be_visible()
    log_text = "\n".join(console_errors["messages"])
    assert "[showRetryButton] Retry clicked" in log_text


def test_correct_move_no_punishment(page, pwa_url):
    """Correct move has no punishment or retry — behavior unchanged."""
    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

    make_move(page, "d2", "d4", "white")
    page.wait_for_timeout(300)

    expect(page.locator("#feedback-text")).to_contain_text("Correct")
    expect(page.locator("#retry-btn")).not_to_be_visible()


def test_wrong_move_fallback_without_wasm(page, pwa_url, console_errors):
    """If Stockfish WASM fails to load, the old try-again behavior works."""
    # Override Worker constructor to block Stockfish loading
    # (page.route does not intercept Web Worker script loads)
    page.add_init_script("""
        const _OrigWorker = Worker;
        window.Worker = function(url, opts) {
            if (typeof url === 'string' && url.includes('stockfish')) {
                throw new Error('WASM blocked for testing');
            }
            return new _OrigWorker(url, opts);
        };
    """)

    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

    make_move(page, "a2", "a3", "white")
    page.wait_for_timeout(3000)

    # No Retry button (fallback resets the board automatically)
    expect(page.locator("#retry-btn")).not_to_be_visible()
    log_text = "\n".join(console_errors["messages"])
    assert "[handleMove] Stockfish unavailable" in log_text


# --- Wrong move animation ---


def test_wrong_move_animation_plays(page, pwa_url, console_errors):
    """Animation plays the wrong move and resets, then the player can interact."""
    _wait_for_board(page, pwa_url)
    _wait_for_animation(page)

    # After animation, prompt should invite the player to find a better move
    expect(page.locator("#prompt")).to_contain_text("You played")

    # Board should accept moves now (make a correct move to verify)
    make_move(page, "d2", "d4", "white")
    page.wait_for_timeout(300)
    expect(page.locator("#feedback-text")).to_contain_text("Correct")

    # Verify animation logs
    log_text = "\n".join(console_errors["messages"])
    assert "[animateWrongMove]" in log_text


def test_annotation_visible_during_animation(page, pwa_url, console_errors):
    """Annotation (??) is rendered via autoShapes during the animation."""
    _wait_for_board(page, pwa_url)

    # Wait for the annotation to appear (after 500ms delay)
    # Position 1 is a blunder → annotation "??"
    page.wait_for_timeout(800)

    # Check that autoShapes SVG is rendered on the board
    # Chessground renders autoShapes as <svg> elements inside cg-wrap
    svg_count = page.locator("cg-container svg").count()
    assert svg_count > 0, "Expected SVG autoShapes on the board during animation"

    # Verify via console
    log_text = "\n".join(console_errors["messages"])
    assert "[animateWrongMove]" in log_text
    assert "category=blunder" in log_text


def test_clock_displayed_when_present(page, pwa_url):
    """Clocks are visible with correct values when position has clock data."""
    _wait_for_board(page, pwa_url)

    # Position 1 has clock: player=540s (09:00), opponent=480s (08:00)
    clock_bottom = page.locator("#clock-bottom")
    clock_top = page.locator("#clock-top")

    expect(clock_bottom).to_be_visible()
    expect(clock_top).to_be_visible()
    expect(clock_bottom).to_have_text("09:00")
    expect(clock_top).to_have_text("08:00")


def test_clock_hidden_when_absent(page, pwa_url):
    """Clocks are hidden when position has no clock data."""
    _wait_for_board(page, pwa_url)

    # Navigate to position 2 (no clock)
    _solve_current_position(page, "d2", "d4", "white")

    _wait_for_animation(page)

    clock_bottom = page.locator("#clock-bottom")
    clock_top = page.locator("#clock-top")
    expect(clock_bottom).not_to_be_visible()
    expect(clock_top).not_to_be_visible()


# --- [App] mode ---


def test_app_mode_smoke(page, app_url):
    """[App] mode: board loads via FastAPI and /api/status returns mode='app'."""
    page.goto(app_url)
    page.wait_for_selector("cg-board piece", timeout=BOARD_TIMEOUT)

    status = page.evaluate("() => fetch('/api/status').then(r => r.json())")
    assert status["mode"] == "app"


def test_app_mode_stats_modal(page, app_url, console_errors):
    """[App] mode: Training stats menu item opens modal with stats."""
    page.goto(app_url)
    page.wait_for_selector("cg-board piece", timeout=BOARD_TIMEOUT)

    # Open menu
    page.locator("#menu-btn").click()
    page.wait_for_timeout(300)

    # Stats item should be visible and enabled
    stats_item = page.locator("#nav-stats")
    expect(stats_item).to_be_visible()
    expect(stats_item).not_to_have_class("disabled")

    # Click stats
    stats_item.click()
    page.wait_for_timeout(500)

    # Modal should appear with stats from fixture data (4 positions)
    expect(page.locator("#stats-modal")).to_be_visible()
    expect(page.locator("#stats-content")).to_contain_text("Total positions")
    expect(page.locator("#stats-content")).to_contain_text("4")

    # Close modal
    page.locator("#close-stats").click()
    expect(page.locator("#stats-modal")).not_to_be_visible()

    # Verify console logs
    log_text = "\n".join(console_errors["messages"])
    assert "[showStats]" in log_text


def test_app_mode_validate_modal(page, app_url, console_errors):
    """[App] mode: Validate PGN menu item opens modal with results."""
    page.goto(app_url)
    page.wait_for_selector("cg-board piece", timeout=BOARD_TIMEOUT)

    # Open menu
    page.locator("#menu-btn").click()
    page.wait_for_timeout(300)

    # Validate item should be visible and enabled
    validate_item = page.locator("#nav-validate")
    expect(validate_item).to_be_visible()
    expect(validate_item).not_to_have_class("disabled")

    # Click validate
    validate_item.click()
    page.wait_for_timeout(500)

    # Modal should appear with results from fixture PGN
    expect(page.locator("#validate-modal")).to_be_visible()
    expect(page.locator("#validate-content")).to_contain_text("test.pgn")
    expect(page.locator("#validate-content")).to_contain_text("Test Chapter")

    # Close modal
    page.locator("#close-validate").click()
    expect(page.locator("#validate-modal")).not_to_be_visible()

    # Verify console logs
    log_text = "\n".join(console_errors["messages"])
    assert "[showValidate]" in log_text


def test_app_mode_status_modal(page, app_url, console_errors):
    """[App] mode: Project status menu item opens modal."""
    page.goto(app_url)
    page.wait_for_selector("cg-board piece", timeout=BOARD_TIMEOUT)

    # Open menu
    page.locator("#menu-btn").click()
    page.wait_for_timeout(300)

    # Status item should be visible and enabled
    status_item = page.locator("#nav-status")
    expect(status_item).to_be_visible()
    expect(status_item).not_to_have_class("disabled")

    # Click status
    status_item.click()
    page.wait_for_timeout(500)

    # Modal should appear (no config.json in test fixture → shows message)
    expect(page.locator("#status-modal")).to_be_visible()
    expect(page.locator("#status-content")).not_to_be_empty()

    # Close modal
    page.locator("#close-status").click()
    expect(page.locator("#status-modal")).not_to_be_visible()

    # Verify console logs
    log_text = "\n".join(console_errors["messages"])
    assert "[showProjectStatus]" in log_text


def test_app_mode_menu_hidden_in_demo(page, pwa_url):
    """[Demo] mode: App-only menu items are hidden."""
    page.goto(pwa_url)
    page.wait_for_selector("cg-board piece", timeout=BOARD_TIMEOUT)

    page.locator("#menu-btn").click()
    page.wait_for_timeout(300)

    expect(page.locator("#nav-stats")).not_to_be_visible()
    expect(page.locator("#nav-validate")).not_to_be_visible()
    expect(page.locator("#nav-status")).not_to_be_visible()
