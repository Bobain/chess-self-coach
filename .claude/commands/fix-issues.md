Collect open bug issues from GitHub, analyze root causes, create reproducing E2E tests, and fix the code.

## Workflow

### 1. Collect open issues

Run: `gh issue list --label bug --state open --json number,title,body,createdAt`

If no issues found, report "No open bug issues" and stop.

### 2. Analyze and deduplicate

For each issue, parse the body (crash reporter format: endpoint, version, traceback).

Group issues by root cause:
- Same exception type + same file = likely same bug
- Same endpoint + different errors = different bugs

Present a summary table:
| # | Title | Root cause | Duplicates |
|---|-------|-----------|------------|

Ask the user to confirm before proceeding.

### 3. For each unique root cause

Follow this loop strictly:

a. **Create a reproducing E2E test** in `tests/e2e/test_bug_fixes.py`:
   - Hit the failing endpoint with the parameters from the issue
   - Assert it returns 200 (not 500)
   - Name the test `test_fix_issue_N` where N is the primary issue number

b. **Run the test** — confirm it FAILS (red):
   `pytest tests/e2e/test_bug_fixes.py::test_fix_issue_N -x`

c. **Fix the code** — make the minimal change to resolve the root cause

d. **Run basedpyright** on changed files — fix any type errors

e. **Run all tests** — confirm everything passes:
   `pytest tests/ -x`

f. **Commit** with message: `Fix #N: <description>`

### 4. Close duplicates

For each duplicate issue:
`gh issue close <dup_number> --comment "Duplicate of #<primary>. Fixed in <commit_sha>."`

### 5. Summary

Report:
- Issues fixed (with links)
- Tests added
- Duplicates closed
- Any issues that could NOT be fixed (with explanation)
