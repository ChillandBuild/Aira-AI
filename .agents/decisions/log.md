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

**2026-07-03 — WhatsApp Lead-Segment Admin Notifications (no migration)**
- **Decision**: Extended the `notification_config` JSON (`app_settings`) with a `whatsapp_notifications` sub-config (`enabled`/`recipient_phones`/`template_id`/`target_segments`). New `services/whatsapp_notify.py::send_admin_whatsapp_alerts` fires a Meta template message to configured admin phones when a lead's segment changes, triggered from `growth.py::record_stage_event` via a fire-and-forget `asyncio` background task (not FastAPI `BackgroundTasks` — see subsystem-notes.md → WhatsApp templates & notifications). 6h cooldown per `(lead_id, to_segment)` against `lead_stage_events` prevents alert spam/cost on a lead flapping segments. Ordinal parameter injection maps however many `{{n}}` placeholders the chosen template has to Name/Phone/Segment/Dashboard-link, in that order. Frontend: new WhatsApp section in `NotificationConfigPanel.tsx`.
- **Rationale**: Admins wanted instant WhatsApp alerts on hot-lead triage without polling the dashboard.

**2026-07-03 — Meta Template Validation + Language Restriction**
- **Decision**: Added validation for Meta's hard template-body rules — leading/trailing variables (Graph API subcode 2388299) and sequential `{{n}}` numbering with no gaps — both client-side (`frontend/.../templates/types.ts::validateTemplateBody`, shared by `variable-inserter.tsx`, template create/edit pages) and server-side (Pydantic validators on `CreateTemplate`/`UpdateTemplate` in `templates.py`). Also fixed `create_template` to save `status="REJECTED"` (was `"PENDING"`) when Meta's submission genuinely fails, so the template becomes editable via the existing PATCH flow instead of a dead-end (PATCH only allows REJECTED/PAUSED; re-POSTing the same name 409s on the local `(tenant_id, name)` uniqueness constraint before ever reaching Meta). Restricted the template language dropdown + backend validation to Indian + English only: `en`, `en_US`, `en_IN`, `hi`, `kn`, `ml`, `ta`, `te`.
- **Rationale**: Template submissions were repeatedly round-tripping to Meta's Graph API and failing on deterministic rules that should be caught before submission; a failed submission previously left the local row in an unrecoverable PENDING state. Language restriction is an Indian-market product requirement.

**2026-07-04 — Itemized Subscriptions: Billing Cycle, Pricing Fixes, Dashboard Gating (follow-up to the same-day itemized-pricing launch)**
- **Decision**: Anchored each tenant's usage/quota period to their subscription **approval date**, not the calendar month — `tenant_subscriptions.period_start`/`period_end` (columns already existed, unused since migration 123) are stamped on first approval (`period_end = period_start + 1 calendar month`, day-clamped for month-length via `entitlements.py::add_one_month`) and rolled forward lazily on read (`get_billing_period`, no cron) rather than via a scheduled job. `tenant_usage_counters.period` is now keyed by the anchor date string instead of `"%Y-%m"`; six call sites (`check_quota`, `increment_usage`, `/subscriptions/me`, `approve_request`, and two `operator.py` usage reads) were migrated to it. A pure, non-mutating `compute_period_key` variant serves the operator's multi-tenant fleet-cockpit list view, since a bulk GET shouldn't have the side effect of resetting counters.
- **Decision**: Fixed real pricing bugs in `_price_for_item`/`_compute_package_price`/`approve_request`'s MRR snapshot: quantity-priced SKUs (`numbers_pool`, `telecaller_seats`, `monthly_price=0`) now correctly treat `included_qty` as free — only units beyond it bill at `unit_price`, netting out quantity already purchased in a prior request so a top-up doesn't re-charge an included unit. Flat-priced SKUs with a metered overage rate (`telecalling_telecmi`: `monthly_price=1999` AND `unit_price=1/call_minute`) were being billed at the overage rate (₹1) instead of the flat price, because the old logic always preferred `unit_price` when present — now `monthly_price > 0` always wins regardless of `unit_price`.
- **Decision**: A top-up/addon request from an already-active tenant no longer flips `tenant_subscriptions.status` to `pending_approval` (only a tenant's first-ever request does) — previously ANY cart submission re-gated the entire dashboard behind the Subscriptions cart page, locking a paying client out of everything (dialer, conversations, etc.) while a single new item (e.g. one more phone number) awaited approval. The specific new item stays locked via the existing purchased-quantity checks at its point of use; nothing else is affected.
- **Decision**: Client-side subscription management moved out of Settings into its own top-level `frontend/app/dashboard/subscription/page.tsx`, linked from a new sidebar item (`components/sidebar.tsx`) — `SubscriptionSettingsPanel.tsx` and the Settings "Subscription" tab were deleted. The operator's per-client sidebar (`client/[id]/sidebar.tsx`) Telecalling group now only exposes switches for the master toggle and "Upload" — Dialer/Scheduled/Notes show as plain status rows (the master-switch cascade to those three already existed server-side in `PATCH /clients/{id}/features`, just wasn't reflected in the UI); Upload was pulled out of that cascade entirely on both frontend and backend, since `bulk_lead_upload` is its own separately-purchasable SKU unrelated to `telecalling_sim`/`telecalling_telecmi`. The dead operator "Billing & Usage" tab (called a route this feature's own launch had deleted) was folded into the "Entitlements" tab instead of restored.
- **Decision**: Found and fixed **three more** instances of the `maybe_single()` None-on-zero-rows crash (see subsystem-notes.md) in this same code area — `GET /subscriptions/me`, `submit_request`, `GET /operator/clients/{id}/entitlements` — all triggered by the ordinary case of a tenant with no `tenant_subscriptions` row yet, manifesting in the browser as a misleading CORS policy error rather than a 500.
- **Rationale**: User-reported production bugs (client creation, a subscription page CORS error) plus explicit product requirements ("existing purchases keep working during a top-up," "a plan bought July 4 should run to Aug 4, not reset July 1"). Backend suite 251 passing / 38 pre-existing-unrelated failures (env-only, `pytest-asyncio` missing from this venv) both before and after — no regressions.

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

---

## 2026-06-27 - Auth login stability on desktop and mobile

- **Decision**: The `/login` page should avoid animated canvas work around the credential form and keep email/password as native uncontrolled inputs, reading credentials through `FormData` on submit.
- **Rationale**: Desktop Chrome showed flicker/focus loss while typing the password. Removing the animated auth background and avoiding per-keystroke React state keeps browser credential entry stable while preserving the responsive mobile login layout.

---

## 2026-06-28 - Push public key auth split

- **Decision**: `GET /api/v1/push/public-key` is mounted on `push.public_router` without the global auth dependency; `/api/v1/push/status` and `/api/v1/push/subscriptions` remain auth-gated.
- **Rationale**: The VAPID public key is non-sensitive and the production PWA registrar can touch push setup from anonymous pages. Keeping only subscription/status routes authenticated stops repeated 401s without exposing user subscription data.

---

## 2026-06-28 - SIM Basic fixes reverted (Updated)

- **Decision**: Commit `e1f8cec3ebf9a411558a4b55a34b561c416974de` (`sim based fixes`) was reverted by `3cd5abde3b208aa30c4a43863cd3a1ef721af559` on `main`.
- **Rationale**: The pushed batch had failing backend checks and a Vercel authorization failure. Treat the extra SIM Basic manual-call status work, migration `121_sim_manual_call_statuses.sql`, graceful push UX, provider-switch confirmation, provider-aware Live Agent Status, and mobile `tel:` dialer changes as not present on `main`; continue from the simpler provider split baseline unless a new branch reintroduces those changes deliberately.

---

## 2026-06-28 - Restored SIM Basic fixes & resolved test errors

- **Decision**: Restored the full set of SIM Based manual statuses, configurations, and dashboards by reverting the revert commit `3cd5abde3b208aa30c4a43863cd3a1ef721af559`.
- **Rationale**: The user requested all SIM Basic manual status features, outcome tracking, config selectors, and performance panels to be restored. 
- **Decision**: Added missing test stats fields and modified Windows tests to force UTF-8 encoding.
- **Rationale**: The unit test `test_call_digest_eval_v2.py` was failing because the new `interested` key was missing from its test stats mock. The static check files were failing on Windows environments due to local charmap decoder limits. Restoring the fixes along with these test adjustments ensures a 100% green test run across all platforms.

---

## 2026-06-29 - Mobile SIM dialer backgrounding fixes

- **Decision**: Added `keepalive: true` to `api.calls.initiate` POST request and softened catch handlers in `useCallingCockpit.ts` to suppress `TypeError` / "Cannot reach server" toasts caused by PWA backgrounding when opening the native phone dialer.
- **Rationale**: Mobile browsers suspend the JavaScript engine when the PWA backgrounds to launch `tel:` links, causing active fetch requests to abort. `keepalive` delegates the request to the browser's background process; the softened catch prevents the error toast from flashing on return.

- **Decision**: Moved `setActiveCallCtx` and `primeSimWrapup` timeout scheduling from inside the async `.then()` callback to synchronous execution immediately when the user taps "Call" in `useCallingCockpit.ts`.
- **Rationale**: The wrap-up modal gate (`showWrapupModal && activeCallCtx`) was never satisfied because `activeCallCtx` was only set after the API response resolved — which never happened while the browser was suspended. Setting context synchronously guarantees the modal renders on return.

- **Decision**: Added a lazy/fallback call log creation path inside `handleWrapupSubmit()`. If `callLogId` is null when the user submits the wrap-up, the app creates the call log in the foreground first, then saves the outcome.
- **Rationale**: The background `api.calls.initiate` request could fail or be aborted during backgrounding, leaving `callLogId` as null. The previous code silently returned without any feedback when `callLogId` was missing.

## 2026-06-29 - Applied migrations 120 & 121 to live Supabase

- **Decision**: Manually applied migrations `120_calling_provider_and_push.sql` and `121_sim_manual_call_statuses.sql` to the live Supabase database (`ayftynkgmfkaqmmnlmoc`) via the Supabase MCP SQL tool. Ran `NOTIFY pgrst, 'reload schema'` to force PostgREST cache refresh.
- **Rationale**: These migrations were present in the codebase but had never been applied to the production database (likely due to the earlier revert cycle). The missing `feedback_source` column was causing a `PGRST204` error on every call log write.

## 2026-06-29 - Mobile wrap-up modal bottom-sheet layout

- **Decision**: Changed the wrap-up modal from a centered overlay to a mobile bottom-sheet layout (`items-end`, `rounded-t-3xl`, `z-[60]`, `safe-area-inset-bottom` padding) on small screens, keeping centered behavior on `sm:` and above.
- **Rationale**: The modal was overlapping with the bottom navigation bar on mobile, making the "Complete Wrap-up" button partially hidden and the form hard to interact with.

## 2026-06-29 - VAPID keys generated and configured

- **Decision**: Generated VAPID key pair via `npx web-push generate-vapid-keys` and added `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` to `backend/.env`. These must also be manually added to Render environment variables for production push notifications.
- **Rationale**: The Python backend's `pywebpush` integration reads these from environment variables. `.env` is git-ignored, so production requires separate Render Dashboard configuration.

---

## 2026-06-30 - Fix mobile modal Z-index overlap

- **Decision**: Increased the `z-index` of all `CockpitModals` from `z-[60]` and `z-50` to `z-[70]`.
- **Rationale**: The mobile bottom navigation bar (`MobileDashboardNav.tsx`) has a `z-[60]` setting and appears later in the DOM structure. When the wrap-up modal was displayed on mobile, the navigation bar was overlapping the bottom of the modal, hiding the submit button. `z-[70]` forces the modal to strictly render on top.

---

## 2026-06-30 - Mobile deep-linking to specific tabs

- **Decision**: Modified `CallerView.tsx` to automatically map a push notification's `lead_id` parameter to its exact sub-tab state (`queueSubTab`).
- **Rationale**: Clicking a push notification loaded `/dashboard/telecalling?lead_id=...` which selected the lead but did not switch the active background tab, meaning returning from the lead detail panel would leave the user in the wrong queue tab. The app now tracks `lastProcessedLeadId` in a React `useRef` to perform a one-time tab switch to "new", "callback", "in_progress", or "closed" whenever a new `lead_id` is loaded via URL.

---

## 2026-07-01 - Callback notifications (claimable-only) + configurable push (Migration 122)

- **Decision**: Replaced the callback **auto-reassignment** pipeline with a **claimable-only** model. New 1-min scheduler job `callback-notifications` (`services/callback_notifications.py`) does two passes: (1) DUE — pushes the assigned caller a "callback due now" reminder at the scheduled slot; (2) CLAIMABLE — after a configurable threshold (default 15 min, **no shift check** — out-of-shift owners included) broadcasts a "claimable" push to the configured audience. Deleted `process_callback_reassignments` + the `callback-reassignment` job (renamed/replaced in `main.py`). The claim path (`POST /leads/{id}/takeover`) now also pushes the previous owner (`callback_taken_over`).
- **Rationale**: User wanted a single manual-pull model — an overdue callback opens to everyone rather than being silently auto-moved. See [subsystem-notes.md](../context/subsystem-notes.md) → Callback notifications.
- **Decision**: Added tenant `notification_config` (`app_settings` key) gating push at one chokepoint — `notify_user` skips `send_user_push` per master switch / per-event toggle / quiet hours, but ALWAYS writes the in-app `app_notifications` row. `push_allowed` is **fail-open** (config read error → push allowed). Owner-only `GET/PUT /api/v1/notifications/config`; admin "Notifications" settings tab (per-event toggles, claimable threshold, claimable audience incl. a "specific" caller picker, quiet hours).
- **Rationale**: Admins need org-wide control of which pushes fire and to whom, without ever losing the in-app record.
- **Migration 122_callback_notification_guards**: `follow_up_jobs.due_notified_at`, `claimable_notified_at` (timestamptz, once-only fire guards; reset by `reschedule_callback`) + index `idx_follow_up_jobs_callback_scan(tenant_id, cadence, status, scheduled_for)`. **Applied to live Supabase (`ayftynkgmfkaqmmnlmoc`) 2026-07-01 and verified.** Built via subagent-driven SDD; plan at `docs/superpowers/plans/2026-06-30-callback-notifications.md`.
- **Also (2026-07-01)**: Segments page (`/dashboard/leads`) now lands on the first **non-empty** segment tab instead of always "Hot/A" — an admin with no telecaller (leads sitting in Cold) no longer sees an empty default tab. Segmentation was never telecaller-gated; only the default tab was misleading.

**2026-07-01 — SaaS Monetization + Entitlements Layer (Migrations 123–126)**
- **Decision**: Added a plan/entitlement/metering layer to the operator console. Tables: `feature_catalog` (43 seed rows), `plans` (6 = 3 messaging + 3 telecalling), `tenant_subscriptions`, `tenant_usage_counters`. Migrations 123 (tables+RLS), 124 (seed), 125 (`tenants` contact cols), 126 (`callers.status` drift close). Applied to live Supabase 2026-07-01 + verified (feature_catalog 43, plans 6). Merged to `main` (merge `1620969`) — **NOT yet pushed to origin**.
- **Model**: a "plan" is a saved preset of feature toggles + quotas. `tenants.enabled_features` (jsonb list) is the console-facing entitlement source; `tenant_subscriptions` holds plan ids + `ai_tier` + `mrr` (authoritative for billing). Metering is **track-only / non-blocking** (`meter()` swallows all errors) — hard-cap enforcement deferred by decision. AI billed per-reply, never per-token; AI tier maps to an internal model.
- **Rationale**: turn the ops console into a subscription control room. See [subsystem-notes.md](../context/subsystem-notes.md) → Operator Console Monetization. Plan: `docs/superpowers/plans/2026-07-01-monetization-and-console.md`.
- **Lesson**: the initial scaffold rewrite of `operator.py` silently DROPPED 4 working endpoints (`PATCH /status`, `wipe-leads`, `GET`/`PATCH /calling-provider`) plus `GET /me` — caught only by a static audit test + an endpoint-parity diff against `main` at the final gate. When rewriting a large route file, diff the endpoint list against the base branch.

**2026-07-02 — Operator Console QA hardening + 6 features (no migrations)**
- **Decision**: Full QA + feature pass on the operator console via subagent-driven SDD (plan: `docs/plans/operator-console-qa-and-features.md`). Safety: layout auth-check now distinguishes unauthorized (redirect) from unreachable (retry screen, ~8s timeout — a Render cold-start no longer ejects a logged-in operator); sign-out → `/operator/login`; critical scheduler pauses + password resets confirm in-app (`ActionConfirm`); temp passwords masked with reveal/copy. Features: custom `OperatorToggle` (role="switch", morphing glyph); fleet attention queue with real `compute_fleet_health()` signals (near_cap / no_activity_14d / token_expired); `GET /operator/alerts` + header bell (pure `compute_alerts`, dedup keyed on incident PK); Ctrl+K command palette; `POST /scheduler/{id}/run` (404 unknown / 409 paused); bulk Suspend/Activate (sequential per-client PATCH loop, no new backend route); read-only tenant impersonation (mint-nothing design, dedicated security review PASS). Shared `frontend/lib/operator.ts` + vitest introduced.
- **Rationale**: QA audit found the console ejected operators on backend blips, leaked temp passwords, allowed one-click platform-wide broadcast pauses, and promised an "attention queue" it never rendered. See [subsystem-notes.md](../context/subsystem-notes.md) → Operator console for the load-bearing gotchas (token-key split, 48h incident cutoff, impersonation banner expiry, keydown target guard).
- **Lesson**: the final whole-branch review caught 3 cross-task bugs no per-task review could see (T4's row keydown hijacking T9's checkboxes; T11's banner expiry desyncing T1/T6 layout offsets; T5's token check missing `telegram_bot_token` + unbounded incident lookback also poisoning T6's bell). Cross-task seams need the whole-diff pass. Also: two subagent runs lost their commits to mid-run disconnects — instruct implementers to commit the moment verification passes.
- **Merged to `main`** (merge `a4fa029`, 2026-07-02) — **NOT pushed**; origin/main is 3 commits ahead locally-unseen (basePath `/aira` + policy pages), reconcile before push (package-lock conflict likely). Dark mode DEFERRED by user (approach specced in the plan, Task 10). Backend suite 241/241; vitest 11/11.

**2026-07-02 — SIM-Based Call Tracking Phase 1 (Migration 122_sim_sync_token) + Android "Aira Sync" APK**
- **Decision**: Built call-log tracking as a hybrid: the existing PWA stays the reliable baseline (dial via `tel:` link + manual outcome tagging, unchanged); a new minimal native Android APK ("Aira Sync") is a best-effort enrichment layer that reads `CallLog.Calls` in the background and auto-syncs matched calls — no CRM UI in the APK. Rationale for hybrid over full-native: browsers structurally cannot read `READ_CALL_LOG` or OEM recorder folders (Android permission model), so *some* native code is required for auto-tracking, but the APK and PWA are separate processes that only share the backend — an APK crash/OEM-kill cannot affect the PWA, and vice versa.
- **Backend**: 3 new endpoints in `calls.py`/`callers.py` — `POST /callers/{id}/sync-token` (owner-only, `secrets.token_urlsafe(32)`, tenant-scoped), `GET /calls/sim-lead-numbers` (returns the caller's assigned-lead phone numbers for on-device filtering), `POST /calls/sim-cdr` (batch ingest, `X-Sync-Token` auth, idempotent dedup on `(caller_id, call_sid=entry_id, provider='sim_basic')`, reuses existing `score_from_outcome`/`recompute_caller_score`). Migration 122: `callers.sync_token` (unique) + partial unique index `uq_call_logs_caller_sim_entry`. **Applied to live Supabase (`ayftynkgmfkaqmmnlmoc`) 2026-06-30, verified.**
- **Privacy — fail-closed personal-call filter**: the APK fetches the caller's lead-number set *before* uploading anything and only uploads calls whose number matches an assigned lead; personal calls never leave the device. If the lead-number fetch fails, `SyncWorker` returns `Result.retry()` and uploads nothing that round — never risks sending an unfiltered batch.
- **Rationale**: user explicitly flagged that telecallers' personal calls must never reach the dashboard/server — this shaped the architecture (filter-on-device, not filter-on-server, since filter-on-server would still transit personal numbers over the wire).
- **Deferred to Phase 2**: recording upload (OEM recorder folder `FileObserver` watcher). Phase 1 is call-log metadata only (number, type, duration, timestamp).
- **Open/unresolved**: the PWA's existing cockpit SIM-dial flow (`sim_started` row creation on tap) and the APK's own row creation are not reconciled — if a telecaller dials via the cockpit AND the APK is installed, the same call can double-count. Not fixed in Phase 1; see active-backlog.md.
- **Android build notes**: SDK/Gradle toolchain installed via Homebrew (not Android Studio) on the dev machine; `gradle wrapper --gradle-version 8.9` generated the missing `gradlew`/wrapper jar (project's `gradle-wrapper.properties` already pinned 8.9, compatible with AGP 8.5.0). Fixed a real theme bug (`AppTheme` referenced `android:Theme.Material3...` without the Material Components dependency — switched to `Theme.AppCompat`, already a project dependency).
- **Fixed a launch-crash bug**: `AiraSyncApplication.onCreate()` unconditionally started `SyncService`, which immediately registered a `ContentObserver` on `CallLog.Calls.CONTENT_URI` before the user had granted `READ_CALL_LOG` — threw an unhandled `SecurityException` on first launch, every time. Fix: `SyncService` now calls `startForeground()` unconditionally (required — skipping it gets the service killed for not entering foreground in time) then checks the permission and `stopSelf()`s if missing, instead of touching the call log; `AiraSyncApplication`/`BootReceiver` only auto-(re)start the service if the permission was already granted in a prior session; `MainActivity.scheduleWork()` now actually starts the service (was previously a no-op toast).
- **Verified end-to-end 2026-07-02**: real device successfully called `sync-token` and `sim-lead-numbers` (both 200 OK, confirmed via Render request logs from a non-localhost IP). Test lead `prem` (`+919345679286`) temporarily reassigned to the `Admin` caller (`13252cf0-06f8-4d3e-bbd5-277362a4cdde`) purely to exercise the filter end-to-end — see active-backlog.md for cleanup.
- **Gotcha surfaced**: `aira-ai-5tfr` Render service currently has **`autoDeploy: no`**, contradicting the 2026-06-06 "Render Auto-Deploy ON" decision above — deploys are happening via manual/API triggers, not automatically on push to `main`. Don't assume a push is live; check `list_deploys` for the actual live commit before verifying a fix in production.

**2026-07-02 — Aira served under `www.bloommatrix.in/aira` (Next.js basePath) + Meta compliance pages**
- **Decision**: Aira and Bloom Matrix stay two separate Vercel projects (no merge, no `aira.bloommatrix.in` subdomain). Aira's `next.config.mjs` sets `basePath: "/aira"`; Bloom Matrix's `vercel.json` rewrites `/aira` and `/aira/:path*` to Aira's production Vercel URL. This is the standard pattern for one path-segment of a domain being served by a separate project, and is a prerequisite for the Meta Tech Provider application (which requires policy pages reachable from the product domain).
- **Added 4 legal pages** (`app/{privacy-policy,terms-and-conditions,contact,data-deletion}/page.tsx`), all built on a shared `components/legal/LegalPageShell.tsx` (cream/violet, matches dashboard tokens) with cross-links via `next/link`. Content supplied by the user (Bloom Matrix's drafted Privacy Policy / Terms). Linked from the landing footer's "Legal" column and the shared legal-page nav.
- **Rationale**: `basePath` is documented by Next.js as the correct way to deploy under a sub-path (build-time, requires rebuild). Meta's Tech Provider review checks that the WhatsApp Business Account's legal entity (Bloom Matrix) is disclosed and reachable from the product's public site — added "A Bloom Matrix product" to the landing footer and legal-page headers for that reason.
- **basePath gotcha (load-bearing, see subsystem-notes.md → Domain/basePath)**: `basePath` does NOT auto-prefix `public/` assets, `metadata.icons`/`metadata.manifest` strings, `app/manifest.ts` fields, or raw `<a href="/...">` tags (literal OR dynamic `href={var}`) — only `next/link`, `router.push`/`redirect`, and `next/image` get the prefix automatically. A first audit pass using `grep -rn 'href="/[^/"]'` missed the operator console's top-nav (`href={item.href}` — a dynamic expression, not a literal string) and 3 more literal instances the first regex silently no-op'd on (it used a `(?!...)` lookahead `grep -E` doesn't support). Corrected sweep: `grep -rn '<a\b'` across the whole `app/`+`components/` tree, manually excluding `mailto:`/`tel:`/external.

**2026-07-02 — Production incident: domain migration broke CORS + operator console (root-caused + fixed)**
- **Symptom**: After the `bloommatrix.in/aira` cutover, the operator console login threw a raw `"Failed to fetch"`, the dashboard sidebar rendered almost empty, and the "Client dashboard? Login here" link 404'd.
- **Root cause 1 (CORS)**: `backend/app/main.py`'s CORS `allow_origins` only listed `localhost:3000/3001` + one optional `FRONTEND_URL` + an `allow_origin_regex` for `*.vercel.app`. `https://www.bloommatrix.in` matched none of these, so every authenticated fetch from the new domain was browser-blocked — including `AuthRoleContext`'s `/api/v1/team/me` (role stayed `null` → sidebar's `role === "owner"` gates hid almost every item) and the operator console's `/api/v1/operator/me`. **Fix**: added `https://www.bloommatrix.in` and `https://bloommatrix.in` to the allowlist. Confirmed live via a manual `OPTIONS` preflight curl showing the correct `access-control-allow-origin` header post-deploy.
- **Root cause 2 (basePath)**: 4 raw `<a href="/...">` tags (operator/login, contact, terms-and-conditions ×2) plus the operator console's top nav (`operator-sidebar.tsx`, dynamic `href={item.href}`) bypassed the automatic basePath prefix — fixed by converting all to `next/link`.
- **Root cause 3 (pre-existing, unrelated to the migration, only surfaced once CORS let traffic through)**: `get_subscription` in `operator.py` crashed with `AttributeError: 'NoneType' object has no attribute 'data'` — `maybe_single().execute()` returns `None` (not a response object with `.data=None`) when zero rows match, for any tenant with no `tenant_subscriptions` row. Confirmed via Render logs dating back to **June 30**, well before this migration. Fix: `if not sub` guard before `.data`. Same latent gap likely exists at other `maybe_single()` call sites in `operator.py` (e.g. `client_overview`'s `tenant`/`owner_row`) — not yet patched, no reported failure there; see active-backlog.md.
- **Root cause 4 (also pre-existing)**: `client_config` and `get_features_catalog` intermittently 500'd on `httpx.RemoteProtocolError: Server disconnected` talking to Supabase/Postgrest, with no retry. Fix: added `_execute_with_retry()` (retry-once-on-transient-disconnect) to `operator.py`, matching the retry pattern already in `dependencies/auth.py` (retry-then-503) and the catch-and-fallback pattern in `chat_handovers.py` — now three call sites share this failure mode; a shared helper is worth extracting if a fourth shows up.
- **Deploy mechanics learned**: `srv-d7m3l4d7vvec738do3mg` (`aira-ai-5tfr`) has `autoDeploy: no` — pushing to `main` does NOT redeploy the backend. Confirmed trick: `mcp__render__update_environment_variables` (even a no-op-ish value touch like re-setting `FRONTEND_URL`) forces Render to pull latest `main` and redeploy, without needing dashboard access. Used twice this session to ship both fix rounds.
- **Diagnostic method**: root-caused via live `mcp__render__list_logs` (found the exact traceback + line number for each bug) rather than guessing from symptoms — a first grep sweep for raw anchors used an unsupported `grep -E` lookahead and silently found nothing, which would have been reported as "all clear" if not cross-checked against actual runtime evidence.

**2026-07-02 — Telegram settings save fixed: removed blocking `setWebhook` call from PATCH save path**
- **Symptom**: user reported "Cannot reach the server" every time they saved a Telegram bot token, plus intermittent "Load failed" on the settings page — but explicitly confirmed WhatsApp/Instagram/Facebook saves worked fine from the same session/origin. That differential (one channel fails, three don't, same endpoint/method/origin) ruled out CORS and pointed at channel-specific save-path code — see subsystem-notes.md → Channel settings save path for the full diagnostic trap writeup (a `net::ERR_FAILED` with no HTTP status looks like a CORS error in Chromium's console even when it isn't).
- **Root cause**: `update_settings()` in `app_settings.py` called `await setup_telegram_webhook(tg_token, tenant_id)` synchronously inside the PATCH handler — a live outbound HTTPS call to `api.telegram.org` that had to complete before the response could be sent. WhatsApp/IG/FB saves never made any outbound call; they upsert credentials and return immediately. On Render's free tier, a slow/hung Telegram API call could exceed the proxy's timeout, killing the TCP connection before the browser received any response — indistinguishable from a network failure client-side.
- **Fix**: Telegram save now matches the other three channels exactly — validates token format locally (regex only, no network call), upserts `telegram_status="configured"`, and clears any stale `telegram_webhook_secret` (so an old secret can't validate updates against a newly-saved token). `setup_telegram_webhook()` is unchanged and still lives in `POST /activate`'s telegram branch — the outbound call now only happens on explicit user action (the "Validate & Activate" button), where a slow Telegram response is a bounded, visible spinner state instead of a silent request killer.
- **Verified**: full backend suite 154/154 passing (`test_telegram_settings.py`'s 8 tests cover incident dedup, 401-only token-invalid detection, webhook-health inclusion, and both activate-branch paths — none needed changes, since they test `setup_telegram_webhook`/`activate_channel` directly, not the save path). Frontend `isChannelConfigured`/Activate-button gating already worked with the new `"configured"` status without changes.
- **Not yet confirmed live**: per the entry above, `aira-ai-5tfr` has `autoDeploy: no` — this fix was pushed to `main` (commit `a7cc6a1`→rebased) but has NOT been confirmed deployed to Render. Do not tell the user "it's fixed in production" until a redeploy is triggered (`mcp__render__update_environment_variables` no-op trick) and verified live.

**2026-07-02 — Admin-customizable subscription plans (Migration 127); Fleet + impersonation removed**
- **Decision**: Replaced the 6 hardcoded messaging/telecalling/AI-tier plans with a single admin-authored `plans` model (`id, name, monthly_price, feature_keys jsonb, quotas jsonb, active, created_at`). `tenant_subscriptions` now carries one nullable `plan_id` instead of `messaging_plan_id`/`telecalling_plan_id`/`ai_tier`/`custom_overrides`. `quotas` keys are the canonical `tenant_usage_counters.metric` names directly (`message_sent`/`ai_reply`/`call_minute`/`team_seat_active`/`storage_gb`/`ai_call_summary`/`ai_call_scoring`) — the old translation layer (`"messages"`→`message_sent` etc.) is gone. AI tier is no longer a separate concept; it was always billing-only (never read in the AI generation path), so it's just quota now. Fleet page and "View as tenant" impersonation (routes, frontend, tests) were deleted outright, not deprecated. Full design/plan at `docs/superpowers/specs/2026-07-02-admin-subscription-plans-design.md` and `docs/superpowers/plans/2026-07-02-admin-subscription-plans.md`.
- **Rationale**: User wanted the system admin to fully define what each plan includes (features + quotas + price) from the console itself, with no predefined plans and billing/usage driven entirely by the assigned plan. See [subsystem-notes.md](../context/subsystem-notes.md) → Operator Console Monetization for the load-bearing details (quota key naming, soft-delete semantics, what still depends on the old `_build_fleet_rows` helper).
- **Migration safety**: confirmed live before writing the migration — `tenant_subscriptions` had zero rows, so the 6 seed `plans` rows were deleted outright (no backfill needed, no tenant lost entitlements). `plans` ships genuinely empty; the admin starts from scratch via the new Subscription page (in Fleet's old sidebar slot).
- **Built via subagent-driven-development, 11 tasks, working in place on `main`** (no worktree, by explicit user choice). One implementer subagent hit a session limit mid-task (Task 5); the controller independently verified its uncommitted diff via grep + tests before committing, and task review caught one file that verification had missed (a docstring edit left unstaged) — fixed in a follow-up commit, re-reviewed clean. A controller-found bug between tasks (`_build_fleet_rows` still selecting the now-dropped `tenant_subscriptions.ai_tier` column, which would have 400'd every `/alerts` poll) was fixed before it shipped. The final whole-branch review caught one more cross-task leftover no single task's diff would have surfaced: `update_features` (a separate, untouched channel-toggle route) still read/wrote the dropped `custom_overrides` column — unreachable today but a live landmine and a direct spec contradiction; fixed same-day.
- **Lesson**: per-task review catches task-scoped regressions; it does NOT catch a shared helper or unrelated route silently made stale by a schema change, because that code never appears in the task's own diff. Both real bugs this session (`_build_fleet_rows`/`ai_tier`, `update_features`/`custom_overrides`) were caught only because someone read the *whole* codebase for the dropped column names, not because any task's scoped diff review found them — worth a deliberate "grep the repo for every dropped column/field name" pass on any future schema-shrinking migration, not just trusting task-by-task review to catch it.
- **Left as explicit non-goals / follow-ups** (see active-backlog.md): editing a plan's price/quotas does not propagate to tenants already assigned to it (no-op until an admin explicitly reassigns); quota enforcement stays track-only (no hard-blocking), unchanged from the pre-existing decision; Feature Store's plan dropdown shows no matching option if the tenant's assigned plan was later soft-deleted (cosmetic — the "Assigned Plan" card above it still renders correctly, and Apply stays correctly disabled).

**2026-07-04 — Itemized subscription pricing + client-driven approval flow (Migration 128); supersedes the 2026-07-02 admin-assigns-one-plan model**
- **Decision**: Replaced "admin assigns one whole plan to a tenant" with a client-driven cart: the client picks individual priced catalog items (channels, telecalling type, seats, numbers, notifications), submits a cart, and is gated out of the entire product until an admin manually confirms payment and approves. New tables `tenant_subscription_items` (current effective entitlements — the only table enforcement reads) and `subscription_requests` (append-only approval log — one row per cart submission or later top-up ask). `feature_catalog` gained 9 new "sellable" rows (`inbound_messaging`, `outbound_messaging`, `telecalling_sim`, `telecalling_telecmi`, `bulk_lead_upload`, `telecaller_seats`, `numbers_pool`, `notifications`, plus an internal `telecalling.upload` flag) that each turn on a bundle of the existing 43 granular internal feature flags via the previously-unused `depends_on` column. `plans` is repurposed as **Packages** — optional discounted bundles of sellable items, price always computed from the catalog (`sum(item price × qty) × (1 - discount%)`), never hand-typed. `resolve_entitlements()` rewritten to read from `tenant_subscription_items` instead of `plans.plan_id` (same signature/return shape, so existing callers didn't need changes). `check_quota()` rewritten from dead/unused code into a real pure hard-cap check (no longer upserts — callers must call `increment_usage`/`meter()` separately after a guarded action succeeds); `included == 0` now means blocked (not purchased), not unlimited.
- **Hard-cap enforcement added** at 4 action points, reusing `check_quota`: telecaller invite (`team.py`, against `telecaller_seats`), phone-number add (`numbers.py`, against new `phone_number` metric), AI auto-reply generation (`ai_reply.py`, against `ai_reply` — fails safe, webhook still returns 200), call initiation (`calls.py`, against `call_minute`, checked pre-call since minutes are only known post-call via the TeleCMI CDR webhook). **Outbound broadcast/template sends were explicitly scoped OUT** of hard enforcement mid-build (user correction: "I need to track the ai reply not the template messages being sent") — `broadcast_executor.py` is unchanged, still track-only `meter()`, no `check_quota` gate.
- **Admin console**: Feature Store (the old per-tenant plan-picker) deleted outright; replaced by a read-only "Entitlements" view (`client/[id]/views/entitlements.tsx`, backed by new `GET /operator/clients/{tenant_id}/entitlements`). The Subscription page (`operator/(console)/subscription/page.tsx`) is now two tabs: **Pricing Catalog** (edit `monthly_price`/`unit_price`/`included_qty` on the 8 sellable SKUs via new `PATCH /operator/catalog/{feature_key}`) and **Packages** (bundle CRUD, `PlanPayload` now `{name, discount_percent, items: [{feature_key, quantity}]}` instead of `{feature_keys, quotas}`). New **Approval Queue** page (`operator/(console)/subscription-requests/`) lists pending/approved/rejected requests with a tenant-name join, a manual "payment confirmed" checkbox gating Approve, and a required reason for Reject.
- **Client-facing** (all new — no client subscription/billing surface existed before this): dashboard shell (`ClientLayout.tsx`) gates the entire app behind `tenant_subscriptions.status` — `none`/`pending_approval` renders only a full-page Subscriptions cart (`dashboard/subscriptions/`), `active` unlocks everything. Settings gained a 7th "Subscription" tab (usage meters + "Request more" reusing the same `CartBuilder` component in `addon` mode). Settings' Notifications tab is now hidden unless the tenant purchased the `notifications` item (fails open for pre-existing tenants with zero purchased items).
- **`create_client` no longer auto-assigns anything** — new tenants get no `tenant_subscriptions` row at all at creation (gated by default); the operator onboarding wizard's plan-picker step was removed (3 steps instead of 4).
- **Rollout**: existing tenants backfilled to `status='active'` (grandfathered, never gated) via `insert ... on conflict (tenant_id) do nothing`. **Caught live**: the "zero rows" assumption from migration 127 (2026-07-02) was stale two days later — 2 real tenants already had `tenant_subscriptions` rows at `status='trial'` from ordinary onboarding in the interim, so the `ON CONFLICT DO NOTHING` backfill silently skipped them. Fixed with a manually-scoped `UPDATE ... WHERE tenant_id IN (...) AND status='trial'` (never a broad `status != 'active'` predicate — the auto-mode classifier correctly blocked that first attempt as a production-data-mass-mutation risk, since it could also clobber deliberately `suspended`/`past_due` tenants).
- **Two real pricing bugs caught and fixed pre-ship**: (1) `_compute_package_price` in `operator.py` only read `feature_catalog.monthly_price`, but `telecaller_seats`/`numbers_pool` are priced via `unit_price` with `monthly_price=0` — a package bundling seats/numbers would've always priced them at ₹0; fixed to match the same price-resolution logic already correct in `subscription_requests.py::_price_for_item`. (2) `features/catalog` operator endpoint was missing `unit_price` in its select — needed by the new Pricing Catalog editor.
- **Built via superpowers inline-execution** (13-task plan, `docs/superpowers/plans/2026-07-04-itemized-subscription-pricing.md`; design at `docs/superpowers/specs/2026-07-04-itemized-subscription-pricing-design.md`) in an isolated git worktree (`itemized-subscription-pricing` branch), fast-forward merged to local `main` after full verification (287 backend tests, clean `next lint` + `tsc`). **Not pushed to origin.**
- **Bug found + fixed post-merge (2026-07-04, by the user directly, commit `96fbf37` "approve error fix")**: approving a live subscription request 500'd with a generic "Failed to fetch" on the frontend — root cause was the exact `maybe_single().execute()` returns `None`-not-an-object gotcha already documented in subsystem-notes.md, recurring in `approve_request`'s `existing = ...maybe_single().execute()` / `existing.data` access, which crashes whenever a tenant's request includes a feature_key they've never purchased before (the normal first-purchase case — reproduced live on a `numbers_pool` top-up for tenant "Astro Tamil"). See active-backlog.md — the user was still sweeping the same pattern across the rest of the itemized-subscriptions code (uncommitted) as of session end, alongside unrelated further build-out (billing-period/renewal-cycle model, marginal pricing across top-ups, moving Subscription out of Settings into its own top-level page). Not reviewed by me in detail; full suite 289/289 passing.

**2026-07-05 — Aira Sync Phase 2 (call recording upload) built, reviewed, fixed, then reverted — blocked on default-dialer variance**
- **What happened**: user had another model build Phase 2 (recording upload to complement Phase 1's call-log-metadata-only sync) from a detailed prompt (saved at `.agents/projects/phase2-recording-prompt.md`, now historical — feature is reverted). I reviewed the diff and found 5 real bugs, most severe: `RecordingScanner.kt`'s privacy filter was **fail-open** — a recording whose filename had no parseable phone number was uploaded unconditionally instead of being dropped, directly violating the "personal calls never leave the phone" invariant Phase 1 established. Also found: a retry-regression in `SyncWorker` (failed call-log POST silently returned `Result.success()` instead of `Result.retry()`), a non-functional folder picker (only listed ancestor dirs, never let the user drill into subfolders), a backend fallback-match that picked "most recent lead call" instead of "closest in time" (misattachment risk on busy shifts), and a permission-chain stall (no `onResume()` recheck after the All-Files-Access Settings screen).
- **Fixed via 3 parallel subagents** (user's explicit ask: "fix these yourself using sub agent driven development"), each scoped to a disjoint file set to avoid merge conflicts: (1) Android sync-core — `RecordingScanner.kt`/`SyncWorker.kt`, fixed the fail-open filter (now correlates unmatched-filename recordings against on-device lead-call timestamps within a 5-min window, drops if no match) and the retry regression; (2) Android UI — `FolderPickerActivity.kt` rewritten as a real drill-down browser, `MainActivity.onResume()` added; (3) backend — `sim_recording`'s fallback match now picks by closest `created_at` via `min(..., key=...)`, not recency-first. All three verified independently (manual diff read, static tests re-run, `py_compile`) before committing.
- **Caught one more bug during the build's own on-device-test build**: `SyncWorker.kt` used `File.toRequestBody(...)` for the multipart audio part — OkHttp only defines that extension on `String`/`ByteArray`/`ByteString`; `File` needs `.asRequestBody()`. Only surfaced because the APK was actually compiled (`./gradlew assembleDebug`) before sideloading — none of the 3 review-fix subagents ran a build (correctly, given their sandboxes may lack the toolchain), so a compile-only bug like this can survive a source-level review + static-test pass undetected. Worth remembering: source-text/static tests (this project's `test_sim_*_static.py` pattern, used because the sandbox lacks `httpx`/`fastapi` for live imports) do not catch compile errors — a real build is still needed as a final gate for Android changes specifically.
- **Decision: reverted, not kept** — on-device testing (screenshots of the phone's actual "Call recording" settings) revealed the phone's default dialer was **Google's Phone app**, not the OEM's native dialer. Google's Phone app restricts call recording to a manual per-number whitelist (Play-policy-driven, region-gated even for the "unknown numbers" toggle) — it does **not** auto-record everything the way the whole Phase 2 design assumed. The known-path auto-detect list (`/storage/emulated/0/MIUI/sound_recorder/call_rec` etc.) only ever gets populated by the OEM's *own* dialer/recorder, e.g. MIUI's stock Dialer — which does auto-record unrestricted (call recording is legal in India, one-party consent), precisely because it's a privileged system app, not subject to the same Play-policy restriction third-party/Google apps face. See subsystem-notes.md for the full why (Android's `VOICE_CALL` audio-source restriction, why an in-app recorder isn't a viable alternative). User decided Phase 1 (call-log metadata only) is sufficient for now rather than solving the fleet-wide default-dialer problem. Reverted cleanly via `git revert` (2 commits: `a4e9019` feat, `080c630` asRequestBody fix), landed as `067d09b` on `main`. Verified the working tree post-revert is byte-identical to the pre-Phase-2 baseline (diffed against the pre-build commit) aside from unrelated concurrent work. See active-backlog.md for the reopened/still-blocked status.

**2026-07-05 — Google Ads → WhatsApp lead attribution via message tags (commit `04375d9`, on `main`, pushed)**
- **Problem**: All ad attribution keyed on Meta's `referral` object (`source_type=="ad"`), which ONLY Meta populates (CTWA / Click-to-Messenger / Click-to-IG-DM). A Google ad driving to a `wa.me` link produces a normal inbound message with no referral → the lead landed as `origin=organic` with no campaign credit. Google got zero attribution.
- **Decision**: Tag-based attribution. Client points a Google ad at a `wa.me` link whose pre-filled `?text=` ends with a `[GADS:<slug>]` tag. On first inbound the WhatsApp webhook parses the tag and links the lead to a `platform="google"` `ad_campaigns` row via the existing `get_or_create_campaign()` — so it flows into `build_ad_performance()` and the Inbound Leads UI for free (both are already platform-agnostic; `growth.py::PLATFORMS` already included `"google"`).
- **New module** `services/google_ads_attribution.py` — pure (no DB/network): `parse_google_ref(text)→GoogleAdRef|None` (regex `\[(?:GADS|GOOGLE)[:_-]([A-Za-z0-9_]+)\]`, case-insensitive; optional `[GCLID:...]` captured but not yet used), `build_tracked_wa_link(phone, campaign, gclid=, greeting=)` (raises ValueError on invalid slug so a malformed link can't ship), `slugify_campaign(name)`. Single source of truth for the tag format — a build→parse round-trip test guarantees generator and parser can't drift. `external_campaign_id` is namespaced `google:<slug>` so it can never collide with a Meta ad id.
- **Webhook wiring** (`webhook.py`, right after the CTWA block): sets `ad_attributed` flag in the CTWA block; Google block runs only `if not ad_attributed` and only sets `ad_campaign_id` when currently null (never clobbers a prior/Meta attribution). Fires on any inbound whose body carries the tag (not gated on is_first_message — the null-check makes repeats idempotent).
- **Endpoint** `GET /api/v1/inbound-leads/google-link?campaign=&gclid=` → looks up tenant's active **primary** WhatsApp number from `phone_numbers` (role=primary, status=active — where channel activation writes it, `app_settings.py:~426`), returns `{link, campaign_slug, whatsapp_number}`. 400s if no active number.
- **UI**: "Google Ads Link" button + `GoogleAdsLinkModal` on the Inbound Leads page (`InboundLeadsClient.tsx`) — client types a campaign name, gets a copy-ready tracked link. Exists specifically so clients can't hand-format (and mis-format) the tag. `api.inboundLeads.googleLink()` in `lib/api.ts`.
- **Scope**: WhatsApp only (the stated use case: Google ad → WA CTA). FB/IG DM not wired. `gclid` is captured + logged but NOT yet reconciled against the Google Ads API for real spend — that's the deliberate "big version" follow-up (see active-backlog.md).
- **Tests**: `test_google_ads_attribution.py` (14 pure tests). Full backend suite green. Verified end-to-end against an in-memory fake DB driving the REAL `parse_google_ref`+`get_or_create_campaign` (organic→ad flip + idempotency on repeat). **NOT yet verified with a live WhatsApp message to a real tenant** — that's the one remaining true green light.

**2026-07-05 — Started Groq → Sarvam provider migration (call transcription first)**
- **Decision**: Begin migrating select Groq workloads to Sarvam AI, whose Saaras/Bulbul/Sarvam-Vision/Sarvam-30B-105B models are purpose-built for Indic-language + telephony-audio use cases Aira's leads/callers actually produce. Sequenced as several small swaps, not one flip — see active-backlog.md for the full remaining sequence and rationale per workload.
- **Landed**: `call_summarizer.transcribe_recording()` now calls Sarvam's `saaras:v3` model (`POST https://api.sarvam.ai/speech-to-text`, multipart, `api-subscription-key` header) instead of Groq `whisper-large-v3-turbo`. New `services/sarvam_client.py` (`get_sarvam_api_key`) mirrors `groq_client.py`'s tenant-aware key lookup pattern. New `sarvam_api_key` setting in `config.py` (added to the missing-secret warning list). `analyze_call()` (the LLM summary/eval pass) is **unchanged** — still Groq `llama-3.3-70b-versatile`, pending eval-gated comparison against Sarvam-30B/105B before any swap.
- **Gotcha hit while adding tests**: `test_call_summarizer_eval_v2.py`'s file-level `patch.dict("sys.modules", {"groq": ..., "app.config": ...})` (used to stub Groq/config at import time) snapshots and restores the **entire** `sys.modules` dict on exit, not just the two explicit keys — so `app.services.call_summarizer` (and anything else imported inside that `with` block) gets silently dropped from the module cache afterward. A later string-target `patch("app.services.call_summarizer.X", ...)` then re-imports a phantom, unmocked copy of the module that the test never actually exercises — tests can pass/fail by accident based on whether real credentials happen to be configured, not because the mock took effect. Fixed by patching directly against the already-held module reference (`call_summarizer.get_sarvam_api_key = MagicMock(...)` / `patch.object(call_summarizer.httpx, "AsyncClient")`) instead of dotted-string `patch()` — same pattern the file's pre-existing `get_groq_client` tests already used, for this exact reason.
- **Not touched yet**: `knowledge_service.py`'s vision OCR call (`llama-3.2-11b-vision-preview`) — Sarvam's equivalent (Sarvam Vision / Document Digitization) is an async job workflow (create job → get upload URL → upload → start → poll status → get download URL → download ZIP), not a synchronous one-shot call like Groq's, so it's a materially bigger change than a model-constant swap. Treating as its own follow-up.
- **Stack decision to revisit**: `stack-and-rules.md`'s "AI (Replies & Scoring): Groq only, do NOT add Gemini/OpenAI imports" Locked Provider line is now stale — needs to become a per-workload table (transcription→Sarvam, replies/scoring→Groq pending eval, vision→TBD) once the sequence below lands.

**2026-07-05 — Groq → Sarvam migration, step 2: knowledge-base image OCR now on Sarvam Vision (Document Digitization)**
- **Decision**: `knowledge_service.py`'s image-upload branch (previously Groq `llama-3.2-11b-vision-preview`, one synchronous chat-completion call) now runs Sarvam's Document Digitization job workflow. New module `services/sarvam_document_intelligence.py::extract_text_from_image()` does the full job lifecycle synchronously (it's already called via `asyncio.to_thread` from `process_document`, so a blocking `httpx.Client` + `time.sleep` poll loop matches the existing execution model without an async rewrite): create job (`POST /doc-digitization/job/v1`, `language="en-IN"`, `output_format="md"`) → get presigned upload URL (`POST .../upload-files`) → `PUT` the file → start (`POST .../{job_id}/start`) → poll `GET .../{job_id}/status` every 3s up to a 120s timeout → get presigned download URL (`POST .../{job_id}/download-files`) → download + unzip, concatenating all `.md` files in the output ZIP.
- **Real API constraint found, not assumed**: Sarvam's Document Digitization only accepts **PDF or ZIP** uploads, and a ZIP's images must be **JPEG/PNG only** — unlike Groq's vision endpoint, which accepted any `image/*` mime type directly as a base64 data URL. `_zip_single_image()` wraps the raw image bytes into a single-file ZIP before upload and raises `ValueError` up-front for unsupported formats (webp/gif/bmp etc.) rather than making a doomed API call — surfaces as the document landing in `status="failed"` with a clear error message, same as any other extraction failure.
- **Known limitation, not solved**: `language` is hardcoded to `en-IN` — there's no per-document language selection in `process_document`'s signature, and Sarvam's Document Digitization API requires one BCP-47 language up front (no auto-detect option, unlike their Speech-to-Text API). Tenant documents in pure Tamil/Hindi may extract with lower accuracy than mixed/English content. Not fixed now — flagging for whoever picks up per-tenant document language config next.
- **Tests**: `test_sarvam_document_intelligence.py` (10 tests: zip-wrapping, markdown extraction from output ZIP, full job flow mocked at the `httpx.Client` boundary — immediate completion, multi-poll completion, Failed job state, poll timeout, unsupported mime rejected pre-flight) + 2 new tests in `test_knowledge_service.py` (routes to Sarvam correctly, wraps Sarvam failures into the existing `ValueError("Could not extract text from...")` path). Full backend suite: 316/316 passing (up from 304 before this + the transcription swap combined).
- **Remaining in the Groq→Sarvam sequence**: eval-gate the LLM swap (7 call-sites on `llama-3.3-70b-versatile`) before touching it — see active-backlog.md.

**2026-07-05 — Groq → Sarvam migration, step 3: AI WhatsApp replies now on Sarvam-30B (skipped the eval-gate, user's explicit call)**
- **Decision**: `ai_reply.py`'s reply-generation path (`_llm_complete`/`_llm_chat`, renamed from `_groq_complete`/`_groq_chat`) now calls Sarvam's Chat Completions API (`sarvam-30b`) instead of Groq `llama-3.3-70b-versatile`. Direct swap, no staged/per-tenant rollout, no logic changes to prompts, `[COLLECT_DONE]` parsing, escalation triggers, or language detection — only the model call underneath changed. User explicitly chose this over the more cautious "eval-gate first" plan flagged in the previous entry, given this workload is the highest-blast-radius one so far (live, customer-facing, per-tenant custom prompts).
- **New endpoint contract** (differs from the other two Sarvam APIs already in use): `POST https://api.sarvam.ai/v1/chat/completions`, `Authorization: Bearer <key>` (not the `api-subscription-key` header the Speech-to-Text/Document Digitization APIs use), OpenAI-compatible request/response shape. New reusable `sarvam_client.sarvam_chat_completion()` — this is the first Sarvam LLM-reasoning integration in the codebase, so it's written generically in case other call-sites (scoring, coaching, digests — still on Groq per the prior entry) get swapped later.
- **Real residual risk, flagged not solved**: escalation-trigger phrase matching (`_ESCALATION_PHRASES`, `_GENERIC_FALLBACK_MARKERS`) and `[COLLECT_DONE]{json}` emission reliability depend on the model actually following the system prompt's exact-phrasing instructions — this can't be verified by unit tests, only by real conversations. **User owes a manual smoke test** (English + Tamil + Tanglish, ideally against a test lead) before fully trusting this in production — same category of risk as the SIM APK hardware-test lesson, just for prompt-following instead of a physical device.
- **Cleanup while in the file**: removed the now-dead `from groq import AsyncGroq` import and updated three stale "Groq" log-message/comment references to be provider-neutral ("LLM"), since they'd otherwise misdescribe what the code does going forward.
- **Tests**: `test_sarvam_chat_completion.py` (3 tests — success, HTTP failure, missing key) + `test_ai_reply_llm_wiring.py` (3 tests — `_llm_complete`/`_llm_chat` call `sarvam_chat_completion` with the right model/params, `_REPLY_MODEL` value). Full backend suite: 322/322 passing.
- **LLM reasoning workloads NOT touched**: scoring, call coaching, call digests, AI tuning, lead briefs, `analyze_call` — all still Groq `llama-3.3-70b-versatile`, per the user's earlier explicit call to defer those (2026-07-05, same day). Only `ai_reply.py`'s reply generation moved.

**2026-07-05 — Removed the `[COLLECT_DONE]` structured-data-collection feature (branch `refactor/remove-collect-done-signal`, not on main)**
- **What it was (for future readers)**: some tenants' custom AI Tune prompts instructed the model to end a reply with a hidden `[COLLECT_DONE]{"budget": "...", "course": "..."}` tag once it had gathered enough info from the customer. `ai_reply.py` stripped the tag before sending the WhatsApp message, parsed the JSON, and saved it to `leads.collected_data`.
- **Why removed**: user decision — no requirements captured beyond "remove it." Checked for downstream impact first: `collected_data`'s only consumer is `reengagement_service.py:193`, which fills custom WhatsApp template variables (anything besides `name`/`phone`) from it when sending proactive re-engagement messages.
- **What changed**: removed the `_collect_match` regex parse + `db.table("leads").update({"collected_data": ...})` save block and its now-redundant `new_segment = segment` pre-initialization (a second, correctly-placed `new_segment = segment` already exists right before the Score Engine section a few lines later). **Deliberately kept** the `_display_text = re.sub(r'^\s*\[COLLECT_DONE\]...', ...)` strip step — a tenant's *stored* custom prompt (DB content, not code) could still instruct the model to emit the tag, and removing the strip too would leak the raw `[COLLECT_DONE]{...}` text straight into a customer's WhatsApp message. The strip is now purely defensive against that legacy-prompt case.
- **Consequence, not fixed**: `collected_data` will stay permanently empty going forward. Any tenant's re-engagement template using a custom variable beyond `name`/`phone` will render it as an empty string instead of the previously-collected value — degrades gracefully (no crash), but is a real, silent personalization downgrade for any tenant actually using it. Nobody checked the live DB for whether any tenant's templates currently use non-name/phone variables before removing this.
- **Git status**: this commit lives on branch `refactor/remove-collect-done-signal` only, NOT merged/rebased onto `main`. The same commit also carries the already-approved, already-tested Groq→Sarvam AI-reply-provider swap (previous entry) because both changes landed in the same uncommitted `ai_reply.py` diff before either was committed — user explicitly chose "commit both together" over a manual patch-split to isolate them, since splitting a real file's hunks non-interactively carries its own error risk. `sarvam_client.py` and `config.py`'s `sarvam_api_key` field are included in the same commit as required dependencies of the reply swap.
- **Tests**: no new tests added (nothing to test — it's a deletion). Full backend suite re-run after removal: 322/322 passing, confirming `reengagement_service.py`'s tests still pass with `collected_data` simply staying empty.
