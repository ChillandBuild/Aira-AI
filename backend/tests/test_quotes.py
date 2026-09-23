"""Tests for app/services/quotes.py -- quote-and-pay inside the WhatsApp
thread. Covers: prices are never re-derived from anything but the snapshot
taken at send time, create_payment_link failure doesn't half-create a quote,
and confirm_quote_payment's race-safety (the actual point of the .neq
filter, not just a style choice).
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.quotes import confirm_quote_payment, create_quote, get_quote_tenant_id, quote_summary_block


class QuoteSummaryBlockTests(unittest.TestCase):
    def test_formats_lines_and_total_in_rupees(self):
        items = [
            {"name": "DSLR Bag", "price_paise": 320000, "qty": 1},
            {"name": "Lens Cap", "price_paise": 15000, "qty": 2},
        ]
        text = quote_summary_block(items, 350000)
        self.assertIn("DSLR Bag x1 — ₹3200", text)
        self.assertIn("Lens Cap x2 — ₹300", text)
        self.assertIn("Total: ₹3500", text)

    def test_matches_intake_rupees_formatting_exactly(self):
        """Deliberately duplicated, not imported, from intake._rupees -- this
        pins the two to stay in sync rather than silently drift apart."""
        from app.services.intake import _rupees as intake_rupees
        from app.services.quotes import _rupees as quotes_rupees

        for paise in [0, 100, 150, 99, 320000, 1, 999999]:
            self.assertEqual(intake_rupees(paise), quotes_rupees(paise))


class CreateQuoteTests(unittest.IsolatedAsyncioTestCase):
    def _db(self, insert_id="quote-1"):
        db = MagicMock()
        db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": insert_id}])
        db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
        return db

    @patch("app.services.quotes.create_payment_link", new_callable=AsyncMock)
    async def test_builds_snapshot_and_returns_summary_with_link(self, mock_link):
        mock_link.return_value = {"payment_link_url": "https://rzp.io/abc", "razorpay_payment_link_id": "plink_1"}
        db = self._db()

        result = await create_quote(
            "tenant-1", "lead-1",
            [{"catalog_item_id": "item-1", "name": "DSLR Bag", "price_paise": 320000, "qty": 1}],
            customer_name="Priya", customer_phone="+919876543210", db=db,
        )

        self.assertEqual(result["quote_id"], "quote-1")
        self.assertIn("https://rzp.io/abc", result["summary_text"])
        self.assertEqual(result["payment_link"], "https://rzp.io/abc")
        mock_link.assert_awaited_once()
        call_kwargs = mock_link.call_args.kwargs
        self.assertEqual(call_kwargs["idempotency_key"], "quote:quote-1:payment_link")
        self.assertEqual(call_kwargs["notes"], {"quote_id": "quote-1"})
        self.assertEqual(call_kwargs["amount_paise"], 320000)

    async def test_drops_unpriced_items_and_returns_none_if_nothing_survives(self):
        db = self._db()
        result = await create_quote(
            "tenant-1", "lead-1",
            [{"catalog_item_id": "item-1", "name": "Mystery Item", "price_paise": None, "qty": 1}],
            customer_name="Priya", customer_phone="+919876543210", db=db,
        )
        self.assertIsNone(result)
        db.table.return_value.insert.assert_not_called()

    async def test_zero_qty_item_is_dropped(self):
        db = self._db()
        result = await create_quote(
            "tenant-1", "lead-1",
            [{"catalog_item_id": "item-1", "name": "DSLR Bag", "price_paise": 320000, "qty": 0}],
            customer_name="Priya", customer_phone="+919876543210", db=db,
        )
        self.assertIsNone(result)

    @patch("app.services.quotes.create_payment_link", new_callable=AsyncMock)
    async def test_payment_link_failure_returns_none_not_a_half_created_quote(self, mock_link):
        mock_link.side_effect = RuntimeError("Razorpay down")
        db = self._db()

        result = await create_quote(
            "tenant-1", "lead-1",
            [{"catalog_item_id": "item-1", "name": "DSLR Bag", "price_paise": 320000, "qty": 1}],
            customer_name="Priya", customer_phone="+919876543210", db=db,
        )

        self.assertIsNone(result)
        # The quote row was inserted (status='sent') before the link attempt --
        # update() to attach the link is what should NOT have happened.
        db.table.return_value.update.assert_not_called()


class GetQuoteTenantIdTests(unittest.TestCase):
    def test_returns_tenant_id_when_found(self):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data={"tenant_id": "tenant-1"}
        )
        self.assertEqual(get_quote_tenant_id("quote-1", db=db), "tenant-1")

    def test_returns_none_when_not_found(self):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)
        self.assertIsNone(get_quote_tenant_id("quote-1", db=db))


class ConfirmQuotePaymentTests(unittest.TestCase):
    def _claiming_db(self, items, tenant_id="tenant-1", lead_id="lead-1"):
        db = MagicMock()
        db.table.return_value.update.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(
            data=[{"tenant_id": tenant_id, "lead_id": lead_id, "items": items, "payment_link": "https://rzp.io/abc"}]
        )
        return db

    @patch("app.services.catalog_stock.decrement_stock")
    def test_deducts_stock_for_each_line_item_with_a_catalog_item_id(self, mock_decrement):
        mock_decrement.return_value = True
        db = self._claiming_db([
            {"catalog_item_id": "item-1", "name": "DSLR Bag", "price_paise": 320000, "qty": 2},
            {"catalog_item_id": None, "name": "Custom framing", "price_paise": 50000, "qty": 1},
        ])

        result = confirm_quote_payment("quote-1", "pay_abc", db=db)

        self.assertEqual(result, {"tenant_id": "tenant-1", "lead_id": "lead-1", "payment_link": "https://rzp.io/abc"})
        mock_decrement.assert_called_once_with("tenant-1", "item-1", 2, db=db)

    def test_returns_none_when_already_paid_or_unknown(self):
        """The .neq('status', 'paid') filter matching zero rows is the race-
        safety guard itself, not a side effect -- this is what stops two
        concurrent Razorpay retries from both deducting stock and sending a
        receipt for the same payment."""
        db = MagicMock()
        db.table.return_value.update.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=[])

        result = confirm_quote_payment("quote-1", "pay_abc", db=db)

        self.assertIsNone(result)

    @patch("app.services.catalog_stock.decrement_stock")
    def test_stock_deduction_failure_does_not_fail_the_confirmation(self, mock_decrement):
        mock_decrement.side_effect = Exception("db unreachable")
        db = self._claiming_db([{"catalog_item_id": "item-1", "name": "DSLR Bag", "price_paise": 320000, "qty": 1}])

        result = confirm_quote_payment("quote-1", "pay_abc", db=db)

        self.assertIsNotNone(result)


class GenerateReplyWiringTests(unittest.TestCase):
    """Static check, same technique as test_catalog.py's stock-blocking
    test: no existing test drives generate_reply's tool-call loop end to
    end, so this confirms the send_quote branch is actually wired in rather
    than trusting the edit was applied correctly."""

    def test_generate_reply_dispatches_send_quote_tool_calls(self):
        import inspect
        from app.services import ai_reply

        source = inspect.getsource(ai_reply.generate_reply)
        self.assertIn('tool_name == "send_quote"', source)
        self.assertIn("create_quote", source)


if __name__ == "__main__":
    unittest.main()
