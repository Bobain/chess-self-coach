Find games that need labeling for the classification ground truth (!! and ! moves), present them interactively for the user to label, and update the test fixtures.

Argument: $ARGUMENTS is the minimum number of ! (great) moves to include a game. Default: 4. Games with >=1 !! are always included regardless of this threshold.

## Step 1: Find candidates

Run this EXACT command (do NOT write your own script):

```bash
uv run python3 -c "
import json, sys
sys.path.insert(0, '.')
from chess_self_coach.classifier import classify_move
from chess_self_coach.config import analysis_data_path, tactics_data_path
from tests.e2e.classification_cases import GAMES
MIN_GREAT = ${ARGUMENTS:-4}
PLAYER = 'Tonigor1982'
with open(analysis_data_path()) as f: analysis = json.load(f)
tactics_games = {}
tp = tactics_data_path()
if tp.exists():
    with open(tp) as f: tactics_games = json.load(f).get('games', {})
existing = {g['game_id'] for g in GAMES}
candidates = []
for url, gd in analysis['games'].items():
    nid = url.rstrip('/').split('/')[-1]
    h = gd['headers']
    opp = h['black'] if h['white'] == PLAYER else h['white']
    gtid = f'{opp}_{nid}'
    if gtid in existing: continue
    moves = gd.get('moves', [])
    gt = tactics_games.get(url, [])
    bc = gc = 0
    for i, m in enumerate(moves):
        s = m.get('side', 'white' if i%2==0 else 'black')
        p = moves[i-1] if i>0 else None
        t = gt[i] if i<len(gt) else None
        c = classify_move(m, s, p, t)
        if c:
            if c['c']=='brilliant': bc+=1
            elif c['c']=='great': gc+=1
    if bc>=1 or gc>=MIN_GREAT:
        candidates.append(dict(url=url,gtid=gtid,b=bc,g=gc,date=h.get('date','?'),w=h['white'],bk=h['black'],moves=len(moves)))
candidates.sort(key=lambda c:(-(c['b']>0),c['date']))
bg=sum(1 for c in candidates if c['b']>0)
print(f'Found {len(candidates)} candidates ({bg} with !!, {len(candidates)-bg} with >={MIN_GREAT} !)')
for c in candidates:
    tags=[]
    if c['b']: tags.append(f\"{c['b']}!!\")
    if c['g']: tags.append(f\"{c['g']}!\")
    print(f\"  {c['gtid']:40s} {c['date']}  {' '.join(tags):10s}  {c['moves']} moves  {c['url']}\")
"
```

If no candidates found, inform the user and stop.

## Step 2: Process each game

For each candidate game, from oldest to newest (!! games first):

1. Show: `{White} vs {Black}, {date}, {result}, {move_count} moves`
2. Give the user the **game URL** so they can review the game on chess.com
3. **Wait** for the user's response. They will reply with move numbers like "9.b Bh2+ is !, 15.w Nxe6 is !!" or "aucun coup !! ni !"
4. **Map move numbers to indices**: `index = (move_number - 1) * 2 + (1 if black else 0)`. Verify SAN with:
```python
python3 -c "
import json
with open('data/analysis_data.json') as f: d=json.load(f)
m=d['games']['{URL}']['moves'][{IDX}]
print(f'idx {IDX}: {(IDX//2)+1}.{\"w\" if m[\"side\"]==\"white\" else \"b\"} {m[\"move_san\"]}')
"
```
5. Any move not mentioned = "other"

## Step 3: Update ground truth JSON

Run this command (replace `{URL}`, `{GTID}`, and the comma-separated indices):
```bash
uv run python scripts/add_ground_truth_game.py "{URL}" "{GTID}" "{BRILLIANT_COMMA_SEP}" "{GREAT_COMMA_SEP}"
```

Example for a game with no brilliant and great at indices 19,31:
```bash
uv run python scripts/add_ground_truth_game.py "https://www.chess.com/game/live/125080133625" "shivauttangi_125080133625" "" "19,31"
```

Example for "aucun coup !! ni !" (all other):
```bash
uv run python scripts/add_ground_truth_game.py "https://www.chess.com/game/live/125083720203" "Has101010_125083720203" "" ""
```

## Step 4: Update classification_cases.py

Open `tests/e2e/classification_cases.py` and add an entry BEFORE the closing `]` of the GAMES list. Use the Edit tool, replacing the last `]` with the new entry + `]`:

```python
    {
        "game_id": "{GTID}",
        "brilliant_indices": [{BRILLIANT_INDICES}],  # comment with move numbers
        "great_indices": [{GREAT_INDICES}],  # comment with move numbers
        "notes": {
            {idx}: "{SAN} — great",  # one line per labeled move
        },
    },
]
```

For "aucun coup !! ni !":
```python
    {
        "game_id": "{GTID}",
        "brilliant_indices": [],
        "great_indices": [],
        "notes": {},
    },
]
```

## Step 5: Test and commit

Run the test:
```bash
uv run pytest tests/test_classifier.py::test_classifier_score_regression -v
```

If PASSED, commit:
```bash
git add tests/e2e/fixtures/classification_ground_truth.json tests/e2e/classification_cases.py && git commit -m "Add {opponent} game to classification ground truth ({N} total)"
```

Where `{N}` is the total number printed by the add script.

If FAILED: report the error to the user, do NOT commit.

## Rules

- Use `classify_move` from `chess_self_coach.classifier` — NOT JS
- **BOTH SIDES**: count !! and ! for both players
- Process !! games before !-only games
- Commit after each game
