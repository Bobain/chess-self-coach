# Meta flows

How this documentation stays up to date.

## Auto-documentation hooks

Claude hooks and CI work together to keep flow documentation synchronized with code changes.

![Auto-documentation hooks flow](images/auto-doc-hooks.svg)

```mermaid
flowchart TD
    subgraph "PostToolUse hook (Write|Edit)"
        CODE_CHANGE[Claude edits a code file] --> MATCH{Path matches<br/>flow-relevant pattern?}
        MATCH -->|src/trainer.py| DATA[Set .pending-flows-check<br/>Category: data flows]
        MATCH -->|src/server.py| SYS[Set .pending-flows-check<br/>Category: system flows]
        MATCH -->|src/config.py, cli.py| MULTI[Set .pending-flows-check<br/>Category: user + data flows]
        MATCH -->|src/importer.py| IMP[Set .pending-flows-check<br/>Category: data flows]
        MATCH -->|pwa/app.js| USER[Set .pending-flows-check<br/>Category: user flows]
        MATCH -->|pwa/sw.js| SYS2[Set .pending-flows-check<br/>Category: system flows]
        MATCH -->|No match| SKIP[No action]
    end

    subgraph "Stop hook"
        STOP[Claude finishes task] --> CHECK{.pending-flows-check<br/>exists?}
        CHECK -->|Yes| BLOCK[Block: remind to review<br/>flow docs for affected category]
        CHECK -->|No| PASS[Let through]
    end

    subgraph "CI: flow-diagrams.yml (push to main/dev)"
        PUSH[git push] --> EXTRACT[Extract Mermaid blocks<br/>from docs/flows/*.md]
        EXTRACT --> MMDC[Run mmdc → generate SVGs]
        MMDC --> DIFF{Images changed?}
        DIFF -->|Yes| COMMIT[Commit + push images<br/>with skip-ci]
        DIFF -->|No| DONE[Done]
    end
```

### How it works

1. **PostToolUse hook** (`check-readme-sync.sh`): when Claude edits a file matching flow-relevant paths, it creates a `.pending-flows-check` marker file. This is separate from the existing `.pending-readme-check` marker.

2. **Stop hook** (`check-flows-on-stop.sh`): when Claude finishes a task, it checks for the marker. If present, it blocks with a reminder listing which flow category to review.

3. **CI workflow** (`flow-diagrams.yml`): on every push to `main` or `dev`, extracts Mermaid blocks from `docs/flows/*.md`, runs `mmdc` (Mermaid CLI) to generate SVG images, and commits them back if changed.

### Flow-relevant path mapping

| Source file | Flow category |
|------------|---------------|
| `src/chess_self_coach/trainer.py` | [Data flows](data-flows.md) |
| `src/chess_self_coach/server.py` | [System flows](system-flows.md) |
| `src/chess_self_coach/config.py` | [Data flows](data-flows.md) |
| `src/chess_self_coach/cli.py` | [User flows](user-flows.md) |
| `src/chess_self_coach/importer.py` | [Data flows](data-flows.md) |
| `pwa/app.js` | [User flows](user-flows.md) |
| `pwa/sw.js` | [System flows](system-flows.md) |
