# Aira AI — Identity & Persona Guide

## Core Identity
- **Target Market**: Generic B2B SaaS for businesses doing WhatsApp lead-gen + telecalling.
- **North Star**: No single block, flag, or outage stops a client's lead-gen for >5 minutes.
- **Dev Style**: Solo dev. Terse. Code over prose. No trailing summaries. No explanations unless asked.

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
