# Flows

This section documents how data and actions flow through the system — from the user's perspective, through the backend, and into storage.

## Categories

### [User flows](user-flows.md)

Interactive workflows visible to the player.

- **Training session** — PWA quiz loop with spaced repetition
- **Analyse latest games** — Fetch, analyze, generate training positions
- **Setup wizard** — CLI interactive configuration
- **Config management** — CLI setup + PWA edit config

### [Data flows](data-flows.md)

How data moves through the system.

- **Data lifecycle** — From chess platforms to practice sessions
- **SRS algorithm** — SM-2 spaced repetition scheduling

### [System flows](system-flows.md)

Infrastructure and runtime internals.

- **CI/CD pipeline** — Test, build, deploy on push
- **PWA mode detection** — Demo vs application mode
- **Service worker & caching** — Offline access and updates
- **Stockfish lifecycle** — Detection, crash recovery, WASM fallback

### [Coming soon flows](coming-soon-flows.md)

Planned features not yet fully implemented.

- **PGN sync** — Push/pull/cleanup Lichess studies

### [Meta flows](meta-flows.md)

How this documentation stays up to date.

- **Auto-documentation hooks** — Claude hooks + CI image generation

## Image generation

Mermaid diagrams in these pages have corresponding SVG images in the `images/` directory, generated automatically by CI on every push to `main` or `dev`. See [Meta flows](meta-flows.md) for details.
