---
name: "source-command-brief"
description: "Turn a rough idea into a sharp brief with Aira's real files and rules. Shows it, waits for \"go\", then routes into the gstack sprint. Never builds before \"go\"."
---

# source-command-brief

Use this skill when the user asks to run the migrated source command `brief`.

## Command Template

The founder typed: $ARGUMENTS

Job: sharpen the idea into a short brief. You do NOT build, edit code, or run fixes in this skill until the
founder says "go". Plain language, short sentences, ELI5 where a term is technical. Recommendation first.

Mode: if the first word of the ask is "quick", use QUICK mode (Goal, Done when, Must respect, Not doing only; no
open questions; 5 lines). Otherwise FULL mode.

## Step 1 — Decode
Read `.agents/context/prem-glossary.md` (small). Replace the founder's words with their meaning. If a word is
ambiguous (for example "dashboard": customer dashboard or make rnd-dashboard), ask ONE question and stop.

## Step 2 — Classify
bug / feature / UI / research / chore. Also flag if it touches: DB, WhatsApp, auth, webhooks, payments, RLS.

## Step 3 — Look up real Aira (cheap, hard limits)
HARD STOP budget, count as you go: 2 graphify queries; 1 `.agents/` read (ONE grep or section read across
`decisions/log.md` + `active-backlog.md` + subsystem-notes counts as that one); 3 file reads (a Read or a grep of a
source file each counts as one). The glossary and this file are free. When the budget is spent, stop looking and write
"not checked: <what>" in the brief. Never read a whole file "for context".
Order (from CLAUDE.md): graphify first, then ONE wiki or `.agents/context/subsystem-notes.md` section, then targeted reads.
```
cd "/Users/prem/Documents/Aira AI" && $(cat graphify-out/.graphify_python) -m graphify query "<question>" --budget 1200
```
- DB or schema ask: the wiki is code only. Use the migration index in `.agents/decisions/log.md` (grep) and live
  Supabase list_tables (read-only). Never write SQL that changes data here.
- Before proposing anything, grep `.agents/decisions/log.md` and `.agents/projects/active-backlog.md` for it. If it was
  already dropped or decided, say so in the brief.
- Only name a file, function or table you actually found this run. If not found, write "not found: <what>".

## Step 4 — Write the brief
Sections, in this order, plain words:
- **Goal and why**: one sentence each.
- **Files**: real file:line from Step 3 (skip in QUICK if none found).
- **Done when**: checkable proof only: a failing-then-passing test, a screenshot, a measured number. Never "looks good".
- **Must respect**: pick ONLY the rules that apply, quote them short.
  - Always consider these charter rules (`.agents/rnd/charter.md` Part 1): evidence labels (FACT / OBSERVATION /
    INFERENCE / HYPOTHESIS); customer privacy (aggregates only, no phone numbers or names, no quote over 8 words);
    never spend a client's money (no AI evals or LLM calls on a client tenant's key); cheapest test first; respect what
    is already decided; plain language.
  - If it touches DB, WhatsApp or security, add the relevant hard invariants from `.agents/context/stack-and-rules.md`
    (read its "Hard Invariants" section): 24h window and templates outside it; opt_in_source gate on broadcasts;
    tenant isolation (RLS plus `get_tenant_and_role()`); webhook signature check; DNC and opt-out fields; lead score 0-10.
  - Always: local backend only via `make dev-backend` (never plain uvicorn); nothing live without asking.
- **Not doing**: what is out of scope, so the work does not sprawl.
- **Open questions** (FULL only): at most 3, each with a recommended answer and a one-line reason.

## Step 5 — STOP
Show the brief and end with: `Say "go", or send edits (for example "q1 yes, add a Not-doing line, go").`
Do nothing else. Do not start work, do not save the file yet.

If the founder corrects one of their own words or meanings, append it to `.agents/context/prem-glossary.md`
(one line, keep the "founder's words" label) and tell them in one line.

## Step 6 — On "go" (or "go" plus edits)
1. Apply the edits, then save the brief to `.agents/briefs/<YYYY-MM-DD>-<short-name>.md` (create the folder if missing).
2. From now on work from the saved brief, not from the original messy wording. Re-read it before each stage.
3. Route into the gstack sprint (pinned 1.91.2.0, prefix gstack-). If several rows apply, run all that apply:

| Ask | Route |
|---|---|
| bug | `/gstack-investigate` (root cause first, then a regression test that fails before the fix and passes after) |
| feature or idea | `/gstack-office-hours`, then `/gstack-autoplan`, then show the plan and WAIT for approval, then build |
| UI change | `/gstack-plan-design-review` on the plan; after building `/gstack-qa` (local backend only via `make dev-backend`, point the frontend with NEXT_PUBLIC_API_URL=http://localhost:8000) |
| auth, webhooks, payments, RLS | also `/gstack-cso` (and the security-reviewer agent for new auth, webhook or payment code) |
| research | answer in chat using an Explore agent for wide reads; no build, no branch |
| chore | write a 3-step plan, wait for approval, then do it |

4. Every route that changed code ends with `/gstack-review` on the diff, then `make verify` (must say RESULT: PASS).
   Frontend-only: typecheck and lint also.
5. Before finishing: `git fetch`, check `HEAD..origin/main` for teammate commits on the same files; if any, rebase
   and re-run the checks.
6. STOP. Do not push or deploy. The founder pushes. (`/gstack-ship` and deploys are user-only.)

## Rules for this skill
- Under 40 lines of brief output in FULL mode. If it is longer, cut, don't summarise.
- Say plainly what you could not find or verify. Silence must not imply success.
- Never invent a file, table, number or rule. "Not found" is a valid answer.
