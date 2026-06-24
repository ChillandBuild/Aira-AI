---
name: aira-status
description: Session-end checklist — save memories, audit stale files, show backlog and session starter
---

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
- If you wrote to `.agents/`, make sure it's staged for commit.

## Step 3 — Refresh the architecture map if code changed
If the session changed code (especially deletions), run `/wiki` so `graphify-out/wiki/` stays current. The Stop hook will also warn if >15 source files drifted.
