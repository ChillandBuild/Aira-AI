---
name: "source-command-second-brain-close"
description: "Session-end checklist — mechanical health check, route new knowledge, refresh the wiki if code changed"
---

# source-command-second-brain-close

Use this skill when the user asks to run the migrated source command `second-brain-close`.

## Command Template

When this skill is invoked, do the following in order:

## Step 1 — Run the mechanical health check
Run `make second-brain-close` (or `python3 scripts/second_brain_close.py`). It checks
dead router links, gitleaks credential scan, `.gitignore`-based generated-artifact churn,
lefthook liveness, and stale `.agents/` claims. Report its findings. Fix or explicitly
flag each one — do not silently ignore anything it surfaces.

## Step 2 — Save what's worth remembering, ROUTED to the right brain
Review the session and route each learning by type — do NOT dump everything into memory/:
- **Project facts** (decisions, architecture, fixes, new features, migrations) → the repo brain:
  - settled decision / migration → append to `.agents/decisions/log.md`
  - load-bearing gotcha / how-a-subsystem-works → `.agents/context/subsystem-notes.md`
  - open item / tech debt → `.agents/projects/active-backlog.md`
- **Working-style** (user preferences, corrections to how I work, patterns about THIS user) → `memory/` (a `feedback_*` or `user_profile` file).
- Never create `project_*` files in memory/ — that knowledge belongs in `.agents/`.

## Step 3 — Audit
- memory/: delete anything no longer true, merge duplicates, keep it to user + feedback only, update MEMORY.md to match.
- If you wrote to `.agents/`, make sure it's staged for commit.

## Step 4 — Refresh the architecture map if code changed (automatic)
Check whether code changed this session:
`find backend/app frontend/app -type f \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' \) -newer graphify-out/manifest.json 2>/dev/null | head -1`
- If it returns ANY file → run `make wiki-refresh` (AST `--force` re-extract + rebuild; fast, no LLM). The wiki is git-ignored (local-only), so this never creates a commit. Report the new article count.
- If it returns nothing → skip (no code changed).
Do this as part of `/second-brain-close` so the user never has to run `/wiki` separately.
