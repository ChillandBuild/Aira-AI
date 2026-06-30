from unittest.mock import MagicMock, patch


def _build_db(due_jobs, claimable_jobs, leads, callers, updates):
    def table_selector(name):
        t = MagicMock()
        if name == "app_settings":
            t.select.return_value.eq.return_value.execute.return_value.data = [{"tenant_id": "t-1"}]
        elif name == "follow_up_jobs":
            chain = t.select.return_value.eq.return_value.eq.return_value.eq.return_value.lte.return_value.is_.return_value.limit.return_value
            chain.execute.side_effect = [MagicMock(data=due_jobs), MagicMock(data=claimable_jobs)]

            def _update(payload):
                upd = MagicMock()
                def _eq1(*a, **k):
                    inner = MagicMock()
                    def _eq2(*a2, **k2):
                        updates.append(payload)
                        res = MagicMock(); res.execute.return_value.data = [{"id": "x"}]; return res
                    inner.eq.side_effect = _eq2
                    return inner
                upd.eq.side_effect = _eq1
                return upd
            t.update.side_effect = _update
        elif name == "leads":
            def _eq(col, val):
                inner = MagicMock()
                inner.eq.return_value.maybe_single.return_value.execute.return_value.data = leads.get(val)
                return inner
            t.select.return_value.eq.side_effect = _eq
        elif name == "callers":
            def _eq(col, val):
                inner = MagicMock()
                inner.maybe_single.return_value.execute.return_value.data = callers.get(val)
                return inner
            t.select.return_value.eq.side_effect = _eq
        return t

    db = MagicMock(); db.table.side_effect = table_selector
    return db


def _cfg(**over):
    base = {"claimable_threshold_minutes": 15, "claimable_audience": "telecallers_and_admin"}
    base.update(over)
    return base


def test_due_pass_pushes_to_assigned_and_sets_guard():
    from app.services import callback_notifications as cn
    updates, sent = [], []
    db = _build_db(
        [{"id": "j1", "lead_id": "l1"}], [],
        {"l1": {"id": "l1", "name": "Asha", "assigned_to": "c1"}},
        {"c1": {"user_id": "u1"}}, updates,
    )
    with patch.object(cn, "get_supabase", return_value=db), \
         patch.object(cn, "get_telecalling_config", return_value={"enabled": True}), \
         patch.object(cn, "get_notification_config", return_value=_cfg()), \
         patch.object(cn, "notify_user", side_effect=lambda t, u, ty, *a, **k: sent.append((u, ty))), \
         patch.object(cn, "notify_callback_claimable") as claim:
        res = cn.process_callback_notifications()
    assert res["due"] == 1
    assert sent == [("u1", "callback_due")]
    assert any("due_notified_at" in u for u in updates)
    claim.assert_not_called()


def test_claimable_pass_broadcasts_regardless_of_shift():
    from app.services import callback_notifications as cn
    updates = []
    db = _build_db(
        [], [{"id": "j2", "lead_id": "l2"}],
        {"l2": {"id": "l2", "name": "Ravi", "assigned_to": "c2"}},
        {"c2": {"user_id": "u2"}}, updates,
    )
    with patch.object(cn, "get_supabase", return_value=db), \
         patch.object(cn, "get_telecalling_config", return_value={"enabled": True}), \
         patch.object(cn, "get_notification_config", return_value=_cfg(claimable_audience="admin_only")), \
         patch.object(cn, "notify_user"), \
         patch.object(cn, "notify_callback_claimable") as claim:
        res = cn.process_callback_notifications()
    assert res["claimable"] == 1
    claim.assert_called_once()
    assert claim.call_args.kwargs["audience"] == "admin_only"
    assert claim.call_args.kwargs["exclude_user_ids"] == ["u2"]
    assert any("claimable_notified_at" in u for u in updates)


def test_disabled_tenant_skipped():
    from app.services import callback_notifications as cn
    updates = []
    db = _build_db([{"id": "j", "lead_id": "l"}], [], {}, {}, updates)
    with patch.object(cn, "get_supabase", return_value=db), \
         patch.object(cn, "get_telecalling_config", return_value={"enabled": False}), \
         patch.object(cn, "get_notification_config", return_value=_cfg()), \
         patch.object(cn, "notify_user") as nu, \
         patch.object(cn, "notify_callback_claimable") as claim:
        res = cn.process_callback_notifications()
    assert res == {"due": 0, "claimable": 0}
    nu.assert_not_called(); claim.assert_not_called()
