# Paid Intake — Diagnosis Report

**Status (2026-09-09): D1–D10, D12, D13 fixed and verified below. Not yet applied: refund-event handling, per-tenant Razorpay dashboard webhook subscriptions for `payment_link.expired`/`payment.failed` (needs your Razorpay dashboard access, not code), D11's dead-arg cleanup (no functional bug, would break test assertions in 4 unrelated files for a no-op). Full backend suite: 1570 passed. Frontend `tsc --noEmit`: clean.**

Read-only diagnosis. All findings below are either **confirmed by a captured transcript** (a mocked-DB repro run against the real `app/services/intake.py` code, no network/LLM calls) or **confirmed by code reading** where noted. Repro script: `scratchpad/intake_repro.py` (throwaway, not committed).

Baseline: `pytest tests/test_intake_packages.py tests/test_intake_non_answers.py tests/test_expert_handoff.py tests/test_payment_razorpay.py tests/test_quick_replies.py` → **166 passed**, run before any of this. The bugs below are real gaps in what those tests exercise, not regressions.

---

## The two symptoms you reported

### 1. "Paid intake is on, lead sends the trigger message, but AI suggests the app instead of collecting details"

Three independent causes converge on this, all confirmed:

**Primary cause — D1, the offer has exactly one acceptable reply.**
[`intake.py:803-806`](backend/app/services/intake.py#L803) — after the offer message goes out, the very next reply is checked against `_is_affirmative()` ([`intake.py:678-680`](backend/app/services/intake.py#L678)), which only recognizes tokens in `_AFFIRMATIVE_RE_WORDS` ([`intake.py:666-676`](backend/app/services/intake.py#L666)): `yes/yeah/ok/sure/seri/aama/haan`, etc. Anything else — **including a clearly interested reply** — sets the session to `cancelled` and hands the turn back to the AI. No re-ask. Every other stage of the flow re-asks on a miss; only this one kills the session on the first miss.

Captured transcript:
```
inbound: 'interested, tell me more'  consumed=False
session patch: [{'status': 'cancelled'}]
```
```
inbound: 'venum, ipo pesuven'  consumed=False
session patch: [{'status': 'cancelled'}]
```
Control (works correctly):
```
inbound: 'yes'  consumed=True
outbound: 'Great! Could you share your full name?'
session patch: [{'package_key': 'standard', ..., 'status': 'collecting'}]
```
Once `consumed=False`, `webhook.py:338-341` falls through to `generate_reply()`. The system prompt at that point contains **no** intake context (session is `cancelled`, not `paid`/in-progress) but does contain the `APP LINK (reference only)` block if `app_download_link` is configured ([`ai_reply.py:299-306`](backend/app/services/ai_reply.py#L299)) — this is the mechanism that produces "download the app."

**Secondary cause — D3, a leftover `paid` session silently blocks the next trigger.**
`_ACTIVE_STATUSES` includes `paid` ([`intake.py:540-544`](backend/app/services/intake.py#L540)), so `_get_active_session` returns it and no new offer is created — but `route_intake` has no `if status == "paid"` branch, so control falls through every `if` to the bottom `return False` ([`intake.py:1029`](backend/app/services/intake.py#L1029), confirmed exact line).

Captured transcript:
```
inbound: 'Will I get married?'  consumed=False
session patch attempts: []
```
`generate_reply()` then injects `_intake_paid_prompt_block` ([`ai_reply.py:1135`](backend/app/services/ai_reply.py#L1135)), which explicitly forbids re-offering the paid service and, when the tenant's answer arrives inside their own app (`answer_in_app=True`), tells the AI to point there. On a demo tenant this session has likely already been paid through once — that stale `paid` row is enough to reproduce your exact symptom on every subsequent trigger until staff resolves it or the 48h sweep runs.

**Tertiary cause — D4, the trigger classifier fails silently.**
[`intake.py:82-101`](backend/app/services/intake.py#L82) — `detect_intake_intent()` is deliberately fail-closed: any Gemini error (missing key, quota, timeout, bad JSON) returns `False` with only a `logger.warning`. Nothing surfaces on the dashboard.

Captured transcript:
```
inbound: 'Will I get married?'  consumed=False
(Gemini raised RuntimeError("quota exceeded") — session never created)
```

**Check this first, in order:** (1) does `intake_sessions` for this lead already have a row with `status='paid'`? — that alone explains it. (2) is `gemini_api_key` actually set for this tenant? (3) reproduce with a plainly affirmative "yes" instead of a more natural reply, to confirm D1.

---

### 2. "Tapped a quick-reply button, bot said it didn't receive the selection"

Confirmed cause — **D2, the tap is matched by a title the button-builder and the matcher don't agree on.**

The chain:
- [`intake.py:471`](backend/app/services/intake.py#L471) builds each button as `{"id": key, "title": button_label or name}`.
- [`webhook.py:546-548`](backend/app/routes/webhook.py#L546) — when the tap comes back, **only `.title` is read**; `.id` (the package `key` — the one value that would match exactly) is discarded.
- [`intake.py:406-408`](backend/app/services/intake.py#L406) — `match_package()` exact-matches the inbound text against `name` or `key` **only**, never `button_label`.
- The Gemini fallback is fed `key: name` pairs too ([`intake.py:410`](backend/app/services/intake.py#L410)) — `button_label` is invisible to it as well.

So the instant a package's `button_label` differs from its `name` (which is the entire reason `button_label` exists — to shorten a name for WhatsApp's 20-char button cap), the tap cannot match anything, fails closed to `None`, and fires `package_reask` — the literal "didn't get your selection, tap again" message.

Captured transcript (package named "General Career Reading", `button_label: "Career"`):
```
inbound (button title as delivered by webhook.py): 'Career'  consumed=True
outbound: "Sorry, I didn't catch which one —

• General Career Reading — ₹299
• General Love Reading — ₹299"
session patch: []
```
Control — when `button_label` happens to equal (a short) `name`, it works:
```
inbound (tap title): 'Basic'  consumed=True
outbound: "Here's what I've got: ... Is that correct?"
session patch: [{'package_key': 'basic', ..., 'status': 'awaiting_confirmation'}]
```
The same hole exists in `match_addons()` ([`intake.py:525`](backend/app/services/intake.py#L525)) and, separately, in list-mode rows: `_row_title()` truncates any label over 24 chars with `…` ([`intake.py:475-485`](backend/app/services/intake.py#L475)), and that truncated form is likewise never shown to the matcher.

**Check this first:** open `/dashboard/settings/packages` for the affected tenant — if any package or addon has a `button_label` set that differs from its full name, or a name over 24 characters being shown as a list, every tap on it is broken. This is not intermittent; it fails every time for that entry.

---

## Full defect table

| ID | Severity | Where | Failure scenario | Status |
|---|---|---|---|---|
| D1 | **Critical** | [intake.py:803-806](backend/app/services/intake.py#L803) | Any offer reply other than an exact affirmative word cancels the session on the first try, no re-ask. | Confirmed — transcript above |
| D2 | **Critical** | [webhook.py:546-548](backend/app/routes/webhook.py#L546), [intake.py:406-408](backend/app/services/intake.py#L406), [intake.py:471](backend/app/services/intake.py#L471) | Button/list tap can't match when `button_label` ≠ `name`, or when the row title was truncated to 24 chars. | Confirmed — transcript above |
| D3 | **High** | [intake.py:1029](backend/app/services/intake.py#L1029) | A lingering `status='paid'` session silently blocks every future trigger for that lead until staff resolves it or the 48h sweep fires. | Confirmed — transcript above |
| D4 | **High** | [intake.py:82-101](backend/app/services/intake.py#L82) | Gemini failure (bad key, quota, timeout) on the trigger classifier fails closed with only a log line — intake silently never starts. | Confirmed — transcript above |
| D5 | Medium | [intake.py:1267](backend/app/services/intake.py#L1267) | `_IN_PROGRESS_STATUSES` omits `awaiting_addon_choice` (present in `_ACTIVE_STATUSES` and `_PACKAGE_CHANGEABLE_STATUSES`) — a lead parked at the addon menu is invisible to the AI's in-progress guard. | Confirmed — `sorted(_IN_PROGRESS_STATUSES)` printed, addon status absent |
| D6 | **High** | [payment_razorpay.py:56-72](backend/app/services/payment_razorpay.py#L56), [routes/intake.py:247-249](backend/app/routes/intake.py#L247) | No `expire_by` sent — links never expire on Razorpay's side; only `payment_link.paid` is handled, so `expired`/`payment.failed`/refund events produce zero state change; `callback_url` is `""`, payer gets no redirect back. | Code reading (Razorpay API not exercised this session — needs test-mode keys) |
| D7 | **High** | [webhook.py:537-538](backend/app/routes/webhook.py#L537) | Image/document/location/sticker inbound is `continue`d — not persisted, no ack, silence to the customer, including mid-intake. | Code reading (deterministic tuple membership check, no branching to verify at runtime) |
| D8 | **High** | [webhook.py:338-341](backend/app/routes/webhook.py#L338) | A consumed intake turn returns before `generate_reply()`'s escalation logic runs — "I want to talk to a human" mid-collection is classified as a question/attempt by `classify_non_answer` and never escalates. | Code reading |
| D9 | Medium | [intake.py:1029-1030](backend/app/services/intake.py#L1029) | A WhatsApp send failure (button or list) is caught only by the outermost blanket `except`, which returns `False` and sends **nothing** — worse, the state-changing DB write for the new status happens *before* the send, so the session is left one step ahead of what the customer actually saw, and `generate_reply()` fires anyway on the same turn. | Confirmed — transcript above |
| D10 | Medium | [IntakeConfigPanel.tsx:35-43](frontend/app/dashboard/settings/IntakeConfigPanel.tsx#L35), [packages/page.tsx:18-27](frontend/app/dashboard/settings/packages/page.tsx#L18) | `DEFAULT.packages = []`; a failed GET leaves the draft at that default, and the next PATCH writes `packages: []`, wiping the tenant's package tree. | Code reading |
| D11 | Low | [webhook.py:345-347](backend/app/routes/webhook.py#L345), [ai_reply.py:1499](backend/app/services/ai_reply.py#L1499) | `build_scorer_context(...)` is computed and passed as `context_block` but never read inside `generate_reply` — dead work, no functional bug. | Code reading |
| D12 | Medium | [intake.py:252-278](backend/app/services/intake.py#L252) | `extract_fields` does no type validation — a `type:"date"` field accepts any string; `options[]` from the config API is never enforced. | Code reading |
| D13 | Medium | [webhook.py:759-777](backend/app/routes/webhook.py#L759) | Opt-out detection only fires on the first inbound after a broadcast — "stop" mid-intake hits `_CANCEL_WORDS` instead, cancelling the session with no unsubscribe recorded. | Code reading |
| D14 | — | — | No existing test covers: stale-button taps, media inbound during intake, button-`id` round-trip, the D9 send-failure path, or the `create_payment_link` payload shape (currency/callback/notes). | Gap, not a defect |

---

## Fix sizing

**One-liner, safe to do first:**
- D5 — add `"awaiting_addon_choice"` to `_IN_PROGRESS_STATUSES`.
- D1 — widen `_AFFIRMATIVE_RE_WORDS`, or (better) treat a non-cancel, non-affirmative reply at `offer_pending` as a re-ask instead of a cancel, mirroring every other stage.

**Contained, one function each:**
- D2 — either (a) start reading `button_reply.id`/`list_reply.id` in `webhook.py` and match on `key` first, falling back to title, or (b) make `match_package`/`match_addons` also compare against `button_label` and the truncated row-title form. (a) is the correct fix — it's the value designed for exactly this and survives truncation and relabeling for free.
- D3 — add a `status == "paid"` branch in `route_intake` (or gate the trigger classifier on `get_paid_unresolved_session`) so a lead can be told a human is already handling their first session, instead of silent no-op.
- D9 — order the DB status write after a successful send, not before; add a text fallback matching `ai_reply.py:1955-1961`'s pattern.
- D12 — enforce `options[]` and lightweight per-type parsing in `extract_fields`.

**Needs design (customer-visible behaviour change, flagging separately):**
- D6 — decide the product behaviour for expired/failed payment links (resend? notify staff? auto-cancel session?) before touching the webhook handler or `create_payment_link`.
- D7 — decide what an image/location sent mid-intake should do (ack + ask for text? forward to staff?) before changing the webhook's type allowlist.
- D8 — decide whether "talk to a human" should interrupt an in-progress paid flow or queue behind it.
- D4 — needs a staff-visible signal (dashboard banner / alert) when the classifier is failing, not just a fix to the failure itself.
- D10 — needs the GET failure path in the frontend fixed so a failed load never round-trips into a destructive PATCH; also worth adding the "before enabling, add a package" guard on this panel too if it isn't already inherited from the packages page.

---

## Scenario matrix

Ran (✅ transcript captured) vs not run this session (code reading only, per D6/D7/D8/D13/D2-webhook-layer above):

| # | Scenario | Expected | Actual | Ran? |
|---|---|---|---|---|
| 1 | Offer → "yes" | Package menu / field ask sent | Matches — `collecting`, asked for name | ✅ |
| 2 | Offer → "interested, tell me more" | Should re-ask or proceed | **Cancelled**, consumed=False (D1) | ✅ |
| 2b | Offer → "venum, ipo pesuven" | Should re-ask or proceed | **Cancelled** (D1) | ✅ |
| 3 | Tap package where `button_label` ≠ `name` | Package selected | **package_reask** (D2) | ✅ |
| 3b | Tap package where `button_label` = short `name` | Package selected | Matches | ✅ (control) |
| 4 | Trigger while a `paid` session exists | Some explicit handling | Silent no-op, falls to app-link AI reply (D3) | ✅ |
| 5 | Trigger with Gemini failing | Some explicit handling | Silent no-op (D4) | ✅ |
| 6 | Lead at addon menu, check in-progress visibility | Should be in-progress | Not in-progress (D5) | ✅ |
| 7 | Button send fails while rendering package menu | Text fallback | **Nothing sent**, state ahead of reality (D9) | ✅ |
| 8 | Free text instead of a tap at each stage | Re-ask | Re-asks correctly (existing test coverage) | Pre-existing test |
| 9 | Two failed attempts on one field → skip | Skip and continue | Covered by `test_intake_attempts.py` | Pre-existing test |
| 10 | Confirm → payment link, amount = leaf + addons | Correct total charged | Covered by `test_expert_handoff.py::test_route_intake_charges_total_amount_including_addons` | Pre-existing test |
| 11 | `payment_link.paid` webhook | Status→paid, receipt sent | Covered by `test_expert_handoff_webhook.py` | Pre-existing test |
| 12 | `payment_link.expired` / `payment.failed` webhook | Some state change | Ignored entirely (D6) | Code reading — needs Razorpay test-mode run |
| 13 | Image/location/document mid-intake | Some ack or handling | Dropped silently (D7) | Code reading — needs webhook HTTP harness |
| 14 | "I want a human" mid-collection | Escalation | Classified as question/attempt, no escalation (D8) | Code reading |
| 15 | "stop" mid-intake | Unsubscribe recorded | Session cancelled, no unsubscribe (D13) | Code reading |
| 16 | Stale button tap from an older menu | Detected as stale | No message-id/menu-version check anywhere — same failure shape as D2 | Code reading |

Scenarios 12–16 need either a live Razorpay test-mode key or a fuller webhook-level HTTP harness (signature verification + tenant resolution mocking) to move from code-reading to captured transcript — that's more setup than the direct in-process calls used above and was not built this session; flagging rather than asserting.

---

## What's unresolved

Nothing further is blocked — this is the full read-only diagnosis. Next move is yours: which fixes to take first (D1/D2/D3 cover both reported symptoms and are the cheapest), and whether to spend the setup cost on a Razorpay-test-mode + webhook-HTTP harness to convert D6/D7/D8/D13 from code-reading to captured transcripts before fixing them.
