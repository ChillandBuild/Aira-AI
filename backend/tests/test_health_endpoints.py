import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app


ALLOWED_ORIGIN = "https://www.bloommatrix.in"


class HealthEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_is_liveness_and_includes_cors_for_frontend(self):
        res = self.client.get("/health", headers={"Origin": ALLOWED_ORIGIN})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("access-control-allow-origin"), ALLOWED_ORIGIN)
        self.assertEqual(res.json()["status"], "healthy")

    @patch("app.db.supabase.get_supabase")
    def test_ready_reports_dependency_failure_with_cors(self, mock_get_supabase):
        mock_get_supabase.side_effect = RuntimeError("db unavailable")

        res = self.client.get("/ready", headers={"Origin": ALLOWED_ORIGIN})

        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.headers.get("access-control-allow-origin"), ALLOWED_ORIGIN)
        body = res.json()
        self.assertEqual(body["status"], "unhealthy")
        self.assertIn("db unavailable", body["details"]["database"])


if __name__ == "__main__":
    unittest.main()
