---
name: "source-command-aira-status"
description: "Session-end checklist — save memories, audit stale files, show backlog and session starter"
---

# source-command-aira-status

Use this skill when the user asks to run the migrated source command `aira-status`.

## Command Template

When this skill is invoked, do the following in order:

## Step 1 — Save what's worth remembering, ROUTED to the right brain
Review the session and route each learning by type — do NOT dump everything into memory/:
- **Project facts** (decisions, architecture, fixes, new features, migrations) → the repo brain:
  - settled decision / migration → append to `.agents/decisions/log.md`
  - load-bearing gotcha / how-a-subsystem-works → `.agents/context/subsystem-notes.md`
  - open item / tech debt → `.agents/projects/active-backlog.md`
- **Working-style** (user preferences, corrections to how I work, patterns about THIS user) → `memory/` (a `feedback_*` or `user_profile` file).
- Never create `project_*` files in memory/ — that knowledge belongs in `.agents/`.

## Step 2 — Audit
- memory/: delete anything no longer true, merge duplicates, keep it to user + feedback only, update MEMORY.md to match.
- If you wrote to `.agents/`, it's committed knowledge — make sure it's staged for commit.

## Step 3 — Refresh the architecture map if code changed (automatic)
Check whether code changed this session:
`find backend/app frontend/app -type f \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' \) -newer graphify-out/manifest.json 2>/dev/null | head -1`
- If it returns ANY file → run `make wiki-refresh` (AST `--force` re-extract + rebuild; fast, no LLM). The wiki is git-ignored (local-only), so this never creates a commit. Report the new article count.
- If it returns nothing → skip (no code changed).
Do this as part of `/aira-status` so the user never has to run `/wiki` separately.
