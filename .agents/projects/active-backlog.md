# Aira AI — Projects & Active Backlog

## Known Technical Debt
- **Orphaned Database Tables**: Bot Flow Builder tables (`automations`, `automation_flow_runs`, `bot_flows`) still exist in the Supabase schema, although the backend and frontend engine code has been deleted.
- **Stale Wiki References**: ✅ Cleared 2026-06-24. The graph carried 183 ghost nodes for deleted bot-flow modules because `graphify update` refuses to shrink the graph without `--force`. Ran `graphify update . --force` (4285 nodes, ghosts pruned) + `make wiki` (182 articles). `make wiki-refresh` now uses `--force` permanently, so deletions self-prune going forward.

## Active Backlog
- **QA audit — 20 fixes parked on branches** (`qa/critical` 3, `qa/high` 9, `qa/medium` 4, `qa/low` 2). The full 58-finding audit (2026-06-22) was reverted from main after a fix broke lead creation (the `opt_in_source` CHECK didn't allow the added `"whatsapp"` value); 12 safe fixes + the env-var leak fix were re-applied. Safety tag `pre-revert-backup` preserves the old HEAD. **Merge one branch at a time, test after each** ([[feedback_qa_revert]]).
- **Number spam / blocking — open product problem** (boss-raised 2026-04-21, unsolved). WhatsApp API numbers get Meta-blocked after ~10–20 reports; manual caller numbers get Truecaller/carrier spam-flagged. Naive "swap dead number" isn't seamless. Treat number-health monitoring + multi-number pooling + branded caller-ID (Truecaller for Business, Exotel/Knowlarity) as a first-class subsystem, not an afterthought — it gates the core lead-gen value prop.
- **Shared UI primitives** — no Button/Input/Badge/Tabs components yet; ~50+ buttons / ~20 inputs / ~8 tab groups are inline. Next planned design step.
- **Retire `lead_scorer.py`** (legacy two-pass scorer) — still called only on the AI-disabled branch; route that branch through `compute_score` instead. Low priority.
- **Render free → Starter ($7/mo)** — fixes cold-start tail and makes in-process APScheduler reliable (free tier sleeps after 15min → jobs skip). User action.
- **`feature/scoring-booking-refactor` branch** — unmerged; contains booking state-machine removal + `[COLLECT_DONE]` pattern (migration 072 already applied). Dynamic pricing is already on main; the state-machine removal is NOT.

---

## Recently Completed Features
- **Security & Multi-Tenancy**: RLS launch blocker (Migration 114) + performance checks (Migration 115).
- **Shift Time Overrides**: Multi-tenant shift hour schedules per caller (Migration 112) + ShiftTimeline ranges.
- **Call Scripts Cockpit integration**: Segment-based routing, branch outcomes, and scripts cockpit panel (Migration 111).
- **Contact Recycling Engine**: Automatic APScheduler recycling job to re-queue unreachable voice leads (Migration 111).

## Tooling Follow-ups
- **Local wiki refresh toolchain on Windows**: `graphify-out/` is now ignored/local-only, but this machine currently lacks `make` and `graphify` on PATH, so `/aira-wiki` cannot rebuild the wiki after a fresh clone/pull. Install/expose graphify + make, or add a Windows-friendly script target.

## Session Follow-ups
- **SIM Basic rollout checklist**: apply migration `120_calling_provider_and_push.sql`, configure `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY`/`VAPID_SUBJECT`, and make telecaller invite fields conditional: TeleCMI requires agent id/password; SIM Basic should ask only name/email/password/mobile plus optional SIM label/shift/target.
