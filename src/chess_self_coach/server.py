"""FastAPI backend server for Chess Self-Coach [App] mode.

Serves the PWA with API endpoints for native Stockfish analysis.
Replaces the old static-file-only serve_pwa() from trainer.py.

Key design decisions:
- No temp dir: PWA files served directly from source, sw.js and
  training_data.json via dynamic routes (always fresh, no copy needed).
- Single Stockfish engine instance with asyncio.Lock for thread safety.
- Engine crash recovery: auto-restart on EngineTerminatedError.
- Port scanning: tries 8000-8010 if default port is busy.
"""

from __future__ import annotations

import asyncio
import socket
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import chess
import chess.engine
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from chess_self_coach import __version__
from chess_self_coach.config import _find_project_root, find_stockfish

# --- State ---

_engine: chess.engine.SimpleEngine | None = None
_engine_lock = asyncio.Lock()
_sf_path: Path | None = None
_sf_version: str = "unknown"
_project_root: Path = Path.cwd()
_pwa_dir: Path = Path.cwd() / "pwa"


# --- Lifespan ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage Stockfish engine lifecycle."""
    global _engine, _sf_path, _sf_version, _project_root, _pwa_dir

    _project_root = _find_project_root()
    _pwa_dir = _project_root / "pwa"

    try:
        _sf_path = find_stockfish()
        _engine = chess.engine.SimpleEngine.popen_uci(str(_sf_path))
        # Parse version from engine id
        _sf_version = _engine.id.get("name", "unknown")
        print(f"  Stockfish: {_sf_version}")
    except SystemExit:
        print("  Warning: Stockfish not found. /api/stockfish/* will be unavailable.")
        _engine = None

    yield

    if _engine:
        _engine.quit()
        _engine = None


# --- App ---

app = FastAPI(
    title="Chess Self-Coach",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


# --- Pydantic models ---


class BestMoveRequest(BaseModel):
    """Request body for /api/stockfish/bestmove."""

    fen: str
    depth: int = Field(ge=1, le=30, default=18)


class BestMoveResponse(BaseModel):
    """Response body for /api/stockfish/bestmove."""

    bestmove: str


class StatusResponse(BaseModel):
    """Response body for /api/status."""

    mode: str = "app"
    version: str
    stockfish_version: str


class StatsResponse(BaseModel):
    """Response body for /api/train/stats."""

    generated: str
    total: int
    by_category: dict[str, int]
    by_source: dict[str, int]


class ChapterResult(BaseModel):
    """Validation result for one PGN chapter."""

    name: str
    errors: list[str]
    warnings: list[str]
    infos: list[str]


class FileValidation(BaseModel):
    """Validation result for one PGN file."""

    file: str
    chapters: list[ChapterResult]


class ValidateResponse(BaseModel):
    """Response body for /api/pgn/validate."""

    files: list[FileValidation]


# --- API routes ---


@app.get("/api/status")
async def status() -> StatusResponse:
    """Return app status for mode detection by the PWA."""
    return StatusResponse(
        version=__version__,
        stockfish_version=_sf_version,
    )


@app.post("/api/stockfish/bestmove")
async def bestmove(req: BestMoveRequest) -> BestMoveResponse:
    """Compute the best move for a position using native Stockfish."""
    global _engine

    if _engine is None:
        raise HTTPException(status_code=503, detail="Stockfish not available")

    try:
        board = chess.Board(req.fen)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid FEN: {err}")

    limit = chess.engine.Limit(depth=req.depth)

    async with _engine_lock:
        try:
            result = await asyncio.to_thread(_engine.play, board, limit)
        except chess.engine.EngineTerminatedError:
            # Engine crashed — restart and retry
            print("  Warning: Stockfish crashed, restarting...")
            if _sf_path:
                _engine = chess.engine.SimpleEngine.popen_uci(str(_sf_path))
                result = await asyncio.to_thread(_engine.play, board, limit)
            else:
                raise HTTPException(status_code=503, detail="Stockfish crashed and cannot restart")

    return BestMoveResponse(bestmove=str(result.move))


@app.get("/api/train/stats")
async def train_stats() -> StatsResponse:
    """Return training data statistics."""
    from chess_self_coach.trainer import get_stats_data

    try:
        stats = get_stats_data(_project_root)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="No training data. Run: chess-self-coach train --prepare",
        )
    return StatsResponse(**stats)


@app.post("/api/pgn/validate")
async def pgn_validate() -> ValidateResponse:
    """Validate all PGN files in the project root."""
    from chess_self_coach.validate import validate_pgn

    pgn_files = sorted(_project_root.glob("*.pgn"))
    if not pgn_files:
        raise HTTPException(status_code=404, detail="No PGN files found")

    results = []
    for pgn_path in pgn_files:
        chapters = validate_pgn(pgn_path)
        results.append(FileValidation(
            file=pgn_path.name,
            chapters=[ChapterResult(**ch) for ch in chapters],
        ))
    return ValidateResponse(files=results)


# --- Dynamic file routes (before StaticFiles mount) ---


@app.get("/training_data.json")
async def training_data():
    """Serve training data directly from project root (always fresh)."""
    path = _project_root / "training_data.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No training data. Run: chess-self-coach train --prepare")
    return FileResponse(path, media_type="application/json")


@app.get("/sw.js")
async def service_worker():
    """Serve service worker with version injected on-the-fly."""
    sw_path = _pwa_dir / "sw.js"
    if not sw_path.exists():
        raise HTTPException(status_code=404, detail="Service worker not found")
    content = sw_path.read_text()
    cache_version = f"{__version__}-{int(time.time())}"
    content = content.replace("__VERSION__", cache_version)
    return Response(content, media_type="application/javascript")


# --- Static files (mounted last — catch-all) ---


def _mount_static(app: FastAPI) -> None:
    """Mount PWA static files. Called after app creation."""
    pwa_dir = _find_project_root() / "pwa"
    if pwa_dir.exists():
        app.mount("/", StaticFiles(directory=str(pwa_dir), html=True), name="pwa")


_mount_static(app)


# --- Server runner ---


def _find_available_port(start: int = 8000, end: int = 8010) -> int:
    """Find the first available port in range."""
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("localhost", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No available port in range {start}-{end}")


def run_server() -> None:
    """Start the FastAPI server and open the browser.

    Called by cli.py when user runs `chess-self-coach` (no subcommand)
    or `chess-self-coach train --serve`.
    """
    import threading

    import uvicorn

    port = _find_available_port()
    url = f"http://localhost:{port}"

    print(f"  Serving PWA at {url} (v{__version__})")
    print("  Press Ctrl+C to stop\n")

    threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    uvicorn.run(
        app,
        host="localhost",
        port=port,
        log_level="warning",
    )
