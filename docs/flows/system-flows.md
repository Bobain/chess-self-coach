# System flows

Infrastructure and runtime internals.

## CI/CD pipeline

What happens when code is pushed.

![CI/CD pipeline flow](images/cicd-pipeline.svg)

```mermaid
flowchart TD
    subgraph "Push to main"
        PUSH[git push origin main]
    end

    subgraph "CI: Test (deploy.yml)"
        UT[Unit tests<br/>pytest tests/ --ignore=e2e]
        E2E[E2E tests<br/>pytest tests/e2e/<br/>Playwright + Chromium]
        UT --> E2E
    end

    subgraph "CD: Deploy (deploy.yml)"
        JSDOC[Generate JS API docs<br/>jsdoc-to-markdown pwa/app.js]
        MKDOCS[Build MkDocs site<br/>mkdocs build]
        VER[Inject version into SW<br/>sed pyproject.toml → sw.js]
        ASM[Assemble site:<br/>landing + docs + PWA]
        GHP[Deploy to GitHub Pages]
        JSDOC --> MKDOCS --> VER --> ASM --> GHP
    end

    subgraph "Release (publish.yml)"
        TAG[Create GitHub Release]
        PYPI[Build + publish to PyPI<br/>uv build + trusted publishing]
        TAG --> PYPI
    end

    PUSH --> UT
    E2E --> JSDOC
    TAG -.-> |manual trigger| PYPI

    subgraph "CI: PR (ci.yml)"
        PRUT[Unit tests]
        PRE2E[E2E tests]
        PRUT --> PRE2E
    end
```

### GitHub Pages site structure

```
site/
├── index.html          ← Landing page
├── docs/               ← MkDocs output (this documentation)
│   ├── index.html
│   ├── setup/
│   ├── cli/
│   ├── training/
│   ├── flows/
│   └── api/
└── train/              ← PWA (demo mode)
    ├── index.html
    ├── app.js
    ├── style.css
    ├── sw.js
    ├── manifest.json
    ├── training_data.json
    └── stockfish/
```

---

## PWA mode detection

How the app decides whether it's running as a demo or as an installed application.

![PWA mode detection flow](images/pwa-mode-detection.svg)

```mermaid
flowchart TD
    START[PWA loads] --> FETCH[Fetch /api/status]
    FETCH -->|200 OK| APP[App mode]
    FETCH -->|Network error / 404| DEMO[Demo mode]

    APP --> SHOW[Show app-only menu items<br/>Enable native Stockfish<br/>Set depth=18]
    DEMO --> HIDE[Hide app-only items<br/>Use WASM Stockfish<br/>Set depth=12]

    APP --> VER{Version check}
    VER -->|Newer available| PROMPT[Show update prompt]
    VER -->|Up to date| READY[Ready]
    DEMO --> READY
```

---

## Service worker & caching

How the PWA handles offline access and updates.

![Service worker & caching flow](images/sw-caching.svg)

```mermaid
flowchart TD
    REQ[Browser request] --> SW[Service Worker]
    SW --> ORIGIN{Same origin?}

    ORIGIN -->|Yes| NF[Network first<br/>Try server → fallback to cache]
    ORIGIN -->|No CDN| CF[Cache first<br/>Try cache → fallback to network]

    NF -->|Success| CACHE1[Update cache + serve]
    NF -->|Offline| SERVE1[Serve from cache]

    CF -->|Cache hit| SERVE2[Serve from cache]
    CF -->|Cache miss| FETCH2[Fetch + cache + serve]
```

### Key rules

- **Network-first** for same-origin assets: always serve fresh files from the server (important because `server.py` serves files dynamically).
- **Cache-first** for CDN resources (chessground, chess.js): these never change.
- `skipWaiting()` + `clients.claim()` ensure the new SW takes over immediately.

---

## Stockfish lifecycle

How Stockfish is detected, managed, and recovered across CLI, server, and PWA.

![Stockfish lifecycle flow](images/stockfish-lifecycle.svg)

```mermaid
flowchart TD
    subgraph "CLI / Server: Native Stockfish"
        FIND[find_stockfish] --> S1{Config path?}
        S1 -->|exists| S_OK[Use config path]
        S1 -->|missing| S2{Fallback path?}
        S2 -->|exists| S_OK
        S2 -->|missing| S3{En-Croissant default?}
        S3 -->|exists| S_OK
        S3 -->|missing| S4{/usr/games/stockfish?}
        S4 -->|exists| S_OK
        S4 -->|missing| S5{which stockfish?}
        S5 -->|found| S_OK
        S5 -->|not found| S_ERR[Error: tested paths + install hint]

        S_OK --> VER_CHK[check_stockfish_version]
        VER_CHK --> VER_OK{Matches expected?}
        VER_OK -->|No| VER_WARN[Warning: version mismatch]
        VER_OK -->|Yes| READY_N[Engine ready]
        VER_WARN --> READY_N
    end

    subgraph "Server: Crash recovery"
        READY_N --> REQ_S[/api/stockfish/bestmove]
        REQ_S --> LOCK[Acquire engine lock]
        LOCK --> PLAY[engine.play]
        PLAY -->|EngineTerminatedError| RESTART[Restart engine]
        RESTART --> PLAY
        PLAY -->|Success| RESP[Return best move]
    end

    subgraph "PWA: WASM Stockfish"
        INIT[initStockfish] --> WORKER[new Worker<br/>stockfish-18-lite-single.js]
        WORKER --> UCI[Send: uci + isready]
        UCI --> READY_W[Engine ready]
        READY_W --> BM[getBestMove fen depth=12]
        BM --> POST_MSG[postMessage: position + go]
        POST_MSG --> PARSE[Parse bestmove from output]
    end
```

### Key details

- **Search order**: config path → fallback path → En-Croissant → `/usr/games/stockfish` → `$PATH`.
- **Server crash recovery**: catches `EngineTerminatedError`, restarts engine, retries the request.
- **Engine lock**: `asyncio.Lock` prevents concurrent access to the single engine process.
- **WASM variant**: uses `stockfish-18-lite-single.js` (single-threaded, suitable for browser). Depth limited to 12 (vs 18 for native).
- **Lazy init**: WASM worker is only created on first call to `getBestMove()`.
