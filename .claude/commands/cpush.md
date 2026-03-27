Run tests, bump patch version if needed, commit, and push to remote.

Steps:
1. Run the full test suite: `uv run pytest tests/ -v` (unit + e2e). If any test fails, STOP and report the failure. Do NOT commit or push.
2. Check if there are changes to commit (`git status`). If working tree is clean, inform the user and stop.
3. Check if the version was already bumped in this set of changes by comparing the version in `pyproject.toml` against the last committed version (`git show HEAD:pyproject.toml`). If the version is the same (not yet bumped), bump the patch version in `pyproject.toml` (e.g. 0.1.11 → 0.1.12). Note: `__init__.py` reads the version from package metadata at runtime, so only `pyproject.toml` needs updating.
4. Stage all changed files with `git add` (list specific files, not `-A`). Never stage `.env`, `config.json`, or `training_data.json`.
5. Create a commit with a descriptive message based on the changes. End with `Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>`.
6. Push to the current branch.
7. If there is an open PR for this branch, watch the CI checks and report the result.

Optional argument: $ARGUMENTS is used as the commit message. If not provided, generate one from the staged changes.
