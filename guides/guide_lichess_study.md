# Lichess Study Guide

## Known version
- URL: https://lichess.org/study
- Last verified: 2026-03-15

---

## Creating a new study

### Steps
1. Go to https://lichess.org/study [CONFIRMED — 2026-03-15]
2. Click "+ Create a study" (button at top, or via an existing study page) [CONFIRMED — 2026-03-15]
3. A dialog opens with these fields: [CONFIRMED — 2026-03-15]
   - **Flair**: emoji icon (optional, cosmetic)
   - **Name**: study name (e.g., "Whites - Queen's Gambit")
   - **Visibility**: `Unlisted` (default, recommended) — only people with the link can see it
   - **Chat**: `Members` (default)
   - **Computer analysis**: `Everyone` (default)
   - **Opening explorer & tablebase**: `Everyone` (default)
   - **Allow cloning**: `Everyone` (default)
   - **Share & export**: `Everyone` (default)
   - **Enable sync**: `Yes: keep everyone on the same position` (default)
   - **Pinned study comment**: `None` (default)
4. Click **START** [CONFIRMED — 2026-03-15]
5. A "New chapter" dialog appears immediately [CONFIRMED — 2026-03-15]
   - Fields: **Name** ("Chapter 1"), tabs: Empty / Editor / URL / FEN / **PGN**
   - **Variant**: Standard, **Orientation**: White, **Analysis mode**: Normal analysis
6. **Close this dialog** (click ✕) — do NOT create a chapter manually [CONFIRMED — 2026-03-15]
   - The CLI will create chapters automatically via `chess-self-coach push`
   - If you accidentally create a default chapter, that's fine — it will be replaced by the push
7. The study is now created. You can see its name at the bottom of the page. [CONFIRMED — 2026-03-15]

### Recommended settings for our repertoire
- **Name**: Use the exact names so the CLI can auto-detect them:
  - `Whites - Queen's Gambit`
  - `Black vs e4 - Scandinavian`
  - `Black vs d4 - Slav`
- **Visibility**: `Unlisted` (keeps your repertoire private but shareable)
- Everything else: leave defaults

### How to create the next study
- From an open study: click on your username (top left) → `+ Create a study`
- Or go back to https://lichess.org/study and click the create button

### How to rename a study [CONFIRMED — 2026-03-15]
- Open the study page
- Click the ☰ menu (hamburger icon, top left next to "1 Chapter")
- Look for study settings / edit name option
- Change the name and save

### Notes
- Create one study per PGN file (3 studies total)
- After creation, the study URL contains the study ID (e.g., `lichess.org/study/AbCdEfGh`)
- The CLI (`chess-self-coach setup`) auto-detects studies by name
- You do NOT need to create chapters manually — the CLI handles this

### History
- 2026-03-15: Initial description created
- 2026-03-15: CONFIRMED — dialog fields, "New chapter" sub-dialog, and full workflow verified via screenshots

---

## Importing PGN into a study

### Via CLI (recommended)
```bash
chess-self-coach push pgn/repertoire_blancs_gambit_dame_annote.pgn
```

### Via web UI
1. In the study, click "+" to add a chapter [TO CONFIRM]
2. Go to the "PGN" tab [TO CONFIRM]
3. Paste the PGN content or upload the file [TO CONFIRM — paste or upload?]
4. Click "Create chapter" [TO CONFIRM]
5. Each `[Event "..."]` in the PGN should create a separate chapter [TO CONFIRM]

### Open questions
- Does a multi-game PGN automatically create multiple chapters? The API does — TO CONFIRM for web UI.
- Are comments `{...}` preserved on import? [TO CONFIRM]

### History
- 2026-03-15: Initial description created

---

## Organizing chapters

### Steps
1. Chapters appear in a list [TO CONFIRM — where?]
2. Reorder by drag & drop [TO CONFIRM]
3. Rename a chapter [TO CONFIRM — how?]

### History
- 2026-03-15: Initial description created

---

## Editing an existing study

### Steps
1. Open the study from https://lichess.org/study [TO CONFIRM]
2. Click on a chapter [TO CONFIRM]
3. Play moves on the board to add variations [TO CONFIRM]
4. Add comments [TO CONFIRM — how?]
5. Changes are saved automatically [TO CONFIRM]

### History
- 2026-03-15: Initial description created

---

## Exporting from a study

### Via CLI (recommended)
```bash
chess-self-coach pull pgn/repertoire_blancs_gambit_dame_annote.pgn
```

### Via web UI
1. Study menu → Export / Download PGN [TO CONFIRM]
2. Choose to export the whole study or a single chapter [TO CONFIRM]

### Usage
- Useful for retrieving edits made in Lichess back to local files

### History
- 2026-03-15: Initial description created
