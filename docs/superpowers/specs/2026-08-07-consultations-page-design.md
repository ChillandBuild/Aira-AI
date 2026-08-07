# Consultations Page — Design

**Date:** 2026-08-07
**Status:** Approved, ready for implementation planning

A dedicated dashboard page where staff can see every Paid Expert Handoff
lead — split into leads who finished giving their details but haven't paid
yet, and leads who paid — and reply to them in place.

## Problem

Paid Expert Handoff (shipped earlier this session) writes to
`expert_handoff_sessions` but nothing reads it anywhere in the dashboard. A
lead can complete the whole flow and pay, and no human ever finds out except
by querying the database directly. An earlier fix-in-progress folded this
into the existing `chat_handovers` escalation pool, but that mixes paid
consultation leads into the AI-escalation inbox, which has a different
purpose and a different reply surface. This design replaces that approach
with a dedicated page instead.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Dedicated page (`/dashboard/consultations`), not folded into Conversations/`chat_handovers` | Keeps paid-consultation leads in their own list with their own status semantics (paid vs awaiting payment) instead of mixing them into the general AI-escalation pool, which answers a different question ("who needs a human right now") than this page does ("who's in the consultation funnel"). |
| D2 | Two buckets: **Awaiting Payment** (fully collected, payment link sent, not yet paid) and **Paid** | Matches exactly what the user asked for. Sessions still mid-collection (partial info) are not shown — not yet actionable, and showing half-finished rows adds noise without a clear next step for staff. |
| D3 | Reuse the existing `ChatThread` component for reply | It already does everything needed — message history, WhatsApp send, RBAC-gated reply box — via `lead: Lead`. No new messaging code. |
| D4 | Reuse `conversations.view`/`conversations.reply` permissions | Same access question ("can this person see/reply to leads") the Conversations page already answers. No new RBAC entries needed. |
| D5 | New top-level sidebar item "Consultations," always visible | Matches how Conversations itself is always shown regardless of whether a tenant has any messages yet. Empty state instead of hiding the entry. |
| D6 | Staff notification via `notify_pool` only, no `chat_handovers` row, no WhatsApp staff alert | A lightweight in-app bell ping ("check the Consultations page") is enough signal; creating a `chat_handovers` row would duplicate the lead into a second inbox with a second reply path (see D1). WhatsApp staff alerts add real complexity (queueing, config) for a notification class that isn't proven to need that urgency yet — can be added later if the bell alone isn't enough. |
| D7 | No new backend table — read existing `expert_handoff_sessions` | The data already exists and is already correct; this is purely a new read path plus one write-side notification call. |

## Backend

New authenticated route in `backend/app/routes/expert_handoff.py`, alongside
the existing public webhook router (same twin-router-one-prefix pattern
`calls.py` already uses — `public_router` for the webhook, `router` for
everything requiring auth, both mounted at `/api/v1/expert-handoff` in
`main.py`):

```
GET /api/v1/expert-handoff/sessions?bucket=awaiting_payment|paid
```

- `bucket=awaiting_payment` → `status = 'awaiting_payment'`
- `bucket=paid` → `status = 'paid'`
- Query: `expert_handoff_sessions` joined with `leads(name, phone)`, scoped
  to `tenant_id`, ordered by `created_at desc`, same shape as the old
  `bookings.py`'s `list_bookings` (`.select("*, leads(name, phone)")`).
- Gated by `require_permission("conversations.view")` — read-only, matches
  who can already see the Conversations list.

`confirm_expert_handoff_payment()` (existing function, already sets
`ai_enabled=False` and marks the session paid) gets one addition: after
marking paid, call `notify_pool(tenant_id, "expert_handoff_paid", "New paid
consultation", f"Lead '{name}' paid for a consultation — check
Consultations.", db=db)`. Best-effort, same as every other `notify_pool`
call site — never blocks or fails the payment confirmation itself.

## Frontend

**New page:** `frontend/app/dashboard/consultations/page.tsx` — two-pane
layout mirroring Conversations:
- Left: list of sessions for the active bucket (tab/toggle: Awaiting
  Payment / Paid), each row showing lead name, phone, and the fee.
- Right, on selecting a row: a small "Consultation Details" card (collected
  fields — name, DOB, birthplace, whatever that tenant configured — plus
  fee and paid/pending status) stacked above `<ChatThread lead={lead} />`,
  where `lead` is fetched via the existing `api.leads.get(leadId)` (same
  call Conversations already makes when a lead is selected).

**Sidebar:** new top-level entry "Consultations" in `sidebar.tsx`, same
gating pattern as Conversations (`isSubscribed && canAny(["conversations.view",
"conversations.reply"])`), linking to `/dashboard/consultations`.

**Notification rendering:** `"expert_handoff_paid"` is a new `notify_pool`
type. `NotificationBell.tsx`'s `getAlertStyle` switch has a `default` case
(blue/info style) that already handles unrecognized types gracefully — no
frontend change is required for the bell to work, though a dedicated case
can be added for a nicer icon/color if desired later.

## Error handling

- Empty bucket (no sessions yet) → empty state message, not an error.
- Lead fetch failure when a row is selected → same error handling
  `ChatThread`'s existing consumer (Conversations page) already has; no new
  pattern needed.
- `notify_pool` failure → already wrapped in try/except at every existing
  call site; the new call site follows the same convention.

## Testing

- Backend: unit test for the new `GET /sessions` route — bucket filtering,
  tenant scoping, RBAC gate.
- Backend: unit test that `confirm_expert_handoff_payment` calls
  `notify_pool` with the right args (mocked, same style as the existing
  `test_expert_handoff.py` suite).
- Frontend: `tsc --noEmit` and `next lint` clean, matching every other panel
  built this session. No new E2E — reused components already have their own
  coverage via the Conversations page.

## Out of scope

- Resending a payment link to an awaiting-payment lead from this page.
- Manually marking a session paid (e.g. an offline payment) from this page.
- A WhatsApp staff alert for new paid consultations (D6) — bell only for
  now.
- The Astrotamil external astrologer-dashboard adapter — unrelated, already
  tracked separately (`.agents/decisions/log.md` 2026-08-07,
  `.agents/projects/active-backlog.md`).
