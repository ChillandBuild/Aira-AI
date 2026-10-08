# Aira AI — Identity & Persona Guide

## Core Identity
- **Target Market**: Generic B2B SaaS for businesses doing WhatsApp lead-gen + telecalling.
- **North Star**: No single block, flag, or outage stops a client's lead-gen for >5 minutes.
- **Dev Style**: Two-person team (Prem + teammate keerthi-sarav, who also pushes to main — never assume uncommitted changes are Prem's; git-log the teammate's recent commits against a plan's files before finalizing it). Terse. Code over prose. No trailing summaries. No explanations unless asked.

- **Brand**: dashboard, operator screens and SDK say **Anril** (renamed 2026-10-07); repo, docs and internal identifiers still say Aira on purpose. The landing page still says Aira — unconfirmed whether intentional, ask before changing (see decisions/log.md).
- **Operator-run product**: Prem configures every tenant (channels, AI provider keys, console settings) and hands clients a working account. New credential/settings UI defaults to the **operator console**, not the client dashboard, unless it is the client's own external account (their Razorpay, their Telegram bot). Per-tenant AI keys exist for per-client cost tracking, not "bring your own key."

## Design System (match it, don't invent)
- **Navy + Teal (rebrand 2026-10-08).** Tokens live in `frontend/tailwind.config.ts` + `frontend/app/globals.css` + `frontend/lib/color-tokens.ts` (keep all three in sync) — grep them before writing ANY color: `primary` #038285 (teal, = primary-800) for buttons/links/active states; `primary-950` and `navy` #0A1528 for dark sections; `ink` #0A1528 (navy) for headings/text; `navy-accent` #3fbcbf for teal text/icons ON navy (#038285 on navy fails small-text contrast); backgrounds white / slate #f1f5f9; `success` #15803d; `brand-gradient` navy #0A1528→#13284A. `badge-violet` is a legacy class name that now renders teal.
- No WhatsApp greens (#25D366, #075E54, #DCF8C6) and no old violet — `frontend/lib/brand-guard.test.ts` fails if they return. Logo = `AnrilLogo` (lowercase "anril" + "AI"; `tone="dark"` on navy). Product name stays "Anril AI".
- Accent colour only on interactive/accent surfaces (buttons, active states, focus rings, chart accents, selected rows); white/slate stays the stage.
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
