import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _lead(**over):
    base = {"id": "lead-1", "name": "Asha", "phone": "919999999999",
            "opted_out": False, "whatsapp_undeliverable": False}
    base.update(over)
    return base


def _step():
    return {"id": "step-1", "message_type": "freeform",
            "message_content": "Hi there!", "fallback_template_name": None}


@pytest.mark.parametrize("lead,expected_reason", [
    (_lead(phone=None), "no phone"),
    (_lead(whatsapp_undeliverable=True), "whatsapp undeliverable"),
    (_lead(opted_out=True), "opted out"),
    (_lead(), None),
])
def test_lead_gate_reasons(lead, expected_reason):
    from app.services.automation_guards import lead_blocks_automated_outbound
    assert lead_blocks_automated_outbound(lead) == expected_reason


def test_master_switch_defaults_on():
    from app.services import automation_guards as g
    with patch.object(g, "get_setting", return_value=None):
        assert g.master_switch_on("t1") is True


def test_master_switch_off_only_on_literal_false():
    from app.services import automation_guards as g
    with patch.object(g, "get_setting", return_value="false"):
        assert g.master_switch_on("t1") is False
    with patch.object(g, "get_setting", return_value="true"):
        assert g.master_switch_on("t1") is True


def _reengagement_db(captured_logs):
    db = MagicMock()

    def table_selector(name):
        t = MagicMock()
        if name == "reengagement_logs":
            def _insert(row):
                captured_logs.append(row)
                res = MagicMock()
                res.execute.return_value.data = [{"id": "log-1"}]
                return res
            t.insert.side_effect = _insert
        else:
            t.insert.return_value.execute.return_value.data = [{"id": "x"}]
        return t

    db.table.side_effect = table_selector
    return db


@pytest.mark.asyncio
@pytest.mark.parametrize("lead", [
    _lead(opted_out=True),
    _lead(whatsapp_undeliverable=True),
    _lead(phone=None),
])
async def test_reengagement_still_skips_blocked_leads_without_logging(lead):
    """Characterisation: blocked leads write NO reengagement_logs row, so the
    step resumes for them later rather than being marked permanently processed.

    The master switch is left on so each case is genuinely exercising the
    lead-level gate rather than short-circuiting earlier.
    """
    from app.services import reengagement_service as svc
    from app.services import automation_guards as g
    logs = []
    db = _reengagement_db(logs)

    with patch.object(svc, "send_whatsapp", new=AsyncMock()) as wa, \
         patch.object(g, "get_setting", return_value="true"):
        ok = await svc._send_reengagement(db, "t1", lead, _step())

    assert ok is False
    wa.assert_not_awaited()
    assert logs == []


@pytest.mark.asyncio
async def test_reengagement_master_switch_off_writes_no_log():
    """Characterisation: the master switch must not consume the step."""
    from app.services import reengagement_service as svc
    from app.services import automation_guards as g
    logs = []
    db = _reengagement_db(logs)

    with patch.object(svc, "send_whatsapp", new=AsyncMock()) as wa, \
         patch.object(g, "get_setting", return_value="false"):
        ok = await svc._send_reengagement(db, "t1", _lead(), _step())

    assert ok is False
    wa.assert_not_awaited()
    assert logs == []
