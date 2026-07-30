"""Tests for the one-lead-per-Meta-ad attribution model."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.meta_ctwa_attribution import (
    build_prefilled_message,
    find_creative_for_message,
    parse_tracking_code,
    record_lead_ad_attribution,
)


class Result:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, db, table, operation="select", payload=None):
        self.db = db
        self.table = table
        self.operation = operation
        self.payload = payload
        self.filters = []
        self.limit_count = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = payload
        return self

    def execute(self):
        rows = self.db.rows.setdefault(self.table, [])
        matched = [
            row for row in rows
            if all(row.get(column) == value for column, value in self.filters)
        ]
        if self.limit_count is not None:
            matched = matched[:self.limit_count]

        if self.operation == "insert":
            key = (
                self.payload.get("tenant_id"),
                self.payload.get("lead_id"),
                self.payload.get("meta_ad_id"),
            )
            for row in rows:
                existing_key = (
                    row.get("tenant_id"),
                    row.get("lead_id"),
                    row.get("meta_ad_id"),
                )
                if key == existing_key:
                    raise ValueError("duplicate attribution")
            rows.append(dict(self.payload))
            return Result([dict(self.payload)])

        if self.operation == "update":
            for row in matched:
                row.update(self.payload)
            return Result([dict(row) for row in matched])

        return Result([dict(row) for row in matched])


class FakeDB:
    def __init__(self, rows=None):
        self.rows = rows or {}

    def table(self, name):
        return Query(self, name)

    def insert(self, *_args, **_kwargs):  # pragma: no cover - never called directly
        raise AssertionError


def _insert_query(db, table, payload):
    return Query(db, table, operation="insert", payload=payload)


# Match Supabase's db.table(...).insert(...) chain.
Query.insert = lambda self, payload: _insert_query(self.db, self.table, payload)


def test_prefilled_message_round_trips():
    message = build_prefilled_message("Hi, tell me more", "7k2q9m")
    assert message == "Hi, tell me more\nRef: [AIRA:7K2Q9M]"
    assert parse_tracking_code(message) == "7K2Q9M"


def test_existing_code_is_replaced_instead_of_duplicated():
    message = build_prefilled_message(
        "Hello [AIRA:AAAAAA]",
        "BBBBBB",
    )
    assert message.count("[AIRA:") == 1
    assert parse_tracking_code(message) == "BBBBBB"


def test_meta_referral_wins_when_message_contains_another_ads_code():
    db = FakeDB({
        "ad_creatives": [
            {
                "id": "creative-a",
                "tenant_id": "tenant-1",
                "meta_ad_account_id": "act-1",
                "is_click_to_whatsapp": True,
                "meta_ad_id": "ad-a",
                "campaign_id": "campaign-a",
                "prefilled_message_code": "AAAAAA",
            },
            {
                "id": "creative-b",
                "tenant_id": "tenant-1",
                "meta_ad_account_id": "act-1",
                "is_click_to_whatsapp": True,
                "meta_ad_id": "ad-b",
                "campaign_id": "campaign-b",
                "prefilled_message_code": "BBBBBB",
            },
        ],
    })

    creative, method = find_creative_for_message(
        db,
        tenant_id="tenant-1",
        meta_ad_account_id="act-1",
        referral_ad_id="ad-a",
        body="Hi [AIRA:BBBBBB]",
    )
    assert creative["id"] == "creative-a"
    assert method == "meta_ad_id"


def test_prefilled_code_is_used_when_meta_referral_is_missing():
    db = FakeDB({
        "ad_creatives": [{
            "id": "creative-b",
            "tenant_id": "tenant-1",
            "meta_ad_account_id": "act-1",
            "is_click_to_whatsapp": True,
            "meta_ad_id": "ad-b",
            "campaign_id": "campaign-b",
            "prefilled_message_code": "BBBBBB",
        }],
    })

    creative, method = find_creative_for_message(
        db,
        tenant_id="tenant-1",
        meta_ad_account_id="act-1",
        referral_ad_id=None,
        body="Hi [AIRA:BBBBBB]",
    )
    assert creative["meta_ad_id"] == "ad-b"
    assert method == "prefilled_code"


def test_missing_referral_and_code_stays_unattributed():
    creative, method = find_creative_for_message(
        FakeDB({"ad_creatives": []}),
        tenant_id="tenant-1",
        meta_ad_account_id="act-1",
        referral_ad_id=None,
        body="Hi",
    )
    assert creative is None
    assert method is None


def test_same_lead_same_ad_counts_once_but_second_ad_is_new():
    db = FakeDB({"lead_meta_ad_attributions": []})
    common = {
        "db": db,
        "tenant_id": "tenant-1",
        "lead_id": "lead-1",
        "meta_ad_account_id": "act-1",
        "ad_creative_id": "creative-a",
        "attribution_method": "meta_ad_id",
    }

    assert record_lead_ad_attribution(meta_ad_id="ad-a", **common) is True
    assert record_lead_ad_attribution(meta_ad_id="ad-a", **common) is False
    assert record_lead_ad_attribution(
        meta_ad_id="ad-b",
        **{**common, "ad_creative_id": "creative-b"},
    ) is True

    rows = db.rows["lead_meta_ad_attributions"]
    assert len(rows) == 2
    assert {row["meta_ad_id"] for row in rows} == {"ad-a", "ad-b"}


def test_migration_enforces_tenant_scoped_lead_ad_uniqueness_and_rls():
    migration = (
        Path(__file__).resolve().parents[1]
        / "supabase"
        / "migrations"
        / "155_lead_meta_ad_attributions.sql"
    ).read_text(encoding="utf-8")
    assert "PRIMARY KEY (tenant_id, lead_id, meta_ad_id)" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "public.is_tenant_member(tenant_id)" in migration
