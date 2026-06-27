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

**2026-06-01 — Per-Broadcast Scoring + Removed Scoring Gate**
- **Decision**: Added `broadcast_lead_scores` (migration 076) for a fresh scoring slate per campaign; removed the `assigned_to`/segment-A gate so scoring runs on every inbound.
- **Rationale**: A cold reply to one product was poisoning another product's score under the same tag. See [subsystem-notes.md](../context/subsystem-notes.md) → Scoring.

**2026-06-06 — Knowledge Base → pgvector RAG (Jina v3 @512)**
- **Decision**: Replaced full-text KB injection with pgvector RAG (migrations 087/088), Jina `jina-embeddings-v3` @512-dim.
- **Rationale**: Groq has no embeddings API; Supabase `gte-small` is English-only (app is multilingual Tamil/Hinglish); Jina is free + multilingual. Full-text retained as fallback.

**2026-06-06 — Render Auto-Deploy ON**
- **Decision**: Enabled Render auto-deploy on `main`; added a 14-min GitHub Actions keep-alive cron (2026-06-21) to defeat free-tier cold starts.
- **Rationale**: Push = deploy with no manual step. Free tier sleeps after 15min, which also stalls in-process APScheduler — keep-alive mitigates until a paid upgrade.

**2026-06-10 — Telecalling Assignment = State-Based**
- **Decision**: Replaced transition-triggered assignment with a single state-based `maybe_assign_lead()` funnel + 2-min sweep; added push/pull modes and a shared callback claim board.
- **Rationale**: The transition model leaked (ungated channel assigns, missed promotions). State-based + sweep is the guarantee. See [subsystem-notes.md](../context/subsystem-notes.md) → Telecalling.

**2026-06-10 — Chat Escalation = Trigger-Only**
- **Decision**: Dropped score/segment chat escalation (trigger E) and auto-assign; handovers are behavioral-trigger-only (A/B/C/D/F) and land UNASSIGNED in a shared pool.
- **Rationale**: Segment temperature drives telecalling assignment, not chat handover. Avoids double-routing.

**2026-06-20 — Security Hardening (Migration 114)**
- **Decision**: Enabled Row Level Security (RLS) on all remaining tables (`conversations`, `bot_flows`, `meta_templates`, `reengagement_steps`, `reengagement_logs`, `call_scripts`, `telecalling_upload_batches`). Revoked `anon` EXECUTE on security definer functions, set explicit `search_path` on RPC helpers, and added deny-all RLS on `scheduler_runs`.
- **Rationale**: Production readiness launch blocker. Secure multi-tenant boundary isolation.

**2026-06-20 — Database Performance Advisor Warnings (Migration 115)**
- **Decision**: Tuned DB queries and policies. Optimized 5 policies using `auth_rls_initplan` (wrapping `auth.uid()` in subselects), split 12 permissive policies targeting `FOR ALL` into individual `INSERT`/`UPDATE`/`DELETE` policies, and dropped duplicate index `csl_tenant_idx`.
- **Rationale**: Resolve performance bottlenecks and execution timeouts in high-throughput query paths.

**2026-06-21 — Deep-Violet Design Unification**
- **Decision**: Unified all accents to `primary` #5b21b6 (deep violet) across 48 files; consolidated tokens, semantic typography. Maturity 8/10.
- **Rationale**: Brand anchor the user chose. Next step = shared UI primitives (Button/Input/Badge/Tabs). Segment badges stay semantic (green/amber/slate/rose), NOT violet; no `dark:` until next-themes is wired.

**2026-06-22 — Env Var Credential Leak Fixed**
- **Decision**: Gated env-var settings fallback to `_DEFAULT_TENANT_ID` only across `config_dynamic.py`, `app_settings.py` (×2), `meta_webhook_verify.py`. Migration 117 expanded `opt_in_source` CHECK to channel values.
- **Rationale**: Fallback was leaking the default tenant's Meta tokens/secret to every new client (security + wrong-credential webhook verification). **Apply rule:** new per-tenant settings must use `get_setting(key, tenant_id=...)` — never fall back to env/`app.config`.

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

---

## 2026-06-26 - PWA support and Codex command migration

- **Decision**: Added PWA support to the Next.js frontend with manifest metadata, generated app icons, a production-only service worker registrar, a narrow service worker, and an offline page.
- **Rationale**: Aira should be installable from browser/mobile without app-store work. The service worker intentionally caches static assets and the offline route only; authenticated API/dashboard data must stay network-first and uncached.
- **Decision**: Converted Claude Code command prompts into Codex skills under `.codex/skills` and installed copies in `C:\Users\vskee\.codex\skills`.
- **Rationale**: Codex does not natively run Claude-style slash commands from `.claude/commands`, but skill triggers let the user invoke equivalent workflows with `/aira-status`, `/aira-wiki`, `/aira-deploy-check`, or `/aira-rls-audit`.
- **Decision**: Cherry-picked remote commit `174ff982f7c68be7c7dc4a0173f278824e239372` onto local `main` as `9e3fe475e3d2a6bb27b109410bbbd9cbd036f164`.
- **Rationale**: The commit untracks `graphify-out/wiki` as local-only generated cache and updates `/aira-status` to refresh it automatically.

---

## 2026-06-26 - Mobile dashboard shell for installed PWA

- **Decision**: Replaced the dashboard's phone layout with a mobile-only shell: hide the fixed desktop sidebar below `md`, use `MobileDashboardNav` as a bottom tab bar, compact the sticky header, and stack telecalling queue/profile panels vertically below `xl`.
- **Rationale**: Installed PWA screenshots showed the 220px desktop sidebar consuming roughly half of a phone viewport, making the dashboard and telecalling cockpit unusably tiny. Desktop/tablet behavior stays unchanged.

---

## 2026-06-26 - Mobile inner-page redesign

- **Decision**: Extended the mobile redesign beyond the dashboard shell into the inner dashboard routes. Conversations now use a phone master-detail flow, dense lead/template/knowledge/outbound data gets mobile card layouts, analytics grids collapse responsively, and number pool rows wrap controls instead of squeezing.
- **Rationale**: Follow-up PWA screenshots showed desktop tables, fixed inbox rails, and multi-column panels still appearing inside the mobile shell. The mobile implementation keeps desktop tables and layouts at larger breakpoints while giving phones separate readable cards and reachable touch actions.

---

## 2026-06-27 - Telecalling provider split and push alerts

- **Decision**: Telecalling now treats TeleCMI and SIM Basic as tenant-level calling providers under `telecalling_config.calling_provider`, not as separate dialer products. TeleCMI keeps API/webhook/recording flow; SIM Basic creates manual `call_logs` with provider/source metadata and opens the phone dialer via `tel:`.
- **Rationale**: Aira should sell premium TeleCMI calling and low-cost SIM calling without duplicating the lead queue, lead profile, notes, callbacks, scheduling, or analytics surface.
- **Decision**: SIM Basic wrap-up is mandatory and captures manual start/end time, duration, outcome, rating, tags, and a short call summary into the same analytics-compatible call log path.
- **Rationale**: SIM/PWA cannot reliably access native call logs or recordings, so structured manual feedback is the compliant substitute for duration, conversion, and team-performance metrics.
- **Decision**: PWA push alerts were added with Web Push subscriptions and lead-assignment deep links to `/dashboard/telecalling?lead_id=...`.
- **Rationale**: Telecallers may leave the installed PWA while waiting for assignments; push notifications should bring them directly back to the assigned lead.
