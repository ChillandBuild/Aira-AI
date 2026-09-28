"""Regression: GET /api/v1/analytics/overview must survive a single dropped
Supabase connection on its read-only RPC calls.

_RetryTransport (app/db/supabase.py) replays only GET/HEAD/OPTIONS, and
postgrest issues an RPC as a POST -- so the analytics RPCs in this route got
no retry at all and a one-off "Server disconnected" became a 500 with an
"unavailable" card on the tenant's dashboard."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role

IST_OFFSET = timedelta(hours=5, minutes=30)


class _FlakyRpc:
    """One RPC builder whose first execute() drops the connection."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def execute(self):
        self.calls += 1
        if self.calls == 1:
            raise httpx.RemoteProtocolError("Server disconnected")
        return MagicMock(data=self.rows)


class AnalyticsOverviewRpcRetryTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    def _db(self, flaky):
        db = MagicMock()

        leads_tbl = MagicMock()
        leads_chain = leads_tbl.select.return_value.eq.return_value.is_.return_value
        leads_chain.range.return_value.execute.return_value = MagicMock(data=[])
        leads_chain.gte.return_value.lt.return_value.range.return_value.execute.return_value = MagicMock(data=[])

        msgs_tbl = MagicMock()
        msgs_tbl.select.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        db.table.side_effect = lambda name: {"leads": leads_tbl, "messages": msgs_tbl}[name]
        db.rpc.side_effect = lambda name, params: (
            flaky if name == "analytics_daily_messages" else MagicMock(
                execute=MagicMock(return_value=MagicMock(data=[]))
            )
        )
        return db

    @patch("app.routes.analytics.get_supabase")
    def test_dropped_connection_on_daily_messages_rpc_is_retried(self, mock_get_db):
        today_ist = (datetime.now(timezone.utc) + IST_OFFSET).date().isoformat()
        flaky = _FlakyRpc([{"day": today_ist, "inbound": 4, "outbound": 3, "ai": 3, "human": 0}])
        mock_get_db.return_value = self._db(flaky)

        res = self.client.get("/api/v1/analytics/overview?range=7d")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(flaky.calls, 2)
        body = res.json()
        self.assertEqual(body["ai_vs_human"], {"ai": 3, "human": 0})
        today_bucket = next(d for d in body["daily_messages"] if d["day"] == today_ist)
        self.assertEqual(today_bucket["inbound"], 4)


if __name__ == "__main__":
    unittest.main()
