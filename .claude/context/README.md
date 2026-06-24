# .claude/context/

Hand-curated primers pasted **inline into subagent prompts** (see [aira-rules](../rules/aira-agents.md)).
Subagents start cold — they don't see CLAUDE.md or memory. These files are the minimum durable
context an agent needs to not break things.

## Drift policy — read before editing
- **CLAUDE.md is canonical** for invariants/build-state. Files here are extracts for pasting.
- Keep these SHORT and SLOW-CHANGING. Anything fast-moving belongs in the auto-built wiki, not here.
- **Domain knowledge is NOT duplicated here** — it lives in `graphify-out/wiki/<Module>.md`, which
  regenerates from code via `/wiki`. Point agents at the wiki article; don't copy it.

## Files
| File | Holds | Source of truth |
|---|---|---|
| `invariants.md` | The 13 "Never Break" rules | mirror of CLAUDE.md → Hard Invariants |

## When the invariants in CLAUDE.md change
Update `invariants.md` in the same commit. They change rarely (that's the point).
