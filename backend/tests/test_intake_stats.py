"""GET /api/v1/intake/stats — the Intake Dashboard numbers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.intake import intake_stats, require_conversations_view, router

app = FastAPI()
app.include_router(router, prefix="/api/v1/intake")
app.dependency_overrides[require_conversations_view] = lambda: {"tenant_id": "t-1"}
client = TestClient(app)


def _db(rows):
    db = MagicMock()
    (db.table.return_value.select.return_value.eq.return_value
       .order.return_value.limit.return_value.execute.return_value).data = rows
    return db


def _iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def test_stats_counts_messages_pending_answered_and_revenue():
    rows = [
        # answered today
        {"status": "paid", "amount_paise": 19900, "paid_at": _iso(0),
         "created_at": _iso(0), "astro_last_reply_id": 5},
        # still waiting, yesterday
        {"status": "paid", "amount_paise": 19900, "paid_at": _iso(1),
         "created_at": _iso(1), "astro_last_reply_id": None},
        # resolved + answered, older than the 14-day window
        {"status": "resolved", "amount_paise": 100, "paid_at": _iso(30),
         "created_at": _iso(30), "astro_last_reply_id": 9},
        # not a consultation yet — must not count as a message
        {"status": "awaiting_payment", "amount_paise": 19900, "paid_at": None,
         "created_at": _iso(0), "astro_last_reply_id": None},
    ]
    with patch("app.routes.intake.get_supabase", return_value=_db(rows)):
        res = client.get("/api/v1/intake/stats")

    assert res.status_code == 200
    body = res.json()
    assert body["totals"] == {
        "messages": 3,
        "answered": 2,
        "pending": 1,
        "awaiting_payment": 1,
        "revenue_inr": 399,
    }
    daily = body["daily"]
    assert len(daily) == 14
    assert daily[-1]["count"] == 1          # answered-today session
    assert daily[-2]["count"] == 1          # yesterday's pending session
    assert sum(d["count"] for d in daily) == 2  # the 30-day-old one is outside the window


def test_stats_is_tenant_scoped_and_survives_an_empty_table():
    db = _db([])
    with patch("app.routes.intake.get_supabase", return_value=db):
        res = client.get("/api/v1/intake/stats")

    assert res.status_code == 200
    assert res.json()["totals"] == {
        "messages": 0, "answered": 0, "pending": 0,
        "awaiting_payment": 0, "revenue_inr": 0,
    }
    db.table.return_value.select.return_value.eq.assert_called_with("tenant_id", "t-1")


def test_stats_reports_fractional_revenue_exactly():
    rows = [{"status": "paid", "amount_paise": 12345, "paid_at": _iso(0),
             "created_at": _iso(0), "astro_last_reply_id": None}]
    with patch("app.routes.intake.get_supabase", return_value=_db(rows)):
        body = client.get("/api/v1/intake/stats").json()
    assert body["totals"]["revenue_inr"] == 123.45
