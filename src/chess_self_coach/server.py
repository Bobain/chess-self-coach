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
import json
import logging
import shutil
import socket
import subprocess
import threading
import time
import traceback
import uuid
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TypedDict, cast

import chess
import chess.engine
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from chess_self_coach import __version__
from chess_self_coach.config import (
    ANALYSIS_DATA_FILE,
    CLASSIFICATIONS_DATA_FILE,
    CONFIG_FILE,
    DATA_DIR,
    TRAINING_DATA_FILE,
    _find_project_root,
    find_stockfish,
)
from chess_self_coach.io import atomic_write_json

# --- State ---

_log = logging.getLogger(__name__)

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
        _log.info("Stockfish: %s", _sf_version)
    except SystemExit:
        _log.warning("Stockfish not found. /api/stockfish/* will be unavailable.")
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


# --- Crash reporter ---


def _gh_create_issue(title: str, body: str) -> None:
    """Create a GitHub issue for an unhandled server error.

    Only runs when `gh` CLI is available and authenticated with write access.
    Deduplicates by checking if an open issue with the same title exists.
    No explicit permission check — if the user lacks write access, `gh` fails
    silently (caught by the except).
    """
    if not shutil.which("gh"):
        return

    try:
        existing = subprocess.run(
            ["gh", "issue", "list", "--state", "open", "--search", title,
             "--json", "title", "-q", ".[].title"],
            capture_output=True, text=True, timeout=5,
        )
        if existing.returncode == 0 and title in existing.stdout:
            return

        subprocess.run(
            ["gh", "issue", "create", "--title", title, "--body", body,
             "--label", "bug"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled exceptions, log them, and create a GitHub issue."""
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    tb_text = "".join(tb)

    error_type = type(exc).__name__
    title = f"[crash] {error_type}: {str(exc)[:80]}"
    body = (
        f"## Server crash\n\n"
        f"**Endpoint:** `{request.method} {request.url.path}`\n"
        f"**Version:** {__version__}\n\n"
        f"```\n{tb_text}\n```"
    )

    threading.Thread(target=_gh_create_issue, args=(title, body), daemon=True).start()

    return JSONResponse(status_code=500, content={"detail": str(exc)})


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


class ConfigResponse(BaseModel):
    """Response body for GET /api/config."""

    players: dict[str, str]
    analysis: dict[str, float | int]


class ConfigUpdateRequest(BaseModel):
    """Request body for POST /api/config."""

    players: dict[str, str] | None = None
    analysis: dict[str, float | int] | None = None


class GameSummaryResponse(BaseModel):
    """One game in the game list."""

    game_id: str
    white: str
    black: str
    player_color: str
    result: str
    date: str
    opening: str
    move_count: int
    source: str
    analyzed: bool


class GameListResponse(BaseModel):
    """Response body for GET /api/games."""

    games: list[GameSummaryResponse]
    fetched_at: str | None = None


class AnalysisSettingsResponse(BaseModel):
    """Response body for GET /api/analysis/settings."""

    threads: int
    hash_mb: int
    limits: dict[str, dict[str, float | int]]


class AnalysisStartRequest(BaseModel):
    """Request body for POST /api/analysis/start."""

    game_ids: list[str] = Field(default_factory=list)
    max_games: int = 10
    reanalyze_all: bool = False


class JobStartResponse(BaseModel):
    """Response body for job start endpoints."""

    job_id: str


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
            _log.warning("Stockfish crashed, restarting...")
            if _sf_path:
                _engine = chess.engine.SimpleEngine.popen_uci(str(_sf_path))
                result = await asyncio.to_thread(_engine.play, board, limit)
            else:
                raise HTTPException(status_code=503, detail="Stockfish crashed and cannot restart")

    return BestMoveResponse(bestmove=str(result.move))


# --- Config API ---


@app.get("/api/config")
async def get_config() -> ConfigResponse:
    """Return editable config fields (players, analysis)."""
    config_path = _project_root / DATA_DIR / CONFIG_FILE
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="config.json not found")

    with open(config_path) as f:
        config = json.load(f)

    return ConfigResponse(
        players=config.get("players", {}),
        analysis=config.get("analysis", {}),
    )


@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest) -> ConfigResponse:
    """Update editable config fields (players, analysis). Preserves other fields."""
    config_path = _project_root / DATA_DIR / CONFIG_FILE
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="config.json not found")

    with open(config_path) as f:
        config = json.load(f)

    if req.players is not None:
        config["players"] = req.players
    if req.analysis is not None:
        config["analysis"] = req.analysis

    atomic_write_json(config_path, config)

    return ConfigResponse(
        players=config.get("players", {}),
        analysis=config.get("analysis", {}),
    )


# --- Game list endpoints ---


@app.post("/api/games/fetch")
async def games_fetch(max_games: int = 200) -> GameListResponse:
    """Fetch games from Lichess/chess.com and cache locally."""
    from chess_self_coach.config import load_config
    from chess_self_coach.game_cache import fetch_and_cache_games, load_game_cache

    config = load_config()
    players = config.get("players", {})
    lichess_user = players.get("lichess", "")
    chesscom_user = players.get("chesscom")

    if not lichess_user and not chesscom_user:
        raise HTTPException(
            status_code=400,
            detail="No player configured. Run 'chess-self-coach setup'.",
        )

    summaries = await asyncio.to_thread(
        fetch_and_cache_games, lichess_user, chesscom_user, max_games
    )
    cache = load_game_cache()

    return GameListResponse(
        games=[GameSummaryResponse(**s.to_dict()) for s in summaries],
        fetched_at=cache.get("fetched_at"),
    )


@app.get("/api/games")
async def games_list(limit: int = 20) -> GameListResponse:
    """Return unified game list (cached + analyzed), sorted by date."""
    from chess_self_coach.game_cache import get_unified_game_list, load_game_cache

    summaries = get_unified_game_list(limit=limit)
    cache = load_game_cache()

    return GameListResponse(
        games=[GameSummaryResponse(**s.to_dict()) for s in summaries],
        fetched_at=cache.get("fetched_at"),
    )


# --- Analysis settings endpoints ---


@app.get("/api/analysis/settings")
async def get_analysis_settings() -> AnalysisSettingsResponse:
    """Return current analysis engine settings (with 'auto' resolved)."""
    from chess_self_coach.analysis import AnalysisSettings
    from chess_self_coach.config import load_config

    config = load_config()
    settings = AnalysisSettings.from_config(config)
    d = settings.to_dict()
    return AnalysisSettingsResponse(
        threads=d["threads"],
        hash_mb=d["hash_mb"],
        limits=d["limits"],
    )


@app.post("/api/analysis/settings")
async def update_analysis_settings(req: AnalysisSettingsResponse) -> AnalysisSettingsResponse:
    """Save analysis engine settings to config.json."""
    config_path = _project_root / DATA_DIR / CONFIG_FILE
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="config.json not found")

    with open(config_path) as f:
        config = json.load(f)

    config["analysis_engine"] = {
        "threads": req.threads,
        "hash_mb": req.hash_mb,
        "limits": req.limits,
    }

    atomic_write_json(config_path, config)

    return req


@app.post("/api/analysis/start", status_code=202)
async def analysis_start(req: AnalysisStartRequest) -> JobStartResponse:
    """Start a background full game analysis job."""
    global _current_job

    with _job_lock:
        if _current_job and _current_job["status"] == "running":
            raise HTTPException(status_code=409, detail="A job is already running")

        job_id = str(uuid.uuid4())[:8]
        _current_job = {
            "id": job_id,
            "status": "running",
            "queue": asyncio.Queue(),
            "cancel": threading.Event(),
            "params": {
                "game_ids": req.game_ids,
                "max_games": req.max_games,
                "reanalyze_all": req.reanalyze_all,
            },
        }

    loop = asyncio.get_event_loop()
    thread = threading.Thread(target=_run_analysis_job, args=(job_id, loop), daemon=True)
    thread.start()

    return JobStartResponse(job_id=job_id)


# --- Job runner ---

class _JobState(TypedDict):
    """Internal state for a running analysis job."""

    id: str
    status: str
    queue: asyncio.Queue[dict[str, object] | None]
    cancel: threading.Event
    params: dict[str, object]


_current_job: _JobState | None = None
_job_lock = threading.Lock()


def _run_analysis_job(job_id: str, loop: asyncio.AbstractEventLoop) -> None:
    """Run analyze_games in a background thread.

    Pushes progress events to the job's asyncio.Queue via the event loop.

    Args:
        job_id: ID of the current job.
        loop: The main asyncio event loop (for call_soon_threadsafe).
    """
    global _current_job

    from chess_self_coach.analysis import AnalysisInterrupted, analyze_games
    from chess_self_coach.classifier import run_classification
    from chess_self_coach.training_data import annotate_and_derive
    from chess_self_coach.tactics import run_tactical_analysis

    assert _current_job is not None
    job = _current_job
    queue = job["queue"]
    cancel = job["cancel"]
    params = job.get("params", {})

    def _push(item: dict[str, object] | None) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
        except RuntimeError:
            pass

    def on_progress(event: dict[str, object]) -> None:
        _push(event)

    try:
        raw_ids = params.get("game_ids")
        game_ids = cast(list[str] | None, raw_ids) if raw_ids else None

        def _on_game_done(game_id: str) -> None:
            _push({"phase": "derive", "message": "Deriving training data...", "game_id": game_id})
            try:
                annotate_and_derive()
            except Exception as e:
                _log.error("annotate_and_derive failed for %s: %s", game_id, e)

        analyze_games(
            game_ids=game_ids,
            max_games=cast(int, params.get("max_games", 10)),
            reanalyze_all=cast(bool, params.get("reanalyze_all", False)),
            on_progress=on_progress,
            on_game_done=_on_game_done,
            cancel=cancel,
        )

        _push({"phase": "tactics", "message": "Running tactical analysis..."})
        run_tactical_analysis()

        _push({"phase": "classification", "message": "Classifying moves..."})
        run_classification()

        job["status"] = "done"
    except AnalysisInterrupted as exc:
        _push({"phase": "interrupted", "message": str(exc), "percent": 100})
        job["status"] = "interrupted"
    except Exception as exc:
        _push({"phase": "error", "message": str(exc), "percent": 100})
        job["status"] = "error"
    finally:
        _push(None)  # Signal end of stream


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    """Stream job progress events via SSE."""
    if not _current_job or _current_job["id"] != job_id:
        raise HTTPException(status_code=404, detail="Job not found")

    queue = _current_job["queue"]

    async def event_generator():
        while True:
            event = await queue.get()
            if event is None:
                break
            yield {"data": json.dumps(event)}

    return EventSourceResponse(event_generator())


@app.get("/api/jobs/current")
async def job_current():
    """Return the current job ID and status, if any."""
    if not _current_job:
        return {"job_id": None, "status": None, "game_ids": []}
    params = _current_job.get("params", {})
    return {"job_id": _current_job["id"], "status": _current_job["status"], "game_ids": params.get("game_ids", [])}


@app.post("/api/jobs/{job_id}/cancel", status_code=202)
async def job_cancel(job_id: str):
    """Request cancellation of a running job."""
    if not _current_job or _current_job["id"] != job_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if _current_job["status"] != "running":
        raise HTTPException(status_code=409, detail="Job is not running")
    _current_job["cancel"].set()
    return {"status": "cancelling"}


# --- Dynamic file routes (before StaticFiles mount) ---


@app.get("/training_data.json")
async def training_data():
    """Serve training data directly from project root (always fresh)."""
    path = _project_root / DATA_DIR / TRAINING_DATA_FILE
    if not path.exists():
        raise HTTPException(status_code=404, detail="No training data. Run: chess-self-coach train --prepare")
    return FileResponse(path, media_type="application/json")


@app.get("/analysis_data.json")
async def analysis_data():
    """Serve analysis data directly from project root (always fresh)."""
    path = _project_root / DATA_DIR / ANALYSIS_DATA_FILE
    if not path.exists():
        raise HTTPException(status_code=404, detail="No analysis data. Run: chess-self-coach train --analyze")
    return FileResponse(path, media_type="application/json")


@app.get("/classifications_data.json")
async def classifications_data():
    """Serve pre-computed move classifications (always fresh)."""
    path = _project_root / DATA_DIR / CLASSIFICATIONS_DATA_FILE
    if not path.exists():
        raise HTTPException(status_code=404, detail="No classifications data")
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
