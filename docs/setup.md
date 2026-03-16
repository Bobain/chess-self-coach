# Setup Guide

## 1. Create a Lichess Account

1. Go to [lichess.org/signup](https://lichess.org/signup)
2. Create a free account

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

## 3. Create Lichess Studies

The CLI cannot create studies via the API (Lichess limitation), so you must create them manually. This is a one-time step.

1. Go to [lichess.org/study](https://lichess.org/study)
2. Click **"+ Create a study"**
3. Set the **Name** to one of these exact names (so the CLI can auto-detect them):
    - `Whites - Queen's Gambit`
    - `Black vs e4 - Scandinavian`
    - `Black vs d4 - Slav`
4. **Visibility**: leave as `Unlisted` (default)
5. Leave all other settings as defaults
6. Click **START**
7. A "New chapter" dialog will appear — **close it** (click ✕). The CLI will create chapters automatically when you push PGN files.
8. Repeat for the other 2 studies

After creating all 3 studies, run `chess-self-coach setup` to auto-detect them.

## 4. Set Up Chessdriller

1. Go to [chessdriller.org](https://chessdriller.org/)
2. Log in with your Lichess account (OAuth — no separate account needed)
3. Chessdriller reads directly from your Lichess Studies

## 5. Install En-Croissant (Optional)

[En-Croissant](https://encroissant.org/) is a desktop chess GUI for visual validation.

1. Download and install from [encroissant.org](https://encroissant.org/)
2. Stockfish 18 is bundled automatically
3. Open PGN files to visually review positions and engine evaluations

!!! warning
    En-Croissant modifies PGN files while they're open. Always **close files** in En-Croissant before running CLI commands.

## 6. Install chess-self-coach

```bash
# From PyPI
pip install chess-self-coach

# From source
git clone https://github.com/Bobain/chess-self-coach.git
cd chess-self-coach
uv venv && uv sync
```

## 7. Configure

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

1. Verify your Lichess authentication
2. Check Stockfish availability
3. List your existing Lichess studies
4. Auto-match studies to PGN files by name
5. Save your personal configuration to `config.json`

!!! note
    Both `config.json` and `.env` are gitignored — they contain your personal data (study IDs, API token) and will never be pushed to the repository. Each user has their own.

## 8. Verify

```bash
chess-self-coach status
```

This shows the current state of all files, Stockfish, and Lichess configuration.
