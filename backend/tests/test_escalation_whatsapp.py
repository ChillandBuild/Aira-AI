import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import whatsapp_notify


def _esc_config(**overrides):
    base = {
        "enabled": True,
        "recipient_phones": ["+15550001111"],
        "template_id": "tmpl-esc",
        "target_segments": ["A"],
        "delay_minutes": 3,
    }
    base.update(overrides)
    return base


def _make_db(esc_config: dict | None, lead_segment: str = "A"):
    """Fake Supabase client: app_settings holds the escalation config, leads
    returns a row with the given segment, and inserts are recorded."""
    db = MagicMock()
    inserts: list[dict] = []

    pwa_table = MagicMock()
    pwa_table.insert.side_effect = lambda row: (inserts.append(row), MagicMock())[1]

    def table_selector(name):
        if name == "app_settings":
            t = MagicMock()
            value = (
                json.dumps({"whatsapp_escalation_notifications": esc_config})
                if esc_config is not None else None
            )
            data = {"value": value} if value is not None else None
            (t.select.return_value.eq.return_value.eq.return_value
             .maybe_single.return_value.execute.return_value.data) = data
            return t
        if name == "leads":
            t = MagicMock()
            (t.select.return_value.eq.return_value.limit.return_value
             .execute.return_value.data) = [{"id": "lead-1", "segment": lead_segment}]
            return t
        if name == "pending_whatsapp_alerts":
            return pwa_table
        return MagicMock()

    db.table.side_effect = table_selector
    db._inserts = inserts
    return db


# --- queueing ---------------------------------------------------------------

def test_queue_noop_when_disabled():
    db = _make_db(_esc_config(enabled=False))
    whatsapp_notify.queue_escalation_whatsapp_alert(
        db, "tenant-1", "lead-1", "ho-1", "user asked for human", None
    )
    assert db._inserts == []


def test_queue_noop_when_segment_not_targeted():
    db = _make_db(_esc_config(target_segments=["A"]), lead_segment="C")
    whatsapp_notify.queue_escalation_whatsapp_alert(
        db, "tenant-1", "lead-1", "ho-1", "reason", None
    )
    assert db._inserts == []


def test_queue_noop_without_template():
    db = _make_db(_esc_config(template_id=None))
    whatsapp_notify.queue_escalation_whatsapp_alert(
        db, "tenant-1", "lead-1", "ho-1", "reason", None
    )
    assert db._inserts == []


def test_queue_noop_without_recipient_phones():
    db = _make_db(_esc_config(recipient_phones=[]))
    whatsapp_notify.queue_escalation_whatsapp_alert(
        db, "tenant-1", "lead-1", "ho-1", "reason", None
    )
    assert db._inserts == []


def test_queue_happy_path_records_row_with_snapshot():
    db = _make_db(_esc_config())
    whatsapp_notify.queue_escalation_whatsapp_alert(
        db, "tenant-1", "lead-1", "ho-1", "user asked for human", "caller-7"
    )
    assert len(db._inserts) == 1
    row = db._inserts[0]
    assert row["alert_type"] == "escalation"
    assert row["handover_id"] == "ho-1"
    assert row["assigned_to_at_queue"] == "caller-7"
    assert row["escalation_reason"] == "user asked for human"
    assert row["status"] == "pending"
    assert row["to_segment"] is None
    assert "send_at" in row


def test_queue_never_raises_on_db_failure():
    """A notification fault must never propagate into escalation."""
    db = MagicMock()
    db.table.side_effect = RuntimeError("db down")
    whatsapp_notify.queue_escalation_whatsapp_alert(
        db, "tenant-1", "lead-1", "ho-1", "reason", None
    )  # must not raise


# --- template rendering -----------------------------------------------------

def test_build_escalation_components_maps_four_variables():
    template = {"body_text": "Lead {{1}} ({{2}}) escalated: {{3}} - {{4}}"}
    lead = {"id": "lead-1", "name": "Asha", "phone": "+919999999999"}
    comps = whatsapp_notify._build_escalation_components(
        template, lead, "user asked for human"
    )
    assert [p["text"] for p in comps[0]["parameters"]] == [
        "Asha",
        "+919999999999",
        "user asked for human",
        "https://aira.ai/dashboard/conversations?lead_id=lead-1",
    ]


def test_build_escalation_components_truncates_long_reason():
    template = {"body_text": "{{1}} {{2}} {{3}}"}
    lead = {"id": "lead-1", "name": "Asha", "phone": "+91999"}
    comps = whatsapp_notify._build_escalation_components(template, lead, "x" * 400)
    assert len(comps[0]["parameters"][2]["text"]) == 120


def test_build_escalation_components_returns_none_without_variables():
    template = {"body_text": "A lead needs attention."}
    lead = {"id": "lead-1", "name": "Asha", "phone": "+91999"}
    assert whatsapp_notify._build_escalation_components(template, lead, "reason") is None


def test_build_escalation_components_maps_source_as_fifth_variable():
    template = {"body_text": "Lead {{1}} ({{2}}) from {{5}}: {{3}} - {{4}}"}
    lead = {"id": "lead-1", "name": "Asha", "phone": "+919999999999"}
    comps = whatsapp_notify._build_escalation_components(
        template, lead, "user asked for human", "Ad: Astro Whatsapp 02"
    )
    # Parameters are positional: index 4 -> {{5}} regardless of text order.
    assert [p["text"] for p in comps[0]["parameters"]] == [
        "Asha",
        "+919999999999",
        "user asked for human",
        "https://aira.ai/dashboard/conversations?lead_id=lead-1",
        "Ad: Astro Whatsapp 02",
    ]


def test_build_escalation_components_source_defaults_to_direct():
    template = {"body_text": "Lead {{1}} from {{5}}: {{2}} {{3}} {{4}}"}
    lead = {"id": "lead-1", "name": "Asha", "phone": "+91999"}
    comps = whatsapp_notify._build_escalation_components(template, lead, "reason")
    assert comps[0]["parameters"][4]["text"] == "Direct (not from an ad)"


def test_lead_ad_source_returns_most_recent_creative_label():
    from unittest.mock import MagicMock

    db = MagicMock()
    (db.table.return_value.select.return_value.eq.return_value.eq.return_value
     .order.return_value.limit.return_value.execute.return_value.data) = [
        {"created_at": "2026-08-01", "ad_creatives": {"creative_label": "Astro Whatsapp 02"}}
    ]
    assert whatsapp_notify._lead_ad_source(db, "tenant-1", "lead-1") == "Ad: Astro Whatsapp 02"


def test_lead_ad_source_falls_back_to_direct_when_no_attribution():
    from unittest.mock import MagicMock

    db = MagicMock()
    (db.table.return_value.select.return_value.eq.return_value.eq.return_value
     .order.return_value.limit.return_value.execute.return_value.data) = []
    assert whatsapp_notify._lead_ad_source(db, "tenant-1", "lead-1") == "Direct (not from an ad)"


def test_lead_ad_source_never_raises():
    from unittest.mock import MagicMock

    db = MagicMock()
    db.table.side_effect = RuntimeError("db down")
    assert whatsapp_notify._lead_ad_source(db, "tenant-1", "lead-1") == "Direct (not from an ad)"


# --- sending / cancel-if-claimed -------------------------------------------

def _alert_row(**overrides):
    row = {
        "id": "alert-1",
        "tenant_id": "tenant-1",
        "lead_id": "lead-1",
        "handover_id": "ho-1",
        "assigned_to_at_queue": None,
        "escalation_reason": "user asked for human",
        "alert_type": "escalation",
        "to_segment": None,
    }
    row.update(overrides)
    return row


def _make_process_db(handover_row, esc_config=None, alert=None):
    """Fake client covering one due escalation alert end to end."""
    db = MagicMock()
    updates: list[dict] = []

    def table_selector(name):
        t = MagicMock()
        if name == "pending_whatsapp_alerts":
            (t.select.return_value.eq.return_value.lte.return_value.order
             .return_value.limit.return_value.execute.return_value.data) = [
                alert or _alert_row()
            ]
            t.update.side_effect = lambda payload: (updates.append(payload), MagicMock())[1]
        elif name == "chat_handovers":
            (t.select.return_value.eq.return_value.limit.return_value
             .execute.return_value.data) = [handover_row] if handover_row else []
        elif name == "app_settings":
            value = json.dumps(
                {"whatsapp_escalation_notifications": esc_config or _esc_config()}
            )
            (t.select.return_value.eq.return_value.eq.return_value.maybe_single
             .return_value.execute.return_value.data) = {"value": value}
        elif name == "leads":
            (t.select.return_value.eq.return_value.eq.return_value.limit
             .return_value.execute.return_value.data) = [
                {"id": "lead-1", "name": "Asha", "phone": "+919999999999",
                 "score": 8, "segment": "A"}
            ]
        elif name == "message_templates":
            (t.select.return_value.eq.return_value.eq.return_value.eq.return_value
             .limit.return_value.execute.return_value.data) = [{
                "id": "tmpl-esc", "name": "escalation_v1", "language": "en",
                "body_text": "Lead {{1}} ({{2}}) escalated: {{3}} - {{4}}",
                "status": "APPROVED",
             }]
        return t

    db.table.side_effect = table_selector
    db._updates = updates
    return db


def _run_process(db):
    with patch.object(whatsapp_notify, "get_supabase", return_value=db), \
         patch.object(whatsapp_notify, "_dispatch_alerts", new=AsyncMock()) as dispatch:
        asyncio.run(whatsapp_notify.process_due_whatsapp_alerts())
    return dispatch


def test_cancelled_when_handover_resolved():
    db = _make_process_db({"id": "ho-1", "status": "resolved", "assigned_to": None})
    dispatch = _run_process(db)
    dispatch.assert_not_called()
    assert {"status": "cancelled"} in db._updates


def test_cancelled_when_handover_claimed():
    db = _make_process_db({"id": "ho-1", "status": "pending", "assigned_to": "caller-9"})
    dispatch = _run_process(db)
    dispatch.assert_not_called()
    assert {"status": "cancelled"} in db._updates


def test_cancelled_when_handover_missing():
    db = _make_process_db(None)
    dispatch = _run_process(db)
    dispatch.assert_not_called()
    assert {"status": "cancelled"} in db._updates


def test_cancelled_when_config_disabled_since_queueing():
    db = _make_process_db(
        {"id": "ho-1", "status": "pending", "assigned_to": None},
        esc_config=_esc_config(enabled=False),
    )
    dispatch = _run_process(db)
    dispatch.assert_not_called()
    assert {"status": "cancelled"} in db._updates


def test_sent_when_still_pending_and_unclaimed():
    db = _make_process_db({"id": "ho-1", "status": "pending", "assigned_to": None})
    dispatch = _run_process(db)
    dispatch.assert_called_once()
    assert {"status": "sent"} in db._updates


def test_preexisting_owner_is_not_treated_as_claimed():
    """assigned_to seeded at creation must compare equal to the snapshot."""
    db = _make_process_db(
        {"id": "ho-1", "status": "pending", "assigned_to": "owner-1"},
        alert=_alert_row(assigned_to_at_queue="owner-1"),
    )
    dispatch = _run_process(db)
    dispatch.assert_called_once()
    assert {"status": "sent"} in db._updates
