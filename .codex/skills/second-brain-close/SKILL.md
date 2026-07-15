---
name: second-brain-close
description: Session-end workflow for the Aira repo. Use when the user says "second-brain-close", "/second-brain-close", "close the session", asks to close out a session, save project notes, refresh the local wiki after code changes, show repo status/backlog, or prepare the next-session starter. (Formerly "aira-status" — renamed 2026-07-15 so every project uses the same trigger name; update any saved muscle-memory/snippets on this machine.)
---

# Second Brain Close

Run this from the repo root. Treat it as the Codex version of `.claude/commands/second-brain-close.md`.

## Workflow

1. Run the mechanical health check: `make second-brain-close` (or `python3 scripts/second_brain_close.py`).
   It checks dead router links, gitleaks credential scan, `.gitignore`-based generated-artifact
   git churn, lefthook liveness, and stale `.agents/` claims. Report its findings — fix or
   explicitly flag each one, don't silently ignore anything it surfaces.
2. Review the current session and decide what is worth preserving.
3. Route durable project knowledge to `.agents/`, not user memory:
   - Settled decisions, migrations, major fixes, or features: append to `.agents/decisions/log.md`.
   - Load-bearing subsystem behavior or gotchas: append to `.agents/context/subsystem-notes.md`.
   - Open items or technical debt: append to `.agents/projects/active-backlog.md`.
4. Reserve user memory for working-style preferences only. Do not create `project_*` memory files.
5. Audit `memory/` only if it exists and is readable in the environment:
   - Remove or update stale user-preference notes.
   - Merge duplicates.
   - Keep memory focused on user profile and feedback.
6. If `.agents/` files were changed, report that they should be staged or stage them only if the user asked.
7. Refresh the local architecture wiki when source files changed after `graphify-out/manifest.json`.

## Wiki Refresh Check

Prefer PowerShell in this Windows workspace:

```powershell
$manifest = "graphify-out\manifest.json"
if (Test-Path $manifest) {
  Get-ChildItem backend\app, frontend\app -Recurse -Include *.py,*.ts,*.tsx |
    Where-Object { $_.LastWriteTime -gt (Get-Item $manifest).LastWriteTime } |
    Select-Object -First 1
}
```

If this returns a file, run:

```powershell
make wiki-refresh
```

If `make` is unavailable, inspect `Makefile` and run the equivalent commands. Report the generated article count and note that `graphify-out/wiki/` is local-only when ignored.

## Output

Report:

- What was saved to `.agents/`, if anything.
- Whether the wiki was refreshed or skipped.
- Current `git status --short --branch`.
- The top active backlog items, if `.agents/projects/active-backlog.md` exists.
- A short next-session starter.
