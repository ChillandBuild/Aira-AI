"""Pure logic for the analytics period-comparison feature.

No DB, no network, no clock reads -- `today` is always passed in so every
function is deterministic and unit-testable. All dates are IST calendar
dates; the caller converts them to timestamptz bounds.
"""

from datetime import date, timedelta
from math import floor

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


def pct_delta(current: float | None, previous: float | None) -> float | None:
    """Whole-number percentage change, or None when there is no baseline.

    Mirrors the existing `_pct_trend` semantics in routes/analytics.py: a
    prior window of zero is not a "% increase", it is new activity, and
    dividing by it would misrepresent that.
    """
    if current is None or previous is None:
        return None
    if previous <= 0:
        return None
    return round((current - previous) / previous * 100)


def fill_days(
    rows: list[dict],
    start: date,
    end: date,
    keys: tuple[str, ...],
) -> list[dict]:
    """Expand sparse aggregate rows into one entry per calendar day.

    The RPCs only emit days that had activity; charts need every day so the
    x-axis does not silently compress quiet periods.
    """
    by_day = {str(r.get("day")): r for r in rows}
    out: list[dict] = []
    cursor = start
    while cursor <= end:
        iso = cursor.isoformat()
        row = by_day.get(iso) or {}
        entry: dict = {"day": iso}
        for key in keys:
            entry[key] = int(row.get(key) or 0)
        out.append(entry)
        cursor += timedelta(days=1)
    return out


def align_series(current: list[dict], previous: list[dict], key: str) -> list[dict]:
    """Pair two day series by position so periods of different lengths overlay.

    July has 31 days and June has 30 -- plotting by calendar date would make
    them incomparable, so both are plotted against "Day N of the period".
    """
    length = max(len(current), len(previous))
    out: list[dict] = []
    for i in range(length):
        cur = current[i] if i < len(current) else None
        prev = previous[i] if i < len(previous) else None
        out.append({
            "index": i + 1,
            "label": f"Day {i + 1}",
            "current_day": cur["day"] if cur else None,
            "current": cur[key] if cur else None,
            "previous_day": prev["day"] if prev else None,
            "previous": prev[key] if prev else None,
        })
    return out


def build_deltas(
    current: dict,
    previous: dict,
    metrics: tuple[str, ...],
) -> dict[str, dict]:
    """Per-metric {current, previous, delta_pct} for the comparison table."""
    out: dict[str, dict] = {}
    for metric in metrics:
        cur = current.get(metric) or 0
        prev = previous.get(metric) or 0
        out[metric] = {
            "current": cur,
            "previous": prev,
            "delta_pct": pct_delta(cur, prev),
        }
    return out


CSV_SERIES_KEYS = ("leads_inbound", "leads_outbound", "messages_in", "messages_out")

CSV_FIELDNAMES = (
    ["day_index", "current_date"]
    + [f"current_{k}" for k in CSV_SERIES_KEYS]
    + ["previous_date"]
    + [f"previous_{k}" for k in CSV_SERIES_KEYS]
)


def compare_csv_rows(series: dict) -> list[dict]:
    """Flatten the aligned series into one CSV row per day index.

    Both periods sit on the same row so the file opens in Excel as a
    ready-made side-by-side comparison. Missing days render as blanks
    rather than zeros -- a day that did not exist is not a day with no
    activity.
    """
    length = max((len(series.get(k) or []) for k in CSV_SERIES_KEYS), default=0)
    rows: list[dict] = []
    for i in range(length):
        first = next(
            (series[k][i] for k in CSV_SERIES_KEYS if i < len(series.get(k) or [])),
            {},
        )
        row: dict = {
            "day_index": first.get("index", i + 1),
            "current_date": first.get("current_day") or "",
            "previous_date": first.get("previous_day") or "",
        }
        for key in CSV_SERIES_KEYS:
            points = series.get(key) or []
            point = points[i] if i < len(points) else {}
            cur = point.get("current")
            prev = point.get("previous")
            row[f"current_{key}"] = "" if cur is None else cur
            row[f"previous_{key}"] = "" if prev is None else prev
        rows.append(row)
    return rows


def _fmt_range(start: date, end: date) -> str:
    if start.year == end.year and start.month == end.month:
        return f"{start.day}–{end.day} {start.strftime('%b %Y')}"
    return f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"


def build_summary(current: dict, previous: dict, start: date, end: date) -> str:
    """A deterministic plain-English paragraph describing the period.

    Template with number slots -- never an LLM call. This text is shown to
    the tenant's own clients, so it must be reproducible and incapable of
    hallucinating a figure.
    """
    leads = int(current.get("new_leads") or 0)
    hot = int(current.get("hot") or 0)
    out = int(current.get("messages_out") or 0)
    ai = int(current.get("ai_replies") or 0)

    parts = [f"Between {_fmt_range(start, end)} you got {leads:,} new leads"]

    delta = pct_delta(leads, previous.get("new_leads") or 0)
    if delta is None:
        parts.append(".")
    else:
        direction = "more" if delta >= 0 else "fewer"
        parts.append(f", {abs(delta)}% {direction} than the previous period.")

    if hot:
        parts.append(f" {hot:,} of them were hot leads.")

    if out:
        # Floor, never round: 1437/1441 rounds to "100%" but 4 replies were
        # human, and telling a client the AI handled everything when it did
        # not is a false claim. Flooring can only understate.
        ai_pct = floor(ai / out * 100)
        parts.append(
            f" The AI sent {out:,} replies and handled {ai_pct}% of them on its own."
        )

    return "".join(parts)
