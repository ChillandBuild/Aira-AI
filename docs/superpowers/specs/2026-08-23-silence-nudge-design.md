# Silence Nudge — design

**Date:** 2026-08-23
**Status:** approved design, not yet implemented

A short contextual WhatsApp follow-up sent when a lead goes quiet minutes after a
live AI reply. UI label: **"Auto follow-up when a lead goes quiet."** Internal
name: `silence_nudge`.

---

## 1. Problem

A lead asks a question, the AI answers well, and the lead goes silent. Today
nothing happens for at least an hour. The existing re-engagement engine cannot
cover this case for three independent reasons:

1. **Granularity.** `reengagement_steps.delay_hours` is a whole-hour integer with
   a 1-hour floor enforced in both the UI and the service.
2. **Anchor.** The `inbound` step measures from `leads.last_inbound_at` — the
   lead's last message. The required anchor is *our* last outbound. At a 5-minute
   delay these differ enough to matter: an inbound anchor can fire while the AI
   is still composing its reply to that same message.
3. **Recurrence.** `_already_processed_lead_ids()` checks `reengagement_logs` for
   `(lead_id, step_id)` with **no time bound** — one send per lead, forever. A
   silence nudge must be able to fire again the next time the lead goes quiet.

Reason 3 is structural. Bolting a second, incompatible dedup model onto a working
377-line production service is the main thing this design avoids.

## 2. Decisions

| Question | Decision |
|---|---|
| Recurrence | Configurable. General form is a ladder of 1..N nudges per lull plus a rolling 24h cap. One-per-lull = ladder of 1; one-per-day = cap of 1. |
| What starts the clock | Live AI replies only. Broadcasts, templates, re-engagement sends, and expert-handoff messages never arm a timer. |
| Escalated chats | Suppress entirely while an open handover exists. Resumes when resolved. |
| Quiet hours | First rung always fires (the lead was demonstrably awake minutes ago). Later rungs landing inside the quiet window are **deferred to the window's end**, not dropped. |
| Paid intake sessions | Suppress. Intake sends its own holding messages; two uncoordinated automated messages to a paying customer read as broken. |
| Default state | **Off.** Every tenant opts in deliberately. |

Because the clock only ever starts on a live AI reply, the lead messaged us
minutes ago and the WhatsApp 24-hour session window is guaranteed open. The first
rung is always freeform-legal and needs no template fallback. Later rungs are
re-checked at send time (§7).

## 3. Non-goals

- WhatsApp only. Telegram / Instagram / Facebook do not arm timers in v1.
- No template fallback path. If the window has closed by the time a later rung
  fires, the nudge is dropped, not converted to a template.
- No per-segment targeting in v1. The daily cap is the volume control.
- The existing Campaign and Reply Follow-up features are untouched in behaviour.

## 4. Architecture

Three touch points. A timer row is written when an AI reply lands, cancelled when
anything else happens in the thread, and drained by a scheduler job.

### 4.1 Arm

Hook: [`ai_reply.py`](../../../backend/app/services/ai_reply.py) immediately after
the Step 4 outbound `messages` insert (~L1717).

Arm only when **all** hold:

- `channel == "whatsapp"`
- `is_ai` is `True`
- `sid is not None` (the send actually succeeded)
- `reply_source in ("ai", "knowledge")` — the only two values `generate_reply`
  produces (L1568, L1620); every other source belongs to a different subsystem
- `silence_nudge_enabled` is `"true"` for the tenant

Insert one `silence_nudge_jobs` row: `step_index = 0`,
`fire_at = now() + delays[0]`, `anchor_message_id` = the id of the row just
inserted, `status = 'pending'`.

**This entire block is wrapped in `try/except` and logged on failure.** A broken
nudge must never break a real reply. This matches the existing best-effort
pattern in the same function (the intake and escalation prompt blocks both log
and continue).

### 4.2 Cancel

Hook: [`webhook.py`](../../../backend/app/routes/webhook.py), where an inbound
message is recorded and `last_inbound_at` is updated.

Any new inbound message for a lead sets every `pending` job for that lead to
`cancelled`. A manual human outbound does the same — a telecaller who has just
replied does not want a robot following them 5 minutes later.

Ordering when the AI replies: cancel pending first, then arm the new rung. This
keeps at most one pending job per lead as an invariant.

### 4.3 Fire

New APScheduler job `silence-nudge`, `interval, minutes=1`, registered in
[`main.py`](../../../backend/app/main.py) alongside the existing eleven. Update
the startup log line to include it.

```
SELECT * FROM silence_nudge_jobs
WHERE status = 'pending' AND fire_at <= now()
ORDER BY fire_at
LIMIT 100
```

Per row: run the gate sequence (§6), send, mark `sent`, then arm the next rung if
the ladder has one. This is O(rows actually due) — typically zero — and
deliberately avoids the unbounded per-tick scan the `inbound` re-engagement
branch performs today ([`reengagement_service.py:147-153`](../../../backend/app/services/reengagement_service.py)).

## 5. Data model

Migration `183_silence_nudge.sql`.

```sql
CREATE TABLE IF NOT EXISTS silence_nudge_jobs (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL,
  lead_id           uuid NOT NULL,
  anchor_message_id uuid NOT NULL,
  step_index        int  NOT NULL DEFAULT 0,
  fire_at           timestamptz NOT NULL,
  status            text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','sent','cancelled','skipped','failed')),
  skip_reason       text,
  message_preview   text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  sent_at           timestamptz
);

CREATE INDEX idx_silence_nudge_due
  ON silence_nudge_jobs (fire_at) WHERE status = 'pending';
CREATE INDEX idx_silence_nudge_lead_pending
  ON silence_nudge_jobs (lead_id) WHERE status = 'pending';
CREATE INDEX idx_silence_nudge_cap
  ON silence_nudge_jobs (lead_id, sent_at) WHERE status = 'sent';
```

`skip_reason` exists for the same reason `follow_up_jobs` and
`reengagement_logs` have one: answering "why didn't this lead get nudged?" from a
single row instead of by inference.

**RLS.** The `ensure_rls` event trigger from
[migration 175](../../../backend/supabase/migrations/175_auto_enable_rls_new_tables.sql)
enables RLS automatically on `CREATE TABLE` in `public`. No policies are added,
which denies `anon` and `authenticated` outright. The backend reaches this table
through the service-role client only, and no route exposes it. **Do not "fix" the
missing policies by adding a permissive one** — the absence is the security
posture.

## 6. Gate sequence

Evaluated in this order at fire time. First failure wins and is written to
`skip_reason`.

| # | Gate | Outcome |
|---|---|---|
| 1 | `silence_nudge_enabled` still `"true"` for tenant | `pending` (resumes on re-enable) |
| 2 | `ai_auto_reply_enabled` still `"true"` | `pending` (resumes on re-enable) |
| 3 | Lead exists, `ai_enabled`, has `phone`, no `converted_at`, no `blocked_at` | `skipped` |
| 4 | Not `opted_out`, not `whatsapp_undeliverable` | `skipped` |
| 5 | No open `chat_handovers` row / `needs_human_attention` false | `skipped` |
| 6 | No active intake session — reuse the exact `intake_active` predicate `_build_base_prompt()` already computes (`ai_reply.py` ~L1280-1295), extracted to a helper rather than reimplemented | `skipped` |
| 7 | Rolling 24h `sent` count for lead < `silence_nudge_daily_cap` | `skipped` |
| 8 | Quiet hours (§8) | deferred, stays `pending` |
| 9 | Race re-check (§7) | `cancelled` |
| 10 | 24h WhatsApp window still open | `skipped` |

Gates 1 and 2 leave the row `pending` rather than consuming it, matching the
deliberate choice already documented in `_send_reengagement()`: a tenant toggling
the master switch off should have automation resume cleanly, not silently lose
queued work.

Gates 1–4 are shared with re-engagement and are extracted into a single helper
(§10).

## 7. Race handling

The failure that matters is the lead replying in the same second the timer fires.
Two independent defences:

1. **Cancel-on-inbound** (§4.2) removes the pending row the moment the reply
   lands.
2. **Re-check at send time** (gate 9): read the newest `messages` row for the
   lead. If its id is not `anchor_message_id`, the thread has moved on — mark the
   job `cancelled` and send nothing.

Defence 2 alone is sufficient for correctness; defence 1 keeps the queue clean
and avoids pointless LLM calls. Both are cheap because we are already holding the
job row.

## 8. Quiet hours

Window is per-tenant, IST, defaulting to 21:00–09:00. `growth.py` already carries
`IST_OFFSET`; reuse it rather than introducing a second timezone convention.

- `step_index == 0` → send regardless of the clock. The lead messaged minutes
  ago; they are awake.
- `step_index > 0` and `fire_at` falls inside the window → set
  `fire_at = next window end` and leave the row `pending`. It fires in the
  morning.

Deferral is unbounded by design in v1: gate 10 (window still open) and gate 7
(daily cap) between them prevent a stale nudge from arriving days later.

## 9. Message generation

New `generate_silence_nudge(lead_id, db=None)` in `ai_reply.py`, modelled on the
existing `generate_reengagement_message()` (L712-747) which already assembles the
last 6 thread messages via `_recent_thread()`.

Differences from the re-engagement prompt, which is tuned for a cold lead hours
or days later and is too heavy here:

- Hard cap **160 characters**, `max_tokens=60`. One line.
- No greeting — the conversation is already open.
- Reference what was just discussed; offer to continue.
- **No links, no prices, no new offers.** Commit `24494b3d` fixed a model
  inventing an app download URL, and `5716c840` fixed app-link and catalog leaks
  into non-intake replies. This prompt must not reopen either hole. It calls
  `_llm_complete` directly and never goes through `_build_base_prompt()`, so it
  inherits no catalog context — keep it that way.
- Fallback on LLM failure: `"Hey, can I help you with anything further?"`

Metering: call `meter(db, tenant_id, "ai_reply")` on success, consistent with
every other AI-authored outbound. Check `check_quota` before generating.

## 10. Shared guard extraction

New `backend/app/services/automation_guards.py`:

```python
def can_send_automated_outbound(lead: dict, tenant_id: str, *, db=None) -> str | None:
    """Return a skip reason, or None if sending is allowed."""
```

Covers gates 1–4. Called by both `silence_nudge.py` and
`_send_reengagement()`.

**This is the riskiest part of the work** — it modifies a working production path
to gain a shared abstraction. Mitigation is ordering: write characterisation
tests against the current `_send_reengagement()` gate behaviour *first*, extract
second, and confirm `test_reengagement_service.py` still passes.

If the extraction proves to disturb re-engagement behaviour in any way, the
fallback is to duplicate the four checks in `silence_nudge.py` and record the
duplication as tech debt in the backlog. A working re-engagement engine is worth
more than a DRY one.

## 11. Known trap: the `reply_source` check constraint

`messages.reply_source` carries a `CHECK` constraint. Its current value, set by
[migration 173](../../../backend/supabase/migrations/173_add_expert_handoff_reply_source.sql):

```sql
CHECK (reply_source IN ('knowledge','ai','automation','reengagement','expert_handoff'))
```

Inserting `'silence_nudge'` without extending this list raises `23514`. This has
already caused a live production incident: expert-handoff inserts violated the
constraint from migration 168 until 173, and because the exception propagated out
of `_send_and_log()`, `webhook.py` fell through to `generate_reply()` **and
answered the same inbound message twice**. Caught live 2026-08-11.

Migration 183 therefore extends the constraint as its **first** statement, before
the table is created:

```sql
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_reply_source_check;
ALTER TABLE messages ADD CONSTRAINT messages_reply_source_check
  CHECK (reply_source IN ('knowledge','ai','automation','reengagement','expert_handoff','silence_nudge'));
```

Note this list intentionally omits `'autopilot'`, which migration 173 already
dropped. Do not reinstate it.

## 12. Configuration

Per-tenant keys in `app_settings`, read via `get_setting()`.

| Key | Default | Meaning |
|---|---|---|
| `silence_nudge_enabled` | `"false"` | Master switch |
| `silence_nudge_delays` | `"5"` | Comma-separated minutes. `"5"` = one rung. `"5,60"` = two. |
| `silence_nudge_daily_cap` | `"1"` | Max `sent` nudges per lead per rolling 24h |
| `silence_nudge_quiet_start` | `"21:00"` | IST |
| `silence_nudge_quiet_end` | `"09:00"` | IST |

Validation on save: each delay is an integer 1–1440, at most 3 rungs, strictly
increasing; cap is 1–10. Reject rather than clamp, so a typo is visible.

UI: a new panel in the existing Automations tab
([`settings/page.tsx:662`](../../../frontend/app/dashboard/settings/page.tsx),
`?tab=automations`), following the save-state pattern already used by
`saveStates.automations_ai`.

## 13. Files

**New**
- `backend/supabase/migrations/183_silence_nudge.sql`
- `backend/app/services/silence_nudge.py` — arm, cancel, drain, gates
- `backend/app/services/automation_guards.py` — shared guard
- `backend/tests/test_silence_nudge.py`
- `backend/tests/test_automation_guards.py`

**Modified**
- `backend/app/services/ai_reply.py` — arm hook, `generate_silence_nudge()`
- `backend/app/routes/webhook.py` — cancel hook
- `backend/app/main.py` — scheduler job + startup log line
- `backend/app/services/reengagement_service.py` — use shared guard
- `frontend/app/dashboard/settings/page.tsx` — Automations panel
- `frontend/lib/api.ts` — settings keys if the tab uses a typed surface

## 14. Testing

**Guard extraction (write first, before touching re-engagement)**
- Each of gates 1–4 blocks a send and returns the expected reason
- `ai_auto_reply_enabled=false` leaves a re-engagement step unlogged, so it
  resumes on re-enable
- `test_reengagement_service.py` passes unchanged after extraction

**Arming**
- A live AI reply (`is_ai`, `sid`, `reply_source` in `ai`/`knowledge`) arms one job
- A broadcast, a template send, a re-engagement send, and an expert-handoff
  message each arm **nothing**
- A failed send (`sid is None`) arms nothing
- Tenant with `silence_nudge_enabled=false` arms nothing
- An exception inside the arm block does not prevent the reply being sent

**Cancelling**
- Inbound message cancels the pending job
- Manual human outbound cancels the pending job
- A second AI reply replaces rather than duplicates (at most one pending per lead)

**Firing**
- Due job with all gates passing sends and marks `sent`
- Race: inbound arrives after `fire_at` but before the drain → `cancelled`, no send
- Race: newest message id ≠ `anchor_message_id` → `cancelled`, no send
- Open handover → `skipped`
- Active intake session → `skipped`
- Daily cap reached → `skipped`
- Ladder: rung 0 sending arms rung 1; last rung arms nothing
- Quiet hours: rung 0 inside the window still sends; rung 1 inside the window
  defers and stays `pending`
- LLM failure falls back to the canned line rather than sending nothing

**Migration**
- A `messages` insert with `reply_source='silence_nudge'` succeeds after 183
- Existing reply sources still insert

## 15. Rollout

1. Apply migration 183.
2. Ship with `silence_nudge_enabled` defaulting to `"false"` — nothing changes for
   any existing tenant.
3. Enable for one pilot tenant with `delays="5"`, `daily_cap="1"`.
4. Watch `silence_nudge_jobs` for a week: `sent` vs `cancelled` ratio, and the
   `skip_reason` distribution. A high `cancelled` count is **healthy** — it means
   leads are replying inside the window and timers are dying as intended.
5. Widen only after reviewing what the AI actually wrote in `message_preview`.

## 16. Risks

| Risk | Mitigation |
|---|---|
| Guard extraction destabilises re-engagement | Characterisation tests first; documented fallback to duplication (§10) |
| `reply_source` constraint violation duplicates replies | Migration 183 extends the constraint first (§11) |
| LLM cost scales with conversation volume, not lead count | Off by default; daily cap defaults to 1; metered through the existing `ai_reply` counter |
| Nudge talks over a human or an intake flow | Gates 5 and 6; two-layer race defence |
| Model invents links or offers in the nudge | Explicit prompt ban; no `_build_base_prompt()`, so no catalog context (§9) |
| Twelfth scheduler job on a 1-minute tick | Query is indexed and bounded to 100 rows; typically returns zero |
