"""Warnings: one row per call+type, instant pushes only for serious types, capped per hour."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_alerts as ca

NOW = datetime(2026, 9, 26, 5, 0, tzinfo=timezone.utc)


class _FakeDb:
    """Tiny in-memory stand-in for the three tables call_alerts touches."""

    def __init__(self, alerts=None, users=None, callers=None):
        self.rows = {"call_alerts": list(alerts or []), "tenant_users": list(users or []), "callers": list(callers or [])}

    def table(self, name):
        return _Q(self, name)


class _Q:
    def __init__(self, db, name):
        self.db, self.name, self.filters, self.payload, self.op = db, name, [], None, "select"

    def select(self, *a, **k): return self
    def insert(self, payload): self.op, self.payload = "insert", payload; return self
    def update(self, payload): self.op, self.payload = "update", payload; return self
    def eq(self, c, v): self.filters.append(lambda r: r.get(c) == v); return self
    def in_(self, c, vs): self.filters.append(lambda r: r.get(c) in vs); return self
    def gte(self, c, v): self.filters.append(lambda r: r.get(c) is not None and r.get(c) >= v); return self
    def lt(self, c, v): self.filters.append(lambda r: r.get(c) is not None and r.get(c) < v); return self
    def is_(self, c, v): self.filters.append(lambda r: r.get(c) is None); return self
    def not_(self): return self
    def limit(self, n): return self
    def order(self, *a, **k): return self

    def execute(self):
        rows = self.db.rows[self.name]
        if self.op == "insert":
            p = self.payload
            if p.get("call_log_id") and any(r.get("call_log_id") == p["call_log_id"] and r["type"] == p["type"] for r in rows):
                raise Exception("duplicate key value violates unique constraint")
            rows.append(dict(p))
            return MagicMock(data=[p])
        hit = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "update":
            for r in hit:
                r.update(self.payload)
        return MagicMock(data=hit, count=len(hit))


class RaiseAlertTests(unittest.TestCase):
    def _db(self, alerts=None):
        return _FakeDb(alerts, users=[{"tenant_id": "t", "user_id": "admin-1", "role": "owner"}],
                       callers=[{"id": "c1", "name": "Priya", "user_id": "u-priya"}])

    def test_duplicate_call_type_is_ignored(self):
        db = self._db()
        with patch.object(ca, "notify_user") as notify:
            self.assertTrue(ca.raise_alert(db, tenant_id="t", type="crm_mismatch", call_log_id="call-1", caller_id="c1", now=NOW))
            self.assertFalse(ca.raise_alert(db, tenant_id="t", type="crm_mismatch", call_log_id="call-1", caller_id="c1", now=NOW))
        self.assertEqual(len(db.rows["call_alerts"]), 1)
        notify.assert_not_called()  # not an instant type

    def test_instant_type_notifies_admin_once_per_hour_per_telecaller(self):
        db = self._db()
        with patch.object(ca, "notify_user") as notify:
            ca.raise_alert(db, tenant_id="t", type="rude", call_log_id="call-1", caller_id="c1", quote="q", now=NOW)
            ca.raise_alert(db, tenant_id="t", type="wrong_info", call_log_id="call-2", caller_id="c1", quote="q", now=NOW + timedelta(minutes=10))
            ca.raise_alert(db, tenant_id="t", type="rude", call_log_id="call-3", caller_id="c1", quote="q", now=NOW + timedelta(minutes=61))
        self.assertEqual(notify.call_count, 2)
        self.assertEqual(notify.call_args.args[1], "admin-1")
        self.assertEqual(len(db.rows["call_alerts"]), 3)

    def test_unknown_type_rejected(self):
        with self.assertRaises(ValueError):
            ca.raise_alert(self._db(), tenant_id="t", type="banana", now=NOW)


class LeadSourceTests(unittest.TestCase):
    def test_threshold(self):
        self.assertTrue(ca.lead_source_is_bad(total=10, bad=3))
        self.assertFalse(ca.lead_source_is_bad(total=10, bad=2))
        self.assertFalse(ca.lead_source_is_bad(total=9, bad=9))


if __name__ == "__main__":
    unittest.main()
