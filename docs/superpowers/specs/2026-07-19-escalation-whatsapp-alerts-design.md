# Escalation WhatsApp Alerts — Design

**Date:** 2026-07-19
**Status:** Approved, ready for implementation planning

## Problem

When the AI escalates a conversation to a human, the team is notified only through
the in-app bell and web push (`notify_pool("handover_new", …)` in
`_trigger_chat_escalation`, `backend/app/services/ai_reply.py`). Nobody gets a
WhatsApp message. Escalations therefore sit unclaimed whenever the team is not
looking at the dashboard.

A WhatsApp path already exists for a *different* event — a lead changing segment
(`whatsapp_notify.py`). This design extends that same machinery to escalations.

### Pre-existing defect found while scoping

`InboxConfigPanel.tsx` renders a "Segments to Escalate" control that writes
`inbox_config.segments`, but **nothing reads it**:

- `should_escalate_to_inbox()` (`assignment.py:517`) gates on master switch,
  trigger list, and channel only — its docstring says "no segment gate".
- `should_escalate_hot_lead()` (`assignment.py:532`) is the only reader of
  `config["segments"]`. It is imported at `ai_reply.py:20` and never called.
- `.agents/context/subsystem-notes.md:79` confirms trigger E (score-hot) was
  dropped deliberately.

The control is dead UI. This design removes it (decision D4 below).

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Separate `whatsapp_escalation_notifications` config block, not an extension of the existing one | Escalation is a different event with different template variables (reason, not segment). One shared template would fit neither well. |
| D2 | Delayed send with cancel-if-claimed | Avoids WhatsApp spam for handovers the team already caught in-app. Mirrors the existing alert's re-verify-before-send behaviour. |
| D3 | Escalation alerts gated by lead segment, with their own picker | Prevents a cold tyre-kicker paging the team at 2am. |
| D4 | Remove the dead "Segments to Escalate" control | It has never worked. Wiring it up instead would silently start suppressing handovers the team currently receives. |
| D5 | Reuse the `pending_whatsapp_alerts` queue rather than add a second table | One scheduler job, one retry path, one incident-logging path. |

## Data model

Migration `142_escalation_whatsapp_alerts.sql`.

### `notification_config`

New column `whatsapp_escalation_notifications jsonb not null default`:

```json
{
  "enabled": false,
  "target_segments": ["A"],
  "recipient_phones": [],
  "template_id": null,
  "delay_minutes": 3
}
```

Defaulting `enabled` to `false` means no tenant starts sending messages without
opting in and choosing an approved template.

### `pending_whatsapp_alerts`

| Column | Type | Notes |
|---|---|---|
| `alert_type` | `text not null default 'segment_change'` | `'segment_change'` or `'escalation'`. The default backfills existing rows correctly. |
| `handover_id` | `uuid null` | FK to `chat_handovers(id)` `on delete cascade`. |
| `assigned_to_at_queue` | `uuid null` | Snapshot needed for cancel-if-claimed (see below). |
| `escalation_reason` | `text null` | Trigger reason, used as a template variable. |
| `to_segment` | relax to nullable | Escalation rows have no segment transition. |

**Why `assigned_to_at_queue` is required.** `_trigger_chat_escalation` seeds the
handover's `assigned_to` with the lead's existing owner, so it is often non-null
at creation. `PATCH /{handover_id}/assign` sets `assigned_to` and leaves `status`
as `pending`; only `/resolve` changes status. So "claimed" cannot be detected as
"`assigned_to` is no longer null" — it must be compared against the value at
queue time.

## Backend

### `services/whatsapp_notify.py`

**`queue_escalation_whatsapp_alert(db, tenant_id, lead_id, handover_id, reason, assigned_to)`**

Returns silently (never raises) unless all hold:
- `whatsapp_escalation_notifications.enabled`
- `template_id` set and `recipient_phones` non-empty
- the lead's current `segment` is in `target_segments`

Then inserts a `pending_whatsapp_alerts` row with `alert_type='escalation'`,
`assigned_to_at_queue=assigned_to`, and `send_at = now() + delay_minutes`.

No cooldown check is needed. `_trigger_chat_escalation` returns early when an
open handover already exists for the lead (`ai_reply.py:774`), so there is
exactly one alert per handover by construction.

**`_build_escalation_components(template, lead, reason)`**

Mirrors `_build_components`, mapping ordinal `{{n}}` placeholders to:

1. lead name (fallback `"Lead"`)
2. lead phone
3. escalation reason, truncated to 120 chars
4. `https://aira.ai/dashboard/conversations?lead_id=<id>`

Returns `None` when the template has no variables — nothing safe to send.

**`process_due_whatsapp_alerts()`**

Branches on `alert_type`. The existing segment-change path is unchanged. The
escalation path marks the row `processing`, then **cancels** if any of:

- handover row missing
- `handover.status != 'pending'` (resolved)
- `handover.assigned_to != assigned_to_at_queue` (claimed)
- `whatsapp_escalation_notifications.enabled` now false
- `template_id` or `recipient_phones` now empty

and marks it **failed** (with an incident) if the template is missing or no
longer `APPROVED`, or if the template has no variables. Otherwise it dispatches
via the existing `_dispatch_alerts` and marks `sent`.

### `services/ai_reply.py`

In `_trigger_chat_escalation`, after the existing `notify_pool` block, call
`queue_escalation_whatsapp_alert(...)` inside its own `try/except`. A WhatsApp
failure must never prevent a handover from being created.

Also remove the unused `should_escalate_hot_lead` import (line 20).

### `routes/notifications.py`

Extend the config schema and validation:
- `recipient_phones` — each must match `^\+[1-9]\d{6,14}$`
- `target_segments` — subset of `{A, B, C, D}`
- `delay_minutes` — integer 0–1440
- `template_id` — nullable UUID

## Frontend

### `lib/api.ts`
Extend the `NotificationConfig` type with the new block.

### `NotificationConfigPanel.tsx`
Add a **WhatsApp escalation alerts** card directly below the existing WhatsApp
lead notifications card, structurally mirroring it: master toggle, segment
pills, recipient phone list with add/remove and E.164 validation, approved
template picker with body preview, and a delay input. Reuse the existing
`Toggle`, `SEGMENT_LABELS`, `SEGMENT_STYLES`, and `E164_REGEX`.

Copy for the delay helper text must reflect the different semantics from the
segment alert: "How long to wait before alerting. If a teammate claims or
resolves the handover first, the message is not sent."

### `InboxConfigPanel.tsx`
Delete the Segments block (lines 178–194) and remove `segments` from the
`InboxConfig` type, `DEFAULT`, and the PATCH payload. Leave the DB column in
place so nothing breaks.

## Error handling

All failures reuse `_log_incident` with `type='whatsapp_alert_failed'` so they
surface on the dashboard. New `reason` values: `escalation_queue_failed`,
`escalation_template_not_found_or_not_approved`, `meta_send_failed` (existing).

Every new code path is wrapped so that escalation itself — handover creation,
`needs_human_attention`, `notify_pool` — cannot be broken by a notification
fault.

## Testing

`backend/tests/test_escalation_whatsapp.py`:

1. queue is a no-op when `enabled` is false
2. queue is a no-op when the lead's segment is not in `target_segments`
3. queue is a no-op with no template or no recipient phones
4. happy path — row queued with correct `send_at`, `alert_type`, and snapshot
5. cancelled when the handover is resolved before `send_at`
6. cancelled when `assigned_to` changes before `send_at`
7. sent when the handover is still pending and unclaimed
8. escalation still creates the handover when the WhatsApp send raises

Existing `test_whatsapp_notifications.py` must continue to pass unchanged —
that is the regression guard for the segment-change path.

## Out of scope

- Changing which conversations escalate (triggers and channels stay as they are)
- WhatsApp alerts for any other notification event
- Per-telecaller routing of escalation alerts (recipients are a flat tenant-level list)
