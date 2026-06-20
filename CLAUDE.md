# Aira AI — Claude Code Operating Manual

## Identity
Generic B2B SaaS — any business that does WhatsApp lead-gen + telecalling.
North Star: no single block/flag/outage stops a client's lead-gen for >5 minutes.
Solo dev. Terse. Code over prose. No trailing summaries. No explanations unless asked.

## Build State
| Component | Status |
|---|---|
| WhatsApp webhook (inbound/outbound) | ✅ Built — X-Hub-Signature-256 verified |
| AI reply pipeline (Knowledge base → Groq/Llama) | ✅ Built — uses Groq, NOT Gemini |
| Lead CRUD + CSV import | ✅ Built |
| Lead scoring (1–10, Groq/Llama) | ✅ Built |
| Segmentation A/B/C/D | ✅ Built |
| Callers CRUD (create/edit/delete) | ✅ Built |
| Manual dial via TeleCMI click-to-call | ✅ Built |
| AI coaching post-call (call_coach.py) | ✅ Built |
| Call scoring (call_scorer.py) | ✅ Built |
| Follow-up scheduler | ✅ Built |
| Knowledge base | ✅ Built |
| AI Tune (integrated into Knowledge page tab) | ✅ Built |
| Analytics page | ✅ Built — WhatsApp tab + Telecalling tab + funnel API |
| Instagram webhook | ✅ Built — tenant-scoped at /webhook/instagram/{tenant_id}, X-Hub-Signature-256 verified |
| Telegram webhook + Bot API | ✅ Built — secret_token verified, per-tenant |
| Facebook Messenger webhook | ✅ Built — tenant-scoped at /webhook/facebook/{tenant_id}, X-Hub-Signature-256 verified |
| Provider abstraction layer | ✅ Built — meta_cloud.py |
| phone_numbers table + pool management | ✅ Built — migration 009 + numbers.py |
| Numbers page (frontend) | ✅ Built — dashboard/numbers/ (outdated health sub-page deleted) |
| opt_in_source on leads + bulk-send gating | ✅ Built — migration 010 + upload.py |
| 7-step CSV upload | ✅ Built — upload.py + dashboard/upload/ |
| Multi-variable template personalization | ✅ Built — variable_mapping + extra_cols per lead |
| Scheduled broadcasts (APScheduler) | ✅ Built — scheduled_broadcasts table, migration 057 |
| Drip broadcasts | ✅ Built — schedule_type=drip, leads split over N days |
| Meta quality webhook handler | ✅ Built — webhook.py + failover.py |
| Auto-failover on RED quality | ✅ Built — handle_quality_red() wired in webhook.py |
| Outbound router (pool-aware) | ✅ Built — services/outbound_router.py |
| Incidents page (frontend) | ✅ Built — dashboard/incidents/ |
| lead_notes table + briefing modal | ✅ Built — migration 012 + lead_notes.py |
| Groq Whisper transcription + AI call summary | ✅ Built — call_summarizer.py |
| Notes page (/dashboard/notes) | ✅ Built |
| Message Templates page | ✅ Built — dashboard/templates/, routes/templates.py |
| Template submission to Meta API | ✅ Built — uses meta_waba_id |
| Template approval webhook | ✅ Built — POST /api/v1/templates/webhook-status |
| Manual template sync | ✅ Built — POST /api/v1/templates/{id}/sync |
| Template Quick Reply buttons | ✅ Built — up to 3 buttons |
| Knowledge base (pgvector RAG, Jina v3 embeddings @512-dim) | ✅ Built — services/knowledge_service.py + services/embeddings.py, migration 087, full-text fallback retained |
| Reply source badge (Knowledge Base / AI / Automation) | ✅ Built — messages.reply_source |
| Callback scheduler & reminders | ✅ Built — follow_up_jobs cadence=callback, in-app due reminders + 60s polling |
| Telecaller multi-tenancy + role-based access | ✅ Built — migration 025 |
| Hot lead alert system (score ≥7, 5-min escalation) | ⛔ Removed — superseded by trigger-only chat_handover escalation (no score/segment escalation) |
| Chat escalation (trigger-only, shared pool) | ✅ Built — fires on behavioral triggers A/B/C/D/F only (no segment/score, no auto-assign); handover lands UNASSIGNED in a shared pool visible to admin + every telecaller (caller scope = assigned OR needs_human_attention) |
| Lead assignment (manual + round-robin auto) | ✅ Built |
| Team management page | ✅ Built — dashboard/team/, routes/team.py |
| Onboarding flow | ✅ Built — dashboard/onboarding/, routes/onboarding.py |
| App settings page | ✅ Built — dashboard/settings/, routes/app_settings.py |
| Settings: webhook guides + copy buttons | ✅ Built — per-channel setup guide with correct URLs |
| Settings: Validate & Activate | ✅ Built — POST /api/v1/settings/activate (validates token + subscribes webhook) |
| Settings: webhook health check | ✅ Built — GET /api/v1/settings/webhook-health, health badge per channel |
| Settings: token expiry alerts | ✅ Built — APScheduler daily job, token_invalid incidents |
| CTWA referral auto-capture | ✅ Built — referral object parsed in webhook.py, linked to ad_campaign |
| Bookings table + booking flow state machine | ✅ Built — migrations 029–030, booking_flow.py, dynamic pricing via booking_types JSON in app_settings |
| Razorpay payment links | ✅ Built — services/payment_razorpay.py |
| Admin bookings dashboard | ✅ Built — dashboard/bookings/ |
| Multi-tenancy (app-layer) | ✅ Built — tenant_id on all tables |
| Role-based access | ✅ Built — owner and caller roles |
| Automations engine | ✅ Built — migration 055, routes/automations.py |
| Broadcast history + fail reason tracking | ✅ Built — migration 058_broadcast_fail_reason |
| Carousel templates (2–10 cards via Meta API) | ✅ Built — migration 060, dashboard/templates/carousel/ |
| WABA onboarding (self-service) | ✅ Built — WABA ID + Phone Number ID configurable in Settings UI |
| Score Engine v2 (composite scoring) | ✅ Built — arc + intent_delta + engagement_delta, migration 070, services/scoring_engine.py |
| Broadcast tags (colored, CSV export) | ✅ Built — migration 072_broadcast_tags, dashboard/tags/ |
| Per-broadcast lead scoring | ✅ Built — broadcast_lead_scores table, migration 076, context-aware arc |
| AI auto-reply toggle (per-bot) | ✅ Built — app_settings.ai_auto_reply, Settings UI |
| Broadcast negative reply + sentiment | ✅ Built — migrations 077–078, negative_reply + sentiment columns |
| Caller daily digest | ✅ Built — migration 065, call_evaluator digest job |
| Telecalling auto-assignment (state-based + sweep) | ✅ Built — services/assignment.py maybe_assign_lead funnel + sweep_unassigned_leads (2-min APScheduler); least-loaded round-robin gated by telecalling_config (enabled+segment+channel) |
| Assignment Log (proof/audit feed) | ✅ Built — routes/assignment_log.py, lead_stage_events 'assigned'/'reassigned' (migration 099), AdminView tab |
| Callback reassignment (away-caller resilience) | ✅ Built — main.py _process_callback_reassignments (1-min); migration 100 follow_up_job_id; auto_assign_lead event_type=reassigned + exclude_caller_ids |
| Telecaller cockpit (wrap-up, Call Next, live call) | ✅ Built — calls.py /pending-wrapups + /next-lead atomic claim; mandatory wrap-up modal; CallerView queue tabs by call_status |
| Admin telecalling monitoring | ✅ Built — Performance tab; /analytics/telecalling (connect rate, idle/bunking, speed-to-lead, quality); owner-gated caller-timeline/qa-queue/export |
| Call-status pipeline + DNC + attempt cap | ✅ Built — migration 102; outcomes drive leads.call_status (orthogonal to segment); DNC lead-level (do_not_call, +opted_out for do-not-contact); no_answer ≥ max_call_attempts → unreachable |
| Telecalling Upload (CSV + round-robin) | ✅ Built — routes/telecalling_upload.py; 2-step wizard (Upload → Confirm) at /dashboard/telecalling/upload; sidebar nav entry; round-robin auto-assign to least-loaded caller (excludes owner, includes null-status callers); dedup by phone; upload history with CSV export |
| Call Scripts (CRUD + cockpit) | ✅ Built — routes/call_scripts.py; segment-based resolution (segment script > default); branching steps with goto navigation; ScriptPanel in telecaller cockpit LeadDetailPanel |
| Contact Recycling | ✅ Built — services/contact_recycler.py; APScheduler 30-min job resets no_answer leads to "new" after configurable delay; IST calling hours + max retries; config in TelecallingConfigPanel |
| Shift Time Management | ✅ Built — migration 112; common or per-caller shift hours in telecalling_config + callers.shift_start_hour/shift_end_hour; LiveAgentStatus shift config UI (unified row: mode toggle + caller dropdown + hours + save) + amber outside-shift indicator; ShiftTimeline dynamic hour range (replaces hardcoded 9–19) |
| Admin Profile Page | ✅ Built — role-based profile: admin sees dark gradient identity card (name, crown badge, email, member-since, quote) + 6 quick-nav cards; telecallers see caller stats/attendance/coaching as before; uses useAuthRole() not stats-null check |
| Admin exclusion from telecaller metrics | ✅ Built — admin filtered from Agent Performance Leaderboard (backend analytics.py owner filter + frontend callerIds filter), excluded from LiveAgentStatus/ShiftTimeline, no attendance/shift/call tracking for admin |

## Hard Invariants — Never Break
1. Lead score always integer 1–10
2. Segments: A=Hot, B=Warm, C=Cold, D=Disqualified — labels immutable
3. WhatsApp 24h session window — approved templates only outside window
4. All segment lists: GET /api/v1/leads?segment=A&format=csv
5. Call recordings → Supabase Storage only, never local disk
6. Tenant isolation enforced at database level via RLS policies and at app layer via `get_tenant_and_role()`. All public tables have RLS enabled (migration 114 applied 2026-06-20). `anon` EXECUTE revoked on `is_system_admin`/`is_tenant_member`/`is_tenant_owner`.
7. Bulk-send endpoint rejects leads with null opt_in_source
8. **Template submission** always uses `meta_waba_id` (NOT `meta_phone_number_id`)
9. AI model is Groq `llama-3.3-70b-versatile` — do NOT add Gemini/OpenAI imports
10. WhatsApp webhook verifies X-Hub-Signature-256 before processing — returns 200 but drops invalid
11. `call_status` (telecalling pipeline) is orthogonal to A/B/C/D `segment` — call outcomes NEVER write segment; segment stays score/chat-owned
12. DNC is lead-level (`do_not_call`), NOT a `call_logs.outcome` value (that column is CHECK-constrained) — "do not contact" also sets `opted_out`; `opted_out`=WhatsApp/broadcast, `do_not_call`=voice
13. Admin (owner) is excluded from ALL telecaller metrics — no attendance, shift tracking, leaderboard rows, or call stats. `list_callers` filters owner by `user_id`; analytics `per_caller` filters owner; frontend leaderboard double-filters via `callerIds` set; profile page uses `useAuthRole()` role check (not stats-null)

## Stack
| Layer | Tech | Location |
|---|---|---|
| Backend | FastAPI, Python 3.11+, Pydantic v2 | backend/app/ |
| DB | Supabase (PostgreSQL + Realtime) | — |
| Frontend | Next.js 14 App Router, TypeScript, Tailwind | frontend/app/dashboard/ |
| AI (replies + scoring) | Groq — llama-3.3-70b-versatile | services/ai_reply.py, lead_scorer.py |
| WhatsApp | Meta Cloud API Direct | — |
| Voice | TeleCMI click-to-call + recording | services/telecmi_client.py |
| Payments | Razorpay Payment Links API | services/payment_razorpay.py |
| Scheduler | APScheduler (AsyncIO) — automations, broadcasts, token health | app/main.py |
| Cache | In-process prompt cache (60s TTL) | ai_reply.py:_prompt_cache |

## Provider Decisions (locked)
- WhatsApp: Meta Cloud API Direct
- Voice: TeleCMI
- AI (replies + scoring): Groq / llama-3.3-70b-versatile (NOT Gemini)
- Payments: Razorpay (Payment Links API — no SDK, direct httpx calls)

## Supabase Config (production)
- Project ID: `ayftynkgmfkaqmmnlmoc`
- Region: ap-northeast-1
- WABA ID in app_settings: `meta_waba_id = 994218516456571`
- Default tenant: `00000000-0000-0000-0000-000000000001`

## Render Config (production)
- Backend URL: `https://aira-ai-5tfr.onrender.com`
- WhatsApp webhook: `https://aira-ai-5tfr.onrender.com/webhook/whatsapp`
- Instagram webhook: `https://aira-ai-5tfr.onrender.com/webhook/instagram/{tenant_id}`
- Facebook webhook: `https://aira-ai-5tfr.onrender.com/webhook/facebook/{tenant_id}`
- Telegram webhook: `https://aira-ai-5tfr.onrender.com/webhook/telegram/{tenant_id}`

## APScheduler Jobs (all in main.py)
| Job | Interval | Purpose |
|---|---|---|
| _process_automation_waits | 5 min | Resume automation wait-step executions |
| _process_scheduled_broadcasts | 1 min | Fire pending scheduled_broadcasts rows |
| _check_token_health | 24 h | Validate Meta tokens, create token_invalid incidents |
| _sync_all_number_quality | 24 h | Sync Meta number quality rating & limits |
| _recycle_contacts | 30 min | Re-queue no_answer leads back to "new" (contact_recycler.recycle_all_tenants) |

## Task Router — Read This File Before Acting
| Task involves | Read first |
|---|---|
| WhatsApp, Meta API, provider layer, phone_numbers | backend/app/routes/webhook.py + services/meta_cloud.py + services/outbound_router.py |
| Telecalling, TeleCMI, call logs, notes, briefing modal | backend/app/routes/calls.py + services/telecmi_client.py + services/call_summarizer.py |
| Telecaller auto-assignment, round-robin, Assignment Log, callback reassignment | backend/app/services/assignment.py + routes/assignment_log.py + main.py (_sweep_unassigned_leads, _process_callback_reassignments) |
| Telecalling upload, call scripts, contact recycling | backend/app/routes/telecalling_upload.py + routes/call_scripts.py + services/contact_recycler.py |
| Leads, scoring, segments, opt-in, call_status pipeline | backend/app/routes/leads.py + services/scoring_engine.py (v2) + services/lead_scorer.py (legacy, AI-disabled path) |
| Number pool, failover, Numbers page, Incidents page | backend/app/routes/numbers.py + services/failover.py + routes/incidents.py |
| CSV upload, bulk send, scheduled/drip broadcasts | backend/app/routes/upload.py + services/broadcast_executor.py |
| Bookings, booking flow, Razorpay payments | backend/app/services/booking_flow.py + routes/bookings.py |
| WhatsApp templates, Meta template API | backend/app/routes/templates.py + services/meta_cloud.py |
| Settings, channel activation, token health | backend/app/routes/app_settings.py |

## Agent Dispatch
Spawn sub-agents automatically for tasks with 2+ independent work units.
Parallel pattern: schema + API route + frontend page → all 3 in one message.

## Settings Page — Fully Configurable
All channel credentials (WhatsApp/Instagram/Facebook/Telegram/TeleCMI/Groq) editable in Settings UI.
InboxConfigPanel: escalation on/off, per-trigger (A/B/C/D/F). Chat escalation is trigger-only — segment/score escalation and auto-assign-to-telecaller were removed; handovers are a shared pool any telecaller or admin can resolve. (Trigger E "score-hot" dropped.)
TelecallingConfigPanel: module on/off, auto-assign, per-segment assignment (A/B/C/D), channels, contact recycling (enable/delay/retries/hours), shift time management (common/individual mode + hours).
BookingConfigPanel: CRUD booking types (name + amount); stored as `booking_types` JSON in app_settings. Multiple types → WhatsApp type-selection step before collection flow. Zero types → default ₹500 flat pricing.

## Known Tech Debt
- lead_scorer.py (legacy two-pass) still called on AI-disabled branch — retire and route through scoring_engine.py

## Architecture Map (auto-derived)
Navigable module wiki at `graphify-out/wiki/index.md` — one article per module (callbacks, assignment, AI reply, webhooks, bot-flow, scoring, etc.) with source files + cross-module links. Plain markdown, no tooling needed to read. Pull it when tracing structure; CLAUDE.md remains the source of truth for invariants/decisions.
Regenerate after big changes: `/graphify . --update` then rebuild the wiki. Live query: `graphify query "<question>"`.

## Key File Locations
| File | Purpose |
|---|---|
| backend/app/main.py | FastAPI entry, route registration, all APScheduler jobs |
| backend/app/routes/webhook.py | WA webhook — inbound routing + signature verification |
| backend/app/routes/app_settings.py | Settings CRUD, activate channel, webhook health |
| backend/app/routes/templates.py | Template CRUD + Meta submission |
| backend/app/routes/bookings.py | Booking REST + Razorpay webhook |
| backend/app/routes/upload.py | CSV upload, bulk send, scheduled/drip broadcasts |
| backend/app/services/ai_reply.py | Knowledge base → Groq reply pipeline |
| backend/app/services/booking_flow.py | Booking state machine |
| backend/app/services/broadcast_executor.py | Executes a scheduled_broadcasts row |
| backend/app/services/failover.py | Quality RED/YELLOW handlers + auto-failover |
| backend/app/services/meta_webhook_verify.py | X-Hub-Signature-256 verification (shared by WA/IG/FB) |
| backend/app/services/meta_cloud.py | Meta Cloud API (text/media/template + carousel submission) |
| backend/app/services/lead_scorer.py | Groq scoring (1–10) |
| backend/app/services/telecmi_client.py | TeleCMI click-to-call |
| backend/app/db/supabase.py | Supabase client singleton |
| backend/app/routes/telecalling_upload.py | Telecalling CSV upload + round-robin assignment |
| backend/app/routes/call_scripts.py | Call scripts CRUD (segment-based, branching steps) |
| backend/app/services/contact_recycler.py | Contact recycling — re-queue no_answer leads |
| frontend/app/dashboard/profile/ProfileClient.tsx | Profile page — role-based: admin card (owner) vs caller stats (caller) |
| backend/supabase/migrations/ | All schema migrations 001–114 |
| frontend/app/dashboard/ | All dashboard pages |

## Migration Index (latest = 115)
| Migration | What |
|---|---|
| 051 | Telegram support — tg_user_id on leads |
| 052 | Instagram dynamic credentials in app_settings |
| 053 | Facebook support — fb_user_id on leads |
| 054 | Multichannel security fixes (unique indexes) |
| 055 | Automations engine table |
| 056 | Automations: score threshold + follow-up trigger types |
| 057 | scheduled_broadcasts table (APScheduler-based) |
| 058_broadcast_fail_reason | fail_reason column on broadcast_recipients |
| 058_incidents_token_health | incidents: tenant_id column + token_invalid/webhook_unhealthy types |
| 060 | carousel_cards JSONB column on message_templates |
| 061_message_delivery_error | message delivery error tracking |
| 061_number_health_engagement | phone_number_quality_history + outbound_no_reply_count + template variations |
| 062 | conversation_last_message RPC |
| 064 | leads.pinned_at |
| 065 | caller_digests — daily call evaluation digest per caller |
| 066 | whatsapp_insights_snapshots — WA analytics snapshot table |
| 067 | fix_conversation_leads_rpc — RPC correctness fix |
| 068 | toggle_lead_pin_rpc — RPC for pinning/unpinning leads |
| 069 | optimize_schema_indexes — index tuning for hot query paths |
| 070_drop_faqs_table | Drop legacy FAQs table |
| 070_score_engine_v2 | Score Engine v2 schema — arc_score columns, segment lock state |
| 071 | lead_stage_events: score_updated event type |
| 072_ad_campaigns_whatsapp_platform | ad_campaigns.platform filter for WhatsApp |
| 072_broadcast_tags | broadcast_tags table — colored tags on broadcasts/leads |
| 072_leads_collected_data | leads.collected_data JSONB — [COLLECT_DONE] output storage |
| 073 | Bot Flow Builder — extend automations in place (block types, node counters, flow_kind, messages↔node link, bump_automation_step_counter RPC) |
| 074 | automation_flow_runs — resumable run-state (replaces broken wait-resume; powers pause-on-reply) |
| 075 | bot_flow_phase2_steps — Phase 2 block types (http_api, random, interactive) |
| 076_botbiz_blocks | BotBiz block schema extensions |
| 076_broadcast_lead_scores | broadcast_lead_scores table — per-broadcast scoring context |
| 077 | broadcast_negative_reply — negative_reply flag on broadcast_recipients |
| 078 | broadcast_reply_sentiment — sentiment column on broadcast replies |
| 079 | fix_conversation_leads_outbound — RPC fix for outbound conversation leads |
| 080 | conversation_leads_filter_failed_broadcasts — exclude failed broadcast leads from conversation list |
| 081 | Drop WATI provider — tighten phone_numbers.provider check to 'meta_cloud' only, drop unused api_key column |
| 082 | Generic booking config — drop GPH hardcode, event_name + ref_prefix + amount_paise moved to per-tenant app_settings |
| 083 | Drop hot_lead_alerts table — score-threshold escalation now goes through chat_handovers gated by inbox_cfg.segments |
| 084 | Drop messages.twilio_message_sid (legacy Twilio column removal) |
| 085_opt_out_per_broadcast_and_tag | lead_tag_opt_outs table + broadcast_recipients.opted_out_at — per-broadcast & per-tag opt-out (NULL tag_id = all-tags sentinel) |
| 086_broadcast_lead_scores_finalized | broadcast_lead_scores.finalized_at — freeze a lead's per-broadcast score slate when the next broadcast sends |
| 086_lead_tag_opt_outs_lead_fk | lead_tag_opt_outs.lead_id FK → leads + orphan cleanup |
| 087_knowledge_rag | knowledge_chunks + vector(512) + HNSW; match/insert RPCs — pgvector RAG (Jina v3 embeddings @512-dim) replaces full-text KB injection |
| 088_knowledge_rag_fix | knowledge RAG RPC/index correctness fix |
| 088_reengagement_fixes | reengagement flow fixes |
| 089_security_hardening | RLS / security hardening pass |
| 090_knowledge_keyword_retrieval | keyword retrieval fallback for KB |
| 091_knowledge_campaign_scope | KB chunk scoping by campaign |
| 092_call_disposition | call_logs.disposition (CHECK: answered/no_answer/busy/switched_off/followup_required) |
| 093_template_performance | template performance metrics |
| 094_automated_reengagement | automated reengagement engine |
| 095_autopilot | autopilot tables |
| 096_leads_assigned_at | leads.assigned_at — assignment timestamp |
| 097_reengagement_fallback_template | reengagement fallback template |
| 098_app_notifications | app_notifications table |
| 099_lead_stage_events_assigned | lead_stage_events event_type 'assigned'/'reassigned' + index + telecalling_config.enabled backfill — powers Assignment Log |
| 100_add_follow_up_job_id_to_call_logs | call_logs.follow_up_job_id FK + index (callback resilience) |
| 101_drop_1d_1w_1m_cadences | drop legacy 1d/1w/1m follow-up cadences |
| 102_call_status_dnc | leads.call_status (new/in_progress/callback/converted/not_interested/dnc/unreachable) + do_not_call + CHECK + idx_leads_call_status — call-status pipeline orthogonal to A/B/C/D segment; DNC is lead-level (not a call outcome) |
| 103_reengagement_target_sources | reengagement_steps.target_sources jsonb — filter re-engagement by acquisition source (organic/meta_ads/csv/telegram/instagram/facebook); NULL = all |
| 111_telecalling_upload_scripts | call_scripts table (segment-based, steps jsonb, is_default, active) + telecalling_upload_batches table (upload history, assignment_snapshot jsonb) |
| 112_caller_shift_hours | callers.shift_start_hour + shift_end_hour (smallint, nullable) — per-caller shift time override |
| 113_security_and_new_tables_rls | Superseded by 114. Enables RLS on reengagement_steps, reengagement_logs, autopilot_runs, call_scripts, telecalling_upload_batches |
| 114_rls_launch_blocker | ✅ Applied 2026-06-20. Drops dead faqs/hot_lead_alerts tables; adds tenant_id to conversations + backfill; enables RLS+policies on all 9 remaining tables (conversations, bot_flows, meta_templates, reengagement_steps/logs, call_scripts, telecalling_upload_batches); deny-all on scheduler_runs; revokes anon EXECUTE on security definer helpers; sets search_path on 6 RPC functions |
| 115_perf_advisor_warnings | ✅ Applied 2026-06-20. 5x auth_rls_initplan (wrap auth.uid() in subselect); 12x multiple_permissive_policies (split FOR ALL into INSERT/UPDATE/DELETE); 1x duplicate_index (drop csl_tenant_idx) |

## Bot Flow Builder (replaces Automations UI)
Visual WhatsApp flow builder at /dashboard/automations (sidebar "Bot Flows"). Backend
extends the automations engine IN PLACE (no renames); "Bot Flow" is a UI name only.
- Engine: `services/automation_engine.py` — resumable step-pointer state machine driven
  by `automation_flow_runs` (`_drive_run`, `_next_step_id`, `resume_due_flow_runs` with
  stale-running reaper). `{{var}}` interpolation reads the run's variable bag.
- Pause-on-reply: `services/flow_runtime.resume_for_inbound` — intercepts inbound in all
  4 channels (webhook/telegram/instagram/facebook) BEFORE trigger fan-out + generate_reply;
  user_input/interactive/ai_agent nodes pause as `waiting_reply`. CAS-guarded against double-drive.
- Blocks: send_message/image/video/audio/file/location, cta_url, template, send_list,
  send_catalog, add_label, wait, condition, user_input, interactive (N-way button branch
  = button id), http_api (SSRF-guarded), random, ai_agent. Per-node analytics
  (sent/delivered/error) on automation_steps.
- ai_agent block: `services/agent_runtime.py` — a *contained* Groq (llama-3.3-70b, Invariant 10)
  agent that drives a multi-turn conversation toward declared outcomes; each turn returns
  STRICT validated JSON (LLM never gets free control), outcomes map to flow branch labels,
  agent state lives in the run's variable bag (survives pause/resume), hard tool-call caps.
- Frontend (`frontend/app/dashboard/automations/[id]/flow/`): the **node-graph map canvas
  (`Canvas.tsx` + `mapLayout.ts`) is the primary and only editor** — pan/zoom, click node →
  `BlockConfigDrawer`, hover toolbar (edit/delete), inline `+` insert on every edge, trigger
  node → right-side `TriggerCard` drawer. Left palette sidebar groups blocks Send/Logic/Tools.
  The old vertical stacked-card renderer (`FlowCanvas.tsx` + `BranchGroup.tsx`) is legacy/
  orphaned — still on disk, no longer wired into `FlowEditor`.
- Specs (historical brainstorming records — CLAUDE.md is the living source of truth):
  docs/superpowers/specs/2026-05-31-bot-flow-builder-design.md (Phase 1; its "vertical stack
  primary / map view later" UX is now INVERTED — map canvas is primary), -phase2-design.md
  (run-state, pause-on-reply, power blocks, residual risks), -agent-block-design.md (ai_agent).

## Response Style
- One sentence per progress update while working
- No trailing summaries
- No inline comments unless WHY is non-obvious
- No multi-line docstrings
- Mark TodoWrite tasks done immediately after finishing
- File refs: [file.py](path/file.py#L42)
- API errors: `{"error": "message", "code": "ERROR_CODE"}`
- All routes prefixed `/api/v1/`
- Pagination: `?page=1&limit=50`
