# Hard Invariants — Never Break

> Frozen extract of CLAUDE.md → "Hard Invariants" for pasting into subagent prompts.
> CLAUDE.md is canonical; update both in the same commit when an invariant changes.

1. Lead score always integer 1–10.
2. Segments: A=Hot, B=Warm, C=Cold, D=Disqualified — labels immutable.
3. WhatsApp 24h session window — approved templates only outside window.
4. All segment lists: `GET /api/v1/leads?segment=A&format=csv`.
5. Call recordings → Supabase Storage only, never local disk.
6. Tenant isolation: DB-level via RLS + app-level via `get_tenant_and_role()`. All public tables have RLS.
7. Bulk-send endpoint rejects leads with null `opt_in_source`.
8. Template submission always uses `meta_waba_id` (NOT `meta_phone_number_id`).
9. AI model is Groq `llama-3.3-70b-versatile` — NO Gemini/OpenAI imports.
10. WhatsApp webhook verifies X-Hub-Signature-256 before processing — returns 200 but drops invalid.
11. `call_status` (telecalling pipeline) is orthogonal to A/B/C/D `segment` — call outcomes NEVER write segment.
12. DNC is lead-level (`do_not_call`), NOT a `call_logs.outcome` value. "Do not contact" also sets `opted_out`
    (`opted_out`=WhatsApp/broadcast, `do_not_call`=voice).
13. Admin (owner) is excluded from ALL telecaller metrics — no attendance, shift, leaderboard, or call stats.

## Conventions (always apply)
- All routes prefixed `/api/v1/`. Pagination `?page=1&limit=50`.
- API errors: `{"error": "message", "code": "ERROR_CODE"}`.
- Immutable patterns. No inline comments unless WHY is non-obvious. No trailing summaries.
- Stack: FastAPI (`backend/app/`), Next.js 14 App Router (`frontend/app/dashboard/`), Supabase, Groq.
