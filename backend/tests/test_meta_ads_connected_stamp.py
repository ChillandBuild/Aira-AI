"""Connecting a Meta ad account starts the join rule (which ads Anril tracks).

A new account gets a connected-at time, history "from today", and a fresh
snapshot of running ads on its next sync. Reconnecting the same account (a token
refresh) must not reset any of that, or the tenant's chosen history date and the
ads tracked since joining would silently change.
"""
from unittest.mock import MagicMock, patch


def _upserted_rows(db) -> dict[str, dict]:
    rows = {}
    for call in db.table.return_value.upsert.call_args_list:
        payload = call.args[0]
        for row in payload if isinstance(payload, list) else [payload]:
            rows[row["key"]] = row
    return rows


def _run(previous_account, connected_at):
    from app.routes.app_settings import _stamp_meta_ads_connected

    db = MagicMock()
    values = {"meta_ads_account_id": previous_account, "meta_ads_connected_at": connected_at}
    with patch("app.routes.app_settings._get_setting_value", side_effect=lambda _db, _t, key: values.get(key)):
        _stamp_meta_ads_connected(db, "tenant-1", "act_42")
    return db


def test_new_account_stamps_connected_at_and_history_from_today():
    db = _run(previous_account=None, connected_at=None)

    rows = _upserted_rows(db)
    assert set(rows) == {"meta_ads_connected_at", "meta_ads_sync_start_date"}
    assert rows["meta_ads_connected_at"]["value"][:10] == rows["meta_ads_sync_start_date"]["value"]
    assert all(r["tenant_id"] == "tenant-1" and r["is_secret"] is False for r in rows.values())
    # The old snapshot/backfill markers are cleared so the next sync re-snapshots.
    deleted_keys = db.table.return_value.delete.return_value.eq.return_value.in_.call_args.args[1]
    assert set(deleted_keys) == {"meta_ads_join_snapshot_account", "meta_ads_backfilled_from"}


def test_switching_to_a_different_account_restamps():
    db = _run(previous_account="act_7", connected_at="2026-01-01T00:00:00+00:00")
    assert "meta_ads_connected_at" in _upserted_rows(db)


def test_reconnecting_the_same_account_keeps_the_join_time_and_history():
    db = _run(previous_account="42", connected_at="2026-01-01T00:00:00+00:00")
    assert _upserted_rows(db) == {}
    db.table.return_value.delete.assert_not_called()
