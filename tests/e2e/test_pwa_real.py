"""E2E tests using REAL training data (production positions).

These tests catch bugs that fixture-based tests miss — like missing game.id,
incompatible data formats, or positions that behave differently in production.

Skipped if training_data.json doesn't exist.

Requirements:
    uv run playwright install chromium
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect

from tests.e2e.conftest import make_move

BOARD_TIMEOUT = 20000
PROJECT_ROOT = Path(__file__).parent.parent.parent


def _wait_for_board(page, url):
    """Navigate to PWA, switch to training via menu, and wait for the board."""
    page.goto(url)
    # Default view is game list; switch to training via nav menu
    page.wait_for_selector("#menu-btn", timeout=5000)
    page.wait_for_timeout(500)
    page.click("#menu-btn")
    page.wait_for_selector("#nav-menu.nav-open", state="attached", timeout=10000)
    page.click("#nav-training")
    page.wait_for_selector("cg-board piece", timeout=BOARD_TIMEOUT)


def _wait_for_animation(page):
    """Wait for the wrong-move animation to complete (500ms + 1500ms + margin)."""
    page.wait_for_timeout(2500)


def _get_first_position():
    """Load the first position from real training data."""
    data_path = PROJECT_ROOT / "training_data.json"
    if not data_path.exists():
        return None
    with open(data_path) as f:
        data = json.load(f)
    return data["positions"][0] if data.get("positions") else None


# --- Real data tests ---


def test_real_board_loads(page, pwa_real_url, console_errors):
    """The PWA loads with real training data and shows a position."""
    _wait_for_board(page, pwa_real_url)
    _wait_for_animation(page)

    expect(page.locator("#prompt")).to_contain_text("You played")
    expect(page.locator("#progress")).to_contain_text("1 /")


def test_real_see_moves_after_correct(page, pwa_real_url, console_errors):
    """The 'See moves' link appears after playing the correct move on real data."""
    import chess

    pos = _get_first_position()
    if pos is None:
        import pytest
        pytest.skip("No training data")

    board = chess.Board(pos["fen"])
    move = board.parse_san(pos["best_move"])
    from_sq = chess.square_name(move.from_square)
    to_sq = chess.square_name(move.to_square)

    _wait_for_board(page, pwa_real_url)
    _wait_for_animation(page)

    make_move(page, from_sq, to_sq, pos["player_color"])
    page.wait_for_timeout(500)

    expect(page.locator("#feedback-text")).to_contain_text("Correct")
    expect(page.locator("#see-moves")).to_be_visible()

    href = page.locator("#see-moves").get_attribute("href")
    assert href is not None, "See moves link has no href"
    assert "chess.com" in href or "lichess.org" in href, f"Unexpected href: {href}"

    # Verify console logs show the flow
    msgs = console_errors["messages"]
    log_text = "\n".join(msgs)
    assert "[showFeedback]" in log_text, f"showFeedback not called. Console:\n{log_text}"
    assert "seeLinkEl=found" in log_text, f"see-moves element not found. Console:\n{log_text}"


def test_real_see_moves_after_failure(page, pwa_real_url, console_errors):
    """The 'See moves' link appears after 2 wrong attempts on real data."""
    _wait_for_board(page, pwa_real_url)
    _wait_for_animation(page)

    pos = _get_first_position()
    if pos is None:
        import pytest
        pytest.skip("No training data")

    import chess
    board = chess.Board(pos["fen"])
    best_move = board.parse_san(pos["best_move"])

    # Find a legal move that is NOT the best move
    wrong_move = None
    for m in board.legal_moves:
        if m != best_move:
            wrong_move = m
            break
    assert wrong_move is not None, "No wrong move available"

    from_sq = chess.square_name(wrong_move.from_square)
    to_sq = chess.square_name(wrong_move.to_square)

    # Play 2 wrong moves — "See moves" link appears after 2 wrong attempts
    for i in range(2):
        page.wait_for_selector("cg-board piece", timeout=5000)
        page.wait_for_timeout(200)
        make_move(page, from_sq, to_sq, pos["player_color"])
        if i < 1:
            page.locator("#retry-btn").wait_for(state="visible", timeout=15000)
            page.locator("#retry-btn").click()
            page.wait_for_timeout(500)
        else:
            page.wait_for_timeout(700)

    # After 2 wrong attempts, "See moves" should be visible (no auto-reveal)
    expect(page.locator("#feedback-text")).to_contain_text("Not quite")
    expect(page.locator("#see-moves")).to_be_visible()
