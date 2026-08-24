import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch as mock_patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.intake import (
    change_session_package,
    match_package,
    normalize_packages,
    package_list_message,
)


class NormalizePackagesTests(unittest.TestCase):
    def test_returns_configured_packages_unchanged(self):
        config = {
            "packages": [
                {"key": "basic", "name": "Basic", "amount_paise": 50000, "description": "30 min call"},
                {"key": "vip", "name": "VIP", "amount_paise": 500000, "description": "90 min + report"},
            ],
            "amount_paise": 0,
        }

        result = normalize_packages(config)

        self.assertEqual([p["key"] for p in result], ["basic", "vip"])
        self.assertEqual(result[1]["amount_paise"], 500000)

    def test_legacy_single_fee_becomes_one_standard_package(self):
        config = {"packages": [], "amount_paise": 1000}

        result = normalize_packages(config)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "standard")
        self.assertEqual(result[0]["name"], "Consultation")
        self.assertEqual(result[0]["amount_paise"], 1000)

    def test_no_packages_and_no_fee_returns_empty(self):
        self.assertEqual(normalize_packages({"packages": [], "amount_paise": 0}), [])

    def test_does_not_mutate_the_input_config(self):
        config = {"packages": [], "amount_paise": 1000}
        normalize_packages(config)
        self.assertEqual(config["packages"], [])


class PackageListMessageTests(unittest.TestCase):
    def test_renders_names_and_rupee_prices_from_config(self):
        packages = [
            {"key": "basic", "name": "Basic", "amount_paise": 50000, "description": "30 min call"},
            {"key": "vip", "name": "VIP", "amount_paise": 500000, "description": "90 min + written report"},
        ]

        text = package_list_message(packages, "consultation")

        self.assertIn("Basic — ₹500", text)
        self.assertIn("30 min call", text)
        self.assertIn("VIP — ₹5000", text)
        self.assertIn("consultation", text)

    def test_uses_the_configured_service_noun(self):
        packages = [{"key": "b", "name": "Basic", "amount_paise": 1000, "description": ""}]
        self.assertIn("reading", package_list_message(packages, "reading"))

    def test_omits_the_dash_when_a_package_has_no_description(self):
        packages = [{"key": "b", "name": "Basic", "amount_paise": 1000, "description": ""}]
        self.assertNotIn("—  ", package_list_message(packages, "consultation"))

    def test_omits_price_for_a_non_leaf_package(self):
        packages = [
            {"key": "basic", "name": "Basic", "amount_paise": 0, "description": "Pick a level", "options": [
                {"key": "basic_q", "name": "One Question", "amount_paise": 10000, "description": ""},
            ]},
        ]
        text = package_list_message(packages, "consultation")
        self.assertIn("Basic\n", text)
        self.assertNotIn("Basic —", text)


PACKAGES = [
    {"key": "basic", "name": "Basic", "amount_paise": 50000, "description": ""},
    {"key": "premium", "name": "Premium", "amount_paise": 200000, "description": ""},
    {"key": "vip", "name": "VIP", "amount_paise": 500000, "description": ""},
]


class MatchPackageTests(unittest.TestCase):
    def test_exact_name_matches_without_calling_the_llm(self):
        with mock_patch("app.services.intake.gemini_chat_completion_json") as llm:
            result = asyncio.run(match_package("VIP", PACKAGES, "t-1"))
        self.assertEqual(result["key"], "vip")
        llm.assert_not_called()

    def test_llm_resolves_a_vague_reply(self):
        with mock_patch(
            "app.services.intake.gemini_chat_completion_json",
            new=AsyncMock(return_value={"key": "premium"}),
        ):
            result = asyncio.run(match_package("the middle one please", PACKAGES, "t-1"))
        self.assertEqual(result["key"], "premium")

    def test_llm_returning_an_unknown_key_is_treated_as_no_match(self):
        with mock_patch(
            "app.services.intake.gemini_chat_completion_json",
            new=AsyncMock(return_value={"key": "platinum"}),
        ):
            result = asyncio.run(match_package("platinum", PACKAGES, "t-1"))
        self.assertIsNone(result)

    def test_llm_failure_is_no_match_not_a_crash(self):
        with mock_patch(
            "app.services.intake.gemini_chat_completion_json",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            result = asyncio.run(match_package("uhh", PACKAGES, "t-1"))
        self.assertIsNone(result)


class ChangeSessionPackageTests(unittest.TestCase):
    def _db_with_session(self, status):
        db = MagicMock()
        existing = MagicMock()
        existing.data = {
            "id": "s-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": status,
            "collected_data": {"name": "Cheran"}, "package_key": "basic",
        }
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = existing
        return db

    def test_refuses_to_change_a_paid_session(self):
        db = self._db_with_session("paid")
        with mock_patch("app.services.intake.get_intake_config", return_value={
            "packages": PACKAGES, "service_noun": "consultation",
        }):
            result = asyncio.run(change_session_package("s-1", "t-1", "vip", db=db))
        self.assertIsNone(result)
        db.table.return_value.update.assert_not_called()

    def test_refuses_an_unknown_package_key(self):
        db = self._db_with_session("awaiting_payment")
        with mock_patch("app.services.intake.get_intake_config", return_value={
            "packages": PACKAGES, "service_noun": "consultation",
        }):
            result = asyncio.run(change_session_package("s-1", "t-1", "platinum", db=db))
        self.assertIsNone(result)

    def test_snapshots_the_new_package_on_an_unpaid_session(self):
        db = self._db_with_session("awaiting_payment")
        with mock_patch("app.services.intake.get_intake_config", return_value={
            "packages": PACKAGES, "service_noun": "consultation",
        }):
            asyncio.run(change_session_package("s-1", "t-1", "vip", db=db))
        update_patch = db.table.return_value.update.call_args[0][0]
        self.assertEqual(update_patch["package_key"], "vip")
        self.assertEqual(update_patch["package_amount_paise"], 500000)


class IntakeConfigRouteTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.dependencies.auth import get_current_user
        from app.dependencies.tenant import get_tenant_and_role

        self.client = TestClient(app)
        self.app = app
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        self.app.dependency_overrides.clear()

    @mock_patch("app.routes.app_settings.save_intake_config")
    @mock_patch("app.routes.app_settings.get_intake_config")
    def test_rejects_duplicate_package_keys(self, mock_get, mock_save):
        mock_get.return_value = {"packages": [], "amount_paise": 0}
        res = self.client.patch("/api/v1/settings/intake-config", json={
            "packages": [
                {"key": "basic", "name": "Basic", "amount_paise": 1000, "description": ""},
                {"key": "basic", "name": "Basic Again", "amount_paise": 2000, "description": ""},
            ]
        })
        self.assertEqual(res.status_code, 400)
        mock_save.assert_not_called()

    @mock_patch("app.routes.app_settings.save_intake_config")
    @mock_patch("app.routes.app_settings.get_intake_config")
    def test_rejects_enabling_with_no_packages(self, mock_get, mock_save):
        mock_get.return_value = {"packages": [], "amount_paise": 0}
        res = self.client.patch("/api/v1/settings/intake-config", json={"enabled": True})
        self.assertEqual(res.status_code, 400)
        mock_save.assert_not_called()

    @mock_patch("app.routes.app_settings.save_intake_config")
    @mock_patch("app.routes.app_settings.get_intake_config")
    def test_saves_valid_packages(self, mock_get, mock_save):
        mock_get.return_value = {"packages": [], "amount_paise": 0}
        res = self.client.patch("/api/v1/settings/intake-config", json={
            "packages": [{"key": "vip", "name": "VIP", "amount_paise": 500000, "description": "90 min"}],
            "service_noun": "reading",
        })
        self.assertEqual(res.status_code, 200)
        saved = mock_save.call_args[0][1]
        self.assertEqual(saved["service_noun"], "reading")
        self.assertEqual(saved["packages"][0]["key"], "vip")


if __name__ == "__main__":
    unittest.main()
