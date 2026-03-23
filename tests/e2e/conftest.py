"""E2E test fixtures: isolated HTTP server with test training data.

Copies PWA files to a temp directory and serves them with a test-only
training_data.json. The real training data is never touched.

All tests automatically capture browser console messages and JS errors
via the console_errors fixture — zero JS errors are tolerated.
"""

from __future__ import annotations

import http.server
import shutil
import socket
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
PWA_DIR = PROJECT_ROOT / "pwa"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _serve_pwa_dir(tmp_dir):
    """Start an HTTP server for a PWA directory. Returns (url, server)."""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(tmp_dir), **kw)

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{port}", server


def _copy_pwa_files(tmp_dir, training_data_path, analysis_data_path=None):
    """Copy PWA files + training data to a temp directory."""
    for f in PWA_DIR.iterdir():
        if f.is_file() and f.name not in ("training_data.json", "analysis_data.json"):
            shutil.copy2(f, tmp_dir / f.name)

    # Copy Stockfish WASM directory if present
    stockfish_src = PWA_DIR / "stockfish"
    if stockfish_src.exists():
        shutil.copytree(stockfish_src, tmp_dir / "stockfish")

    # Inject unique version into service worker
    sw_path = tmp_dir / "sw.js"
    sw_text = sw_path.read_text()
    sw_path.write_text(sw_text.replace("__VERSION__", f"test-{int(time.time())}"))

    shutil.copy2(training_data_path, tmp_dir / "training_data.json")

    # Copy analysis data if provided
    if analysis_data_path and analysis_data_path.exists():
        shutil.copy2(analysis_data_path, tmp_dir / "analysis_data.json")


@pytest.fixture(scope="session")
def pwa_url(tmp_path_factory):
    """Serve the PWA with test fixture data (simplified positions)."""
    tmp_dir = tmp_path_factory.mktemp("pwa_e2e")
    analysis_fixture = FIXTURES_DIR / "analysis_data.json"
    _copy_pwa_files(
        tmp_dir,
        FIXTURES_DIR / "training_data.json",
        analysis_fixture if analysis_fixture.exists() else None,
    )
    url, server = _serve_pwa_dir(tmp_dir)
    yield url
    server.shutdown()


@pytest.fixture(scope="session")
def pwa_real_url(tmp_path_factory):
    """Serve the PWA with real training data (production positions).

    Skips if training_data.json doesn't exist.
    """
    real_data = PROJECT_ROOT / "training_data.json"
    if not real_data.exists():
        pytest.skip("training_data.json not found (run train --prepare first)")
    tmp_dir = tmp_path_factory.mktemp("pwa_e2e_real")
    real_analysis = PROJECT_ROOT / "analysis_data.json"
    _copy_pwa_files(
        tmp_dir,
        real_data,
        real_analysis if real_analysis.exists() else None,
    )
    url, server = _serve_pwa_dir(tmp_dir)
    yield url
    server.shutdown()


@pytest.fixture(scope="session")
def app_url(tmp_path_factory):
    """Serve the FastAPI app with test fixture data ([App] mode).

    Starts a uvicorn server in a background thread with _project_root
    patched to a temp directory containing the test training_data.json.
    The real PWA files are served via symlink.
    """
    import uvicorn

    from chess_self_coach.server import app

    # Create temp dir mimicking project root
    tmp_dir = tmp_path_factory.mktemp("app_e2e")
    shutil.copy2(FIXTURES_DIR / "training_data.json", tmp_dir / "training_data.json")
    analysis_fixture = FIXTURES_DIR / "analysis_data.json"
    if analysis_fixture.exists():
        shutil.copy2(analysis_fixture, tmp_dir / "analysis_data.json")
    for pgn in FIXTURES_DIR.glob("*.pgn"):
        shutil.copy2(pgn, tmp_dir / pgn.name)
    (tmp_dir / "pwa").symlink_to(PWA_DIR)

    # Copy coaching journal fixtures
    coaching_src = PROJECT_ROOT / "coaching"
    if coaching_src.exists():
        shutil.copytree(coaching_src, tmp_dir / "coaching")

    # Create a test config.json for config API tests
    import json
    test_config = {
        "stockfish": {"path": "/usr/games/stockfish"},
        "players": {"lichess": "testuser", "chesscom": "testcom"},
        "analysis": {"default_depth": 18, "blunder_threshold": 1.0},
        "studies": {},
    }
    (tmp_dir / "config.json").write_text(json.dumps(test_config, indent=2))

    # Find a free port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    with patch("chess_self_coach.server._find_project_root", return_value=tmp_dir):
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)

        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        while not server.started:
            time.sleep(0.05)

        yield f"http://127.0.0.1:{port}"

        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture(autouse=True)
def console_errors(page):
    """Capture browser console messages and JS errors for every test.

    Automatically attached to every e2e test. Fails the test if any
    JS error (console.error or uncaught exception) is detected.
    All console output is printed on failure for debugging.
    """
    messages = []
    errors = []

    page.on("console", lambda msg: messages.append(f"[{msg.type}] {msg.text}"))
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    yield {"messages": messages, "errors": errors}

    # Print all console output for debugging (visible in pytest -v output)
    if messages:
        print("\n--- Browser console ---")
        for msg in messages:
            print(f"  {msg}")

    # Fail on JS errors
    assert not errors, f"JS errors detected:\n" + "\n".join(errors)


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
