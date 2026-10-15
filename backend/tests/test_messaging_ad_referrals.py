"""Instagram / Messenger chats from Meta ads get credited to the ad.

Meta's documented referral for these channels is
{source: "ADS", type: "OPEN_THREAD", ad_id, ads_context_data}; the handlers used
to check WhatsApp's {source_type: "ad", source_id} and so never matched (live data
on 2026-10-16: 0 of 68 Instagram and 0 of 7 Messenger inbound messages were ever
flagged as ad-driven). Payloads below follow Meta's webhook reference examples.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, Request

from app.services.meta_ctwa_attribution import (
    attribute_chat_to_ad,
    parse_ad_referral,
    record_lead_ad_attribution,
)

AD_REFERRAL = {
    "ref": "REF-DATA",
    "ad_id": "120210000000001",
    "source": "ADS",
    "type": "OPEN_THREAD",
    "ads_context_data": {"ad_title": "Free consultation", "photo_url": "https://x/p.jpg"},
}


# ── parse_ad_referral ─────────────────────────────────────────────────────────

def test_reads_metas_instagram_and_messenger_ad_shape():
    assert parse_ad_referral(AD_REFERRAL) == "120210000000001"


def test_still_reads_the_whatsapp_shape():
    assert parse_ad_referral({"source_type": "ad", "source_id": "999"}) == "999"


@pytest.mark.parametrize("referral", [
    None,
    {},
    {"source": "SHORTLINK", "type": "OPEN_THREAD", "ref": "promo"},   # m.me link, not an ad
    {"source": "IGME-SOURCE-LINK", "type": "OPEN_THREAD"},           # ig.me link
    {"source": "ADS", "type": "OPEN_THREAD"},                        # ad shape without an id
    {"source_type": "post", "source_id": "1"},
])
def test_non_ad_referrals_are_ignored(referral):
    assert parse_ad_referral(referral) is None


# ── attribute_chat_to_ad ──────────────────────────────────────────────────────

class _Table:
    def __init__(self, store, name):
        self.store, self.name, self.filters, self.op, self.payload = store, name, {}, "select", None

    def select(self, *_a, **_k):
        self.op = "select"
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, *_a):
        return self

    def execute(self):
        rows = self.store.setdefault(self.name, [])
        matching = [r for r in rows if all(r.get(k) == v for k, v in self.filters.items())]
        if self.op == "insert":
            rows.append(dict(self.payload))
            return MagicMock(data=[self.payload])
        if self.op == "update":
            for r in matching:
                r.update(self.payload)
            return MagicMock(data=matching)
        return MagicMock(data=matching)


class _DB:
    def __init__(self, **tables):
        self.store = {k: list(v) for k, v in tables.items()}

    def table(self, name):
        return _Table(self.store, name)


def _attribute(db, referral=AD_REFERRAL, channel="instagram"):
    with patch("app.services.meta_ads_insights_sync.get_current_ads_account_id", return_value="act_1"), \
         patch("app.services.growth.get_or_create_campaign", return_value={"id": "placeholder-camp"}) as placeholder:
        ad_id = attribute_chat_to_ad(
            db, tenant_id="t1", lead_id="lead-1", referral=referral,
            channel=channel, platform=channel,
        )
    return ad_id, placeholder


def test_synced_ad_is_recorded_with_its_channel_and_campaign():
    db = _DB(
        ad_creatives=[{
            "id": "cr-1", "tenant_id": "t1", "meta_ad_account_id": "act_1",
            "meta_ad_id": "120210000000001", "campaign_id": "camp-1",
            # An Instagram-only ad: WhatsApp is not a destination.
            "is_click_to_whatsapp": False,
        }],
        leads=[{"id": "lead-1", "tenant_id": "t1", "ad_campaign_id": None}],
    )
    ad_id, placeholder = _attribute(db)

    assert ad_id == "120210000000001"
    [row] = db.store["lead_meta_ad_attributions"]
    assert row["channel"] == "instagram"
    assert row["ad_creative_id"] == "cr-1"
    assert row["attribution_method"] == "meta_ad_id"
    assert db.store["leads"][0]["ad_campaign_id"] == "camp-1"
    placeholder.assert_not_called()


def test_unsynced_ad_is_still_recorded_and_gets_a_placeholder_campaign():
    db = _DB(leads=[{"id": "lead-1", "tenant_id": "t1", "ad_campaign_id": None}])
    _, placeholder = _attribute(db, channel="messenger")

    [row] = db.store["lead_meta_ad_attributions"]
    assert row["meta_ad_id"] == "120210000000001"
    assert row["ad_creative_id"] is None
    assert row["channel"] == "messenger"
    assert placeholder.call_args.kwargs["campaign_name"] == "Free consultation"
    assert placeholder.call_args.kwargs["external_campaign_id"] == "120210000000001"
    assert db.store["leads"][0]["ad_campaign_id"] == "placeholder-camp"


def test_lead_keeps_an_existing_campaign():
    db = _DB(leads=[{"id": "lead-1", "tenant_id": "t1", "ad_campaign_id": "older-camp"}])
    _attribute(db)
    assert db.store["leads"][0]["ad_campaign_id"] == "older-camp"


def test_a_repeat_chat_from_the_same_ad_is_counted_once():
    db = _DB(leads=[{"id": "lead-1", "tenant_id": "t1", "ad_campaign_id": None}])
    _attribute(db)
    _attribute(db)
    assert len(db.store["lead_meta_ad_attributions"]) == 1


def test_non_ad_referral_records_nothing():
    db = _DB()
    ad_id, _ = _attribute(db, referral={"source": "SHORTLINK", "ref": "x"})
    assert ad_id is None
    assert "lead_meta_ad_attributions" not in db.store


def test_attribution_failure_never_raises():
    db = MagicMock()
    db.table.side_effect = RuntimeError("db down")
    ad_id, _ = _attribute(db)
    assert ad_id == "120210000000001"


def test_whatsapp_rows_default_to_the_whatsapp_channel():
    db = _DB()
    record_lead_ad_attribution(
        db, tenant_id="t1", lead_id="l", meta_ad_account_id="act_1", meta_ad_id="9",
        ad_creative_id=None, attribution_method="meta_ad_id",
    )
    assert db.store["lead_meta_ad_attributions"][0]["channel"] == "whatsapp"


# ── webhook routing ───────────────────────────────────────────────────────────

def _request(payload):
    req = MagicMock(spec=Request)
    req.body = AsyncMock(return_value=json.dumps(payload).encode("utf-8"))
    req.headers = {"X-Hub-Signature-256": "sha256=x"}
    return req


def _messenger(event):
    return {"object": "page", "entry": [{"id": "page-1", "messaging": [event]}]}


def _instagram(event):
    return {"object": "instagram", "entry": [{"id": "ig-1", "messaging": [event]}]}


def _db_with_no_duplicate_messages():
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    return db


async def _run_facebook(payload):
    from app.routes import facebook

    db = _db_with_no_duplicate_messages()
    with patch.object(facebook, "verify_meta_signature", return_value=True), \
         patch.object(facebook, "resolve_tenant_for_page", return_value=None), \
         patch.object(facebook, "get_supabase", return_value=db), \
         patch.object(facebook, "_get_or_create_facebook_lead", return_value="lead-fb") as lead, \
         patch.object(facebook, "attribute_chat_to_ad") as attribute, \
         patch("app.services.context_builder.build_scorer_context", return_value=""):
        await facebook.facebook_webhook("t1", _request(payload), MagicMock(spec=BackgroundTasks))
    return db, lead, attribute


async def _run_instagram(payload):
    from app.routes import instagram

    db = _db_with_no_duplicate_messages()
    with patch.object(instagram, "verify_meta_signature", return_value=True), \
         patch.object(instagram, "resolve_tenant_for_page", return_value=None), \
         patch.object(instagram, "get_supabase", return_value=db), \
         patch.object(instagram, "_get_or_create_instagram_lead", return_value="lead-ig") as lead, \
         patch.object(instagram, "attribute_chat_to_ad") as attribute, \
         patch("app.services.context_builder.build_scorer_context", return_value=""):
        await instagram.instagram_webhook("t1", _request(payload), MagicMock(spec=BackgroundTasks))
    return db, lead, attribute


def _inserted_messages(db):
    return [
        c.args[0] for c in db.table.return_value.insert.call_args_list
        if isinstance(c.args[0], dict) and "direction" in c.args[0]
    ]


@pytest.mark.asyncio
async def test_messenger_ad_chat_is_credited_and_flagged():
    db, _, attribute = await _run_facebook(_messenger({
        "sender": {"id": "psid-1"}, "recipient": {"id": "page-1"},
        "message": {"mid": "m1", "text": "Hi", "referral": AD_REFERRAL},
    }))
    attribute.assert_called_once()
    assert attribute.call_args.kwargs["channel"] == "messenger"
    assert attribute.call_args.kwargs["lead_id"] == "lead-fb"
    [msg] = _inserted_messages(db)
    assert msg["via_ad_referral"] is True


@pytest.mark.asyncio
async def test_messenger_returning_chat_via_ad_is_credited_without_a_message():
    """Standalone messaging_referrals event: existing thread re-opened from an ad."""
    db, lead, attribute = await _run_facebook(_messenger({
        "sender": {"id": "psid-1"}, "recipient": {"id": "page-1"},
        "referral": AD_REFERRAL,
    }))
    lead.assert_called_once()
    attribute.assert_called_once()
    assert _inserted_messages(db) == []


@pytest.mark.asyncio
async def test_messenger_shortlink_referral_credits_nothing():
    _, lead, attribute = await _run_facebook(_messenger({
        "sender": {"id": "psid-1"}, "recipient": {"id": "page-1"},
        "referral": {"source": "SHORTLINK", "type": "OPEN_THREAD", "ref": "promo"},
    }))
    lead.assert_not_called()
    attribute.assert_not_called()


@pytest.mark.asyncio
async def test_plain_messenger_chat_is_not_flagged_as_ad():
    db, _, attribute = await _run_facebook(_messenger({
        "sender": {"id": "psid-1"}, "recipient": {"id": "page-1"},
        "message": {"mid": "m2", "text": "Hello"},
    }))
    attribute.assert_not_called()
    [msg] = _inserted_messages(db)
    assert msg["via_ad_referral"] is False


@pytest.mark.asyncio
async def test_instagram_ad_chat_is_credited_and_flagged():
    db, _, attribute = await _run_instagram(_instagram({
        "sender": {"id": "igsid-1"}, "recipient": {"id": "ig-1"},
        "message": {"mid": "m3", "text": "Price?", "referral": AD_REFERRAL},
    }))
    attribute.assert_called_once()
    assert attribute.call_args.kwargs["channel"] == "instagram"
    [msg] = _inserted_messages(db)
    assert msg["via_ad_referral"] is True


@pytest.mark.asyncio
async def test_instagram_ad_click_without_text_still_credits_the_ad():
    """Meta's documented Click-to-Instagram-Direct example carries no text."""
    db, lead, attribute = await _run_instagram(_instagram({
        "sender": {"id": "igsid-1"}, "recipient": {"id": "ig-1"},
        "message": {"mid": "m4", "referral": AD_REFERRAL},
    }))
    lead.assert_called_once()
    attribute.assert_called_once()
    assert _inserted_messages(db) == []


@pytest.mark.asyncio
async def test_instagram_echo_is_ignored_even_with_a_referral():
    _, lead, attribute = await _run_instagram(_instagram({
        "sender": {"id": "ig-1"}, "recipient": {"id": "igsid-1"},
        "message": {"mid": "m5", "text": "our reply", "is_echo": True, "referral": AD_REFERRAL},
    }))
    lead.assert_not_called()
    attribute.assert_not_called()
