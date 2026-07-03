# Aira AI — Agent Operating Manual

## Core Commands
- **Backend Dev**: `cd backend && uvicorn app.main:app --reload`
- **Backend Build/Deps**: `cd backend && pip install -r requirements.txt`
- **Backend Test**: `cd backend && pytest` (runs tests under `backend/tests/`)
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
- `/graphify` = rebuild/update the graph itself (new content, not a lookup). When the user types
  it, invoke the Skill tool with `skill: "graphify"` before doing anything else.

## Agent Routing Instructions
To prevent context dilution, general invariants and rules have been split into modular guides. **Always read these files first based on the scope of your task:**

1.  **Identity, Dev Persona & Code Style Rules**:
    *   Location: [.agents/context/identity.md](file:///Users/prem/Documents/Aira%20AI/.agents/context/identity.md)
    *   Read when: You start a new session or need to review coding styles, formatting preferences, and file/API response conventions.
2.  **Invariants, Tech Stack & File Map**:
    *   Location: [.agents/context/stack-and-rules.md](file:///Users/prem/Documents/Aira%20AI/.agents/context/stack-and-rules.md)
    *   Read when: Modifying DB calls, working with WhatsApp/TeleCMI webhooks, routing outbound calls, or checking security policies (RLS).
3.  **Historical Decisions & DB Migrations**:
    *   Location: [.agents/decisions/log.md](file:///Users/prem/Documents/Aira%20AI/.agents/decisions/log.md)
    *   Read when: Seeking context on why specific modules (e.g., Bot Flow Builder) were dropped, checking migration histories, or verifying schema structures.
4.  **Active Roadmap & Technical Debt**:
    *   Location: [.agents/projects/active-backlog.md](file:///Users/prem/Documents/Aira%20AI/.agents/projects/active-backlog.md)
    *   Read when: Checking current backlog tasks or reviewing known tech debt (e.g., orphaned tables).
5.  **Subsystem Notes & Load-Bearing Gotchas**:
    *   Location: [.agents/context/subsystem-notes.md](file:///Users/prem/Documents/Aira%20AI/.agents/context/subsystem-notes.md)
    *   Read when: Editing broadcasts/delivery, scoring, call evaluation, knowledge RAG, frontend perf, telecalling, chat escalation, or operator console — holds the *why* and the traps the wiki can't.

