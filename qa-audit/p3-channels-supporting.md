# P3+P4 — Multi-Channel & Supporting Features QA Audit

You are QA-auditing Aira AI before first client deployment. Read CLAUDE.md for full context.

## Task
Audit each feature. Read the route, service, AND frontend. Flag logic bugs, missing error handling, broken data flow, invariant violations, security gaps, race conditions.

## P3 — Multi-Channel

### 41. Instagram Webhook
- Backend: backend/app/routes/instagram.py
- Check: tenant-scoped at /webhook/instagram/{tenant_id}, X-Hub-Signature-256 verified, message routing to AI reply pipeline, media handling

### 42. Telegram Webhook + Bot API
- Backend: backend/app/routes/telegram.py
- Check: secret_token verified, per-tenant bot, message routing, command handling

### 43. Facebook Messenger Webhook
- Backend: backend/app/routes/facebook.py
- Check: tenant-scoped at /webhook/facebook/{tenant_id}, X-Hub-Signature-256 verified, message routing

### 44. CTWA Referral Auto-Capture
- Backend: referral parsing in webhook.py
- Check: referral object parsed correctly, linked to ad_campaign, handles missing referral gracefully

## P4 — Supporting Features

### 45. Knowledge Base (pgvector RAG)
- Backend: backend/app/routes/knowledge.py + services/knowledge_service.py + services/embeddings.py
- Frontend: frontend/app/dashboard/knowledge/
- Check: Jina v3 embeddings @512-dim, HNSW index, chunk insert/match RPCs, full-text fallback, CRUD UI

### 46. AI Tune
- Backend: backend/app/routes/ai_tune.py
- Check: integrated into Knowledge page tab, tuning parameters saved correctly

### 47. Lead Notes + Briefing Modal
- Backend: backend/app/routes/lead_notes.py
- Frontend: frontend/app/dashboard/notes/
- Check: CRUD notes, briefing modal display, tenant isolation

### 48. Analytics
- Backend: backend/app/routes/analytics.py
- Frontend: frontend/app/dashboard/analytics/
- Check: WhatsApp tab + Telecalling tab + funnel API, data accuracy, admin-only gating where needed

### 49. Telecalling Upload (CSV + Round-Robin)
- Backend: backend/app/routes/telecalling_upload.py
- Frontend: frontend/app/dashboard/telecalling/upload/
- Check: 2-step wizard (Upload → Confirm), round-robin to least-loaded caller (excludes owner), dedup by phone, upload history with CSV export

### 50. Chat Escalation
- Backend: backend/app/routes/chat_handovers.py
- Check: trigger-only (A/B/C/D/F behavioral triggers), shared pool (UNASSIGNED), no segment/score escalation, no auto-assign, visible to admin + every telecaller

### 51. Bot Flow Builder
- Backend: backend/app/services/automation_engine.py
- Frontend: frontend/app/dashboard/automations/
- Check: visual node-graph canvas, all block types (send_message/image/video/audio/file/location, cta_url, template, send_list, send_catalog, add_label, wait, condition, user_input, interactive, http_api, random, ai_agent), pause-on-reply resume, per-node analytics

### 52. ai_agent Block
- Backend: backend/app/services/agent_runtime.py
- Check: contained Groq agent (llama-3.3-70b), STRICT validated JSON output, outcome branching, hard tool-call caps, state survives pause/resume

### 53. Bookings + Razorpay
- Backend: backend/app/services/booking_flow.py + routes/bookings.py + services/payment_razorpay.py
- Frontend: frontend/app/dashboard/bookings/
- Check: booking state machine, dynamic pricing via booking_types JSON, Razorpay payment link creation, webhook callback, no SDK (direct httpx)

### 54. Phone Numbers + Pool Management
- Backend: backend/app/routes/numbers.py
- Frontend: frontend/app/dashboard/numbers/
- Check: provider 'meta_cloud' only (migration 081), pool CRUD, number assignment

### 55. Auto-Failover on RED Quality
- Backend: backend/app/services/failover.py
- Check: handle_quality_red() triggered, number rotation logic, incident creation

### 56. Incidents Page
- Backend: backend/app/routes/incidents.py
- Frontend: frontend/app/dashboard/(incidents area if exists)
- Check: incident CRUD, types (token_invalid, webhook_unhealthy, quality_red), tenant_id scoping

### 57. Notifications
- Backend: backend/app/routes/notifications.py
- Check: app_notifications table, notification creation/retrieval, read status

### 58. Inbound Leads
- Backend: backend/app/routes/inbound_leads.py + services/inbound_leads_logic.py
- Frontend: frontend/app/dashboard/inbound-leads/
- Check: inbound lead capture, source tracking, dedup, tenant isolation

### 59. Reengagement
- Backend: backend/app/services/reengagement_service.py + routes/reengagement.py
- Check: reengagement steps with target_sources filter, automated execution, fallback template, logging

### 60. Admin Profile Page
- Frontend: frontend/app/dashboard/profile/ProfileClient.tsx
- Check: role-based display (admin card with crown vs caller stats), useAuthRole() not stats-null check

### 61. Admin Exclusion from Telecaller Metrics
- Backend: analytics.py owner filter + assignment.py
- Frontend: leaderboard callerIds filter, LiveAgentStatus, ShiftTimeline
- Check: admin NEVER appears in Agent Performance Leaderboard, attendance, shift tracking, call stats (Hard Invariant #13)

## Output Format
For each feature (41-61), report:
```
### Feature N: [Name]
- **Status**: PASS | FAIL | WARN
- **Files checked**: [paths with line numbers]
- **Issues found**:
  - [CRITICAL|HIGH|MEDIUM|LOW] Description — reproduction steps — fix suggestion
- **Notes**: any observations
```

End with summary table: feature | status | critical count | high count.
