# P0 — Client-Critical Features QA Audit

You are QA-auditing Aira AI before first client deployment. Read CLAUDE.md for full context (stack, invariants, file locations).

## Task
Audit each feature below. For each: read the route, service, AND frontend page. Flag:
- Logic bugs (wrong conditions, missing checks, data not saved)
- Missing error handling (unhandled exceptions, silent failures)
- Broken data flow (frontend calls wrong endpoint, wrong field names, missing params)
- Hard invariant violations (see CLAUDE.md)
- Security gaps (missing tenant_id checks, unauthenticated endpoints)
- Race conditions

## Features to Audit

### 1. Client Self-Onboarding
- Backend: backend/app/routes/onboarding.py
- Frontend: frontend/app/dashboard/onboarding/
- Check: full flow from signup to dashboard, credential setup, tenant creation

### 2. Settings — Channel Credentials
- Backend: backend/app/routes/app_settings.py
- Frontend: frontend/app/dashboard/settings/ (ConnectChannelsPanel.tsx)
- Check: save/update WhatsApp/Instagram/Facebook/Telegram/TeleCMI/Groq credentials, input validation, secrets not leaked to frontend

### 3. Settings — Validate & Activate
- Endpoint: POST /api/v1/settings/activate
- Check: validates Meta token, subscribes webhook, error handling on invalid token, idempotency

### 4. Settings — Webhook Health Check
- Endpoint: GET /api/v1/settings/webhook-health
- Check: returns per-channel health status, handles missing credentials gracefully

### 5. Settings — Token Expiry Alerts
- Backend: main.py _check_token_health job (24h APScheduler)
- Check: creates token_invalid incidents correctly, doesn't duplicate incidents

### 6. WhatsApp Inbound Webhook
- Backend: backend/app/routes/webhook.py
- Check: X-Hub-Signature-256 verification (returns 200 but drops invalid), message routing, 24h session window enforcement, status callbacks (delivered/read/failed)

### 7. AI Reply Pipeline
- Backend: backend/app/services/ai_reply.py + knowledge_service.py + embeddings.py
- Check: Knowledge Base RAG → Groq reply flow, prompt cache (60s TTL), ai_auto_reply toggle respected, reply_source badge set correctly, model is Groq llama-3.3-70b-versatile (NOT Gemini)

### 8. Lead CRUD
- Backend: backend/app/routes/leads.py
- Frontend: frontend/app/dashboard/leads/
- Check: create/read/update/delete, pagination (?page=1&limit=50), segment filtering, CSV export, tenant isolation

### 9. Lead Scoring (Score Engine v2)
- Backend: backend/app/services/scoring_engine.py
- Check: arc + intent_delta + engagement + decay, ALWAYS integer 1-10 (Hard Invariant #1), score_engagement column used correctly

### 10. Segmentation A/B/C/D
- Backend: backend/app/services/segmentation.py + routes/segments.py
- Check: A=Hot, B=Warm, C=Cold, D=Disqualified (labels immutable — Hard Invariant #2), segment assignment logic, call_status NEVER writes segment (Hard Invariant #11)

### 11. Conversations UI + Outbound Messaging
- Backend: backend/app/routes/conversations.py + services/meta_cloud.py + services/outbound_router.py
- Frontend: frontend/app/dashboard/conversations/
- Check: 3-panel layout loads, message send/receive, template-only outside 24h window (Hard Invariant #3), outbound router picks correct number from pool

## Output Format
For each feature (1-11), report:
```
### Feature N: [Name]
- **Status**: PASS | FAIL | WARN
- **Files checked**: [paths with line numbers]
- **Issues found**:
  - [CRITICAL|HIGH|MEDIUM|LOW] Description — reproduction steps — fix suggestion
- **Notes**: any observations
```

Put CRITICAL issues first. End with a summary table: feature | status | critical count | high count.
