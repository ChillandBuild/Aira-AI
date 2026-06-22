# Cross-Cutting Concerns QA Audit

You are QA-auditing Aira AI before first client deployment. Read CLAUDE.md for full context.

## Task
Audit these system-wide concerns that span ALL features. These are the most dangerous category — a failure here affects every feature.

## Features to Audit

### 62. Multi-Tenancy
- Check EVERY route in backend/app/routes/ for tenant_id filtering
- Verify RLS policies on all tables (migration 114 applied)
- Check that no endpoint leaks data across tenants
- Verify get_tenant_and_role() used consistently
- Check Supabase RPC functions have search_path set

### 63. Role-Based Access
- Check every endpoint for owner vs caller permission checks
- Verify admin-only endpoints reject caller role
- Verify caller endpoints scope to assigned leads only
- Check frontend route guards match backend permissions

### 64. APScheduler Jobs (all 5 in main.py)
- _process_automation_waits (5 min) — verify automation wait-step resumption
- _process_scheduled_broadcasts (1 min) — verify scheduled broadcast firing
- _check_token_health (24h) — verify Meta token validation + incident creation
- _sync_all_number_quality (24h) — verify Meta number quality sync
- _recycle_contacts (30 min) — verify contact recycler runs for all tenants
- Check: error handling in each job (one tenant failure shouldn't crash the job for others), logging, idempotency

### 65. Token Expiry Alerts
- Backend: _check_token_health in main.py
- Check: validates Meta tokens daily, creates token_invalid incidents, no duplicate incidents, handles expired/revoked tokens

### 66. AI Auto-Reply Toggle
- Check: app_settings.ai_auto_reply flag respected in ai_reply.py
- Verify: when OFF, no AI replies generated; when ON, normal flow
- Check: toggle persisted correctly in app_settings

### 67. Reply Source Badge
- Check: messages.reply_source set correctly:
  - "knowledge_base" when answer from KB RAG
  - "ai" when general AI reply
  - "automation" when from bot flow
- Verify frontend displays the badge

### 68. Delivery Status Tracking
- Check: messages.delivery_status as source of truth (not broadcast_recipients.send_status)
- Verify: WhatsApp status callbacks update delivery_status correctly (sent → delivered → read → failed)
- Check: leads.whatsapp_undeliverable flag set on persistent failure

## Additional Cross-Cutting Checks

### 69. Error Response Format
- All API errors should return: {"error": "message", "code": "ERROR_CODE"}
- Check 5-10 routes for consistent error format

### 70. Pagination
- All list endpoints should support ?page=1&limit=50
- Check 5-10 list routes for consistent pagination

### 71. Route Prefix
- All routes should be prefixed /api/v1/
- Grep for any routes missing the prefix

### 72. Webhook Signature Verification
- WhatsApp: X-Hub-Signature-256 via meta_webhook_verify.py
- Instagram: same verification (shared verify function)
- Facebook: same verification (shared verify function)
- Telegram: secret_token verification
- Check: all return 200 but DROP invalid payloads (don't process them)

### 73. Supabase Client Usage
- All DB calls go through the singleton in backend/app/db/supabase.py
- No direct connection strings in route/service files
- RLS context (tenant_id) passed correctly

## Output Format
For each item (62-73), report:
```
### Item N: [Name]
- **Status**: PASS | FAIL | WARN
- **Files checked**: [paths with line numbers]
- **Issues found**:
  - [CRITICAL|HIGH|MEDIUM|LOW] Description — reproduction steps — fix suggestion
- **Notes**: any observations
```

End with:
1. Summary table: item | status | critical count | high count
2. Overall GO / NO-GO recommendation for client deployment
3. Top 5 fixes required before launch (if NO-GO)
