"""End to end: a signed Meta webhook for an Instagram / Messenger ad click lands in
the Messaging ads report's "Messages sent" for that ad.

Everything real except the database (in-memory fake) and the AI reply: the route
handlers, Meta signature check, ad-referral parsing, attribution, and
build_creative_performance. Payload shapes follow Meta's webhook reference.
"""
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, Request

from tests.fake_supabase import FakeSupabase

SECRET = "test-app-secret"
ACCOUNT = "act_111"
AD_ID = "120210000000777"
REFERRAL = {
    "ad_id": AD_ID,
    "source": "ADS",
    "type": "OPEN_THREAD",
    "ads_context_data": {"ad_title": "Diwali offer"},
}


def _db() -> FakeSupabase:
    db = FakeSupabase()
    db.add("app_settings", tenant_id="t1", key="meta_ads_account_id", value=ACCOUNT)
    db.add("ad_campaigns", id="c1", tenant_id="t1", meta_ad_account_id=ACCOUNT, campaign_name="Diwali")
    db.add(
        "ad_creatives", id="cr1", tenant_id="t1", meta_ad_account_id=ACCOUNT, campaign_id="c1",
        meta_ad_id=AD_ID, creative_label="Diwali reel", tracked_in_anril=True,
        is_click_to_whatsapp=True, destination_type="MESSAGING_INSTAGRAM_DIRECT_MESSENGER_WHATSAPP",
        messaging_channels=["whatsapp", "instagram", "messenger"], ad_effective_status="ACTIVE",
    )
    return db


def _signed_request(payload: dict) -> Request:
    body = json.dumps(payload).encode("utf-8")
    digest = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    req = MagicMock(spec=Request)
    req.body = AsyncMock(return_value=body)
    req.headers = {"X-Hub-Signature-256": f"sha256={digest}"}
    return req


def _setting(key, tenant_id=None):
    return SECRET if key in ("meta_app_secret", "instagram_app_secret") else None


async def _deliver(module, handler_name: str, db, payload):
    with patch.object(module, "get_supabase", return_value=db), \
         patch.object(module, "resolve_tenant_for_page", return_value="t1"), \
         patch("app.services.meta_webhook_verify.get_setting", side_effect=_setting), \
         patch("app.services.meta_ads_insights_sync.get_current_ads_account_id", return_value=ACCOUNT), \
         patch("app.services.segmentation.new_lead_score_and_segment", return_value=(10, "C")), \
         patch.object(module, "new_lead_score_and_segment", return_value=(10, "C")), \
         patch.object(module, "record_stage_event"), \
         patch("app.services.assignment.maybe_assign_lead"), \
         patch("app.services.notify.notify_assigned_caller_of_reply"), \
         patch("app.services.conversation_state.get_or_create_state", return_value={"message_count": 0}), \
         patch("app.services.context_builder.build_scorer_context", return_value=""):
        handler = getattr(module, handler_name)
        return await handler("t1", _signed_request(payload), MagicMock(spec=BackgroundTasks))


def _report(db):
    from app.services import ad_performance

    with patch("app.services.meta_ads_insights_sync._get_ads_credentials", return_value=None):
        return ad_performance.build_creative_performance(db, "t1")


@pytest.mark.asyncio
async def test_instagram_and_messenger_ad_chats_count_in_the_report():
    from app.routes import facebook, instagram

    db = _db()
    await _deliver(instagram, "instagram_webhook", db, {"object": "instagram", "entry": [{
        "id": "ig-1", "messaging": [{
            "sender": {"id": "igsid-1"}, "recipient": {"id": "ig-1"},
            "message": {"mid": "ig-m1", "text": "Price?", "referral": REFERRAL},
        }],
    }]})
    await _deliver(facebook, "facebook_webhook", db, {"object": "page", "entry": [{
        "id": "page-1", "messaging": [{
            "sender": {"id": "psid-1"}, "recipient": {"id": "page-1"},
            "message": {"mid": "fb-m1", "text": "Hi", "referral": REFERRAL},
        }],
    }]})
    # Same Messenger person again from the same ad: still one.
    await _deliver(facebook, "facebook_webhook", db, {"object": "page", "entry": [{
        "id": "page-1", "messaging": [{
            "sender": {"id": "psid-1"}, "recipient": {"id": "page-1"},
            "message": {"mid": "fb-m2", "text": "Hello again", "referral": REFERRAL},
        }],
    }]})

    attributions = db.rows("lead_meta_ad_attributions")
    assert sorted(a["channel"] for a in attributions) == ["instagram", "messenger"]
    assert {a["ad_creative_id"] for a in attributions} == {"cr1"}

    [row] = _report(db)
    assert row["messages"] == 2
    assert row["messages_by_channel"] == {"whatsapp": 0, "instagram": 1, "messenger": 1}
    assert row["messaging_channels"] == ["whatsapp", "instagram", "messenger"]

    flagged = [m for m in db.rows("messages") if m.get("via_ad_referral")]
    assert len(flagged) == 3


@pytest.mark.asyncio
async def test_messenger_returning_chat_via_ad_is_counted():
    from app.routes import facebook

    db = _db()
    await _deliver(facebook, "facebook_webhook", db, {"object": "page", "entry": [{
        "id": "page-1", "messaging": [{
            "sender": {"id": "psid-9"}, "recipient": {"id": "page-1"}, "referral": REFERRAL,
        }],
    }]})
    [row] = _report(db)
    assert row["messages_by_channel"]["messenger"] == 1
    assert db.rows("messages") == []


@pytest.mark.asyncio
async def test_unsigned_payload_credits_nothing():
    from app.routes import instagram

    db = _db()
    payload = {"object": "instagram", "entry": [{"id": "ig-1", "messaging": [{
        "sender": {"id": "igsid-1"}, "recipient": {"id": "ig-1"},
        "message": {"mid": "x", "text": "hi", "referral": REFERRAL},
    }]}]}
    req = _signed_request(payload)
    req.headers = {"X-Hub-Signature-256": "sha256=forged"}
    with patch.object(instagram, "get_supabase", return_value=db), \
         patch("app.services.meta_webhook_verify.get_setting", side_effect=_setting):
        resp = await instagram.instagram_webhook("t1", req, MagicMock(spec=BackgroundTasks))
    assert getattr(resp, "status_code", None) == 403
    assert db.rows("lead_meta_ad_attributions") == []
