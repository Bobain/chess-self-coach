#!/usr/bin/env bash
# Stop hook: block if flow-relevant code was modified and flow docs have not been checked.

set -euo pipefail

INPUT=$(cat)

# Anti-loop: if already handling a stop hook, let through
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [ "$STOP_HOOK_ACTIVE" = "true" ]; then
  exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
MARKER="/tmp/chess-doc-markers/.pending-flows-check"

if [ ! -f "$MARKER" ]; then
  exit 0
fi

cat <<'EOF'
{"decision": "block", "reason": "FLOW DOCS SYNC — Flow-relevant code was modified during this session. Check if docs/flows/ needs updating:\n- trainer.py, config.py → data-flows.md\n- server.py, sw.js → system-flows.md\n- app.js, cli.py → user-flows.md\nIf the docs are already up to date, remove the marker with: rm -f /tmp/chess-doc-markers/.pending-flows-check"}
EOF
