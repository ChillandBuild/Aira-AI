# Agent Dispatch Rules

## When to Spawn (autonomous — never ask the user)
Spawn when a task has 2+ of these that are independent:
- Schema migration (SQL / Supabase)
- API route (FastAPI)
- Frontend component / page (Next.js)
- Service / business logic (Python)
- Codebase research (reading existing patterns)

## Agent Types

| Agent | Use for |
|---|---|
| `Explore` | Reading existing code, finding patterns, checking what's built |
| `general-purpose` | Implementing isolated features (single route, component, service) |
| `Plan` | Before complex multi-file features |

## Parallel Patterns

**3-layer feature (schema + API + frontend):**
- Agent 1: schema migration + Supabase types
- Agent 2: FastAPI routes + Pydantic schemas
- Agent 3: Next.js page/component
Launch all three in one message.

**Research + implement:**
- Agent 1 (Explore): read existing code, report patterns
- Wait → Agent 2: implement
Sequential only.

**Multi-page frontend (independent pages):** One agent per page, all parallel.

**Backend service + frontend hook:** Both parallel if interface is known upfront.

## Context Scoping Rules
Subagents start cold — they see none of CLAUDE.md, memory, or this chat. Paste their context inline.
Each agent prompt must include:
1. The specific task (1–2 sentences)
2. The Hard Invariants from `.agents/context/stack-and-rules.md` (paste the section — it's short)
3. The relevant `graphify-out/wiki/<Module>.md` article for the domain (copy the section, don't make the agent go read it)
4. Relevant rows from `.agents/decisions/log.md` or `.agents/projects/active-backlog.md` if they apply
5. NOT the full CLAUDE.md / .agents tree

## Agent Prompt Template
```
Task: <1-2 sentence description>

Stack: FastAPI (backend/app/), Next.js 14 (frontend/app/dashboard/), Supabase, Groq.

Context:
<paste relevant graphify-out/wiki/<Module>.md section>

Constraints:
<paste the Hard Invariants section from .agents/context/stack-and-rules.md>

Write code only. No explanations. No trailing summaries.
```

## Do Not Spawn For
- Single-file edits
- Bugs touching fewer than 3 files
- Sequential tasks where each step needs the previous result
