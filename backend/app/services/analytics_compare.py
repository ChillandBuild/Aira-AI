"""Pure logic for the analytics period-comparison feature.

No DB, no network, no clock reads -- `today` is always passed in so every
function is deterministic and unit-testable. All dates are IST calendar
dates; the caller converts them to timestamptz bounds.
"""

from datetime import date, timedelta

PRESETS = (
    "this_month",
    "last_month",
    "this_week",
    "last_week",
    "last_7d",
    "last_14d",
    "last_30d",
    "custom",
)

# Presets whose natural comparison is the previous *calendar* month rather
# than "the same number of days, immediately before".
_MONTH_PRESETS = ("this_month", "last_month")


def _first_of_month(d: date) -> date:
    return d.replace(day=1)


def _next_month(d: date) -> date:
    return d.replace(day=28) + timedelta(days=4)


def _last_of_month(d: date) -> date:
    return _first_of_month(_next_month(d)) - timedelta(days=1)


def _prev_month(d: date) -> date:
    return _first_of_month(d) - timedelta(days=1)


def resolve_period(
    preset: str | None,
    start: str | None,
    end: str | None,
    today: date,
) -> tuple[date, date]:
    """Resolve a preset (or an explicit start/end pair) to inclusive IST dates."""
    preset = preset or "last_7d"
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset: {preset}")

    if preset == "custom":
        if not start or not end:
            raise ValueError("custom range requires both start and end")
        try:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
        except ValueError as exc:
            raise ValueError("start and end must be YYYY-MM-DD") from exc
        if end_date < start_date:
            raise ValueError("end must not be earlier than start")
        return start_date, end_date

    if preset == "this_month":
        return _first_of_month(today), today
    if preset == "last_month":
        prev = _prev_month(today)
        return _first_of_month(prev), _last_of_month(prev)
    if preset == "this_week":
        return today - timedelta(days=today.weekday()), today
    if preset == "last_week":
        this_monday = today - timedelta(days=today.weekday())
        last_monday = this_monday - timedelta(days=7)
        return last_monday, last_monday + timedelta(days=6)

    days = {"last_7d": 7, "last_14d": 14, "last_30d": 30}[preset]
    return today - timedelta(days=days - 1), today


def previous_period(
    start: date,
    end: date,
    preset: str | None,
) -> tuple[date, date]:
    """The comparison window for a resolved period.

    Month presets compare to the previous calendar month (what a client
    means by "last month"). Everything else compares to the immediately
    preceding block of the same length, which never overlaps the current one.
    """
    if preset in _MONTH_PRESETS:
        prev = _prev_month(start)
        return _first_of_month(prev), _last_of_month(prev)

    span_days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    return prev_end - timedelta(days=span_days - 1), prev_end
