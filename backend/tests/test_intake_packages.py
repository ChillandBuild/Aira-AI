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

    def test_finds_a_nested_leaf_by_key(self):
        db = self._db_with_session("awaiting_payment")
        with mock_patch("app.services.intake.get_intake_config", return_value={
            "packages": NESTED_PACKAGES, "service_noun": "reading",
        }):
            result = asyncio.run(change_session_package("s-1", "t-1", "basic_detail", db=db))
        self.assertIsNotNone(result)
        update_patch = db.table.return_value.update.call_args[0][0]
        self.assertEqual(update_patch["package_key"], "basic_detail")
        self.assertEqual(update_patch["package_amount_paise"], 30000)
        self.assertEqual(update_patch["package_path"], [
            {"key": "basic", "name": "Basic"}, {"key": "basic_detail", "name": "Detailed Consultation"},
        ])

    def test_refuses_a_non_leaf_key(self):
        db = self._db_with_session("awaiting_payment")
        with mock_patch("app.services.intake.get_intake_config", return_value={
            "packages": NESTED_PACKAGES, "service_noun": "reading",
        }):
            result = asyncio.run(change_session_package("s-1", "t-1", "basic", db=db))
        self.assertIsNone(result)


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

    @mock_patch("app.routes.app_settings.save_intake_config")
    @mock_patch("app.routes.app_settings.get_intake_config")
    def test_saves_a_nested_package_tree(self, mock_get, mock_save):
        mock_get.return_value = {"packages": [], "amount_paise": 0}
        res = self.client.patch("/api/v1/settings/intake-config", json={
            "packages": [
                {"key": "basic", "name": "Basic", "amount_paise": 0, "description": "", "active": True, "options": [
                    {"key": "basic_q", "name": "One Question", "amount_paise": 10000, "description": "", "active": True},
                ]},
            ],
        })
        self.assertEqual(res.status_code, 200)
        saved = mock_save.call_args[0][1]
        self.assertEqual(saved["packages"][0]["options"][0]["key"], "basic_q")

    @mock_patch("app.routes.app_settings.save_intake_config")
    @mock_patch("app.routes.app_settings.get_intake_config")
    def test_non_leaf_amount_paise_is_not_validated(self, mock_get, mock_save):
        mock_get.return_value = {"packages": [], "amount_paise": 0}
        res = self.client.patch("/api/v1/settings/intake-config", json={
            "packages": [
                {"key": "basic", "name": "Basic", "amount_paise": 0, "description": "", "active": True, "options": [
                    {"key": "basic_q", "name": "One Question", "amount_paise": 10000, "description": "", "active": True},
                ]},
            ],
        })
        self.assertEqual(res.status_code, 200)

    @mock_patch("app.routes.app_settings.save_intake_config")
    @mock_patch("app.routes.app_settings.get_intake_config")
    def test_rejects_a_leaf_with_zero_amount(self, mock_get, mock_save):
        mock_get.return_value = {"packages": [], "amount_paise": 0}
        res = self.client.patch("/api/v1/settings/intake-config", json={
            "packages": [{"key": "basic", "name": "Basic", "amount_paise": 0, "description": "", "active": True}],
        })
        self.assertEqual(res.status_code, 400)
        mock_save.assert_not_called()

    @mock_patch("app.routes.app_settings.save_intake_config")
    @mock_patch("app.routes.app_settings.get_intake_config")
    def test_rejects_a_duplicate_key_between_a_sub_package_and_an_addon(self, mock_get, mock_save):
        mock_get.return_value = {"packages": [], "amount_paise": 0}
        res = self.client.patch("/api/v1/settings/intake-config", json={
            "packages": [
                {"key": "basic", "name": "Basic", "amount_paise": 10000, "description": "", "active": True,
                 "addons": [{"key": "basic", "name": "Dup", "amount_paise": 500, "description": "", "active": True}]},
            ],
        })
        self.assertEqual(res.status_code, 400)
        mock_save.assert_not_called()


from app.services.intake import _active_children, _find_leaf, _menu_at_path, _resolve_choice


NESTED_PACKAGES = [
    {"key": "basic", "name": "Basic", "amount_paise": 0, "description": "", "active": True, "options": [
        {"key": "basic_q", "name": "One Question", "amount_paise": 10000, "description": "", "active": True},
        {"key": "basic_detail", "name": "Detailed Consultation", "amount_paise": 30000, "description": "", "active": True,
         "addons": [{"key": "pdf", "name": "PDF summary", "amount_paise": 20000, "description": "", "active": True}]},
    ]},
    {"key": "premium", "name": "Premium", "amount_paise": 50000, "description": "", "active": True},
]


class ActiveChildrenTests(unittest.TestCase):
    def test_filters_out_inactive_nodes(self):
        nodes = [{"key": "a", "active": True}, {"key": "b", "active": False}, {"key": "c"}]
        result = _active_children(nodes)
        self.assertEqual([n["key"] for n in result], ["a", "c"])


class ResolveChoiceTests(unittest.TestCase):
    def test_two_active_roots_asks_the_lead(self):
        outcome, result, path = _resolve_choice(NESTED_PACKAGES, [])
        self.assertEqual(outcome, "choose")
        self.assertEqual([n["key"] for n in result], ["basic", "premium"])
        self.assertEqual(path, [])

    def test_single_active_root_with_no_children_is_a_leaf(self):
        outcome, result, path = _resolve_choice([NESTED_PACKAGES[1]], [])
        self.assertEqual(outcome, "leaf")
        self.assertEqual(result["key"], "premium")
        self.assertEqual(path, [{"key": "premium", "name": "Premium"}])

    def test_single_active_root_with_children_auto_descends(self):
        outcome, result, path = _resolve_choice([NESTED_PACKAGES[0]], [])
        self.assertEqual(outcome, "choose")
        self.assertEqual([n["key"] for n in result], ["basic_q", "basic_detail"])
        self.assertEqual(path, [{"key": "basic", "name": "Basic"}])

    def test_auto_descends_through_a_single_active_child_to_a_leaf(self):
        single_child_chain = [{"key": "only", "name": "Only", "active": True, "options": [
            {"key": "leaf", "name": "Leaf", "amount_paise": 5000, "active": True},
        ]}]
        outcome, result, path = _resolve_choice(single_child_chain, [])
        self.assertEqual(outcome, "leaf")
        self.assertEqual(result["key"], "leaf")
        self.assertEqual(path, [{"key": "only", "name": "Only"}, {"key": "leaf", "name": "Leaf"}])

    def test_zero_active_options_is_empty(self):
        outcome, result, path = _resolve_choice([{"key": "a", "active": False}], [])
        self.assertEqual(outcome, "empty")
        self.assertEqual(result, [])


class MenuAtPathTests(unittest.TestCase):
    def test_root_path_returns_top_level(self):
        self.assertEqual([n["key"] for n in _menu_at_path(NESTED_PACKAGES, [])], ["basic", "premium"])

    def test_walks_into_a_matched_key(self):
        menu = _menu_at_path(NESTED_PACKAGES, [{"key": "basic", "name": "Basic"}])
        self.assertEqual([n["key"] for n in menu], ["basic_q", "basic_detail"])

    def test_unknown_key_in_path_returns_empty(self):
        self.assertEqual(_menu_at_path(NESTED_PACKAGES, [{"key": "nope", "name": "?"}]), [])


class FindLeafTests(unittest.TestCase):
    def test_finds_a_nested_leaf_and_its_path(self):
        found = _find_leaf(NESTED_PACKAGES, "basic_detail")
        self.assertIsNotNone(found)
        leaf, path = found
        self.assertEqual(leaf["key"], "basic_detail")
        self.assertEqual(path, [{"key": "basic", "name": "Basic"}, {"key": "basic_detail", "name": "Detailed Consultation"}])

    def test_finds_a_root_level_leaf(self):
        found = _find_leaf(NESTED_PACKAGES, "premium")
        self.assertEqual(found[1], [{"key": "premium", "name": "Premium"}])

    def test_unknown_key_returns_none(self):
        self.assertIsNone(_find_leaf(NESTED_PACKAGES, "nope"))


from app.services.intake import _package_patch, addon_list_block, match_addons

ADDONS = [
    {"key": "pdf", "name": "PDF summary", "amount_paise": 20000, "description": ""},
    {"key": "call", "name": "Follow-up call", "amount_paise": 15000, "description": ""},
]


class AddonListBlockTests(unittest.TestCase):
    def test_renders_names_and_plus_prices(self):
        text = addon_list_block(ADDONS)
        self.assertIn("PDF summary — +₹200", text)
        self.assertIn("Follow-up call — +₹150", text)


class MatchAddonsTests(unittest.TestCase):
    def test_no_addons_configured_returns_empty_without_calling_llm(self):
        with mock_patch("app.services.intake.gemini_chat_completion_json") as llm:
            result = asyncio.run(match_addons("yes please", [], "t-1"))
        self.assertEqual(result, [])
        llm.assert_not_called()

    def test_decline_words_short_circuit_without_calling_the_llm(self):
        with mock_patch("app.services.intake.gemini_chat_completion_json") as llm:
            result = asyncio.run(match_addons("no thanks", ADDONS, "t-1"))
        self.assertEqual(result, [])
        llm.assert_not_called()

    def test_llm_selects_multiple_addons(self):
        with mock_patch(
            "app.services.intake.gemini_chat_completion_json",
            new=AsyncMock(return_value={"keys": ["pdf", "call"]}),
        ):
            result = asyncio.run(match_addons("both please", ADDONS, "t-1"))
        self.assertEqual({a["key"] for a in result}, {"pdf", "call"})

    def test_unknown_keys_from_the_llm_are_dropped_not_guessed(self):
        with mock_patch(
            "app.services.intake.gemini_chat_completion_json",
            new=AsyncMock(return_value={"keys": ["pdf", "made_up"]}),
        ):
            result = asyncio.run(match_addons("the summary one", ADDONS, "t-1"))
        self.assertEqual([a["key"] for a in result], ["pdf"])

    def test_llm_failure_returns_no_addons_not_a_crash(self):
        with mock_patch(
            "app.services.intake.gemini_chat_completion_json",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            result = asyncio.run(match_addons("uhh", ADDONS, "t-1"))
        self.assertEqual(result, [])


class PackagePatchTests(unittest.TestCase):
    def test_defaults_have_no_path_or_total(self):
        patch = _package_patch({"key": "basic", "name": "Basic", "amount_paise": 10000})
        self.assertEqual(patch, {
            "package_key": "basic", "package_name": "Basic", "package_amount_paise": 10000,
        })

    def test_includes_path_and_total_when_given(self):
        path = [{"key": "basic", "name": "Basic"}]
        patch = _package_patch({"key": "basic", "name": "Basic", "amount_paise": 10000}, path=path, total_amount_paise=30000)
        self.assertEqual(patch["package_path"], path)
        self.assertEqual(patch["total_amount_paise"], 30000)


from app.services.intake import _build_buttons, _build_list_sections, _short_label, _tap_mode


def _leaf(key, name, button_label=None):
    return {"key": key, "name": name, "amount_paise": 10000, "active": True, "button_label": button_label}


class ShortLabelTests(unittest.TestCase):
    def test_uses_button_label_when_set(self):
        self.assertEqual(_short_label(_leaf("k", "Very Long Package Name Indeed", "Short"), 20), "Short")

    def test_falls_back_to_name_when_it_fits(self):
        self.assertEqual(_short_label(_leaf("k", "Basic"), 20), "Basic")

    def test_none_when_neither_fits(self):
        self.assertIsNone(_short_label(_leaf("k", "Way Too Long A Package Name"), 20))


class TapModeTests(unittest.TestCase):
    def test_one_option_is_text(self):
        self.assertEqual(_tap_mode([_leaf("a", "A")]), "text")

    def test_two_to_three_short_labels_is_buttons(self):
        self.assertEqual(_tap_mode([_leaf("a", "A"), _leaf("b", "B")]), "buttons")
        self.assertEqual(_tap_mode([_leaf("a", "A"), _leaf("b", "B"), _leaf("c", "C")]), "buttons")

    def test_four_to_ten_short_labels_is_list(self):
        level = [_leaf(f"k{i}", f"Option {i}") for i in range(4)]
        self.assertEqual(_tap_mode(level), "list")
        level10 = [_leaf(f"k{i}", f"Option {i}") for i in range(10)]
        self.assertEqual(_tap_mode(level10), "list")

    def test_eleven_options_is_text(self):
        level = [_leaf(f"k{i}", f"Option {i}") for i in range(11)]
        self.assertEqual(_tap_mode(level), "text")

    def test_a_label_too_long_for_buttons_with_only_two_options_is_text(self):
        level = [_leaf("a", "A"), _leaf("b", "A Name Definitely Over Twenty Chars")]
        self.assertEqual(_tap_mode(level), "text")

    def test_a_label_too_long_even_for_list_tier_is_text(self):
        level = [_leaf(f"k{i}", "A Description Text Well Over Twenty Four Characters Long") for i in range(5)]
        self.assertEqual(_tap_mode(level), "text")


class BuildButtonsAndSectionsTests(unittest.TestCase):
    def test_build_buttons_uses_key_as_id(self):
        buttons = _build_buttons([_leaf("basic_q", "One Question")])
        self.assertEqual(buttons, [{"id": "basic_q", "title": "One Question"}])

    def test_build_list_sections_wraps_rows_in_one_section(self):
        sections = _build_list_sections([_leaf("a", "A"), _leaf("b", "B")])
        self.assertEqual(sections, [{"rows": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]}])


from app.services.intake import _send_buttons_and_log, _send_list_and_log


class SendButtonsAndLogTests(unittest.TestCase):
    def test_logs_the_body_and_button_titles(self):
        db = MagicMock()
        with mock_patch(
            "app.services.meta_cloud.send_interactive_buttons",
            new=AsyncMock(return_value={"messages": [{"id": "wamid.1"}]}),
        ):
            asyncio.run(_send_buttons_and_log(
                "+91123", "Pick one:", [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}],
                "t-1", "lead-1", db,
            ))
        logged = db.table.return_value.insert.call_args[0][0]
        self.assertIn("Pick one:", logged["content"])
        self.assertIn("[A]", logged["content"])
        self.assertEqual(logged["meta_message_id"], "wamid.1")
        self.assertEqual(logged["reply_source"], "expert_handoff")


class SendListAndLogTests(unittest.TestCase):
    def test_logs_the_body_and_row_titles(self):
        db = MagicMock()
        sections = [{"rows": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]}]
        with mock_patch(
            "app.services.meta_cloud.send_list_message",
            new=AsyncMock(return_value={"messages": [{"id": "wamid.2"}]}),
        ):
            asyncio.run(_send_list_and_log("+91123", "Pick one:", "Choose", sections, "t-1", "lead-1", db))
        logged = db.table.return_value.insert.call_args[0][0]
        self.assertIn("[A]", logged["content"])
        self.assertIn("[B]", logged["content"])
        self.assertEqual(logged["meta_message_id"], "wamid.2")


if __name__ == "__main__":
    unittest.main()
