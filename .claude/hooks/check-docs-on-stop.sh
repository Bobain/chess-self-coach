#!/usr/bin/env bash
# Stop hook: block if docs-relevant code was modified and docs have not been checked.

set -euo pipefail

INPUT=$(cat)

# Anti-loop: if already handling a stop hook, let through
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [ "$STOP_HOOK_ACTIVE" = "true" ]; then
  exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
MARKER="$REPO_ROOT/.claude/.pending-docs-check"

if [ ! -f "$MARKER" ]; then
  exit 0
fi

cat <<'EOF'
{"decision": "block", "reason": "DOCS SYNC — Source code that affects documentation was modified during this session. Check if docs/*.md needs updating:\n- trainer.py → training.md\n- cli.py → cli.md, setup.md\n- app.js → training.md, index.md\nIf the docs are already up to date, remove the marker with: rm -f .claude/.pending-docs-check"}
EOF
