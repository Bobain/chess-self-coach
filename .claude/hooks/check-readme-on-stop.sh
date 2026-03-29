#!/usr/bin/env bash
# Stop hook: block if code was modified and README sync has not been checked.

set -euo pipefail

INPUT=$(cat)

# Anti-loop: if already handling a stop hook, let through
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [ "$STOP_HOOK_ACTIVE" = "true" ]; then
  exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
MARKER="/tmp/chess-doc-markers/.pending-readme-check"

if [ ! -f "$MARKER" ]; then
  exit 0
fi

cat <<'EOF'
{"decision": "block", "reason": "README SYNC — Du code a été modifié pendant cette session. Vérifie si README.md et CONTRIBUTING.md (section Architecture) doivent être mis à jour (nouvelles commandes, options modifiées, workflow changé, sections CI/CD, distinction static demo / application). Pense aussi à docs/flows/ si des flux ont changé. Si la doc est déjà à jour, supprime le marker avec : rm -f /tmp/chess-doc-markers/.pending-readme-check"}
EOF
