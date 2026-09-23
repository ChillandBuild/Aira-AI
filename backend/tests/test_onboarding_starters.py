"""Tests for POST /api/v1/onboarding/apply-starter -- the zero-AI-calls
fallback for a brand-new self-serve tenant. Covers the clobber guard: it
must refuse to overwrite a tenant's own customised prompt/description
unless force=true, and it must NOT mistake an un-customised tenant (no
ai_prompts row at all) for a customised one.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.routes import onboarding as onboarding_route
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_id

STARTER_ROW = {
    "key": "coaching",
    "master_prompt": "Starter master prompt.",
    "business_description": "Starter business description.",
}


def _table_mock(starter_row=STARTER_ROW, existing_prompt_row=None):
    """A get_supabase() stand-in shaped for apply_starter's three reads:
    vertical_starters (maybe_single), ai_prompts (maybe_single), then an
    upsert; plus save_setting's own db.table("app_settings").upsert() call."""
    db = MagicMock()

    def table(name):
        tbl = MagicMock()
        if name == "vertical_starters":
            tbl.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
                MagicMock(data=starter_row)
            )
        elif name == "ai_prompts":
            tbl.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
                MagicMock(data=existing_prompt_row)
            )
            tbl.upsert.return_value.execute.return_value = MagicMock(data=[{}])
        elif name == "app_settings":
            tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            tbl.upsert.return_value.execute.return_value = MagicMock(data=[{}])
        return tbl

    db.table.side_effect = table
    return db


class ApplyStarterRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_id] = lambda: "tenant-1"

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.onboarding.get_setting", return_value=None)
    @patch("app.routes.onboarding.save_setting")
    @patch("app.routes.onboarding.invalidate_prompt_cache")
    @patch("app.routes.onboarding.get_supabase")
    def test_applies_cleanly_to_a_fresh_tenant(self, mock_get_db, mock_invalidate, mock_save, mock_get_setting):
        mock_get_db.return_value = _table_mock(existing_prompt_row=None)

        res = self.client.post("/api/v1/onboarding/apply-starter", json={"key": "coaching"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"applied": "coaching"})
        mock_invalidate.assert_called_once_with("master")
        mock_save.assert_called_once_with("business_description", "Starter business description.", tenant_id="tenant-1")

    @patch("app.routes.onboarding.get_setting", return_value=None)
    @patch("app.routes.onboarding.save_setting")
    @patch("app.routes.onboarding.invalidate_prompt_cache")
    @patch("app.routes.onboarding.get_supabase")
    def test_refuses_to_clobber_a_customised_prompt_without_force(self, mock_get_db, mock_invalidate, mock_save, mock_get_setting):
        mock_get_db.return_value = _table_mock(existing_prompt_row={"content": "This tenant's own tuned prompt."})

        res = self.client.post("/api/v1/onboarding/apply-starter", json={"key": "coaching"})

        self.assertEqual(res.status_code, 409)
        self.assertTrue(res.json()["detail"]["would_overwrite"]["master_prompt"])
        mock_save.assert_not_called()
        mock_invalidate.assert_not_called()

    @patch("app.routes.onboarding.get_setting", return_value=None)
    @patch("app.routes.onboarding.save_setting")
    @patch("app.routes.onboarding.invalidate_prompt_cache")
    @patch("app.routes.onboarding.get_supabase")
    def test_force_overwrites_a_customised_prompt(self, mock_get_db, mock_invalidate, mock_save, mock_get_setting):
        mock_get_db.return_value = _table_mock(existing_prompt_row={"content": "This tenant's own tuned prompt."})

        res = self.client.post("/api/v1/onboarding/apply-starter", json={"key": "coaching", "force": True})

        self.assertEqual(res.status_code, 200)
        mock_save.assert_called_once()

    @patch("app.routes.onboarding.get_setting", return_value="  ")
    @patch("app.routes.onboarding.save_setting")
    @patch("app.routes.onboarding.invalidate_prompt_cache")
    @patch("app.routes.onboarding.get_supabase")
    def test_whitespace_only_description_does_not_count_as_customised(self, mock_get_db, mock_invalidate, mock_save, mock_get_setting):
        mock_get_db.return_value = _table_mock(existing_prompt_row=None)

        res = self.client.post("/api/v1/onboarding/apply-starter", json={"key": "coaching"})

        self.assertEqual(res.status_code, 200)

    @patch("app.routes.onboarding.get_setting", return_value=None)
    @patch("app.routes.onboarding.get_supabase")
    def test_unknown_starter_key_is_404(self, mock_get_db, mock_get_setting):
        mock_get_db.return_value = _table_mock(starter_row=None)

        res = self.client.post("/api/v1/onboarding/apply-starter", json={"key": "not-a-real-key"})

        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
