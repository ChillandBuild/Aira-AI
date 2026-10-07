import os
import stat
from datetime import timedelta

import pytest

from aira_private_send.store import PostgresStore, SqliteStore, make_store
from conftest import T0


def test_sqlite_file_store_roundtrip(tmp_path):
    store = make_store(f"sqlite:///{tmp_path / 'a.db'}")
    store.add_opt_out("+919876543210")
    store.set_meta("k", "v")
    store.close()
    again = SqliteStore(str(tmp_path / "a.db"))
    assert again.is_opted_out("+919876543210") and again.get_meta("k") == "v"
    again.delete_meta("k")
    assert again.get_meta("k") is None


def test_schema_has_documented_tables_and_columns():
    store = SqliteStore(":memory:")
    cols = lambda t: [r["name"] for r in store._run(f"PRAGMA table_info({t})", ())[0]]
    assert {"id", "phone", "event", "template_id", "status", "reason", "send_at", "sent_at", "created_at"} <= set(cols("sends"))
    assert cols("opt_outs") == ["phone"]
    assert {"day", "event", "template_id", "sent", "failed"} == set(cols("counters"))


def test_counter_upsert_accumulates():
    store = SqliteStore(":memory:")
    store.bump_counter("2026-10-07", "purchased", "t", 1, 0)
    store.bump_counter("2026-10-07", "purchased", "t", 0, 1)
    store.bump_counter("2026-10-07", "purchased", "t", 1, 0)
    assert store.counters(["2026-10-07"])[0]["sent"] == 2
    assert store.counters(["2026-10-07"])[0]["failed"] == 1


def test_recent_send_window_ignores_skipped_and_failed():
    store = SqliteStore(":memory:")
    from aira_private_send.store import iso
    for status in ("skipped", "failed"):
        store.insert_send({"phone": "+1", "event": "e", "status": status, "created_at": iso(T0)})
    assert store.has_recent_send("+1", "e", T0 - timedelta(hours=1)) is False
    store.insert_send({"phone": "+1", "event": "e", "status": "sent", "created_at": iso(T0)})
    assert store.has_recent_send("+1", "e", T0 - timedelta(hours=1)) is True
    assert store.has_recent_send("+1", "e", T0 + timedelta(seconds=1)) is False


def test_make_store_rejects_unknown_url():
    with pytest.raises(ValueError):
        make_store("mysql://x")


def test_postgres_store_without_psycopg_gives_clear_error(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake(name, *a, **k):
        if name.startswith("psycopg"):
            raise ImportError("no psycopg")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    with pytest.raises(ImportError, match="aira-private-send\\[postgres\\]"):
        PostgresStore("postgresql://localhost/x")


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions only")
def test_new_sqlite_file_is_owner_only(tmp_path):
    path = tmp_path / "new.db"
    store = SqliteStore(str(path))
    store.add_opt_out("+919876543210")  # forces WAL sidecar files to exist
    store.close()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    for sidecar in tmp_path.glob("new.db-*"):
        assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions only")
def test_existing_sqlite_file_permissions_are_left_alone(tmp_path):
    path = tmp_path / "old.db"
    SqliteStore(str(path)).close()
    path.chmod(0o640)
    SqliteStore(str(path)).close()
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
