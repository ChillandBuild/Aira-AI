"""Regression: POST /marketplace/{provider}/token must reach the authed generate
route, not the public webhook route (which would read "token" as the ingest token)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class MarketplaceRouteOrderTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_unauthenticated_generate_hits_auth_guard_not_webhook(self):
        for provider in ("indiamart", "justdial"):
            res = self.client.post(f"/api/v1/marketplace/{provider}/token")
            self.assertEqual(res.status_code, 401)
            self.assertEqual(res.json(), {"detail": "Not authenticated"})

    def test_authenticated_generate_returns_ingest_url(self):
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }
        with patch("app.routes.marketplace_intake.save_setting") as save:
            res = self.client.post("/api/v1/marketplace/indiamart/token")
        self.assertEqual(res.status_code, 200)
        self.assertIn("/api/v1/marketplace/indiamart/", res.json()["ingest_url"])
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
