"""Aira Brain: the five 'what you told Aira' rows and the 'Aira can reply' status block."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.services import brain, business_profile, intake
from app.services.brain import inputs, status
from brain_helpers import BrainDB

T1, T2 = "tenant-1", "tenant-2"
ROW_KEYS = {"key", "label", "state", "detail", "edit_href", "can_edit", "reason"}


@pytest.fixture
def settings(monkeypatch):
    """Per-tenant app_settings: {(tenant_id, key): value}."""
    store: dict[tuple[str, str], str] = {}

    def fake_get(key, fallback=None, tenant_id=None):
        return store.get((tenant_id, key), fallback)

    monkeypatch.setattr(inputs, "get_setting", fake_get)
    monkeypatch.setattr(status, "get_setting", fake_get)
    monkeypatch.setattr(intake, "get_intake_config", lambda tenant_id, db=None: {**intake._DEFAULT_CONFIG})
    return store


def _full_description() -> str:
    return "\n".join(f"{s.heading}\nsomething about {s.key}" for s in business_profile.SECTIONS)


class TestInputs:
    def test_five_rows_with_the_contract_keys(self, settings):
        rows = inputs.build_inputs(BrainDB(), T1, role="owner", permissions=[])
        assert [r["key"] for r in rows] == ["description", "knowledge_files", "services", "products", "business_details"]
        assert all(ROW_KEYS <= set(r) for r in rows)

    def test_description_sections_follow_business_profile_sections(self, settings, monkeypatch):
        settings[(T1, "business_description")] = _full_description()
        row = inputs.description_row(T1, "owner")
        assert [s["key"] for s in row["sections"]] == [s.key for s in business_profile.SECTIONS]
        assert row["state"] == "ok" and row["label"] == f"Description ({len(business_profile.SECTIONS)} sections)"

        grown = [*business_profile.SECTIONS, business_profile.Section("extra", "EXTRA PART", "Extra part", "", 10)]
        monkeypatch.setattr(business_profile, "SECTIONS", grown)
        row = inputs.description_row(T1, "owner")
        assert len(row["sections"]) == len(grown)
        assert row["sections"][-1] == {"key": "extra", "label": "Extra part", "filled": False}
        assert row["state"] == "attention" and row["label"] == f"Description ({len(grown)} sections)"

    def test_description_reports_filled_and_empty_per_section(self, settings):
        first = business_profile.SECTIONS[0]
        settings[(T1, "business_description")] = f"{first.heading}\nWe sell sarees."
        row = inputs.description_row(T1, "owner")
        assert [s["filled"] for s in row["sections"]] == [True] + [False] * (len(business_profile.SECTIONS) - 1)
        assert row["state"] == "attention"

    def test_no_description_is_missing_and_only_the_owner_can_edit(self, settings):
        assert inputs.description_row(T1, "owner")["state"] == "missing"
        row = inputs.description_row(T1, "caller")
        assert (row["can_edit"], row["reason"]) == (False, "Owner only")

    def test_draft_products_are_a_flag_on_the_products_row(self):
        db = BrainDB()
        db.add("catalog_items", tenant_id=T1, status="ready")
        db.add("catalog_items", tenant_id=T1, status="draft")
        db.add("catalog_items", tenant_id=T1, status="draft")
        db.add("catalog_items", tenant_id=T2, status="draft")
        row = inputs.products_row(db, T1, can_edit=True)
        assert row["state"] == "ok" and "2 draft" in row["flag"]
        assert inputs.products_row(BrainDB(), T1, can_edit=True)["flag"] is None

    def test_knowledge_files_counts_only_this_tenants_live_files(self):
        db = BrainDB()
        db.add("knowledge_documents", tenant_id=T1, status="indexed")
        db.add("knowledge_documents", tenant_id=T1, status="failed")
        db.add("knowledge_documents", tenant_id=T2, status="indexed")
        assert inputs.knowledge_files_row(db, T1, True)["detail"] == "1 file live"

    def test_business_details_missing_then_set(self, settings):
        assert inputs.business_details_row(T1, True)["state"] == "missing"
        settings[(T1, "business_details")] = json.dumps({"legal_name": "Acme Traders"})
        assert inputs.business_details_row(T1, True)["state"] == "ok"
        settings[(T1, "business_details")] = "{broken"
        assert inputs.business_details_row(T1, True)["state"] == "missing"

    def test_edit_rights_follow_each_pages_own_permission(self, settings):
        rows = {r["key"]: r for r in inputs.build_inputs(BrainDB(), T1, role="caller", permissions=["catalog.manage"])}
        assert rows["products"]["can_edit"] is True
        for key in ("knowledge_files", "services", "business_details"):
            assert (rows[key]["can_edit"], rows[key]["reason"]) == (False, "Needs manage access")


def _incident(db, tenant, created_at, channel="whatsapp"):
    db.add("incidents", tenant_id=tenant, type="token_invalid", detail={"channel": channel, "error": "expired"}, created_at=created_at)


class TestStatus:
    def test_connection_is_omitted_without_settings_view(self, settings):
        result = status.build_status(BrainDB(), T1, role="caller", permissions=["knowledge.view"])
        assert "connection" not in result
        assert result["auto_reply"] == "on" and result["quota"] is None

    def test_connection_is_included_with_settings_view_or_owner(self, settings):
        assert "connection" in status.build_status(BrainDB(), T1, role="caller", permissions=["settings.view"])
        assert "connection" in status.build_status(BrainDB(), T1, role="owner", permissions=[])

    def test_auto_reply_off(self, settings):
        settings[(T1, "ai_auto_reply_enabled")] = "false"
        assert status.auto_reply_state(T1) == "off"

    def test_token_problem_uses_the_48_hour_rule(self):
        now = datetime.now(timezone.utc)
        recent, old = BrainDB(), BrainDB()
        _incident(recent, T1, (now - timedelta(hours=47)).isoformat())
        _incident(old, T1, (now - timedelta(hours=49)).isoformat())
        assert status.connection_status(recent, T1)["state"] == "token_problem"
        assert status.connection_status(old, T1)["state"] == "unknown"

    def test_other_tenants_incident_is_ignored(self):
        db = BrainDB()
        _incident(db, T2, datetime.now(timezone.utc).isoformat())
        assert status.connection_status(db, T1)["state"] == "unknown"

    def test_recent_inbound_is_ok_and_stale_inbound_is_quiet(self):
        now = datetime.now(timezone.utc)
        fresh, stale = BrainDB(), BrainDB()
        fresh.add("messages", tenant_id=T1, channel="whatsapp", direction="inbound", created_at=(now - timedelta(days=1)).isoformat())
        stale.add("messages", tenant_id=T1, channel="whatsapp", direction="inbound", created_at=(now - timedelta(days=30)).isoformat())
        assert status.connection_status(fresh, T1)["state"] == "ok"
        assert status.connection_status(stale, T1)["state"] == "quiet"

    def test_quota_is_null_unless_a_hard_cap_is_set(self):
        db = BrainDB()
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        db.add("tenant_usage_counters", tenant_id=T1, period=period, metric="ai_reply", used=5, hard_cap=None)
        assert status.quota_status(db, T1) is None
        db.add("tenant_usage_counters", tenant_id=T1, period=period, metric="message_sent", used=9, hard_cap=100)
        db.add("tenant_usage_counters", tenant_id=T2, period=period, metric="ai_reply", used=1, hard_cap=1)
        assert status.quota_status(db, T1) == {"metrics": [{"metric": "message_sent", "used": 9, "hard_cap": 100}]}


class TestBuildBrain:
    def test_top_level_shape_and_no_connection_for_view_only(self, settings, monkeypatch):
        monkeypatch.setattr("app.services.consistency.get_setting", lambda *a, **k: None)
        result = brain.build_brain(T1, role="caller", permissions=["knowledge.view"], db=BrainDB())
        assert set(result) == {"headline", "waiting", "inputs", "handovers", "status"}
        assert result["waiting"]["count"] == 0 and result["handovers"] == []
        assert "connection" not in result["status"]
