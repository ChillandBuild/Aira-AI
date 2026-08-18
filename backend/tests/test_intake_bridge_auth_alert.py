"""A rejected astrologer reply is the one bridge failure with no other symptom:
the expert sees "sent", the customer hears nothing, Aira logs one line. Staff
must be told — but only once per hour, because Django retries."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.intake import public_router
from app.services import intake as ik

app = FastAPI()
app.include_router(public_router, prefix="/api/v1/expert-handoff")
client = TestClient(app)

TENANT = "0f897915-2d34-4b67-8d69-f83f52e4fb6c"
SID = "11111111-2222-3333-4444-555555555555"


def _cooldown_db(recent_rows):
    db = MagicMock()
    result = MagicMock()
    result.data = recent_rows
    (db.table.return_value.select.return_value.eq.return_value.eq.return_value
       .gte.return_value.limit.return_value.execute.return_value) = result
    return db


def test_a_mismatched_secret_alerts_staff():
    with patch("app.routes.intake.get_session_tenant_id", return_value=TENANT), \
         patch("app.routes.intake.astro_bridge.get_bridge_secret", return_value="right"), \
         patch("app.routes.intake.astro_bridge.verify_astro_signature", return_value=False), \
         patch("app.routes.intake.alert_bridge_auth_failure") as alert:
        res = client.post(
            "/api/v1/expert-handoff/astro-reply",
            json={"external_ref": SID, "reply_id": 1, "reply_text": "hi"},
            headers={"x-astro-signature": "sha256=wrong"},
        )
    assert res.status_code == 401
    alert.assert_called_once_with(TENANT, SID)


def test_an_unknown_ref_does_not_alert():
    """Someone probing the endpoint must not be able to fill the tray."""
    with patch("app.routes.intake.get_session_tenant_id", return_value=None), \
         patch("app.routes.intake.alert_bridge_auth_failure") as alert:
        res = client.post(
            "/api/v1/expert-handoff/astro-reply",
            json={"external_ref": "not-a-session", "reply_id": 1},
            headers={"x-astro-signature": "sha256=whatever"},
        )
    assert res.status_code == 401
    alert.assert_not_called()


def test_the_alert_names_the_setting_to_check():
    db = _cooldown_db([])
    with patch.object(ik, "notify_pool") as notify:
        ik.alert_bridge_auth_failure(TENANT, SID, db=db)
    notify.assert_called_once()
    args = notify.call_args[0]
    assert args[0] == TENANT
    assert args[1] == "intake_bridge_auth_failed"
    assert "astro_bridge_secret" in args[3]
    assert "AIRA_BRIDGE_SECRET" in args[3]


def test_repeat_failures_inside_the_cooldown_do_not_re_alert():
    db = _cooldown_db([{"id": "n-1"}])
    with patch.object(ik, "notify_pool") as notify:
        ik.alert_bridge_auth_failure(TENANT, SID, db=db)
    notify.assert_not_called()


def test_a_broken_cooldown_lookup_still_alerts():
    """A missed alert is the exact failure this function exists to prevent."""
    db = MagicMock()
    db.table.return_value.select.side_effect = RuntimeError("postgrest down")
    with patch.object(ik, "notify_pool") as notify:
        ik.alert_bridge_auth_failure(TENANT, SID, db=db)
    notify.assert_called_once()


def test_a_failing_notify_never_breaks_the_callback():
    db = _cooldown_db([])
    with patch.object(ik, "notify_pool", side_effect=RuntimeError("push down")):
        ik.alert_bridge_auth_failure(TENANT, SID, db=db)
