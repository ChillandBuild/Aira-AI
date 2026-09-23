"""Tests for record_catalog_quote() -- the visibility-only record of a
WhatsApp reply that quoted a real catalog price. Not a pipeline stage: just
confirms the upsert shape (one row per lead, on_conflict="lead_id") is
called correctly.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.catalog_quotes import record_catalog_quote


class RecordCatalogQuoteTests(unittest.TestCase):
    def test_upserts_one_row_per_lead(self):
        db = MagicMock()

        record_catalog_quote(
            "tenant-1", "lead-1", "item-1", "DSLR Camera Bag", 320000, db=db,
        )

        db.table.assert_called_once_with("catalog_quotes")
        upsert_call = db.table.return_value.upsert
        upsert_call.assert_called_once_with(
            {
                "tenant_id": "tenant-1",
                "lead_id": "lead-1",
                "catalog_item_id": "item-1",
                "item_name": "DSLR Camera Bag",
                "amount_paise": 320000,
                "amount_is_estimate": True,
            },
            on_conflict="lead_id",
        )
        upsert_call.return_value.execute.assert_called_once()

    def test_amount_is_estimate_can_be_overridden(self):
        db = MagicMock()

        record_catalog_quote(
            "tenant-1", "lead-1", "item-1", "DSLR Camera Bag", 320000,
            amount_is_estimate=False, db=db,
        )

        payload = db.table.return_value.upsert.call_args[0][0]
        self.assertFalse(payload["amount_is_estimate"])


if __name__ == "__main__":
    unittest.main()
