# Call Wrap-up v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two separate wrap-up lists (SIM and cloud), the star rating, the tags and "Log the sale" with one two-tap wrap-up. Replace the lead page's "Call Outcome" card with a "Send details on WhatsApp" card. Wire the new values through lead status, reminders, deals, DNC, alerts, check-10 scoring (including the cloud-only AI Hot/Warm/Cold correction) and every report.

**Architecture:**
- The backend rules live in one pure module, `services/call_wrapup.py` (constants, validation, retry times, phrases, connect rate).
- All database effects of a saved wrap-up live in `services/wrapup_apply.py`. The `PATCH /calls/{id}/outcome` route only validates and delegates, and a new `GET /calls/wrapup-context` feeds the form its cloud pre-fill and retry suggestions.
- The frontend mirrors this: `lib/call-wrapup.ts` holds labels, tones and IST time helpers, `wrapup-draft.ts` holds the pure form logic, and there are presentational `WrapupModal` and `SendDetailsView` components.
- The database changes in two steps: migration 208 (before deploy) widens the checks to old ∪ new and adds columns, and migration 209 (after deploy) maps old rows, narrows the checks and drops the replaced columns.

**Tech Stack:** FastAPI + supabase-py (Python 3.13, unittest/pytest), Next.js 14 (basePath `/aira`) + TypeScript + Tailwind + vitest, Supabase Postgres, Meta WhatsApp Cloud API, Gemini (check 10).

**Spec:** `docs/superpowers/specs/2026-09-27-call-wrapup-v2-design.md` (binding). Read it before starting any task.

## Global Constraints

- One wrap-up for both providers: "Two-tap wrap-up, identical for SIM and cloud".
- Tap 1 values: `connected | not_picked | busy | switched_off`, stored in `call_logs.manual_status` for both providers.
- Tap 2 values (only when Connected): `interested_booked`, `interested_needs_time`, `maybe_later`, `call_later`, `converted`, `not_interested`, `disqualified`, `wrong_number`, `language_barrier`, `do_not_call`, stored in `call_logs.outcome`.
- Labels (verbatim): 👍 Interested, next step booked · 🤔 Interested, needs time or more information · 🙂 Maybe later · 📅 Call later (customer asked) · 🎉 Converted · 👎 Not interested · 🚫 Disqualified · ❓ Wrong number · 🗣️ Language barrier · ⛔ Do not call.
- Star rating and tags are removed from the wrap-up. "Converted" replaces "Log the sale" by creating the deal itself (≥1 product from catalog OR an amount; a `won` deal, source `call`).
- The wrap-up form has **no** WhatsApp button, only the notes box.
- Notes are required for "Interested, next step booked", "Interested, needs time" and "Converted".
- "Language barrier" requires one of: Tamil, English, Hindi, Telugu, Malayalam, Kannada, Other.
- `not_interested` reason ∈ price, already_bought, no_need, other. `disqualified` reason ∈ never_enquired, not_a_fit, not_decision_maker.
- `do_not_call` has an optional checkbox "Also stop WhatsApp/SMS" (sets `opted_out = true`).
- Retry suggestions: Not picked → +2 h; Busy → +30 min; Switched off / not reachable → tomorrow 10:00 (tenant local = IST). After 3 consecutive failed attempts on the lead → tomorrow 10:00. The telecaller can change the time. Saving creates the reminder in Scheduled Calls.
- Quick time buttons: In 1 hour · This evening 6 PM · Tomorrow 10 AM · Pick a date & time.
- A cloud call is pre-filled from the CDR (answered → connected, otherwise not_picked) and stays editable. TeleCMI can't tell busy from switched off.
- The lead's A/B/C/D segment is never changed by the wrap-up. Stage events keep being recorded.
- D10 (cloud only): check 10 also returns the AI's hot/warm/cold/none reading. If it differs from the telecaller's hot/warm/cold, `leads.call_status` becomes the AI's value, the original is kept in the evaluation, and the admin sees "AI changed Warm → Hot" on the call card. SIM keeps the telecaller's choice.
- Send details: from the business WhatsApp number. If the customer's last inbound message is under 24 h old, send a free message pre-filled from the Services page. Otherwise send an approved template with blanks pre-filled. Everything is editable, nothing is ever sent automatically, and the message appears in Conversations. The card is hidden when the tenant has no WhatsApp or the lead has opted out.
- Connect rate = connected ÷ all wrap-ups.
- New `call_logs` columns: `outcome_reason text`, `preferred_language text`, `next_action_at timestamptz` (replaces `wrapup_callback_at`), `ai_call_status text`.
- User preferences:
  - The UI must be top-grade and match the existing dashboard style.
  - Remove replaced code completely (no dead code).
  - Commit with explicit pathspecs.
  - Never push.
  - End commit messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Migrations: the controller applies them via Supabase MCP. Implementers only write the files. 208 is applied **before** deploy; 209 only **after** deploy. 207 is already reserved (pending post-deploy scoring cleanup) and is untouched here.
- Backend test command (from `backend/`): `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/<file>.py -v`.
- Frontend: `npm run typecheck` and `npm run lint` must both pass after every frontend task. Unit tests: `npx vitest run <path>`.

## Review Focus

These are the inputs most likely to bite a real user that the spec implies but does not spell out. Each one has a pinned test in the owning task.

1. **A double-submitted "Converted"** (the telecaller taps Save again after a network blip, or re-opens the call) must create exactly one Won deal. Pinned in Task 4 (`test_resubmitted_conversion_does_not_create_a_second_deal`).
2. **A reminder time in the past** ("This evening 6 PM" after 6 PM, or a custom past date) must never become a silently-missed reminder.
   - The 6 PM chip is disabled after 6 PM (Task 9 `quickTimes` test).
   - The backend rejects times more than 5 minutes in the past with "Pick a time in the future." (Task 1 `test_past_time_is_rejected`).
3. **A telecaller whose laptop is not set to IST** must still get "Tomorrow 10 AM" = 10:00 IST and see IST times. All time helpers compute from UTC with a fixed +05:30 offset and never read the machine time zone. Pinned in Task 9 (`fromIstInputs` / `formatIstWhen` tests) and Task 1 (`tomorrow_at_10`).
4. **The AI Hot/Warm/Cold correction racing a newer state** (the lead was re-called and converted before the background check-10 ran) must not overwrite the newer status. The lead update is guarded by `call_status = <telecaller's value>`. Pinned in Task 6 (`test_correction_only_replaces_the_telecallers_value`).
5. **Services-page details with line breaks put into a WhatsApp template variable**: Meta rejects template parameters containing new lines. Details are flattened to one line for templates, and every typed variable is whitespace-collapsed before sending. Pinned in Task 8 (`test_template_variables_are_flattened_to_one_line`).

Also covered by tests but less likely: an AI-raised `language_barrier` alert that already exists for the call gets the "Reassign to a Tamil speaker" text instead of being dropped (Task 3); a cloud call that never connected cannot be saved as Connected (Tasks 1, 5).

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `backend/app/services/call_wrapup.py` | Create | Pure wrap-up rules: value sets, labels, validation, retry suggestion, streaks, lead status mapping, reminder note, next-step phrase, wrap-up context, connect rate |
| `backend/tests/test_call_wrapup_rules.py` | Create | Tests for the rules |
| `backend/supabase/migrations/208_call_wrapup_v2_widen.sql` | Create | Pre-deploy: new columns, checks widened to old ∪ new |
| `backend/supabase/migrations/209_call_wrapup_v2_narrow.sql` | Create | Post-deploy: map old rows, narrow checks, drop `wrapup_callback_at`, `quality_rating` |
| `backend/tests/test_wrapup_v2_migrations.py` | Create | Migration contract tests (value sets equal the Python constants) |
| `backend/app/services/call_alerts.py` | Modify | Add `raise_reassign_alert` |
| `backend/tests/test_reassign_alert.py` | Create | Tests for the reassign alert |
| `backend/app/services/wrapup_apply.py` | Create | Writes one saved wrap-up (call row, lead, stage event, follow-ups, reminder, deal, DNC, alert) |
| `backend/tests/test_wrapup_apply.py` | Create | Per-option effect tests (FakeSupabase) |
| `backend/app/routes/calls.py` | Modify | New `WrapupIn` + `set_outcome`; `GET /wrapup-context`; CDR/SIM never write `outcome`; dial sets `trying`; pending list; card fields; next-lead exclusions |
| `backend/tests/test_call_wrapup_routes.py` | Create | Route tests (save, context, Literal contract) |
| `backend/tests/test_calls_scoring_routes.py` | Modify | Remove the two old outcome classes (replaced by the new file) |
| `backend/tests/test_sim_cdr_static.py`, `test_telecmi_cdr_legs.py`, `test_sim_manual_status_static.py`, `test_call_feedback_gate.py`, `test_calls_recent.py` | Modify | Follow the new contract |
| `backend/app/services/call_marking.py` | Modify | Check-10 prompt/mapping on new values + D10 correction |
| `backend/tests/test_call_crm_check.py` | Modify (full rewrite) | Check-10 + D10 tests |
| `backend/app/routes/analytics.py`, `operator.py`, `callers.py`, `leads.py`, `telecalling_upload.py`; `services/assignment.py`, `contact_recycler.py`, `ai_reply.py`; `models/schemas.py`; `main.py` | Modify | Readers of the removed values |
| `backend/tests/test_wrapup_readers.py` | Create | Reader tests |
| `backend/app/services/call_details_share.py` | Create | Send-details context + send (free text / template) |
| `backend/app/routes/lead_details_share.py` | Create | `GET/POST /api/v1/leads/{id}/send-details` |
| `backend/tests/test_call_details_share.py` | Create | Service + route tests |
| `frontend/lib/api.ts` | Modify | New types and methods; remove old types and methods (Task 12) |
| `frontend/lib/call-wrapup.ts` (+ `.test.ts`) | Create | Options, labels, tones, lead-status helpers, IST quick times |
| `frontend/app/dashboard/telecalling/lib/wrapup-draft.ts` (+ `.test.ts`) | Create | Draft state, selection rules, validation, payload |
| `frontend/app/dashboard/telecalling/components/wrapup/WrapupModal.tsx` | Create | The two-tap form (presentational) |
| `frontend/app/dashboard/telecalling/components/wrapup/QuickTimePicker.tsx` | Create | Quick time buttons + custom IST date/time |
| `frontend/app/dashboard/telecalling/components/wrapup/SalePicker.tsx` | Create | Products-or-amount for Converted |
| `frontend/app/dashboard/telecalling/components/CockpitModals.tsx` | Modify (full rewrite) | Old wrap-up removed; renders `WrapupModal` |
| `frontend/app/dashboard/telecalling/lib/useCallingCockpit.ts` | Modify | Draft/context/catalog state, cloud no-answer opens wrap-up, new submit, quick-outcome removed |
| `frontend/app/dashboard/telecalling/lib/send-details.ts` (+ `.test.ts`) | Create | Template render/label helpers |
| `frontend/app/dashboard/telecalling/components/SendDetailsCard.tsx` | Create | Lead-page WhatsApp card (container + view) |
| `frontend/app/dashboard/telecalling/components/LeadDetailPanel.tsx` | Modify | Call Outcome card → SendDetailsCard; shared labels |
| `frontend/components/CallAi.tsx` | Modify | Admin-only "AI changed Warm → Hot" note |
| 13 reader components (listed in Task 12) | Modify | New labels, tones and lead statuses |
| `.agents/context/subsystem-notes.md`, `.agents/decisions/log.md` | Modify | Docs |

---

### Task 1: Wrap-up rules module (backend)

**Files:**
- Create: `backend/app/services/call_wrapup.py`
- Test: `backend/tests/test_call_wrapup_rules.py`

**Interfaces:**
- Consumes: nothing.
- Produces (all in `app.services.call_wrapup`):
  - Constants:
    - `IST`
    - `CONNECTS`, `NO_CONNECTS`, `OUTCOMES`
    - `NOT_INTERESTED_REASONS`, `DISQUALIFIED_REASONS`, `REASONS`, `LANGUAGES`
    - `LEAD_CALL_STATUSES`, `CLOSED_LEAD_STATUSES`
    - `TEMPERATURES`, `AI_CALL_STATUSES`
    - `CONNECT_LABEL`, `OUTCOME_LABEL`, `LANGUAGE_LABEL`, `TEMPERATURE_LABEL`
    - `LEAD_STATUS_FOR_OUTCOME`, `TEMPERATURE_FOR_OUTCOME`
    - `NEEDS_NOTES`, `NEEDS_TIME`, `REMINDER_OUTCOMES`, `STOP_ALL_FOLLOW_UPS`
    - `SALE_LINE_NAME`
  - `class WrapupError(ValueError)`
  - `as_aware(dt: datetime) -> datetime` (naive ⇒ IST)
  - `tomorrow_at_10(now: datetime) -> datetime` (UTC)
  - `suggest_retry_at(manual_status: str, failed_before: int, now: datetime) -> datetime` (UTC)
  - `is_no_connect(log: dict) -> bool`
  - `consecutive_no_connects(logs_newest_first: Iterable[dict]) -> int`
  - `lead_status_after(manual_status: str, outcome: str | None, no_connects_total: int, max_attempts: int) -> str`
  - `cloud_never_connected(row: dict) -> bool`
  - `validate_wrapup(*, never_connected, manual_status, outcome, notes, next_action_at, reason, preferred_language, has_products, amount_paise, now) -> None` (raises `WrapupError`)
  - `sale_lines(products: list[dict], amount_paise: int | None) -> list[dict]`
  - `reminder_note(manual_status: str, outcome: str | None, notes: str | None) -> str`
  - `when_phrase(at, now) -> str`
  - `next_step_phrase(outcome, at, now) -> str`
  - `call_result_label(row: dict) -> str | None`
  - `wrapup_context(row: dict | None, failed_before: int, now: datetime) -> dict` with keys `connect_prefill`, `never_connected`, `failed_before`, `retry_suggestions` ({not_picked, busy, switched_off} → ISO)
  - `connect_rate(logs: Iterable[dict]) -> float`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_call_wrapup_rules.py
"""Wrap-up v2 rules: retry times, streaks, lead status, validation, phrases, context, connect rate."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_wrapup as cw

UTC = timezone.utc
NOW = datetime(2026, 9, 27, 8, 30, tzinfo=UTC)  # Sunday 14:00 IST
TOMORROW_10 = datetime(2026, 9, 28, 4, 30, tzinfo=UTC)  # Monday 10:00 IST


def _v(**kw):
    args = dict(
        never_connected=False, manual_status="connected", outcome="maybe_later", notes=None,
        next_action_at=None, reason=None, preferred_language=None, has_products=False,
        amount_paise=None, now=NOW,
    )
    args.update(kw)
    cw.validate_wrapup(**args)


class RetryTests(unittest.TestCase):
    def test_not_picked_is_two_hours_later(self):
        self.assertEqual(cw.suggest_retry_at("not_picked", 0, NOW), NOW + timedelta(hours=2))

    def test_busy_is_thirty_minutes_later(self):
        self.assertEqual(cw.suggest_retry_at("busy", 1, NOW), NOW + timedelta(minutes=30))

    def test_switched_off_is_tomorrow_10am_ist(self):
        self.assertEqual(cw.suggest_retry_at("switched_off", 0, NOW), TOMORROW_10)

    def test_third_failure_in_a_row_is_tomorrow_10am(self):
        self.assertEqual(cw.suggest_retry_at("not_picked", 2, NOW), TOMORROW_10)

    def test_tomorrow_follows_the_ist_calendar_after_midnight_ist(self):
        late = datetime(2026, 9, 27, 19, 0, tzinfo=UTC)  # 00:30 IST on the 28th
        self.assertEqual(cw.tomorrow_at_10(late), datetime(2026, 9, 29, 4, 30, tzinfo=UTC))

    def test_suggestions_are_utc(self):
        self.assertEqual(cw.suggest_retry_at("busy", 0, NOW.astimezone(cw.IST)).utcoffset(), timedelta(0))

    def test_connected_has_no_retry(self):
        with self.assertRaises(cw.WrapupError):
            cw.suggest_retry_at("connected", 0, NOW)


class StreakTests(unittest.TestCase):
    def test_counts_until_the_first_connected_call(self):
        logs = [
            {"manual_status": "busy"}, {"manual_status": None, "status": "no_answer"},
            {"manual_status": "connected"}, {"manual_status": "busy"},
        ]
        self.assertEqual(cw.consecutive_no_connects(logs), 2)

    def test_a_call_still_in_progress_breaks_the_streak(self):
        self.assertEqual(cw.consecutive_no_connects([{"manual_status": None, "status": "initiated"}, {"manual_status": "busy"}]), 0)

    def test_empty_history(self):
        self.assertEqual(cw.consecutive_no_connects([]), 0)


class LeadStatusTests(unittest.TestCase):
    def test_no_connect_is_trying_until_max_attempts(self):
        self.assertEqual(cw.lead_status_after("not_picked", None, 3, 4), "trying")
        self.assertEqual(cw.lead_status_after("busy", None, 4, 4), "unreachable")

    def test_each_outcome_maps_to_the_approved_status(self):
        expected = {
            "interested_booked": "hot", "interested_needs_time": "warm", "maybe_later": "cold",
            "call_later": "callback", "converted": "converted", "not_interested": "not_interested",
            "disqualified": "disqualified", "wrong_number": "wrong_number",
            "language_barrier": "language_barrier", "do_not_call": "dnc",
        }
        for outcome, status in expected.items():
            self.assertEqual(cw.lead_status_after("connected", outcome, 0, 4), status)

    def test_every_status_is_allowed(self):
        self.assertTrue(set(cw.LEAD_STATUS_FOR_OUTCOME.values()) <= set(cw.LEAD_CALL_STATUSES))


class ValidateTests(unittest.TestCase):
    def assertRejects(self, message, **kw):
        with self.assertRaises(cw.WrapupError) as err:
            _v(**kw)
        self.assertEqual(str(err.exception), message)

    def test_a_valid_wrapup_passes(self):
        _v()
        _v(manual_status="busy", outcome=None)

    def test_cloud_call_that_never_connected_cannot_be_connected(self):
        self.assertRejects("This call never connected, so pick Not picked, Busy or Switched off.", never_connected=True)

    def test_no_connect_cannot_have_a_result(self):
        self.assertRejects("Only a connected call can have a result.", manual_status="not_picked", outcome="maybe_later")

    def test_connected_needs_a_result(self):
        self.assertRejects("Pick what happened on the call.", outcome=None)

    def test_notes_required(self):
        for outcome in ("interested_booked", "interested_needs_time"):
            self.assertRejects("Add a short note for this result.", outcome=outcome, next_action_at=NOW + timedelta(days=1))
        self.assertRejects("Add a short note for this result.", outcome="converted", amount_paise=50000, notes="  ")

    def test_time_required(self):
        for outcome in ("interested_booked", "interested_needs_time", "call_later"):
            self.assertRejects("Pick a date and time.", outcome=outcome, notes="x")

    def test_maybe_later_time_is_optional(self):
        _v(outcome="maybe_later", next_action_at=None)

    def test_past_time_is_rejected(self):
        self.assertRejects("Pick a time in the future.", outcome="call_later", next_action_at=NOW - timedelta(minutes=6))
        _v(outcome="call_later", next_action_at=NOW - timedelta(minutes=4))

    def test_reasons(self):
        self.assertRejects("Pick why they're not interested.", outcome="not_interested", reason=None)
        self.assertRejects("Pick why the lead is disqualified.", outcome="disqualified", reason="price")
        _v(outcome="disqualified", reason="never_enquired")

    def test_language(self):
        self.assertRejects("Pick the language the customer speaks.", outcome="language_barrier")
        _v(outcome="language_barrier", preferred_language="tamil")

    def test_sale_needs_products_or_amount_not_both(self):
        self.assertRejects("Add the products sold or the amount.", outcome="converted", notes="paid")
        self.assertRejects("Add the products sold or the amount, not both.", outcome="converted", notes="paid", has_products=True, amount_paise=100)
        _v(outcome="converted", notes="paid", has_products=True)


class ContextTests(unittest.TestCase):
    def test_no_call_row(self):
        ctx = cw.wrapup_context(None, 0, NOW)
        self.assertEqual((ctx["connect_prefill"], ctx["never_connected"], ctx["failed_before"]), (None, False, 0))
        self.assertEqual(ctx["retry_suggestions"]["not_picked"], (NOW + timedelta(hours=2)).isoformat())

    def test_cloud_answered_prefills_connected(self):
        ctx = cw.wrapup_context({"provider": "telecmi", "status": "completed", "duration_seconds": 80}, 0, NOW)
        self.assertEqual((ctx["connect_prefill"], ctx["never_connected"]), ("connected", False))

    def test_cloud_missed_prefills_not_picked(self):
        ctx = cw.wrapup_context({"provider": "telecmi", "status": "no_answer", "duration_seconds": 0}, 2, NOW)
        self.assertEqual((ctx["connect_prefill"], ctx["never_connected"]), ("not_picked", True))
        self.assertEqual(set(ctx["retry_suggestions"].values()), {TOMORROW_10.isoformat()})

    def test_sim_is_never_prefilled(self):
        self.assertIsNone(cw.wrapup_context({"provider": "sim_basic", "status": "sim_started"}, 0, NOW)["connect_prefill"])


class PhraseTests(unittest.TestCase):
    def test_within_a_week_uses_the_weekday(self):
        at = datetime(2026, 10, 2, 5, 30, tzinfo=UTC)
        self.assertEqual(cw.next_step_phrase("interested_booked", at, NOW), "Next step on Friday at 11 AM")

    def test_today_and_tomorrow(self):
        self.assertEqual(cw.next_step_phrase("call_later", datetime(2026, 9, 27, 12, 30, tzinfo=UTC), NOW), "Call back today at 6 PM")
        self.assertEqual(
            cw.next_step_phrase("interested_needs_time", datetime(2026, 9, 28, 5, 0, tzinfo=UTC), NOW),
            "Follow-up call tomorrow at 10:30 AM",
        )

    def test_far_dates_use_day_and_month(self):
        self.assertEqual(cw.next_step_phrase("interested_booked", datetime(2026, 10, 10, 5, 30, tzinfo=UTC), NOW), "Next step on 10 Oct at 11 AM")


class SmallHelperTests(unittest.TestCase):
    def test_reminder_note(self):
        self.assertEqual(cw.reminder_note("busy", None, None), "Retry: Busy")
        self.assertEqual(cw.reminder_note("connected", "call_later", "after salary"), "Call later (customer asked) — after salary")

    def test_sale_lines(self):
        self.assertEqual(cw.sale_lines([{"catalog_item_id": "i1", "qty": 2}], None), [{"catalog_item_id": "i1", "qty": 2}])
        self.assertEqual(cw.sale_lines([], 150000), [{"name": "Sale on call", "qty": 1, "unit_price_paise": 150000}])

    def test_connect_rate_counts_wrapups_only(self):
        logs = [{"manual_status": "connected"}, {"manual_status": "not_picked"}, {"manual_status": None}, {"manual_status": "busy"}]
        self.assertEqual(cw.connect_rate(logs), 0.3333)
        self.assertEqual(cw.connect_rate([]), 0.0)

    def test_as_aware_reads_naive_times_as_ist(self):
        self.assertEqual(cw.as_aware(datetime(2026, 9, 28, 10, 0)), TOMORROW_10)

    def test_call_result_label(self):
        self.assertEqual(cw.call_result_label({"outcome": "maybe_later", "manual_status": "connected"}), "Maybe later")
        self.assertEqual(cw.call_result_label({"outcome": None, "manual_status": "busy"}), "Busy")
        self.assertIsNone(cw.call_result_label({}))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`): `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_call_wrapup_rules.py -v`
Expected: collection error: `ImportError: cannot import name 'call_wrapup'`.

- [ ] **Step 3: Write the implementation**

```python
# backend/app/services/call_wrapup.py
"""Call wrap-up v2 rules (docs/superpowers/specs/2026-09-27-call-wrapup-v2-design.md).

One two-tap wrap-up for SIM and cloud calls. Tap 1 (`call_logs.manual_status`) says
whether the call connected; tap 2 (`call_logs.outcome`) says what happened. Pure
functions only: services/wrapup_apply.py does the writes, so every rule here is
tested without a database.
"""
from collections.abc import Iterable
from datetime import datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

CONNECTS = ("connected", "not_picked", "busy", "switched_off")
NO_CONNECTS = ("not_picked", "busy", "switched_off")
OUTCOMES = (
    "interested_booked", "interested_needs_time", "maybe_later", "call_later", "converted",
    "not_interested", "disqualified", "wrong_number", "language_barrier", "do_not_call",
)
NOT_INTERESTED_REASONS = ("price", "already_bought", "no_need", "other")
DISQUALIFIED_REASONS = ("never_enquired", "not_a_fit", "not_decision_maker")
REASONS = NOT_INTERESTED_REASONS + DISQUALIFIED_REASONS
LANGUAGES = ("tamil", "english", "hindi", "telugu", "malayalam", "kannada", "other")
LEAD_CALL_STATUSES = (
    "new", "trying", "unreachable", "hot", "warm", "cold", "callback", "converted",
    "not_interested", "disqualified", "wrong_number", "language_barrier", "dnc",
)
# Leads nobody should be dialled or auto-assigned for any more.
CLOSED_LEAD_STATUSES = ("converted", "dnc", "unreachable", "disqualified", "wrong_number")
TEMPERATURES = ("hot", "warm", "cold")
AI_CALL_STATUSES = TEMPERATURES + ("none",)

CONNECT_LABEL = {
    "connected": "Connected", "not_picked": "Not picked", "busy": "Busy",
    "switched_off": "Switched off / not reachable",
}
OUTCOME_LABEL = {
    "interested_booked": "Interested, next step booked",
    "interested_needs_time": "Interested, needs time or more information",
    "maybe_later": "Maybe later",
    "call_later": "Call later (customer asked)",
    "converted": "Converted",
    "not_interested": "Not interested",
    "disqualified": "Disqualified",
    "wrong_number": "Wrong number",
    "language_barrier": "Language barrier",
    "do_not_call": "Do not call",
}
LANGUAGE_LABEL = {
    "tamil": "Tamil", "english": "English", "hindi": "Hindi", "telugu": "Telugu",
    "malayalam": "Malayalam", "kannada": "Kannada", "other": "Other",
}
TEMPERATURE_LABEL = {"hot": "Hot", "warm": "Warm", "cold": "Cold"}

LEAD_STATUS_FOR_OUTCOME = {
    "interested_booked": "hot", "interested_needs_time": "warm", "maybe_later": "cold",
    "call_later": "callback", "converted": "converted", "not_interested": "not_interested",
    "disqualified": "disqualified", "wrong_number": "wrong_number",
    "language_barrier": "language_barrier", "do_not_call": "dnc",
}
TEMPERATURE_FOR_OUTCOME = {"interested_booked": "hot", "interested_needs_time": "warm", "maybe_later": "cold"}

NEEDS_NOTES = ("interested_booked", "interested_needs_time", "converted")
NEEDS_TIME = ("interested_booked", "interested_needs_time", "call_later")
REMINDER_OUTCOMES = ("interested_booked", "interested_needs_time", "maybe_later", "call_later")
STOP_ALL_FOLLOW_UPS = ("wrong_number", "do_not_call")
NEXT_STEP_NOUN = {
    "interested_booked": "Next step", "interested_needs_time": "Follow-up call",
    "maybe_later": "Follow-up call", "call_later": "Call back",
}

RETRY_DELAY = {"not_picked": timedelta(hours=2), "busy": timedelta(minutes=30)}
FAILED_STREAK_LIMIT = 3
PAST_TOLERANCE = timedelta(minutes=5)
SALE_LINE_NAME = "Sale on call"


class WrapupError(ValueError):
    """A wrap-up the telecaller has to fix; routes turn it into a 400."""


def as_aware(dt: datetime) -> datetime:
    """A time picked without a zone is the tenant's local time (IST)."""
    return dt if dt.tzinfo else dt.replace(tzinfo=IST)


def tomorrow_at_10(now: datetime) -> datetime:
    day = now.astimezone(IST).date() + timedelta(days=1)
    return datetime.combine(day, time(10, 0), tzinfo=IST).astimezone(timezone.utc)


def suggest_retry_at(manual_status: str, failed_before: int, now: datetime) -> datetime:
    """D5: not picked +2h, busy +30min, switched off tomorrow 10:00 IST; the 3rd failure in a row -> tomorrow 10:00."""
    if manual_status not in NO_CONNECTS:
        raise WrapupError("Only a call that didn't connect gets a retry time.")
    if manual_status == "switched_off" or failed_before + 1 >= FAILED_STREAK_LIMIT:
        return tomorrow_at_10(now)
    return (now + RETRY_DELAY[manual_status]).astimezone(timezone.utc)


def is_no_connect(log: dict) -> bool:
    manual_status = log.get("manual_status")
    if manual_status:
        return manual_status in NO_CONNECTS
    return log.get("status") in ("no_answer", "missed", "failed")


def consecutive_no_connects(logs_newest_first: Iterable[dict]) -> int:
    count = 0
    for log in logs_newest_first:
        if not is_no_connect(log):
            break
        count += 1
    return count


def lead_status_after(manual_status: str, outcome: str | None, no_connects_total: int, max_attempts: int) -> str:
    if manual_status in NO_CONNECTS:
        return "unreachable" if no_connects_total >= max_attempts else "trying"
    return LEAD_STATUS_FOR_OUTCOME[outcome]


def cloud_never_connected(row: dict) -> bool:
    """TeleCMI's CDR is the truth for cloud calls: no talk time means nobody answered."""
    return row.get("status") in ("no_answer", "missed") or (
        row.get("status") == "completed" and not row.get("duration_seconds")
    )


def validate_wrapup(
    *, never_connected: bool, manual_status: str, outcome: str | None, notes: str | None,
    next_action_at: datetime | None, reason: str | None, preferred_language: str | None,
    has_products: bool, amount_paise: int | None, now: datetime,
) -> None:
    if manual_status not in CONNECTS:
        raise WrapupError("Pick whether the call connected.")
    if manual_status == "connected":
        if never_connected:
            raise WrapupError("This call never connected, so pick Not picked, Busy or Switched off.")
        if outcome not in OUTCOMES:
            raise WrapupError("Pick what happened on the call.")
    elif outcome is not None:
        raise WrapupError("Only a connected call can have a result.")
    if outcome in NEEDS_TIME and next_action_at is None:
        raise WrapupError("Pick a date and time.")
    uses_time = manual_status in NO_CONNECTS or outcome in REMINDER_OUTCOMES
    if uses_time and next_action_at is not None and next_action_at < now - PAST_TOLERANCE:
        raise WrapupError("Pick a time in the future.")
    if outcome == "not_interested" and reason not in NOT_INTERESTED_REASONS:
        raise WrapupError("Pick why they're not interested.")
    if outcome == "disqualified" and reason not in DISQUALIFIED_REASONS:
        raise WrapupError("Pick why the lead is disqualified.")
    if outcome == "language_barrier" and preferred_language not in LANGUAGES:
        raise WrapupError("Pick the language the customer speaks.")
    if outcome == "converted":
        if has_products and amount_paise:
            raise WrapupError("Add the products sold or the amount, not both.")
        if not has_products and not amount_paise:
            raise WrapupError("Add the products sold or the amount.")
    if outcome in NEEDS_NOTES and not (notes or "").strip():
        raise WrapupError("Add a short note for this result.")


def sale_lines(products: list[dict], amount_paise: int | None) -> list[dict]:
    """Deal lines for a call sale: catalog products (price comes from the catalog), or one amount line."""
    if products:
        return [{"catalog_item_id": p["catalog_item_id"], "qty": int(p.get("qty") or 1)} for p in products]
    return [{"name": SALE_LINE_NAME, "qty": 1, "unit_price_paise": int(amount_paise)}]


def reminder_note(manual_status: str, outcome: str | None, notes: str | None) -> str:
    label = OUTCOME_LABEL[outcome] if outcome else f"Retry: {CONNECT_LABEL[manual_status].split(' / ')[0]}"
    return (f"{label} — {notes}" if notes else label)[:500]


def _clock(local: datetime) -> str:
    hour = local.hour % 12 or 12
    suffix = "AM" if local.hour < 12 else "PM"
    return f"{hour} {suffix}" if local.minute == 0 else f"{hour}:{local.minute:02d} {suffix}"


def when_phrase(at: datetime, now: datetime) -> str:
    local = at.astimezone(IST)
    days = (local.date() - now.astimezone(IST).date()).days
    if days == 0:
        day = "today"
    elif days == 1:
        day = "tomorrow"
    elif 1 < days < 7:
        day = f"on {local.strftime('%A')}"
    else:
        day = f"on {local.day} {local.strftime('%b')}"
    return f"{day} at {_clock(local)}"


def next_step_phrase(outcome: str, at: datetime, now: datetime) -> str:
    """'Next step on Friday at 11 AM' — used to pre-fill the WhatsApp details."""
    return f"{NEXT_STEP_NOUN[outcome]} {when_phrase(at, now)}"


def call_result_label(row: dict) -> str | None:
    return OUTCOME_LABEL.get(row.get("outcome")) or CONNECT_LABEL.get(row.get("manual_status"))


def wrapup_context(row: dict | None, failed_before: int, now: datetime) -> dict:
    cloud = bool(row) and row.get("provider") == "telecmi"
    never = cloud and cloud_never_connected(row)
    prefill = None
    if cloud and row.get("status") in ("completed", "no_answer", "missed"):
        prefill = "not_picked" if never else "connected"
    return {
        "connect_prefill": prefill,
        "never_connected": never,
        "failed_before": failed_before,
        "retry_suggestions": {c: suggest_retry_at(c, failed_before, now).isoformat() for c in NO_CONNECTS},
    }


def connect_rate(logs: Iterable[dict]) -> float:
    """Connected ÷ all wrap-ups (calls with a tap-1 answer)."""
    wrapped = [log for log in logs if log.get("manual_status") in CONNECTS]
    if not wrapped:
        return 0.0
    return round(sum(1 for log in wrapped if log["manual_status"] == "connected") / len(wrapped), 4)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_call_wrapup_rules.py -v`
Expected: all tests PASS (35 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/call_wrapup.py backend/tests/test_call_wrapup_rules.py
git commit -m "feat(calls): wrap-up v2 rules module" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/app/services/call_wrapup.py backend/tests/test_call_wrapup_rules.py
```

---

### Task 2: Migration 208 — widen checks, add columns (safe before deploy)

**Files:**
- Create: `backend/supabase/migrations/208_call_wrapup_v2_widen.sql`
- Test: `backend/tests/test_wrapup_v2_migrations.py`

**Interfaces:**
- Consumes: `call_wrapup.OUTCOMES`, `CONNECTS`, `LEAD_CALL_STATUSES`, `REASONS`, `LANGUAGES`, `AI_CALL_STATUSES`.
- Produces: new DB columns `call_logs.outcome_reason`, `preferred_language`, `next_action_at`, `ai_call_status`. The checks accept old ∪ new values.

- [ ] **Step 1 (controller, Supabase MCP `execute_sql`, read-only): read the live constraint definitions.**

```sql
select conrelid::regclass as tbl, conname, pg_get_constraintdef(oid) as def
from pg_constraint
where contype = 'c'
  and conrelid in ('public.call_logs'::regclass, 'public.leads'::regclass)
  and (pg_get_constraintdef(oid) ilike '%outcome%'
       or pg_get_constraintdef(oid) ilike '%manual_status%'
       or pg_get_constraintdef(oid) ilike '%call_status%');
```

Expected: `call_logs_outcome_check` (converted, interested, callback, not_interested, no_answer), `call_logs_manual_status_check` (connected, not_picked, busy, wrong_number, interested, not_interested, callback) and `leads_call_status_check` (new, in_progress, callback, converted, not_interested, dnc, unreachable).

If the live names or value sets differ, the SQL below must be adjusted before commit:
- Use the live constraint names in `DROP CONSTRAINT`.
- Add every extra live value to the widened set.
- Add every extra live value to `OLD_*` in the test.
- Add a mapping for every extra live value to Task 13's migration 209.

Also run:

```sql
select proname from pg_proc
where prosrc ilike '%wrapup_callback_at%' or prosrc ilike '%quality_rating%'
   or (prosrc ilike '%call_status%' and prosrc ilike '%in_progress%');
select viewname from pg_views where definition ilike '%wrapup_callback_at%' or definition ilike '%quality_rating%';
```

Expected: no rows. Any hit must be updated in migration 209 (Task 13) before the column drop.

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_wrapup_v2_migrations.py
"""Migration contract: 208 widens to old ∪ new and adds columns; 209 narrows to exactly the new sets."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import call_wrapup as cw

OLD_OUTCOMES = {"converted", "interested", "callback", "not_interested", "no_answer"}
OLD_MANUAL = {"connected", "not_picked", "busy", "wrong_number", "interested", "not_interested", "callback"}
OLD_LEAD = {"new", "in_progress", "callback", "converted", "not_interested", "dnc", "unreachable"}


def check_values(sql: str, name: str) -> set[str]:
    match = re.search(rf"ADD CONSTRAINT {name} CHECK \((.*?)\);", sql, re.S)
    assert match, f"{name} not found"
    return set(re.findall(r"'([a-z_]+)'", match.group(1)))


class Migration208Tests(unittest.TestCase):
    sql = (ROOT / "supabase/migrations/208_call_wrapup_v2_widen.sql").read_text(encoding="utf-8")

    def test_outcome_check_is_old_union_new(self):
        self.assertEqual(check_values(self.sql, "call_logs_outcome_check"), OLD_OUTCOMES | set(cw.OUTCOMES))

    def test_manual_status_check_is_old_union_new(self):
        self.assertEqual(check_values(self.sql, "call_logs_manual_status_check"), OLD_MANUAL | set(cw.CONNECTS))

    def test_lead_call_status_check_is_old_union_new(self):
        self.assertEqual(check_values(self.sql, "leads_call_status_check"), OLD_LEAD | set(cw.LEAD_CALL_STATUSES))

    def test_new_columns_and_their_checks(self):
        for col in ("outcome_reason text", "preferred_language text", "next_action_at timestamptz", "ai_call_status text"):
            self.assertIn(f"ADD COLUMN IF NOT EXISTS {col}", self.sql)
        self.assertEqual(check_values(self.sql, "call_logs_outcome_reason_check"), set(cw.REASONS))
        self.assertEqual(check_values(self.sql, "call_logs_preferred_language_check"), set(cw.LANGUAGES))
        self.assertEqual(check_values(self.sql, "call_logs_ai_call_status_check"), set(cw.AI_CALL_STATUSES))

    def test_safe_before_deploy(self):
        self.assertNotIn("DROP COLUMN", self.sql.upper())
        self.assertNotIn("UPDATE ", self.sql.upper())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_wrapup_v2_migrations.py -v`
Expected: FAIL with `FileNotFoundError ... 208_call_wrapup_v2_widen.sql`.

- [ ] **Step 4: Write the migration**

```sql
-- 208_call_wrapup_v2_widen.sql
-- Call wrap-up v2, step 1 of 2. Safe to apply BEFORE the new code deploys:
-- adds the new call_logs columns and widens the three check constraints to
-- old ∪ new values, so the old code (live until deploy) and the new code can
-- both write. 209_call_wrapup_v2_narrow.sql maps old rows and narrows the
-- checks AFTER the deploy.

ALTER TABLE public.call_logs
  ADD COLUMN IF NOT EXISTS outcome_reason text,
  ADD COLUMN IF NOT EXISTS preferred_language text,
  ADD COLUMN IF NOT EXISTS next_action_at timestamptz,
  ADD COLUMN IF NOT EXISTS ai_call_status text;

ALTER TABLE public.call_logs DROP CONSTRAINT IF EXISTS call_logs_outcome_reason_check;
ALTER TABLE public.call_logs ADD CONSTRAINT call_logs_outcome_reason_check CHECK (
  outcome_reason IS NULL OR outcome_reason IN (
    'price', 'already_bought', 'no_need', 'other',
    'never_enquired', 'not_a_fit', 'not_decision_maker'));

ALTER TABLE public.call_logs DROP CONSTRAINT IF EXISTS call_logs_preferred_language_check;
ALTER TABLE public.call_logs ADD CONSTRAINT call_logs_preferred_language_check CHECK (
  preferred_language IS NULL OR preferred_language IN (
    'tamil', 'english', 'hindi', 'telugu', 'malayalam', 'kannada', 'other'));

ALTER TABLE public.call_logs DROP CONSTRAINT IF EXISTS call_logs_ai_call_status_check;
ALTER TABLE public.call_logs ADD CONSTRAINT call_logs_ai_call_status_check CHECK (
  ai_call_status IS NULL OR ai_call_status IN ('hot', 'warm', 'cold', 'none'));

ALTER TABLE public.call_logs DROP CONSTRAINT IF EXISTS call_logs_outcome_check;
ALTER TABLE public.call_logs ADD CONSTRAINT call_logs_outcome_check CHECK (
  outcome IS NULL OR outcome IN (
    'converted', 'interested', 'callback', 'not_interested', 'no_answer',
    'interested_booked', 'interested_needs_time', 'maybe_later', 'call_later',
    'disqualified', 'wrong_number', 'language_barrier', 'do_not_call'));

ALTER TABLE public.call_logs DROP CONSTRAINT IF EXISTS call_logs_manual_status_check;
ALTER TABLE public.call_logs ADD CONSTRAINT call_logs_manual_status_check CHECK (
  manual_status IS NULL OR manual_status IN (
    'connected', 'not_picked', 'busy', 'wrong_number', 'interested', 'not_interested', 'callback',
    'switched_off'));

ALTER TABLE public.leads DROP CONSTRAINT IF EXISTS leads_call_status_check;
ALTER TABLE public.leads ADD CONSTRAINT leads_call_status_check CHECK (
  call_status IN (
    'new', 'in_progress', 'callback', 'converted', 'not_interested', 'dnc', 'unreachable',
    'trying', 'hot', 'warm', 'cold', 'disqualified', 'wrong_number', 'language_barrier'));
```

- [ ] **Step 5: Run test to verify it passes**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_wrapup_v2_migrations.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/supabase/migrations/208_call_wrapup_v2_widen.sql backend/tests/test_wrapup_v2_migrations.py
git commit -m "feat(db): 208 widen call wrap-up checks and add v2 columns (pre-deploy)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/supabase/migrations/208_call_wrapup_v2_widen.sql backend/tests/test_wrapup_v2_migrations.py
```

- [ ] **Step 7 (controller hand-off):** Apply via Supabase MCP `apply_migration` (name `208_call_wrapup_v2_widen`) **before** the deploy. Then verify with the Step 1 query that the three checks show the widened sets and the four columns exist.

---

### Task 3: "Reassign to a {language} speaker" alert

**Files:**
- Modify: `backend/app/services/call_alerts.py` (imports + new function after `raise_alert`)
- Test: `backend/tests/test_reassign_alert.py`

**Interfaces:**
- Consumes: `raise_alert` (existing), `call_wrapup.LANGUAGE_LABEL`.
- Produces: `raise_reassign_alert(db, *, tenant_id: str, call_log_id: str, caller_id: str | None, language: str) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_reassign_alert.py
"""Language barrier wrap-up -> one Needs-attention row that names the language, even if the AI raised one first."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_alerts as ca


class ReassignAlertTests(unittest.TestCase):
    def test_new_alert_names_the_language(self):
        db = MagicMock()
        with patch.object(ca, "raise_alert", return_value=True) as raise_alert:
            ca.raise_reassign_alert(db, tenant_id="t1", call_log_id="call-1", caller_id="c1", language="tamil")
        raise_alert.assert_called_once_with(
            db, tenant_id="t1", type="language_barrier", call_log_id="call-1", caller_id="c1",
            quote="Reassign to a Tamil speaker", detail={"preferred_language": "tamil", "source": "wrapup"},
        )
        db.table.assert_not_called()

    def test_existing_ai_alert_is_rewritten_and_shown_again(self):
        db = MagicMock()
        with patch.object(ca, "raise_alert", return_value=False):
            ca.raise_reassign_alert(db, tenant_id="t1", call_log_id="call-1", caller_id="c1", language="hindi")
        db.table.assert_called_with("call_alerts")
        self.assertEqual(db.table.return_value.update.call_args.args[0], {
            "quote": "Reassign to a Hindi speaker",
            "detail": {"preferred_language": "hindi", "source": "wrapup"},
            "seen_at": None, "seen_by": None,
        })

    def test_other_language_wording(self):
        db = MagicMock()
        with patch.object(ca, "raise_alert", return_value=True) as raise_alert:
            ca.raise_reassign_alert(db, tenant_id="t1", call_log_id="call-1", caller_id=None, language="other")
        self.assertEqual(raise_alert.call_args.kwargs["quote"], "Reassign to someone who speaks the customer's language")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_reassign_alert.py -v`
Expected: FAIL with `AttributeError: module 'app.services.call_alerts' has no attribute 'raise_reassign_alert'`.

- [ ] **Step 3: Implement.**

In `backend/app/services/call_alerts.py`, add after `from app.services.notify import notify_user`:

```python
from app.services.call_wrapup import LANGUAGE_LABEL
```

Add directly after the `raise_alert` function:

```python
def raise_reassign_alert(db, *, tenant_id: str, call_log_id: str, caller_id: str | None, language: str) -> None:
    """A 'Language barrier' wrap-up. Alerts are deduped per call+type, so if the AI already raised a
    language_barrier alert for this call, that row is rewritten with the language and shown again."""
    quote = (
        "Reassign to someone who speaks the customer's language" if language == "other"
        else f"Reassign to a {LANGUAGE_LABEL[language]} speaker"
    )
    detail = {"preferred_language": language, "source": "wrapup"}
    if raise_alert(db, tenant_id=tenant_id, type="language_barrier", call_log_id=call_log_id,
                   caller_id=caller_id, quote=quote, detail=detail):
        return
    (
        db.table("call_alerts")
        .update({"quote": quote, "detail": detail, "seen_at": None, "seen_by": None})
        .eq("call_log_id", call_log_id).eq("type", "language_barrier").eq("tenant_id", tenant_id)
        .execute()
    )
```

- [ ] **Step 4: Run tests**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_reassign_alert.py tests/test_call_alerts.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/call_alerts.py backend/tests/test_reassign_alert.py
git commit -m "feat(calls): reassign-to-language alert for language barrier wrap-ups" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/app/services/call_alerts.py backend/tests/test_reassign_alert.py
```

---

### Task 4: Apply a saved wrap-up (all database effects)

**Files:**
- Create: `backend/app/services/wrapup_apply.py`
- Test: `backend/tests/test_wrapup_apply.py`

**Interfaces:**
- Consumes:
  - Task 1 helpers: `NO_CONNECTS`, `REMINDER_OUTCOMES`, `STOP_ALL_FOLLOW_UPS`, `CLOSED_LEAD_STATUSES`, `consecutive_no_connects`, `is_no_connect`, `lead_status_after`, `reminder_note`, `sale_lines`, `suggest_retry_at`.
  - Task 3: `raise_reassign_alert`.
  - Existing:
    - `deals.create_deal(tenant_id, lead_id, lines, source, stage, *, payment_method, notes, created_by, db) -> {"deal": {...}}` (raises `DealError`)
    - `growth.sync_follow_up_jobs`, `cancel_pending_follow_ups`, `record_stage_event`
    - `assignment.get_telecalling_config`, `maybe_assign_lead(lead_id, tenant_id, segment, channel, *, reason)`
- Produces: `async apply_wrapup(db, *, tenant_id, user_id, caller_id, call_log_id, log: dict, wrapup: dict, log_extra: dict, now: datetime) -> {"call_status": str | None, "next_action_at": str | None, "deal_id": str | None}`.
  - `wrapup` keys: `manual_status`, `outcome`, `notes`, `next_action_at` (aware datetime | None), `reason`, `preferred_language`, `stop_messages`, `products` (list of `{catalog_item_id, qty}`), `amount_paise`.
  - `log` keys: `provider`, `status`, `lead_id`, `follow_up_job_id`, `outcome`, `caller_id`.
  - Raises `DealError` before writing anything.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_wrapup_apply.py
"""Wrap-up v2 writes: call row, lead status, reminders, the sale, DNC and the reassign alert."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import wrapup_apply as wa
from app.services.deals import DealError
from tests.fake_supabase import FakeSupabase

UTC = timezone.utc
NOW = datetime(2026, 9, 27, 8, 30, tzinfo=UTC)  # 14:00 IST
TOMORROW_10_IST = "2026-09-28T04:30:00+00:00"


class ApplyWrapupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = FakeSupabase()
        self.db.add("leads", id="lead-1", tenant_id="t1", segment="B", phone="+919800000001", ai_enabled=True,
                    converted_at=None, assigned_to="caller-1", call_status="trying", do_not_call=False, opted_out=False)
        self.db.add("call_logs", id="call-1", tenant_id="t1", lead_id="lead-1", provider="telecmi", status="completed",
                    duration_seconds=120, caller_id="caller-1", follow_up_job_id=None, outcome=None, manual_status=None,
                    created_at="2026-09-27T08:00:00+00:00")
        self.mocks = {}
        for name, mock in {
            "sync_follow_up_jobs": MagicMock(), "cancel_pending_follow_ups": MagicMock(),
            "record_stage_event": MagicMock(), "maybe_assign_lead": MagicMock(),
            "get_telecalling_config": MagicMock(return_value={"max_call_attempts": 4}),
            "create_deal": AsyncMock(return_value={"deal": {"id": "deal-1"}}),
            "raise_reassign_alert": MagicMock(),
        }.items():
            patcher = patch.object(wa, name, mock)
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)

    async def run_wrapup(self, log_patch=None, log_extra=None, **wrapup):
        body = {"manual_status": "connected", "outcome": None, "notes": None, "next_action_at": None, "reason": None,
                "preferred_language": None, "stop_messages": False, "products": [], "amount_paise": None}
        body.update(wrapup)
        log = {**self.call(), **(log_patch or {})}
        return await wa.apply_wrapup(self.db, tenant_id="t1", user_id="user-1", caller_id="caller-1",
                                     call_log_id="call-1", log=log, wrapup=body, log_extra=log_extra or {}, now=NOW)

    def call(self):
        return next(r for r in self.db.rows("call_logs") if r["id"] == "call-1")

    def lead(self):
        return self.db.rows("leads")[0]

    def reminders(self):
        return [r for r in self.db.rows("follow_up_jobs") if r.get("channel") == "phone" and r.get("status") == "pending"]

    def earlier_call(self, created_at, **kw):
        self.db.add("call_logs", tenant_id="t1", lead_id="lead-1", created_at=created_at, **{"status": "completed", **kw})

    # ── didn't connect ─────────────────────────────────────────────
    async def test_not_picked_sets_trying_and_a_two_hour_retry(self):
        out = await self.run_wrapup(manual_status="not_picked")
        self.assertEqual(self.lead()["call_status"], "trying")
        self.assertEqual((self.call()["manual_status"], self.call()["outcome"]), ("not_picked", None))
        self.assertEqual(self.call()["next_action_at"], "2026-09-27T10:30:00+00:00")
        [reminder] = self.reminders()
        self.assertEqual(reminder["scheduled_for"], "2026-09-27T10:30:00+00:00")
        self.assertEqual((reminder["cadence"], reminder["message_preview"]), ("callback", "Retry: Not picked"))
        self.assertEqual(reminder["scheduled_by_caller_id"], "caller-1")
        self.assertEqual(out["next_action_at"], "2026-09-27T10:30:00+00:00")
        self.mocks["sync_follow_up_jobs"].assert_called_once()

    async def test_third_failure_in_a_row_retries_tomorrow_10am(self):
        self.earlier_call("2026-09-27T06:00:00+00:00", manual_status="busy")
        self.earlier_call("2026-09-27T05:00:00+00:00", manual_status="not_picked")
        await self.run_wrapup(manual_status="not_picked")
        self.assertEqual(self.reminders()[0]["scheduled_for"], TOMORROW_10_IST)

    async def test_telecallers_time_wins_over_the_suggestion(self):
        chosen = datetime(2026, 9, 27, 12, 30, tzinfo=UTC)
        await self.run_wrapup(manual_status="busy", next_action_at=chosen)
        self.assertEqual(self.reminders()[0]["scheduled_for"], chosen.isoformat())

    async def test_reaching_max_attempts_makes_the_lead_unreachable(self):
        self.mocks["get_telecalling_config"].return_value = {"max_call_attempts": 2}
        self.lead()["assigned_to"] = None
        self.earlier_call("2026-09-26T05:00:00+00:00", manual_status="not_picked")
        out = await self.run_wrapup(manual_status="switched_off")
        self.assertEqual(out["call_status"], "unreachable")
        self.mocks["maybe_assign_lead"].assert_not_called()

    # ── connected ──────────────────────────────────────────────────
    async def test_interested_booked_is_hot_with_a_reminder_and_stage_event(self):
        at = datetime(2026, 10, 2, 5, 30, tzinfo=UTC)
        await self.run_wrapup(outcome="interested_booked", next_action_at=at, notes="Demo booked")
        self.assertEqual(self.lead()["call_status"], "hot")
        [reminder] = self.reminders()
        self.assertEqual(reminder["scheduled_for"], at.isoformat())
        self.assertEqual(reminder["message_preview"], "Interested, next step booked — Demo booked")
        self.assertEqual(self.call()["notes"], "Demo booked")
        event = self.mocks["record_stage_event"].call_args
        self.assertEqual(event.kwargs["event_type"], "call_outcome")
        self.assertEqual(event.kwargs["metadata"]["outcome"], "interested_booked")

    async def test_needs_time_is_warm(self):
        await self.run_wrapup(outcome="interested_needs_time", next_action_at=datetime(2026, 9, 29, 5, 0, tzinfo=UTC), notes="x")
        self.assertEqual(self.lead()["call_status"], "warm")

    async def test_maybe_later_without_a_date_is_cold_with_no_reminder(self):
        await self.run_wrapup(outcome="maybe_later")
        self.assertEqual(self.lead()["call_status"], "cold")
        self.assertEqual(self.reminders(), [])
        self.assertIsNone(self.call()["next_action_at"])

    async def test_call_later_is_callback(self):
        await self.run_wrapup(outcome="call_later", next_action_at=datetime(2026, 9, 27, 12, 30, tzinfo=UTC))
        self.assertEqual(self.lead()["call_status"], "callback")
        self.assertEqual(len(self.reminders()), 1)

    async def test_converted_creates_a_won_call_deal_from_products(self):
        self.lead()["assigned_to"] = None
        out = await self.run_wrapup(outcome="converted", notes="Paid by UPI", products=[{"catalog_item_id": "item-1", "qty": 2}])
        self.mocks["create_deal"].assert_awaited_once_with(
            "t1", "lead-1", [{"catalog_item_id": "item-1", "qty": 2}], "call", "won",
            payment_method="other", notes="Paid by UPI", created_by="user-1", db=self.db,
        )
        self.assertEqual(out["deal_id"], "deal-1")
        self.assertEqual((self.lead()["call_status"], self.lead()["converted_at"]), ("converted", NOW.isoformat()))
        self.assertEqual(self.lead()["conversion_notes"], "Paid by UPI")
        self.assertEqual(self.mocks["record_stage_event"].call_args.kwargs["event_type"], "converted")
        self.mocks["maybe_assign_lead"].assert_not_called()

    async def test_converted_with_an_amount(self):
        await self.run_wrapup(outcome="converted", notes="cash", amount_paise=150000)
        self.assertEqual(self.mocks["create_deal"].await_args.args[2],
                         [{"name": "Sale on call", "qty": 1, "unit_price_paise": 150000}])

    async def test_resubmitted_conversion_does_not_create_a_second_deal(self):
        await self.run_wrapup(log_patch={"outcome": "converted"}, outcome="converted", notes="cash", amount_paise=150000)
        self.mocks["create_deal"].assert_not_awaited()

    async def test_a_failed_deal_writes_nothing(self):
        self.mocks["create_deal"].side_effect = DealError("No price for Pen")
        with self.assertRaises(DealError):
            await self.run_wrapup(outcome="converted", notes="x", products=[{"catalog_item_id": "pen", "qty": 1}])
        self.assertIsNone(self.call()["manual_status"])
        self.assertEqual(self.lead()["call_status"], "trying")

    async def test_not_interested_and_disqualified_save_the_reason(self):
        await self.run_wrapup(outcome="not_interested", reason="price")
        self.assertEqual((self.lead()["call_status"], self.call()["outcome_reason"]), ("not_interested", "price"))
        self.mocks["sync_follow_up_jobs"].assert_called_once()
        await self.run_wrapup(outcome="disqualified", reason="never_enquired")
        self.assertEqual((self.lead()["call_status"], self.call()["outcome_reason"]), ("disqualified", "never_enquired"))

    async def test_reason_and_language_are_only_kept_for_their_options(self):
        await self.run_wrapup(outcome="maybe_later", reason="price", preferred_language="tamil")
        self.assertEqual((self.call()["outcome_reason"], self.call()["preferred_language"]), (None, None))

    async def test_wrong_number_blocks_calls_and_cancels_every_follow_up(self):
        await self.run_wrapup(outcome="wrong_number")
        self.assertEqual((self.lead()["call_status"], self.lead()["do_not_call"]), ("wrong_number", True))
        self.mocks["cancel_pending_follow_ups"].assert_called_once_with("lead-1", reason="dnc_wrong_number", db=self.db)
        self.mocks["sync_follow_up_jobs"].assert_not_called()

    async def test_do_not_call_optionally_stops_messages(self):
        await self.run_wrapup(outcome="do_not_call")
        self.assertEqual((self.lead()["call_status"], self.lead()["do_not_call"], self.lead()["opted_out"]), ("dnc", True, False))
        await self.run_wrapup(outcome="do_not_call", stop_messages=True)
        self.assertTrue(self.lead()["opted_out"])

    async def test_language_barrier_saves_the_language_and_alerts(self):
        await self.run_wrapup(outcome="language_barrier", preferred_language="tamil")
        self.assertEqual((self.lead()["call_status"], self.call()["preferred_language"]), ("language_barrier", "tamil"))
        self.mocks["raise_reassign_alert"].assert_called_once_with(
            self.db, tenant_id="t1", call_log_id="call-1", caller_id="caller-1", language="tamil",
        )

    async def test_a_failing_alert_never_fails_the_wrapup(self):
        self.mocks["raise_reassign_alert"].side_effect = RuntimeError("insert failed")
        out = await self.run_wrapup(outcome="language_barrier", preferred_language="hindi")
        self.assertEqual(out["call_status"], "language_barrier")

    async def test_the_linked_scheduled_call_is_closed(self):
        self.db.add("follow_up_jobs", id="job-1", tenant_id="t1", lead_id="lead-1", channel="phone", cadence="callback", status="pending")
        await self.run_wrapup(log_patch={"follow_up_job_id": "job-1"}, outcome="maybe_later")
        job = next(r for r in self.db.rows("follow_up_jobs") if r["id"] == "job-1")
        self.assertEqual(job["status"], "sent")

    async def test_the_linked_scheduled_call_is_canceled_on_dnc(self):
        self.db.add("follow_up_jobs", id="job-1", tenant_id="t1", lead_id="lead-1", channel="phone", cadence="callback", status="pending")
        await self.run_wrapup(log_patch={"follow_up_job_id": "job-1"}, outcome="do_not_call")
        job = next(r for r in self.db.rows("follow_up_jobs") if r["id"] == "job-1")
        self.assertEqual((job["status"], job["skip_reason"]), ("canceled", "dnc_do_not_call"))

    async def test_an_unassigned_open_lead_is_offered_for_assignment(self):
        self.lead()["assigned_to"] = None
        await self.run_wrapup(outcome="interested_needs_time", next_action_at=datetime(2026, 9, 29, 5, 0, tzinfo=UTC), notes="x")
        self.mocks["maybe_assign_lead"].assert_called_once_with("lead-1", "t1", "B", None, reason="call_interested_needs_time")

    async def test_sim_rows_are_completed_manually_with_typed_timing(self):
        await self.run_wrapup(log_patch={"provider": "sim_basic"}, log_extra={"duration_seconds": 95}, outcome="maybe_later")
        self.assertEqual((self.call()["status"], self.call()["feedback_source"], self.call()["duration_seconds"]),
                         ("completed", "manual", 95))
        self.assertEqual(self.call()["feedback_at"], NOW.isoformat())

    async def test_a_call_without_a_lead_still_saves(self):
        out = await self.run_wrapup(log_patch={"lead_id": None}, manual_status="busy")
        self.assertIsNone(out["call_status"])
        self.assertEqual(self.call()["manual_status"], "busy")
        self.assertEqual(self.reminders(), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_wrapup_apply.py -v`
Expected: collection error: `cannot import name 'wrapup_apply'`.

- [ ] **Step 3: Implement**

```python
# backend/app/services/wrapup_apply.py
"""Writes one saved call wrap-up (v2): the call row, the lead, reminders, the sale and the
reassign alert. The rules themselves live in services/call_wrapup.py."""
import logging
from datetime import datetime

from app.services.assignment import get_telecalling_config, maybe_assign_lead
from app.services.call_alerts import raise_reassign_alert
from app.services.call_wrapup import (
    CLOSED_LEAD_STATUSES, NO_CONNECTS, REMINDER_OUTCOMES, STOP_ALL_FOLLOW_UPS,
    consecutive_no_connects, is_no_connect, lead_status_after, reminder_note, sale_lines, suggest_retry_at,
)
from app.services.deals import create_deal
from app.services.growth import cancel_pending_follow_ups, record_stage_event, sync_follow_up_jobs

logger = logging.getLogger(__name__)
LEAD_HISTORY_LIMIT = 50


def _earlier_calls(db, tenant_id: str, lead_id: str, call_log_id: str) -> list[dict]:
    rows = (
        db.table("call_logs").select("id,manual_status,status,created_at")
        .eq("lead_id", lead_id).eq("tenant_id", tenant_id)
        .order("created_at", desc=True).limit(LEAD_HISTORY_LIMIT).execute()
    ).data or []
    return [r for r in rows if r["id"] != call_log_id]


async def apply_wrapup(
    db, *, tenant_id: str, user_id: str | None, caller_id: str | None, call_log_id: str,
    log: dict, wrapup: dict, log_extra: dict, now: datetime,
) -> dict:
    manual_status = wrapup["manual_status"]
    outcome = wrapup.get("outcome")
    notes = (wrapup.get("notes") or "").strip() or None
    lead_id = log.get("lead_id")
    earlier = _earlier_calls(db, tenant_id, lead_id, call_log_id) if lead_id else []

    next_at = wrapup.get("next_action_at")
    if manual_status in NO_CONNECTS:
        next_at = next_at or suggest_retry_at(manual_status, consecutive_no_connects(earlier), now)
    elif outcome not in REMINDER_OUTCOMES:
        next_at = None

    # The sale first: if the deal can't be created (unknown product, no price) nothing is written.
    deal_id = None
    if outcome == "converted" and lead_id and log.get("outcome") != "converted":
        result = await create_deal(
            tenant_id, lead_id, sale_lines(wrapup.get("products") or [], wrapup.get("amount_paise")), "call", "won",
            payment_method="other", notes=notes, created_by=user_id, db=db,
        )
        deal_id = result["deal"]["id"]

    log_updates = {
        **log_extra,
        "manual_status": manual_status,
        "outcome": outcome,
        "outcome_reason": wrapup.get("reason") if outcome in ("not_interested", "disqualified") else None,
        "preferred_language": wrapup.get("preferred_language") if outcome == "language_barrier" else None,
        "next_action_at": next_at.isoformat() if next_at else None,
        "feedback_at": now.isoformat(),
    }
    if notes:
        log_updates["notes"] = notes
    if log.get("provider") == "sim_basic":
        log_updates["feedback_source"] = "manual"
        log_updates["status"] = "completed"
    db.table("call_logs").update(log_updates).eq("id", call_log_id).eq("tenant_id", tenant_id).execute()

    summary = {"call_status": None, "next_action_at": log_updates["next_action_at"], "deal_id": deal_id}
    if not lead_id:
        return summary
    rows = (
        db.table("leads").select("segment,phone,ai_enabled,converted_at,assigned_to")
        .eq("id", lead_id).eq("tenant_id", tenant_id).limit(1).execute()
    ).data or []
    if not rows:
        return summary
    lead = rows[0]

    no_connects_total = sum(1 for r in earlier if is_no_connect(r)) + (1 if manual_status in NO_CONNECTS else 0)
    max_attempts = get_telecalling_config(tenant_id).get("max_call_attempts", 4)
    status = lead_status_after(manual_status, outcome, no_connects_total, max_attempts)
    lead_updates: dict = {"call_status": status}
    if outcome == "converted":
        lead_updates["converted_at"] = now.isoformat()
        if notes:
            lead_updates["conversion_notes"] = notes
    if outcome in STOP_ALL_FOLLOW_UPS:
        lead_updates["do_not_call"] = True
    if outcome == "do_not_call" and wrapup.get("stop_messages"):
        lead_updates["opted_out"] = True
    updated = db.table("leads").update(lead_updates).eq("id", lead_id).eq("tenant_id", tenant_id).execute().data or []
    lead_after = {**lead, **(updated[0] if updated else lead_updates)}
    summary["call_status"] = status

    record_stage_event(
        lead_id, from_segment=lead.get("segment"), to_segment=lead_after.get("segment"),
        event_type="converted" if outcome == "converted" else "call_outcome",
        metadata={
            "outcome": outcome, "manual_status": manual_status, "call_status": status,
            "reason": log_updates["outcome_reason"], "preferred_language": log_updates["preferred_language"],
            "deal_id": deal_id,
        },
        tenant_id=tenant_id, db=db,
    )

    tag = f"call_{outcome or manual_status}"
    stop_all = outcome in STOP_ALL_FOLLOW_UPS
    if stop_all:
        cancel_pending_follow_ups(lead_id, reason=f"dnc_{outcome}", db=db)
    else:
        # Re-plans the WhatsApp follow-ups and cancels every other pending reminder for the lead.
        sync_follow_up_jobs(
            lead_id, segment=lead_after.get("segment"), phone=lead_after.get("phone"),
            converted_at=lead_after.get("converted_at"), ai_enabled=lead_after.get("ai_enabled", True),
            reason=tag, tenant_id=tenant_id, db=db,
        )

    linked = log.get("follow_up_job_id")
    if linked:
        db.table("follow_up_jobs").update({
            "status": "canceled" if stop_all else "sent",
            "sent_at": None if stop_all else now.isoformat(),
            "skip_reason": f"dnc_{outcome}" if stop_all else None,
        }).eq("id", linked).eq("tenant_id", tenant_id).execute()

    if next_at:
        db.table("follow_up_jobs").insert({
            "lead_id": lead_id, "tenant_id": tenant_id, "channel": "phone", "cadence": "callback",
            "status": "pending", "scheduled_for": next_at.isoformat(),
            "message_preview": reminder_note(manual_status, outcome, notes),
            "scheduled_by_caller_id": caller_id,
        }).execute()

    if status not in CLOSED_LEAD_STATUSES and not lead.get("assigned_to"):
        maybe_assign_lead(lead_id, tenant_id, lead_after.get("segment"), None, reason=tag)

    if outcome == "language_barrier":
        try:
            raise_reassign_alert(db, tenant_id=tenant_id, call_log_id=call_log_id,
                                 caller_id=log.get("caller_id") or caller_id, language=wrapup["preferred_language"])
        except Exception as e:
            logger.error(f"reassign alert failed for call {call_log_id}: {e}")
    return summary
```

- [ ] **Step 4: Run test to verify it passes**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_wrapup_apply.py -v`
Expected: 24 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/wrapup_apply.py backend/tests/test_wrapup_apply.py
git commit -m "feat(calls): apply wrap-up v2 effects (lead status, reminders, deal, DNC, alert)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/app/services/wrapup_apply.py backend/tests/test_wrapup_apply.py
```

---

### Task 5: Calls routes — new wrap-up endpoint, wrap-up context, CDR/SIM/dial clean-up

**Files:**
- Modify: `backend/app/routes/calls.py` (imports lines 17-25; constants 32-75; `OutcomeUpdate` 127-136; CDR 512-574; `_sim_status_from_type` 672-681; `_ingest_sim_call` 862-936; set_outcome 1023-1272; pending 1597-1615; dial `in_progress` writes at 277, 318, 543, 884; new `/wrapup-context` route)
- Create: `backend/tests/test_call_wrapup_routes.py`
- Modify tests:
  - `backend/tests/test_calls_scoring_routes.py`: delete `OutcomeGateTests` and `WrapupCrmCheckTests`.
  - `backend/tests/test_telecmi_cdr_legs.py`: line 209.
  - `backend/tests/test_sim_cdr_static.py`
  - `backend/tests/test_sim_manual_status_static.py`
  - `backend/tests/test_call_feedback_gate.py`: new class.
  - `backend/tests/test_calls_recent.py`: fixture value.

**Interfaces:**
- Consumes: Task 1 (`WrapupError`, `as_aware`, `cloud_never_connected`, `consecutive_no_connects`, `validate_wrapup`, `wrapup_context`), Task 4 (`apply_wrapup`), `deals.DealError`.
- Produces:
  - `PATCH /api/v1/calls/{id}/outcome`.
    - Body `WrapupIn`: `manual_status`, `outcome?`, `notes?`, `next_action_at?`, `reason?`, `preferred_language?`, `stop_messages`, `products[{catalog_item_id, qty}]`, `amount_paise?`, `manual_started_at?`, `manual_ended_at?`, `duration_seconds?`.
    - Response: `{call_log_id, manual_status, outcome, call_status, next_action_at, deal_id, score, score_status}`.
  - `GET /api/v1/calls/wrapup-context?lead_id=&call_log_id=` → `{connect_prefill, never_connected, failed_before, retry_suggestions}`.
  - Module aliases `ConnectValue`, `OutcomeValue`, `ReasonValue`, `LanguageValue`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_call_wrapup_routes.py
"""PATCH /calls/{id}/outcome (wrap-up v2) and GET /calls/wrapup-context."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.routes import calls
from app.services import call_wrapup as cw
from app.services.deals import DealError
from tests.fake_supabase import FakeSupabase

CALL_ID = "11111111-2222-3333-4444-555555555555"
LEAD_ID = "99999999-8888-7777-6666-555555555555"
WARM = {"manual_status": "connected", "outcome": "interested_needs_time", "notes": "wants the brochure",
        "next_action_at": "2030-01-06T10:00:00+05:30"}
CLOUD = {"provider": "telecmi", "status": "completed", "duration_seconds": 240, "lead_id": None, "caller_id": "caller-1"}
SIM = {"provider": "sim_basic", "status": "sim_started", "duration_seconds": None, "lead_id": None, "caller_id": "caller-1"}


def _log_db(row):
    db = MagicMock()
    chain = db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value
    chain.execute.return_value = MagicMock(data=row)
    return db


class _Base(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "caller", "user_id": "user-1", "caller_id": "caller-1",
            "permissions": ["telecalling.dialer"],
        }

    def tearDown(self):
        app.dependency_overrides.clear()


class SaveWrapupTests(_Base):
    def _save(self, row, body, apply=None):
        apply = apply or AsyncMock(return_value={"call_status": "warm", "next_action_at": "2030-01-06T04:30:00+00:00", "deal_id": None})
        crm_task = AsyncMock()
        with patch("app.routes.calls.get_supabase", return_value=_log_db(row)), \
             patch("app.routes.calls.apply_wrapup", apply), \
             patch("app.routes.calls.mark_crm_update_task", crm_task), \
             patch("app.routes.calls.finalize_call_score", return_value={"score": 72.5, "score_status": "provisional"}):
            res = self.client.patch(f"/api/v1/calls/{CALL_ID}/outcome", json=body)
        return res, apply, crm_task

    def test_never_connected_cloud_call_cannot_be_marked_connected(self):
        res, apply, _ = self._save({**CLOUD, "status": "no_answer", "duration_seconds": 0}, WARM)
        self.assertEqual(res.status_code, 400)
        self.assertIn("never connected", res.json()["detail"])
        apply.assert_not_awaited()

    def test_zero_second_completed_call_is_blocked_too(self):
        res, _, _ = self._save({**CLOUD, "duration_seconds": 0}, WARM)
        self.assertEqual(res.status_code, 400)

    def test_never_connected_call_saves_not_picked(self):
        res, apply, _ = self._save({**CLOUD, "status": "no_answer", "duration_seconds": 0}, {"manual_status": "not_picked"})
        self.assertEqual(res.status_code, 200)
        wrapup = apply.await_args.kwargs["wrapup"]
        self.assertEqual((wrapup["manual_status"], wrapup["outcome"], wrapup["next_action_at"]), ("not_picked", None, None))

    def test_telecmi_talk_time_is_never_overridden(self):
        _, apply, _ = self._save(CLOUD, {**WARM, "duration_seconds": 10})
        self.assertEqual(apply.await_args.kwargs["log_extra"], {})

    def test_sim_keeps_typed_timing(self):
        body = {**WARM, "duration_seconds": 95, "manual_started_at": "2026-09-27T08:00:00+00:00",
                "manual_ended_at": "2026-09-27T08:01:35+00:00"}
        _, apply, _ = self._save(SIM, body)
        self.assertEqual(apply.await_args.kwargs["log_extra"], {
            "duration_seconds": 95, "manual_started_at": "2026-09-27T08:00:00+00:00",
            "manual_ended_at": "2026-09-27T08:01:35+00:00",
        })

    def test_naive_time_is_read_as_ist(self):
        _, apply, _ = self._save(CLOUD, {**WARM, "next_action_at": "2030-01-06T10:00:00"})
        self.assertEqual(apply.await_args.kwargs["wrapup"]["next_action_at"], datetime(2030, 1, 6, 4, 30, tzinfo=timezone.utc))

    def test_response_carries_status_reminder_and_score(self):
        res, _, _ = self._save(CLOUD, WARM)
        body = res.json()
        self.assertEqual((body["call_status"], body["next_action_at"], body["score"], body["score_status"]),
                         ("warm", "2030-01-06T04:30:00+00:00", 72.5, "provisional"))

    def test_rule_errors_are_400s(self):
        res, _, _ = self._save(CLOUD, {"manual_status": "connected", "outcome": "interested_booked", "next_action_at": "2030-01-06T10:00:00+05:30"})
        self.assertEqual((res.status_code, res.json()["detail"]), (400, "Add a short note for this result."))

    def test_deal_errors_are_400s(self):
        apply = AsyncMock(side_effect=DealError("No price for Pen"))
        res, _, _ = self._save(CLOUD, {"manual_status": "connected", "outcome": "converted", "notes": "sold",
                                       "products": [{"catalog_item_id": "pen", "qty": 1}]}, apply=apply)
        self.assertEqual((res.status_code, res.json()["detail"]), (400, "No price for Pen"))

    def test_old_payload_shape_is_rejected(self):
        res, _, _ = self._save(CLOUD, {"outcome": "interested"})
        self.assertEqual(res.status_code, 422)

    def test_unknown_call_is_404(self):
        res, _, _ = self._save(None, WARM)
        self.assertEqual(res.status_code, 404)

    def test_cloud_wrapup_queues_the_crm_check(self):
        _, _, crm_task = self._save(CLOUD, WARM)
        crm_task.assert_awaited_once_with(CALL_ID)

    def test_sim_wrapup_does_not_queue_the_crm_check(self):
        _, _, crm_task = self._save(SIM, WARM)
        crm_task.assert_not_awaited()


class LiteralContractTests(unittest.TestCase):
    def test_route_literals_match_the_rules_module(self):
        self.assertEqual(set(get_args(calls.ConnectValue)), set(cw.CONNECTS))
        self.assertEqual(set(get_args(calls.OutcomeValue)), set(cw.OUTCOMES))
        self.assertEqual(set(get_args(calls.ReasonValue)), set(cw.REASONS))
        self.assertEqual(set(get_args(calls.LanguageValue)), set(cw.LANGUAGES))


class WrapupContextTests(_Base):
    def setUp(self):
        super().setUp()
        self.db = FakeSupabase()
        self.db.add("call_logs", id=CALL_ID, tenant_id="tenant-1", provider="telecmi", status="no_answer",
                    duration_seconds=0, lead_id=LEAD_ID, manual_status=None, created_at="2026-09-27T08:00:00+00:00")
        for created_at in ("2026-09-27T06:00:00+00:00", "2026-09-27T05:00:00+00:00"):
            self.db.add("call_logs", tenant_id="tenant-1", lead_id=LEAD_ID, manual_status="busy", status="completed", created_at=created_at)

    def _get(self, qs):
        with patch("app.routes.calls.get_supabase", return_value=self.db):
            return self.client.get(f"/api/v1/calls/wrapup-context?{qs}")

    def test_cloud_missed_call_is_prefilled_not_picked(self):
        body = self._get(f"call_log_id={CALL_ID}").json()
        self.assertEqual((body["connect_prefill"], body["never_connected"], body["failed_before"]), ("not_picked", True, 2))
        # third failure in a row: every suggestion is tomorrow 10:00 IST
        self.assertEqual(len(set(body["retry_suggestions"].values())), 1)

    def test_lead_only_context_for_a_sim_call_not_logged_yet(self):
        body = self._get(f"lead_id={LEAD_ID}").json()
        self.assertEqual((body["connect_prefill"], body["failed_before"]), (None, 0))

    def test_another_tenants_call_is_404(self):
        self.db.rows("call_logs")[0]["tenant_id"] = "other"
        self.assertEqual(self._get(f"call_log_id={CALL_ID}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
```

In `backend/tests/test_calls_scoring_routes.py`, delete the whole `class OutcomeGateTests(_Base):` block (lines 44-88) and the whole `class WrapupCrmCheckTests(unittest.IsolatedAsyncioTestCase):` block (lines 127-140). They are replaced by `SaveWrapupTests`. Update the module docstring's first line to `"""Routes around the TeleCMI call score: admin alerts, retry, winners and transcript masking."""`.

In `backend/tests/test_telecmi_cdr_legs.py` line 209 replace the expectation with:

```python
        self.assertEqual(db.updates_to("call_logs"), [{"status": "no_answer"}])
```

In `backend/tests/test_sim_cdr_static.py`:
- Replace `    assert "not pending_outcome" in source` with:

```python
    # The APK never writes an outcome: tap 2 of the wrap-up belongs to the telecaller.
    assert "pending_outcome" not in source
```

- In `test_sim_cdr_never_writes_human_owned_fields`, change the forbidden tuple to `("notes", "tags", "quality_rating", "manual_started_at", "manual_ended_at", "outcome")`.
- Replace the body of `test_sim_status_mapping_contract` after `assert "def _sim_status_from_type" in source` with:

```python
    # outgoing/incoming answered -> completed
    assert 'return "completed", "answered"' in source
    # outgoing unanswered + missed -> no_answer, and never an outcome
    assert 'return "no_answer", "no_answer"' in source
    assert '"no_answer", "no_answer", "no_answer"' not in source
```

In `backend/tests/test_sim_manual_status_static.py` replace `test_calls_route_maps_all_manual_statuses` with:

```python
def test_calls_route_uses_the_wrapup_v2_contract():
    source = _read("app/routes/calls.py")
    assert "ConnectValue = Literal" in source
    assert "_MANUAL_STATUS_TO_OUTCOME" not in source
    assert "_MANUAL_STATUS_TO_DISPOSITION" not in source
    assert "await apply_wrapup(" in source
```

Append to `backend/tests/test_call_feedback_gate.py` (end of file):

```python
class CloudPendingTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "caller", "caller_id": "caller-1", "user_id": "user-1", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.calls.get_supabase")
    def test_cloud_pending_skips_wrapped_up_calls(self, mock_get_db):
        db = FakeDb({"call_logs": []})
        mock_get_db.return_value = db
        self.client.get("/api/v1/calls/pending-wrapups")
        other_q = db.queries["call_logs"][1]
        self.assertTrue(other_q.has("eq", "status", "completed"))
        self.assertTrue(other_q.has("is_", "manual_status", "null"))
```

In `backend/tests/test_calls_recent.py` line 24 change `"outcome": "interested",` to `"outcome": "interested_needs_time",`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_call_wrapup_routes.py tests/test_telecmi_cdr_legs.py tests/test_sim_cdr_static.py tests/test_sim_manual_status_static.py tests/test_call_feedback_gate.py -v`
Expected: FAIL. `test_call_wrapup_routes` fails with `AttributeError: module 'app.routes.calls' has no attribute 'apply_wrapup'` (and others). The CDR leg-A test fails, the static tests fail, and `test_cloud_pending_skips_wrapped_up_calls` fails.

- [ ] **Step 3: Implement in `backend/app/routes/calls.py`.**

(a) Imports. Replace `from app.services.growth import record_stage_event, sync_follow_up_jobs` with:

```python
from app.services.call_wrapup import (
    WrapupError, as_aware, cloud_never_connected, consecutive_no_connects, validate_wrapup, wrapup_context,
)
from app.services.deals import DealError
from app.services.wrapup_apply import apply_wrapup
```

(b) `CALL_CARD_FIELDS`: change the line `"id,created_at,duration_seconds,status,outcome,provider,score,score_status,"` to `"id,created_at,duration_seconds,status,outcome,manual_status,next_action_at,provider,score,score_status,"`.

(c) Replace lines 42-75 (the `Outcome`, `Disposition` and `ManualStatus` literals and the three mapping dicts) with:

```python
# Wrap-up v2 (spec 2026-09-27). Kept equal to services/call_wrapup.py by test_call_wrapup_routes.
ConnectValue = Literal["connected", "not_picked", "busy", "switched_off"]
OutcomeValue = Literal[
    "interested_booked", "interested_needs_time", "maybe_later", "call_later", "converted",
    "not_interested", "disqualified", "wrong_number", "language_barrier", "do_not_call",
]
ReasonValue = Literal["price", "already_bought", "no_need", "other", "never_enquired", "not_a_fit", "not_decision_maker"]
LanguageValue = Literal["tamil", "english", "hindi", "telugu", "malayalam", "kannada", "other"]
```

(d) Replace the `OutcomeUpdate` class (lines 127-136) with:

```python
class WrapupProduct(BaseModel):
    catalog_item_id: str = Field(min_length=1, max_length=64)
    qty: int = Field(1, ge=1, le=1000)


class WrapupIn(BaseModel):
    manual_status: ConnectValue
    outcome: OutcomeValue | None = None
    notes: str | None = Field(None, max_length=2000)
    next_action_at: datetime | None = None
    reason: ReasonValue | None = None
    preferred_language: LanguageValue | None = None
    stop_messages: bool = False
    products: list[WrapupProduct] = Field(default_factory=list, max_length=20)
    amount_paise: int | None = Field(None, ge=100, le=10_000_000_000)
    manual_started_at: datetime | None = None
    manual_ended_at: datetime | None = None
    duration_seconds: int | None = Field(default=None, ge=0, le=24 * 60 * 60)
```

(e) TeleCMI CDR leg A (line ~515). Change the update to `db.table("call_logs").update({"status": "no_answer"}).eq("id", call_log_id).execute()`. For leg B's `elif status in ("missed", "no_answer"):` block, keep only `updates["status"] = "no_answer"` (delete the `updates["outcome"] = "no_answer"` line).

(f) Replace `_sim_status_from_type` with:

```python
def _sim_status_from_type(call_type: int, duration: int) -> tuple[str, str | None]:
    """Map an Android CallLog type + duration to (status, disposition). Never an outcome:
    tap 2 of the wrap-up is the telecaller's."""
    # 2 = outgoing, 1 = incoming, 3 = missed (rejected/blocked/voicemail → failed)
    if call_type in (1, 2) and duration > 0:
        return "completed", "answered"
    if call_type == 2 and duration == 0:
        return "no_answer", "no_answer"
    if call_type == 3:
        return "no_answer", "no_answer"
    return "failed", None
```

(g) In `_ingest_sim_call`:
- `status, disposition, outcome = _sim_status_from_type(...)` → `status, disposition = _sim_status_from_type(entry.call_type, entry.duration)`.
- Delete `pending_outcome = None`.
- Change `.select("id,outcome")` → `.select("id")` in the pending lookup.
- Delete `pending_outcome = pending.data[0].get("outcome")`.
- Delete the four lines starting `# Only stamp the APK-derived outcome` through `updates["outcome"] = apply_outcome`.
- In the comment above `updates`, change "It must NEVER include notes, tags, quality_rating, or manual_started_at/ended_at" to "It must NEVER include an outcome, notes, or manual_started_at/ended_at".

(h) Dial-time and auto-created leads now start as `trying`. At the four places that write `"call_status": "in_progress"` (initiate auto-create ~277, SIM initiate ~318, CDR auto-create ~543, SIM ingest auto-create ~884), change the value to `"trying"`.

(i) Replace the whole `set_outcome` function (from `@router.patch("/{call_log_id}/outcome")` to its `return {...}`) with:

```python
@router.patch("/{call_log_id}/outcome")
async def set_outcome(call_log_id: str, payload: WrapupIn, background_tasks: BackgroundTasks, ctx: dict = Depends(get_tenant_and_role)):
    """Save the two-tap wrap-up (v2). Rules: services/call_wrapup.py; writes: services/wrapup_apply.py."""
    db = get_supabase()
    log = (
        db.table("call_logs")
        .select("caller_id,duration_seconds,lead_id,follow_up_job_id,provider,status,outcome")
        .eq("id", call_log_id)
        .eq("tenant_id", ctx["tenant_id"])
        .maybe_single()
        .execute()
    )
    if not log or not log.data:
        raise HTTPException(status_code=404, detail="Call log not found")
    row = log.data
    is_telecmi = row.get("provider") == "telecmi"
    now = datetime.now(timezone.utc)
    next_at = as_aware(payload.next_action_at) if payload.next_action_at else None
    try:
        validate_wrapup(
            never_connected=is_telecmi and cloud_never_connected(row),
            manual_status=payload.manual_status, outcome=payload.outcome, notes=payload.notes,
            next_action_at=next_at, reason=payload.reason, preferred_language=payload.preferred_language,
            has_products=bool(payload.products), amount_paise=payload.amount_paise, now=now,
        )
    except WrapupError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # TeleCMI's measured talk time decides scoring; a typed-in duration must never override it.
    log_extra: dict = {}
    if not is_telecmi:
        if payload.duration_seconds is not None:
            log_extra["duration_seconds"] = payload.duration_seconds
        if payload.manual_started_at is not None:
            log_extra["manual_started_at"] = payload.manual_started_at.isoformat()
        if payload.manual_ended_at is not None:
            log_extra["manual_ended_at"] = payload.manual_ended_at.isoformat()
    wrapup = {
        "manual_status": payload.manual_status, "outcome": payload.outcome, "notes": payload.notes,
        "next_action_at": next_at, "reason": payload.reason, "preferred_language": payload.preferred_language,
        "stop_messages": payload.stop_messages, "products": [p.model_dump() for p in payload.products],
        "amount_paise": payload.amount_paise,
    }
    try:
        result = await apply_wrapup(
            db, tenant_id=ctx["tenant_id"], user_id=ctx.get("user_id"), caller_id=ctx.get("caller_id"),
            call_log_id=call_log_id, log=row, wrapup=wrapup, log_extra=log_extra, now=now,
        )
    except DealError as e:
        raise HTTPException(status_code=400, detail=str(e))

    scoring = finalize_call_score(db, call_log_id)
    if is_telecmi:
        background_tasks.add_task(mark_crm_update_task, call_log_id)
    return {
        "call_log_id": call_log_id,
        "manual_status": payload.manual_status,
        "outcome": payload.outcome,
        "call_status": result["call_status"],
        "next_action_at": result["next_action_at"],
        "deal_id": result["deal_id"],
        "score": (scoring or {}).get("score"),
        "score_status": (scoring or {}).get("score_status"),
    }
```

(j) Pending wrap-ups: in `get_pending_wrapups`, add `.is_("manual_status", "null")` to `other_q` directly after `.eq("status", "completed")`.

(k) Add the context route directly after `pending_wrapups_summary` (it must stay above `@router.get("/{call_log_id}")`):

```python
@router.get("/wrapup-context")
async def get_wrapup_context(
    lead_id: UUID | None = Query(None),
    call_log_id: UUID | None = Query(None),
    ctx: dict = Depends(get_tenant_and_role),
):
    """What the wrap-up form needs up front: the cloud pre-fill of tap 1 and the retry suggestions."""
    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    row = None
    if call_log_id:
        rows = (
            db.table("call_logs").select("id,provider,status,duration_seconds,lead_id")
            .eq("id", str(call_log_id)).eq("tenant_id", tenant_id).limit(1).execute()
        ).data or []
        if not rows:
            raise HTTPException(status_code=404, detail="Call log not found")
        row = rows[0]
    lead = str(lead_id) if lead_id else (row or {}).get("lead_id")
    failed_before = 0
    if lead:
        history = (
            db.table("call_logs").select("id,manual_status,status,created_at")
            .eq("lead_id", lead).eq("tenant_id", tenant_id)
            .order("created_at", desc=True).limit(20).execute()
        ).data or []
        current = str(call_log_id) if call_log_id else None
        failed_before = consecutive_no_connects([r for r in history if r["id"] != current])
    return wrapup_context(row, failed_before, datetime.now(timezone.utc))
```

(l) `Field` and `timedelta` are still used elsewhere in the file; keep those imports. Confirm nothing else in `calls.py` references the removed names:

`grep -nE "OutcomeUpdate|_DISPOSITION_TO_OUTCOME|_MANUAL_STATUS_TO|quality_rating|wrapup_callback_at|record_stage_event|sync_follow_up_jobs|\"in_progress\"" backend/app/routes/calls.py`

Expected: only `in_progress` hits that refer to `call_logs.status` (the telecmi live-event mapping and the `.in_("status", ["initiated", "in_progress"])` filter). Nothing else.

- [ ] **Step 4: Run tests**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_call_wrapup_routes.py tests/test_calls_scoring_routes.py tests/test_telecmi_cdr_legs.py tests/test_sim_cdr_static.py tests/test_sim_manual_status_static.py tests/test_call_feedback_gate.py tests/test_calls_recent.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/calls.py backend/tests/test_call_wrapup_routes.py backend/tests/test_calls_scoring_routes.py backend/tests/test_telecmi_cdr_legs.py backend/tests/test_sim_cdr_static.py backend/tests/test_sim_manual_status_static.py backend/tests/test_call_feedback_gate.py backend/tests/test_calls_recent.py
git commit -m "feat(calls): wrap-up v2 endpoint and wrap-up context; CDR/SIM never write outcome" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/app/routes/calls.py backend/tests/test_call_wrapup_routes.py backend/tests/test_calls_scoring_routes.py backend/tests/test_telecmi_cdr_legs.py backend/tests/test_sim_cdr_static.py backend/tests/test_sim_manual_status_static.py backend/tests/test_call_feedback_gate.py backend/tests/test_calls_recent.py
```

---

### Task 6: Check 10 on the new values + D10 AI Hot/Warm/Cold correction

**Files:**
- Modify: `backend/app/services/call_marking.py` (imports; replace everything from `# ── Check 10` to end of file)
- Modify (full rewrite): `backend/tests/test_call_crm_check.py`

**Interfaces:**
- Consumes: `call_wrapup.CONNECT_LABEL`, `LANGUAGE_LABEL`, `OUTCOME_LABEL`, `TEMPERATURES`, `TEMPERATURE_FOR_OUTCOME`, `AI_CALL_STATUSES`.
- Produces:
  - `wrapup_snapshot(db, row) -> dict | None` with keys `outcome, manual_status, reason, preferred_language, notes, next_action_at, do_not_call`.
  - `crm_matches_expected(expected, wrapup) -> bool | None`.
  - `mark_crm_update(db, call_log_id, *, now=None) -> bool`. It now also writes `call_logs.ai_call_status`, adds `evaluation.crm_correction = {"from", "to"} | None`, and updates `leads.call_status` (guarded) when the AI reading differs.

- [ ] **Step 1: Write the failing test (replace the whole file)**

```python
# backend/tests/test_call_crm_check.py
"""Check 10: marked from the wrap-up (v2 values), Missing after 2 hours, re-marked when the
wrap-up changes; D10: the AI's Hot/Warm/Cold reading corrects the lead status on cloud calls."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_marking as cm

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


def _checks(crm_level=None):
    out = []
    for c in cm.CHECKS:
        level = "good" if c["key"] != "crm_update" else crm_level
        out.append({"key": c["key"], "full": c["full"], "level": level, "marks": cm.check_marks(c["key"], level)})
    return out


def _row(**kw):
    row = {
        "id": "call-1", "tenant_id": "t", "caller_id": "c1", "lead_id": "lead-1", "provider": "telecmi",
        "call_group": "real_conversation", "ai_status": "done",
        "created_at": (NOW - timedelta(minutes=30)).isoformat(), "feedback_at": None,
        "outcome": None, "manual_status": None, "outcome_reason": None, "preferred_language": None,
        "next_action_at": None, "notes": None,
        "transcript": "[00:01] Telecaller: Hello\n[00:03] Customer: I need a demo",
        "evaluation": {"evaluation_version": 4, "group": "real_conversation", "checks": _checks(), "signs": []},
    }
    row.update(kw)
    return row


def _snap(r):
    return {
        "outcome": r.get("outcome"), "manual_status": r.get("manual_status"), "reason": r.get("outcome_reason"),
        "preferred_language": r.get("preferred_language"), "notes": r.get("notes"),
        "next_action_at": r.get("next_action_at"), "do_not_call": False,
    }


WARM = {"feedback_at": NOW.isoformat(), "manual_status": "connected", "outcome": "interested_needs_time"}


class CrmExpectedTests(unittest.TestCase):
    def test_mapping(self):
        self.assertTrue(cm.crm_matches_expected("wrong_number", {"outcome": "wrong_number"}))
        self.assertFalse(cm.crm_matches_expected("wrong_number", {"outcome": "interested_needs_time"}))
        self.assertTrue(cm.crm_matches_expected("not_enquired", {"outcome": "not_interested"}))
        self.assertTrue(cm.crm_matches_expected("not_enquired", {"outcome": "disqualified", "reason": "never_enquired"}))
        self.assertFalse(cm.crm_matches_expected("not_enquired", {"outcome": "disqualified", "reason": "not_a_fit"}))
        self.assertTrue(cm.crm_matches_expected("callback", {"outcome": "call_later", "next_action_at": "2026-09-26T05:00:00+00:00"}))
        self.assertFalse(cm.crm_matches_expected("callback", {"outcome": "call_later", "next_action_at": None}))
        self.assertTrue(cm.crm_matches_expected("language_barrier", {"outcome": "language_barrier"}))
        self.assertFalse(cm.crm_matches_expected("language_barrier", {"outcome": "not_interested"}))
        self.assertIsNone(cm.crm_matches_expected("voicemail", {"outcome": None}))
        self.assertIsNone(cm.crm_matches_expected("other", {"outcome": "maybe_later"}))

    def test_snapshot_reads_the_v2_columns(self):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data={"do_not_call": True})
        row = _row(**WARM, outcome_reason=None, next_action_at="2026-09-26T05:00:00+00:00", notes="n")
        self.assertEqual(cm.wrapup_snapshot(db, row), {
            "outcome": "interested_needs_time", "manual_status": "connected", "reason": None,
            "preferred_language": None, "notes": "n", "next_action_at": "2026-09-26T05:00:00+00:00", "do_not_call": True,
        })
        self.assertIsNone(cm.wrapup_snapshot(db, _row()))


class MarkCrmUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, row, ai=None, alert_error=None):
        db = MagicMock()
        writes = []
        db.table.return_value.update.side_effect = lambda payload: writes.append(payload) or db.table.return_value.update.return_value
        with patch.object(cm, "_load_row", return_value=row), \
             patch.object(cm, "wrapup_snapshot", side_effect=lambda db, r: None if not r.get("feedback_at") else _snap(r)), \
             patch.object(cm, "gemini_analysis_json", AsyncMock(return_value=ai or {"level": "excellent", "reason": "matches", "customer": "warm"})) as gem, \
             patch.object(cm, "raise_alert", side_effect=alert_error) as alert, \
             patch.object(cm, "finalize_call_score") as fin:
            changed = await cm.mark_crm_update(db, "call-1", now=NOW)
        return changed, writes, gem, alert, fin, db

    async def test_no_wrapup_before_cutoff_does_nothing(self):
        changed, writes, gem, _, _, _ = await self._run(_row())
        self.assertFalse(changed)
        self.assertEqual(writes, [])
        gem.assert_not_called()

    async def test_no_wrapup_after_cutoff_is_missing_without_ai(self):
        changed, writes, gem, _, fin, _ = await self._run(_row(created_at=(NOW - timedelta(hours=2, minutes=1)).isoformat()))
        self.assertTrue(changed)
        gem.assert_not_called()
        crm = writes[0]["evaluation"]["checks"][-1]
        self.assertEqual((crm["level"], crm["marks"]), ("missing", 0.0))
        self.assertNotIn("ai_call_status", writes[0])
        fin.assert_called_once()

    async def test_wrapup_marks_with_ai_and_leaves_other_checks(self):
        changed, writes, gem, _, _, _ = await self._run(_row(**WARM, notes="needs demo friday"), ai={"level": "good", "reason": "notes thin", "customer": "warm"})
        checks = writes[0]["evaluation"]["checks"]
        self.assertEqual(checks[-1]["level"], "good")
        self.assertEqual(checks[-1]["marks"], 5.25)
        self.assertEqual([c["level"] for c in checks[:-1]], ["good"] * 9)
        self.assertEqual(gem.call_args.kwargs["temperature"], 0.0)
        prompt = gem.call_args.kwargs["user_prompt"]
        self.assertIn("what happened: Interested, needs time or more information", prompt)
        self.assertIn("did the call connect: Connected", prompt)

    async def test_changed_wrapup_is_remarked(self):
        row = _row(feedback_at=NOW.isoformat(), manual_status="connected", outcome="call_later", next_action_at=None)
        row["evaluation"]["checks"] = _checks(crm_level="excellent")
        row["evaluation"]["crm_wrapup"] = _snap(_row(**WARM))
        changed, writes, _, _, _, _ = await self._run(row, ai={"level": "poor", "reason": "callback without time", "customer": "none"})
        self.assertTrue(changed)
        self.assertEqual(writes[0]["evaluation"]["checks"][-1]["level"], "poor")

    async def test_same_wrapup_not_remarked(self):
        row = _row(**WARM)
        row["evaluation"]["checks"] = _checks(crm_level="excellent")
        row["evaluation"]["crm_wrapup"] = _snap(row)
        changed, writes, gem, _, fin, _ = await self._run(row)
        self.assertFalse(changed)
        self.assertEqual(writes, [])
        gem.assert_not_called()
        fin.assert_called_once()  # score_final was never set on the row: self-heal

    async def test_same_wrapup_with_score_final_already_true_skips_finalize(self):
        row = _row(**WARM, score_final=True)
        row["evaluation"]["checks"] = _checks(crm_level="excellent")
        row["evaluation"]["crm_wrapup"] = _snap(row)
        changed, _, gem, _, fin, _ = await self._run(row)
        self.assertFalse(changed)
        gem.assert_not_called()
        fin.assert_not_called()

    async def test_early_exit_mismatch_raises_alert_without_ai(self):
        row = _row(call_group="early_exit", **WARM,
                   evaluation={"evaluation_version": 4, "group": "early_exit",
                               "early_exit_check": {"expected_crm": "wrong_number", "crm_matches": None}})
        changed, writes, gem, alert, fin, _ = await self._run(row)
        gem.assert_not_called()
        self.assertFalse(writes[0]["evaluation"]["early_exit_check"]["crm_matches"])
        self.assertEqual(alert.call_args.kwargs["type"], "crm_mismatch")
        self.assertEqual(alert.call_args.kwargs["quote"],
                         "The call sounded like: Wrong number. Wrap-up saved: Interested, needs time or more information.")
        fin.assert_called_once()

    async def test_early_exit_language_barrier_matches(self):
        row = _row(call_group="early_exit", feedback_at=NOW.isoformat(), manual_status="connected", outcome="language_barrier",
                   preferred_language="tamil",
                   evaluation={"evaluation_version": 4, "group": "early_exit",
                               "early_exit_check": {"expected_crm": "language_barrier", "crm_matches": None}})
        _, writes, _, alert, _, _ = await self._run(row)
        self.assertTrue(writes[0]["evaluation"]["early_exit_check"]["crm_matches"])
        alert.assert_not_called()

    async def test_early_exit_no_wrapup_after_cutoff_is_mismatch_with_alert(self):
        row = _row(call_group="early_exit", created_at=(NOW - timedelta(hours=2, minutes=1)).isoformat(),
                   evaluation={"evaluation_version": 4, "group": "early_exit",
                               "early_exit_check": {"expected_crm": "wrong_number", "crm_matches": None}})
        changed, writes, gem, alert, fin, _ = await self._run(row)
        self.assertTrue(changed)
        gem.assert_not_called()
        early = writes[0]["evaluation"]["early_exit_check"]
        self.assertFalse(early["crm_matches"])
        self.assertTrue(early["no_wrapup"])
        self.assertEqual(alert.call_args.kwargs["quote"], "No wrap-up saved within 2 hours")
        fin.assert_called_once()

    async def test_early_exit_alert_failure_still_saves_and_finalizes(self):
        row = _row(call_group="early_exit", **WARM,
                   evaluation={"evaluation_version": 4, "group": "early_exit",
                               "early_exit_check": {"expected_crm": "wrong_number", "crm_matches": None}})
        changed, writes, _, _, fin, _ = await self._run(row, alert_error=RuntimeError("insert failed"))
        self.assertTrue(changed)
        self.assertFalse(writes[0]["evaluation"]["early_exit_check"]["crm_matches"])
        fin.assert_called_once()

    async def test_real_conversation_alert_failure_still_saves_and_finalizes(self):
        changed, writes, _, _, fin, _ = await self._run(_row(**WARM), ai={"level": "poor", "reason": "status wrong", "customer": "warm"},
                                                        alert_error=RuntimeError("insert failed"))
        self.assertTrue(changed)
        self.assertEqual(writes[0]["evaluation"]["checks"][-1]["level"], "poor")
        fin.assert_called_once()

    async def test_ai_failure_increments_crm_attempts_and_reraises(self):
        row = _row(**WARM)
        db = MagicMock()
        writes = []
        db.table.return_value.update.side_effect = lambda payload: writes.append(payload) or db.table.return_value.update.return_value
        with patch.object(cm, "_load_row", return_value=row), \
             patch.object(cm, "wrapup_snapshot", return_value=_snap(row)), \
             patch.object(cm, "gemini_analysis_json", AsyncMock(side_effect=RuntimeError("timeout"))), \
             patch.object(cm, "finalize_call_score") as fin:
            with self.assertRaises(cm.CallMarkingError):
                await cm.mark_crm_update(db, "call-1", now=NOW)
        self.assertEqual(writes[-1]["evaluation"]["crm_attempts"], 1)
        fin.assert_not_called()

    async def test_third_ai_failure_marks_missing_and_alerts_no_proof(self):
        row = _row(**WARM)
        row["evaluation"]["crm_attempts"] = 3
        changed, writes, gem, alert, fin, _ = await self._run(row)
        self.assertTrue(changed)
        gem.assert_not_called()
        crm = writes[0]["evaluation"]["checks"][-1]
        self.assertEqual((crm["level"], crm["marks"], crm["reason"]), ("missing", 0.0, "The wrap-up couldn't be checked automatically."))
        self.assertEqual(alert.call_args.kwargs["quote"], "Wrap-up check failed 3 times")
        fin.assert_called_once()

    async def test_ai_not_done_yet_waits(self):
        changed, writes, _, _, _, _ = await self._run(_row(ai_status="scoring", feedback_at=NOW.isoformat(), evaluation=None))
        self.assertFalse(changed)
        self.assertEqual(writes, [])

    async def test_gemini_called_ai_votes_times(self):
        _, _, gem, _, _, _ = await self._run(_row(**WARM))
        self.assertEqual(gem.await_count, cm.AI_VOTES)


class TemperatureCorrectionTests(unittest.IsolatedAsyncioTestCase):
    """D10: on cloud calls the AI's majority Hot/Warm/Cold reading corrects the telecaller's."""

    async def _run(self, row, votes):
        db = MagicMock()
        writes = []
        db.table.return_value.update.side_effect = lambda payload: writes.append(payload) or db.table.return_value.update.return_value
        with patch.object(cm, "_load_row", return_value=row), \
             patch.object(cm, "wrapup_snapshot", return_value=_snap(row)), \
             patch.object(cm, "gemini_analysis_json", AsyncMock(side_effect=votes)), \
             patch.object(cm, "raise_alert"), \
             patch.object(cm, "finalize_call_score"):
            await cm.mark_crm_update(db, "call-1", now=NOW)
        return writes, db

    async def test_ai_majority_hot_corrects_a_warm_lead(self):
        votes = [{"level": "good", "reason": "r", "customer": c} for c in ("hot", "hot", "warm")]
        writes, db = await self._run(_row(**WARM), votes)
        self.assertEqual(writes[0]["ai_call_status"], "hot")
        self.assertEqual(writes[0]["evaluation"]["crm_correction"], {"from": "warm", "to": "hot"})
        self.assertEqual(writes[1], {"call_status": "hot"})
        db.table.assert_any_call("leads")

    async def test_correction_only_replaces_the_telecallers_value(self):
        votes = [{"level": "good", "reason": "r", "customer": "cold"}] * 3
        _, db = await self._run(_row(**WARM), votes)
        chain = db.table.return_value.update.return_value.eq.return_value.eq.return_value.eq
        chain.assert_called_with("call_status", "warm")

    async def test_agreement_means_no_correction(self):
        votes = [{"level": "good", "reason": "r", "customer": "warm"}] * 3
        writes, _ = await self._run(_row(**WARM), votes)
        self.assertEqual(len(writes), 1)
        self.assertIsNone(writes[0]["evaluation"]["crm_correction"])
        self.assertEqual(writes[0]["ai_call_status"], "warm")

    async def test_no_majority_reads_none(self):
        votes = [{"level": "good", "reason": "r", "customer": c} for c in ("hot", "warm", "cold")]
        writes, _ = await self._run(_row(**WARM), votes)
        self.assertEqual((writes[0]["ai_call_status"], writes[0]["evaluation"]["crm_correction"]), ("none", None))

    async def test_non_temperature_results_are_never_corrected(self):
        row = _row(feedback_at=NOW.isoformat(), manual_status="connected", outcome="not_interested", outcome_reason="price")
        votes = [{"level": "good", "reason": "r", "customer": "hot"}] * 3
        writes, _ = await self._run(row, votes)
        self.assertEqual(len(writes), 1)
        self.assertIsNone(writes[0]["evaluation"]["crm_correction"])


class MarkCrmUpdateVotingTests(unittest.IsolatedAsyncioTestCase):
    """Check 10 also asks Gemini AI_VOTES times and decides by majority."""

    async def _run_votes(self, row, votes, alert=None):
        db = MagicMock()
        writes = []
        db.table.return_value.update.side_effect = lambda payload: writes.append(payload) or db.table.return_value.update.return_value
        with patch.object(cm, "_load_row", return_value=row), \
             patch.object(cm, "wrapup_snapshot", return_value=_snap(row)), \
             patch.object(cm, "gemini_analysis_json", AsyncMock(side_effect=votes)), \
             patch.object(cm, "raise_alert", alert or MagicMock()), \
             patch.object(cm, "finalize_call_score"):
            changed = await cm.mark_crm_update(db, "call-1", now=NOW)
        return changed, writes

    async def test_majority_level_from_three_runs(self):
        votes = [{"level": "good", "reason": "r1"}, {"level": "good", "reason": "r2"}, {"level": "poor", "reason": "r3"}]
        changed, writes = await self._run_votes(_row(**WARM), votes)
        crm = writes[0]["evaluation"]["checks"][-1]
        self.assertEqual((changed, crm["level"], crm["reason"]), (True, "good", "r1"))

    async def test_all_differ_takes_median(self):
        votes = [{"level": "poor", "reason": "r1"}, {"level": "good", "reason": "r2"}, {"level": "excellent", "reason": "r3"}]
        _, writes = await self._run_votes(_row(**WARM), votes)
        self.assertEqual(writes[0]["evaluation"]["checks"][-1]["level"], "good")

    async def test_fewer_than_two_valid_votes_raises_and_counts_one_attempt(self):
        row = _row(**WARM)
        votes = [{"level": "good", "reason": "r1"}, {"level": "not_a_real_level"}, {"level": None}]
        with self.assertRaises(cm.CallMarkingError):
            await self._run_votes(row, votes)

    async def test_one_run_fails_two_disagree_raises_no_proof_alert(self):
        alert = MagicMock()
        votes = [RuntimeError("boom"), {"level": "good", "reason": "r1"}, {"level": "poor", "reason": "r2"}]
        changed, writes = await self._run_votes(_row(**WARM), votes, alert=alert)
        self.assertTrue(changed)
        self.assertEqual(writes[0]["evaluation"]["checks"][-1]["level"], "poor")
        self.assertIn("Wrap-up check: the AI votes disagreed", [c.kwargs["quote"] for c in alert.call_args_list])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_call_crm_check.py -v`
Expected: FAIL. The mapping, snapshot, prompt and correction tests fail (for example `AssertionError: False is not true` in `test_mapping`, and `KeyError: 'ai_call_status'`).

- [ ] **Step 3: Implement.**

In `backend/app/services/call_marking.py`, add to the imports:

```python
from collections import Counter

from app.services.call_wrapup import (
    AI_CALL_STATUSES, CONNECT_LABEL, LANGUAGE_LABEL, OUTCOME_LABEL, TEMPERATURE_FOR_OUTCOME, TEMPERATURES,
)
```

Then replace everything from the line `# ── Check 10: CRM update, from the telecaller's wrap-up ─────────────────` to the end of the file with:

```python
# ── Check 10: CRM update, from the telecaller's wrap-up ─────────────────

_CRM_ROW_FIELDS = (
    "id,tenant_id,caller_id,lead_id,provider,call_group,ai_status,created_at,feedback_at,"
    "outcome,manual_status,outcome_reason,preferred_language,next_action_at,notes,transcript,evaluation,score_final"
)

_CRM_PROMPT = """A telecaller just finished this sales call and saved a wrap-up. Mark check 10 (CRM update) and give your own reading of how interested the customer is.

Transcript:
{transcript}

Wrap-up saved:
- did the call connect: {manual_status}
- what happened: {outcome}
- reason: {reason}
- preferred language: {preferred_language}
- next step / follow-up / callback time: {next_action_at}
- do not call: {do_not_call}
- notes: {notes}

Correct status guide:
- Interested, next step booked (hot): interested and a specific next step with a date and time was agreed.
- Interested, needs time or more information (warm): interested but wants time, information or to think it over.
- Maybe later (cold): low interest now, maybe in future.
- Call later (customer asked): the customer asked to be called later; a date and time must be set.
- Converted: the customer bought or booked.
- Not interested: clearly not interested (reason: price, already bought, no need, other).
- Disqualified: never enquired, not a fit, or not the decision maker.
- Wrong number: the person is not the lead.
- Language barrier: they could not understand each other; the customer's language must be set.
- Do not call: the customer asked not to be contacted again.

Levels: "excellent" = status matches the call, the notes cover the key points (need, budget, next step) and the time is set if one was agreed; "good" = status correct, notes thin; "partial" = status slightly off; "poor" = status wrong; "missing" = nothing useful saved.
customer = your own reading of the customer by the guide: "hot", "warm" or "cold"; "none" if they were not a buying prospect on this call (converted, not interested, disqualified, wrong number, language barrier, do not call).
Return JSON only: {{"level": "...", "reason": "one line", "customer": "hot|warm|cold|none"}}"""


EXPECTED_CRM_LABEL = {
    "wrong_number": "Wrong number", "not_enquired": "Never enquired", "callback": "Callback with a date and time",
    "language_barrier": "Language barrier", "voicemail": "Voicemail / IVR", "other": "Other",
}


def _wrapup_label(snap: dict) -> str:
    if snap.get("outcome") in OUTCOME_LABEL:
        return OUTCOME_LABEL[snap["outcome"]]
    if snap.get("manual_status") in CONNECT_LABEL:
        return CONNECT_LABEL[snap["manual_status"]]
    if snap.get("do_not_call"):
        return "Do not call"
    return "Nothing"


def crm_matches_expected(expected: str, wrapup: dict) -> bool | None:
    """Early-exit check 3. None when no wrap-up status fits that situation (voicemail, other)."""
    outcome = wrapup.get("outcome")
    if expected == "wrong_number":
        return outcome == "wrong_number"
    if expected == "not_enquired":
        return outcome == "not_interested" or (outcome == "disqualified" and wrapup.get("reason") == "never_enquired")
    if expected == "callback":
        return outcome == "call_later" and bool(wrapup.get("next_action_at"))
    if expected == "language_barrier":
        return outcome == "language_barrier"
    return None


def _load_row(db, call_log_id: str) -> dict | None:
    res = db.table("call_logs").select(_CRM_ROW_FIELDS).eq("id", call_log_id).maybe_single().execute()
    return res.data if res else None


def wrapup_snapshot(db, row: dict) -> dict | None:
    if not row.get("feedback_at"):
        return None
    dnc = False
    if row.get("lead_id"):
        lead = db.table("leads").select("do_not_call").eq("id", row["lead_id"]).maybe_single().execute()
        dnc = bool(((lead.data if lead else None) or {}).get("do_not_call"))
    return {
        "outcome": row.get("outcome"), "manual_status": row.get("manual_status"), "reason": row.get("outcome_reason"),
        "preferred_language": row.get("preferred_language"), "notes": row.get("notes"),
        "next_action_at": row.get("next_action_at"), "do_not_call": dnc,
    }


def _prompt_values(snap: dict) -> dict:
    return {
        "manual_status": CONNECT_LABEL.get(snap.get("manual_status"), "—"),
        "outcome": OUTCOME_LABEL.get(snap.get("outcome"), "—"),
        "reason": (snap.get("reason") or "—").replace("_", " "),
        "preferred_language": LANGUAGE_LABEL.get(snap.get("preferred_language"), "—"),
        "next_action_at": snap.get("next_action_at") or "—",
        "do_not_call": "yes" if snap.get("do_not_call") else "no",
        "notes": snap.get("notes") or "—",
    }


def _majority_customer(results: list[dict]) -> str:
    votes = [d.get("customer") for d in results if d.get("customer") in AI_CALL_STATUSES]
    if not votes:
        return "none"
    top, count = Counter(votes).most_common(1)[0]
    return top if count >= 2 else "none"


def _temperature_correction(snap: dict | None, customer: str | None) -> dict | None:
    """D10: only the telecaller's Hot/Warm/Cold is corrected, and only by a clear AI majority."""
    chosen = TEMPERATURE_FOR_OUTCOME.get((snap or {}).get("outcome"))
    if chosen and customer in TEMPERATURES and customer != chosen:
        return {"from": chosen, "to": customer}
    return None


def _past_cutoff(row: dict, now: datetime) -> bool:
    created = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
    return now - created >= timedelta(hours=WRAPUP_CUTOFF_HOURS)


async def mark_crm_update(db, call_log_id: str, *, now: datetime | None = None) -> bool:
    """Mark (or re-mark) check 10 / the early-exit CRM check. Safe to call any time."""
    now = now or datetime.now(timezone.utc)
    row = _load_row(db, call_log_id)
    evaluation = (row or {}).get("evaluation") or {}
    if not row or row.get("ai_status") != "done" or evaluation.get("evaluation_version") != 4:
        return False
    snap = wrapup_snapshot(db, row)
    group = evaluation.get("group")

    if group == "early_exit":
        early = dict(evaluation.get("early_exit_check") or {})
        alert_quote = None
        if snap is None:
            if early.get("crm_matches") is not None or not _past_cutoff(row, now):
                return False
            early["crm_matches"] = False
            early["no_wrapup"] = True
            alert_quote = "No wrap-up saved within 2 hours"
        else:
            if evaluation.get("crm_wrapup") == snap:
                return False
            matches = crm_matches_expected(early.get("expected_crm", "other"), snap)
            early["crm_matches"] = matches
            if matches is False:
                alert_quote = clip(f"The call sounded like: {EXPECTED_CRM_LABEL.get(early.get('expected_crm'), 'Other')}. Wrap-up saved: {_wrapup_label(snap)}.")
        new_eval = {**evaluation, "early_exit_check": early, "crm_wrapup": snap}
        db.table("call_logs").update({"evaluation": new_eval}).eq("id", call_log_id).execute()
        finalize_call_score(db, call_log_id)
        if alert_quote:
            try:
                raise_alert(db, tenant_id=row["tenant_id"], type="crm_mismatch", call_log_id=call_log_id,
                            caller_id=row.get("caller_id"), quote=alert_quote)
            except Exception as e:
                logger.error(f"crm_mismatch alert failed for call {call_log_id}: {e}")
        return True

    checks = [dict(c) for c in evaluation.get("checks") or []]
    if not checks:
        return False
    crm = checks[-1]
    alerts: list[tuple[str, str]] = []  # (type, quote), fired only after the mark is saved and the score finalized
    customer: str | None = None  # the AI's Hot/Warm/Cold reading; None when the AI didn't run
    if snap is None:
        if crm.get("level") is not None or not _past_cutoff(row, now):
            return False
        crm.update({"level": "missing", "ai_level": None, "marks": 0.0,
                    "reason": f"No wrap-up saved within {WRAPUP_CUTOFF_HOURS} hours of the call."})
    else:
        if evaluation.get("crm_wrapup") == snap and crm.get("level") is not None:
            if not row.get("score_final"):
                finalize_call_score(db, call_log_id)
            return False
        attempts = evaluation.get("crm_attempts") or 0
        if attempts >= CRM_AI_ATTEMPT_CAP:
            crm.update({"level": "missing", "ai_level": None, "marks": 0.0,
                        "reason": "The wrap-up couldn't be checked automatically."})
            alerts.append(("no_proof", "Wrap-up check failed 3 times"))
        else:
            try:
                prompt = _CRM_PROMPT.format(
                    transcript=format_transcript(parse_transcript(row.get("transcript"))), **_prompt_values(snap),
                )
                results = await _gather_votes((
                    gemini_analysis_json(
                        system_prompt=_SYSTEM, user_prompt=prompt,
                        tenant_id=row.get("tenant_id"), temperature=0.0, purpose="call_crm_check", max_tokens=400,
                    )
                    for _ in range(AI_VOTES)
                ), label="mark_crm_update")
                votes = [d.get("level") for d in results if d.get("level") in LEVEL_ORDER]
                if len(votes) < 2:
                    raise CallMarkingError("no valid level for check crm_update")
                level = _majority_level(votes)
                disagreement = len(votes) == 2 and votes[0] != votes[1]
                source = next(d for d in results if d.get("level") == level)
                customer = _majority_customer(results)
            except Exception:
                db.table("call_logs").update({"evaluation": {**evaluation, "crm_attempts": attempts + 1}}).eq("id", call_log_id).execute()
                raise
            crm.update({"level": level, "ai_level": level, "marks": round(check_marks("crm_update", level), 2),
                        "reason": clip(source.get("reason"))})
            if disagreement:
                alerts.append(("no_proof", "Wrap-up check: the AI votes disagreed"))
            if level in ("poor", "missing"):
                alerts.append(("crm_mismatch", clip(source.get("reason"))))
    correction = _temperature_correction(snap, customer)
    checks[-1] = crm
    new_eval = {**evaluation, "checks": checks, "top_improve": top_improve(checks), "crm_wrapup": snap,
                "crm_correction": correction}
    updates: dict = {"evaluation": new_eval}
    if customer is not None:
        updates["ai_call_status"] = customer
    db.table("call_logs").update(updates).eq("id", call_log_id).execute()
    finalize_call_score(db, call_log_id)
    if correction and row.get("lead_id"):
        # Guarded: a newer wrap-up or a conversion since this call must not be overwritten.
        try:
            (
                db.table("leads").update({"call_status": correction["to"]})
                .eq("id", row["lead_id"]).eq("tenant_id", row["tenant_id"]).eq("call_status", correction["from"])
                .execute()
            )
        except Exception as e:
            logger.error(f"AI status correction failed for call {call_log_id}: {e}")
    for alert_type, quote in alerts:
        try:
            raise_alert(db, tenant_id=row["tenant_id"], type=alert_type, call_log_id=call_log_id,
                        caller_id=row.get("caller_id"), quote=quote)
        except Exception as e:
            logger.error(f"{alert_type} alert failed for call {call_log_id}: {e}")
    return True
```

- [ ] **Step 4: Run tests**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_call_crm_check.py tests/test_call_marking.py tests/test_call_ai_pipeline.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/call_marking.py backend/tests/test_call_crm_check.py
git commit -m "feat(scoring): check 10 on wrap-up v2 values and AI Hot/Warm/Cold correction (cloud)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/app/services/call_marking.py backend/tests/test_call_crm_check.py
```

---

### Task 7: Backend readers of the removed values

**Files:**
- Modify: `backend/app/routes/analytics.py`
- Modify: `backend/app/routes/operator.py` (remove `_is_connected_call`, lines 40-53; the two uses ~1799-1806 and ~1928-1935)
- Modify: `backend/app/services/contact_recycler.py` (lines 57-92)
- Modify: `backend/app/services/assignment.py` (lines 45-62, 131-136, 331-346)
- Modify: `backend/app/routes/telecalling_upload.py` (lines 124-137)
- Modify: `backend/app/routes/calls.py` (`next_lead` lead queries ~1444-1532)
- Modify: `backend/app/routes/callers.py` (selects at ~158, ~407, ~588; timeline event dict ~437-445)
- Modify: `backend/app/routes/leads.py` (`get_lead_call_logs` select ~1205)
- Modify: `backend/app/services/ai_reply.py` (`_recent_call_context` select + `_call_context_block`)
- Modify: `backend/app/models/schemas.py` (line 10)
- Modify: `backend/app/main.py` (`_recycle_contacts` docstring)
- Test: `backend/tests/test_wrapup_readers.py`

**Interfaces:**
- Consumes: `call_wrapup.CONNECTS`, `OUTCOMES`, `CLOSED_LEAD_STATUSES`, `connect_rate`, `call_result_label`.
- Produces:
  - Analytics response keys: `connected_calls` = manual_status connected; `connect_rate` = connected ÷ wrap-ups; `outcome_breakdown` keyed by the 10 outcomes; `manual_status_breakdown` keyed by the 4 connect values; `followups_scheduled` = today's wrap-ups with `next_action_at`.
  - Removed keys: `not_picked_calls`, `busy_calls`, `wrong_number_calls`, `interested_leads`, `manual_status_all_time_breakdown`.
  - Call rows from callers, leads, analytics QA and calls recent now carry `manual_status`. Caller timeline events carry `manual_status`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_wrapup_readers.py
"""Readers of call outcomes after wrap-up v2: analytics, recycler, workload, AI call context, operator."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.routes import analytics
from app.services import assignment, contact_recycler
from app.services.ai_reply import _call_context_block
from app.services.call_wrapup import CONNECTS
from tests.fake_supabase import FakeSupabase

UTC = timezone.utc


class AnalyticsTests(unittest.TestCase):
    def test_connect_rate_is_connected_over_wrapups(self):
        logs = [
            {"created_at": "2026-09-27T05:00:00+00:00", "manual_status": "connected", "outcome": "converted", "duration_seconds": 60, "caller_id": "c1"},
            {"created_at": "2026-09-27T05:10:00+00:00", "manual_status": "not_picked", "outcome": None, "duration_seconds": 0, "caller_id": "c1"},
            {"created_at": "2026-09-27T05:20:00+00:00", "manual_status": None, "outcome": None, "duration_seconds": None, "caller_id": "c1"},
        ]
        out = analytics._window_aggregate(logs, [], [], datetime(2026, 9, 27, tzinfo=UTC), datetime(2026, 9, 28, tzinfo=UTC), 1)
        self.assertEqual((out["calls"], out["connect_rate"], out["conversions"]), (3.0, 0.5, 1.0))

    def test_manual_status_breakdown_is_the_four_connect_values(self):
        counts = analytics._manual_status_breakdown([{"manual_status": "busy"}, {"manual_status": "switched_off"}, {"manual_status": None}])
        self.assertEqual(set(counts), set(CONNECTS))
        self.assertEqual((counts["busy"], counts["switched_off"], counts["connected"]), (1, 1, 0))

    def test_old_helpers_are_gone(self):
        self.assertFalse(hasattr(analytics, "_is_connected"))
        self.assertFalse(hasattr(analytics, "MANUAL_STATUS_KEYS"))


class RecyclerTests(unittest.TestCase):
    def test_only_trying_leads_whose_last_call_never_connected_are_recycled(self):
        db = FakeSupabase()
        old = (datetime.now(UTC) - timedelta(hours=10)).isoformat()
        for lead_id, status in (("l1", "trying"), ("l2", "trying"), ("l3", "hot")):
            db.add("leads", id=lead_id, tenant_id="t1", call_status=status, converted_at=None, deleted_at=None,
                   do_not_call=False, assigned_to="c1")
        db.add("call_logs", tenant_id="t1", lead_id="l1", outcome=None, manual_status="not_picked", created_at=old)
        db.add("call_logs", tenant_id="t1", lead_id="l2", outcome="interested_needs_time", manual_status="connected", created_at=old)
        db.add("call_logs", tenant_id="t1", lead_id="l3", outcome=None, manual_status="busy", created_at=old)
        cfg = {"enabled": True, "delay_hours": 4, "max_retries": 3, "start_hour": 0, "end_hour": 24, "max_call_attempts": 4}
        with patch.object(contact_recycler, "get_supabase", return_value=db), \
             patch.object(contact_recycler, "_get_recycle_config", return_value=cfg):
            count = contact_recycler.recycle_leads_for_tenant("t1")
        statuses = {r["id"]: r["call_status"] for r in db.rows("leads")}
        self.assertEqual(count, 1)
        self.assertEqual(statuses, {"l1": "new", "l2": "trying", "l3": "hot"})


class WorkloadTests(unittest.TestCase):
    def test_disqualified_leads_do_not_count_as_open_work(self):
        db = FakeSupabase()
        for status in ("warm", "disqualified", "dnc"):
            db.add("leads", tenant_id="t1", assigned_to="c1", segment="B", converted_at=None, do_not_call=False, call_status=status)
        self.assertEqual(assignment._open_lead_count(db, "t1", "c1"), 1)


class AiCallContextTests(unittest.TestCase):
    def test_uses_readable_labels(self):
        block = _call_context_block([
            {"created_at": "2026-09-27T05:00:00", "outcome": "interested_needs_time", "manual_status": "connected", "ai_summary": {"brief": "b"}},
            {"created_at": "2026-09-26T05:00:00", "outcome": None, "manual_status": "busy", "ai_summary": {"next_action": "retry"}},
        ])
        self.assertIn("outcome: Interested, needs time or more information", block)
        self.assertIn("2026-09-26 — Busy — retry", block)


class StaticReaderTests(unittest.TestCase):
    def test_operator_uses_the_shared_connect_rate(self):
        src = (ROOT / "app/routes/operator.py").read_text(encoding="utf-8")
        self.assertNotIn("_is_connected_call", src)
        self.assertIn("wrapup_connect_rate(", src)

    def test_unused_outcome_literal_removed(self):
        self.assertNotIn("OutcomeType", (ROOT / "app/models/schemas.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_wrapup_readers.py -v`
Expected: FAIL. `connect_rate` is 0.3333 instead of 0.5, the recycler returns 0, `OutcomeType` is still present, and so on.

- [ ] **Step 3: Implement.**

**`backend/app/routes/analytics.py`**
- Delete the line `MANUAL_STATUS_KEYS = (...)`. Add to the imports: `from app.services.call_wrapup import CONNECTS, OUTCOMES, connect_rate as wrapup_connect_rate`.
- Delete the whole `_is_connected` function.
- Replace `_manual_status_breakdown` with:

```python
def _manual_status_breakdown(logs: list[dict]) -> dict[str, int]:
    counts = {key: 0 for key in CONNECTS}
    for log in logs:
        status = log.get("manual_status")
        if status in counts:
            counts[status] += 1
    return counts
```

- In `_window_aggregate`, replace the two lines `connected = sum(...)` and `connect_rate = round(connected / calls, 4) ...` with `connect_rate = wrapup_connect_rate(win_logs)`.
- In the `comp_logs` select, change `"id,duration_seconds,outcome,caller_id,created_at"` to `"id,duration_seconds,outcome,manual_status,caller_id,created_at"`.
- In `logs_today_query`, change the select to `"id,duration_seconds,outcome,manual_status,next_action_at,provider,feedback_source,caller_id,created_at,score,score_status,lead_id,leads(created_at,assigned_at)"`.
- In the week query, change `.select("id,caller_id,manual_status,outcome,disposition,duration_seconds")` to `.select("id,caller_id")`.
- Replace the `outcome_breakdown = {...}` line with `outcome_breakdown = {key: 0 for key in OUTCOMES}`, keeping the loop after it.
- Delete the `rpc_manual_breakdown` and `manual_status_all_time_breakdown` lines (4 lines).
- Replace `team_connected_calls = [l for l in logs_today_res if _is_connected(l)]` with `team_connected_calls = [l for l in logs_today_res if l.get("manual_status") == "connected"]`.
- Replace `team_connect_rate = ...` with `team_connect_rate = wrapup_connect_rate(logs_today_res)`.
- In the per-caller loop, replace the two lines `c_connected = ...` / `c_connect_rate = ...` with `c_connect_rate = wrapup_connect_rate(caller_calls)`.
- In the return dict, delete the keys `not_picked_calls`, `busy_calls`, `wrong_number_calls`, `interested_leads`, `manual_status_all_time_breakdown`. Replace `followups_scheduled` with:

```python
        "followups_scheduled": sum(1 for l in logs_today_res if l.get("next_action_at")),
```

- In the QA feed select (the block with `"id,created_at,duration_seconds,status,outcome,provider,score,score_status,"`), change that line to `"id,created_at,duration_seconds,status,outcome,manual_status,provider,score,score_status,"`.
- Run `grep -n "_is_connected\|MANUAL_STATUS_KEYS\|disposition\|\"interested\"\|\"callback\"\|\"no_answer\"" backend/app/routes/analytics.py`. Expected: only the export column list (`"outcome", "disposition", "manual_status", ...` near line 912) and the CSV row using `row.get("disposition")`. These export the raw `disposition` column, which still exists (SIM APK), so they stay.

**`backend/app/routes/operator.py`**
- Delete `_is_connected_call`. Add `from app.services.call_wrapup import connect_rate as wrapup_connect_rate`.
- In both places change `.select("id,duration_seconds,outcome,disposition,manual_status")` → `.select("id,manual_status")`.
- Replace each `connect_count = sum(1 for row in call_rows if _is_connected_call(row))` plus the following percentage line with:
  - dashboard: `result["connect_rate"] = round(wrapup_connect_rate(call_rows) * 100, 1)`
  - dialer: `"connect_rate": round(wrapup_connect_rate(call_rows) * 100, 1),`

  Keep `call_count` for `total_calls` / `calls_today`.

**`backend/app/services/contact_recycler.py`**
- In the leads query change `.eq("call_status", "in_progress")` → `.eq("call_status", "trying")`.
- Keep `.select("outcome, created_at")`.
- Replace `if last_outcome not in ("no_answer", None):` with:

```python
        # Tap 2 exists only for connected calls: any outcome means someone already reached this lead.
        if last_outcome is not None:
```

**`backend/app/services/assignment.py`**
- Add `from app.services.call_wrapup import CLOSED_LEAD_STATUSES`.
- In `_open_lead_count`, add `.neq("call_status", "disqualified")` after `.neq("call_status", "dnc")`, and change the docstring's second line to `Excludes Not Interested (D), Converted, DNC, Disqualified and Unreachable leads.`
- In the auto-assign safety check replace `ld.get("call_status") in ("converted", "dnc", "unreachable")` with `ld.get("call_status") in CLOSED_LEAD_STATUSES`.
- In the sweep query (~340) add `.neq("call_status", "disqualified")` after `.neq("call_status", "dnc")`.

**`backend/app/routes/telecalling_upload.py`** (~134) and **`backend/app/routes/calls.py` `next_lead`** (both lead queries): add `.neq("call_status", "disqualified")` after each `.neq("call_status", "dnc")`. Wrong-number leads are already excluded by `.neq("do_not_call", True)`.

**`backend/app/routes/callers.py`**
- In the two `select("id,lead_id,call_sid,provider,duration_seconds,outcome,recording_url,...")` strings, insert `manual_status,` after `outcome,`.
- In the timeline query change `.select("id,created_at,duration_seconds,outcome,lead_id")` → `.select("id,created_at,duration_seconds,outcome,manual_status,lead_id")`.
- In the call event dict add `"manual_status": c.get("manual_status"),` after `"outcome": c.get("outcome"),`.

**`backend/app/routes/leads.py`** (`get_lead_call_logs`): in the select string insert `manual_status,next_action_at,` after `outcome,`.

**`backend/app/services/ai_reply.py`**
- In the recent-calls fetch change `.select("outcome,created_at,ai_summary")` → `.select("outcome,manual_status,created_at,ai_summary")`.
- Add `from app.services.call_wrapup import call_result_label` inside `_call_context_block` as the first line of the function body (a local import keeps ai_reply's import graph unchanged).
- Replace `outcome: {latest.get('outcome') or 'unknown'}` with `outcome: {call_result_label(latest) or 'unknown'}`, and `{c.get('outcome') or 'unknown'}` with `{call_result_label(c) or 'unknown'}`.

**`backend/app/models/schemas.py`**: delete the line `OutcomeType = Literal[...]` (`Literal` is still used by the other aliases).

**`backend/app/main.py`**: change the `_recycle_contacts` docstring to `"""APScheduler job: re-queue leads nobody has reached yet, within calling hours."""`.

- [ ] **Step 4: Run tests**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_wrapup_readers.py tests/test_analytics_compare_logic.py tests/test_analytics_compare_routes.py tests/test_telecaller_performance.py tests/test_operator_client_overview.py tests/test_calls_queue_priority.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/analytics.py backend/app/routes/operator.py backend/app/services/contact_recycler.py backend/app/services/assignment.py backend/app/routes/telecalling_upload.py backend/app/routes/calls.py backend/app/routes/callers.py backend/app/routes/leads.py backend/app/services/ai_reply.py backend/app/models/schemas.py backend/app/main.py backend/tests/test_wrapup_readers.py
git commit -m "refactor(calls): analytics, recycler, workload and call context read wrap-up v2 values" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/app/routes/analytics.py backend/app/routes/operator.py backend/app/services/contact_recycler.py backend/app/services/assignment.py backend/app/routes/telecalling_upload.py backend/app/routes/calls.py backend/app/routes/callers.py backend/app/routes/leads.py backend/app/services/ai_reply.py backend/app/models/schemas.py backend/app/main.py backend/tests/test_wrapup_readers.py
```

---

### Task 8: Send details on WhatsApp (backend)

**Files:**
- Create: `backend/app/services/call_details_share.py`
- Create: `backend/app/routes/lead_details_share.py`
- Modify: `backend/app/main.py` (router import + include)
- Test: `backend/tests/test_call_details_share.py`

**Interfaces:**
- Consumes:
  - `call_wrapup.REMINDER_OUTCOMES`, `next_step_phrase`
  - `intake.get_intake_config`, `normalize_packages`
  - `config_dynamic.get_setting`
  - `ai_reply.send_whatsapp`, `get_last_send_error`
  - `meta_cloud.send_template_message`
- Produces:
  - `share_context(db, tenant_id, lead_id, *, now) -> dict | None`. Returns `{"available": False}` or `{"available": True, "window_open", "last_inbound_at", "free_text", "templates": [{id, name, language, body_text, variables: [{key, role, value}]}]}`.
  - `async send_details(db, tenant_id, lead_id, *, text: str | None, template_id: str | None, variables: list[str], now) -> dict` (the inserted `messages` row).
  - `ShareError`, `services_text`, `services_one_line`, `free_message`, `template_variables`, `render_template`, `window_open`.
  - Routes `GET/POST /api/v1/leads/{lead_id}/send-details`. Permission: owner, `telecalling.dialer` or `conversations.reply`. POST body `{text}` or `{template_id, variables[]}`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_call_details_share.py
"""Lead page 'Send details on WhatsApp': free message inside 24h, approved template otherwise."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.services import call_details_share as share
from tests.fake_supabase import FakeSupabase

UTC = timezone.utc
NOW = datetime(2026, 9, 27, 8, 30, tzinfo=UTC)  # Sunday 14:00 IST
PACKAGES = [
    {"key": "basic", "name": "Basic reading", "amount_paise": 4900, "description": "20 minute call", "active": True},
    {"key": "premium", "name": "Premium", "amount_paise": 0, "active": True, "options": [
        {"key": "k", "name": "Kundli", "amount_paise": 9900, "active": True},
        {"key": "m", "name": "Marriage match", "amount_paise": 14900, "active": True},
    ]},
    {"key": "old", "name": "Old plan", "amount_paise": 100, "active": False},
]
SETTINGS = {"meta_phone_number_id": "pn-1", "meta_access_token": "tok", "meta_waba_id": "waba-1"}
SHARE_BODY = "Hi {{1}}, thanks for calling {{2}}. Details: {{3}}"


class _Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = FakeSupabase()
        self.db.add("leads", id="lead-1", tenant_id="t1", name="Priya Raman", phone="+919800000001", opted_out=False,
                    last_inbound_at=(NOW - timedelta(hours=2)).isoformat())
        self.db.add("tenants", id="t1", name="Astro Tamil")
        self.db.add("call_logs", tenant_id="t1", lead_id="lead-1", outcome="interested_booked",
                    next_action_at="2026-10-02T05:30:00+00:00", created_at="2026-09-27T08:00:00+00:00")
        self.db.add("message_templates", id="tpl-1", tenant_id="t1", name="call_details_share", language="en",
                    body_text=SHARE_BODY, status="APPROVED", meta_waba_id="waba-1", header_media_type=None)
        self.db.add("message_templates", id="tpl-2", tenant_id="t1", name="promo", language="en", body_text="Hi {{1}} {{2}}",
                    status="APPROVED", meta_waba_id="waba-1", header_media_type=None)
        self.db.add("message_templates", id="tpl-3", tenant_id="t1", name="pending_one", language="en", body_text="x",
                    status="PENDING", meta_waba_id="waba-1", header_media_type=None)
        self.db.add("message_templates", id="tpl-4", tenant_id="t1", name="old_waba", language="en", body_text="x",
                    status="APPROVED", meta_waba_id="waba-0", header_media_type=None)
        self.db.add("message_templates", id="tpl-5", tenant_id="t1", name="with_image", language="en", body_text="x",
                    status="APPROVED", meta_waba_id="waba-1", header_media_type="IMAGE")
        self.settings = dict(SETTINGS)
        self.send_text = AsyncMock(return_value="wamid.1")
        self.send_template = AsyncMock(return_value={"messages": [{"id": "wamid.2"}]})
        for target, value in (
            ("get_setting", lambda key, tenant_id=None: self.settings.get(key)),
            ("get_intake_config", lambda tenant_id, db=None: {"packages": PACKAGES}),
            ("send_whatsapp", self.send_text),
            ("send_template_message", self.send_template),
            ("get_last_send_error", lambda: "(#131047) Re-engagement message"),
        ):
            patcher = patch.object(share, target, side_effect=value) if callable(value) and not isinstance(value, AsyncMock) else patch.object(share, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def lead(self):
        return self.db.rows("leads")[0]


class TextTests(unittest.TestCase):
    def test_services_text_nests_options_and_skips_inactive(self):
        self.assertEqual(share.services_text(PACKAGES),
                         "• Basic reading — ₹49\n  20 minute call\n• Premium\n  • Kundli — ₹99\n  • Marriage match — ₹149")

    def test_one_line_for_templates(self):
        self.assertEqual(share.services_one_line(PACKAGES), "Basic reading ₹49; Premium (Kundli ₹99; Marriage match ₹149)")

    def test_render_template_leaves_unfilled_blanks(self):
        self.assertEqual(share.render_template("Hi {{1}}, {{2}}", ["Priya"]), "Hi Priya, {{2}}")


class ContextTests(_Base):
    async def test_free_message_inside_the_window(self):
        ctx = share.share_context(self.db, "t1", "lead-1", now=NOW)
        self.assertTrue(ctx["available"])
        self.assertTrue(ctx["window_open"])
        self.assertEqual(ctx["free_text"], (
            "Hi Priya, thank you for your time on the call today.\n\n"
            "Here are the details from Astro Tamil:\n\n"
            "• Basic reading — ₹49\n  20 minute call\n• Premium\n  • Kundli — ₹99\n  • Marriage match — ₹149\n\n"
            "Next step on Friday at 11 AM."
        ))

    async def test_only_approved_text_templates_on_the_current_number(self):
        ctx = share.share_context(self.db, "t1", "lead-1", now=NOW)
        self.assertEqual([t["name"] for t in ctx["templates"]], ["call_details_share", "promo"])
        self.assertEqual(ctx["templates"][0]["variables"], [
            {"key": "1", "role": "customer_name", "value": "Priya Raman"},
            {"key": "2", "role": "business_name", "value": "Astro Tamil"},
            {"key": "3", "role": "details", "value": "Basic reading ₹49; Premium (Kundli ₹99; Marriage match ₹149)"},
        ])
        self.assertEqual(ctx["templates"][1]["variables"], [
            {"key": "1", "role": None, "value": ""}, {"key": "2", "role": None, "value": ""},
        ])

    async def test_window_closed_after_24_hours(self):
        self.lead()["last_inbound_at"] = (NOW - timedelta(hours=25)).isoformat()
        self.assertFalse(share.share_context(self.db, "t1", "lead-1", now=NOW)["window_open"])

    async def test_hidden_without_whatsapp_or_for_opted_out_leads(self):
        self.settings.pop("meta_access_token")
        self.assertEqual(share.share_context(self.db, "t1", "lead-1", now=NOW), {"available": False})
        self.settings["meta_access_token"] = "tok"
        self.lead()["opted_out"] = True
        self.assertEqual(share.share_context(self.db, "t1", "lead-1", now=NOW), {"available": False})

    async def test_unknown_lead(self):
        self.assertIsNone(share.share_context(self.db, "t1", "nope", now=NOW))


class SendTests(_Base):
    async def test_free_text_goes_out_and_lands_in_conversations(self):
        row = await share.send_details(self.db, "t1", "lead-1", text=" Hello ", template_id=None, variables=[], now=NOW)
        self.send_text.assert_awaited_once_with("+919800000001", "Hello", tenant_id="t1")
        self.assertEqual((row["content"], row["meta_message_id"], row["direction"], row["channel"], row["is_ai_generated"]),
                         ("Hello", "wamid.1", "outbound", "whatsapp", False))

    async def test_free_text_outside_the_window_is_refused(self):
        self.lead()["last_inbound_at"] = (NOW - timedelta(days=2)).isoformat()
        with self.assertRaises(share.ShareError) as err:
            await share.send_details(self.db, "t1", "lead-1", text="Hello", template_id=None, variables=[], now=NOW)
        self.assertIn("send a template instead", str(err.exception))
        self.send_text.assert_not_awaited()

    async def test_template_variables_are_flattened_to_one_line(self):
        row = await share.send_details(self.db, "t1", "lead-1", text=None, template_id="tpl-1",
                                       variables=["Priya", "Astro Tamil", "Basic ₹49\n  Premium ₹99"], now=NOW)
        components = self.send_template.await_args.kwargs["components"]
        self.assertEqual([p["text"] for p in components[0]["parameters"]], ["Priya", "Astro Tamil", "Basic ₹49 Premium ₹99"])
        self.assertEqual(self.send_template.await_args.args, ("+919800000001", "call_details_share", "en"))
        self.assertEqual(row["content"], "Hi Priya, thanks for calling Astro Tamil. Details: Basic ₹49 Premium ₹99")
        self.assertEqual(row["meta_message_id"], "wamid.2")

    async def test_every_blank_must_be_filled(self):
        with self.assertRaises(share.ShareError) as err:
            await share.send_details(self.db, "t1", "lead-1", text=None, template_id="tpl-2", variables=["Priya", "  "], now=NOW)
        self.assertEqual(str(err.exception), "Fill every blank in the template.")

    async def test_unapproved_template_is_refused(self):
        with self.assertRaises(share.ShareError):
            await share.send_details(self.db, "t1", "lead-1", text=None, template_id="tpl-3", variables=[], now=NOW)

    async def test_meta_errors_are_reported(self):
        self.send_template.side_effect = HTTPException(status_code=400, detail="(#132000) param count mismatch")
        with self.assertRaises(share.ShareError) as err:
            await share.send_details(self.db, "t1", "lead-1", text=None, template_id="tpl-2", variables=["a", "b"], now=NOW)
        self.assertIn("WhatsApp didn't send it", str(err.exception))

    async def test_failed_free_text_reports_metas_reason(self):
        self.send_text.return_value = None
        with self.assertRaises(share.ShareError) as err:
            await share.send_details(self.db, "t1", "lead-1", text="Hello", template_id=None, variables=[], now=NOW)
        self.assertIn("131047", str(err.exception))
        self.assertEqual(self.db.rows("messages"), [])


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1"}
        self.as_perms(["telecalling.dialer"])

    def tearDown(self):
        app.dependency_overrides.clear()

    def as_perms(self, perms):
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t1", "role": "caller", "user_id": "u1", "caller_id": "c1", "permissions": perms,
        }

    def test_telecallers_without_dialer_or_reply_are_refused(self):
        self.as_perms(["leads.view"])
        self.assertEqual(self.client.get("/api/v1/leads/11111111-2222-3333-4444-555555555555/send-details").status_code, 403)

    def test_get_returns_the_context(self):
        with patch("app.routes.lead_details_share.get_supabase"), \
             patch("app.routes.lead_details_share.share_context", return_value={"available": False}):
            res = self.client.get("/api/v1/leads/11111111-2222-3333-4444-555555555555/send-details")
        self.assertEqual(res.json(), {"available": False})

    def test_post_needs_exactly_one_of_text_or_template(self):
        res = self.client.post("/api/v1/leads/11111111-2222-3333-4444-555555555555/send-details",
                               json={"text": "hi", "template_id": "tpl-1"})
        self.assertEqual(res.status_code, 400)

    def test_share_errors_are_400s(self):
        with patch("app.routes.lead_details_share.get_supabase"), \
             patch("app.routes.lead_details_share.send_details", AsyncMock(side_effect=share.ShareError("Fill every blank in the template."))):
            res = self.client.post("/api/v1/leads/11111111-2222-3333-4444-555555555555/send-details",
                                   json={"template_id": "tpl-1", "variables": [""]})
        self.assertEqual((res.status_code, res.json()["detail"]), (400, "Fill every blank in the template."))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_call_details_share.py -v`
Expected: collection error: `cannot import name 'call_details_share'`.

- [ ] **Step 3: Implement the service**

```python
# backend/app/services/call_details_share.py
"""'Send details on WhatsApp' on the lead page (call wrap-up v2 spec §5).

Free message when the customer wrote in the last 24 h (pre-filled from the Services
page), otherwise an approved template with its blanks pre-filled. Nothing is sent
without a tap; the message is logged in `messages`, so it shows in Conversations."""
import re
from datetime import datetime, timedelta

from fastapi import HTTPException

from app.config_dynamic import get_setting
from app.services.ai_reply import get_last_send_error, send_whatsapp
from app.services.call_wrapup import REMINDER_OUTCOMES, next_step_phrase
from app.services.intake import get_intake_config, normalize_packages
from app.services.meta_cloud import send_template_message

VAR_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")
FREE_WINDOW = timedelta(hours=24)
# The two templates the owner submits for approval (spec §1); any other template's blanks start empty.
KNOWN_TEMPLATE_ROLES = {
    "call_details_share": ("customer_name", "business_name", "details"),
    "call_details_next_step": ("customer_name", "details", "next_step"),
}


class ShareError(ValueError):
    """Something the telecaller can fix or needs to know; the route turns it into a 400."""


def _rupees(paise: int) -> str:
    return f"₹{paise // 100}" if paise % 100 == 0 else f"₹{paise / 100:.2f}"


def _active(nodes: list[dict] | None) -> list[dict]:
    return [n for n in nodes or [] if n.get("active", True) and (n.get("name") or "").strip()]


def services_text(packages: list[dict], depth: int = 0) -> str:
    indent = "  " * depth
    lines = []
    for p in _active(packages):
        name = p["name"].strip()
        if p.get("options"):
            lines.append(f"{indent}• {name}")
            inner = services_text(p["options"], depth + 1)
            if inner:
                lines.append(inner)
        else:
            lines.append(f"{indent}• {name} — {_rupees(p.get('amount_paise') or 0)}")
        description = (p.get("description") or "").strip()
        if description:
            lines.append(f"{indent}  {description}")
    return "\n".join(lines)


def services_one_line(packages: list[dict]) -> str:
    """WhatsApp template parameters can't hold new lines, so templates get this form."""
    parts = []
    for p in _active(packages):
        name = p["name"].strip()
        if p.get("options"):
            inner = services_one_line(p["options"])
            parts.append(f"{name} ({inner})" if inner else name)
        else:
            parts.append(f"{name} {_rupees(p.get('amount_paise') or 0)}")
    return "; ".join(parts)


def one_line(text: str | None) -> str:
    return " ".join((text or "").split())


def free_message(customer_name: str | None, business_name: str, details: str, next_step: str) -> str:
    first = (customer_name or "").strip().split(" ")[0] or "there"
    parts = [f"Hi {first}, thank you for your time on the call today."]
    if details:
        parts.append(f"Here are the details from {business_name or 'us'}:\n\n{details}")
    if next_step:
        parts.append(f"{next_step}.")
    return "\n\n".join(parts)


def template_variables(name: str, body: str | None, facts: dict) -> list[dict]:
    count = max((int(m) for m in VAR_RE.findall(body or "")), default=0)
    roles = KNOWN_TEMPLATE_ROLES.get(name, ())
    out = []
    for i in range(1, count + 1):
        role = roles[i - 1] if i - 1 < len(roles) else None
        out.append({"key": str(i), "role": role, "value": facts.get(role, "") if role else ""})
    return out


def render_template(body: str | None, values: list[str]) -> str:
    def sub(match: re.Match) -> str:
        i = int(match.group(1))
        return values[i - 1] if 0 < i <= len(values) and values[i - 1] else match.group(0)
    return VAR_RE.sub(sub, body or "")


def window_open(last_inbound_at: str | None, now: datetime) -> bool:
    if not last_inbound_at:
        return False
    at = datetime.fromisoformat(str(last_inbound_at).replace("Z", "+00:00"))
    return now - at < FREE_WINDOW


def _lead(db, tenant_id: str, lead_id: str) -> dict | None:
    rows = (
        db.table("leads").select("id,name,phone,opted_out,last_inbound_at")
        .eq("id", lead_id).eq("tenant_id", tenant_id).limit(1).execute()
    ).data or []
    return rows[0] if rows else None


def _whatsapp_ready(tenant_id: str, lead: dict) -> bool:
    connected = get_setting("meta_phone_number_id", tenant_id=tenant_id) and get_setting("meta_access_token", tenant_id=tenant_id)
    return bool(connected and lead.get("phone") and not lead.get("opted_out"))


def _business_name(db, tenant_id: str) -> str:
    rows = db.table("tenants").select("name").eq("id", tenant_id).limit(1).execute().data or []
    return ((rows[0].get("name") if rows else None) or "").strip()


def _next_step(db, tenant_id: str, lead_id: str, now: datetime) -> str:
    rows = (
        db.table("call_logs").select("outcome,next_action_at,created_at")
        .eq("lead_id", lead_id).eq("tenant_id", tenant_id).in_("outcome", list(REMINDER_OUTCOMES))
        .order("created_at", desc=True).limit(1).execute()
    ).data or []
    if not rows or not rows[0].get("next_action_at"):
        return ""
    at = datetime.fromisoformat(str(rows[0]["next_action_at"]).replace("Z", "+00:00"))
    return next_step_phrase(rows[0]["outcome"], at, now) if at > now else ""


def _approved_templates(db, tenant_id: str) -> list[dict]:
    """Approved, text-only templates on the tenant's current WhatsApp account."""
    waba_id = get_setting("meta_waba_id", tenant_id=tenant_id)
    if not waba_id:
        return []
    rows = db.table("message_templates").select("*").eq("tenant_id", tenant_id).execute().data or []
    return [
        r for r in rows
        if (r.get("status") or "").upper() == "APPROVED" and r.get("meta_waba_id") == waba_id and not r.get("header_media_type")
    ]


def share_context(db, tenant_id: str, lead_id: str, *, now: datetime) -> dict | None:
    lead = _lead(db, tenant_id, lead_id)
    if not lead:
        return None
    if not _whatsapp_ready(tenant_id, lead):
        return {"available": False}
    packages = normalize_packages(get_intake_config(tenant_id, db))
    business = _business_name(db, tenant_id)
    next_step = _next_step(db, tenant_id, lead_id, now)
    facts = {
        "customer_name": (lead.get("name") or "").strip(), "business_name": business,
        "details": services_one_line(packages), "next_step": next_step,
    }
    return {
        "available": True,
        "window_open": window_open(lead.get("last_inbound_at"), now),
        "last_inbound_at": lead.get("last_inbound_at"),
        "free_text": free_message(lead.get("name"), business, services_text(packages), next_step),
        "templates": [
            {
                "id": t["id"], "name": t["name"], "language": t.get("language") or "en",
                "body_text": t.get("body_text") or "",
                "variables": template_variables(t["name"], t.get("body_text"), facts),
            }
            for t in _approved_templates(db, tenant_id)
        ],
    }


async def send_details(db, tenant_id: str, lead_id: str, *, text: str | None, template_id: str | None,
                       variables: list[str], now: datetime) -> dict:
    lead = _lead(db, tenant_id, lead_id)
    if not lead:
        raise ShareError("Lead not found.")
    if not _whatsapp_ready(tenant_id, lead):
        raise ShareError("WhatsApp isn't available for this lead.")
    if text is not None:
        body = text.strip()
        if not body:
            raise ShareError("The message is empty.")
        if not window_open(lead.get("last_inbound_at"), now):
            raise ShareError("The customer hasn't messaged in the last 24 hours, so send a template instead.")
        sid = await send_whatsapp(lead["phone"], body, tenant_id=tenant_id)
        if not sid:
            raise ShareError(f"WhatsApp didn't send it: {get_last_send_error() or 'unknown error'}")
        content = body
    else:
        template = next((t for t in _approved_templates(db, tenant_id) if t["id"] == template_id), None)
        if not template:
            raise ShareError("That template isn't approved for this WhatsApp number.")
        values = [one_line(v) for v in variables]
        count = len(template_variables(template["name"], template.get("body_text"), {}))
        if len(values) != count or any(not v for v in values):
            raise ShareError("Fill every blank in the template.")
        components = [{"type": "body", "parameters": [{"type": "text", "text": v} for v in values]}] if count else None
        try:
            resp = await send_template_message(
                lead["phone"], template["name"], template.get("language") or "en", components=components, tenant_id=tenant_id,
            )
        except HTTPException as e:
            raise ShareError(f"WhatsApp didn't send it: {str(e.detail)[:300]}")
        sid = ((resp or {}).get("messages") or [{}])[0].get("id")
        content = render_template(template.get("body_text"), values)
    rows = db.table("messages").insert({
        "lead_id": lead_id, "tenant_id": tenant_id, "direction": "outbound", "channel": "whatsapp",
        "content": content, "is_ai_generated": False, "meta_message_id": sid,
    }).execute().data or []
    return rows[0] if rows else {"sent": True}
```

- [ ] **Step 4: Implement the routes**

```python
# backend/app/routes/lead_details_share.py
"""Lead page: Send details on WhatsApp (call wrap-up v2 spec §5)."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_and_role
from app.services.call_details_share import ShareError, send_details, share_context

router = APIRouter()


def require_share_permission(ctx: dict = Depends(get_tenant_and_role)) -> dict:
    permissions = set(ctx.get("permissions") or [])
    if ctx.get("role") == "owner" or permissions & {"telecalling.dialer", "conversations.reply"}:
        return ctx
    raise HTTPException(status_code=403, detail="Permission required: telecalling.dialer")


class SendDetailsIn(BaseModel):
    text: str | None = Field(None, max_length=4096)
    template_id: str | None = Field(None, max_length=64)
    variables: list[str] = Field(default_factory=list, max_length=20)


@router.get("/{lead_id}/send-details")
async def get_send_details(lead_id: UUID, ctx: dict = Depends(require_share_permission)):
    context = share_context(get_supabase(), ctx["tenant_id"], str(lead_id), now=datetime.now(timezone.utc))
    if context is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return context


@router.post("/{lead_id}/send-details")
async def post_send_details(lead_id: UUID, payload: SendDetailsIn, ctx: dict = Depends(require_share_permission)):
    if (payload.text is None) == (payload.template_id is None):
        raise HTTPException(status_code=400, detail="Send either a message or a template")
    try:
        return await send_details(
            get_supabase(), ctx["tenant_id"], str(lead_id), text=payload.text, template_id=payload.template_id,
            variables=payload.variables, now=datetime.now(timezone.utc),
        )
    except ShareError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

In `backend/app/main.py`:
- Add `from app.routes import lead_details_share` after `from app.routes import deals, business_details`.
- Add directly above `app.include_router(leads.router, prefix="/api/v1/leads", ...)`:

```python
app.include_router(lead_details_share.router, prefix="/api/v1/leads", tags=["leads"], dependencies=_auth)
```

- [ ] **Step 5: Run tests**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_call_details_share.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/call_details_share.py backend/app/routes/lead_details_share.py backend/app/main.py backend/tests/test_call_details_share.py
git commit -m "feat(leads): send call details on WhatsApp (free message or approved template)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/app/services/call_details_share.py backend/app/routes/lead_details_share.py backend/app/main.py backend/tests/test_call_details_share.py
```

---

### Task 9: Frontend shared wrap-up library and API methods (additive)

**Files:**
- Create: `frontend/lib/call-wrapup.ts`
- Test: `frontend/lib/call-wrapup.test.ts`
- Modify: `frontend/lib/api.ts` (new types near line 154; `CallLog` fields; `CallEvaluation.crm_correction`; `TimelineEvent.manual_status`; `api.calls.saveWrapup`, `api.calls.wrapupContext`; `api.leads.sendDetailsContext`, `api.leads.sendDetails`)

**Interfaces:**
- Consumes: backend contracts from Tasks 5 and 8.
- Produces:
  - From `@/lib/api`:
    - Types: `CallConnect`, `NoConnect`, `CallResult`, `LeadCallStatus`, `OutcomeReason`, `PreferredLanguage`, `CallTemperature`, `WrapupPayload`, `WrapupContext`, `WrapupSaved`, `SendDetailsVariable`, `SendDetailsTemplate`, `SendDetailsContext`.
    - Methods: `api.calls.saveWrapup(callLogId, payload)`, `api.calls.wrapupContext({leadId?, callLogId?})`, `api.leads.sendDetailsContext(leadId)`, `api.leads.sendDetails(leadId, body)`.
  - From `@/lib/call-wrapup`:
    - Types: `Tone`, `ConnectOption`, `ResultOption`.
    - Styles: `TONE_CHIP`, `TONE_DOT`, `TONE_HEX`.
    - Option lists: `CONNECT_OPTIONS`, `NO_CONNECTS`, `RESULT_OPTIONS`, `resultOption(value)`, `NOT_INTERESTED_REASONS`, `DISQUALIFIED_REASONS`, `LANGUAGE_OPTIONS`.
    - Result helpers: `callResultKey(log)`, `callResultLabel(key)`, `callResultTone(key)`.
    - Lead status: `LEAD_CALL_STATUSES`, `LEAD_STATUS_LABEL`, `leadStatusTone(s)`, `isClosedLeadStatus(s)`, `isWorkingLeadStatus(s)`.
    - `TEMPERATURE_LABEL`.
    - Time helpers: `quickTimes(now)`, `toIstInputs(d)`, `fromIstInputs(date, time)`, `formatIstWhen(d, now)`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/lib/call-wrapup.test.ts
import { describe, expect, it } from "vitest";
import {
  RESULT_OPTIONS,
  callResultKey,
  callResultLabel,
  callResultTone,
  formatIstWhen,
  fromIstInputs,
  isClosedLeadStatus,
  isWorkingLeadStatus,
  leadStatusTone,
  LEAD_STATUS_LABEL,
  quickTimes,
  resultOption,
  toIstInputs,
} from "./call-wrapup";

const NOW = new Date("2026-09-27T08:30:00Z"); // Sunday 14:00 IST

describe("quick times (IST, whatever the machine's time zone)", () => {
  it("offers in 1 hour, this evening 6 PM and tomorrow 10 AM", () => {
    const [hour, evening, tomorrow] = quickTimes(NOW);
    expect(hour.at.toISOString()).toBe("2026-09-27T09:30:00.000Z");
    expect(evening.at.toISOString()).toBe("2026-09-27T12:30:00.000Z");
    expect(evening.disabled).toBe(false);
    expect(tomorrow.at.toISOString()).toBe("2026-09-28T04:30:00.000Z");
  });

  it("disables this evening once 6 PM IST has passed", () => {
    expect(quickTimes(new Date("2026-09-27T13:30:00Z"))[1].disabled).toBe(true);
  });

  it("round-trips date and time inputs as IST", () => {
    expect(toIstInputs(new Date("2026-09-28T04:30:00Z"))).toEqual({ date: "2026-09-28", time: "10:00" });
    expect(fromIstInputs("2026-10-02", "11:00")?.toISOString()).toBe("2026-10-02T05:30:00.000Z");
    expect(fromIstInputs("", "11:00")).toBeNull();
  });

  it("formats times for people", () => {
    expect(formatIstWhen(new Date("2026-09-27T12:30:00Z"), NOW)).toBe("Today, 6:00 PM");
    expect(formatIstWhen(new Date("2026-09-28T04:30:00Z"), NOW)).toBe("Tomorrow, 10:00 AM");
    expect(formatIstWhen(new Date("2026-10-02T05:30:00Z"), NOW)).toBe("Fri 2 Oct, 11:00 AM");
  });
});

describe("labels and tones", () => {
  it("has the ten results with their rules", () => {
    expect(RESULT_OPTIONS.map((o) => o.value)).toHaveLength(10);
    expect(resultOption("interested_booked")).toMatchObject({ time: "required", notes: true });
    expect(resultOption("maybe_later").time).toBe("optional");
    expect(resultOption("converted")).toMatchObject({ time: null, notes: true });
  });

  it("labels a call by its result, else by whether it connected", () => {
    expect(callResultLabel(callResultKey({ outcome: "interested_booked", manual_status: "connected" }))).toBe("Interested, next step booked");
    expect(callResultLabel(callResultKey({ outcome: null, manual_status: "busy" }))).toBe("Busy");
    expect(callResultLabel(null)).toBeNull();
    expect(callResultTone("converted")).toBe("won");
    expect(callResultTone("not_picked")).toBe("missed");
    expect(callResultTone("something_old")).toBe("neutral");
  });

  it("groups lead statuses", () => {
    expect(LEAD_STATUS_LABEL.callback).toBe("Call later");
    expect(leadStatusTone("hot")).toBe("hot");
    expect(isClosedLeadStatus("disqualified")).toBe(true);
    expect(isClosedLeadStatus("warm")).toBe(false);
    expect(isWorkingLeadStatus("language_barrier")).toBe(true);
    expect(isWorkingLeadStatus(null)).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npx vitest run lib/call-wrapup.test.ts`
Expected: FAIL: `Failed to resolve import "./call-wrapup"`.

- [ ] **Step 3: Add the API types and methods (additive only).**

In `frontend/lib/api.ts`, directly after the line `export type CallOutcome = ...;` (~156) add:

```ts
/** Wrap-up v2 tap 1 (call_logs.manual_status). */
export type CallConnect = "connected" | "not_picked" | "busy" | "switched_off";
export type NoConnect = Exclude<CallConnect, "connected">;
/** Wrap-up v2 tap 2 (call_logs.outcome). */
export type CallResult =
  | "interested_booked" | "interested_needs_time" | "maybe_later" | "call_later" | "converted"
  | "not_interested" | "disqualified" | "wrong_number" | "language_barrier" | "do_not_call";
export type LeadCallStatus =
  | "new" | "trying" | "unreachable" | "hot" | "warm" | "cold" | "callback" | "converted"
  | "not_interested" | "disqualified" | "wrong_number" | "language_barrier" | "dnc";
export type OutcomeReason =
  | "price" | "already_bought" | "no_need" | "other" | "never_enquired" | "not_a_fit" | "not_decision_maker";
export type PreferredLanguage = "tamil" | "english" | "hindi" | "telugu" | "malayalam" | "kannada" | "other";
export type CallTemperature = "hot" | "warm" | "cold";

export interface WrapupPayload {
  manual_status: CallConnect;
  outcome: CallResult | null;
  notes: string | null;
  next_action_at: string | null;
  reason: OutcomeReason | null;
  preferred_language: PreferredLanguage | null;
  stop_messages: boolean;
  products: { catalog_item_id: string; qty: number }[];
  amount_paise: number | null;
  duration_seconds?: number;
  manual_started_at?: string;
  manual_ended_at?: string;
}

export interface WrapupContext {
  connect_prefill: CallConnect | null;
  never_connected: boolean;
  failed_before: number;
  retry_suggestions: Record<NoConnect, string>;
}

export interface WrapupSaved {
  call_log_id: string;
  manual_status: CallConnect;
  outcome: CallResult | null;
  call_status: LeadCallStatus | null;
  next_action_at: string | null;
  deal_id: string | null;
  score: number | null;
  score_status: CallScoreStatus | null;
}

export interface SendDetailsVariable {
  key: string;
  role: "customer_name" | "business_name" | "details" | "next_step" | null;
  value: string;
}

export interface SendDetailsTemplate {
  id: string;
  name: string;
  language: string;
  body_text: string;
  variables: SendDetailsVariable[];
}

export type SendDetailsContext =
  | { available: false }
  | { available: true; window_open: boolean; last_inbound_at: string | null; free_text: string; templates: SendDetailsTemplate[] };
```

Additional changes in the same file:
- In `interface CallEvaluation`, add after `language_barrier?: boolean;`:

```ts
  /** D10: the AI's Hot/Warm/Cold reading replaced the telecaller's. */
  crm_correction?: { from: CallTemperature; to: CallTemperature } | null;
```

- In `interface CallLog`, add after `feedback_at?: string | null;`:

```ts
  next_action_at?: string | null;
  outcome_reason?: OutcomeReason | null;
  preferred_language?: PreferredLanguage | null;
  ai_call_status?: CallTemperature | "none" | null;
```

- In `interface TimelineEvent`, add `manual_status?: string | null;` after `outcome?: string;`.
- In `api.calls`, add after `recent: ...`:

```ts
    saveWrapup: (callLogId: string, payload: WrapupPayload) =>
      apiFetch<WrapupSaved>(`/api/v1/calls/${callLogId}/outcome`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    wrapupContext: (target: { leadId?: string; callLogId?: string }) => {
      const q = new URLSearchParams();
      if (target.leadId) q.set("lead_id", target.leadId);
      if (target.callLogId) q.set("call_log_id", target.callLogId);
      return apiFetch<WrapupContext>(`/api/v1/calls/wrapup-context?${q.toString()}`);
    },
```

- In `api.leads`, add after `convert: ...`:

```ts
    sendDetailsContext: (leadId: string) =>
      apiFetch<SendDetailsContext>(`/api/v1/leads/${leadId}/send-details`),
    sendDetails: (leadId: string, body: { text: string } | { template_id: string; variables: string[] }) =>
      apiFetch<Message>(`/api/v1/leads/${leadId}/send-details`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
```

- [ ] **Step 4: Write the library**

```ts
// frontend/lib/call-wrapup.ts
/**
 * Call wrap-up v2: the one list of options, labels, colours and IST time helpers every
 * screen uses (spec: docs/superpowers/specs/2026-09-27-call-wrapup-v2-design.md).
 * Times are always tenant-local IST, computed with a fixed +05:30 offset so a telecaller
 * whose laptop is set to another zone still gets "Tomorrow 10 AM" in IST.
 */
import type {
  CallConnect, CallResult, CallTemperature, LeadCallStatus, NoConnect, OutcomeReason, PreferredLanguage,
} from "@/lib/api";

export type Tone = "won" | "hot" | "warm" | "cold" | "callback" | "lost" | "blocked" | "attention" | "missed" | "neutral";

export const TONE_CHIP: Record<Tone, string> = {
  won: "bg-emerald-50 text-emerald-700 border-emerald-200",
  hot: "bg-orange-50 text-orange-700 border-orange-200",
  warm: "bg-amber-50 text-amber-700 border-amber-200",
  cold: "bg-sky-50 text-sky-700 border-sky-200",
  callback: "bg-violet-50 text-violet-700 border-violet-200",
  lost: "bg-[#faf8f5] text-[#78716c] border-[#e8e3db]",
  blocked: "bg-red-50 text-red-700 border-red-200",
  attention: "bg-indigo-50 text-indigo-700 border-indigo-200",
  missed: "bg-rose-50 text-rose-700 border-rose-200",
  neutral: "bg-primary-light text-primary border-primary-muted",
};

export const TONE_DOT: Record<Tone, string> = {
  won: "bg-emerald-500", hot: "bg-orange-500", warm: "bg-amber-400", cold: "bg-sky-400",
  callback: "bg-violet-500", lost: "bg-[#a8a29e]", blocked: "bg-red-600", attention: "bg-indigo-500",
  missed: "bg-rose-400", neutral: "bg-primary",
};

export const TONE_HEX: Record<Tone, string> = {
  won: "#10b981", hot: "#f97316", warm: "#f59e0b", cold: "#38bdf8", callback: "#8b5cf6",
  lost: "#a8a29e", blocked: "#dc2626", attention: "#6366f1", missed: "#fb7185", neutral: "var(--primary-400)",
};

export interface ConnectOption { value: CallConnect; label: string; hint: string }

export const CONNECT_OPTIONS: ConnectOption[] = [
  { value: "connected", label: "Connected", hint: "Spoke to the customer" },
  { value: "not_picked", label: "Not picked", hint: "Rang, no answer" },
  { value: "busy", label: "Busy", hint: "Line busy or cut" },
  { value: "switched_off", label: "Switched off", hint: "Not reachable" },
];
export const NO_CONNECTS: NoConnect[] = ["not_picked", "busy", "switched_off"];

export interface ResultOption {
  value: CallResult;
  emoji: string;
  label: string;
  time: "required" | "optional" | null;
  timeLabel: string;
  notes: boolean;
  tone: Tone;
}

export const RESULT_OPTIONS: ResultOption[] = [
  { value: "interested_booked", emoji: "👍", label: "Interested, next step booked", time: "required", timeLabel: "Next step", notes: true, tone: "hot" },
  { value: "interested_needs_time", emoji: "🤔", label: "Interested, needs time or more information", time: "required", timeLabel: "Follow up", notes: true, tone: "warm" },
  { value: "maybe_later", emoji: "🙂", label: "Maybe later", time: "optional", timeLabel: "Follow up (optional)", notes: false, tone: "cold" },
  { value: "call_later", emoji: "📅", label: "Call later (customer asked)", time: "required", timeLabel: "Call back at", notes: false, tone: "callback" },
  { value: "converted", emoji: "🎉", label: "Converted", time: null, timeLabel: "", notes: true, tone: "won" },
  { value: "not_interested", emoji: "👎", label: "Not interested", time: null, timeLabel: "", notes: false, tone: "lost" },
  { value: "disqualified", emoji: "🚫", label: "Disqualified", time: null, timeLabel: "", notes: false, tone: "lost" },
  { value: "wrong_number", emoji: "❓", label: "Wrong number", time: null, timeLabel: "", notes: false, tone: "blocked" },
  { value: "language_barrier", emoji: "🗣️", label: "Language barrier", time: null, timeLabel: "", notes: false, tone: "attention" },
  { value: "do_not_call", emoji: "⛔", label: "Do not call", time: null, timeLabel: "", notes: false, tone: "blocked" },
];

export function resultOption(value: CallResult): ResultOption {
  return RESULT_OPTIONS.find((o) => o.value === value) as ResultOption;
}

export const NOT_INTERESTED_REASONS: { value: OutcomeReason; label: string }[] = [
  { value: "price", label: "Price" },
  { value: "already_bought", label: "Already bought" },
  { value: "no_need", label: "No need" },
  { value: "other", label: "Other" },
];
export const DISQUALIFIED_REASONS: { value: OutcomeReason; label: string }[] = [
  { value: "never_enquired", label: "Never enquired" },
  { value: "not_a_fit", label: "Not a fit" },
  { value: "not_decision_maker", label: "Not the decision maker" },
];
export const LANGUAGE_OPTIONS: { value: PreferredLanguage; label: string }[] = [
  { value: "tamil", label: "Tamil" },
  { value: "english", label: "English" },
  { value: "hindi", label: "Hindi" },
  { value: "telugu", label: "Telugu" },
  { value: "malayalam", label: "Malayalam" },
  { value: "kannada", label: "Kannada" },
  { value: "other", label: "Other" },
];

const CONNECT_LABEL: Record<CallConnect, string> = {
  connected: "Connected", not_picked: "Not picked", busy: "Busy", switched_off: "Switched off",
};

/** The one thing to show for a call: its result, else whether it connected. */
export function callResultKey(log: { outcome?: string | null; manual_status?: string | null }): string | null {
  return log.outcome || log.manual_status || null;
}

export function callResultLabel(key: string | null | undefined): string | null {
  if (!key) return null;
  const option = RESULT_OPTIONS.find((o) => o.value === key);
  if (option) return option.label;
  return CONNECT_LABEL[key as CallConnect] ?? null;
}

export function callResultTone(key: string | null | undefined): Tone {
  const option = RESULT_OPTIONS.find((o) => o.value === key);
  if (option) return option.tone;
  if (NO_CONNECTS.includes(key as NoConnect)) return "missed";
  return "neutral";
}

export const LEAD_CALL_STATUSES: LeadCallStatus[] = [
  "new", "trying", "hot", "warm", "cold", "callback", "language_barrier", "converted",
  "not_interested", "disqualified", "wrong_number", "dnc", "unreachable",
];

export const LEAD_STATUS_LABEL: Record<LeadCallStatus, string> = {
  new: "New", trying: "Trying", unreachable: "Unreachable", hot: "Hot", warm: "Warm", cold: "Cold",
  callback: "Call later", converted: "Converted", not_interested: "Not interested",
  disqualified: "Disqualified", wrong_number: "Wrong number", language_barrier: "Language barrier", dnc: "Do not call",
};

const LEAD_STATUS_TONE: Record<LeadCallStatus, Tone> = {
  new: "neutral", trying: "missed", unreachable: "lost", hot: "hot", warm: "warm", cold: "cold",
  callback: "callback", converted: "won", not_interested: "lost", disqualified: "lost",
  wrong_number: "blocked", language_barrier: "attention", dnc: "blocked",
};

export function leadStatusTone(status: LeadCallStatus | null | undefined): Tone {
  return status ? LEAD_STATUS_TONE[status] : "neutral";
}

const CLOSED: LeadCallStatus[] = ["converted", "not_interested", "disqualified", "wrong_number", "dnc", "unreachable"];
const WORKING: LeadCallStatus[] = ["trying", "hot", "warm", "cold", "language_barrier"];

export function isClosedLeadStatus(status: LeadCallStatus | null | undefined): boolean {
  return !!status && CLOSED.includes(status);
}

export function isWorkingLeadStatus(status: LeadCallStatus | null | undefined): boolean {
  return !!status && WORKING.includes(status);
}

export const TEMPERATURE_LABEL: Record<CallTemperature, string> = { hot: "Hot", warm: "Warm", cold: "Cold" };

// ── IST time helpers ──────────────────────────────────────────────
const IST_OFFSET_MS = 330 * 60_000;
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function istFields(d: Date) {
  const t = new Date(d.getTime() + IST_OFFSET_MS);
  return { y: t.getUTCFullYear(), mo: t.getUTCMonth(), d: t.getUTCDate(), h: t.getUTCHours(), mi: t.getUTCMinutes() };
}

function istDate(y: number, mo: number, d: number, h: number, mi: number): Date {
  return new Date(Date.UTC(y, mo, d, h, mi) - IST_OFFSET_MS);
}

export type QuickTimeKey = "in_1_hour" | "this_evening" | "tomorrow_10am";

export function quickTimes(now: Date): { key: QuickTimeKey; label: string; at: Date; disabled: boolean }[] {
  const f = istFields(now);
  const evening = istDate(f.y, f.mo, f.d, 18, 0);
  return [
    { key: "in_1_hour", label: "In 1 hour", at: new Date(now.getTime() + 3_600_000), disabled: false },
    { key: "this_evening", label: "This evening 6 PM", at: evening, disabled: evening.getTime() <= now.getTime() },
    { key: "tomorrow_10am", label: "Tomorrow 10 AM", at: istDate(f.y, f.mo, f.d + 1, 10, 0), disabled: false },
  ];
}

export function toIstInputs(d: Date): { date: string; time: string } {
  const f = istFields(d);
  return { date: `${f.y}-${pad(f.mo + 1)}-${pad(f.d)}`, time: `${pad(f.h)}:${pad(f.mi)}` };
}

export function fromIstInputs(date: string, time: string): Date | null {
  const dm = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  const tm = /^(\d{2}):(\d{2})$/.exec(time);
  if (!dm || !tm) return null;
  return istDate(Number(dm[1]), Number(dm[2]) - 1, Number(dm[3]), Number(tm[1]), Number(tm[2]));
}

export function formatIstWhen(d: Date, now: Date): string {
  const a = istFields(d);
  const b = istFields(now);
  const dayDiff = Math.round((Date.UTC(a.y, a.mo, a.d) - Date.UTC(b.y, b.mo, b.d)) / 86_400_000);
  const clock = `${a.h % 12 || 12}:${pad(a.mi)} ${a.h < 12 ? "AM" : "PM"}`;
  if (dayDiff === 0) return `Today, ${clock}`;
  if (dayDiff === 1) return `Tomorrow, ${clock}`;
  const weekday = WEEKDAYS[new Date(Date.UTC(a.y, a.mo, a.d)).getUTCDay()];
  return `${weekday} ${a.d} ${MONTHS[a.mo]}, ${clock}`;
}
```

- [ ] **Step 5: Run tests, typecheck and lint**

Run (from `frontend/`): `npx vitest run lib/call-wrapup.test.ts && npm run typecheck && npm run lint`
Expected: vitest reports 8 passed. `tsc --noEmit` exits 0. `next lint` prints `✔ No ESLint warnings or errors`.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/call-wrapup.ts frontend/lib/call-wrapup.test.ts frontend/lib/api.ts
git commit -m "feat(telecalling): shared wrap-up v2 options, labels and IST time helpers" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- frontend/lib/call-wrapup.ts frontend/lib/call-wrapup.test.ts frontend/lib/api.ts
```

---

### Task 10: The two-tap wrap-up form (frontend)

**Files:**
- Create: `frontend/app/dashboard/telecalling/lib/wrapup-draft.ts`
- Test: `frontend/app/dashboard/telecalling/lib/wrapup-draft.test.ts`
- Create: `frontend/app/dashboard/telecalling/components/wrapup/QuickTimePicker.tsx`
- Create: `frontend/app/dashboard/telecalling/components/wrapup/SalePicker.tsx`
- Create: `frontend/app/dashboard/telecalling/components/wrapup/WrapupModal.tsx`
- Modify (full rewrite): `frontend/app/dashboard/telecalling/components/CockpitModals.tsx`
- Modify: `frontend/app/dashboard/telecalling/lib/useCallingCockpit.ts`

**Interfaces:**
- Consumes: Task 9 (`api.calls.saveWrapup`, `api.calls.wrapupContext`, `WrapupContext`, the `@/lib/call-wrapup` helpers), `api.catalog.listItems`, `TickMark`, `formatRupees`.
- Produces:
  - `wrapup-draft.ts`: `SaleLine`, `WrapupDraft`, `emptyDraft()`, `selectConnect(draft, value, context)`, `selectOutcome(draft, value)`, `applyContext(draft, context)`, `amountPaise(rupees)`, `draftError(draft, now)`, `draftToPayload(draft)`.
  - `WrapupModal` default export with props `WrapupModalProps` (plus `SimTiming`).
  - Cockpit returns `wrapupDraft`, `setWrapupDraft`, `wrapupContext` and `catalogItems` (replacing `wrapupOutcome`, `wrapupTags`, `toggleWrapupTag`, `wrapupQualityRating`, `wrapupCallbackDate` and `wrapupCallbackTime`, plus their setters).

- [ ] **Step 1: Write the failing test**

```ts
// frontend/app/dashboard/telecalling/lib/wrapup-draft.test.ts
import { describe, expect, it } from "vitest";
import type { WrapupContext } from "@/lib/api";
import { applyContext, draftError, draftToPayload, emptyDraft, selectConnect, selectOutcome, type WrapupDraft } from "./wrapup-draft";

const NOW = new Date("2026-09-27T08:30:00Z");
const LATER = "2026-09-27T12:30:00.000Z";
const CTX: WrapupContext = {
  connect_prefill: "not_picked",
  never_connected: true,
  failed_before: 0,
  retry_suggestions: { not_picked: "2026-09-27T10:30:00+00:00", busy: "2026-09-27T09:00:00+00:00", switched_off: "2026-09-28T04:30:00+00:00" },
};

function connected(outcome: WrapupDraft["outcome"], patch: Partial<WrapupDraft> = {}): WrapupDraft {
  return { ...selectOutcome(selectConnect(emptyDraft(), "connected", null), outcome!), ...patch };
}

describe("selecting", () => {
  it("fills the suggested retry for a call that didn't connect", () => {
    const d = selectConnect(emptyDraft(), "busy", CTX);
    expect(d).toMatchObject({ manualStatus: "busy", outcome: null, nextActionAt: CTX.retry_suggestions.busy });
  });

  it("clears the retry when switching to connected", () => {
    expect(selectConnect(selectConnect(emptyDraft(), "busy", CTX), "connected", CTX).nextActionAt).toBeNull();
  });

  it("clears reason and language when the result changes", () => {
    const d = selectOutcome(connected("not_interested", { reason: "price" }), "maybe_later");
    expect(d.reason).toBeNull();
  });

  it("applies the cloud pre-fill once, without overriding the telecaller", () => {
    expect(applyContext(emptyDraft(), CTX)).toMatchObject({ manualStatus: "not_picked", nextActionAt: CTX.retry_suggestions.not_picked });
    const mine = selectConnect(emptyDraft(), "connected", null);
    expect(applyContext(mine, CTX)).toBe(mine);
    const waiting = { ...emptyDraft(), manualStatus: "switched_off" as const };
    expect(applyContext(waiting, CTX).nextActionAt).toBe(CTX.retry_suggestions.switched_off);
  });
});

describe("validation mirrors the server", () => {
  it("walks the telecaller through the required fields", () => {
    expect(draftError(emptyDraft(), NOW)).toBe("Pick whether the call connected.");
    expect(draftError(selectConnect(emptyDraft(), "connected", null), NOW)).toBe("Pick what happened on the call.");
    expect(draftError(connected("interested_booked"), NOW)).toBe("Pick a date and time.");
    expect(draftError(connected("interested_booked", { nextActionAt: LATER }), NOW)).toBe("Add a short note for this result.");
    expect(draftError(connected("interested_booked", { nextActionAt: LATER, notes: "Demo Friday" }), NOW)).toBeNull();
    expect(draftError(connected("not_interested"), NOW)).toBe("Pick why they're not interested.");
    expect(draftError(connected("disqualified"), NOW)).toBe("Pick why the lead is disqualified.");
    expect(draftError(connected("language_barrier"), NOW)).toBe("Pick the language the customer speaks.");
    expect(draftError(connected("converted", { notes: "paid" }), NOW)).toBe("Add the products sold.");
    expect(draftError(connected("converted", { notes: "paid", saleMode: "amount", amountRupees: "0" }), NOW)).toBe("Enter the sale amount.");
    expect(draftError(connected("maybe_later"), NOW)).toBeNull();
  });

  it("rejects past times", () => {
    expect(draftError(connected("call_later", { nextActionAt: "2026-09-27T08:00:00Z" }), NOW)).toBe("Pick a time in the future.");
  });
});

describe("payload", () => {
  it("sends products or an amount for a sale, never both", () => {
    const products = connected("converted", {
      notes: " paid ",
      products: [{ catalogItemId: "i1", name: "Pen", qty: 2, pricePaise: 5000 }],
      amountRupees: "900",
    });
    expect(draftToPayload(products)).toMatchObject({
      manual_status: "connected", outcome: "converted", notes: "paid",
      products: [{ catalog_item_id: "i1", qty: 2 }], amount_paise: null,
    });
    const amount = { ...products, saleMode: "amount" as const, amountRupees: "1,499.50" };
    expect(draftToPayload(amount)).toMatchObject({ products: [], amount_paise: 149950 });
  });

  it("sends stop_messages only for do-not-call", () => {
    expect(draftToPayload(connected("do_not_call", { stopMessages: true })).stop_messages).toBe(true);
    expect(draftToPayload(connected("maybe_later", { stopMessages: true })).stop_messages).toBe(false);
  });

  it("never sends a result for a call that didn't connect", () => {
    expect(draftToPayload(selectConnect(emptyDraft(), "busy", CTX))).toMatchObject({ manual_status: "busy", outcome: null });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run app/dashboard/telecalling/lib/wrapup-draft.test.ts`
Expected: FAIL: `Failed to resolve import "./wrapup-draft"`.

- [ ] **Step 3: Implement the draft logic**

```ts
// frontend/app/dashboard/telecalling/lib/wrapup-draft.ts
/** The wrap-up form's state and rules, kept pure so they are unit-tested and mirror the server. */
import type { CallConnect, CallResult, OutcomeReason, PreferredLanguage, WrapupContext, WrapupPayload } from "@/lib/api";
import { resultOption } from "@/lib/call-wrapup";

export interface SaleLine {
  catalogItemId: string;
  name: string;
  qty: number;
  pricePaise: number | null;
}

export interface WrapupDraft {
  manualStatus: CallConnect | null;
  outcome: CallResult | null;
  notes: string;
  nextActionAt: string | null;
  reason: OutcomeReason | null;
  preferredLanguage: PreferredLanguage | null;
  stopMessages: boolean;
  saleMode: "products" | "amount";
  products: SaleLine[];
  amountRupees: string;
}

const PAST_TOLERANCE_MS = 5 * 60_000;

export function emptyDraft(): WrapupDraft {
  return {
    manualStatus: null, outcome: null, notes: "", nextActionAt: null, reason: null, preferredLanguage: null,
    stopMessages: false, saleMode: "products", products: [], amountRupees: "",
  };
}

export function selectConnect(draft: WrapupDraft, value: CallConnect, context: WrapupContext | null): WrapupDraft {
  if (value === "connected") return { ...draft, manualStatus: value, nextActionAt: null };
  return {
    ...draft, manualStatus: value, outcome: null, reason: null, preferredLanguage: null, stopMessages: false,
    nextActionAt: context?.retry_suggestions[value] ?? null,
  };
}

export function selectOutcome(draft: WrapupDraft, value: CallResult): WrapupDraft {
  return {
    ...draft, outcome: value, reason: null, preferredLanguage: null, stopMessages: false,
    nextActionAt: resultOption(value).time ? draft.nextActionAt : null,
  };
}

/** The cloud pre-fill and retry suggestion arrive after the form opens; never override a choice. */
export function applyContext(draft: WrapupDraft, context: WrapupContext): WrapupDraft {
  if (!draft.manualStatus) {
    return context.connect_prefill ? selectConnect(draft, context.connect_prefill, context) : draft;
  }
  if (draft.manualStatus !== "connected" && !draft.nextActionAt) {
    return { ...draft, nextActionAt: context.retry_suggestions[draft.manualStatus] };
  }
  return draft;
}

export function amountPaise(rupees: string): number | null {
  const value = Number(rupees.replace(/,/g, "").trim());
  return Number.isFinite(value) && value >= 1 ? Math.round(value * 100) : null;
}

function futureError(iso: string, now: Date): string | null {
  return new Date(iso).getTime() < now.getTime() - PAST_TOLERANCE_MS ? "Pick a time in the future." : null;
}

export function draftError(draft: WrapupDraft, now: Date): string | null {
  if (!draft.manualStatus) return "Pick whether the call connected.";
  if (draft.manualStatus !== "connected") {
    return draft.nextActionAt ? futureError(draft.nextActionAt, now) : "Pick when to try again.";
  }
  if (!draft.outcome) return "Pick what happened on the call.";
  const option = resultOption(draft.outcome);
  if (option.time === "required" && !draft.nextActionAt) return "Pick a date and time.";
  if (option.time && draft.nextActionAt) {
    const past = futureError(draft.nextActionAt, now);
    if (past) return past;
  }
  if (draft.outcome === "not_interested" && !draft.reason) return "Pick why they're not interested.";
  if (draft.outcome === "disqualified" && !draft.reason) return "Pick why the lead is disqualified.";
  if (draft.outcome === "language_barrier" && !draft.preferredLanguage) return "Pick the language the customer speaks.";
  if (draft.outcome === "converted") {
    if (draft.saleMode === "products" && draft.products.length === 0) return "Add the products sold.";
    if (draft.saleMode === "amount" && amountPaise(draft.amountRupees) === null) return "Enter the sale amount.";
  }
  if (option.notes && !draft.notes.trim()) return "Add a short note for this result.";
  return null;
}

export function draftToPayload(draft: WrapupDraft): WrapupPayload {
  const connected = draft.manualStatus === "connected";
  const sale = connected && draft.outcome === "converted";
  return {
    manual_status: draft.manualStatus as CallConnect,
    outcome: connected ? draft.outcome : null,
    notes: draft.notes.trim() || null,
    next_action_at: draft.nextActionAt,
    reason: draft.reason,
    preferred_language: draft.preferredLanguage,
    stop_messages: connected && draft.outcome === "do_not_call" && draft.stopMessages,
    products: sale && draft.saleMode === "products"
      ? draft.products.map((p) => ({ catalog_item_id: p.catalogItemId, qty: p.qty }))
      : [],
    amount_paise: sale && draft.saleMode === "amount" ? amountPaise(draft.amountRupees) : null,
  };
}
```

- [ ] **Step 4: Run the draft tests**

Run: `npx vitest run app/dashboard/telecalling/lib/wrapup-draft.test.ts`
Expected: 10 passed.

- [ ] **Step 5: Write the three components**

```tsx
// frontend/app/dashboard/telecalling/components/wrapup/QuickTimePicker.tsx
"use client";
import { useState } from "react";
import { CalendarClock, X } from "lucide-react";
import { formatIstWhen, fromIstInputs, quickTimes, toIstInputs } from "@/lib/call-wrapup";

interface QuickTimePickerProps {
  value: string | null;
  onChange: (iso: string | null) => void;
  now: Date;
  optional?: boolean;
  suggested?: string | null;
}

const CHIP = "px-3 py-1.5 rounded-full border font-label text-[11px] font-bold transition-all disabled:opacity-40 disabled:cursor-not-allowed";
const ON = "bg-primary border-primary text-white shadow-sm";
const OFF = "bg-white border-[#e8e3db] text-[#57534e] hover:border-primary-muted hover:text-primary";
const INPUT = "flex-1 min-w-0 rounded-xl border border-[#e8e3db] bg-white px-3 py-2 font-body text-xs focus:outline-none focus:ring-2 focus:ring-primary";

/** In 1 hour · This evening 6 PM · Tomorrow 10 AM · Pick a date & time — all in IST. */
export default function QuickTimePicker({ value, onChange, now, optional = false, suggested = null }: QuickTimePickerProps) {
  const [custom, setCustom] = useState(false);
  const quick = quickTimes(now);
  const picked = value ? new Date(value) : null;
  const matched = picked ? quick.find((q) => Math.abs(q.at.getTime() - picked.getTime()) < 60_000)?.key ?? null : null;
  const showCustom = custom || (picked !== null && matched === null && value !== suggested);
  const inputs = toIstInputs(picked ?? quick[0].at);

  function setPart(part: "date" | "time", next: string) {
    const merged = { ...inputs, [part]: next };
    const at = fromIstInputs(merged.date, merged.time);
    if (at) onChange(at.toISOString());
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {quick.map((q) => (
          <button
            key={q.key}
            type="button"
            disabled={q.disabled}
            onClick={() => {
              setCustom(false);
              onChange(q.at.toISOString());
            }}
            className={`${CHIP} ${matched === q.key && !custom ? ON : OFF}`}
          >
            {q.label}
          </button>
        ))}
        <button
          type="button"
          onClick={() => {
            setCustom(true);
            if (!picked) onChange(quick[0].at.toISOString());
          }}
          className={`${CHIP} inline-flex items-center gap-1 ${showCustom ? ON : OFF}`}
        >
          <CalendarClock size={11} /> Pick a date &amp; time
        </button>
        {optional && value && (
          <button
            type="button"
            onClick={() => {
              setCustom(false);
              onChange(null);
            }}
            className={`${CHIP} inline-flex items-center gap-1 bg-white border-[#e8e3db] text-[#a8a29e] hover:text-rose-600`}
          >
            <X size={11} /> No follow-up
          </button>
        )}
      </div>
      {showCustom && (
        <div className="flex items-center gap-2">
          <input type="date" aria-label="Date" value={inputs.date} min={toIstInputs(now).date} onChange={(e) => setPart("date", e.target.value)} className={INPUT} />
          <input type="time" aria-label="Time" value={inputs.time} onChange={(e) => setPart("time", e.target.value)} className={INPUT} />
          <span className="font-label text-[10px] font-bold text-[#a8a29e]">IST</span>
        </div>
      )}
      {picked && (
        <p className="font-label text-[11px] text-[#57534e]">
          <span className="font-bold text-[#292524]">{formatIstWhen(picked, now)}</span>
          {value === suggested && (
            <span className="ml-1.5 rounded-full bg-primary-light px-1.5 py-0.5 text-[9px] font-black uppercase tracking-wider text-primary">
              Suggested
            </span>
          )}
        </p>
      )}
    </div>
  );
}
```

```tsx
// frontend/app/dashboard/telecalling/components/wrapup/SalePicker.tsx
"use client";
import { Minus, Plus, X } from "lucide-react";
import type { CatalogItem } from "@/lib/api";
import { formatRupees } from "@/components/deals/money";
import type { SaleLine, WrapupDraft } from "../../lib/wrapup-draft";

type SalePatch = Partial<Pick<WrapupDraft, "saleMode" | "products" | "amountRupees">>;

interface SalePickerProps {
  mode: WrapupDraft["saleMode"];
  products: SaleLine[];
  amountRupees: string;
  catalogItems: CatalogItem[];
  onChange: (patch: SalePatch) => void;
}

const STEP = "grid h-6 w-6 place-items-center rounded-lg border border-[#e8e3db] text-[#57534e] hover:bg-[#faf8f5]";

/** Converted: products from the catalog (price comes from the catalog) or one amount. */
export default function SalePicker({ mode, products, amountRupees, catalogItems, onChange }: SalePickerProps) {
  const available = catalogItems.filter((item) => !products.some((p) => p.catalogItemId === item.id));
  const total = products.reduce((sum, p) => sum + (p.pricePaise ?? 0) * p.qty, 0);

  function add(id: string) {
    const item = catalogItems.find((i) => i.id === id);
    if (!item || item.price_paise == null) return;
    onChange({ products: [...products, { catalogItemId: item.id, name: item.name, qty: 1, pricePaise: item.price_paise }] });
  }

  function setQty(id: string, qty: number) {
    onChange({ products: products.map((p) => (p.catalogItemId === id ? { ...p, qty: Math.max(1, Math.min(1000, qty)) } : p)) });
  }

  return (
    <div className="rounded-2xl border border-emerald-200 bg-emerald-50/50 p-3 space-y-3">
      <div className="inline-flex rounded-xl border border-emerald-200 bg-white p-0.5">
        {(["products", "amount"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => onChange({ saleMode: m })}
            className={`px-3 py-1 rounded-lg font-label text-[11px] font-bold transition-colors ${mode === m ? "bg-emerald-600 text-white" : "text-emerald-800 hover:bg-emerald-50"}`}
          >
            {m === "products" ? "From products" : "Enter amount"}
          </button>
        ))}
      </div>

      {mode === "products" ? (
        <>
          {products.length > 0 && (
            <ul className="space-y-1.5">
              {products.map((p) => (
                <li key={p.catalogItemId} className="flex items-center gap-2 rounded-xl border border-[#e8e3db] bg-white px-2.5 py-2">
                  <span className="min-w-0 flex-1 truncate font-body text-xs font-semibold text-[#292524]">{p.name}</span>
                  <div className="flex items-center gap-1">
                    <button type="button" aria-label={`One less ${p.name}`} onClick={() => setQty(p.catalogItemId, p.qty - 1)} className={STEP}>
                      <Minus size={11} />
                    </button>
                    <span className="w-6 text-center font-mono text-xs font-bold tabular-nums">{p.qty}</span>
                    <button type="button" aria-label={`One more ${p.name}`} onClick={() => setQty(p.catalogItemId, p.qty + 1)} className={STEP}>
                      <Plus size={11} />
                    </button>
                  </div>
                  <span className="w-16 text-right font-label text-[11px] font-bold tabular-nums text-[#44403c]">{formatRupees((p.pricePaise ?? 0) * p.qty)}</span>
                  <button
                    type="button"
                    aria-label={`Remove ${p.name}`}
                    onClick={() => onChange({ products: products.filter((x) => x.catalogItemId !== p.catalogItemId) })}
                    className="text-[#a8a29e] hover:text-rose-600"
                  >
                    <X size={13} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <select
            value=""
            onChange={(e) => add(e.target.value)}
            aria-label="Add a product"
            className="w-full rounded-xl border border-[#e8e3db] bg-white px-3 py-2 font-body text-xs text-[#44403c] focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="">{catalogItems.length === 0 ? "No products yet — enter the amount instead" : "Add a product…"}</option>
            {available.map((item) => (
              <option key={item.id} value={item.id} disabled={item.price_paise == null}>
                {item.name}{item.price_paise == null ? " (no price)" : ` · ${formatRupees(item.price_paise)}`}
              </option>
            ))}
          </select>
          {products.length > 0 && <p className="text-right font-label text-xs font-bold text-emerald-800">Total {formatRupees(total)}</p>}
        </>
      ) : (
        <label className="flex items-center gap-2 rounded-xl border border-[#e8e3db] bg-white px-3 py-2">
          <span className="font-label text-sm font-bold text-[#57534e]">₹</span>
          <input
            inputMode="decimal"
            value={amountRupees}
            onChange={(e) => onChange({ amountRupees: e.target.value })}
            placeholder="Amount received"
            aria-label="Sale amount in rupees"
            className="flex-1 bg-transparent font-body text-sm focus:outline-none"
          />
        </label>
      )}
      <p className="font-label text-[10px] text-emerald-800/80">Saving records a Won deal from this call.</p>
    </div>
  );
}
```

```tsx
// frontend/app/dashboard/telecalling/components/wrapup/WrapupModal.tsx
"use client";
import { useState } from "react";
import { Check, PhoneCall, PhoneMissed, PhoneOff, Power, RefreshCw } from "lucide-react";
import type { CallConnect, CatalogItem, WrapupContext } from "@/lib/api";
import {
  CONNECT_OPTIONS, DISQUALIFIED_REASONS, LANGUAGE_OPTIONS, NOT_INTERESTED_REASONS, RESULT_OPTIONS, TONE_CHIP, resultOption,
} from "@/lib/call-wrapup";
import { TickMark } from "@/components/ui/controls";
import { draftError, selectConnect, selectOutcome, type WrapupDraft } from "../../lib/wrapup-draft";
import QuickTimePicker from "./QuickTimePicker";
import SalePicker from "./SalePicker";

const CONNECT_ICON: Record<CallConnect, typeof PhoneCall> = {
  connected: PhoneCall, not_picked: PhoneMissed, busy: PhoneOff, switched_off: Power,
};
const LABEL = "font-label text-[10px] text-[#a8a29e] uppercase tracking-wider font-extrabold block mb-2";

function chip(selected: boolean): string {
  return `px-3 py-1.5 rounded-full border font-label text-[11px] font-bold transition-all ${
    selected ? "bg-primary border-primary text-white shadow-sm" : "bg-[#faf8f5] border-[#e8e3db] text-[#57534e] hover:border-primary-muted hover:text-primary"
  }`;
}

export interface SimTiming {
  startedAt: string;
  endedAt: string;
  setStartedAt: (value: string) => void;
  setEndedAt: (value: string) => void;
}

export interface WrapupModalProps {
  callee: string;
  provider: "telecmi" | "sim_basic";
  context: WrapupContext | null;
  draft: WrapupDraft;
  onChange: (draft: WrapupDraft) => void;
  saving: boolean;
  onSubmit: () => void;
  catalogItems: CatalogItem[];
  simTiming: SimTiming | null;
  /** Fixed "now" for previews; defaults to when the form opened. */
  now?: Date;
}

function simSeconds(t: SimTiming): number | null {
  if (!t.startedAt || !t.endedAt) return null;
  const s = Math.round((new Date(t.endedAt).getTime() - new Date(t.startedAt).getTime()) / 1000);
  return Number.isFinite(s) ? Math.max(0, s) : null;
}

/** The mandatory two-tap wrap-up, identical for SIM and cloud calls. */
export default function WrapupModal({
  callee, provider, context, draft, onChange, saving, onSubmit, catalogItems, simTiming, now,
}: WrapupModalProps) {
  const [openedAt] = useState(() => now ?? new Date());
  const problem = draftError(draft, openedAt);
  const option = draft.outcome ? resultOption(draft.outcome) : null;
  const noConnect = draft.manualStatus !== null && draft.manualStatus !== "connected";
  const streak = (context?.failed_before ?? 0) + 1;
  const suggested = draft.manualStatus && draft.manualStatus !== "connected" ? context?.retry_suggestions[draft.manualStatus] ?? null : null;
  const seconds = simTiming ? simSeconds(simTiming) : null;
  const setTime = (iso: string | null) => onChange({ ...draft, nextActionAt: iso });

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center bg-[#1c1917]/80 p-0 backdrop-blur-sm sm:items-center sm:p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="wrapup-title"
        className="flex max-h-[88vh] w-full max-w-lg flex-col rounded-t-3xl border border-[#e8e3db] bg-white shadow-2xl animate-in fade-in slide-in-from-bottom-4 sm:max-h-[92vh] sm:rounded-3xl sm:zoom-in-95"
      >
        <div className="border-b border-[#f0ece4] px-5 pb-4 pt-5 sm:px-7 sm:pt-6">
          <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 font-label text-[10px] font-black uppercase tracking-wider text-amber-700">
            {provider === "sim_basic" ? "SIM call" : "Cloud call"}
          </span>
          <h3 id="wrapup-title" className="mt-2 font-display text-xl font-bold text-[#1c1917]">Wrap up the call</h3>
          <p className="mt-0.5 font-body text-xs text-[#a8a29e]">
            with <span className="font-semibold text-[#44403c]">{callee}</span>
          </p>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5 sm:px-7">
          {simTiming && (
            <section className="rounded-2xl border border-primary-muted bg-primary-light/40 p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <p className="font-label text-[10px] font-black uppercase tracking-wider text-primary">Call timing</p>
                  <p className="mt-0.5 font-body text-[11px] text-[#78716c]">Aira can&apos;t read SIM call time, so check it before saving.</p>
                </div>
                <span className="rounded-xl bg-white px-3 py-1.5 font-mono text-xs font-bold text-[#292524]">
                  {seconds !== null ? `${Math.floor(seconds / 60)}m ${seconds % 60}s` : "0m"}
                </span>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {([["Started", simTiming.startedAt, simTiming.setStartedAt], ["Ended", simTiming.endedAt, simTiming.setEndedAt]] as const).map(([label, value, set]) => (
                  <label key={label} className="block">
                    <span className="mb-1 block font-label text-[9px] font-black uppercase tracking-wider text-[#a8a29e]">{label}</span>
                    <input
                      type="datetime-local"
                      value={value}
                      onChange={(e) => set(e.target.value)}
                      className="w-full rounded-xl border border-[#e8e3db] bg-white px-3 py-2 font-body text-xs focus:outline-none focus:ring-2 focus:ring-primary"
                    />
                  </label>
                ))}
              </div>
            </section>
          )}

          <section>
            <p className={LABEL}>1 · Did the call connect?</p>
            <div className="grid grid-cols-2 gap-2">
              {CONNECT_OPTIONS.map((o) => {
                const Icon = CONNECT_ICON[o.value];
                const selected = draft.manualStatus === o.value;
                const blocked = o.value === "connected" && !!context?.never_connected;
                return (
                  <button
                    key={o.value}
                    type="button"
                    disabled={blocked}
                    title={blocked ? "The call record shows nobody answered" : undefined}
                    onClick={() => onChange(selectConnect(draft, o.value, context))}
                    className={`flex items-center gap-2.5 rounded-2xl border px-3 py-2.5 text-left transition-all disabled:cursor-not-allowed disabled:opacity-40 ${
                      selected ? "border-primary bg-primary text-white shadow-md" : "border-[#e8e3db] bg-[#faf8f5] text-[#44403c] hover:bg-[#f0ece4]"
                    }`}
                  >
                    <Icon size={15} className="shrink-0" />
                    <span className="min-w-0">
                      <span className="block font-label text-xs font-bold">{o.label}</span>
                      <span className={`block font-label text-[10px] ${selected ? "text-white/75" : "text-[#a8a29e]"}`}>{o.hint}</span>
                    </span>
                  </button>
                );
              })}
            </div>
            {provider === "telecmi" && context?.connect_prefill && (
              <p className="mt-2 font-label text-[10px] text-[#a8a29e]">Filled in from the call record. Change it if it&apos;s wrong.</p>
            )}
          </section>

          {noConnect && (
            <section className="rounded-2xl border border-amber-200 bg-amber-50/60 p-4">
              <p className="mb-1 font-label text-[10px] font-extrabold uppercase tracking-wider text-amber-700">Try again</p>
              {streak >= 3 && (
                <p className="mb-2 font-body text-[11px] text-amber-800">{streak} missed calls in a row, so the next try is tomorrow morning.</p>
              )}
              <QuickTimePicker value={draft.nextActionAt} onChange={setTime} now={openedAt} suggested={suggested} />
              <p className="mt-2 font-label text-[10px] text-amber-700/80">Saving adds this to Scheduled Calls.</p>
            </section>
          )}

          {draft.manualStatus === "connected" && (
            <section>
              <p className={LABEL}>2 · What happened?</p>
              <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                {RESULT_OPTIONS.map((o) => {
                  const selected = draft.outcome === o.value;
                  return (
                    <button
                      key={o.value}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => onChange(selectOutcome(draft, o.value))}
                      className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-left font-label text-xs font-bold transition-all ${
                        selected ? `${TONE_CHIP[o.tone]} ring-2 ring-primary/30 ring-offset-1` : "border-[#e8e3db] bg-white text-[#44403c] hover:bg-[#faf8f5]"
                      }`}
                    >
                      <span aria-hidden className="text-base leading-none">{o.emoji}</span>
                      <span>{o.label}</span>
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          {option?.time && (
            <section>
              <p className={LABEL}>{option.timeLabel}{option.time === "required" ? " *" : ""}</p>
              <QuickTimePicker value={draft.nextActionAt} onChange={setTime} now={openedAt} optional={option.time === "optional"} />
            </section>
          )}

          {(draft.outcome === "not_interested" || draft.outcome === "disqualified") && (
            <section>
              <p className={LABEL}>Why? *</p>
              <div className="flex flex-wrap gap-1.5">
                {(draft.outcome === "not_interested" ? NOT_INTERESTED_REASONS : DISQUALIFIED_REASONS).map((r) => (
                  <button key={r.value} type="button" onClick={() => onChange({ ...draft, reason: r.value })} className={chip(draft.reason === r.value)}>
                    {r.label}
                  </button>
                ))}
              </div>
            </section>
          )}

          {draft.outcome === "language_barrier" && (
            <section>
              <p className={LABEL}>Customer&apos;s language *</p>
              <div className="flex flex-wrap gap-1.5">
                {LANGUAGE_OPTIONS.map((l) => (
                  <button key={l.value} type="button" onClick={() => onChange({ ...draft, preferredLanguage: l.value })} className={chip(draft.preferredLanguage === l.value)}>
                    {l.label}
                  </button>
                ))}
              </div>
              <p className="mt-2 font-label text-[10px] text-[#a8a29e]">Your admin gets an alert to hand this lead to someone who speaks it.</p>
            </section>
          )}

          {draft.outcome === "converted" && (
            <section>
              <p className={LABEL}>What was sold? *</p>
              <SalePicker
                mode={draft.saleMode}
                products={draft.products}
                amountRupees={draft.amountRupees}
                catalogItems={catalogItems}
                onChange={(patch) => onChange({ ...draft, ...patch })}
              />
            </section>
          )}

          {draft.outcome === "do_not_call" && (
            <button
              type="button"
              role="checkbox"
              aria-checked={draft.stopMessages}
              onClick={() => onChange({ ...draft, stopMessages: !draft.stopMessages })}
              className="flex w-full items-center gap-2.5 rounded-2xl border border-red-200 bg-red-50/60 px-3 py-2.5 text-left font-body text-xs font-semibold text-red-800"
            >
              <TickMark checked={draft.stopMessages} size="sm" />
              Also stop WhatsApp/SMS
            </button>
          )}

          <section>
            <label htmlFor="wrapup-notes" className={LABEL}>Notes{option?.notes ? " *" : ""}</label>
            <textarea
              id="wrapup-notes"
              value={draft.notes}
              onChange={(e) => onChange({ ...draft, notes: e.target.value })}
              placeholder="What did the customer say? Need, budget, next step…"
              rows={3}
              className="w-full resize-none rounded-2xl border border-[#e8e3db] bg-[#faf8f5] px-4 py-3 font-body text-xs shadow-inner focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </section>
        </div>

        <div className="space-y-2 border-t border-[#f0ece4] px-5 py-4 pb-[calc(1rem+env(safe-area-inset-bottom,0px))] sm:px-7 sm:pb-5">
          {problem && draft.manualStatus && <p className="text-center font-label text-[11px] text-[#a8a29e]">{problem}</p>}
          <button
            type="button"
            onClick={onSubmit}
            disabled={saving || !!problem}
            className="flex w-full items-center justify-center gap-1.5 rounded-2xl bg-primary py-3 font-label text-xs font-black text-white shadow-md transition-all hover:scale-[1.01] hover:bg-primary-dark active:scale-[0.99] disabled:opacity-50"
          >
            {saving ? <RefreshCw size={14} className="animate-spin" /> : <Check size={14} />}
            <span>Save wrap-up</span>
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Rewrite `CockpitModals.tsx` (whole file)**

```tsx
// frontend/app/dashboard/telecalling/components/CockpitModals.tsx
"use client";
import { AlertCircle, Copy, Phone, RefreshCw, Send, X } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { toast } from "sonner";
import { formatPhone } from "@/lib/utils";
import { pendingCallLabel } from "../lib/feedbackLabels";
import type { CallingCockpit } from "../lib/useCallingCockpit";
import WrapupModal from "./wrapup/WrapupModal";

/**
 * Shared overlays for the calling cockpit: accidental-dial guard, SIM desktop handoff, the
 * mandatory two-tap wrap-up and the blocking pending-wrap-ups list. All state comes from
 * useCallingCockpit; the blocking list only renders when `blockingWrapups` is on.
 */
export default function CockpitModals({ cockpit }: { cockpit: CallingCockpit }) {
  const {
    dialCountdown,
    dialTarget,
    cancelDial,
    showWrapupModal,
    activeCallCtx,
    wrapupDraft,
    setWrapupDraft,
    wrapupContext,
    catalogItems,
    wrapupSaving,
    handleWrapupSubmit,
    pendingWrapups,
    openWrapupFromLog,
    blockingWrapups,
    simHandoffLead,
    setSimHandoffLead,
    simHandoffSending,
    sendSimHandoffToMobile,
    activeCallProvider,
    wrapupStartedAt,
    setWrapupStartedAt,
    wrapupEndedAt,
    setWrapupEndedAt,
  } = cockpit;

  const simHandoffUrl = simHandoffLead && typeof window !== "undefined"
    ? `${window.location.origin}/aira/dashboard/telecalling?lead_id=${simHandoffLead.id}`
    : "";

  const copySimNumber = async () => {
    if (!simHandoffLead?.phone) return;
    try {
      await navigator.clipboard.writeText(simHandoffLead.phone);
      toast.success("Phone number copied");
    } catch {
      toast.error("Could not copy phone number");
    }
  };

  return (
    <>
      {/* Accidental-dial guard countdown */}
      {dialCountdown !== null && dialTarget && (
        <div className="fixed inset-0 bg-[#1c1917]/70 backdrop-blur-sm flex items-center justify-center z-[70]">
          <div className="bg-white rounded-3xl p-8 max-w-sm w-full mx-4 shadow-2xl border border-[#e8e3db] text-center animate-in fade-in zoom-in-95">
            <div className="w-16 h-16 bg-[var(--primary-50)] text-[var(--primary-800)] rounded-full flex items-center justify-center mx-auto mb-4 animate-bounce">
              <Phone size={24} />
            </div>
            <h3 className="font-display text-lg font-bold text-[#292524]">Calling in {dialCountdown}s...</h3>
            <p className="font-body text-sm text-[#78716c] mt-1.5">
              Target: {"lead" in dialTarget ? dialTarget.lead?.name || dialTarget.lead?.phone : dialTarget.phone}
            </p>
            <button
              onClick={cancelDial}
              className="mt-6 w-full py-3 bg-red-50 hover:bg-red-100 text-red-600 font-label text-sm font-bold rounded-2xl transition-all border border-red-200"
            >
              Cancel Dial
            </button>
          </div>
        </div>
      )}

      {/* SIM Basic desktop handoff */}
      {simHandoffLead && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-[#1c1917]/75 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md overflow-hidden rounded-3xl border border-[#e8e3db] bg-white shadow-2xl animate-in fade-in zoom-in-95">
            <div className="flex items-start justify-between gap-4 border-b border-[#f0ece4] px-6 py-5">
              <div>
                <span className="rounded-full bg-primary-light px-3 py-1 font-label text-[10px] font-black uppercase tracking-wider text-primary">
                  SIM Basic
                </span>
                <h3 className="mt-3 font-display text-xl font-extrabold text-[#1c1917]">Open this lead on mobile</h3>
                <p className="mt-1 font-body text-sm leading-relaxed text-[#78716c]">
                  This tenant uses SIM calling. Open this lead on your phone to call using your SIM.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSimHandoffLead(null)}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[#78716c] hover:bg-[#f0ece4] hover:text-[#292524]"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            <div className="space-y-5 px-6 py-5">
              <div className="rounded-2xl border border-[#e8e3db] bg-[#faf8f5] p-4">
                <p className="font-label text-[10px] font-black uppercase tracking-wider text-[#a8a29e]">Lead</p>
                <p className="mt-1 font-display text-base font-bold text-[#1c1917]">{simHandoffLead.name || "Unnamed Lead"}</p>
                <div className="mt-3 flex items-center justify-between gap-3 rounded-xl bg-white px-3 py-2">
                  <span className="font-mono text-sm font-bold text-[#292524]">{formatPhone(simHandoffLead.phone)}</span>
                  <button
                    type="button"
                    onClick={copySimNumber}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[#e8e3db] px-2.5 py-1.5 font-label text-[11px] font-bold text-[#57534e] hover:border-primary-muted hover:text-primary"
                  >
                    <Copy size={12} />
                    Copy
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-center rounded-3xl border border-primary-muted bg-primary-light/40 p-5">
                {simHandoffUrl && (
                  <QRCodeSVG
                    value={simHandoffUrl}
                    size={168}
                    bgColor="#ffffff"
                    fgColor="#1c1917"
                    level="M"
                    includeMargin
                    className="rounded-2xl bg-white p-2 shadow-sm"
                  />
                )}
              </div>

              <button
                type="button"
                onClick={sendSimHandoffToMobile}
                disabled={simHandoffSending}
                className="flex w-full items-center justify-center gap-2 rounded-2xl bg-primary px-4 py-3 font-label text-sm font-black text-white shadow-md transition-all hover:bg-primary-dark disabled:opacity-50"
              >
                {simHandoffSending ? <RefreshCw size={15} className="animate-spin" /> : <Send size={15} />}
                Send to my mobile
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Mandatory two-tap wrap-up */}
      {showWrapupModal && activeCallCtx && (
        <WrapupModal
          callee={activeCallCtx.name || formatPhone(activeCallCtx.phone ?? "") || "this lead"}
          provider={activeCallProvider}
          context={wrapupContext}
          draft={wrapupDraft}
          onChange={setWrapupDraft}
          saving={wrapupSaving}
          onSubmit={handleWrapupSubmit}
          catalogItems={catalogItems}
          simTiming={
            activeCallProvider === "sim_basic"
              ? { startedAt: wrapupStartedAt, endedAt: wrapupEndedAt, setStartedAt: setWrapupStartedAt, setEndedAt: setWrapupEndedAt }
              : null
          }
        />
      )}

      {/* Blocking pending-wrap-ups list (telecaller discipline gate only) */}
      {blockingWrapups && pendingWrapups.length > 0 && !showWrapupModal && (
        <div className="fixed inset-0 bg-[#1c1917]/85 backdrop-blur-md flex items-center justify-center z-[70] p-4 animate-in fade-in">
          <div className="bg-white rounded-3xl p-8 max-w-2xl w-full max-h-[80vh] shadow-2xl flex flex-col border border-[#e8e3db]">
            <div className="text-center mb-6 shrink-0">
              <div className="w-12 h-12 bg-amber-50 border border-amber-200 text-amber-600 rounded-full flex items-center justify-center mx-auto mb-3">
                <AlertCircle size={24} />
              </div>
              <h2 className="font-display text-xl font-extrabold text-[#1c1917]">Action Required: Pending Call Wrap-ups</h2>
              <p className="font-body text-xs text-[#a8a29e] mt-1.5">
                You have {pendingWrapups.length} call(s) that need an outcome. Submit feedback for each to unlock the app.
              </p>
            </div>

            <div className="flex-1 overflow-y-auto space-y-3 mb-2 pr-1">
              {pendingWrapups.map((log) => (
                <div key={log.id} className="border border-[#f0ece4] rounded-2xl p-4 bg-[#faf8f5]/50 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="min-w-0">
                    <p className="font-body text-sm font-bold text-[#292524] truncate">
                      {log.leads?.name || "Unnamed Lead"} ({formatPhone(log.leads?.phone || "")})
                    </p>
                    <p className="font-label text-xs text-[#78716c] mt-1">
                      {pendingCallLabel(log)} · {log.duration_seconds || 0}s · {new Date(log.created_at).toLocaleString()}
                    </p>
                  </div>
                  <button
                    onClick={() => openWrapupFromLog(log)}
                    className="px-4 py-2 bg-primary hover:bg-primary-dark text-white rounded-xl font-label text-xs font-bold transition-all shadow-sm shrink-0"
                  >
                    Wrap Up
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 7: Rewire `useCallingCockpit.ts`.**

(a) Replace the first import line with:

```ts
import { api, Lead, CallLog, Message, TelecallingConfig, type CatalogItem, type WrapupContext } from "@/lib/api";
```

Add after the `import { isMobileDialSurface, openNativeDialer } from "./sim-dialer";` line:

```ts
import { formatIstWhen } from "@/lib/call-wrapup";
import { applyContext, draftError, draftToPayload, emptyDraft, type WrapupDraft } from "./wrapup-draft";
```

(b) Replace the block from `// Mandatory wrap-up` through `const [pendingWrapups, setPendingWrapups] = useState<CallLog[]>([]);` with:

```ts
  // Mandatory wrap-up (two taps, identical for SIM and cloud)
  const [showWrapupModal, setShowWrapupModal] = useState(false);
  const [wrapupDraft, setWrapupDraft] = useState<WrapupDraft>(emptyDraft);
  const [wrapupContext, setWrapupContext] = useState<WrapupContext | null>(null);
  const [catalogItems, setCatalogItems] = useState<CatalogItem[]>([]);
  const catalogLoaded = useRef(false);
  const [wrapupSaving, setWrapupSaving] = useState(false);
  const [wrapupStartedAt, setWrapupStartedAt] = useState("");
  const [wrapupEndedAt, setWrapupEndedAt] = useState("");
  const [pendingWrapups, setPendingWrapups] = useState<CallLog[]>([]);
```

(c) In the live-call polling effect, replace:

```ts
        } else if (log.status === "no_answer" || log.status === "failed") {
          setCallStatus("ended");
          setActiveCallCtx(null);
          clearInterval(pollInterval);
          refreshQueueRef.current();
```

with:

```ts
        } else if (log.status === "no_answer") {
          // Nobody picked up: open the wrap-up pre-filled "Not picked" so the retry gets scheduled.
          setCallStatus("ended");
          setShowWrapupModal(true);
          clearInterval(pollInterval);
        } else if (log.status === "failed") {
          setCallStatus("ended");
          setActiveCallCtx(null);
          clearInterval(pollInterval);
          refreshQueueRef.current();
```

(d) Directly after the `// Call duration timer` effect, add:

```ts
  // Wrap-up context: cloud pre-fill of tap 1 + retry suggestions (refetched once a SIM call gets its log id).
  const wrapLeadId = activeCallCtx?.leadId ?? null;
  const wrapLogId = activeCallCtx?.callLogId ?? null;
  useEffect(() => {
    if (!showWrapupModal) return;
    let cancelled = false;
    api.calls
      .wrapupContext({ leadId: wrapLeadId ?? undefined, callLogId: wrapLogId ?? undefined })
      .then((ctx) => {
        if (cancelled) return;
        setWrapupContext(ctx);
        setWrapupDraft((draft) => applyContext(draft, ctx));
      })
      .catch(() => {
        if (!cancelled) setWrapupContext(null);
      });
    return () => {
      cancelled = true;
    };
  }, [showWrapupModal, wrapLeadId, wrapLogId]);

  // Catalog for "Converted", loaded once the first time a wrap-up opens.
  useEffect(() => {
    if (!showWrapupModal || catalogLoaded.current) return;
    catalogLoaded.current = true;
    api.catalog.listItems().then(setCatalogItems).catch(() => {
      catalogLoaded.current = false;
    });
  }, [showWrapupModal]);
```

(e) Replace `resetWrapup` with:

```ts
  function resetWrapup() {
    setShowWrapupModal(false);
    setWrapupDraft(emptyDraft());
    setWrapupContext(null);
    setWrapupStartedAt("");
    setWrapupEndedAt("");
  }
```

(f) Delete the `toggleWrapupTag` `useCallback` block entirely.

(g) Replace `handleWrapupSubmit` with:

```ts
  async function handleWrapupSubmit() {
    if (!activeCallCtx) return;
    const problem = draftError(wrapupDraft, new Date());
    if (problem) {
      toast.error(problem);
      return;
    }
    setWrapupSaving(true);
    try {
      let callLogId = activeCallCtx.callLogId;
      if (!callLogId) {
        toast.info("Logging call on server first...");
        try {
          const res = await api.calls.initiate(
            {
              leadId: activeCallCtx.leadId ?? undefined,
              phone: activeCallCtx.phone ?? undefined,
              callbackJobId: selectedCallbackJobId ?? undefined,
            },
            callerId ?? undefined,
          );
          callLogId = res.call_log_id;
          setActiveCallCtx({ ...activeCallCtx, callLogId: res.call_log_id });
        } catch (initErr) {
          throw new Error("Failed to create call log on server: " + (initErr instanceof Error ? initErr.message : String(initErr)));
        }
      }

      const isSim = activeCallProvider === "sim_basic";
      const saved = await api.calls.saveWrapup(callLogId, {
        ...draftToPayload(wrapupDraft),
        duration_seconds: isSim ? secondsBetween(wrapupStartedAt, wrapupEndedAt) : undefined,
        manual_started_at: isSim ? inputToIso(wrapupStartedAt) : undefined,
        manual_ended_at: isSim ? inputToIso(wrapupEndedAt) : undefined,
      });
      const notes = wrapupDraft.notes.trim();
      if (notes && activeCallCtx.leadId) {
        await saveNote(activeCallCtx.leadId, notes, false, []);
      }

      toast.success(
        saved.next_action_at
          ? `Wrap-up saved · reminder ${formatIstWhen(new Date(saved.next_action_at), new Date())}`
          : "Wrap-up saved",
      );
      resetWrapup();
      setActiveCallProvider("telecmi");
      setActiveCallCtx(null);
      refreshQueueRef.current();
      loadCallbacks();
      loadPendingWrapups();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to submit wrap-up");
    } finally {
      setWrapupSaving(false);
    }
  }
```

(h) In the returned object, replace the lines from `wrapupOutcome,` through `setWrapupCallbackTime,` (keeping everything else) with:

```ts
    wrapupDraft,
    setWrapupDraft,
    wrapupContext,
    catalogItems,
    wrapupStartedAt,
    setWrapupStartedAt,
    wrapupEndedAt,
    setWrapupEndedAt,
```

`handleQuickOutcome` stays for now (Task 11 removes it together with the card that calls it).

- [ ] **Step 8: Run tests, typecheck and lint**

Run (from `frontend/`): `npx vitest run app/dashboard/telecalling/lib/wrapup-draft.test.ts lib/call-wrapup.test.ts && npm run typecheck && npm run lint`
Expected: all vitest pass; typecheck exit 0; lint `✔ No ESLint warnings or errors`.

- [ ] **Step 9: Commit**

```bash
git add frontend/app/dashboard/telecalling/lib/wrapup-draft.ts frontend/app/dashboard/telecalling/lib/wrapup-draft.test.ts frontend/app/dashboard/telecalling/components/wrapup/QuickTimePicker.tsx frontend/app/dashboard/telecalling/components/wrapup/SalePicker.tsx frontend/app/dashboard/telecalling/components/wrapup/WrapupModal.tsx frontend/app/dashboard/telecalling/components/CockpitModals.tsx frontend/app/dashboard/telecalling/lib/useCallingCockpit.ts
git commit -m "feat(telecalling): two-tap wrap-up form for SIM and cloud calls" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- frontend/app/dashboard/telecalling/lib/wrapup-draft.ts frontend/app/dashboard/telecalling/lib/wrapup-draft.test.ts frontend/app/dashboard/telecalling/components/wrapup/QuickTimePicker.tsx frontend/app/dashboard/telecalling/components/wrapup/SalePicker.tsx frontend/app/dashboard/telecalling/components/wrapup/WrapupModal.tsx frontend/app/dashboard/telecalling/components/CockpitModals.tsx frontend/app/dashboard/telecalling/lib/useCallingCockpit.ts
```

---

### Task 11: Lead page — "Send details on WhatsApp" replaces "Call Outcome"

**Files:**
- Create: `frontend/app/dashboard/telecalling/lib/send-details.ts`
- Test: `frontend/app/dashboard/telecalling/lib/send-details.test.ts`
- Create: `frontend/app/dashboard/telecalling/components/SendDetailsCard.tsx`
- Modify: `frontend/app/dashboard/telecalling/components/LeadDetailPanel.tsx`
- Modify: `frontend/app/dashboard/telecalling/lib/useCallingCockpit.ts` (remove `handleQuickOutcome`)

**Interfaces:**
- Consumes: Task 9 (`api.leads.sendDetailsContext`, `api.leads.sendDetails`, `SendDetailsContext`, `SendDetailsTemplate`; `TONE_DOT`, `callResultKey`, `callResultLabel`, `callResultTone`).
- Produces:
  - `SendDetailsView` (named export) and `SendDetailsCard` (default) with props `{ leadId: string; readOnly?: boolean }`.
  - `send-details.ts` exports `VARIABLE_LABEL`, `templateLabel`, `renderTemplate`, `blankVariables`.
  - `LeadDetailPanelProps` loses `handleQuickOutcome`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/app/dashboard/telecalling/lib/send-details.test.ts
import { describe, expect, it } from "vitest";
import { blankVariables, renderTemplate, templateLabel } from "./send-details";

describe("send details helpers", () => {
  it("renders filled blanks and keeps empty ones visible", () => {
    expect(renderTemplate("Hi {{1}}, from {{2}}. {{3}}", ["Priya", "Astro Tamil", " "])).toBe("Hi Priya, from Astro Tamil. {{3}}");
  });

  it("counts blanks", () => {
    expect(blankVariables(["a", "", "  "])).toBe(2);
  });

  it("names templates with their language", () => {
    expect(templateLabel({ name: "call_details_share", language: "ta" })).toBe("call_details_share · Tamil");
    expect(templateLabel({ name: "promo", language: "xx" })).toBe("promo · xx");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run app/dashboard/telecalling/lib/send-details.test.ts`
Expected: FAIL: cannot resolve `./send-details`.

- [ ] **Step 3: Implement the helpers**

```ts
// frontend/app/dashboard/telecalling/lib/send-details.ts
import type { SendDetailsTemplate, SendDetailsVariable } from "@/lib/api";

export const VARIABLE_LABEL: Record<NonNullable<SendDetailsVariable["role"]>, string> = {
  customer_name: "Customer name",
  business_name: "Business name",
  details: "Details",
  next_step: "Next step",
};

const LANGUAGE_NAME: Record<string, string> = {
  en: "English", en_US: "English", en_GB: "English", ta: "Tamil", hi: "Hindi", te: "Telugu", ml: "Malayalam", kn: "Kannada",
};

export function templateLabel(t: Pick<SendDetailsTemplate, "name" | "language">): string {
  return `${t.name} · ${LANGUAGE_NAME[t.language] ?? t.language}`;
}

export function renderTemplate(body: string, values: string[]): string {
  return body.replace(/\{\{\s*(\d+)\s*\}\}/g, (match, n: string) => {
    const value = values[Number(n) - 1];
    return value && value.trim() ? value : match;
  });
}

export function blankVariables(values: string[]): number {
  return values.filter((v) => !v.trim()).length;
}
```

- [ ] **Step 4: Implement the card**

```tsx
// frontend/app/dashboard/telecalling/components/SendDetailsCard.tsx
"use client";
import { useCallback, useEffect, useState } from "react";
import { MessageCircle, RefreshCw, Send } from "lucide-react";
import { toast } from "sonner";
import { api, type SendDetailsContext, type SendDetailsTemplate } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import { VARIABLE_LABEL, blankVariables, renderTemplate, templateLabel } from "../lib/send-details";

type ReadyContext = Extract<SendDetailsContext, { available: true }>;

export interface SendDetailsViewProps {
  context: ReadyContext;
  sending: boolean;
  readOnly?: boolean;
  onSendText: (text: string) => void;
  onSendTemplate: (template: SendDetailsTemplate, values: string[]) => void;
}

const SEND = "flex items-center justify-center gap-1.5 rounded-xl bg-emerald-600 px-4 py-2 font-label text-xs font-bold text-white shadow-sm transition-all hover:bg-emerald-700 disabled:opacity-50";

/** Presentational: free message inside the 24 h window, otherwise an approved template. */
export function SendDetailsView({ context, sending, readOnly = false, onSendText, onSendTemplate }: SendDetailsViewProps) {
  const [text, setText] = useState(context.free_text);
  const [templateId, setTemplateId] = useState(context.templates[0]?.id ?? "");
  const template = context.templates.find((t) => t.id === templateId) ?? null;
  const [values, setValues] = useState<string[]>(template ? template.variables.map((v) => v.value) : []);
  const blanks = template ? blankVariables(values) : 0;

  function pickTemplate(id: string) {
    setTemplateId(id);
    const next = context.templates.find((t) => t.id === id);
    setValues(next ? next.variables.map((v) => v.value) : []);
  }

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-3 rounded-2xl border border-[#e8e3db] bg-white p-4 shadow-sm">
      <h3 className="flex items-center gap-1.5 font-display text-xs font-black uppercase tracking-widest text-[#292524]">
        <MessageCircle size={12} className="text-emerald-500" /> Send details on WhatsApp
      </h3>
      <span
        className={`inline-flex items-center gap-1.5 self-start rounded-full border px-2 py-0.5 font-label text-[9px] font-bold ${
          context.window_open ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-700"
        }`}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${context.window_open ? "bg-emerald-500" : "bg-amber-500"}`} />
        {context.window_open
          ? `Free message · customer wrote ${context.last_inbound_at ? timeAgo(context.last_inbound_at) : "recently"}`
          : "Template needed · no message from the customer in 24 h"}
      </span>

      {context.window_open ? (
        <>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={7}
            aria-label="Message"
            className="w-full resize-none rounded-xl border border-[#e8e3db] bg-[#faf8f5]/40 p-3 font-body text-xs leading-relaxed transition-all focus:bg-white focus:outline-none focus:ring-2 focus:ring-emerald-300"
          />
          <button type="button" disabled={readOnly || sending || !text.trim()} onClick={() => onSendText(text.trim())} className={SEND}>
            {sending ? <RefreshCw size={12} className="animate-spin" /> : <Send size={12} />} Send
          </button>
        </>
      ) : context.templates.length === 0 ? (
        <p className="rounded-xl border border-dashed border-[#e8e3db] bg-[#faf8f5] p-3 font-body text-[11px] leading-relaxed text-[#78716c]">
          No approved templates yet. Add one under Templates (for example <span className="font-semibold">call_details_share</span>) and it shows here once Meta approves it.
        </p>
      ) : (
        <>
          <select
            value={templateId}
            onChange={(e) => pickTemplate(e.target.value)}
            aria-label="Template"
            className="w-full rounded-xl border border-[#e8e3db] bg-white px-3 py-2 font-body text-xs text-[#44403c] focus:outline-none focus:ring-2 focus:ring-emerald-300"
          >
            {context.templates.map((t) => (
              <option key={t.id} value={t.id}>{templateLabel(t)}</option>
            ))}
          </select>
          {template?.variables.map((v, i) => (
            <label key={v.key} className="block">
              <span className="mb-1 block font-label text-[9px] font-black uppercase tracking-wider text-[#a8a29e]">
                {`{{${v.key}}}`} · {v.role ? VARIABLE_LABEL[v.role] : "Fill this in"}
              </span>
              <input
                value={values[i] ?? ""}
                onChange={(e) => setValues((prev) => prev.map((x, j) => (j === i ? e.target.value : x)))}
                className={`w-full rounded-lg border px-2.5 py-1.5 font-body text-xs focus:outline-none focus:ring-2 focus:ring-emerald-300 ${
                  (values[i] ?? "").trim() ? "border-[#e8e3db] bg-white" : "border-amber-300 bg-amber-50/50"
                }`}
              />
            </label>
          ))}
          {template && (
            <div className="whitespace-pre-wrap rounded-xl border border-emerald-100 bg-[#dcf8c6]/60 p-3 font-body text-[11px] leading-relaxed text-[#292524]">
              {renderTemplate(template.body_text, values)}
            </div>
          )}
          <button
            type="button"
            disabled={readOnly || sending || !template || blanks > 0}
            onClick={() => template && onSendTemplate(template, values)}
            className={SEND}
          >
            {sending ? <RefreshCw size={12} className="animate-spin" /> : <Send size={12} />}
            {blanks > 0 ? `Fill ${blanks} blank${blanks === 1 ? "" : "s"}` : "Send template"}
          </button>
        </>
      )}
      <p className="font-label text-[10px] text-[#a8a29e]">Sends from your business number and shows in Conversations.</p>
    </div>
  );
}

/** Lead page card. Hidden when the tenant has no WhatsApp or the lead opted out. */
export default function SendDetailsCard({ leadId, readOnly = false }: { leadId: string; readOnly?: boolean }) {
  const [context, setContext] = useState<SendDetailsContext | null>(null);
  const [sending, setSending] = useState(false);

  const load = useCallback(() => {
    api.leads.sendDetailsContext(leadId).then(setContext).catch(() => setContext({ available: false }));
  }, [leadId]);

  useEffect(() => {
    setContext(null);
    load();
  }, [load]);

  if (!context || !context.available) return null;

  async function send(body: { text: string } | { template_id: string; variables: string[] }) {
    setSending(true);
    try {
      await api.leads.sendDetails(leadId, body);
      toast.success("Sent on WhatsApp. It's in Conversations.");
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "WhatsApp didn't send it");
    } finally {
      setSending(false);
    }
  }

  return (
    <SendDetailsView
      key={leadId}
      context={context}
      sending={sending}
      readOnly={readOnly}
      onSendText={(text) => void send({ text })}
      onSendTemplate={(template, values) => void send({ template_id: template.id, variables: values })}
    />
  );
}
```

- [ ] **Step 5: Edit `LeadDetailPanel.tsx`.**

(a) Imports. After `import { SegmentBadge } from "@/components/segment-badge";` add:

```ts
import SendDetailsCard from "./SendDetailsCard";
import { TONE_DOT, callResultKey, callResultLabel, callResultTone } from "@/lib/call-wrapup";
```

(b) Change `export const QUICK_NOTE_TAGS = [` to `const QUICK_NOTE_TAGS = [` (nothing else imports it after Task 10).

(c) Delete `handleQuickOutcome: (outcome: string) => void;` from `LeadDetailPanelProps` and `handleQuickOutcome,` from the destructuring.

(d) Delete the whole `outcomeStyle` and `outcomeLabel` object literals (the `// Call attempt trail` block). Leave `const recentCallLogs = ...` in place.

(e) In `timelineItems`, change the call mapper to:

```ts
    ...selectedLeadCallLogs.map(l => ({
      type: "call" as const, id: l.id, created_at: l.created_at,
      outcome: l.outcome, manual_status: l.manual_status, duration_seconds: l.duration_seconds,
    })),
```

(f) Replace the opening `<div className="grid grid-cols-2 gap-3">` of the "Quick Note + Call Outcome" block with `<div className="flex flex-col gap-3 lg:flex-row lg:items-stretch">`. Change the Quick Note card's class from `bg-white border border-[#e8e3db] rounded-2xl p-4 shadow-sm flex flex-col gap-3` to `min-w-0 flex-1 bg-white border border-[#e8e3db] rounded-2xl p-4 shadow-sm flex flex-col gap-3`. Then replace the entire Call Outcome card (the `<div ...>` containing `<Phone size={12} className="text-orange-400" /> Call Outcome` and its button grid, through its closing `</div>`) with:

```tsx
              <SendDetailsCard leadId={selectedLead.id} readOnly={readOnly} />
```

Also change the comment `{/* ── Quick Note + Call Outcome ── */}` to `{/* ── Quick Note + Send details on WhatsApp ── */}`.

(g) In the Call History dots, replace the two lines using `outcomeStyle`/`outcomeLabel` with:

```tsx
                        <div className={`w-6 h-6 rounded-full ring-2 ring-offset-1 ring-[#f0ece4] ${TONE_DOT[callResultTone(callResultKey(log))]} cursor-default shadow-sm`} />
```

and

```tsx
                          {callResultLabel(callResultKey(log)) ?? "Not wrapped up"} · {timeAgo(log.created_at)}
```

(h) In both timeline call rows replace `{outcomeLabel[item.outcome ?? ""] ?? "Call logged"}` with `{callResultLabel(callResultKey(item)) ?? "Call logged"}`, and replace `{outcomeLabel[log.outcome ?? ""] ?? "Call logged"}` with `{callResultLabel(callResultKey(log)) ?? "Call logged"}`.

- [ ] **Step 6: Remove the quick-outcome path from `useCallingCockpit.ts`.**

Delete the whole `async function handleQuickOutcome(outcome: string) { ... }` and the `handleQuickOutcome,` entry in `leadDetailProps`. Confirm with `grep -rn "handleQuickOutcome\|api.calls.setOutcome\|leads.convert" frontend/app/dashboard/telecalling`, which should print nothing.

- [ ] **Step 7: Run tests, typecheck and lint**

Run (from `frontend/`): `npx vitest run app/dashboard/telecalling/lib/send-details.test.ts && npm run typecheck && npm run lint`
Expected: 3 passed; typecheck exit 0; lint clean.

- [ ] **Step 8: Commit**

```bash
git add frontend/app/dashboard/telecalling/lib/send-details.ts frontend/app/dashboard/telecalling/lib/send-details.test.ts frontend/app/dashboard/telecalling/components/SendDetailsCard.tsx frontend/app/dashboard/telecalling/components/LeadDetailPanel.tsx frontend/app/dashboard/telecalling/lib/useCallingCockpit.ts
git commit -m "feat(telecalling): Send details on WhatsApp card replaces the Call Outcome card" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- frontend/app/dashboard/telecalling/lib/send-details.ts frontend/app/dashboard/telecalling/lib/send-details.test.ts frontend/app/dashboard/telecalling/components/SendDetailsCard.tsx frontend/app/dashboard/telecalling/components/LeadDetailPanel.tsx frontend/app/dashboard/telecalling/lib/useCallingCockpit.ts
```

---

### Task 12: Frontend readers + remove the old types

**Files (all Modify):**
- `frontend/lib/api.ts`
- `frontend/components/CallAi.tsx`
- `frontend/app/dashboard/telecalling/components/RecentCallsTab.tsx`
- `frontend/app/dashboard/telecalling/components/sections/QaReviewFeed.tsx`
- `frontend/app/dashboard/telecalling/components/sections/ShiftTimeline.tsx`
- `frontend/app/dashboard/telecalling/components/sections/OutcomeBreakdown.tsx`
- `frontend/app/dashboard/telecalling/components/sections/BulkAssignment.tsx`
- `frontend/app/dashboard/telecalling/components/sections/LeadProfileModal.tsx`
- `frontend/app/dashboard/telecalling/AdminView.tsx`
- `frontend/app/dashboard/telecalling/CallerView.tsx`
- `frontend/app/dashboard/telecalling/scheduled/page.tsx`
- `frontend/app/dashboard/notes/components/shared.tsx`
- `frontend/app/dashboard/notes/NotesClient.tsx`
- `frontend/app/dashboard/profile/ProfileClient.tsx`
- `frontend/app/dashboard/team/TeamProfilePanel.tsx`
- `frontend/app/operator/(console)/client/[id]/views/telecalling.tsx`

**Interfaces:**
- Consumes: `@/lib/call-wrapup` (Task 9).
- Produces: in `@/lib/api`:
  - `CallLog.outcome: CallResult | null`, `CallLog.manual_status?: CallConnect | null`, `Lead.call_status?: LeadCallStatus | null`.
  - Analytics types keyed by the new values.
  - `CallOutcome`, `ManualCallStatus`, `Disposition`, `CallLog.quality_rating`, `api.calls.setOutcome` and `api.calls.setDisposition` are removed.

This task has no new unit test: TypeScript is the test. Narrowing the types makes every stale reader a compile error.

- [ ] **Step 1: Narrow the types first (the failing check).** In `frontend/lib/api.ts`:
- Line 40: `call_status?: LeadCallStatus | null;`
- Delete the three lines `export type Disposition = ...`, `export type ManualCallStatus = ...` and `export type CallOutcome = ...`.
- In `CallLog`: `outcome: CallResult | null;`, `manual_status?: CallConnect | null;`, and delete `quality_rating: number | null;`.
- In `TelecallingAnalytics`:
  - `outcome_breakdown: Record<CallResult, number>;`
  - `manual_status_breakdown?: Record<CallConnect, number>;`
- In `TelecallingAnalyticsExtended`:
  - Delete `not_picked_calls?`, `busy_calls?`, `wrong_number_calls?`, `interested_leads?` and `manual_status_all_time_breakdown?`.
  - Set `outcome_breakdown: Record<CallResult, number>;` and `manual_status_breakdown: Record<CallConnect, number>;`.
- In `api.calls`: delete `setOutcome: (...) => ...` and `setDisposition: (...) => ...` entirely.

Run: `npm run typecheck`
Expected: FAIL with errors in the reader files listed above. The typical errors are "This comparison appears to be unintentional because the types 'CallResult' and '"interested"' have no overlap" and "Property 'no_answer' does not exist". This is the failing test.

- [ ] **Step 2: `components/CallAi.tsx`, the admin-only correction note.**
- Add the imports `import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";` and `import { TEMPERATURE_LABEL } from "@/lib/call-wrapup";`.
- In `RealConversationCard`, make the first lines:

```tsx
function RealConversationCard({ log }: { log: CallLog }) {
  const { role, permissions } = useAuthRole();
  const evaluation = log.evaluation;
```

- Directly after the closing `</div>` of the score header row (the `flex items-center gap-3` block), insert:

```tsx
      {evaluation?.crm_correction && (role === "owner" || permissions.includes("team.manage")) && (
        <p className="flex items-center gap-1.5 rounded-lg border border-indigo-100 bg-indigo-50 px-2.5 py-1.5 font-label text-[11px] font-bold text-indigo-800">
          <Sparkles size={12} className="shrink-0" />
          AI changed {TEMPERATURE_LABEL[evaluation.crm_correction.from]} → {TEMPERATURE_LABEL[evaluation.crm_correction.to]}
          <span className="font-semibold text-indigo-700/70">· from the recording</span>
        </p>
      )}
```

- [ ] **Step 3: `RecentCallsTab.tsx`.**
- Delete the `OUTCOME_LABEL` and `OUTCOME_CHIP` constants.
- Add `import { TONE_CHIP, callResultKey, callResultLabel, callResultTone } from "@/lib/call-wrapup";`.
- Replace `const outcome = log.outcome ?? "";` with `const resultKey = callResultKey(log);`.
- Replace the chip block with:

```tsx
                {resultKey && (
                  <span className={`shrink-0 px-2 py-0.5 rounded-full border font-label text-[9px] font-bold ${TONE_CHIP[callResultTone(resultKey)]}`}>
                    {callResultLabel(resultKey) ?? resultKey}
                  </span>
                )}
```

- [ ] **Step 4: `QaReviewFeed.tsx`.**
- Delete the `OUTCOME_LABEL` constant.
- Add `import { callResultKey, callResultLabel } from "@/lib/call-wrapup";`.
- Replace `{log.outcome ? \` · ${OUTCOME_LABEL[log.outcome] ?? log.outcome}\` : ""}` with `{callResultLabel(callResultKey(log)) ? \` · ${callResultLabel(callResultKey(log))}\` : ""}`.

- [ ] **Step 5: `ShiftTimeline.tsx`.** Add `import { TONE_CHIP, TONE_DOT, callResultKey, callResultLabel, callResultTone } from "@/lib/call-wrapup";`. In the bar block replace the five `let color ...` lines with:

```tsx
                  const resultKey = callResultKey(event);
                  const color = `${TONE_DOT[callResultTone(resultKey)]} border-black/10`;
```

Change the title to `` title={`Call (${callResultLabel(resultKey) ?? "not wrapped up"}): ${formatIST(event.started_at)} (${event.duration_seconds || 0}s)\nLead: ${event.lead_name || event.lead_phone}`} ``. In the list chip replace the conditional class chain and text with:

```tsx
                    <span className={`px-2 py-0.5 rounded font-bold text-[9px] uppercase border ${TONE_CHIP[callResultTone(callResultKey(event))]}`}>
                      {callResultLabel(callResultKey(event)) ?? "Not wrapped up"}
                    </span>
```

- [ ] **Step 6: `OutcomeBreakdown.tsx` (whole file).**

```tsx
"use client";

import type { TelecallingAnalyticsExtended } from "@/lib/api";
import { RESULT_OPTIONS, TONE_DOT } from "@/lib/call-wrapup";

export default function OutcomeBreakdown({ stats }: { stats: TelecallingAnalyticsExtended | null }) {
  const ob = stats?.outcome_breakdown;
  const total = ob ? RESULT_OPTIONS.reduce((sum, o) => sum + (ob[o.value] ?? 0), 0) : 0;

  return (
    <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
      <h2 className="font-display text-base font-bold text-primary mb-1">Outcome Breakdown</h2>
      <p className="font-label text-xs text-on-surface-muted mb-5">What happened on connected calls.</p>

      {total === 0 ? (
        <p className="font-body text-sm text-on-surface-muted text-center py-6">No call outcomes in this window.</p>
      ) : (
        <div className="space-y-3">
          {RESULT_OPTIONS.map(({ value, label, tone }) => {
            const count = ob?.[value] ?? 0;
            const pct = Math.round((count / total) * 100);
            return (
              <div key={value} className="flex items-center gap-3">
                <span className="font-label text-xs text-on-surface-muted w-44 shrink-0 truncate" title={label}>{label}</span>
                <div className="flex-1 bg-surface-mid rounded-full h-4 overflow-hidden">
                  <div className={`h-4 rounded-full ${TONE_DOT[tone]} transition-all`} style={{ width: `${pct}%` }} />
                </div>
                <span className="font-label text-xs text-on-surface w-8 text-right shrink-0">{count}</span>
                <span className="font-label text-xs text-on-surface-muted w-8 shrink-0">{pct}%</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 7: Lead-status chips.**

`BulkAssignment.tsx`: add `import { LEAD_STATUS_LABEL, TONE_CHIP, leadStatusTone } from "@/lib/call-wrapup";` and replace the status `<span>` with:

```tsx
                      <span className={`px-1.5 py-0.5 rounded border font-label text-[9px] font-black uppercase ${TONE_CHIP[leadStatusTone(lead.call_status ?? "new")]}`}>
                        {LEAD_STATUS_LABEL[lead.call_status ?? "new"]}
                        {lead.do_not_call ? " (DNC)" : ""}
                      </span>
```

`LeadProfileModal.tsx`: add the same import and replace the `{lead.call_status && (<span ...>{lead.call_status}</span>)}` block with:

```tsx
                      {lead.call_status && (
                        <span className={`px-2 py-0.5 rounded border font-label text-[9px] font-black uppercase ${TONE_CHIP[leadStatusTone(lead.call_status)]}`}>
                          {LEAD_STATUS_LABEL[lead.call_status]}
                        </span>
                      )}
```

- [ ] **Step 8: `AdminView.tsx`.** Add `import { LEAD_CALL_STATUSES, LEAD_STATUS_LABEL, isClosedLeadStatus } from "@/lib/call-wrapup";`.
- Replace the Status filter `opts` array with `opts: [["all", "All"], ...LEAD_CALL_STATUSES.map((s) => [s, LEAD_STATUS_LABEL[s]] as [string, string])]`.
- Replace `} else if (lead.call_status && ["converted", "not_interested", "dnc", "unreachable"].includes(lead.call_status)) {` with `} else if (isClosedLeadStatus(lead.call_status)) {`.

- [ ] **Step 9: `CallerView.tsx`.** Add `import { isClosedLeadStatus, isWorkingLeadStatus } from "@/lib/call-wrapup";`.
- Change the sub-tab state union `"in_progress"` to `"working"` in `useState<...>`.
- In the `lead_id` effect replace the two branches `lead.call_status === "in_progress"` → `isWorkingLeadStatus(lead.call_status)` with `setQueueSubTab("working")`, and `["converted", ...].includes(lead.call_status)` → `isClosedLeadStatus(lead.call_status)`.
- Replace the three filters:

```ts
  const workingLeads = filteredLeads.filter((l) => isWorkingLeadStatus(l.call_status));
  const closedLeads = filteredLeads.filter((l) => isClosedLeadStatus(l.call_status));
```

(delete `inProgressLeads`).
- Change `queueSubTab === "in_progress" ? inProgressLeads :` to `queueSubTab === "working" ? workingLeads :`.
- Change the tab entry to `{ id: "working", label: \`In Prog (${workingLeads.length})\` },`.
- Replace the card accent condition `} else if (lead.call_status && ["converted", "not_interested", "dnc", "unreachable"].includes(lead.call_status)) {` with `} else if (isClosedLeadStatus(lead.call_status)) {`.
- Rename the `CALLBACK` badge text to `CALL LATER`, and `Scheduled callback` to `Customer asked to call later`.

- [ ] **Step 10: `scheduled/page.tsx`.** Add `import { TONE_CHIP, callResultKey, callResultLabel, callResultTone } from "@/lib/call-wrapup";` and replace the chip with:

```tsx
                            <span className={`px-2 py-0.5 rounded border text-[8px] font-bold uppercase ${TONE_CHIP[callResultTone(callResultKey(log))]}`}>
                              {callResultLabel(callResultKey(log)) ?? "Not wrapped up"}
                            </span>
```

- [ ] **Step 11: `notes/components/shared.tsx` and `NotesClient.tsx`.**

In `shared.tsx`:
- Delete `OUTCOME_DOT_COLOR`, `OUTCOME_BADGE_COLOR` and `outcomeBadgeColor`.
- Add `import { TONE_CHIP, TONE_DOT, callResultKey, callResultLabel, callResultTone } from "@/lib/call-wrapup";`.
- Replace `outcomeDotColor` with:

```ts
export function outcomeDotColor(log: Pick<CallLog, "outcome" | "manual_status">): string {
  const key = callResultKey(log);
  return key ? TONE_DOT[callResultTone(key)] : "bg-primary/70";
}
```

- Replace both badge blocks (`{log.outcome && (<span ... outcomeBadgeColor(log.outcome) ...>{log.outcome.replace("_", " ")}</span>)}`) with:

```tsx
            {callResultKey(log) && (
              <span className={`inline-block mt-1 px-2 py-0.5 rounded-full border font-label text-[10px] font-bold ${TONE_CHIP[callResultTone(callResultKey(log))]}`}>
                {callResultLabel(callResultKey(log))}
              </span>
            )}
```

For the second occurrence use the same JSX without `inline-block mt-1`.

In `NotesClient.tsx`, change `color={outcomeDotColor(log.outcome)}` to `color={outcomeDotColor(log)}`.

- [ ] **Step 12: `profile/ProfileClient.tsx`.**
- Delete the `outcomeIcon` and `outcomeLabel` functions. Remove `CheckCircle2,`, `XCircle,`, `PhoneForwarded,` and `Minus,` from the lucide import; lines 92-100 were their only uses.
- Add `import { TONE_DOT, callResultKey, callResultLabel, callResultTone } from "@/lib/call-wrapup";`.
- Replace the cell content with:

```tsx
                      <span className="flex items-center gap-1.5 font-label text-xs">
                        <span className={`h-2 w-2 rounded-full ${TONE_DOT[callResultTone(callResultKey(log))]}`} />
                        {callResultLabel(callResultKey(log)) ?? "—"}
                      </span>
```

- [ ] **Step 13: `team/TeamProfilePanel.tsx`.**
- Delete `OUTCOME_COLORS` and `OUTCOME_LABELS`.
- Add `import { TONE_HEX, callResultKey, callResultLabel, callResultTone } from "@/lib/call-wrapup";`.
- In `outcomeBreakdown` use `const key = callResultKey(l) ?? "unknown";`.
- In the bars use `{callResultLabel(key) ?? "Not wrapped up"}` and `backgroundColor: TONE_HEX[callResultTone(key)]`.
- In the timeline details replace `tev.outcome ? \`${tev.outcome}\` : null` with `callResultLabel(callResultKey(tev))`.

- [ ] **Step 14: operator `views/telecalling.tsx`.** Replace `DISPOSITION_BADGE` with:

```tsx
// Tap 1 of the wrap-up (manual_status) or, for calls not wrapped up, the SIM app's measured disposition.
const CONNECT_BADGE: Record<string, string> = {
  connected: "bg-green-50 text-success",
  answered: "bg-green-50 text-success",
  not_picked: "bg-amber-50 text-warning",
  no_answer: "bg-amber-50 text-warning",
  busy: "bg-red-50 text-danger",
  switched_off: "bg-stone-100 text-ink-muted",
};
```

and update the one usage `DISPOSITION_BADGE[...]` → `CONNECT_BADGE[...]`. Rename the column header `Disposition` → `Connected?`.

- [ ] **Step 15: Verify no reader of removed values remains**

Run from the repo root:

`grep -rnE "\"(in_progress|no_answer|interested|callback|do_not_contact|followup_required)\"|quality_rating|QUICK_NOTE_TAGS|setOutcome|setDisposition|ManualCallStatus|CallOutcome" frontend/app frontend/components frontend/lib --include=*.ts --include=*.tsx`

Expected remaining hits, all legitimate, and nothing else:
- `quality_rating` in `app/dashboard/numbers/page.tsx` and the operator `views/content.tsx`. These are phone-number quality, unrelated.
- `"no_answer"` in `CONNECT_BADGE`. This is the SIM disposition.
- `"callback"` only as `LeadCallStatus` / `follow_up_jobs` cadence uses.
- `QUICK_NOTE_TAGS` only inside `LeadDetailPanel.tsx`.

Run `npm run typecheck && npm run lint`.
Expected: typecheck exit 0; lint clean.

- [ ] **Step 16: Commit**

```bash
git add frontend/lib/api.ts frontend/components/CallAi.tsx frontend/app/dashboard/telecalling/components/RecentCallsTab.tsx frontend/app/dashboard/telecalling/components/sections/QaReviewFeed.tsx frontend/app/dashboard/telecalling/components/sections/ShiftTimeline.tsx frontend/app/dashboard/telecalling/components/sections/OutcomeBreakdown.tsx frontend/app/dashboard/telecalling/components/sections/BulkAssignment.tsx frontend/app/dashboard/telecalling/components/sections/LeadProfileModal.tsx frontend/app/dashboard/telecalling/AdminView.tsx frontend/app/dashboard/telecalling/CallerView.tsx frontend/app/dashboard/telecalling/scheduled/page.tsx frontend/app/dashboard/notes/components/shared.tsx frontend/app/dashboard/notes/NotesClient.tsx frontend/app/dashboard/profile/ProfileClient.tsx frontend/app/dashboard/team/TeamProfilePanel.tsx "frontend/app/operator/(console)/client/[id]/views/telecalling.tsx"
git commit -m "refactor(telecalling): every call and lead view reads wrap-up v2 values; old types removed" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- frontend/lib/api.ts frontend/components/CallAi.tsx frontend/app/dashboard/telecalling/components/RecentCallsTab.tsx frontend/app/dashboard/telecalling/components/sections/QaReviewFeed.tsx frontend/app/dashboard/telecalling/components/sections/ShiftTimeline.tsx frontend/app/dashboard/telecalling/components/sections/OutcomeBreakdown.tsx frontend/app/dashboard/telecalling/components/sections/BulkAssignment.tsx frontend/app/dashboard/telecalling/components/sections/LeadProfileModal.tsx frontend/app/dashboard/telecalling/AdminView.tsx frontend/app/dashboard/telecalling/CallerView.tsx frontend/app/dashboard/telecalling/scheduled/page.tsx frontend/app/dashboard/notes/components/shared.tsx frontend/app/dashboard/notes/NotesClient.tsx frontend/app/dashboard/profile/ProfileClient.tsx frontend/app/dashboard/team/TeamProfilePanel.tsx "frontend/app/operator/(console)/client/[id]/views/telecalling.tsx"
```

---

### Task 13: Migration 209 — map old rows, narrow checks, drop replaced columns (after deploy only)

**Files:**
- Create: `backend/supabase/migrations/209_call_wrapup_v2_narrow.sql`
- Modify: `backend/tests/test_wrapup_v2_migrations.py` (add `Migration209Tests`)

**Interfaces:**
- Consumes: the constants from Task 1 and the live values found in Task 2 Step 1.
- Produces: final DB state. The checks equal exactly the new sets, and `call_logs.wrapup_callback_at` and `call_logs.quality_rating` are gone.

- [ ] **Step 1: Write the failing test** (append the class before `if __name__ == "__main__":`)

```python
class Migration209Tests(unittest.TestCase):
    path = ROOT / "supabase/migrations/209_call_wrapup_v2_narrow.sql"

    def setUp(self):
        self.sql = self.path.read_text(encoding="utf-8")

    def test_checks_are_exactly_the_new_sets(self):
        self.assertEqual(check_values(self.sql, "call_logs_outcome_check"), set(cw.OUTCOMES))
        self.assertEqual(check_values(self.sql, "call_logs_manual_status_check"), set(cw.CONNECTS))
        self.assertEqual(check_values(self.sql, "leads_call_status_check"), set(cw.LEAD_CALL_STATUSES))

    def test_every_old_value_is_mapped_before_narrowing(self):
        upper = self.sql.upper()
        for old in ("'INTERESTED'", "'CALLBACK'", "'NO_ANSWER'", "'IN_PROGRESS'", "'WRONG_NUMBER'", "'NOT_INTERESTED'"):
            self.assertIn(old, upper)
        self.assertLess(upper.index("UPDATE PUBLIC.CALL_LOGS"), upper.index("ADD CONSTRAINT CALL_LOGS_OUTCOME_CHECK"))
        self.assertLess(upper.index("UPDATE PUBLIC.LEADS"), upper.index("ADD CONSTRAINT LEADS_CALL_STATUS_CHECK"))

    def test_replaced_columns_are_dropped_after_copying_callback_times(self):
        self.assertIn("next_action_at = wrapup_callback_at", self.sql)
        self.assertIn("DROP COLUMN IF EXISTS wrapup_callback_at", self.sql)
        self.assertIn("DROP COLUMN IF EXISTS quality_rating", self.sql)
```

- [ ] **Step 2: Run to verify it fails**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_wrapup_v2_migrations.py -v`
Expected: the three `Migration209Tests` FAIL with `FileNotFoundError`.

- [ ] **Step 3: Write the migration.** If Task 2 Step 1 found extra live values or a function/view hit, add their mapping or fix here.

```sql
-- 209_call_wrapup_v2_narrow.sql
-- Call wrap-up v2, step 2 of 2. Apply ONLY AFTER the new code is deployed (the old
-- code writes values this migration removes). Maps old rows, narrows the checks to
-- the new sets, and drops the replaced columns.

-- Tap 2 (outcome): old business outcomes -> new; no_answer was never a human result.
UPDATE public.call_logs SET outcome = 'interested_needs_time' WHERE outcome = 'interested';
UPDATE public.call_logs SET outcome = 'call_later' WHERE outcome = 'callback';
UPDATE public.call_logs SET outcome = NULL WHERE outcome = 'no_answer';

-- Old SIM wrap-ups put the result in manual_status: move it to outcome, tap 1 = connected.
UPDATE public.call_logs
SET outcome = COALESCE(outcome, CASE manual_status
      WHEN 'interested' THEN 'interested_needs_time'
      WHEN 'not_interested' THEN 'not_interested'
      WHEN 'callback' THEN 'call_later'
      WHEN 'wrong_number' THEN 'wrong_number'
    END),
    manual_status = 'connected'
WHERE manual_status IN ('interested', 'not_interested', 'callback', 'wrong_number');

UPDATE public.call_logs
SET next_action_at = wrapup_callback_at
WHERE next_action_at IS NULL AND wrapup_callback_at IS NOT NULL;

UPDATE public.leads SET call_status = 'trying' WHERE call_status = 'in_progress';

ALTER TABLE public.call_logs DROP CONSTRAINT IF EXISTS call_logs_outcome_check;
ALTER TABLE public.call_logs ADD CONSTRAINT call_logs_outcome_check CHECK (
  outcome IS NULL OR outcome IN (
    'interested_booked', 'interested_needs_time', 'maybe_later', 'call_later', 'converted',
    'not_interested', 'disqualified', 'wrong_number', 'language_barrier', 'do_not_call'));

ALTER TABLE public.call_logs DROP CONSTRAINT IF EXISTS call_logs_manual_status_check;
ALTER TABLE public.call_logs ADD CONSTRAINT call_logs_manual_status_check CHECK (
  manual_status IS NULL OR manual_status IN ('connected', 'not_picked', 'busy', 'switched_off'));

ALTER TABLE public.leads DROP CONSTRAINT IF EXISTS leads_call_status_check;
ALTER TABLE public.leads ADD CONSTRAINT leads_call_status_check CHECK (
  call_status IN (
    'new', 'trying', 'unreachable', 'hot', 'warm', 'cold', 'callback', 'converted',
    'not_interested', 'disqualified', 'wrong_number', 'language_barrier', 'dnc'));

ALTER TABLE public.call_logs
  DROP COLUMN IF EXISTS wrapup_callback_at,
  DROP COLUMN IF EXISTS quality_rating;
```

- [ ] **Step 4: Run tests**

Run: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest tests/test_wrapup_v2_migrations.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/supabase/migrations/209_call_wrapup_v2_narrow.sql backend/tests/test_wrapup_v2_migrations.py
git commit -m "feat(db): 209 map old wrap-up values, narrow checks, drop replaced columns (post-deploy)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/supabase/migrations/209_call_wrapup_v2_narrow.sql backend/tests/test_wrapup_v2_migrations.py
```

- [ ] **Step 6 (controller hand-off, after the deploy only):**
  1. Before applying, run `select outcome, manual_status, count(*) from call_logs group by 1,2;` and `select call_status, count(*) from leads group by 1;` and record the counts.
  2. Apply via Supabase MCP `apply_migration` (name `209_call_wrapup_v2_narrow`).
  3. Re-run both queries. Only new values should remain, and the 2 real old rows should show as `interested_needs_time` and SIM `connected`.

---

### Task 14: Full verification, screenshots, docs

**Files:**
- Temporary, never committed: `frontend/app/wrapup-preview/page.tsx`, and the scratch script `<scratchpad>/shoot-wrapup.cjs`.
- Modify: `.agents/context/subsystem-notes.md` (new section before `## Telecalling assignment (services/assignment.py)`)
- Modify: `.agents/decisions/log.md` (append a dated entry)

**Interfaces:**
- Consumes: `WrapupModal`, `SendDetailsView`, `emptyDraft`, `selectConnect`, `selectOutcome`.
- Produces: screenshots for the user and the docs.

- [ ] **Step 1: Full backend suite.** Run from `backend/`: `SUPABASE_URL=https://dummy.supabase.co SUPABASE_SERVICE_KEY=dummy python -m pytest -q`
Expected: every test passes (0 failed).

- [ ] **Step 2: Full frontend checks.** Run from `frontend/`: `npx vitest run && npm run typecheck && npm run lint`
Expected: all vitest files pass; typecheck exit 0; lint clean.

- [ ] **Step 3: Create the temporary preview page** (outside `/dashboard`, so it needs no login; **never commit it**):

```tsx
// frontend/app/wrapup-preview/page.tsx  — TEMPORARY, delete in Step 6
"use client";
import { useState } from "react";
import type { CatalogItem, SendDetailsTemplate, WrapupContext } from "@/lib/api";
import WrapupModal from "../dashboard/telecalling/components/wrapup/WrapupModal";
import { SendDetailsView } from "../dashboard/telecalling/components/SendDetailsCard";
import { emptyDraft, selectConnect, selectOutcome, type WrapupDraft } from "../dashboard/telecalling/lib/wrapup-draft";

const NOW = new Date("2026-09-27T08:30:00Z");
const CLOUD_CTX: WrapupContext = {
  connect_prefill: "not_picked", never_connected: true, failed_before: 0,
  retry_suggestions: { not_picked: "2026-09-27T10:30:00Z", busy: "2026-09-27T09:00:00Z", switched_off: "2026-09-28T04:30:00Z" },
};
const SIM_CTX: WrapupContext = { ...CLOUD_CTX, connect_prefill: null, never_connected: false, failed_before: 2 };
const CATALOG = [
  { id: "i1", name: "Kundli report", price_paise: 9900 },
  { id: "i2", name: "Marriage match", price_paise: 14900 },
] as CatalogItem[];
const TEMPLATES: SendDetailsTemplate[] = [{
  id: "t1", name: "call_details_share", language: "en",
  body_text: "Hi {{1}}, thank you for speaking with {{2}}. Here are the details: {{3}}",
  variables: [
    { key: "1", role: "customer_name", value: "Priya Raman" },
    { key: "2", role: "business_name", value: "Astro Tamil" },
    { key: "3", role: "details", value: "Basic reading ₹49; Premium (Kundli ₹99; Marriage match ₹149)" },
  ],
}];
const FREE_TEXT = "Hi Priya, thank you for your time on the call today.\n\nHere are the details from Astro Tamil:\n\n• Basic reading — ₹49\n  20 minute call\n• Premium\n  • Kundli — ₹99\n  • Marriage match — ₹149\n\nNext step on Friday at 11 AM.";

function connected(outcome: Parameters<typeof selectOutcome>[1], patch: Partial<WrapupDraft> = {}): WrapupDraft {
  return { ...selectOutcome(selectConnect(emptyDraft(), "connected", null), outcome), ...patch };
}

const VARIANTS: Record<string, { draft: WrapupDraft; ctx: WrapupContext; provider: "telecmi" | "sim_basic" }> = {
  sim: { draft: emptyDraft(), ctx: SIM_CTX, provider: "sim_basic" },
  cloud_missed: { draft: selectConnect(emptyDraft(), "not_picked", CLOUD_CTX), ctx: CLOUD_CTX, provider: "telecmi" },
  sim_third_miss: { draft: selectConnect(emptyDraft(), "busy", { ...SIM_CTX, retry_suggestions: { ...SIM_CTX.retry_suggestions, busy: "2026-09-28T04:30:00Z" } }), ctx: SIM_CTX, provider: "sim_basic" },
  booked: { draft: connected("interested_booked", { nextActionAt: "2026-10-02T05:30:00Z", notes: "Demo on Friday with her husband" }), ctx: SIM_CTX, provider: "sim_basic" },
  needs_time: { draft: connected("interested_needs_time"), ctx: SIM_CTX, provider: "sim_basic" },
  maybe_later: { draft: connected("maybe_later"), ctx: SIM_CTX, provider: "sim_basic" },
  call_later: { draft: connected("call_later", { nextActionAt: "2026-09-27T12:30:00Z" }), ctx: SIM_CTX, provider: "sim_basic" },
  converted: { draft: connected("converted", { notes: "Paid by UPI", products: [{ catalogItemId: "i1", name: "Kundli report", qty: 2, pricePaise: 9900 }] }), ctx: SIM_CTX, provider: "sim_basic" },
  not_interested: { draft: connected("not_interested", { reason: "price" }), ctx: SIM_CTX, provider: "sim_basic" },
  disqualified: { draft: connected("disqualified"), ctx: SIM_CTX, provider: "sim_basic" },
  wrong_number: { draft: connected("wrong_number"), ctx: SIM_CTX, provider: "sim_basic" },
  language: { draft: connected("language_barrier", { preferredLanguage: "tamil" }), ctx: SIM_CTX, provider: "sim_basic" },
  dnc: { draft: connected("do_not_call", { stopMessages: true }), ctx: SIM_CTX, provider: "sim_basic" },
};

export default function WrapupPreview({ searchParams }: { searchParams: { v?: string } }) {
  const v = searchParams.v ?? "sim";
  const variant = VARIANTS[v];
  const [draft, setDraft] = useState<WrapupDraft>(variant?.draft ?? emptyDraft());
  const [started, setStarted] = useState("2026-09-27T13:55");
  const [ended, setEnded] = useState("2026-09-27T13:58");

  if (v === "details_free" || v === "details_template") {
    const open = v === "details_free";
    return (
      <main data-preview-ready className="min-h-screen bg-[#faf8f5] p-8">
        <div className="mx-auto flex max-w-xl">
          <SendDetailsView
            context={{ available: true, window_open: open, last_inbound_at: open ? "2026-09-27T06:30:00Z" : "2026-09-24T06:30:00Z", free_text: FREE_TEXT, templates: TEMPLATES }}
            sending={false}
            onSendText={() => {}}
            onSendTemplate={() => {}}
          />
        </div>
      </main>
    );
  }
  return (
    <main data-preview-ready className="min-h-screen bg-[#faf8f5]">
      <WrapupModal
        callee="Priya Raman"
        provider={variant.provider}
        context={variant.ctx}
        draft={draft}
        onChange={setDraft}
        saving={false}
        onSubmit={() => {}}
        catalogItems={CATALOG}
        simTiming={variant.provider === "sim_basic" ? { startedAt: started, endedAt: ended, setStartedAt: setStarted, setEndedAt: setEnded } : null}
        now={NOW}
      />
    </main>
  );
}
```

- [ ] **Step 4: Shoot the screenshots.** Start the frontend: `cd frontend && npm run dev` (run in the background; wait until `Ready`). Write the scratch script `<scratchpad>/shoot-wrapup.cjs`, where `<scratchpad>` is the session scratchpad directory:

```js
// shoot-wrapup.cjs — scratch only, not part of the repo
const { chromium } = require("C:/Users/vskee/Desktop/Aira-Ai/.worktrees/wrapup-v2/frontend/node_modules/@playwright/test");
const OUT = __dirname;
const VARIANTS = ["sim", "cloud_missed", "sim_third_miss", "booked", "needs_time", "maybe_later", "call_later", "converted",
  "not_interested", "disqualified", "wrong_number", "language", "dnc", "details_free", "details_template"];
(async () => {
  const browser = await chromium.launch({ channel: "chrome" });
  for (const [label, viewport] of [["desktop", { width: 1280, height: 900 }], ["mobile", { width: 390, height: 844 }]]) {
    const page = await browser.newPage({ viewport });
    for (const v of VARIANTS) {
      await page.goto(`http://localhost:3000/aira/wrapup-preview?v=${v}`);
      await page.waitForSelector("[data-preview-ready]");
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${OUT}/wrapup-${label}-${v}.png` });
    }
    await page.close();
  }
  await browser.close();
})();
```

Run: `node <scratchpad>/shoot-wrapup.cjs`
Expected: 30 PNGs in the scratchpad.

Open each one with the Read tool and check it against the spec:
- two-tap layout
- cloud pre-fill note
- suggested retry chip
- "3 missed calls in a row" line
- each tap-2 variant's required fields
- sale picker
- DNC checkbox
- free-message and template cards

Also check against the dashboard style: the warm neutrals `#e8e3db`/`#faf8f5`, `rounded-2xl` and `font-label` caps. Fix anything that looks broken or off-style in the component, re-run, and repeat until clean.

- [ ] **Step 5: Real-app smoke test (optional, if a tenant login is available).** Log in on `http://localhost:3000/aira/login` as the UI test account (see `.agents/context/subsystem-notes.md`, "UI test account"). Open Telecalling, pick a lead, and confirm the "Send details on WhatsApp" card replaced "Call Outcome". Do not send anything and do not save a wrap-up against production data.

- [ ] **Step 6: Delete the preview page and confirm nothing temporary is staged.**

Run: `rm -r frontend/app/wrapup-preview && git status --short`
Expected: no `wrapup-preview` entry and no untracked files from this task.

- [ ] **Step 7: Docs.** In `.agents/context/subsystem-notes.md`, insert before `## Telecalling assignment (services/assignment.py)`:

```markdown
## Telecalling — call wrap-up v2 (2026-09-27)
- **One two-tap wrap-up for SIM and cloud.** Tap 1 (`call_logs.manual_status`): connected / not_picked / busy / switched_off. Tap 2 (`call_logs.outcome`, connected only): interested_booked, interested_needs_time, maybe_later, call_later, converted, not_interested, disqualified, wrong_number, language_barrier, do_not_call. Extra columns: `outcome_reason`, `preferred_language`, `next_action_at` (every reminder time; replaced `wrapup_callback_at`), `ai_call_status` (D10).
- **Where the rules live:** `services/call_wrapup.py` (pure rules, labels, retry times, connect rate) → `services/wrapup_apply.py` (all writes) → `PATCH /calls/{id}/outcome`. `GET /calls/wrapup-context` gives the cloud pre-fill and the retry suggestions. Frontend mirror: `lib/call-wrapup.ts` (labels/tones/IST times) and `telecalling/lib/wrapup-draft.ts` (form rules).
- **Retry times are IST, not the browser's zone:** +2h not picked, +30min busy, tomorrow 10:00 IST switched off or 3rd failure in a row. The frontend helpers never read the machine time zone; keep it that way.
- **Nothing automatic writes `outcome` any more.** The TeleCMI CDR and the SIM APK only write status/disposition/duration; a missed cloud call opens the wrap-up pre-filled "Not picked". `leads.call_status`: new, trying (was in_progress), unreachable, hot, warm, cold, callback, converted, not_interested, disqualified, wrong_number, language_barrier, dnc.
- **Converted creates the Won deal itself** (`deals.create_deal`, source `call`, payment_method `other`) before anything else is written; a re-submitted conversion never makes a second deal.
- **D10 (cloud only):** check 10 also votes hot/warm/cold/none; a majority that differs from the telecaller's Hot/Warm/Cold rewrites `leads.call_status` only if it still holds the telecaller's value; `evaluation.crm_correction` drives the admin-only "AI changed Warm → Hot" note.
- **Send details on WhatsApp** (lead page, `services/call_details_share.py`): free text inside 24h, otherwise an approved text-only template on the current WABA; template variables are flattened to one line (Meta rejects new lines). Messages are logged in `messages`, so they show in Conversations. Known templates `call_details_share` / `call_details_next_step` get their blanks pre-filled.
- **Language barrier alert** reuses `call_alerts.type = language_barrier`; if the AI already raised one for the call, the wrap-up rewrites its quote to "Reassign to a {language} speaker" and un-sees it.
```

Append to `.agents/decisions/log.md`:

```markdown
## 2026-09-27 — Call wrap-up v2: one two-tap wrap-up for SIM and cloud
- **Why:** SIM and cloud had different outcome lists, stars/tags nobody used, and "Log the sale" was a separate step; the lead page had a second "Call Outcome" card doing the same job.
- **Decisions (spec `docs/superpowers/specs/2026-09-27-call-wrapup-v2-design.md`, D1–D10):** two taps (connected? → what happened?), notes required for the three interested/converted results, Converted creates the Won deal, IST retry suggestions with the 3-failures rule, the lead-page card became "Send details on WhatsApp", cloud Hot/Warm/Cold is corrected by the AI's majority reading (admin sees it).
- **Interpretations made while planning:** "cancel others" = the normal WhatsApp follow-up re-plan (which cancels every pending reminder); wrong_number and do_not_call cancel every pending follow-up (the number isn't the customer / they asked for no contact). Dial-time and auto-created leads start as `trying`. Connect rate counts only wrapped-up calls.
- **Migrations:** 208 (pre-deploy: new columns, checks widened to old ∪ new) and 209 (post-deploy: old rows mapped — interested→interested_needs_time, callback→call_later, no_answer→NULL, SIM result statuses moved to outcome, in_progress→trying — checks narrowed, `wrapup_callback_at` and `quality_rating` dropped). 207 (scoring cleanup) is separate and still pending.
```

- [ ] **Step 8: Commit the docs**

```bash
git add .agents/context/subsystem-notes.md .agents/decisions/log.md
git commit -m "docs: call wrap-up v2 notes and decision log" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- .agents/context/subsystem-notes.md .agents/decisions/log.md
```

- [ ] **Step 9: Hand back.** Report to the user: test results, the screenshots, and what is waiting on them. Migration 208 must be applied before deploy, and migration 209 after deploy. The owner must submit the `call_details_share` / `call_details_next_step` templates. **Do not push.**

---

## Self-Review

**1. Spec coverage**

| Spec requirement | Task |
|---|---|
| D1 two taps, SIM = cloud | Tasks 5, 10 |
| D2 no stars/tags; Converted creates the deal | Tasks 4, 10 (`CockpitModals` rewrite removes stars/tags/NewDealDialog) |
| D3 Call Outcome card → Send details; no WhatsApp button in the form | Task 11; the form has only notes (Task 10) |
| D4 free vs template, prefill, tap Send, in Conversations | Tasks 8, 11 |
| D5 retry rules incl. the 3-failure rule; the reminder in Scheduled Calls | Tasks 1, 4 (`follow_up_jobs` cadence `callback`), 5, 10 |
| D6 per-option lead effects table | Task 4 (one test per row) |
| D7 quick buttons | Tasks 9, 10 |
| D8 notes required | Tasks 1, 10 |
| D9 language list | Tasks 1, 2, 10 |
| D10 AI correction, admin sees it, SIM unchanged | Tasks 6, 12 (CallAi) |
| §3 cloud pre-fill from CDR, editable | Tasks 1 (`wrapup_context`), 5, 10 (`applyContext`, polling opens the wrap-up on no_answer) |
| §3 pending list / lazy SIM log / keepalive unchanged | Task 5 keeps `pending-wrapups` (plus `manual_status` null); Task 10 keeps the lazy initiate |
| §4 segment untouched; stage events recorded | Task 4 (never writes `segment`; `record_stage_event` tested) |
| §5 hidden without WhatsApp / opted out | Task 8 (`test_hidden_without_whatsapp_or_for_opted_out_leads`) |
| §5 next step "Demo on Friday at 11 AM" style | Tasks 1, 8 (`next_step_phrase` → "Next step on Friday at 11 AM") |
| §6 check-10 mapping + early exit | Task 6 |
| §6 analytics / charts / recent / history / operator labels; connect rate | Tasks 7, 12 |
| §7 columns, checks, migration of the 2 rows | Tasks 2, 13 |
| §9 tests + screenshots | every task; Task 14 |

No gaps found.

**2. Placeholder scan.** No "TBD", "similar to", or "add validation" without code. Every code step has complete code. The consumer edits in Task 12 give the exact replacement JSX.

**3. Type and name consistency** (checked across tasks):
- `apply_wrapup(..., wrapup=, log_extra=, now=)` is the same in Tasks 4 and 5.
- `WrapupContext.retry_suggestions: Record<NoConnect, string>` matches the backend keys.
- `selectConnect` / `selectOutcome` / `applyContext` / `draftError` / `draftToPayload` are used identically in Tasks 10 and 14.
- `callResultKey` returns `string | null` and is used with `callResultLabel` / `callResultTone` everywhere.
- `SendDetailsView` props match the preview page.
- `raise_reassign_alert(db, *, tenant_id, call_log_id, caller_id, language)` matches Task 4's call.
- `crm_correction` shape `{from, to}` is shared by Task 6 and `CallEvaluation`.

**4. Review Focus.** All five items have a pinned test in the owning task (Task 4 resubmit, Task 1/9 past time and 6 PM chip, Task 9/1 IST independence, Task 6 guarded correction, Task 8 flattened variables).

**Notes for the controller:**
- I did not query the live database while planning; Task 2 Step 1 does it before the SQL is final. The value sets in the plan come from repo migrations 102 and 121.
- Two readings of the spec were made and recorded in the decision-log entry:
  - wrong_number cancels every pending follow-up;
  - "cancel others" = the existing WhatsApp follow-up re-plan.

---

