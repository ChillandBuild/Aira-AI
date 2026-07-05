# Aira AI — Stack, Configuration, & Invariants

## Technology Stack
| Layer | Tech | Location |
|---|---|---|
| Backend | FastAPI, Python 3.11+, Pydantic v2 | backend/app/ |
| DB | Supabase (PostgreSQL + Realtime) | — |
| Frontend | Next.js 14 App Router, TypeScript, Tailwind | frontend/app/dashboard/ |
| AI | Sarvam-30B for WhatsApp replies; Sarvam Saaras/Vision for transcription/OCR; Groq remains for scoring/coaching/digests/tuning/briefs | services/ai_reply.py, services/sarvam_client.py, services/scoring_engine.py |
| WhatsApp | Meta Cloud API Direct | — |
| Voice | TeleCMI click-to-call + recording | services/telecmi_client.py |
| Payments | Razorpay Payment Links API | services/payment_razorpay.py |
| Scheduler | APScheduler (AsyncIO) | app/main.py |
| Cache | In-process prompt cache (60s TTL) | ai_reply.py:_prompt_cache |

## Provider Decisions (Locked)
- **WhatsApp**: Meta Cloud API Direct.
- **Voice**: TeleCMI (click-to-call + recording).
- **AI providers**: Sarvam powers WhatsApp AI replies (`sarvam-30b`), call transcription (`saaras:v3`), and knowledge image OCR (Sarvam Vision). Groq still powers scoring, call coaching/digests, AI tuning, lead briefs, and conversation compaction until explicitly migrated. Do NOT add Gemini/OpenAI imports.
- **Payments**: Razorpay (Payment Links API — no SDK, direct httpx/httpx-async calls).

## Production Configs
- **Supabase Project ID**: `ayftynkgmfkaqmmnlmoc`
- **Supabase Region**: `ap-northeast-1`
- **WhatsApp Business Account (WABA) ID**: `meta_waba_id = 994218516456571`
- **Default Tenant ID**: `00000000-0000-0000-0000-000000000001`
- **Backend Production URL**: `https://aira-ai-5tfr.onrender.com`
- **WhatsApp Webhook URL**: `https://aira-ai-5tfr.onrender.com/webhook/whatsapp`
- **Instagram Webhook URL**: `https://aira-ai-5tfr.onrender.com/webhook/instagram/{tenant_id}`
- **Facebook Webhook URL**: `https://aira-ai-5tfr.onrender.com/webhook/facebook/{tenant_id}`
- **Telegram Webhook URL**: `https://aira-ai-5tfr.onrender.com/webhook/telegram/{tenant_id}`

## Hard Invariants (Never Break)
1. **Lead Score**: Always an integer 1–10.
2. **Segments**: A=Hot, B=Warm, C=Cold, D=Disqualified. Labels are immutable.
3. **WhatsApp Window**: 24h session window — approved templates only outside window.
4. **Segment Export**: All segment list routes must resolve: `GET /api/v1/leads?segment=A&format=csv`.
5. **Call Recordings**: Uploaded to Supabase Storage only, never saved to local disk.
6. **Multi-Tenancy & Security**: Isolation enforced at DB level (RLS policies) and app-layer (`get_tenant_and_role()`). All public tables have RLS enabled (migration 114). `anon` role EXECUTE privilege is revoked on definer functions.
7. **Broadcast Gate**: Bulk-send endpoint rejects leads with null `opt_in_source`.
8. **Template Submissions**: Meta API template submissions must use `meta_waba_id` (not `meta_phone_number_id`).
9. **Signature Checks**: WhatsApp webhooks must verify `X-Hub-Signature-256` before processing (returns 200 but drops invalid signature calls).
10. **Pipeline Independence**: `call_status` (telecalling outcomes) is orthogonal to lead `segment`. Voice outcomes do NOT write segment labels.
11. **DNC/Opt-Out**: DNC is lead-level (`do_not_call`), NOT a `call_logs.outcome` constraint. Voice opt-out sets `do_not_call`. Text opt-out sets `opted_out`.
12. **Admin Exclusion**: Owner/Admin filtered from all telecaller metrics (attendance, shift tracking, leaderboards, timeline metrics). Frontend Leaderboard filters admin via `callerIds` set. Profile page resolves admin card using `useAuthRole()`.

## Core Configuration Panels
- **InboxConfigPanel**: Chat escalation toggle on/off per behavioral triggers (A/B/C/D/F). Escales are trigger-only; handovers land `UNASSIGNED` in a shared pool.
- **TelecallingConfigPanel**: Auto-assign, per-segment routing (A/B/C/D), channels, contact recycling configurations, and shift hour limits.

## File Map & Routing Guidelines
- WhatsApp/Meta: [routes/webhook.py](file:///Users/prem/Documents/Aira%20AI/backend/app/routes/webhook.py), [services/meta_cloud.py](file:///Users/prem/Documents/Aira%20AI/backend/app/services/meta_cloud.py), [services/outbound_router.py](file:///Users/prem/Documents/Aira%20AI/backend/app/services/outbound_router.py)
- Voice/Telecalling: [routes/calls.py](file:///Users/prem/Documents/Aira%20AI/backend/app/routes/calls.py), [services/telecmi_client.py](file:///Users/prem/Documents/Aira%20AI/backend/app/services/telecmi_client.py), [services/call_summarizer.py](file:///Users/prem/Documents/Aira%20AI/backend/app/services/call_summarizer.py)
- Reassignment/Round-Robin: [services/assignment.py](file:///Users/prem/Documents/Aira%20AI/backend/app/services/assignment.py), [routes/assignment_log.py](file:///Users/prem/Documents/Aira%20AI/backend/app/routes/assignment_log.py), [main.py (scheduler sweeps)](file:///Users/prem/Documents/Aira%20AI/backend/app/main.py)
- Upload/Scripts/Recycler: [routes/telecalling_upload.py](file:///Users/prem/Documents/Aira%20AI/backend/app/routes/telecalling_upload.py), [routes/call_scripts.py](file:///Users/prem/Documents/Aira%20AI/backend/app/routes/call_scripts.py), [services/contact_recycler.py](file:///Users/prem/Documents/Aira%20AI/backend/app/services/contact_recycler.py)
- Leads & Scoring: [routes/leads.py](file:///Users/prem/Documents/Aira%20AI/backend/app/routes/leads.py), [services/scoring_engine.py](file:///Users/prem/Documents/Aira%20AI/backend/app/services/scoring_engine.py)
- Incidents: [routes/numbers.py](file:///Users/prem/Documents/Aira%20AI/backend/app/routes/numbers.py), [services/failover.py](file:///Users/prem/Documents/Aira%20AI/backend/app/services/failover.py), [routes/incidents.py](file:///Users/prem/Documents/Aira%20AI/backend/app/routes/incidents.py)
- Broadcasts/Templates: [routes/upload.py](file:///Users/prem/Documents/Aira%20AI/backend/app/routes/upload.py), [services/broadcast_executor.py](file:///Users/prem/Documents/Aira%20AI/backend/app/services/broadcast_executor.py), [routes/templates.py](file:///Users/prem/Documents/Aira%20AI/backend/app/routes/templates.py)
- Settings & Health: [routes/app_settings.py](file:///Users/prem/Documents/Aira%20AI/backend/app/routes/app_settings.py)
