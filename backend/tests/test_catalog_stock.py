"""Tests for decrement_stock() -- the race-safe stock deduction called on a
CONFIRMED sale only (never on an AI catalog quote, which is interest, not a
sale). The actual race-safety lives in the decrement_catalog_stock() SQL
function's WHERE clause (195_catalog_stock.sql); this only confirms the
Python wrapper calls the RPC correctly and interprets its result.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.catalog_stock import decrement_stock


class DecrementStockTests(unittest.TestCase):
    def test_returns_true_when_the_rpc_reports_rows_updated(self):
        db = MagicMock()
        db.rpc.return_value.execute.return_value = MagicMock(data=[{"stock_quantity": 3}])

        result = decrement_stock("tenant-1", "item-1", 2, db=db)

        self.assertTrue(result)
        db.rpc.assert_called_once_with(
            "decrement_catalog_stock",
            {"p_item_id": "item-1", "p_tenant_id": "tenant-1", "p_qty": 2},
        )

    def test_returns_false_when_not_enough_stock(self):
        """The SQL function's WHERE clause matches zero rows when stock is
        insufficient -- this is the actual race-safety guard, exercised here
        only at the Python-wrapper boundary."""
        db = MagicMock()
        db.rpc.return_value.execute.return_value = MagicMock(data=[])

        result = decrement_stock("tenant-1", "item-1", 5, db=db)

        self.assertFalse(result)

    def test_returns_false_when_item_does_not_track_stock(self):
        """NULL stock_quantity never matches the RPC's `is not null` guard,
        so an item with no tracked stock reports False -- callers must not
        treat this as an error, just as 'nothing to deduct'."""
        db = MagicMock()
        db.rpc.return_value.execute.return_value = MagicMock(data=[])

        result = decrement_stock("tenant-1", "service-item", 1, db=db)

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
