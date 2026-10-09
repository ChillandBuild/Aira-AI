"""In-memory Supabase stand-in for the Aira Brain tests: fake_supabase.FakeSupabase plus the
filters the brain reads use (gte, lte, range) and an exact count that ignores limit()."""
from types import SimpleNamespace

from fake_supabase import FakeSupabase, _Query


class _BrainQuery(_Query):
    def __init__(self, db, name):
        super().__init__(db, name)
        self._range: tuple[int, int] | None = None
        self.op_count = False

    def select(self, _columns="*", count=None):
        self.op_count = count is not None
        return super().select(_columns, count)

    def gte(self, column, value):
        self.filters.append(lambda r: r.get(column) is not None and str(r.get(column)) >= str(value))
        return self

    def lte(self, column, value):
        self.filters.append(lambda r: r.get(column) is not None and str(r.get(column)) <= str(value))
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        if self.op != "select":
            return super().execute()
        matched = [dict(r) for r in self._matching()]
        for column, desc in reversed(self._order):  # stable sorts, last key first
            matched.sort(key=lambda r, c=column: (r.get(c) is None, r.get(c) or ""), reverse=desc)
        total = len(matched)
        if self._range:
            matched = matched[self._range[0]: self._range[1] + 1]
        if self._limit is not None:
            matched = matched[: self._limit]
        return SimpleNamespace(data=matched, count=total)


class BrainDB(FakeSupabase):
    def table(self, name):
        return _BrainQuery(self, name)
