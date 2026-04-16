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
3. No special scopes needed (default read access is sufficient for fetching games)
4. Click **Submit** — copy the token immediately (shown only once, starts with `lip_`)

### Test your token

```bash
curl -H "Authorization: Bearer lip_your_token" https://lichess.org/api/account
```

## 3. Configure

```bash
# Create your personal config from the template
cp data/config.example.json data/config.json

# Save your Lichess token
cp .env.example .env
# Edit .env and replace lip_your_token_here with your actual token

# Run interactive setup (verifies auth, saves config)
chess-self-coach setup
```

The `setup` command will:

1. Check Stockfish availability
2. Download Syzygy endgame tablebases (3-5 pieces, ~1 GB) — prompts for installation directory
3. Ask for your Lichess username and API token
4. Ask for your chess.com username
5. Save your personal configuration to `data/config.json`

!!! note
    Both `data/config.json` and `.env` are gitignored — they contain your personal data (API token, usernames) and will never be pushed to the repository.

## 4. Verify

```bash
chess-self-coach train --stats
```

This shows your training progress statistics.
