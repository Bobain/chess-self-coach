# Dev Setup

For **end users**, see the one-liner install in the [README](https://github.com/Bobain/chess-self-coach#installation).

This page is for **contributors and developers** who want to run from source.

## 1. Clone and install

```bash
git clone https://github.com/Bobain/chess-self-coach.git
cd chess-self-coach
uv venv && uv sync
```

## 2. Create a Lichess API Token

1. Go to [lichess.org/account/oauth/token/create](https://lichess.org/account/oauth/token/create)
2. **Token description**: `chess-self-coach`
3. Under **STUDIES & BROADCASTS**, check:
    - "Read private studies and broadcasts" (`study:read`)
    - "Create, update, delete studies and broadcasts" (`study:write`)
4. Do **NOT** check any other scopes
5. Click **Submit** — copy the token immediately (shown only once, starts with `lip_`)

### Test your token

```bash
curl -H "Authorization: Bearer lip_your_token" https://lichess.org/api/account
```

## 3. Configure

```bash
# Create your personal config from the template
cp config.example.json config.json

# Save your Lichess token
cp .env.example .env
# Edit .env and replace lip_your_token_here with your actual token

# Run interactive setup (verifies auth, finds studies, saves config)
chess-self-coach setup
```

The `setup` command will:

1. Check Stockfish availability
2. Download Syzygy endgame tablebases (3-5 pieces, ~1 GB) if not already installed
3. Verify your Lichess authentication
4. List your existing Lichess studies
5. Auto-match studies to PGN files by name
6. Save your personal configuration to `config.json`

!!! note
    Both `config.json` and `.env` are gitignored — they contain your personal data (study IDs, API token) and will never be pushed to the repository.

## 4. Verify

```bash
chess-self-coach status
```

This shows the current state of all files, Stockfish, and Lichess configuration.
