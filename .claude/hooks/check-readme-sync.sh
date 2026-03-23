#!/usr/bin/env bash
# PostToolUse hook (Write|Edit): detect code file changes that may require README update.
# Creates a marker so the Stop hook can remind to check README.

set -euo pipefail

INPUT=$(cat)

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
README_MARKER="$REPO_ROOT/.claude/.pending-readme-check"
FLOWS_MARKER="$REPO_ROOT/.claude/.pending-flows-check"
DOCS_MARKER="$REPO_ROOT/.claude/.pending-docs-check"

# Extract the file path from the tool input
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty')
[ -z "$FILE_PATH" ] && exit 0

# README marker: only these paths count as "code"
if [ ! -f "$README_MARKER" ]; then
  case "$FILE_PATH" in
    */src/*|*/pwa/*.js|*/pwa/*.html|*/pwa/*.css|*/tests/*|*/pyproject.toml|*/.github/workflows/*)
      touch "$README_MARKER"
      ;;
  esac
fi

# Flows marker: flow-relevant source files
if [ ! -f "$FLOWS_MARKER" ]; then
  case "$FILE_PATH" in
    */src/chess_self_coach/trainer.py|*/src/chess_self_coach/server.py|*/src/chess_self_coach/lichess.py|*/src/chess_self_coach/config.py|*/src/chess_self_coach/cli.py|*/pwa/app.js|*/pwa/sw.js)
      touch "$FLOWS_MARKER"
      ;;
  esac
fi

# Docs marker: source files whose changes may require docs/*.md updates
if [ ! -f "$DOCS_MARKER" ]; then
  case "$FILE_PATH" in
    */src/chess_self_coach/trainer.py|*/src/chess_self_coach/cli.py|*/pwa/app.js)
      touch "$DOCS_MARKER"
      ;;
  esac
fi

exit 0
