"""Minimal in-memory stand-in for the supabase-py client, covering the query chain the
knowledge auto-sort services use: table().select/insert/update/delete, eq/neq/is_/in_,
order, limit, execute. Rows get sequential created_at values so "newest first"
ordering is deterministic, and deleting a knowledge_documents row cascades the way the
real foreign keys do."""
import itertools
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

_DEFAULTS = {
    "knowledge_documents": {
        "status": "processing", "rule_lines": [], "sorted_at": None, "sort_state": None,
        "source_text": None, "full_text": None, "campaign_tag_id": None,
        "storage_path": None, "error_message": None, "name": "doc.txt",
    },
    "knowledge_reviews": {
        "status": "pending", "origin": "upload", "base_version_id": None,
        "proposed_description": "", "proposed_facts": "", "proposed_rule_lines": [],
        "conflicts": [], "fact_disagreements": [], "unverified": [], "left_out": [],
        "left_out_rules": [], "truncated": False, "replaces_document_id": None, "created_by": None,
        "suggested_handover": "",
    },
    "knowledge_versions": {"document_id": None, "created_by": None, "content": ""},
}

# child table -> (column, on-delete behaviour) when a knowledge_documents row is deleted
_CASCADES = {
    "knowledge_chunks": ("document_id", "delete"),
    "knowledge_versions": ("document_id", "delete"),
    "knowledge_reviews": ("document_id", "delete"),
}
_SET_NULL = {"knowledge_reviews": "replaces_document_id"}


class FakeSupabase:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self._clock = itertools.count(1)
        self.storage = MagicMock()

    def table(self, name: str) -> "_Query":
        return _Query(self, name)

    def rows(self, name: str) -> list[dict]:
        return self.tables.setdefault(name, [])

    def add(self, _table: str, **row) -> dict:
        return _Query(self, _table).insert(row).execute().data[0]

    def _stamp(self) -> str:
        return f"2026-01-01T00:00:{next(self._clock):012d}"


class _Query:
    def __init__(self, db: FakeSupabase, name: str):
        self.db, self.name = db, name
        self.op, self.payload = "select", None
        self.filters: list = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, _columns: str = "*", count: str | None = None):
        self.op = "select"
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload: dict):
        self.op, self.payload = "update", payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def neq(self, column, value):
        self.filters.append(lambda r: r.get(column) != value)
        return self

    def is_(self, column, value):
        assert value == "null", "fake only supports is_(col, 'null')"
        self.filters.append(lambda r: r.get(column) is None)
        return self

    def in_(self, column, values):
        allowed = set(values)
        self.filters.append(lambda r: r.get(column) in allowed)
        return self

    def order(self, column, desc: bool = False):
        self._order = (column, desc)
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def _matching(self) -> list[dict]:
        return [r for r in self.db.rows(self.name) if all(f(r) for f in self.filters)]

    def execute(self):
        if self.op == "insert":
            payloads = self.payload if isinstance(self.payload, list) else [self.payload]
            created = []
            for p in payloads:
                row = {**_DEFAULTS.get(self.name, {}), **p}
                row.setdefault("id", str(uuid.uuid4()))
                row.setdefault("created_at", self.db._stamp())
                self.db.rows(self.name).append(row)
                created.append(dict(row))
            return SimpleNamespace(data=created, count=len(created))

        matched = self._matching()
        if self.op == "update":
            for r in matched:
                r.update(self.payload)
            return SimpleNamespace(data=[dict(r) for r in matched], count=len(matched))

        if self.op == "delete":
            ids = {r["id"] for r in matched}
            self.db.tables[self.name] = [r for r in self.db.rows(self.name) if r not in matched]
            if self.name == "knowledge_documents":
                for child, (column, _) in _CASCADES.items():
                    self.db.tables[child] = [r for r in self.db.rows(child) if r.get(column) not in ids]
                for child, column in _SET_NULL.items():
                    for r in self.db.rows(child):
                        if r.get(column) in ids:
                            r[column] = None
            return SimpleNamespace(data=[dict(r) for r in matched], count=len(matched))

        rows = [dict(r) for r in matched]
        if self._order:
            column, desc = self._order
            rows.sort(key=lambda r: (r.get(column) is None, r.get(column) or ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return SimpleNamespace(data=rows, count=len(rows))
