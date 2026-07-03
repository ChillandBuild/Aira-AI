"""Tests for `get_purchased_quantity` (migration 128)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.entitlements import get_purchased_quantity


def _query(data):
    result = MagicMock()
    result.data = data
    return result


class GetPurchasedQuantityTests(unittest.TestCase):
    def test_no_rows_returns_zero(self):
        tbl = MagicMock()
        tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value = _query([])
        db = MagicMock()
        db.table.return_value = tbl
        self.assertEqual(get_purchased_quantity(db, "tenant-1", "telecaller_seats"), 0)

    def test_single_row_returns_its_quantity(self):
        tbl = MagicMock()
        tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value = _query([{"quantity": 3}])
        db = MagicMock()
        db.table.return_value = tbl
        self.assertEqual(get_purchased_quantity(db, "tenant-1", "telecaller_seats"), 3)


if __name__ == "__main__":
    unittest.main()
