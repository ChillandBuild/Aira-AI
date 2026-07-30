"""Regression guard: analytics must aggregate in SQL, never by pulling raw
message rows. PostgREST caps result sets at 1000 and returns no error, which
silently truncated the 7-day message chart (1250 rows) and the AI/human
counts (579 reported vs 711 actual)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


def _stub_table(name):
    """A table mock that answers every chain shape /overview uses."""
    tbl = MagicMock()
    tbl.select.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(data=[])
    tbl.select.return_value.eq.return_value.is_.return_value.gte.return_value.lt.return_value.execute.return_value = MagicMock(data=[])
    chain = tbl.select.return_value.eq.return_value.eq.return_value.gte.return_value
    chain.execute.return_value = MagicMock(data=[])
    chain.lt.return_value.execute.return_value = MagicMock(data=[])
    # 24h unreplied window: select -> eq -> gte -> limit -> execute
    tbl.select.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
    return tbl


class OverviewUsesSqlAggregationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.analytics.get_supabase")
    def test_overview_never_bulk_selects_message_rows(self, mock_get_db):
        """The only permitted messages read is the bounded 24h unreplied scan,
        which must carry an explicit .limit(). A bare select over the whole
        window is the truncation bug."""
        db = MagicMock()
        message_chains = []

        def table(name):
            tbl = _stub_table(name)
            if name == "messages":
                message_chains.append(tbl)
            return tbl

        db.table.side_effect = table
        db.rpc.return_value.execute.return_value = MagicMock(data=[])
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/analytics/overview?range=30d")
        self.assertEqual(res.status_code, 200)

        for tbl in message_chains:
            self.assertTrue(
                tbl.select.return_value.eq.return_value.gte.return_value.limit.called,
                "any messages read in /overview must be explicitly bounded with .limit()",
            )

    @patch("app.routes.analytics.get_supabase")
    def test_overview_ai_counts_come_from_the_rpc(self, mock_get_db):
        db = MagicMock()
        db.table.side_effect = _stub_table
        db.rpc.return_value.execute.return_value = MagicMock(data=[
            {"day": "2026-07-29", "inbound": 186, "outbound": 256, "ai": 256, "human": 0},
            {"day": "2026-07-30", "inbound": 21, "outbound": 23, "ai": 23, "human": 0},
        ])
        mock_get_db.return_value = db

        body = self.client.get("/api/v1/analytics/overview?range=7d").json()
        self.assertEqual(body["ai_vs_human"], {"ai": 279, "human": 0})


if __name__ == "__main__":
    unittest.main()
