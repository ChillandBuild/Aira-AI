"""The money maths behind the auditor's sales register and the Insights tab:
IST month boundaries, the optional GST split, refunds as negative rows."""
import io
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook

from app.services import deals_reports
from app.services.deals_reports import _tax_split, month_bounds


def test_month_bounds_are_ist_calendar_month_in_utc():
    start, end = month_bounds("2026-09")
    # 1 Sep 00:00 IST is 31 Aug 18:30 UTC
    assert start.startswith("2026-08-31T18:30:00")
    assert end.startswith("2026-09-30T18:30:00")


def test_month_bounds_december_rolls_into_next_year():
    _, end = month_bounds("2026-12")
    assert end.startswith("2026-12-31T18:30:00")


@pytest.mark.parametrize("bad", ["2026-13", "26-09", "", "2026-9", "abc"])
def test_month_bounds_rejects_bad_input(bad):
    with pytest.raises(HTTPException) as exc:
        month_bounds(bad)
    assert exc.value.status_code == 400


def test_tax_split_price_includes_gst():
    # ₹499.00 at 18% inclusive -> taxable 422.88, tax 76.12
    split = _tax_split(49900, 18, prices_include_gst=True)
    assert split["taxable"] == 42288
    assert split["tax"] == 7612
    assert split["cgst"] + split["sgst"] == split["tax"]
    assert split["gross"] == 49900


def test_tax_split_price_excludes_gst_adds_on_top():
    split = _tax_split(49900, 18, prices_include_gst=False)
    assert split["taxable"] == 49900
    assert split["tax"] == 8982
    assert split["gross"] == 58882


def test_tax_split_odd_paisa_goes_to_cgst():
    split = _tax_split(10001, 5, prices_include_gst=False)  # tax 500 -> even; use one that is odd
    odd = _tax_split(10100, 5, prices_include_gst=False)    # tax 505
    assert odd["cgst"] == 253 and odd["sgst"] == 252
    assert split["cgst"] + split["sgst"] == split["tax"]


def test_tax_split_without_rate_is_untaxed():
    assert _tax_split(1000, None, True) == {"taxable": 1000, "tax": 0, "cgst": 0, "sgst": 0, "gross": 1000}


def _deal(number, when, items, source="walk_in", method="cash"):
    return {
        "deal_number": number, "won_at": when, "lost_at": when, "source": source, "payment_method": method,
        "razorpay_payment_id": None, "total_paise": sum(i["line_total_paise"] for i in items),
        "leads": {"name": "Ravi", "phone": "+919800000001"}, "deal_items": items,
    }


def _line(name, qty, unit, rate=None):
    return {"name": name, "qty": qty, "unit_price_paise": unit, "gst_rate": rate, "line_total_paise": qty * unit}


PROFILE = {
    "legal_name": "Kumar Mobiles", "address": "12 Anna Salai", "city": "Chennai", "state": "Tamil Nadu",
    "pincode": "600002", "gstin": "", "email": "", "phone": "9800000000", "prices_include_gst": True,
}


def _register(won, refunds, profile, fmt="xlsx"):
    with patch.object(deals_reports, "get_business_details", return_value=profile), \
         patch.object(deals_reports, "_won_in_month", return_value=won), \
         patch.object(deals_reports, "_refunded_in_month", return_value=refunds):
        return deals_reports.sales_register("tenant", "2026-09", fmt, db=object())


def test_register_header_is_the_clients_business_not_aira():
    content, media_type, filename = _register([_deal(41, "2026-09-03T05:00:00+00:00", [_line("Earbuds", 2, 129900)])], [], PROFILE)
    ws = load_workbook(io.BytesIO(content)).active
    assert ws["A1"].value == "Kumar Mobiles"
    assert "Aira" not in " ".join(str(c.value) for row in ws.iter_rows() for c in row if c.value)
    assert filename == "kumar-mobiles-sales-2026-09.xlsx"
    assert media_type.endswith("spreadsheetml.sheet")


def test_register_total_nets_refunds_as_negative_rows():
    won = [_deal(41, "2026-09-03T05:00:00+00:00", [_line("Earbuds", 2, 129900)])]
    refunds = [_deal(38, "2026-09-10T05:00:00+00:00", [_line("Charger", 1, 49900)])]
    content, _, _ = _register(won, refunds, PROFILE, fmt="csv")
    text = content.decode("utf-8-sig")
    assert "D-0038 (refund)" in text
    assert "TOTAL,2099.0" in text  # 2598 - 499


def test_register_gst_columns_only_with_gstin_and_rates():
    won = [_deal(41, "2026-09-03T05:00:00+00:00", [_line("Earbuds", 1, 49900, rate=18)])]
    plain, _, _ = _register(won, [], PROFILE, fmt="csv")
    assert "CGST" not in plain.decode("utf-8-sig")
    with_gst, _, _ = _register(won, [], {**PROFILE, "gstin": "33ABCDE1234F1Z5"}, fmt="csv")
    text = with_gst.decode("utf-8-sig")
    assert "GSTIN: 33ABCDE1234F1Z5" in text
    assert "Taxable value (₹),GST %,CGST (₹),SGST (₹),IGST (₹),Amount (₹)" in text
    assert "422.88" in text


def test_register_neutralises_formula_injection_in_customer_names():
    deal = _deal(41, "2026-09-03T05:00:00+00:00", [_line("=cmd()", 1, 100)])
    deal["leads"] = {"name": "=HYPERLINK(evil)", "phone": "+91"}
    content, _, _ = _register([deal], [], PROFILE, fmt="csv")
    text = content.decode("utf-8-sig")
    assert "'=HYPERLINK(evil)" in text and "'=cmd()" in text
