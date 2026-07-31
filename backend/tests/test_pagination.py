"""Regression guard for the generic Supabase pagination helper: PostgREST
caps any single .execute() at 1000 rows with no error, so any fetch that
could return more than that must page through with .range()."""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.pagination import fetch_all_rows


class FakeQueryBuilder:
    """Simulates a Supabase query builder: .range(start, end) returns an
    object whose .execute() yields the next page in sequence."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def range(self, start, end):
        idx = len(self.calls)
        self.calls.append((start, end))
        data = self.pages[idx] if idx < len(self.pages) else []
        result = MagicMock()
        result.execute.return_value = MagicMock(data=data)
        return result


class FetchAllRowsTests(unittest.TestCase):
    def test_stops_after_a_short_page(self):
        pages = [[{"id": i} for i in range(1000)], [{"id": i} for i in range(50)]]
        query = FakeQueryBuilder(pages)

        rows = asyncio.run(fetch_all_rows(lambda: query, page_size=1000))

        self.assertEqual(len(rows), 1050)
        self.assertEqual(query.calls, [(0, 999), (1000, 1999)])

    def test_empty_result_returns_empty_list(self):
        query = FakeQueryBuilder([[]])

        rows = asyncio.run(fetch_all_rows(lambda: query, page_size=1000))

        self.assertEqual(rows, [])
        self.assertEqual(query.calls, [(0, 999)])

    def test_exact_multiple_of_page_size_fetches_one_more_empty_page(self):
        """A tenant with exactly 1000 rows must not be mistaken for having
        more -- the loop must fetch page 2, see it's empty, and stop."""
        pages = [[{"id": i} for i in range(1000)], []]
        query = FakeQueryBuilder(pages)

        rows = asyncio.run(fetch_all_rows(lambda: query, page_size=1000))

        self.assertEqual(len(rows), 1000)
        self.assertEqual(len(query.calls), 2)

    def test_none_data_is_treated_as_an_empty_page(self):
        query = FakeQueryBuilder([None])

        rows = asyncio.run(fetch_all_rows(lambda: query, page_size=1000))

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
