"""Tests for GET /api/v1/analytics/qa-queue — the Team page's QA review feed.

The feed reads the list under `data`, the key every other list endpoint here
uses. This route returned `queue`, so the feed rendered empty no matter how
many scored calls existed (found 2026-09-19 against a real scored call). These
pin the key down, plus the worst-first ordering the feed depends on.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


def _call(call_id: str, overall_score, **extra) -> dict:
    row = {
        "id": call_id,
        "created_at": "2026-09-19T08:03:07+00:00",
        "duration_seconds": 177,
        "recording_url": f"https://storage.test/{call_id}.wav",
        "evaluation": {"overall_score": overall_score, "quality_label": "Good"},
        "caller_id": None,
        "lead_id": "lead-1",
    }
    row.update(extra)
    return row


class QaQueueTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    def _mock_db(self, mock_get_db, rows):
        db = MagicMock()
        (db.table.return_value.select.return_value.eq.return_value
         .not_.is_.return_value.order.return_value.limit.return_value
         .execute.return_value) = MagicMock(data=rows)
        mock_get_db.return_value = db
        return db

    @patch("app.routes.analytics.get_supabase")
    def test_scored_calls_are_returned_under_data(self, mock_get_db):
        """The key the QA feed reads. `queue` left the feed permanently empty."""
        self._mock_db(mock_get_db, [_call("call-1", 7.6)])

        res = self.client.get("/api/v1/analytics/qa-queue")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("data", body)
        self.assertEqual([c["id"] for c in body["data"]], ["call-1"])

    @patch("app.routes.analytics.get_supabase")
    def test_worst_scoring_calls_come_first(self, mock_get_db):
        """It is a review queue: the calls needing attention lead."""
        self._mock_db(mock_get_db, [_call("good", 9.0), _call("bad", 3.0), _call("mid", 6.0)])

        body = self.client.get("/api/v1/analytics/qa-queue").json()

        self.assertEqual([c["id"] for c in body["data"]], ["bad", "mid", "good"])
        self.assertEqual([c["overall_score"] for c in body["data"]], [3.0, 6.0, 9.0])

    @patch("app.routes.analytics.get_supabase")
    def test_calls_without_a_usable_score_are_skipped(self, mock_get_db):
        self._mock_db(mock_get_db, [
            _call("scored", 5.0),
            _call("no-score", None, evaluation={"quality_label": "Good"}),
            _call("not-a-number", None, evaluation={"overall_score": "n/a"}),
            _call("eval-not-a-dict", None, evaluation="broken"),
        ])

        body = self.client.get("/api/v1/analytics/qa-queue").json()

        self.assertEqual([c["id"] for c in body["data"]], ["scored"])

    @patch("app.routes.analytics.get_supabase")
    def test_limit_caps_the_list(self, mock_get_db):
        self._mock_db(mock_get_db, [_call(f"call-{i}", float(i)) for i in range(5)])

        body = self.client.get("/api/v1/analytics/qa-queue?limit=2").json()

        self.assertEqual(len(body["data"]), 2)

    @patch("app.routes.analytics.get_supabase")
    def test_no_scored_calls_returns_an_empty_list(self, mock_get_db):
        self._mock_db(mock_get_db, [])

        body = self.client.get("/api/v1/analytics/qa-queue").json()

        self.assertEqual(body["data"], [])


if __name__ == "__main__":
    unittest.main()
