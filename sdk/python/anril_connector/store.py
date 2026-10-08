"""Local state for the plug-in: the send log and retry queue, daily counters, bundle cache.
Everything stays on the client's machine. SqliteStore (stdlib) is the default; PostgresStore needs
`pip install anril-connector[postgres]`."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple, Union

_TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"  # fixed width, so text comparison orders correctly


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime(_TS_FORMAT)


def parse_iso(value: str) -> datetime:
    return datetime.strptime(value, _TS_FORMAT).replace(tzinfo=timezone.utc)


class Store(Protocol):
    def get_meta(self, key: str) -> Optional[str]: ...
    def set_meta(self, key: str, value: str) -> None: ...
    def delete_meta(self, key: str) -> None: ...
    def insert_send(self, row: Dict[str, Any]) -> str: ...
    def claim_send(self, send_id: str, now: datetime) -> bool: ...
    def finish_send(self, send_id: str, status: str, reason: Optional[str], sent_at: Optional[datetime]) -> None: ...
    def due_sends(self, now: datetime, limit: int) -> List[Dict[str, Any]]: ...
    def retry_send(self, send_id: str, send_at: datetime, reason: Optional[str]) -> None: ...
    def fail_stuck(self, before: datetime) -> int: ...
    def bump_counter(self, day: str, event: str, template_id: str, sent: int, failed: int) -> None: ...
    def counters(self, days: Sequence[str]) -> List[Dict[str, Any]]: ...
    def close(self) -> None: ...


_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS sends (
        id TEXT PRIMARY KEY, phone TEXT NOT NULL, event TEXT NOT NULL, template_id TEXT,
        status TEXT NOT NULL, reason TEXT, send_at TEXT, sent_at TEXT, created_at TEXT NOT NULL,
        name TEXT, extra TEXT, claimed_at TEXT)""",
    "CREATE INDEX IF NOT EXISTS sends_due ON sends (status, send_at)",
    """CREATE TABLE IF NOT EXISTS counters (
        day TEXT NOT NULL, event TEXT NOT NULL, template_id TEXT NOT NULL,
        sent INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (day, event, template_id))""",
    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
)
_SEND_COLUMNS = ("id", "phone", "event", "template_id", "status", "reason", "send_at", "sent_at", "created_at", "name", "extra", "claimed_at")


class _SqlStore:
    """Shared SQL for both backends; subclasses supply `_run` and the placeholder style."""

    _placeholder = "?"

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def _init_schema(self) -> None:
        for statement in _SCHEMA:
            self._run(statement, ())

    def _run(self, sql: str, params: Tuple[Any, ...]) -> Tuple[List[Dict[str, Any]], int]:
        raise NotImplementedError

    def _q(self, sql: str) -> str:
        return sql.replace("?", self._placeholder)

    def _exec(self, sql: str, *params: Any) -> Tuple[List[Dict[str, Any]], int]:
        return self._run(self._q(sql), params)

    def get_meta(self, key: str) -> Optional[str]:
        rows, _ = self._exec("SELECT value FROM meta WHERE key = ?", key)
        return rows[0]["value"] if rows else None

    def set_meta(self, key: str, value: str) -> None:
        self._exec("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", key, value)

    def delete_meta(self, key: str) -> None:
        self._exec("DELETE FROM meta WHERE key = ?", key)

    def insert_send(self, row: Dict[str, Any]) -> str:
        send_id = row.get("id") or str(uuid.uuid4())
        full = {**{c: None for c in _SEND_COLUMNS}, **row, "id": send_id}
        full["extra"] = json.dumps(row["extra"]) if row.get("extra") else None
        marks = ", ".join("?" for _ in _SEND_COLUMNS)
        self._exec(f"INSERT INTO sends ({', '.join(_SEND_COLUMNS)}) VALUES ({marks})", *(full[c] for c in _SEND_COLUMNS))
        return send_id

    def claim_send(self, send_id: str, now: datetime) -> bool:
        """queued -> sending, atomically; False when someone else already claimed it."""
        _, count = self._exec(
            "UPDATE sends SET status = 'sending', claimed_at = ? WHERE id = ? AND status = 'queued'", iso(now), send_id)
        return count == 1

    def finish_send(self, send_id: str, status: str, reason: Optional[str], sent_at: Optional[datetime]) -> None:
        self._exec(
            "UPDATE sends SET status = ?, reason = ?, sent_at = ? WHERE id = ?",
            status, reason[:300] if reason else None, iso(sent_at) if sent_at else None, send_id)

    def due_sends(self, now: datetime, limit: int) -> List[Dict[str, Any]]:
        rows, _ = self._exec(
            "SELECT * FROM sends WHERE status = 'queued' AND send_at <= ? ORDER BY send_at LIMIT ?", iso(now), limit)
        return [{**r, "extra": json.loads(r["extra"]) if r.get("extra") else {}} for r in rows]

    def retry_send(self, send_id: str, send_at: datetime, reason: Optional[str]) -> None:
        """A claimed send that provably never reached Meta goes back to 'queued' for run_due."""
        self._exec(
            "UPDATE sends SET status = 'queued', send_at = ?, reason = ?, claimed_at = NULL "
            "WHERE id = ? AND status = 'sending'", iso(send_at), reason[:300] if reason else None, send_id)

    def fail_stuck(self, before: datetime) -> int:
        """'sending' rows left by a crash are failed, never re-sent: Meta may already have delivered them."""
        _, count = self._exec(
            "UPDATE sends SET status = 'failed', reason = 'interrupted' WHERE status = 'sending' AND claimed_at < ?", iso(before))
        return count

    def bump_counter(self, day: str, event: str, template_id: str, sent: int, failed: int) -> None:
        self._exec(
            "INSERT INTO counters (day, event, template_id, sent, failed) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (day, event, template_id) DO UPDATE SET sent = counters.sent + excluded.sent, "
            "failed = counters.failed + excluded.failed", day, event, template_id, sent, failed)

    def counters(self, days: Sequence[str]) -> List[Dict[str, Any]]:
        marks = ", ".join("?" for _ in days)
        rows, _ = self._exec(
            f"SELECT day, event, template_id, sent, failed FROM counters WHERE day IN ({marks}) ORDER BY day, event, template_id", *days)
        return rows


class SqliteStore(_SqlStore):
    def __init__(self, path: str = "anril_connector.db"):
        super().__init__()
        is_new_file = path != ":memory:" and not os.path.exists(path)
        self._conn = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if is_new_file and os.name == "posix":
            os.chmod(path, 0o600)  # the db holds customer phone numbers; set before WAL files copy its mode
        self._conn.execute("PRAGMA busy_timeout = 30000")
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._init_schema()

    def _run(self, sql: str, params: Tuple[Any, ...]) -> Tuple[List[Dict[str, Any]], int]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()], cur.rowcount

    def close(self) -> None:
        self._conn.close()


class PostgresStore(_SqlStore):
    _placeholder = "%s"

    def __init__(self, dsn: str):
        super().__init__()
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise ImportError("PostgresStore needs psycopg: pip install 'anril-connector[postgres]'") from exc
        self._conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
        self._init_schema()

    def _run(self, sql: str, params: Tuple[Any, ...]) -> Tuple[List[Dict[str, Any]], int]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            rows = cur.fetchall() if cur.description else []
            return [dict(r) for r in rows], cur.rowcount

    def close(self) -> None:
        self._conn.close()


def make_store(spec: Union[str, Store]) -> Store:
    """'sqlite:///file.db', 'sqlite:////abs/file.db', 'sqlite:///:memory:', 'postgresql://...', or a Store."""
    if not isinstance(spec, str):
        return spec
    if spec.startswith("sqlite:///"):
        return SqliteStore(spec[len("sqlite:///"):] or "anril_connector.db")
    if spec.startswith(("postgres://", "postgresql://")):
        return PostgresStore(spec)
    raise ValueError("store must be a sqlite:/// or postgresql:// URL, or a Store object")
