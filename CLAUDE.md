# Aira AI — Agent Operating Manual

## Core Commands
- **Backend Dev**: `make dev-backend` (safe mode: scheduler paused, outbound dry-run). Never plain `uvicorn` on a laptop — it shares the live DB.
- **Backend Build/Deps**: `cd backend && pip install -r requirements.txt`
- **Backend Test**: `cd backend && python -m pytest` (runs tests under `backend/tests/`). Use `python -m pytest`, not bare `pytest` — several test modules import `app.*` without adding the backend dir to `sys.path`, so bare `pytest` dies at collection with `ModuleNotFoundError: No module named 'app'`. `python -m` puts the cwd on `sys.path` and the suite passes (2553 tests collected as of 2026-09-29). Run it from `backend/`, not the repo root.
- **Frontend Dev**: `cd frontend && npm run dev`
- **Frontend Build**: `cd frontend && npm run build`
- **Frontend Typecheck**: `cd frontend && npm run typecheck`
- **Frontend Lint**: `cd frontend && npm run lint`
- **Production Run (Render)**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (executed from `backend/` directory)

---

## How to Work Efficiently (low context — this is the DEFAULT, no need to be told)
- The brain is **queried, not loaded**. Never read whole files or the whole wiki "to get context."
- Lookup order for ANY task: (1) `graphify query "<question>"` → exact file:line, (2) the ONE relevant `graphify-out/wiki/<Module>.md` or `.agents/context/subsystem-notes.md` section, (3) at most 2–3 targeted reads. Full-file reads are the last resort.
- Pull ONLY the `.agents/` file the task scope points to (below) — never preload all of them.
- **Database/schema work:** the wiki is CODE only. Use the migration index in [decisions/log.md](.agents/decisions/log.md) + live Supabase `list_tables`/`execute_sql` — NOT the wiki.
- This runs automatically for every task; the user does NOT have to say "use the wiki/graph."

## gstack setup (pinned — same version on every machine)
The sprint below needs gstack **1.91.2.0** installed with the `gstack-` prefix. Install steps + upgrade policy:
[.agents/context/gstack-setup.md](.agents/context/gstack-setup.md). If a session starts with a "gstack is NOT installed"
or "pinned to" warning (scripts/rnd/check-gstack.sh), tell the user; never upgrade it yourself.

## How we work — the gstack sprint (every task, no need to be told)
- Bug, error, "it stopped working" → `/gstack-investigate`. Root cause before any fix;
  a regression test that fails before the fix and passes after.
- New feature or idea → `/gstack-office-hours` → `/gstack-autoplan` → show the plan and
  wait for approval → build.
- UI change → `/gstack-plan-design-review` on the plan; after building, `/gstack-qa`
  as the UI test tenant — on the live site, or locally. Local backend ONLY via `make dev-backend`
  (plain uvicorn would run the scheduler and message real leads from the live DB; see
  subsystem-notes.md). Point the local frontend at it with NEXT_PUBLIC_API_URL=http://localhost:8000.
- Auth, webhooks, payments, RLS → also `/gstack-cso`.
- Before any commit → `/gstack-review` on the diff, plus `python -m pytest` (backend)
  or typecheck + lint (frontend).
- Before finishing → `git fetch`, check `HEAD..origin/main` for teammate commits on the
  same files; if any, rebase and re-run the tests.
- Weekly → `/gstack-retro`.
- `/gstack-ship`, `/gstack-land-and-deploy`, `/gstack-setup-deploy` are user-only
  (hidden from agents via skillOverrides). Push or deploy only when the user says so.
  A push to `main` auto-deploys the backend on Render.

## Agent Routing Instructions
To prevent context dilution, general invariants and rules have been split into modular guides. **Always read these files first based on the scope of your task:**

1.  **Identity, Dev Persona & Code Style Rules**:
    *   Location: [.agents/context/identity.md](.agents/context/identity.md)
    *   Read when: You start a new session or need to review coding styles, formatting preferences, and file/API response conventions.
2.  **Invariants, Tech Stack & File Map**:
    *   Location: [.agents/context/stack-and-rules.md](.agents/context/stack-and-rules.md)
    *   Read when: Modifying DB calls, working with WhatsApp/TeleCMI webhooks, routing outbound calls, or checking security policies (RLS).
3.  **Historical Decisions & DB Migrations**:
    *   Location: [.agents/decisions/log.md](.agents/decisions/log.md)
    *   Read when: Seeking context on why specific modules (e.g., Bot Flow Builder) were dropped, checking migration histories, or verifying schema structures.
4.  **Active Roadmap & Technical Debt**:
    *   Location: [.agents/projects/active-backlog.md](.agents/projects/active-backlog.md)
    *   Read when: Checking current backlog tasks or reviewing known tech debt (e.g., orphaned tables).
5.  **Subsystem Notes & Load-Bearing Gotchas**:
    *   Location: [.agents/context/subsystem-notes.md](.agents/context/subsystem-notes.md)
    *   Read when: Editing broadcasts/delivery, scoring, call evaluation, knowledge RAG, frontend perf, telecalling, chat escalation, or operator console — holds the *why* and the traps the wiki can't.
6.  **Security & Vulnerability Guidance**:
    *   Location: [.agents/context/security-checklist.md](.agents/context/security-checklist.md)
    *   Read when: Touching auth, webhooks, payments (Razorpay), file uploads, RLS policies, or any route reading `tenant_id`. Escalate to the `security-reviewer` agent for new auth/webhook/payment code or RLS changes.
7.  **AI Reply Master Prompt**:
    *   Location: [docs/whatsapp-master-prompt.md](docs/whatsapp-master-prompt.md)
    *   Read when: Touching `_build_base_prompt()` / `ai_reply.py`'s prompt assembly, or the `ai_prompts` table's `master` row — this is the canonical text and explains why the per-channel rows (`whatsapp_reply` etc.) are dead weight.

## Agent skills

### Issue tracker

Issues live in GitHub Issues for `ChillandBuild/Aira-AI`, managed via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context layout — `CONTEXT.md` + `docs/adr/` at the repo root (created lazily as needed). See `docs/agents/domain.md`.

