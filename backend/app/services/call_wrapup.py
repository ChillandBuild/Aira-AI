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
