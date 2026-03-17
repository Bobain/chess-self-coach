#!/usr/bin/env bash
# PostToolUse hook (Write|Edit|Bash): detect [Dev] commands or trainer.py changes
# that require /review-training. Creates a marker so the Stop hook can force the review.

set -euo pipefail

INPUT=$(cat)

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
MARKER="$REPO_ROOT/.claude/.pending-review-training"

# Already flagged this session
[ -f "$MARKER" ] && exit 0

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')

# Check Bash commands for [Dev] flags
if [ "$TOOL_NAME" = "Bash" ]; then
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
  # Match any [Dev] option: --fresh, --refresh-explanations, and future dev flags
  if echo "$COMMAND" | grep -qE -- '--fresh|--refresh-explanations'; then
    touch "$MARKER"
  fi
  exit 0
fi

# Check Write|Edit for trainer.py modifications
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty')
[ -z "$FILE_PATH" ] && exit 0

case "$FILE_PATH" in
  */trainer.py)
    touch "$MARKER"
    ;;
esac

exit 0
