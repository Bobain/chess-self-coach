"""E2E test fixtures: isolated HTTP server with test training data.

Copies PWA files to a temp directory and serves them with a test-only
training_data.json. The real training data is never touched.
"""

from __future__ import annotations

import http.server
import shutil
import threading
from pathlib import Path

import pytest

PWA_DIR = Path(__file__).parent.parent.parent / "pwa"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def pwa_url(tmp_path_factory):
    """Serve the PWA from a temp directory with test fixture data.

    Isolation guarantees:
    - PWA files are copied (not symlinked) to a temp dir
    - training_data.json comes from tests/e2e/fixtures/, not the real one
    - Each browser context has isolated localStorage (Playwright default)
    """
    tmp_dir = tmp_path_factory.mktemp("pwa_e2e")

    # Copy PWA source files (skip any existing training data)
    for f in PWA_DIR.iterdir():
        if f.is_file() and f.name != "training_data.json":
            shutil.copy2(f, tmp_dir / f.name)

    # Inject version placeholder into service worker (matches CI behavior)
    sw_path = tmp_dir / "sw.js"
    sw_text = sw_path.read_text()
    sw_path.write_text(sw_text.replace("__VERSION__", "test"))

    # Copy test fixture data (NOT the real training data)
    shutil.copy2(
        FIXTURES_DIR / "training_data.json",
        tmp_dir / "training_data.json",
    )

    # Start server on a random available port
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(tmp_dir), **kw)

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{port}"

    server.shutdown()


def click_square(page, square: str, orientation: str):
    """Click a square on the chessground board.

    Computes pixel coordinates from the square name and board orientation,
    then clicks at the center of that square.

    Args:
        page: Playwright page.
        square: Chess square name (e.g., "e2").
        orientation: Board orientation ("white" or "black").
    """
    board = page.locator("cg-board")
    rect = board.bounding_box()
    assert rect is not None, "Board element not found"

    file_idx = ord(square[0]) - ord("a")  # 0-7
    rank_idx = int(square[1]) - 1  # 0-7

    sq_w = rect["width"] / 8
    sq_h = rect["height"] / 8

    if orientation == "white":
        x = rect["x"] + file_idx * sq_w + sq_w / 2
        y = rect["y"] + (7 - rank_idx) * sq_h + sq_h / 2
    else:
        x = rect["x"] + (7 - file_idx) * sq_w + sq_w / 2
        y = rect["y"] + rank_idx * sq_h + sq_h / 2

    page.mouse.click(x, y)


def make_move(page, from_sq: str, to_sq: str, orientation: str):
    """Make a move on the chessground board via click-to-move.

    Clicks the source square (selects the piece), waits briefly,
    then clicks the destination square.

    Args:
        page: Playwright page.
        from_sq: Source square (e.g., "e2").
        to_sq: Destination square (e.g., "e4").
        orientation: Board orientation ("white" or "black").
    """
    page.wait_for_selector("cg-board piece", timeout=5000)
    click_square(page, from_sq, orientation)
    page.wait_for_timeout(150)
    click_square(page, to_sq, orientation)
