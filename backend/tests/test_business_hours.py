import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, timezone

from app.services.business_hours import (
    is_within_business_hours,
    describe_hours,
    next_open_description,
)


def _cfg(**overrides):
    base = {
        "enabled": True,
        "timezone": "Asia/Kolkata",
        "open_time": "09:00",
        "close_time": "19:00",
        "working_days": [1, 2, 3, 4, 5, 6],
    }
    base.update(overrides)
    return base


# 2026-07-20 is a Monday. 06:30 UTC == 12:00 IST (in hours).
MON_MIDDAY_UTC = datetime(2026, 7, 20, 6, 30, tzinfo=timezone.utc)
# 2026-07-20 22:00 UTC == 03:30 IST Tuesday (out of hours).
MON_NIGHT_UTC = datetime(2026, 7, 20, 22, 0, tzinfo=timezone.utc)
# 2026-07-19 is a Sunday. 06:30 UTC == 12:00 IST.
SUN_MIDDAY_UTC = datetime(2026, 7, 19, 6, 30, tzinfo=timezone.utc)


def test_inside_window_on_working_day_is_open():
    assert is_within_business_hours(_cfg(), now=MON_MIDDAY_UTC) is True


def test_outside_window_is_closed():
    assert is_within_business_hours(_cfg(), now=MON_NIGHT_UTC) is False


def test_non_working_day_is_closed():
    assert is_within_business_hours(_cfg(), now=SUN_MIDDAY_UTC) is False


def test_disabled_config_is_always_closed():
    assert is_within_business_hours(_cfg(enabled=False), now=MON_MIDDAY_UTC) is False


def test_timezone_is_respected():
    """22:00 UTC is out of hours in IST but inside a 20:00-23:00 UTC window."""
    assert is_within_business_hours(_cfg(), now=MON_NIGHT_UTC) is False
    assert is_within_business_hours(
        _cfg(timezone="UTC", open_time="20:00", close_time="23:00"), now=MON_NIGHT_UTC
    ) is True


def test_midnight_spanning_window():
    # 22:00 UTC == 03:30 IST, inside a 20:00 -> 04:00 window.
    assert is_within_business_hours(
        _cfg(open_time="20:00", close_time="04:00"), now=MON_NIGHT_UTC
    ) is True


def test_equal_open_and_close_is_closed():
    assert is_within_business_hours(
        _cfg(open_time="09:00", close_time="09:00"), now=MON_MIDDAY_UTC
    ) is False


def test_describe_hours_contiguous_days():
    assert describe_hours(_cfg()) == "Monday to Saturday, 9:00 AM to 7:00 PM IST"


def test_describe_hours_non_contiguous_days():
    out = describe_hours(_cfg(working_days=[1, 3, 5]))
    assert out.startswith("Monday, Wednesday, Friday, ")


def test_describe_hours_with_no_working_days():
    assert describe_hours(_cfg(working_days=[])) == "not currently published"


def test_next_open_is_tomorrow_after_close_on_a_working_day():
    # 15:00 UTC == 20:30 IST Monday, after close; Tuesday is a working day.
    after_close = datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)
    assert next_open_description(_cfg(), now=after_close) == "tomorrow"


def test_next_open_is_later_today_before_opening():
    # 02:00 UTC == 07:30 IST Monday, before the 09:00 open.
    before_open = datetime(2026, 7, 20, 2, 0, tzinfo=timezone.utc)
    assert next_open_description(_cfg(), now=before_open) == "later today"


def test_next_open_names_the_day_when_further_out():
    # Saturday 15:00 UTC == 20:30 IST, after close. Sunday is not a working day,
    # so the next opening is Monday.
    sat_evening = datetime(2026, 7, 18, 15, 0, tzinfo=timezone.utc)
    assert next_open_description(_cfg(), now=sat_evening) == "on Monday"


def test_naive_datetime_is_treated_as_utc():
    naive = datetime(2026, 7, 20, 6, 30)
    assert is_within_business_hours(_cfg(), now=naive) is True
