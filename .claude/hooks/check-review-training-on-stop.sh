#!/usr/bin/env bash
# Stop hook: remind to run /review-training if trainer.py was modified.

set -euo pipefail

INPUT=$(cat)

STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [ "$STOP_HOOK_ACTIVE" = "true" ]; then
  exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
MARKER="$REPO_ROOT/.claude/.pending-review-training"

if [ ! -f "$MARKER" ]; then
  exit 0
fi

cat <<'EOF'
{"decision": "block", "reason": "REVIEW TRAINING — Du code de génération de texte ou une commande [Dev] a été exécutée. Tu DOIS lancer /review-training maintenant pour vérifier la qualité des textes. Une fois terminé, supprime le marker avec : rm .claude/.pending-review-training"}
EOF
