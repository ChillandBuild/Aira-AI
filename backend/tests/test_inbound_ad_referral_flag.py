"""Every ad channel must stamp `via_ad_referral` on the inbound message row.

The dashboard's returning-lead count reads this column, and it is the only
per-message ad signal there is: a lead's `ad_campaign_id` is deliberately left
untouched on repeat contacts, so it cannot say whether *this* message came from
an ad. Meta Click-to-WhatsApp already set the flag; Instagram, Messenger and
Google click-to-chat detected the ad and then dropped the fact on the floor,
which made every returning lead on those channels uncountable.
"""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routes import facebook, instagram, webhook


class _Result:
    def __init__(self, data):
        self.data = data


class _Table:
    """Minimal PostgREST stand-in that records inserted message rows."""

    def __init__(self, name, captured_messages):
        self.name = name
        self.captured_messages = captured_messages
        self.operation = "select"

    def select(self, *_a, **_k):
        self.operation = "select"
        return self

    def insert(self, row):
        self.operation = "insert"
        if self.name == "messages":
            self.captured_messages.append(row)
        return self

    def update(self, _row):
        self.operation = "update"
        return self

    def eq(self, *_a, **_k):
        return self

    def is_(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def maybe_single(self):
        return self

    def execute(self):
        if self.name == "phone_numbers":
            return _Result({"tenant_id": "tenant-1"})
        if self.name == "leads" and self.operation == "select":
            return _Result([{"id": "lead-1", "tenant_id": "tenant-1"}])
        if self.name == "leads" and self.operation == "insert":
            return _Result([{"id": "lead-1"}])
        if self.name == "messages" and self.operation == "insert":
            return _Result([{"id": "message-1"}])
        return _Result([])


def _db(captured):
    db = MagicMock()
    db.table.side_effect = lambda name: _Table(name, captured)
    return db


def _ad_referral(source_type="ad"):
    return {"source_type": source_type, "source_id": "ad-123", "headline": "Summer offer"}


# ── Instagram ──────────────────────────────────────────────────────────────

def _instagram_payload(referral=None):
    message = {"mid": "mid.instagram.1", "text": "Hello"}
    event = {
        "sender": {"id": "ig-user-1"},
        "recipient": {"id": "ig-page-1"},
        "timestamp": 1716223400,
        "message": message,
    }
    if referral:
        event["referral"] = referral
    return {"object": "instagram", "entry": [{"id": "ig-page-1", "time": 1, "messaging": [event]}]}


async def _post_instagram(db, payload):
    request = MagicMock(spec=Request)
    request.json = AsyncMock(return_value=payload)
    request.body = AsyncMock(return_value=json.dumps(payload).encode("utf-8"))
    with patch("app.routes.instagram.get_supabase", return_value=db), \
         patch("app.routes.instagram.verify_meta_signature", return_value=True), \
         patch("app.routes.instagram.resolve_tenant_for_page", return_value="tenant-1"), \
         patch("app.routes.instagram.record_stage_event"), \
         patch("app.routes.instagram.get_or_create_campaign", return_value={"id": "camp-1"}):
        return await instagram.instagram_webhook(
            tenant_id="tenant-1", request=request,
            background_tasks=MagicMock(spec=BackgroundTasks),
        )


@pytest.mark.asyncio
async def test_instagram_ad_click_flags_the_message():
    captured = []
    await _post_instagram(_db(captured), _instagram_payload(_ad_referral()))
    assert captured, "no message row inserted"
    assert captured[-1]["via_ad_referral"] is True


@pytest.mark.asyncio
async def test_instagram_organic_dm_is_not_flagged():
    captured = []
    await _post_instagram(_db(captured), _instagram_payload())
    assert captured[-1]["via_ad_referral"] is False


@pytest.mark.asyncio
async def test_instagram_non_ad_referral_is_not_flagged():
    """A referral object exists for non-ad entry points too (shortlinks, QR
    codes); only source_type == 'ad' is an ad."""
    captured = []
    await _post_instagram(_db(captured), _instagram_payload(_ad_referral(source_type="SHORTLINK")))
    assert captured[-1]["via_ad_referral"] is False


# ── Facebook Messenger ─────────────────────────────────────────────────────

def _facebook_payload(referral=None):
    event = {
        "sender": {"id": "fb-user-1"},
        "recipient": {"id": "fb-page-1"},
        "timestamp": 1716223400,
        "message": {"mid": "mid.facebook.1", "text": "Hello"},
    }
    if referral:
        event["referral"] = referral
    return {"object": "page", "entry": [{"id": "fb-page-1", "time": 1, "messaging": [event]}]}


async def _post_facebook(db, payload):
    request = MagicMock(spec=Request)
    request.json = AsyncMock(return_value=payload)
    request.body = AsyncMock(return_value=json.dumps(payload).encode("utf-8"))
    with patch("app.routes.facebook.get_supabase", return_value=db), \
         patch("app.routes.facebook.verify_meta_signature", return_value=True), \
         patch("app.routes.facebook.resolve_tenant_for_page", return_value="tenant-1"), \
         patch("app.routes.facebook.record_stage_event"), \
         patch("app.routes.facebook.get_or_create_campaign", return_value={"id": "camp-1"}):
        return await facebook.facebook_webhook(
            tenant_id="tenant-1", request=request,
            background_tasks=MagicMock(spec=BackgroundTasks),
        )


@pytest.mark.asyncio
async def test_facebook_ad_click_flags_the_message():
    captured = []
    await _post_facebook(_db(captured), _facebook_payload(_ad_referral()))
    assert captured, "no message row inserted"
    assert captured[-1]["via_ad_referral"] is True


@pytest.mark.asyncio
async def test_facebook_organic_dm_is_not_flagged():
    captured = []
    await _post_facebook(_db(captured), _facebook_payload())
    assert captured[-1]["via_ad_referral"] is False


# ── WhatsApp click-to-chat from a Google ad ────────────────────────────────

def _whatsapp_payload(body):
    return {
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": "phone-number-1"},
                    "contacts": [{"profile": {"name": "Ramesh"}, "wa_id": "919999999999"}],
                    "messages": [{
                        "from": "919999999999",
                        "id": "wamid.google.1",
                        "timestamp": "1700000000",
                        "type": "text",
                        "text": {"body": body},
                    }],
                },
            }],
        }],
    }


async def _post_whatsapp(db, payload):
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=json.dumps(payload).encode("utf-8"))
    request.headers = {"x-hub-signature-256": "sha256=test"}
    with patch("app.routes.webhook.get_supabase", return_value=db), \
         patch("app.routes.webhook.verify_meta_signature", return_value=True):
        return await webhook.whatsapp_webhook(request, MagicMock(spec=BackgroundTasks))


@pytest.mark.asyncio
async def test_google_ad_tag_flags_the_message():
    """The campaign link below this branch is skipped for a lead that already
    has an attribution, which previously left repeat Google clicks unflagged."""
    captured = []
    await _post_whatsapp(_db(captured), _whatsapp_payload("Hi, I'm interested [GADS:summer_sale]"))
    inbound = [m for m in captured if m.get("direction") == "inbound"]
    assert inbound, "no inbound message row inserted"
    assert inbound[-1]["via_ad_referral"] is True


@pytest.mark.asyncio
async def test_organic_whatsapp_message_is_not_flagged():
    captured = []
    await _post_whatsapp(_db(captured), _whatsapp_payload("Hi, is this still available?"))
    inbound = [m for m in captured if m.get("direction") == "inbound"]
    assert inbound, "no inbound message row inserted"
    assert inbound[-1]["via_ad_referral"] is False
