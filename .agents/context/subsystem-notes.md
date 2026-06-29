# Aira AI — Subsystem Notes & Load-Bearing Gotchas

> Operational truths and traps an agent MUST know **before editing a subsystem**. The auto-built
> `graphify-out/wiki/` describes structure; this file holds the *why* and the *don't-do-X* that
> structure can't. Migrated from Claude memory 2026-06-24. Keep condensed; link migrations in
> [decisions/log.md](../decisions/log.md).

## Broadcast delivery & retry
- **Delivery truth = `messages.delivery_status`** (+ `delivery_error_code`/`_title`), set by the delivery webhook (webhook.py ~L463-517). `broadcast_recipients.send_status` only reflects **Meta API acceptance** (returns message_id), NOT delivery — it's the WRONG signal for "did the lead receive it."
- **`broadcast_recipients.send_status` delivery-failed flip is DEAD CODE** (3 reasons: CHECK constraint rejects `'delivery_failed'`; executor stores `meta_message_id` only on `messages`, not the recipient row, so `.eq` matches nothing; errors swallowed). Never trust `send_status` for delivery.
- **Per-send / per-broadcast attribution = `services/delivery_status.py` `nearest_record`/`nearest_status`** (the outbound `messages` row nearest in time, −2min/+10min). Used by all 3 sites (upload.py history+segment CSV, tags.py stats) so they never disagree. **NEVER** use max-priority-in-window (an adjacent broadcast's `sent` masks this one's `failed`) or any-failed-in-window (over-attributes).
- **`leads.whatsapp_undeliverable`** = sticky lead-level "is this number currently reachable" flag (resets on inbound + delivered/read receipt). Good for re-engagement skip; **WRONG for per-broadcast stats** (never reset per send).
- **Error codes:** `131049` = marketing cap ("healthy ecosystem engagement") — manifests async as a `failed` webhook OR a silent accepted-never-delivered; retry-worthy. `131026` = wrong number → set `whatsapp_undeliverable`, never retry. Transient set `{131049,131048,131056,130472}` does NOT set undeliverable.
- **Auto-retry (migration 104):** eligibility = "sent but no delivered/read receipt by cutoff" minus undeliverable/opted-out/replied-since/disengaged (`outbound_no_reply_count>=3`). Each attempt = a CHILD `scheduled_broadcasts` row (`retry_of`/`retry_attempt`) the 1-min scheduler sends. Per-broadcast toggle; fires at wall-clock time in tenant tz with a **≥20h guard** (cap must have reset). `services/broadcast_retry.py`.
- Both `broadcast_recipients.meta_message_id` and `leads.whatsapp_undeliverable` exist in prod but were added manually — **no migration**. Durable fix (not done): store `meta_message_id` on the recipient at send time for an exact join.

## Scoring (`services/scoring_engine.py` v2, on main)
- Composite: `arc + intent_delta + engagement_delta`, clamped 1–10. Language-aware arc (Tamil/Hindi rejection patterns). Rejection sentinel → instant score=1/segment=D on stop/not-interested/வேண்டாம். Segment lock: upgrade immediate, drop needs 2 consecutive confirmations. Engagement decay every 6h. Arc fallback on Groq failure = current arc, not hardcoded 5.
- **The segment-A/assigned gate is GONE (2026-06-01).** Scoring fires on every inbound unconditionally.
- **Per-broadcast scoring (migration 076):** `broadcast_lead_scores` table, `UNIQUE(broadcast_id, lead_id)`, seeded score=5/seg=C per send; arc window restricted to messages **after `broadcast_sent_at`** so a cold biscuit reply can't poison the ice-cream score. `compute_score(broadcast_context={broadcast_id,broadcast_sent_at,tag_id})` writes both the per-broadcast row and global `leads`. Rolls up to `lead_tag_interest` (most-recent broadcast wins).
- `lead_scorer.py` (legacy two-pass) is still called only on the AI-disabled branch — tech debt to retire (see backlog).

## Call evaluation (`call_summarizer.py` / `call_scorer.py` / `call_digest.py`)
- Two scores: `call_logs.score` (per-call, set once at outcome-mark, never changes) vs `callers.overall_score` (rolling, recomputed twice — at outcome-mark, then after AI eval ~1-2min later). Composite `_effective_score = 0.5×outcome + 0.5×AI`; no AI eval → 100% outcome (no penalty).
- **Gate before Whisper** (`_run_summarization`): skip AI entirely if outcome ∈ {no_answer, voicemail} or duration<30s. Halves token cost (~$3-5/mo total at 10 callers × 50 calls).
- `analyze_call()` = single merged LLM pass (summary + evaluation). `_GROQ_SEMAPHORE = asyncio.Semaphore(5)` guards burst at shift-end. Monthly winner needs ≥20 calls. Daily digest job fires 14:00 UTC.

## Knowledge base (pgvector RAG)
- Jina `jina-embeddings-v3` @512-dim (Matryoshka-truncated), `JINA_API_KEY`. **Why Jina:** Groq has no embeddings API; Supabase `gte-small` is English-only (app serves Tamil/Hinglish → silent degrade); Voyage had no usable free tier. Jina = free 10M tokens, true multilingual.
- RPCs (`insert_knowledge_chunk`/`match_knowledge_chunks`) take the embedding as **text** and cast `::vector(512)` inside (sidesteps supabase-py vector serialization).
- Modes via `kb_retrieval_mode` per-tenant: semantic (default) | keyword (tsvector+pg_trgm, no Jina) | hybrid (RRF). **Always falls back to full-text injection** on error/empty. `reply_source="knowledge"`.
- **Gotcha:** `create table if not exists` no-op'd against a leftover `vector(768)` table → inserts 400'd → silent full-text fallback. Always check for pre-existing tables before `if not exists`.

## Frontend performance pattern
- **Recipe:** `page.tsx` (async server component) fetches a seed via `lib/serverApi.ts serverFetchJson<T>(path, token, 2500ms)` (timeout-guarded → null on fail; MANDATORY or a cold backend white-screens SSR) → passes to a `<Route>Client.tsx` as SWR `fallbackData`. **Gate on DATA presence, not role** (seeded owners skip the spinner).
- `lib/api.ts apiFetch`: GET-only retry (network/timeout/502-503-504) + backoff + 30s GET timeout. **Mutations NEVER retry** (no double broadcasts/sends/assignments).
- Server components: `import type` for `@/lib/api` types (it pulls the browser supabase client).
- Render free tier sleeps after 15min → cold-start tail + **in-process APScheduler doesn't run**; keep-alive cron pings every 14min. One scaling caveat: externalize APScheduler before running >1 backend instance.

## Conversations UI (3-panel)
- `conversations/page.tsx`: left list (340px) | center ChatThread | right LeadDetailsPanel (320px); both collapsible, state in localStorage. `getAvatarColor(id)` duplicated in conversation-list.tsx and chat-thread.tsx **by design**. Input bar is never AI-gated. All 3 panels stay in sync via `onLeadUpdate`.

## Telecalling assignment (services/assignment.py)
- **State-based, not transition-triggered** (the original leak: channel webhooks force-assigned ungated, promotions never assigned). One `maybe_assign_lead()` funnel gated on `telecalling_config` (enabled+segment+channel; channel=None bypasses for call/manual/CSV) at every promotion site, PLUS a 2-min `sweep_unassigned_leads` guarantee.
- Round-robin = **least-loaded counting OPEN leads only** (exclude segment D + converted) so closers aren't punished. Auto-assign switch = `telecalling_config.enabled`.
- **Push/Pull mode** (`telecalling_config.assignment_mode`): PUSH = auto round-robin; PULL = blind shark-tank (ALL auto-assign paths no-op including `reassign_backlog`; callers draw top-scored lead via `GET /calls/next-lead`, atomic claim). Not browseable cherry-pick.
- **Shared callback claim board:** overdue callbacks claimed via `POST /leads/{id}/takeover` (CAS-guarded `.eq("assigned_to", old)` else 409). Live Call Shield: `is_caller_on_call()` — a caller mid-call can't be taken over. `_process_callback_reassignments` only escalates/releases, never auto-reassigns.
- Proof = **Assignment Log tab** (reuses `lead_stage_events` event_type 'assigned'/'reassigned', migration 099), not per-lead timeline.

## Chat escalation (ai_reply.py / chat_handovers.py)
- **Trigger-only:** A=fallback, B=AI/Groq error, C=user asked for human (always fires), D=repeated question, F=AI said team will follow up. `_TRIGGER_PRIORITY = ["C","B","A","D","F"]`. **Trigger E (score-hot) was DROPPED** — no score/segment chat escalation.
- **No auto-assign:** handovers land UNASSIGNED in a shared pool visible to admin + every telecaller (caller scope = `assigned_to == me OR needs_human_attention`). `needs_human_attention` set on escalation, cleared on resolve. Booking `notify_telecaller` path is separate, untouched.

## Operator console (separate from /dashboard)
- Multi-tenant management at `/operator/login`. `system_admins` table (migration 042), dedicated account `developer@airaai.com` (no tenant). `tenants.enabled_features text[]` + `status` (migration 041) drive sidebar feature-gating (whatsapp vs telecalling items) and suspension 403s (`get_tenant_id`/`get_tenant_and_role` check `status=='suspended'`). System health card polls `GET /api/v1/operator/system-health` (psutil) every 60s.

## PWA support
- Frontend PWA is intentionally conservative: `components/PwaRegistrar.tsx` registers `/sw.js` only in production, `app/manifest.ts` starts installed users at `/dashboard`, and `app/offline/page.tsx` is the navigation fallback.
- `public/sw.js` must not cache `/api/*`, `/auth/*`, mutations, tenant data, lead data, conversations, or dashboard JSON. Keep authenticated/product data network-first; only cache install icons, offline fallback, and static build assets.
- Do not enable service worker registration in development unless actively debugging cache behavior; stale dev caches make frontend work confusing.
- Mobile dashboard UX is intentionally separate from desktop: `ClientLayout.tsx` hides `Sidebar` below `md`, adds `MobileDashboardNav`, and gives content bottom padding for the fixed nav. Preserve this split when changing dashboard navigation.
- Inner dashboard pages follow the same split: keep desktop tables/panels for `md+`, but use mobile-specific cards/flows for phone screens. `components/MobileRecord.tsx` is the shared pattern for dense mobile records; conversations intentionally hide the inbox rail on phone and switch list -> chat with a back action.

## Auth login
- `/login` deliberately uses a static right-panel background and native uncontrolled email/password fields. Do not reintroduce the animated canvas around the credential form or controlled password state unless you verify desktop Chrome focus/typing behavior; it previously caused flicker and blocked password entry.

## Telecalling provider split
- `telecalling_config.calling_provider` is the tenant-level switch: `telecmi` uses API click-to-call plus CDR/recording webhook; `sim_basic` creates a manual call log, opens `tel:`, and requires manual wrap-up. Keep lead queue/profile/notes/callbacks/analytics shared; only call execution and evidence source differ.
- On mobile view, SIM Basic calls bypass the 3-second dial countdown and launch the native phone dialer synchronously (via the `openNativeDialer` utility in `sim-dialer.ts`) to avoid browser security policy blocks on delayed/asynchronous redirects.
- SIM Basic analytics truth: `call_logs.provider='sim_basic'` and `feedback_source='manual'`. Duration comes from caller-confirmed start/end time, notes from short manual summary. Do not promise PWA-native call recording or automatic SIM call-log access.
- **Mobile backgrounding trap (SIM Basic):** When `tel:` opens the native dialer, mobile browsers immediately suspend the PWA's JS engine. Any async code inside `.then()` (e.g., setting `activeCallCtx`, scheduling `primeSimWrapup`) will NOT execute until the user returns. Always set call state and schedule timers SYNCHRONOUSLY before the async API call. Use `keepalive: true` on `api.calls.initiate` to survive backgrounding. `handleWrapupSubmit` must lazily create the call log if `callLogId` is null (background request may have been aborted).
- **Wrap-up modal z-index:** The mobile wrap-up modal must use `z-[60]` (above bottom nav at `z-50`) and bottom-sheet layout (`items-end`, `rounded-t-3xl`, `safe-area-inset-bottom`) to avoid overlap with `MobileDashboardNav`.

## Web Push
- Web Push is permission-gated from the notification bell and stored in `push_subscriptions`. Backend delivery is best-effort via VAPID keys and must not block assignments if a subscription is stale or push config is missing.
- `GET /api/v1/push/public-key` is intentionally public (`push.public_router`); it returns only the VAPID public key. Subscription save/delete/status routes stay auth-gated. Frontend `syncPushSubscription()` must no-op when there is no Supabase session so anonymous pages do not spam 401s or redirect back to `/login`.
