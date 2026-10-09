"""Tests for the new deals list filtering and summary endpoints.
Tests cover: tenant isolation, stage filtering, source/payment_method lists,
date windows, numeric ranges, products, attention criteria, sorting, pagination,
and summary aggregation."""
import pytest
from datetime import datetime, timezone, timedelta
from app.routes import deals
from tests.fake_supabase import FakeSupabase


@pytest.fixture
def db_with_deals():
    """Seed ~6 deals for tenant "t1" with inline leads and deal_items, plus one for "t2"."""
    db = FakeSupabase()

    # Deal 1: quoted, whatsapp, 5000 paise, 5 days old
    created_5d_ago = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    db.add("deals", id="d1", tenant_id="t1", deal_number=1, stage="quoted", source="whatsapp",
           total_paise=5000, created_at=created_5d_ago, payment_method="razorpay",
           lead_id="lead1", leads={"id": "lead1", "name": "Alice", "phone": "9111"},
           deal_items=[{"id": "di1", "name": "Widget A", "qty": 5}])

    # Deal 2: awaiting_payment, form, 100000 paise, 2 days old
    created_2d_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    db.add("deals", id="d2", tenant_id="t1", deal_number=2, stage="awaiting_payment",
           source="form", total_paise=100000, created_at=created_2d_ago, intake_session_id="s1",
           payment_method="razorpay", link_expires_at=(datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
           lead_id="lead2", leads={"id": "lead2", "name": "Bob", "phone": "9222"},
           deal_items=[{"id": "di2", "name": "Widget B", "qty": 2}])

    # Deal 3: awaiting_payment, call, 4900 paise, 4 days old (unpaid_3d candidate)
    created_4d_ago = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
    db.add("deals", id="d3", tenant_id="t1", deal_number=3, stage="awaiting_payment",
           source="call", total_paise=4900, created_at=created_4d_ago, payment_method="upi",
           lead_id="lead1", leads={"id": "lead1", "name": "Alice", "phone": "9111"},
           deal_items=[{"id": "di3", "name": "Widget C", "qty": 1}])

    # Deal 4: won, walk_in, 50000 paise, 1 day old
    created_1d_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    db.add("deals", id="d4", tenant_id="t1", deal_number=4, stage="won", source="walk_in",
           total_paise=50000, created_at=created_1d_ago, payment_method="cash",
           won_at=created_1d_ago, lead_id="lead3", leads={"id": "lead3", "name": "Charlie", "phone": "9333"},
           deal_items=[{"id": "di4", "name": "Widget D", "qty": 10}])

    # Deal 5: lost, manual, 30000 paise, today
    db.add("deals", id="d5", tenant_id="t1", deal_number=5, stage="lost", source="manual",
           total_paise=30000, created_at=datetime.now(timezone.utc).isoformat(), payment_method="other",
           lost_at=datetime.now(timezone.utc).isoformat(), lead_id="lead4",
           leads={"id": "lead4", "name": "Diana", "phone": "9444"},
           deal_items=[{"id": "di5", "name": "Widget E", "qty": 3}])

    # Deal 6: awaiting_payment, form, 200000 paise, today (with refund intake session)
    db.add("deals", id="d6", tenant_id="t1", deal_number=6, stage="awaiting_payment",
           source="form", total_paise=200000, created_at=datetime.now(timezone.utc).isoformat(),
           payment_method="razorpay", intake_session_id="s2", link_expires_at=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
           lead_id="lead5", leads={"id": "lead5", "name": "Eve", "phone": "9555"},
           deal_items=[{"id": "di6", "name": "Widget F", "qty": 20}])

    # Tenant t2 deal (should never appear)
    db.add("deals", id="d7", tenant_id="t2", deal_number=1, stage="quoted", source="manual",
           total_paise=1000, lead_id="t2lead1",
           leads={"id": "t2lead1", "name": "Other", "phone": "0000"},
           deal_items=[{"id": "di7", "name": "Other Widget", "qty": 1}])

       # Add deal_items to the deal_items table (for product filtering)
    db.add("deal_items", id="di1", deal_id="d1", tenant_id="t1", name="Widget A", qty=5)
    db.add("deal_items", id="di2", deal_id="d2", tenant_id="t1", name="Widget B", qty=2)
    db.add("deal_items", id="di3", deal_id="d3", tenant_id="t1", name="Widget C", qty=1)
    db.add("deal_items", id="di4", deal_id="d4", tenant_id="t1", name="Widget D", qty=10)
    db.add("deal_items", id="di5", deal_id="d5", tenant_id="t1", name="Widget E", qty=3)
    db.add("deal_items", id="di6", deal_id="d6", tenant_id="t1", name="Widget F", qty=20)
    db.add("deal_items", id="di7", deal_id="d7", tenant_id="t2", name="Other Widget", qty=1)
    
     # Intake sessions for refund testing
    db.add("intake_sessions", id="s1", tenant_id="t1", refund_needed=False)
    db.add("intake_sessions", id="s2", tenant_id="t1", refund_needed=True)

    return db


def test_tenant_isolation(db_with_deals, monkeypatch):
    """Only t1 deals appear; t2 deal is filtered out."""
    monkeypatch.setattr(deals, "get_supabase", lambda: db_with_deals)

    result = deals.list_deals(ctx={"tenant_id": "t1"}, stage=None, source=None, q=None,
                              created_from=None, created_to=None, min_rupees=None, max_rupees=None,
                              payment_method=None, product=None, attention=None,
                              sort="created_at", dir="desc", page=1, limit=50)

    deal_ids = {d["id"] for d in result["data"]}
    assert "d7" not in deal_ids
    assert result["total"] == 6


def test_stage_filter(db_with_deals, monkeypatch):
    """stage='awaiting_payment' returns only awaiting_payment deals."""
    monkeypatch.setattr(deals, "get_supabase", lambda: db_with_deals)

    result = deals.list_deals(ctx={"tenant_id": "t1"}, stage="awaiting_payment", source=None, q=None,
                              created_from=None, created_to=None, min_rupees=None, max_rupees=None,
                              payment_method=None, product=None, attention=None,
                              sort="created_at", dir="desc", page=1, limit=50)

    assert all(d["stage"] == "awaiting_payment" for d in result["data"])
    assert result["total"] == 3  # d2, d3, d6


def test_source_list_filter(db_with_deals, monkeypatch):
    """source='form,call' returns form and call deals."""
    monkeypatch.setattr(deals, "get_supabase", lambda: db_with_deals)

    result = deals.list_deals(ctx={"tenant_id": "t1"}, stage=None, source="form,call", q=None,
                              created_from=None, created_to=None, min_rupees=None, max_rupees=None,
                              payment_method=None, product=None, attention=None,
                              sort="created_at", dir="desc", page=1, limit=50)

    sources = {d["source"] for d in result["data"]}
    assert sources == {"form", "call"}
    assert result["total"] == 3  # d2, d3


def test_created_date_window(db_with_deals, monkeypatch):
    """created_from/created_to filters by date range (IST)."""
    monkeypatch.setattr(deals, "get_supabase", lambda: db_with_deals)

    today = datetime.now(timezone.utc).date()
    two_days_ago = (today - timedelta(days=2)).isoformat()

    # Only deals created in the last 2 days
    result = deals.list_deals(ctx={"tenant_id": "t1"}, stage=None, source=None, q=None,
                              created_from=two_days_ago, created_to=today.isoformat(),
                              min_rupees=None, max_rupees=None, payment_method=None,
                              product=None, attention=None, sort="created_at", dir="desc",
                              page=1, limit=50)

    # Should include d2 (2d old), d4 (1d old), d5 (today), d6 (today)
    assert result["total"] == 4


def test_min_max_rupees(db_with_deals, monkeypatch):
    """min_rupees and max_rupees filter by total_paise (converted from rupees)."""
    monkeypatch.setattr(deals, "get_supabase", lambda: db_with_deals)

    # 49 rupees = 4900 paise, 200 rupees = 20000 paise
    # Should get d3 (4900), d1 (5000)
    result = deals.list_deals(ctx={"tenant_id": "t1"}, stage=None, source=None, q=None,
                              created_from=None, created_to=None, min_rupees=49, max_rupees=100,
                              payment_method=None, product=None, attention=None,
                              sort="created_at", dir="desc", page=1, limit=50)

    amounts = sorted([d["total_paise"] for d in result["data"]])
    assert amounts == [4900, 5000]  # numeric comparison, not string


def test_payment_method_filter(db_with_deals, monkeypatch):
    """payment_method filters by comma-separated list."""
    monkeypatch.setattr(deals, "get_supabase", lambda: db_with_deals)

    result = deals.list_deals(ctx={"tenant_id": "t1"}, stage=None, source=None, q=None,
                              created_from=None, created_to=None, min_rupees=None, max_rupees=None,
                              payment_method="razorpay,cash", product=None, attention=None,
                              sort="created_at", dir="desc", page=1, limit=50)

    methods = {d["payment_method"] for d in result["data"]}
    assert methods == {"razorpay", "cash"}


def test_product_filter(db_with_deals, monkeypatch):
    """product filters by deal_items.name."""
    monkeypatch.setattr(deals, "get_supabase", lambda: db_with_deals)

    result = deals.list_deals(ctx={"tenant_id": "t1"}, stage=None, source=None, q=None,
                              created_from=None, created_to=None, min_rupees=None, max_rupees=None,
                              payment_method=None, product="Widget A,Widget D", attention=None,
                              sort="created_at", dir="desc", page=1, limit=50)

    # d1 has Widget A, d4 has Widget D
    assert result["total"] == 2
    deal_ids = {d["id"] for d in result["data"]}
    assert deal_ids == {"d1", "d4"}


def test_attention_unpaid_3d(db_with_deals, monkeypatch):
    """attention=unpaid_3d returns awaiting_payment deals older than 3 days."""
    monkeypatch.setattr(deals, "get_supabase", lambda: db_with_deals)

    result = deals.list_deals(ctx={"tenant_id": "t1"}, stage=None, source=None, q=None,
                              created_from=None, created_to=None, min_rupees=None, max_rupees=None,
                              payment_method=None, product=None, attention="unpaid_3d",
                              sort="created_at", dir="desc", page=1, limit=50)

    # d3 is 4 days old and awaiting_payment; d2 is 2 days old so excluded
    assert result["total"] == 1
    assert result["data"][0]["id"] == "d3"


def test_attention_refund(db_with_deals, monkeypatch):
    """attention=refund returns deals with refund_needed=true in intake_sessions."""
    monkeypatch.setattr(deals, "get_supabase", lambda: db_with_deals)

    result = deals.list_deals(ctx={"tenant_id": "t1"}, stage=None, source=None, q=None,
                              created_from=None, created_to=None, min_rupees=None, max_rupees=None,
                              payment_method=None, product=None, attention="refund",
                              sort="created_at", dir="desc", page=1, limit=50)

    # d6 has refund_needed=true (s2), d2 has refund_needed=false
    assert result["total"] == 1
    assert result["data"][0]["id"] == "d6"


def test_unknown_source_400(db_with_deals, monkeypatch):
    """Unknown source value raises HTTPException 400."""
    monkeypatch.setattr(deals, "get_supabase", lambda: db_with_deals)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        deals.list_deals(ctx={"tenant_id": "t1"}, stage=None, source="invalid_source", q=None,
                         created_from=None, created_to=None, min_rupees=None, max_rupees=None,
                         payment_method=None, product=None, attention=None,
                         sort="created_at", dir="desc", page=1, limit=50)
    assert exc_info.value.status_code == 400


def test_sort_total_paise_asc(db_with_deals, monkeypatch):
    """sort='total_paise' dir='asc' orders by amount ascending."""
    monkeypatch.setattr(deals, "get_supabase", lambda: db_with_deals)

    result = deals.list_deals(ctx={"tenant_id": "t1"}, stage=None, source=None, q=None,
                              created_from=None, created_to=None, min_rupees=None, max_rupees=None,
                              payment_method=None, product=None, attention=None,
                              sort="total_paise", dir="asc", page=1, limit=50)

    amounts = [d["total_paise"] for d in result["data"]]
    assert amounts == sorted(amounts)


def test_pagination(db_with_deals, monkeypatch):
    """page=2 limit=2 returns the second page (items 3-4)."""
    monkeypatch.setattr(deals, "get_supabase", lambda: db_with_deals)

    result = deals.list_deals(ctx={"tenant_id": "t1"}, stage=None, source=None, q=None,
                              created_from=None, created_to=None, min_rupees=None, max_rupees=None,
                              payment_method=None, product=None, attention=None,
                              sort="created_at", dir="desc", page=2, limit=2)

    assert result["page"] == 2
    assert result["limit"] == 2
    assert result["total"] == 6
    assert len(result["data"]) == 2


def test_summary_stage_totals(db_with_deals, monkeypatch):
    """summary returns per-stage count and total_paise."""
    monkeypatch.setattr(deals, "get_supabase", lambda: db_with_deals)

    result = deals.get_summary(ctx={"tenant_id": "t1"}, source=None, q=None,
                               created_from=None, created_to=None, min_rupees=None, max_rupees=None,
                               payment_method=None, product=None, attention=None)

    # quoted: d1 (5000)
    # awaiting_payment: d2 (100000), d3 (4900), d6 (200000) = 304900
    # won: d4 (50000)
    # lost: d5 (30000)
    assert result["stages"]["quoted"]["count"] == 1
    assert result["stages"]["quoted"]["total_paise"] == 5000
    assert result["stages"]["awaiting_payment"]["count"] == 3
    assert result["stages"]["awaiting_payment"]["total_paise"] == 304900
    assert result["stages"]["won"]["count"] == 1
    assert result["stages"]["lost"]["count"] == 1


def test_summary_unpaid_3d(db_with_deals, monkeypatch):
    """summary.unpaid_3d counts awaiting_payment deals older than 3 days."""
    monkeypatch.setattr(deals, "get_supabase", lambda: db_with_deals)

    result = deals.get_summary(ctx={"tenant_id": "t1"}, source=None, q=None,
                               created_from=None, created_to=None, min_rupees=None, max_rupees=None,
                               payment_method=None, product=None, attention=None)

    # d3 is 4 days old, awaiting_payment
    assert result["unpaid_3d"]["count"] == 1
    assert result["unpaid_3d"]["total_paise"] == 4900


def test_summary_products_list(db_with_deals, monkeypatch):
    """summary.products returns distinct deal_items.name sorted, ignoring filters."""
    monkeypatch.setattr(deals, "get_supabase", lambda: db_with_deals)

    # Filter to just one deal
    result = deals.get_summary(ctx={"tenant_id": "t1"}, source="walk_in", q=None,
                               created_from=None, created_to=None, min_rupees=None, max_rupees=None,
                               payment_method=None, product=None, attention=None)

    # Should still list all products for the tenant (ignores filters)
    expected = ["Widget A", "Widget B", "Widget C", "Widget D", "Widget E", "Widget F"]
    assert sorted(result["products"]) == sorted(expected)


def test_summary_empty_when_no_matches(db_with_deals, monkeypatch):
    """summary returns empty stages and unpaid_3d when filter matches nothing."""
    monkeypatch.setattr(deals, "get_supabase", lambda: db_with_deals)

    # Filter that matches nothing
    result = deals.get_summary(ctx={"tenant_id": "t1"}, source="indiamart", q=None,
                               created_from=None, created_to=None, min_rupees=None, max_rupees=None,
                               payment_method=None, product=None, attention=None)

    assert result["stages"]["quoted"]["count"] == 0
    assert result["stages"]["awaiting_payment"]["count"] == 0
    assert result["unpaid_3d"]["count"] == 0
    # But products should still be there
    assert len(result["products"]) > 0


def test_equal_values_page_through_without_repeats(monkeypatch):
    """Many deals share one amount (₹1 form deals): paging by value must still show each exactly once."""
    db = FakeSupabase()
    for i, deal_id in enumerate(["d3", "d1", "d2"]):
        db.add("deals", id=deal_id, tenant_id="t1", deal_number=i + 1, stage="won", source="form",
               total_paise=100, created_at="2026-10-01T00:00:00+00:00", lead_id="l1",
               leads={"name": "Vivek", "phone": "9"}, deal_items=[])
    monkeypatch.setattr(deals, "get_supabase", lambda: db)

    def page(n):
        return deals.list_deals(ctx={"tenant_id": "t1"}, stage=None, source=None, q=None,
                                created_from=None, created_to=None, min_rupees=None, max_rupees=None,
                                payment_method=None, product=None, attention=None,
                                sort="total_paise", dir="asc", page=n, limit=1)["data"][0]["id"]

    assert [page(1), page(2), page(3)] == ["d1", "d2", "d3"]
