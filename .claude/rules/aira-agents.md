# Agent Dispatch Rules (Aira-specific; the standing permission to spawn lives in ~/.claude/CLAUDE.md)

## Agent Types
| Agent | Use for |
|---|---|
| `Explore` | Reading existing code, finding patterns, checking what's built |
| `general-purpose` | Implementing isolated features (single route, component, service) |
| `Plan` | Before complex multi-file features |

## Parallel Patterns
- 3-layer feature: Agent 1 schema migration + Supabase types, Agent 2 FastAPI routes + Pydantic schemas,
  Agent 3 Next.js page/component. Launch all three in one message.
- Research then implement: Explore first, wait, then implement. Sequential only.
- Independent frontend pages: one agent per page, all parallel.

## Agent Prompt Contents (subagents start cold — paste context inline, never the full CLAUDE.md)
1. The task (1–2 sentences), stack: FastAPI (backend/app/), Next.js 14 (frontend/app/dashboard/), Supabase, Groq.
2. Hard Invariants section from `.agents/context/stack-and-rules.md`.
3. The relevant `graphify-out/wiki/<Module>.md` section.
4. Relevant rows from `.agents/decisions/log.md` / `.agents/projects/active-backlog.md`.
5. "Write code only. No explanations. No trailing summaries."

## Do Not Spawn For
- Single-file edits
- Bugs touching fewer than 3 files
- Sequential tasks where each step needs the previous result
