# Aira AI — Decisions & Architecture Log

## Architecture Log
*Append-only. Newest at the bottom. Format: Date — Decision — Rationale.*

---

**2026-05-15 — Dropped Hot Lead Alert System**
- **Decision**: Removed the `hot_lead_alerts` table (Migration 083) and associated logic.
- **Rationale**: Superseded by trigger-only `chat_handover` escalation. Lead segments and scores do not trigger alerts; escalations are behavioral-trigger-only and land `UNASSIGNED` in a shared pool.

**2026-05-20 — Dropped WATI Provider & Twilio SID**
- **Decision**: Locked outbound router to Meta Cloud API (`meta_cloud`) only; dropped Twilio columns and WATI provider references (Migrations 081 & 084).
- **Rationale**: Streamline outbound pipeline, lower cost, and maintain single-provider direct webhook management.

**2026-06-01 — Removed Bot Flow Builder Engine**
- **Decision**: Deleted source code and UI pages for the Bot Flow Builder automations engine.
- **Rationale**: The flow builder added high maintenance overhead and system complexity. Replaced with structured, procedural automations and automated re-engagement triggers. Database tables (`bot_flows`, `automation_flow_runs`) remain orphaned in the database for backwards compatibility, but are not loaded or executed.

**2026-06-20 — Security Hardening (Migration 114)**
- **Decision**: Enabled Row Level Security (RLS) on all remaining tables (`conversations`, `bot_flows`, `meta_templates`, `reengagement_steps`, `reengagement_logs`, `call_scripts`, `telecalling_upload_batches`). Revoked `anon` EXECUTE on security definer functions, set explicit `search_path` on RPC helpers, and added deny-all RLS on `scheduler_runs`.
- **Rationale**: Production readiness launch blocker. Secure multi-tenant boundary isolation.

**2026-06-20 — Database Performance Advisor Warnings (Migration 115)**
- **Decision**: Tuned DB queries and policies. Optimized 5 policies using `auth_rls_initplan` (wrapping `auth.uid()` in subselects), split 12 permissive policies targeting `FOR ALL` into individual `INSERT`/`UPDATE`/`DELETE` policies, and dropped duplicate index `csl_tenant_idx`.
- **Rationale**: Resolve performance bottlenecks and execution timeouts in high-throughput query paths.

---

## Historical DB Migrations Index (051–119)
| Migration | Scope / Action |
|---|---|
| **051** | Telegram support added — `tg_user_id` column on `leads` |
| **052** | Instagram dynamic credentials stored in `app_settings` |
| **053** | Facebook support added — `fb_user_id` column on `leads` |
| **054** | Unique indexes to prevent multichannel collisions |
| **055** | Automations engine tables created (now orphaned) |
| **056** | Score thresholds & follow-up trigger setups |
| **057** | `scheduled_broadcasts` table (APScheduler engine) |
| **058_broadcast_fail_reason** | `fail_reason` column tracked in `broadcast_recipients` |
| **058_incidents_token_health** | Webhook unhealthy and token invalid incident logging |
| **060** | Carousel cards JSONB support in `message_templates` |
| **061_message_delivery_error** | Delivery failure reasons tracking |
| **061_number_health_engagement** | Outbound no-reply count, health logs, template variations |
| **062** | `conversation_last_message` RPC creation |
| **064** | `leads.pinned_at` index and column |
| **065** | Caller evaluations daily digests |
| **066** | Snapshot logging for WhatsApp platform insights |
| **067** | Fix RPC matching conversations to leads |
| **068** | `toggle_lead_pin_rpc` RPC for pin operations |
| **069** | Index tuning pass for conversational lists |
| **070_drop_faqs_table** | Deprecated FAQs table dropped |
| **070_score_engine_v2** | Score Engine v2 (composite scores, locks, and delta metrics) |
| **071** | `lead_stage_events` setup for updating scores |
| **072_ad_campaigns_whatsapp_platform** | Dynamic WhatsApp platform filter configurations |
| **072_broadcast_tags** | Color tags for bulk broadcasts and leads |
| **072_leads_collected_data** | JSONB store for captured form variables |
| **073** | Automations builder step counters (now orphaned) |
| **074** | Resumable automation run states (now orphaned) |
| **075** | Bot flow phase 2 logic triggers (now orphaned) |
| **076_botbiz_blocks** | Schema changes for botbiz automation blocks (now orphaned) |
| **076_broadcast_lead_scores** | Segment context snapshot per broadcast |
| **077** | Negative response flagging on broadcasts |
| **078** | Sentiment tagging for broadcast replies |
| **079** | Outbound message conversation linking RPC fix |
| **080** | Excluded failed broadcast leads from UI inbox lists |
| **081** | Dropped WATI provider dependency (Meta Direct only) |
| **082** | Dynamic dynamic pricing bookings moved to `app_settings` |
| **083** | Removed `hot_lead_alerts` table |
| **084** | Removed legacy `twilio_message_sid` columns |
| **085_opt_out_per_broadcast_and_tag** | Target opt-outs per broadcast or tag |
| **086_broadcast_lead_scores_finalized** | Score lock frozen on subsequent broadcast sends |
| **086_lead_tag_opt_outs_lead_fk** | Foreign key linking opt-outs to lead records |
| **087_knowledge_rag** | Vector search schema (512-dim vector + Jina + pgvector RAG) |
| **088_knowledge_rag_fix** | Vector indexing RPC corrected |
| **088_reengagement_fixes** | Re-engagement rules updates |
| **089_security_hardening** | Preliminary RLS security checks |
| **090_knowledge_keyword_retrieval** | Keyword match fallback when RAG confidence is low |
| **091_knowledge_campaign_scope** | Scope RAG queries based on lead acquisition campaign |
| **092_call_disposition** | Voice outcome checkpoints (answered, busy, etc.) |
| **093** | Template execution performance trackers |
| **094** | Scheduled automatic re-engagement rules |
| **095_autopilot** | Autopilot flow controls |
| **096** | Lead assignment timestamps (`assigned_at`) |
| **097** | Re-engagement fallback template setup |
| **098** | `app_notifications` table for real-time alerts |
| **099_lead_stage_events_assigned** | Log audit trail on assignments |
| **100** | Callback resilient foreign key links on calls |
| **101** | Removed old 1-day/1-week follow-up logic |
| **102_call_status_dnc** | Orthogonal `call_status` pipeline & lead-level DNC |
| **103_reengagement_target_sources** | Filter re-engagement logic by lead source |
| **104–110** | Broadcast retry logic, call rating parameters, archiving checks |
| **111_telecalling_upload_scripts** | Call scripts (segment-based) + telecalling uploads |
| **112_caller_shift_hours** | Caller-level shift scheduling overrides |
| **113_security_and_new_tables_rls** | RLS configurations for secondary tables |
| **114_rls_launch_blocker** | RLS enforcement, functions secure execution config |
| **115_perf_advisor_warnings** | Subselect uid mapping, permissive splits, indexes |
| **115_telecalling_subfeatures_backfill** | Telecalling config panel flag setups |
| **116_scoring_engagement_decay** | Explicit scoring signals & engagement decay checks |
| **117_opt_in_source_channels** | Channel verification validation gates |
| **118_fix_secret_flags** | Dynamic credentials secret tags fix |
| **119_telecmi_agent_password** | TeleCMI credentials support for voice call lines |
