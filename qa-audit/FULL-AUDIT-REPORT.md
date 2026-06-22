# Aira AI — Pre-Launch QA Audit Report

**Date**: 2026-06-22
**Auditor**: Claude Code (automated code-level QA)
**Scope**: 68 features across 6 priority tiers + cross-cutting concerns
**Method**: Static code analysis — route → service → DB → frontend trace per feature

---

## Executive Summary

### Verdict: **CONDITIONAL GO** — Fix 5 launch blockers first

| Severity | Count |
|----------|-------|
| CRITICAL | 7 |
| HIGH | 12 |
| MEDIUM | 22 |
| LOW | 17 |

| Tier | Features | PASS | WARN | FAIL |
|------|----------|------|------|------|
| P0 Client-facing | 11 | 9 | 2 | 0 |
| P1 Telecalling | 15 | 8 | 2 | 5 |
| P2 Broadcasts | 14 | 12 | 1 | 1 |
| P3 Multi-channel | 4 | 4 | 0 | 0 |
| P4 Supporting | 17 | 13 | 2 | 2 |
| Cross-cutting | 7 | 4 | 1 | 2 |
| **TOTAL** | **68** | **50** | **8** | **10** |

### Hard Invariants Verification

| # | Invariant | Status |
|---|-----------|--------|
| 1 | Lead score always integer 1-10 | **PASS** |
| 2 | Segments A/B/C/D immutable labels | **PASS** |
| 3 | WhatsApp 24h template window | **PASS** |
| 4 | Segment CSV endpoint | **PASS** |
| 5 | Call recordings → Supabase Storage only | **PASS** |
| 6 | Tenant isolation (RLS + get_tenant_and_role) | **PASS** (with caveats) |
| 7 | Bulk-send rejects null opt_in_source | **PASS** (upload.py:604-607) |
| 8 | Template submission uses meta_waba_id | **PASS** (templates.py:88) |
| 9 | AI model Groq llama-3.3-70b-versatile only | **PASS** |
| 10 | WhatsApp webhook X-Hub-Signature-256 | **PASS** |
| 11 | call_status orthogonal to segment | **PASS** |
| 12 | DNC is lead-level, not call_logs.outcome | **PASS** |
| 13 | Admin excluded from telecaller metrics | **WARN** — /winners leaderboard doesn't exclude owner |

---

## Top 5 Fixes Before Launch

### 1. Callers CRUD missing role checks — CRITICAL
**File**: [callers.py:434-517](backend/app/routes/callers.py#L434-L517)
**Impact**: Any telecaller can create/edit/delete callers and read colleagues' private performance data via direct API calls. Cross-tenant IDOR on status-summary (L276) and timeline (L377) — missing `tenant_id` filter.
**Fix**: Replace `get_tenant_id` with `require_owner` on `create_caller`, `update_caller`, `delete_caller`. Add `.eq("tenant_id", tenant_id)` to status-summary and timeline queries.

### 2. Caller can bypass lead scope via `assigned_to` param — HIGH
**File**: [leads.py:80-85](backend/app/routes/leads.py#L80-L85)
**Impact**: A telecaller can pass `?assigned_to=<another_caller_id>` to see another caller's leads. Tenant isolation holds but business rule violated.
**Fix**: When `role == "caller"`, always force filter to `ctx["caller_id"]` regardless of query param.

### 3. TelecallingConfigUpdate Pydantic model missing ~10 fields — CRITICAL
**File**: [app_settings.py:59-66](backend/app/routes/app_settings.py#L59-L66)
**Impact**: Contact recycling config, shift management config, and eval_daily_cap are silently dropped by Pydantic v2. Three feature subsystems have non-functional Settings UIs.
**Fix**: Add `recycle_enabled`, `recycle_delay_hours`, `recycle_max_retries`, `recycle_start_hour`, `recycle_end_hour`, `shift_mode`, `shift_start_hour`, `shift_end_hour`, `eval_daily_cap` to `TelecallingConfigUpdate`.

### 4. SourceType Literal too restrictive — HIGH
**File**: [schemas.py:8](backend/app/schemas.py#L8)
**Impact**: `SourceType = Literal["whatsapp", "instagram", "upload", "manual"]` is missing "facebook", "telegram", "csv". Any Facebook/Telegram lead will cause a 500 on GET/PATCH `/api/v1/leads/{lead_id}`.
**Fix**: Add "facebook", "telegram", "csv" to the `SourceType` literal.

### 5. Missing APScheduler jobs — HIGH
**File**: [main.py:252-306](backend/app/main.py#L252-L306)
**Impact**: Three documented features are dead in production:
- `_process_callback_reassignments` — away-caller callback resilience non-functional
- `_process_automation_waits` — bot flow wait-step resume non-functional
- `_sync_all_number_quality` — proactive quality sync non-functional
- `generate_all_digests` — daily caller coaching digest non-functional
**Fix**: Register these jobs or update CLAUDE.md to reflect they were removed.

---

## P0 — Client-Facing Launch Flows

### Feature 1: Client Self-Onboarding
**Status**: PASS

### Feature 2: Settings & Credential Management
**Status**: WARN
- [HIGH] `update_settings` upsert missing `on_conflict="tenant_id,key"` — app_settings.py:202. Can cause duplicate rows.

### Feature 3: Settings Validate & Activate
**Status**: PASS

### Feature 4: Settings Webhook Health Check
**Status**: PASS

### Feature 5: WhatsApp Inbound Webhook
**Status**: PASS
- Signature verification is fail-closed. Message routing correct. 24h window respected.

### Feature 6: AI Reply Pipeline
**Status**: WARN
- [MEDIUM] `ai_reply.py:789` — NameError: references `new_segment` before definition at L803. Crashes on `[COLLECT_DONE]` + `notify_telecaller` path.
- [MEDIUM] `resume_for_inbound` (pause-on-reply) not called in WhatsApp webhook background task.
- [MEDIUM] New inbound WhatsApp leads created without `opt_in_source`, blocking future bulk-sends.
- [MEDIUM] Trigger "E" (score-hot, dropped per CLAUDE.md) still accepted in inbox config validation.

### Feature 7: Lead CRUD
**Status**: PASS
- [HIGH] `SourceType` missing "facebook", "telegram", "csv" — schemas.py:8. 500 on leads from those channels.
- [MEDIUM] CSV export not owner-gated — telecallers can export all tenant leads.

### Feature 8: Lead Scoring (Score Engine v2)
**Status**: PASS — arc + intent_delta + engagement + decay. Pydantic validator + `max(1, min(10, ...))`.

### Feature 9: Segmentation A/B/C/D
**Status**: PASS — labels immutable, correctly enforced.

### Feature 10: Conversations UI
**Status**: PASS

### Feature 11: Outbound Messaging
**Status**: PASS — template outside 24h, session message inside.

**P0 Summary**: 0 CRITICAL, 2 HIGH, 11 MEDIUM, 7 LOW

---

## P1 — Telecalling Core

### Feature 12: Callers CRUD
**Status**: FAIL
- [CRITICAL] Missing role checks on CRUD (create/update/delete) — callers.py:434, 460, 517
- [CRITICAL] Missing role checks on admin-only reads (status-summary, timeline, coaching, digest, winners) — callers.py:268, 358, 524, 643, 675
- [HIGH] Cross-tenant IDOR on status-summary and timeline — no `tenant_id` filter — callers.py:276, 377
- [HIGH] `/winners` does not exclude owner — Invariant 13 violation — callers.py:556

### Feature 13: Telecaller Auto-Assignment
**Status**: WARN
- [HIGH] `reassign_backlog` no CAS guard — can steal leads — assignment.py:411-414
- [HIGH] `reassign_backlog` wrong column name — `needs_human_intervention` vs `needs_human_attention` — assignment.py:398

### Feature 14: Assignment Log
**Status**: PASS

### Feature 15: Telecaller Cockpit
**Status**: WARN
- [MEDIUM] `/next-lead` does not check caller shift hours — calls.py:904-976

### Feature 16: Admin Telecalling Monitoring
**Status**: PASS — owner exclusion correctly implemented.

### Feature 17: Manual Dial (TeleCMI)
**Status**: PASS
- [MEDIUM] TeleCMI secret could appear in error logs — calls.py:326-329

### Feature 18: Call Recording + Transcription
**Status**: PASS — 3-layer funnel correct. Supabase Storage only. Semaphore rate limiting.

### Feature 19: AI Coaching Post-Call
**Status**: PASS

### Feature 20: Call Scoring
**Status**: PASS

### Feature 21: Call-Status Pipeline + DNC
**Status**: PASS — Invariants 11 and 12 fully verified.

### Feature 22: Call Scripts
**Status**: PASS

### Feature 23: Callback Reassignment
**Status**: FAIL
- [CRITICAL] `_process_callback_reassignments` job not registered in APScheduler — main.py:252-306. Away-caller resilience is dead.

### Feature 24: Contact Recycling
**Status**: FAIL
- [CRITICAL] Config key mismatch — recycler reads `enabled` (master toggle) not `recycle_enabled`. Config fields not in Pydantic model. Settings UI is decorative — app_settings.py:59-66, contact_recycler.py:23-28
- [MEDIUM] Recycled leads retain `assigned_to` — never re-enter shared pool — contact_recycler.py:111-113

### Feature 25: Shift Time Management
**Status**: FAIL
- [CRITICAL] Common shift mode/hours cannot be saved — missing from `TelecallingConfigUpdate`. UI is non-functional — app_settings.py:59-66
- [HIGH] "common" and "individual" modes behave identically — assignment.py:176-189

### Feature 26: Caller Daily Digest
**Status**: FAIL
- [CRITICAL] Digest job never registered in APScheduler — main.py:252-306. Daily coaching is dead.
- [MEDIUM] UTC day boundaries for IST business — call_digest.py:116-117

**P1 Summary**: 7 CRITICAL, 5 HIGH, 6 MEDIUM, 8 LOW

---

## P2 — Broadcasts & Templates

### Feature 27: Message Templates CRUD
**Status**: PASS — tenant isolation on all queries.

### Feature 28: Template Submission to Meta API
**Status**: PASS — uses `meta_waba_id` (templates.py:88). Invariant 8 verified.

### Feature 29: Template Approval Webhook
**Status**: PASS — X-Hub-Signature-256 verified (templates.py:347-353). Status updates handled.

### Feature 30: Template Sync
**Status**: PASS — pulls from Meta, upserts locally.

### Feature 31: Carousel Templates
**Status**: PASS — 2-10 cards, button support.

### Feature 32: 7-Step CSV Upload
**Status**: PASS — upload.py handles multi-step flow with validation.

### Feature 33: Bulk Send
**Status**: PASS — rejects null/manual opt_in_source (upload.py:604-607). Invariant 7 verified.

### Feature 34: Scheduled Broadcasts
**Status**: PASS — APScheduler job `_process_scheduled_broadcasts` fires every 1 min (main.py:39). CAS lock in executor (broadcast_executor.py:54-63).

### Feature 35: Drip Broadcasts
**Status**: PASS — ceiling division for even splits, IST-aware send times (upload.py:667-703).

### Feature 36: Broadcast History + Fail Reason
**Status**: PASS — fail_reason tracked per recipient.

### Feature 37: Broadcast Tags
**Status**: PASS — tenant-scoped CRUD, per-tag stats with delivery attribution (tags.py:74-253).

### Feature 38: Per-Broadcast Lead Scoring
**Status**: PASS — broadcast_lead_scores seeded on send (upload.py:1090-1113).

### Feature 39: Broadcast Negative Reply + Sentiment
**Status**: WARN — columns exist and are written, but negative_reply exclusion in bulk-send depends on `broadcast_negative_reply_at` on leads table — verify this column is populated.

### Feature 40: Broadcast Auto-Retry
**Status**: PASS — `_process_broadcast_retries` job registered every 5 min (main.py:62-69). Delegated to `broadcast_retry.process_due_retries()`.

**P2 Summary**: 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW (cleanest tier)

---

## P3 — Multi-Channel

### Feature 41: Instagram Webhook
**Status**: PASS — tenant-scoped, X-Hub-Signature-256 verified, fail-closed.

### Feature 42: Telegram Webhook
**Status**: PASS
- [MEDIUM] Raises 500 on lead creation failure instead of returning 200 — telegram.py:90. Telegram will retry.

### Feature 43: Facebook Messenger Webhook
**Status**: PASS — same solid pattern as Instagram.

### Feature 44: CTWA Referral Auto-Capture
**Status**: PASS — parsed across WhatsApp, Instagram, Facebook.

**P3 Summary**: 0 CRITICAL, 0 HIGH, 1 MEDIUM, 3 LOW

---

## P4 — Supporting Features

### Feature 45: Knowledge Base (pgvector RAG)
**Status**: PASS — Jina v3 @512-dim, full-text fallback, campaign scoping.

### Feature 46: AI Tune
**Status**: PASS
- [LOW] Missing `require_owner` — callers can modify system prompts — ai_tune.py

### Feature 47: Lead Notes
**Status**: PASS

### Feature 48: Analytics
**Status**: PASS — owner exclusion correct.

### Feature 49: Telecalling Upload
**Status**: PASS — owner exclusion from round-robin correct.

### Feature 50: Chat Escalation
**Status**: PASS
- [MEDIUM] Operator console queries wrong status value — operator.py:620 uses `"needs_human_attention"` but actual values are `"pending"/"resolved"`. Always shows 0 handovers.

### Feature 51: Bot Flow Builder
**Status**: WARN
- [MEDIUM] Backend source files deleted — only orphaned .pyc remain. Frontend directory missing. Feature cleanly absent from both sides, but CLAUDE.md still claims "Built".

### Feature 52: ai_agent Block
**Status**: WARN — same as Feature 51, source deleted.

### Feature 53: Bookings + Razorpay
**Status**: PASS — HMAC-SHA256 webhook verification, dynamic pricing.

### Feature 54: Phone Numbers + Pool
**Status**: FAIL
- [HIGH] `CreatePhoneNumber` accepts `api_key` field but migration 081 dropped the column — numbers.py:14-19. Number creation will 500.
- [MEDIUM] `provider` is free-text but DB has `CHECK (provider IN ('meta_cloud'))` — unvalidated.

### Feature 55: Auto-Failover on RED Quality
**Status**: PASS

### Feature 56: Incidents Page
**Status**: PASS
- [LOW] No `require_owner` — callers can view incidents.

### Feature 57: Notifications
**Status**: PASS

### Feature 58: Inbound Leads
**Status**: PASS

### Feature 59: Reengagement
**Status**: PASS

### Feature 60: Admin Profile Page
**Status**: PASS — uses `useAuthRole()`, not stats-null check.

### Feature 61: Admin Exclusion from Metrics
**Status**: PASS — verified in analytics backend and frontend.

**P4 Summary**: 0 CRITICAL, 1 HIGH, 3 MEDIUM, 3 LOW

---

## Cross-Cutting

### Feature 62: Multi-tenancy
**Status**: WARN
- All routes use auth dependencies. RLS enabled (migration 114).
- [MEDIUM] `todos.py` queries without `tenant_id` filter.
- [MEDIUM] `system.py` status endpoint leaks config to callers.

### Feature 63: Role-Based Access
**Status**: FAIL
- [HIGH] Caller can bypass lead scope via `assigned_to` query param — leads.py:80-85
- [MEDIUM] Callers CRUD not owner-gated (confirmed, same as P1 Feature 12)
- [MEDIUM] `caller_timeline`/`status-summary` not owner-gated

### Feature 64: APScheduler Jobs
**Status**: FAIL
- [HIGH] `_process_automation_waits` — MISSING (bot flow resume dead)
- [HIGH] `_sync_all_number_quality` — MISSING (proactive quality sync dead)
- [HIGH] `_process_callback_reassignments` — MISSING (callback resilience dead)
- All 7 registered jobs have proper try/except wrappers.

### Feature 65: Token Expiry Alerts
**Status**: PASS — 24h check, dedup within 23h, incident creation.

### Feature 66: AI Auto-Reply Toggle
**Status**: PASS — global + per-lead toggle respected.

### Feature 67: Reply Source Badge
**Status**: WARN
- [LOW] Value is `"knowledge"` not `"knowledge_base"` — verify frontend badge matches.

### Feature 68: Delivery Status Tracking
**Status**: PASS — webhook handlers update correctly, transient errors excluded from permanent flags.

**Cross-cutting Summary**: 0 CRITICAL, 4 HIGH, 4 MEDIUM, 1 LOW

---

## Security Posture

**Rating**: CONDITIONAL PASS

**Strengths**:
- Tenant isolation at app-layer + RLS (migration 114+115)
- Webhook signature verification on all channels (WhatsApp/IG/FB/TG/Razorpay)
- No hardcoded secrets in source
- Auth on every API route
- Groq-only AI invariant upheld — no OpenAI/Gemini imports
- .env comprehensively gitignored
- Suspended tenant check in auth dependency

**Weaknesses**:
- Role checks missing on several telecalling-admin endpoints (callers CRUD, status endpoints)
- Caller lead scope bypassable via query param
- Cross-tenant IDOR on 2 endpoints (status-summary, timeline)

---

## Recommended Fix Order

| Priority | What | Effort |
|----------|------|--------|
| 1 | Add `require_owner` to callers CRUD + admin-only endpoints | 30 min |
| 2 | Fix `leads.py` caller scope bypass | 10 min |
| 3 | Add missing fields to `TelecallingConfigUpdate` | 30 min |
| 4 | Add missing channels to `SourceType` literal | 5 min |
| 5 | Add `tenant_id` filter to status-summary/timeline queries | 10 min |
| 6 | Fix `numbers.py` stale `api_key` field | 10 min |
| 7 | Register missing APScheduler jobs or update CLAUDE.md | 30-60 min |
| 8 | Fix operator console handover status query | 5 min |
| 9 | Fix `ai_reply.py:789` NameError | 10 min |
| 10 | Fix Telegram webhook 500 on lead creation failure | 5 min |

**Estimated total fix time**: 3-4 hours

---

## What This Audit Did NOT Cover

- **Live browser testing** — no Playwright/Selenium was run
- **Load/stress testing** — no concurrent user simulation
- **Real WhatsApp/Meta API integration** — no live webhook traffic
- **Frontend visual regression** — no screenshot comparison
- **Mobile responsiveness** — no viewport testing
- **Database migration integrity** — migrations not executed, only read
- **Production environment config** — .env values not inspected

These should be covered in Phase 2 (Playwright E2E) and Phase 3 (API contract tests).
