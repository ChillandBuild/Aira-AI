# Escalation: WhatsApp Alerts + Live AI — Design

**Date:** 2026-07-19
**Status:** Approved, ready for implementation planning

Two related changes to what happens when the AI escalates a conversation:

- **Part 1** — notify the team on WhatsApp, not just the in-app bell.
- **Part 2** — stop pausing the AI, and make it answer appropriately while the
  customer waits for a human.

## Problem

When the AI escalates, `_trigger_chat_escalation` (`backend/app/services/ai_reply.py`)
does two unhelpful things:

1. It notifies the team only via `notify_pool("handover_new", …)` — in-app bell
   and web push. If nobody is looking at the dashboard, the escalation sits.
2. It sets `ai_enabled = False`, which kills the AI for that lead entirely
   (`ai_reply.py:1048` skips reply generation). The customer who just asked for
   a human then gets **total silence** until a person shows up.

A WhatsApp path already exists for a *different* event — a lead changing segment
(`whatsapp_notify.py`). Part 1 extends that machinery to escalations.

### Pre-existing defect found while scoping

`InboxConfigPanel.tsx` renders a "Segments to Escalate" control that writes
`inbox_config.segments`, but **nothing reads it**:

- `should_escalate_to_inbox()` (`assignment.py:517`) gates on master switch,
  trigger list, and channel only — its docstring says "no segment gate".
- `should_escalate_hot_lead()` (`assignment.py:532`) is the only reader of
  `config["segments"]`. It is imported at `ai_reply.py:20` and never called.
- `.agents/context/subsystem-notes.md:79` confirms trigger E (score-hot) was
  dropped deliberately.

The control is dead UI. This design removes it (D4).

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Separate `whatsapp_escalation_notifications` config block | Escalation is a different event with different template variables (reason, not segment). One shared template would fit neither well. |
| D2 | Delayed send with cancel-if-claimed | Avoids WhatsApp spam for handovers the team already caught in-app. Mirrors the existing alert's re-verify-before-send behaviour. |
| D3 | Escalation alerts gated by lead segment, own picker | Prevents a cold tyre-kicker paging the team at 2am. |
| D4 | Remove the dead "Segments to Escalate" control | It has never worked. Wiring it up instead would silently start suppressing handovers the team currently receives. |
| D5 | Reuse the `pending_whatsapp_alerts` queue, not a new table | One scheduler job, one retry path, one incident-logging path. |
| D6 | **AI never pauses on escalation** — drop `ai_enabled: False` | An escalated customer should never hit a wall of silence. Explicit product decision (see Accepted risk). |
| D7 | Drop `ai_enabled: True` from `resolve_handover` too | Once escalation stops pausing, that line no longer restores anything — it would clobber a manual admin mute. `ai_enabled` becomes a purely manual control that escalation never touches. |
| D8 | New tenant-level business-hours config | No such config exists. `quiet_hours` means "don't push staff overnight" — a different concept that must not be overloaded. |
| D9 | Escalation state + office status injected into the AI prompt | The AI should answer *situationally* ("contacted shortly" vs "call tomorrow") rather than replaying one canned string. |
| D10 | No holding-reply cooldown, no silence rule | The AI keeps behaving normally throughout the handover. Explicit product decision. |

### Accepted risk (D6 + D10)

With the AI live for the whole handover, it **can reply alongside a human agent**
— customer asks a question, telecaller types an answer, AI posts its own reply on
top. This was raised explicitly and accepted.

Mitigation available today: the per-lead `ai_enabled` toggle still exists as a
manual escape hatch, and after D7 it is no longer overwritten by the escalation
lifecycle — so muting a lead now actually sticks.

---

# Part 1 — WhatsApp escalation alerts

## Data model

### `notification_config` — no migration needed

`notification_config` is **not** a table or a set of columns. It is a single JSON
blob stored in `app_settings` under `key='notification_config'`, deep-merged with
`_NOTIFICATION_CONFIG_DEFAULT` in `services/notification_config.py`.

Adding the new block therefore requires only two code changes:

1. A new entry in `_NOTIFICATION_CONFIG_DEFAULT`:

```python
"whatsapp_escalation_notifications": {
    "enabled": False,
    "recipient_phones": [],
    "template_id": None,
    "target_segments": ["A"],
    "delay_minutes": 3,
},
```

2. A matching line in the `merged` seed dict and in the deep-merge body of
   `get_notification_config`, following the exact pattern used by
   `whatsapp_notifications`. Miss the merge line and the block silently reverts
   to defaults on every read.

`enabled: False` means no tenant starts sending without opting in and choosing an
approved template. Existing stored blobs lack the key entirely, and the merge
supplies the default — so no backfill is required.

### `pending_whatsapp_alerts` — the only migration

Migration `142_escalation_whatsapp_alerts.sql`. Existing schema (from `131`):
`id, tenant_id, lead_id, from_segment, to_segment NOT NULL, send_at, status,
created_at`, with indexes on `(status, send_at)` and `(lead_id, status)`.

| Column | Type | Notes |
|---|---|---|
| `alert_type` | `text not null default 'segment_change'` | `'segment_change'` or `'escalation'`. The default backfills existing rows correctly. |
| `handover_id` | `uuid null` | FK to `chat_handovers(id)` `on delete cascade`. |
| `assigned_to_at_queue` | `uuid null` | Snapshot needed for cancel-if-claimed. |
| `escalation_reason` | `text null` | Trigger reason, used as a template variable. |
| `to_segment` | relax to nullable | Escalation rows have no segment transition. |

**Why `assigned_to_at_queue` is required.** `_trigger_chat_escalation` seeds the
handover's `assigned_to` with the lead's existing owner, so it is often non-null
at creation. `PATCH /{handover_id}/assign` sets `assigned_to` and leaves `status`
as `pending`; only `/resolve` changes status. So "claimed" cannot be detected as
"`assigned_to` is no longer null" — it must be compared against the queue-time value.

## Backend

### `services/whatsapp_notify.py`

**`queue_escalation_whatsapp_alert(db, tenant_id, lead_id, handover_id, reason, assigned_to)`**

Returns silently (never raises) unless all hold:
- `whatsapp_escalation_notifications.enabled`
- `template_id` set and `recipient_phones` non-empty
- the lead's current `segment` is in `target_segments`

Then inserts a row with `alert_type='escalation'`,
`assigned_to_at_queue=assigned_to`, `send_at = now() + delay_minutes`.

No cooldown check needed: `_trigger_chat_escalation` returns early when an open
handover already exists (`ai_reply.py:774`), so there is exactly one alert per
handover by construction.

**`_build_escalation_components(template, lead, reason)`**

Mirrors `_build_components`, mapping ordinal `{{n}}` placeholders to:

1. lead name (fallback `"Lead"`)
2. lead phone
3. escalation reason, truncated to 120 chars
4. `https://aira.ai/dashboard/conversations?lead_id=<id>`

Returns `None` when the template has no variables.

**`process_due_whatsapp_alerts()`**

Branches on `alert_type`; the segment-change path is unchanged. The escalation
path marks the row `processing`, then **cancels** if any of:

- handover row missing
- `handover.status != 'pending'` (resolved)
- `handover.assigned_to != assigned_to_at_queue` (claimed)
- config now disabled, or `template_id` / `recipient_phones` now empty

and marks **failed** (with an incident) if the template is missing, no longer
`APPROVED`, or has no variables. Otherwise dispatches via the existing
`_dispatch_alerts` and marks `sent`.

### `routes/notifications.py`

Extend schema and validation: phones match `^\+[1-9]\d{6,14}$`, segments ⊆
`{A,B,C,D}`, `delay_minutes` 0–1440, `template_id` nullable UUID.

## Frontend

- `lib/api.ts` — extend the `NotificationConfig` type.
- `NotificationConfigPanel.tsx` — new **WhatsApp escalation alerts** card below
  the existing WhatsApp card, mirroring it structurally: master toggle, segment
  pills, phone list with E.164 validation, approved-template picker with preview,
  delay input. Reuse `Toggle`, `SEGMENT_LABELS`, `SEGMENT_STYLES`, `E164_REGEX`.
  Delay helper text must state the different semantics: "How long to wait before
  alerting. If a teammate claims or resolves the handover first, the message is
  not sent."
- `InboxConfigPanel.tsx` — delete the Segments block (lines 178–194) and remove
  `segments` from the type, `DEFAULT`, and the PATCH payload. Leave the DB column.

---

# Part 2 — AI stays live during escalation

## Behaviour change

In `_trigger_chat_escalation`, the lead update drops `ai_enabled`:

```python
db.table("leads").update({
    "needs_human_attention": True,
    "escalation_reason": reason,
}).eq("id", lead_id).execute()
```

In `resolve_handover` (`routes/chat_handovers.py:136-140`), likewise drop
`"ai_enabled": True`, keeping `needs_human_attention: False` and
`escalation_reason: None`.

Net effect: the AI answers every inbound message for the whole handover
lifetime, exactly as it would for a non-escalated lead — but with the added
context below.

## Business hours config

Stored as its own `app_settings` row under `key='business_hours'`, following the
same pattern as `telecalling_config` and `inbox_config`. **No migration needed.**
Default, supplied by the service layer when the row is absent:

```json
{
  "enabled": true,
  "timezone": "Asia/Kolkata",
  "open_time": "09:00",
  "close_time": "19:00",
  "working_days": [1, 2, 3, 4, 5, 6]
}
```

`working_days` uses ISO weekday numbering (Mon=1 … Sun=7).

New helper `services/business_hours.py`:

- `get_business_hours(tenant_id, db) -> dict`
- `is_within_business_hours(cfg, now=None) -> bool` — false when
  `enabled` is false, when today is not a working day, or when the local time is
  outside `[open_time, close_time)`. Uses `zoneinfo` for the tenant timezone.
- `describe_hours(cfg) -> str` — human string for the prompt, e.g.
  `"Monday to Saturday, 9:00 AM to 7:00 PM IST"`.
- `next_open_description(cfg, now=None) -> str` — e.g. `"tomorrow morning"`,
  `"Monday morning"`.

## Prompt injection

In `generate_ai_reply`, when the lead has an open handover (`needs_human_attention`
is true), append an escalation block to the system prompt before generation:

```
ESCALATION CONTEXT
This customer has already been escalated to the human team. A team member has
been notified and will follow up. The office is currently {OPEN|CLOSED}.
Our office hours are {describe_hours}.

If the customer asks to speak to a person, asks about their request, or says
nobody has contacted them yet:
- If the office is OPEN: reassure them that the team has their request and will
  contact them shortly.
- If the office is CLOSED: tell them the team will call them {next_open_description},
  and state the office hours.

Rules:
- Never promise a specific time, a named person, or a callback within N minutes.
- Never claim someone has already called or messaged them.
- Never say the request was resolved.
- Otherwise keep answering their questions normally and helpfully.
```

Keeping this as prompt context rather than a canned string is what makes the
reply situational (D9) and keeps it in the customer's own language, which the
existing pipeline already handles.

## Interaction with escalation triggers

The new holding replies will contain phrases like "our team will contact you",
which **will** match `_AI_ESCALATION_RE` and raise trigger F on every turn. This
is harmless: `_trigger_chat_escalation` returns early when an open handover
exists, so no duplicate handover and no duplicate WhatsApp alert are created.
No change needed — but it must not be "fixed" by someone later assuming the
repeated trigger is a bug.

## Frontend

New **Business Hours** card in settings: enabled toggle, timezone select,
open/close time inputs, working-day pills. Follows the existing settings-card
pattern (`card rounded-3xl`, `Toggle`, violet `primary` for active state).

---

## Error handling

All notification failures reuse `_log_incident` with
`type='whatsapp_alert_failed'`. New `reason` values:
`escalation_queue_failed`, `escalation_template_not_found_or_not_approved`.

Every new path is wrapped so escalation itself — handover creation,
`needs_human_attention`, `notify_pool` — cannot be broken by a notification or
business-hours fault. If `business_hours` lookup fails, the AI falls back to
replying without the escalation block rather than not replying at all.

## Testing

`backend/tests/test_escalation_whatsapp.py`:

1. queue is a no-op when `enabled` is false
2. queue is a no-op when the lead's segment is not in `target_segments`
3. queue is a no-op with no template or no recipient phones
4. happy path — row queued with correct `send_at`, `alert_type`, snapshot
5. cancelled when the handover is resolved before `send_at`
6. cancelled when `assigned_to` changes before `send_at`
7. sent when still pending and unclaimed
8. escalation still creates the handover when the WhatsApp send raises

`backend/tests/test_business_hours.py`:

9. inside window on a working day → open
10. outside window → closed
11. non-working day → closed
12. `enabled: false` → always closed
13. timezone respected (UTC instant that is in-hours IST)
14. midnight-spanning window handled

`backend/tests/test_escalation_ai_live.py`:

15. escalation no longer sets `ai_enabled = False`
16. `resolve_handover` no longer sets `ai_enabled = True`
17. AI still generates a reply for a lead with an open handover
18. escalation prompt block present and marked OPEN in-hours
19. escalation prompt block present and marked CLOSED out-of-hours
20. no escalation block for a lead without an open handover
21. second escalation attempt creates no duplicate handover (trigger-F loop)

Existing `test_whatsapp_notifications.py` and `test_notify_service.py` must pass
unchanged — the regression guard for the segment-change path.

## Out of scope

- Changing which conversations escalate (triggers and channels stay as they are)
- WhatsApp alerts for any other notification event
- Per-telecaller routing of escalation alerts (recipients are a flat tenant list)
- Any mechanism to stop the AI replying over a live human agent (see Accepted risk)
