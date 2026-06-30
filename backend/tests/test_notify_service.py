from unittest.mock import MagicMock, patch


def _make_db(captured):
    db = MagicMock()
    tables = {}

    def table_selector(name):
        if name in tables:
            return tables[name]
        t = MagicMock()
        if name == "app_notifications":
            def _insert(row):
                captured.append(row)
                res = MagicMock()
                res.execute.return_value.data = [{"id": "n-1"}]
                return res
            t.insert.side_effect = _insert
            t.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        elif name == "callers":
            t.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
                {"user_id": "u-caller-1"}, {"user_id": "u-caller-2"}, {"user_id": None},
            ]
        elif name == "tenant_users":
            t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
                {"user_id": "u-owner"}
            ]
        tables[name] = t
        return t

    db.table.side_effect = table_selector
    return db


def test_notify_user_inserts_one_row():
    from app.services import notify
    captured = []
    db = _make_db(captured)
    with patch.object(notify, "get_supabase", return_value=db):
        notify.notify_user("t-1", "u-1", "lead_assigned", "New lead", "Call Asha", db=db)
    assert len(captured) == 1
    assert captured[0]["user_id"] == "u-1"
    assert captured[0]["type"] == "lead_assigned"
    assert captured[0]["tenant_id"] == "t-1"


def test_notify_user_dedupe_skips_when_unread_exists():
    from app.services import notify
    captured = []
    db = _make_db(captured)
    db.table("app_notifications").select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"id": "old"}]
    with patch.object(notify, "get_supabase", return_value=db):
        notify.notify_user("t-1", "u-1", "lead_replied", "Reply", "Asha replied", db=db, dedupe_lead_id="lead-1")
    assert captured == []


def test_notify_pool_fans_out_to_active_callers_and_owner():
    from app.services import notify
    captured = []
    db = _make_db(captured)
    with patch.object(notify, "get_supabase", return_value=db):
        notify.notify_pool("t-1", "handover_new", "Handover", "Ravi needs a human", db=db)
    targets = {r["user_id"] for r in captured}
    assert targets == {"u-caller-1", "u-caller-2", "u-owner"}


def test_notify_pool_excludes_given_user():
    from app.services import notify
    captured = []
    db = _make_db(captured)
    with patch.object(notify, "get_supabase", return_value=db):
        notify.notify_pool("t-1", "callback_claimable", "Callback", "Ravi", db=db, exclude_user_ids=["u-caller-1"])
    targets = {r["user_id"] for r in captured}
    assert "u-caller-1" not in targets


def test_notify_never_raises_on_db_error():
    from app.services import notify
    db = MagicMock()
    db.table.side_effect = RuntimeError("db down")
    with patch.object(notify, "get_supabase", return_value=db):
        notify.notify_user("t-1", "u-1", "x", "t", "m", db=db)
        notify.notify_pool("t-1", "x", "t", "m", db=db)


def test_notify_assigned_caller_of_reply_skips_when_unassigned():
    from app.services import notify
    captured = []
    db = _make_db(captured)
    db.table("leads").select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "assigned_to": None, "name": "Asha",
    }
    with patch.object(notify, "get_supabase", return_value=db):
        notify.notify_assigned_caller_of_reply("lead-1", "t-1", db=db)
    assert captured == []


def test_notify_assigned_caller_of_reply_notifies_assigned_caller():
    from app.services import notify
    captured = []
    db = _make_db(captured)
    db.table("leads").select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "assigned_to": "caller-1", "name": "Asha",
    }
    db.table("callers").select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "user_id": "u-caller-1",
    }
    with patch.object(notify, "get_supabase", return_value=db):
        notify.notify_assigned_caller_of_reply("lead-1", "t-1", db=db)
    assert len(captured) == 1
    assert captured[0]["user_id"] == "u-caller-1"
    assert captured[0]["type"] == "lead_replied"


def test_notify_user_skips_push_when_disabled():
    from app.services import notify
    captured = []
    db = _make_db(captured)
    with patch.object(notify, "get_supabase", return_value=db), \
         patch("app.services.notification_config.push_allowed", return_value=False), \
         patch("app.services.web_push.send_user_push") as push:
        notify.notify_user("t-1", "u-1", "callback_due", "Due", "Call now", db=db)
    assert len(captured) == 1           # in-app row still written
    push.assert_not_called()            # push suppressed


def test_notify_user_sends_push_when_allowed():
    from app.services import notify
    captured = []
    db = _make_db(captured)
    with patch.object(notify, "get_supabase", return_value=db), \
         patch("app.services.notification_config.push_allowed", return_value=True), \
         patch("app.services.web_push.send_user_push") as push:
        notify.notify_user("t-1", "u-1", "callback_due", "Due", "Call now", db=db)
    push.assert_called_once()


def test_enrolled_caller_ids_ignores_status():
    from app.services import notify
    db = MagicMock()
    t = MagicMock()
    t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"user_id": "u-active"}, {"user_id": "u-loggedout"}, {"user_id": None},
    ]
    db.table.return_value = t
    assert set(notify._enrolled_caller_user_ids(db, "t-1")) == {"u-active", "u-loggedout"}


def test_notify_callback_claimable_audience_admin_only():
    from app.services import notify
    sent = []
    db = MagicMock()
    with patch.object(notify, "_enrolled_caller_user_ids", return_value=["u-c1", "u-c2"]), \
         patch.object(notify, "_owner_user_id", return_value="u-owner"), \
         patch.object(notify, "notify_user", side_effect=lambda t, u, *a, **k: sent.append(u)):
        notify.notify_callback_claimable("t-1", title="x", message="y", lead_id="l-1",
                                         audience="admin_only", db=db)
    assert sent == ["u-owner"]


def test_notify_callback_claimable_excludes_owner():
    from app.services import notify
    sent = []
    db = MagicMock()
    with patch.object(notify, "_enrolled_caller_user_ids", return_value=["u-c1", "u-c2"]), \
         patch.object(notify, "_owner_user_id", return_value="u-owner"), \
         patch.object(notify, "notify_user", side_effect=lambda t, u, *a, **k: sent.append(u)):
        notify.notify_callback_claimable("t-1", title="x", message="y", lead_id="l-1",
                                         audience="telecallers_and_admin",
                                         exclude_user_ids=["u-c1"], db=db)
    assert set(sent) == {"u-c2", "u-owner"}


def test_notify_callback_claimable_specific_callers_only():
    from app.services import notify
    sent = []
    db = MagicMock()
    with patch.object(notify, "_enrolled_caller_user_ids", return_value=["u-c1", "u-c2", "u-c3"]), \
         patch.object(notify, "_caller_user_ids_by_ids", return_value=["u-c2", "u-c3"]) as by_ids, \
         patch.object(notify, "_owner_user_id", return_value="u-owner"), \
         patch.object(notify, "notify_user", side_effect=lambda t, u, *a, **k: sent.append(u)):
        notify.notify_callback_claimable("t-1", title="x", message="y", lead_id="l-1",
                                         audience="specific", caller_ids=["c2", "c3"], db=db)
    assert set(sent) == {"u-c2", "u-c3"}   # only the chosen callers; no owner
    by_ids.assert_called_once()
