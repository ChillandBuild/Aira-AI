# Aira AI — Identity & Persona Guide

## Core Identity
- **Target Market**: Generic B2B SaaS for businesses doing WhatsApp lead-gen + telecalling.
- **North Star**: No single block, flag, or outage stops a client's lead-gen for >5 minutes.
- **Dev Style**: Two-person team (Prem + teammate keerthi-sarav, who also pushes to main — never assume uncommitted changes are Prem's; git-log the teammate's recent commits against a plan's files before finalizing it). Terse. Code over prose. No trailing summaries. No explanations unless asked.

- **Brand**: dashboard, operator screens and SDK say **Anril** (renamed 2026-10-07); repo, docs and internal identifiers still say Aira on purpose. The landing page still says Aira — unconfirmed whether intentional, ask before changing (see decisions/log.md).
- **Operator-run product**: Prem configures every tenant (channels, AI provider keys, console settings) and hands clients a working account. New credential/settings UI defaults to the **operator console**, not the client dashboard, unless it is the client's own external account (their Razorpay, their Telegram bot). Per-tenant AI keys exist for per-client cost tracking, not "bring your own key."

## Design System (match it, don't invent)
- Tokens live in `frontend/tailwind.config.ts` + `frontend/app/globals.css` — grep them before writing ANY color: `primary` #5b21b6 (violet), `background` #faf8f5 (cream), `primary-dark/light/muted`, `brand-gradient` (#2e1065→#5b21b6, 135deg/`to-br`), `ink/ink-muted/ink-secondary`, `badge-violet`, plus the violet/amber/sky/emerald accent tiles in `SettingsSection.tsx`.
- Accent colour only on interactive/accent surfaces (buttons, active states, focus rings, chart accents, selected rows); cream stays the stage.
- No raw hex or stock Tailwind colour classes (`bg-emerald-500`…) without checking an existing token covers it. A genuinely new semantic need = flag a new token to Prem, don't pick a shade solo.
- Prefer composition/content changes over new colours; avoid the generic "badge pill + gradient headline + stock dashboard screenshot" SaaS look.

## Agent Dispatch
- Spawn sub-agents automatically for tasks with 2+ independent work units.
- Parallel pattern: schema + API route + frontend page → all 3 in one message.

## Response Style Invariants
- One sentence per progress update while working.
- No trailing summaries.
- No inline comments in code unless the *WHY* is highly non-obvious.
- No multi-line docstrings.
- Mark `TodoWrite` tasks done immediately after finishing.
- File references must be clickable: `[basename](file:///absolute/path/to/file#Lline)` or `[basename](file:///absolute/path/to/file)`. Do NOT wrap links in backticks.
- API errors must follow this contract: `{"error": "message", "code": "ERROR_CODE"}`.
- All backend routes must be prefixed with `/api/v1/`.
- Backend list/query routes must support pagination: `?page=1&limit=50`.
