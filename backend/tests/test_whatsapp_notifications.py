import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import logging
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from app.services import whatsapp_notify
whatsapp_notify.ALERT_DELAY_SECONDS = 0



def _wa_config(**overrides):
    base = {
        "enabled": True,
        "recipient_phones": ["+15550001111", "+15550002222"],
        "template_id": "tmpl-1",
        "target_segments": ["A", "B"],
    }
    base.update(overrides)
    return base


def _lead_row(**overrides):
    row = {"id": "lead-1", "name": "Asha", "phone": "+919999999999", "score": 7, "segment": "B"}
    row.update(overrides)
    return row


def _template_row(body_text="Hi {{1}}, your number is {{2}}, status: {{3}}", **overrides):
    row = {
        "id": "tmpl-1",
        "name": "segment_alert_v1",
        "language": "en",
        "body_text": body_text,
        "status": "APPROVED",
    }
    row.update(overrides)
    return row


def _make_db(
    *,
    wa_config: dict | None,
    template_rows: list | None = None,
    lead_rows: list | None = None,
    cooldown_rows: list | None = None,
    last_segment_rows: list | None = None,
):
    db = MagicMock()
    cached_pwa_table = None

    def table_selector(name):
        t = MagicMock()
        if name == "incidents":
            db._incidents_table = t
        elif name == "app_settings":
            value = None
            if wa_config is not None:
                import json as _json
                value = _json.dumps({"whatsapp_notifications": wa_config})
            data = {"value": value} if value is not None else None
            (
                t.select.return_value.eq.return_value.eq.return_value.maybe_single
                .return_value.execute.return_value.data
            ) = data
        elif name == "message_templates":
            chain = (
                t.select.return_value.eq.return_value.eq.return_value.eq
                .return_value.limit.return_value.execute.return_value
            )
            chain.data = template_rows if template_rows is not None else []
        elif name == "leads":
            chain = (
                t.select.return_value.eq.return_value.eq.return_value.limit
                .return_value.execute.return_value
            )
            chain.data = lead_rows if lead_rows is not None else []
        elif name == "lead_stage_events":
            def select_mock(columns):
                if "id,created_at" in columns:
                    execute = MagicMock()
                    execute.return_value.data = cooldown_rows if cooldown_rows is not None else []
                    
                    sel = MagicMock()
                    (
                        sel.eq.return_value.eq.return_value.eq.return_value
                        .gte.return_value.order.return_value.execute
                    ) = execute
                    return sel
                else:
                    execute = MagicMock()
                    execute.return_value.data = last_segment_rows if last_segment_rows is not None else [{"to_segment": "B"}]
                    
                    sel = MagicMock()
                    (
                        sel.eq.return_value.eq.return_value.order.return_value
                        .limit.return_value.execute
                    ) = execute
                    return sel
            t.select.side_effect = select_mock
        elif name == "pending_whatsapp_alerts":
            nonlocal cached_pwa_table
            if cached_pwa_table is not None:
                return cached_pwa_table
            
            fluent = MagicMock()
            db._pending_wa_table = fluent
            cached_pwa_table = fluent
            fluent.select.return_value = fluent
            fluent.insert.return_value = fluent
            fluent.update.return_value = fluent
            fluent.eq.return_value = fluent
            fluent.lte.return_value = fluent
            fluent.order.return_value = fluent
            fluent.limit.return_value = fluent
            
            target_seg = "B"
            if last_segment_rows and len(last_segment_rows) > 0:
                target_seg = last_segment_rows[0].get("to_segment", "B")
            
            state = {"rows": []}
            
            def insert_side_effect(row):
                if isinstance(row, dict):
                    row_copy = dict(row)
                    row_copy.setdefault("id", f"alert-{len(state['rows']) + 1}")
                    row_copy.setdefault("status", "pending")
                    state["rows"].append(row_copy)
                elif isinstance(row, list):
                    for r in row:
                        row_copy = dict(r)
                        row_copy.setdefault("id", f"alert-{len(state['rows']) + 1}")
                        row_copy.setdefault("status", "pending")
                        state["rows"].append(row_copy)
                return fluent
            fluent.insert.side_effect = insert_side_effect
            
            update_payload = {}
            def update_side_effect(payload):
                nonlocal update_payload
                update_payload = payload
                return fluent
            fluent.update.side_effect = update_side_effect
            
            filters = []
            def eq_side_effect(col, val):
                filters.append(("eq", col, val))
                return fluent
            fluent.eq.side_effect = eq_side_effect
            
            def lte_side_effect(col, val):
                filters.append(("lte", col, val))
                return fluent
            fluent.lte.side_effect = lte_side_effect
            
            def execute_side_effect():
                nonlocal update_payload, filters
                if update_payload:
                    for r in state["rows"]:
                        match = True
                        for filt in filters:
                            op, col, val = filt
                            if op == "eq":
                                if str(r.get(col)) != str(val):
                                    match = False
                                    break
                        if match:
                            r.update(update_payload)
                    update_payload = {}
                    filters = []
                    return MagicMock(data=[])
                
                selected = []
                for r in state["rows"]:
                    match = True
                    for filt in filters:
                        op, col, val = filt
                        if op == "eq":
                            if str(r.get(col)) != str(val):
                                match = False
                                break
                    if match:
                        selected.append(r)
                filters = []
                return MagicMock(data=selected)
            
            fluent.execute.side_effect = execute_side_effect
            return fluent
        return t

    db.table.side_effect = table_selector
    return db


@pytest.mark.asyncio
async def test_disabled_feature_does_not_send():
    from app.services import whatsapp_notify as svc
    db = _make_db(wa_config=_wa_config(enabled=False))
    with patch.object(svc, "get_supabase", return_value=db), \
         patch.object(svc, "send_template_message", new=AsyncMock()) as tpl:
        await svc.send_admin_whatsapp_alerts("t1", "lead-1", "C", "B")
    tpl.assert_not_called()


@pytest.mark.asyncio
async def test_segment_not_in_target_list_does_not_send():
    from app.services import whatsapp_notify as svc
    db = _make_db(wa_config=_wa_config(target_segments=["A"]))
    with patch.object(svc, "get_supabase", return_value=db), \
         patch.object(svc, "send_template_message", new=AsyncMock()) as tpl:
        await svc.send_admin_whatsapp_alerts("t1", "lead-1", "C", "B")
    tpl.assert_not_called()


@pytest.mark.asyncio
async def test_unchanged_segment_does_not_send():
    from app.services import whatsapp_notify as svc
    db = _make_db(wa_config=_wa_config())
    with patch.object(svc, "get_supabase", return_value=db), \
         patch.object(svc, "send_template_message", new=AsyncMock()) as tpl:
        await svc.send_admin_whatsapp_alerts("t1", "lead-1", "B", "B")
    tpl.assert_not_called()


@pytest.mark.asyncio
async def test_segment_change_to_target_sends_to_each_recipient_with_mapped_params():
    from app.services import whatsapp_notify as svc
    db = _make_db(
        wa_config=_wa_config(),
        template_rows=[_template_row()],
        lead_rows=[_lead_row()],
        cooldown_rows=[{"id": "evt-1"}],
    )
    with patch.object(svc, "get_supabase", return_value=db), \
         patch.object(svc, "send_template_message", new=AsyncMock()) as tpl:
        await svc.send_admin_whatsapp_alerts("t1", "lead-1", "C", "B")
    assert tpl.await_count == 2
    called_phones = {call.kwargs["to_number"] for call in tpl.await_args_list}
    assert called_phones == {"+15550001111", "+15550002222"}
    components = tpl.await_args_list[0].kwargs["components"]
    assert components == [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": "Asha"},
                {"type": "text", "text": "+919999999999"},
                {"type": "text", "text": "Warm"},
            ],
        }
    ]


@pytest.mark.asyncio
async def test_template_placeholder_count_limits_injected_params():
    from app.services import whatsapp_notify as svc
    db = _make_db(
        wa_config=_wa_config(),
        template_rows=[_template_row(body_text="Hi {{1}}, contact {{2}}")],
        lead_rows=[_lead_row()],
        cooldown_rows=[{"id": "evt-1"}],
    )
    with patch.object(svc, "get_supabase", return_value=db), \
         patch.object(svc, "send_template_message", new=AsyncMock()) as tpl:
        await svc.send_admin_whatsapp_alerts("t1", "lead-1", "C", "B")
    components = tpl.await_args_list[0].kwargs["components"]
    assert len(components[0]["parameters"]) == 2
    assert components[0]["parameters"] == [
        {"type": "text", "text": "Asha"},
        {"type": "text", "text": "+919999999999"},
    ]


@pytest.mark.asyncio
async def test_no_template_configured_does_not_send():
    from app.services import whatsapp_notify as svc
    db = _make_db(wa_config=_wa_config(template_id=None))
    with patch.object(svc, "get_supabase", return_value=db), \
         patch.object(svc, "send_template_message", new=AsyncMock()) as tpl:
        await svc.send_admin_whatsapp_alerts("t1", "lead-1", "C", "B")
    tpl.assert_not_called()


@pytest.mark.asyncio
async def test_no_recipient_phones_does_not_send():
    from app.services import whatsapp_notify as svc
    db = _make_db(wa_config=_wa_config(recipient_phones=[]))
    with patch.object(svc, "get_supabase", return_value=db), \
         patch.object(svc, "send_template_message", new=AsyncMock()) as tpl:
        await svc.send_admin_whatsapp_alerts("t1", "lead-1", "C", "B")
    tpl.assert_not_called()


@pytest.mark.asyncio
async def test_template_not_found_or_not_approved_does_not_send(caplog):
    from app.services import whatsapp_notify as svc
    db = _make_db(wa_config=_wa_config(), template_rows=[], lead_rows=[_lead_row()], cooldown_rows=[{"id": "evt-1"}])
    with patch.object(svc, "get_supabase", return_value=db), \
         patch.object(svc, "send_template_message", new=AsyncMock()) as tpl, \
         caplog.at_level(logging.WARNING):
        await svc.send_admin_whatsapp_alerts("t1", "lead-1", "C", "B")
    tpl.assert_not_called()
    assert any("not found/approved" in record.getMessage() for record in caplog.records)
    incident = db._incidents_table.insert.call_args.args[0]
    assert incident["type"] == "whatsapp_alert_failed"
    assert incident["detail"]["reason"] == "template_not_found_or_not_approved"


@pytest.mark.asyncio
async def test_lead_not_found_records_incident():
    from app.services import whatsapp_notify as svc
    db = _make_db(
        wa_config=_wa_config(),
        template_rows=[_template_row()],
        lead_rows=[],
        cooldown_rows=[{"id": "evt-1"}],
    )
    with patch.object(svc, "get_supabase", return_value=db), \
         patch.object(svc, "send_template_message", new=AsyncMock()) as tpl:
        await svc.send_admin_whatsapp_alerts("t1", "lead-1", "C", "B")
    tpl.assert_not_called()
    incident = db._incidents_table.insert.call_args.args[0]
    assert incident["detail"]["reason"] == "lead_not_found"


@pytest.mark.asyncio
async def test_meta_send_failure_records_incident():
    from app.services import whatsapp_notify as svc
    db = _make_db(
        wa_config=_wa_config(recipient_phones=["+15550001111"]),
        template_rows=[_template_row()],
        lead_rows=[_lead_row()],
        cooldown_rows=[{"id": "evt-1"}],
    )
    tpl = AsyncMock(side_effect=RuntimeError("Meta API down"))
    with patch.object(svc, "get_supabase", return_value=db), \
         patch.object(svc, "send_template_message", new=tpl):
        await svc.send_admin_whatsapp_alerts("t1", "lead-1", "C", "B")
    incident = db._incidents_table.insert.call_args.args[0]
    assert incident["detail"]["reason"] == "meta_send_failed"
    assert incident["detail"]["phone"] == "+15550001111"


@pytest.mark.asyncio
async def test_multiple_recent_notifications_within_cooldown_skips_send():
    from app.services import whatsapp_notify as svc
    db = _make_db(
        wa_config=_wa_config(),
        template_rows=[_template_row()],
        lead_rows=[_lead_row()],
        cooldown_rows=[{"id": "evt-1"}, {"id": "evt-2"}],
    )
    with patch.object(svc, "get_supabase", return_value=db), \
         patch.object(svc, "send_template_message", new=AsyncMock()) as tpl:
        await svc.send_admin_whatsapp_alerts("t1", "lead-1", "C", "B")
    tpl.assert_not_called()


@pytest.mark.asyncio
async def test_single_current_event_row_within_cooldown_still_sends():
    from app.services import whatsapp_notify as svc
    db = _make_db(
        wa_config=_wa_config(),
        template_rows=[_template_row()],
        lead_rows=[_lead_row()],
        cooldown_rows=[{"id": "evt-1"}],
    )
    with patch.object(svc, "get_supabase", return_value=db), \
         patch.object(svc, "send_template_message", new=AsyncMock()) as tpl:
        await svc.send_admin_whatsapp_alerts("t1", "lead-1", "C", "B")
    assert tpl.await_count == 2


@pytest.mark.asyncio
async def test_one_recipient_failure_does_not_block_remaining_recipients():
    from app.services import whatsapp_notify as svc
    db = _make_db(
        wa_config=_wa_config(),
        template_rows=[_template_row()],
        lead_rows=[_lead_row()],
        cooldown_rows=[{"id": "evt-1"}],
    )
    tpl = AsyncMock(side_effect=[RuntimeError("Meta API down"), None])
    with patch.object(svc, "get_supabase", return_value=db), \
         patch.object(svc, "send_template_message", new=tpl):
        await svc.send_admin_whatsapp_alerts("t1", "lead-1", "C", "B")
    assert tpl.await_count == 2


@pytest.mark.asyncio
async def test_segment_changed_event_schedules_whatsapp_alert_task():
    from app.services import growth as svc
    db = MagicMock()
    db.table.return_value.insert.return_value.execute.return_value.data = [{"id": "evt-1"}]
    with patch("app.services.whatsapp_notify.send_admin_whatsapp_alerts", new=AsyncMock()) as alert:
        svc.record_stage_event(
            "lead-1",
            to_segment="B",
            event_type="segment_changed",
            from_segment="C",
            tenant_id="t1",
            db=db,
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    alert.assert_awaited_once_with("t1", "lead-1", "C", "B")


def test_no_running_event_loop_records_incident():
    """record_stage_event called from sync code (no event loop) must not
    raise, and must leave a visible trail instead of silently dropping."""
    from app.services import growth as svc
    db = MagicMock()
    db.table.return_value.insert.return_value.execute.return_value.data = [{"id": "evt-1"}]
    incidents_db = MagicMock()
    with patch.object(svc, "get_supabase", return_value=incidents_db):
        svc.record_stage_event(
            "lead-1",
            to_segment="B",
            event_type="segment_changed",
            from_segment="C",
            tenant_id="t1",
            db=db,
        )
    incident_calls = [
        c for c in incidents_db.table.call_args_list if c.args and c.args[0] == "incidents"
    ]
    assert incident_calls, "expected an incidents table insert when no event loop is running"


@pytest.mark.asyncio
async def test_non_segment_changed_event_does_not_schedule_whatsapp_alert_task():
    from app.services import growth as svc
    db = MagicMock()
    db.table.return_value.insert.return_value.execute.return_value.data = [{"id": "evt-1"}]
    with patch("app.services.whatsapp_notify.send_admin_whatsapp_alerts", new=AsyncMock()) as alert:
        svc.record_stage_event(
            "lead-1",
            to_segment="B",
            event_type="manual_update",
            from_segment="C",
            tenant_id="t1",
            db=db,
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    alert.assert_not_awaited()


@pytest.mark.asyncio
async def test_alert_delay_and_segment_recheck_success():
    from app.services import whatsapp_notify as svc
    db = _make_db(
        wa_config=_wa_config(),
        template_rows=[_template_row()],
        lead_rows=[_lead_row(segment="B")],
        cooldown_rows=[{"id": "evt-1"}],
        last_segment_rows=[{"to_segment": "B"}],
    )
    with patch.object(svc, "get_supabase", return_value=db), \
         patch.object(svc, "send_template_message", new=AsyncMock()) as tpl, \
         patch.object(svc, "ALERT_DELAY_SECONDS", 0.05):
        
        task = asyncio.create_task(svc.send_admin_whatsapp_alerts("t1", "lead-1", "C", "B"))
        await asyncio.sleep(0.01)
        assert not tpl.called
        
        await task
        assert tpl.await_count == 2


@pytest.mark.asyncio
async def test_alert_delay_and_segment_recheck_fails():
    from app.services import whatsapp_notify as svc
    db = _make_db(
        wa_config=_wa_config(),
        template_rows=[_template_row()],
        lead_rows=[_lead_row(segment="B")],
        cooldown_rows=[{"id": "evt-1"}],
        last_segment_rows=[{"to_segment": "A"}],
    )
    with patch.object(svc, "get_supabase", return_value=db), \
         patch.object(svc, "send_template_message", new=AsyncMock()) as tpl, \
         patch.object(svc, "ALERT_DELAY_SECONDS", 0.05):
        
        task = asyncio.create_task(svc.send_admin_whatsapp_alerts("t1", "lead-1", "C", "B"))
        await asyncio.sleep(0.01)
        
        await task
        tpl.assert_not_called()


@pytest.mark.asyncio
async def test_dynamic_delay_from_client_config():
    from app.services import whatsapp_notify as svc
    db = _make_db(
        wa_config=_wa_config(delay_minutes=10),
        template_rows=[_template_row()],
        lead_rows=[_lead_row(segment="B")],
        cooldown_rows=[{"id": "evt-1"}],
        last_segment_rows=[{"to_segment": "B"}],
    )
    with patch.object(svc, "get_supabase", return_value=db), \
         patch.object(svc, "send_template_message", new=AsyncMock()), \
         patch("asyncio.sleep", new=AsyncMock()) as mock_sleep, \
         patch.object(svc, "ALERT_DELAY_SECONDS", 300):
        
        await svc.send_admin_whatsapp_alerts("t1", "lead-1", "C", "B")
        mock_sleep.assert_called_once_with(600)


