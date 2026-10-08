import os
import stat
from datetime import timedelta

import pytest

from anril_connector.store import PostgresStore, SqliteStore, make_store
from conftest import T0


def test_sqlite_file_store_roundtrip(tmp_path):
    store = make_store(f"sqlite:///{tmp_path / 'a.db'}")
    store.set_meta("k", "v")
    store.close()
    again = SqliteStore(str(tmp_path / "a.db"))
    assert again.get_meta("k") == "v"
    again.delete_meta("k")
    assert again.get_meta("k") is None


def test_schema_has_documented_tables_and_columns():
    store = SqliteStore(":memory:")
    cols = lambda t: [r["name"] for r in store._run(f"PRAGMA table_info({t})", ())[0]]
    assert {"id", "phone", "event", "template_id", "status", "reason", "send_at", "sent_at", "created_at"} <= set(cols("sends"))
    assert cols("opt_outs") == []  # opt-outs are gone
    assert {"day", "event", "template_id", "sent", "failed"} == set(cols("counters"))


def test_counter_upsert_accumulates():
    store = SqliteStore(":memory:")
    store.bump_counter("2026-10-07", "purchased", "t", 1, 0)
    store.bump_counter("2026-10-07", "purchased", "t", 0, 1)
    store.bump_counter("2026-10-07", "purchased", "t", 1, 0)
    assert store.counters(["2026-10-07"])[0]["sent"] == 2
    assert store.counters(["2026-10-07"])[0]["failed"] == 1


def test_retry_send_requeues_only_a_claimed_row():
    from anril_connector.store import iso
    store = SqliteStore(":memory:")
    later = T0 + timedelta(minutes=1)
    claimed = store.insert_send({"phone": "+1", "event": "e", "status": "queued", "send_at": iso(T0), "created_at": iso(T0)})
    sent = store.insert_send({"phone": "+2", "event": "e", "status": "sent", "send_at": iso(T0), "created_at": iso(T0)})
    assert store.claim_send(claimed, T0)
    store.retry_send(claimed, later, "network_error: ConnectError")
    store.retry_send(sent, later, "x")
    rows = {r["id"]: r for r in store._run("SELECT id, status, send_at, reason, claimed_at FROM sends", ())[0]}
    assert (rows[claimed]["status"], rows[claimed]["send_at"], rows[claimed]["claimed_at"]) == ("queued", iso(later), None)
    assert rows[claimed]["reason"] == "network_error: ConnectError"
    assert (rows[sent]["status"], rows[sent]["send_at"]) == ("sent", iso(T0))
    assert store.due_sends(later, 10)[0]["id"] == claimed


OLD_SCHEMA = (
    "CREATE TABLE sends (id TEXT PRIMARY KEY, phone TEXT NOT NULL, event TEXT NOT NULL, template_id TEXT, "
    "status TEXT NOT NULL, reason TEXT, send_at TEXT, sent_at TEXT, created_at TEXT NOT NULL, name TEXT, "
    "extra TEXT, claimed_at TEXT)",
    "CREATE INDEX sends_dedupe ON sends (phone, event, created_at)",
    "CREATE INDEX sends_due ON sends (status, send_at)",
    "CREATE TABLE opt_outs (phone TEXT PRIMARY KEY)",
    "CREATE TABLE counters (day TEXT NOT NULL, event TEXT NOT NULL, template_id TEXT NOT NULL, "
    "sent INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, event, template_id))",
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
)


def test_old_store_file_with_opt_outs_and_dedupe_history_still_opens_and_is_ignored(tmp_path, private_key, clock, anril):
    """A store written before the opt-out/duplicate removal: its opt_outs table, dedupe index and a recent
    'sent' row for the same phone+event must not crash the plug-in or block a send."""
    import sqlite3

    import httpx

    from anril_connector import AnrilPrivateSend
    from anril_connector.store import iso
    from conftest import LICENSE_KEY, META_TOKEN, PHONE_NUMBER_ID, public_b64

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    for statement in OLD_SCHEMA:
        conn.execute(statement)
    conn.execute("INSERT INTO opt_outs (phone) VALUES ('+919876543210')")
    conn.execute(
        "INSERT INTO sends (id, phone, event, template_id, status, created_at) VALUES ('old', '+919876543210', "
        "'purchased', 'tpl-1', 'sent', ?)", (iso(clock.now),))
    conn.commit()
    conn.close()
    c = AnrilPrivateSend(LICENSE_KEY, META_TOKEN, PHONE_NUMBER_ID, public_b64(private_key),
                         store=f"sqlite:///{path}", http=httpx.Client(transport=httpx.MockTransport(anril)), clock=clock)
    assert c.track("purchased", "9876543210").status == "sent"
    c.close()


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
    with pytest.raises(ImportError, match="anril-connector\\[postgres\\]"):
        PostgresStore("postgresql://localhost/x")


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions only")
def test_new_sqlite_file_is_owner_only(tmp_path):
    path = tmp_path / "new.db"
    store = SqliteStore(str(path))
    store.set_meta("k", "v")  # forces WAL sidecar files to exist
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
