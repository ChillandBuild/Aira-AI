"""Deal lifecycle rules (services/deals.py) against a small in-memory fake of
the Supabase client: stock moves on won only and exactly once, a refund puts
it back, prices come from the catalog, the AI keeps one open quote per lead,
and the intake form mirrors onto one deal per session."""
import itertools
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import deals

TENANT = "t-1"


class _Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.op, self.payload = db, table, [], "select", None
        self._single, self._limit = False, None

    def select(self, *_a, **_k):
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, k, v):
        self.filters.append(lambda r: r.get(k) == v)
        return self

    def neq(self, k, v):
        self.filters.append(lambda r: r.get(k) != v)
        return self

    def in_(self, k, vs):
        self.filters.append(lambda r: r.get(k) in vs)
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def maybe_single(self):
        self._single = True
        return self

    def execute(self):
        rows = self.db.tables.setdefault(self.table, [])
        match = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "insert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            new = [{"id": str(uuid.uuid4()), "created_at": "2026-09-25T00:00:00+00:00", **i} for i in items]
            rows.extend(new)
            return SimpleNamespace(data=new)
        if self.op == "update":
            for r in match:
                r.update(self.payload)
            return SimpleNamespace(data=[dict(r) for r in match])
        if self.op == "delete":
            self.db.tables[self.table] = [r for r in rows if r not in match]
            return SimpleNamespace(data=match)
        if self._limit:
            match = match[: self._limit]
        if self._single:
            return SimpleNamespace(data=dict(match[0]) if match else None)
        return SimpleNamespace(data=[dict(r) for r in match])


class FakeDb:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self.counter = itertools.count(1)
        self.movements: list[tuple] = []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        if name == "next_deal_number":
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=next(self.counter)))
        assert name == "apply_stock_movement"
        item = next(i for i in self.tables["catalog_items"] if i["id"] == params["p_item_id"])
        current = item.get("stock_quantity")
        if current is None:
            row = {"ok": True, "tracked": False, "quantity_after": None}
        elif current + params["p_delta"] < 0:
            row = {"ok": False, "tracked": True, "quantity_after": current}
        else:
            item["stock_quantity"] = current + params["p_delta"]
            self.movements.append((params["p_item_id"], params["p_delta"], params["p_reason"]))
            row = {"ok": True, "tracked": True, "quantity_after": item["stock_quantity"]}
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=[row]))


@pytest.fixture
def db():
    fake = FakeDb()
    fake.tables["catalog_items"] = [
        {"id": "earbuds", "tenant_id": TENANT, "name": "Earbuds", "price_paise": 129900, "gst_rate": 18, "stock_quantity": 3},
        {"id": "service", "tenant_id": TENANT, "name": "Setup", "price_paise": 50000, "gst_rate": None, "stock_quantity": None},
    ]
    fake.tables["leads"] = [{"id": "lead-1", "tenant_id": TENANT, "name": "Ravi", "phone": "+919800000001"}]
    with patch("app.services.business_details.prices_include_gst", return_value=True):
        yield fake


@pytest.mark.asyncio
async def test_walk_in_won_sale_snapshots_catalog_price_and_deducts_stock(db):
    result = await deals.create_deal(TENANT, "lead-1", [{"catalog_item_id": "earbuds", "qty": 2}], "walk_in", "won",
                                     payment_method="cash", db=db)
    assert result["deal"]["total_paise"] == 259800
    assert result["deal"]["deal_number"] == 1
    assert result["items"][0]["unit_price_paise"] == 129900
    assert db.tables["catalog_items"][0]["stock_quantity"] == 1
    assert db.movements == [("earbuds", -2, "sale")]
    assert result["stock_warnings"] == []


@pytest.mark.asyncio
async def test_overselling_still_records_the_sale_but_warns(db):
    result = await deals.create_deal(TENANT, "lead-1", [{"catalog_item_id": "earbuds", "qty": 5}], "walk_in", "won",
                                     payment_method="upi", db=db)
    assert result["deal"]["stage"] == "won"
    assert result["stock_warnings"] == [{"catalog_item_id": "earbuds", "name": "Earbuds", "available": 3}]
    assert db.tables["catalog_items"][0]["stock_quantity"] == 3


@pytest.mark.asyncio
async def test_quoted_deal_never_touches_stock(db):
    await deals.create_deal(TENANT, "lead-1", [{"catalog_item_id": "earbuds", "qty": 1}], "manual", "quoted", db=db)
    assert db.movements == []


@pytest.mark.asyncio
async def test_line_without_any_price_is_rejected(db):
    with pytest.raises(deals.DealError):
        await deals.create_deal(TENANT, "lead-1", [{"name": "Mystery box", "qty": 1}], "manual", "won", db=db)


@pytest.mark.asyncio
async def test_other_tenants_product_is_not_found(db):
    db.tables["catalog_items"].append({"id": "theirs", "tenant_id": "t-2", "name": "X", "price_paise": 1})
    with pytest.raises(deals.DealError):
        await deals.create_deal(TENANT, "lead-1", [{"catalog_item_id": "theirs", "qty": 1}], "manual", "won", db=db)


@pytest.mark.asyncio
async def test_mark_won_twice_deducts_stock_once(db):
    created = await deals.create_deal(TENANT, "lead-1", [{"catalog_item_id": "earbuds", "qty": 1}], "manual", "quoted", db=db)
    deal_id = created["deal"]["id"]
    first = deals.mark_won(TENANT, deal_id, payment_method="razorpay", razorpay_payment_id="pay_1", db=db)
    second = deals.mark_won(TENANT, deal_id, payment_method="razorpay", razorpay_payment_id="pay_1", db=db)
    assert first is not None and second is None
    assert db.movements == [("earbuds", -1, "sale")]


@pytest.mark.asyncio
async def test_refund_of_a_won_deal_returns_stock(db):
    created = await deals.create_deal(TENANT, "lead-1", [{"catalog_item_id": "earbuds", "qty": 2}], "walk_in", "won",
                                      payment_method="cash", db=db)
    lost = deals.mark_lost(TENANT, created["deal"]["id"], "Customer returned it", db=db)
    assert lost["deal"]["stage"] == "lost"
    assert db.tables["catalog_items"][0]["stock_quantity"] == 3
    assert db.movements[-1] == ("earbuds", 2, "return")


@pytest.mark.asyncio
async def test_prices_excluding_gst_add_tax_to_what_the_customer_pays(db):
    with patch("app.services.business_details.prices_include_gst", return_value=False):
        result = await deals.create_deal(TENANT, "lead-1", [{"catalog_item_id": "earbuds", "qty": 1}], "manual", "quoted", db=db)
    assert result["deal"]["total_paise"] == 129900 + round(129900 * 18 / 100)
    assert result["items"][0]["line_total_paise"] == 129900


@pytest.mark.asyncio
async def test_awaiting_payment_creates_link_with_deal_id_in_notes(db):
    fake_link = AsyncMock(return_value={"payment_link_url": "https://rzp.io/x", "razorpay_payment_link_id": "plink_1"})
    with patch("app.services.payment_razorpay.create_payment_link", fake_link), \
         patch("app.services.ai_reply.send_whatsapp", AsyncMock(side_effect=RuntimeError("outside 24h window"))):
        result = await deals.create_deal(TENANT, "lead-1", [{"catalog_item_id": "earbuds", "qty": 1}], "manual",
                                         "awaiting_payment", send_link=True, db=db)
    assert fake_link.await_args.kwargs["notes"] == {"deal_id": result["deal"]["id"]}
    assert result["payment_link"] == "https://rzp.io/x"
    assert result["message_sent"] is False  # link still returned so staff can share it
    assert db.tables["deals"][0]["stage"] == "awaiting_payment"


def test_ai_recommendations_keep_one_open_quote_per_lead(db):
    deals.upsert_quoted_deal(TENANT, "lead-1", {"catalog_item_id": "earbuds", "name": "Earbuds", "qty": 1}, db=db)
    deals.upsert_quoted_deal(TENANT, "lead-1", {"catalog_item_id": "service", "name": "Setup", "qty": 1}, db=db)
    assert len(db.tables["deals"]) == 1
    assert [i["name"] for i in db.tables["deal_items"]] == ["Setup"]
    assert db.tables["deals"][0]["total_paise"] == 50000


def test_intake_session_mirrors_onto_one_deal_through_its_statuses(db):
    session = {
        "id": "s-1", "tenant_id": TENANT, "lead_id": "lead-1", "status": "awaiting_payment",
        "package_name": "Horoscope", "package_amount_paise": 150000,
        "selected_addons": [{"name": "Remedy", "amount_paise": 50000}], "total_amount_paise": 200000,
        "payment_link": "https://rzp.io/s",
    }
    deals.sync_intake_session(session, db=db)
    deals.sync_intake_session({**session, "status": "paid", "razorpay_payment_id": "pay_9"}, db=db)
    assert len(db.tables["deals"]) == 1
    deal = db.tables["deals"][0]
    assert deal["source"] == "form" and deal["stage"] == "won" and deal["total_paise"] == 200000
    assert sorted(i["name"] for i in db.tables["deal_items"]) == ["Horoscope", "Remedy"]


def test_cancelled_intake_session_marks_its_deal_lost(db):
    session = {"id": "s-2", "tenant_id": TENANT, "lead_id": "lead-1", "status": "awaiting_payment",
               "package_name": "Horoscope", "package_amount_paise": 150000}
    deals.sync_intake_session(session, db=db)
    deals.sync_intake_session({**session, "status": "cancelled"}, db=db)
    assert db.tables["deals"][0]["stage"] == "lost"


def test_sync_never_raises_on_bad_input():
    deals.sync_intake_session({"status": "paid"}, db=FakeDb())
