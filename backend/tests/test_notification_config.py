from unittest.mock import MagicMock, patch


def test_in_quiet_hours_wraps_midnight():
    from app.services.notification_config import _in_quiet_hours
    q = {"enabled": True, "start_hour": 22, "end_hour": 8}
    assert _in_quiet_hours(q, 23) is True
    assert _in_quiet_hours(q, 2) is True
    assert _in_quiet_hours(q, 8) is False
    assert _in_quiet_hours(q, 12) is False


def test_in_quiet_hours_same_day_window():
    from app.services.notification_config import _in_quiet_hours
    q = {"enabled": True, "start_hour": 9, "end_hour": 17}
    assert _in_quiet_hours(q, 12) is True
    assert _in_quiet_hours(q, 18) is False


def test_get_config_merges_defaults_for_missing_subkeys():
    from app.services import notification_config as nc
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "value": '{"claimable_threshold_minutes": 20, "events": {"lead_replied": false}}'
    }
    cfg = nc.get_notification_config("t-1", db=db)
    assert cfg["claimable_threshold_minutes"] == 20
    assert cfg["events"]["lead_replied"] is False          # override kept
    assert cfg["events"]["callback_due"] is True            # default filled in
    assert cfg["push_enabled"] is True                      # default filled in
    assert cfg["quiet_hours"]["start_hour"] == 22           # default subtree filled in


def test_push_allowed_respects_master_and_event_toggle():
    from app.services import notification_config as nc
    base = {
        "push_enabled": True,
        "events": {"callback_due": False, "lead_assigned": True},
        "quiet_hours": {"enabled": False, "start_hour": 22, "end_hour": 8},
    }
    with patch.object(nc, "get_notification_config", return_value={**nc._NOTIFICATION_CONFIG_DEFAULT, **base}):
        assert nc.push_allowed("t-1", "lead_assigned") is True
        assert nc.push_allowed("t-1", "callback_due") is False   # event off
        assert nc.push_allowed("t-1", "unlisted_type") is True   # unknown → allowed


def test_push_allowed_false_when_master_off():
    from app.services import notification_config as nc
    cfg = {**nc._NOTIFICATION_CONFIG_DEFAULT, "push_enabled": False}
    with patch.object(nc, "get_notification_config", return_value=cfg):
        assert nc.push_allowed("t-1", "lead_assigned") is False


def test_get_config_merges_delay_minutes():
    from app.services import notification_config as nc
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "value": '{"whatsapp_notifications": {"delay_minutes": 10}}'
    }
    cfg = nc.get_notification_config("t-1", db=db)
    assert cfg["whatsapp_notifications"]["delay_minutes"] == 10
    assert cfg["whatsapp_notifications"]["enabled"] is False

