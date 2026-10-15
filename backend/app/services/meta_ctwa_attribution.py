"""Meta click-to-message ad attribution helpers (WhatsApp, Instagram, Messenger).

One lead is counted once per Meta ad. Meta's webhook referral ad id is the
primary signal; a short code in the pre-filled message is a WhatsApp-only
fallback (only WhatsApp ads can pre-fill the first message).
"""

from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_TRACKING_RE = re.compile(
    # Ads already running carry the old AIRA tag; new ones are written as ANRIL.
    r"(?:\[(?:ANRIL|AIRA):([A-Z0-9]{6,12})\]|(?:ANRIL|AIRA)-([A-Z0-9]{6,12}))",
    re.IGNORECASE,
)
_DEFAULT_GREETING = "Hi, I'm interested in this service."


def parse_tracking_code(text: str | None) -> str | None:
    """Return the normalized Anril ad code in an inbound message, if present."""
    if not text:
        return None
    match = _TRACKING_RE.search(text)
    if not match:
        return None
    return (match.group(1) or match.group(2)).upper()


def generate_tracking_code(length: int = 6) -> str:
    """Generate a short human-readable code without ambiguous 0/O/1/I chars."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def clean_greeting(greeting: str | None) -> str:
    """Strip any tracking tag and return the greeting text alone, falling back
    to the default. This is the exact text scoring_engine.py should expect a
    lead to have sent verbatim -- store it, don't just discard it."""
    clean = _TRACKING_RE.sub("", (greeting or "")).strip()
    return clean or _DEFAULT_GREETING


def build_prefilled_message(greeting: str | None, code: str) -> str:
    """Append one canonical tracking tag, replacing any older tag
    (the old AIRA form included)."""
    return f"{clean_greeting(greeting)}\nRef: [ANRIL:{code.upper()}]"


def parse_ad_referral(referral: dict | None) -> str | None:
    """The Meta ad id in a webhook referral, or None when it isn't an ad click.

    Instagram and Messenger send {source: "ADS", type: "OPEN_THREAD", ad_id}; WhatsApp
    sends {source_type: "ad", source_id}. Instagram/Messenger handlers used to check
    only the WhatsApp shape, so no chat on those channels was ever credited to an ad.
    """
    r = referral or {}
    if str(r.get("source") or "").upper() == "ADS" and r.get("ad_id"):
        return str(r["ad_id"])
    if r.get("source_type") == "ad" and r.get("source_id"):
        return str(r["source_id"])
    return None


def referral_ad_title(referral: dict | None) -> str | None:
    r = referral or {}
    return (r.get("ads_context_data") or {}).get("ad_title") or r.get("headline") or None


def _first(result) -> dict | None:
    rows = result.data or []
    return rows[0] if rows else None


def find_creative_for_message(
    db,
    *,
    tenant_id: str,
    meta_ad_account_id: str,
    referral_ad_id: str | None,
    body: str | None,
    whatsapp_only: bool = True,
) -> tuple[dict | None, str | None]:
    """Resolve the current-account creative, preferring Meta's referral ad id.

    Instagram/Messenger callers pass whatsapp_only=False: their ad may not open
    WhatsApp at all. The pre-filled-code fallback stays WhatsApp-only."""
    if referral_ad_id:
        query = (
            db.table("ad_creatives")
            .select("id,meta_ad_id,campaign_id,prefilled_message_code")
            .eq("tenant_id", tenant_id)
            .eq("meta_ad_account_id", meta_ad_account_id)
            .eq("meta_ad_id", referral_ad_id)
        )
        if whatsapp_only:
            query = query.eq("is_click_to_whatsapp", True)
        creative = _first(query.limit(1).execute())
        # A valid Meta referral always wins, even if this brand-new ad has not
        # reached the insights sync yet. The relation can still be saved by
        # meta_ad_id and will join to the creative after the next sync.
        return creative, "meta_ad_id"

    code = parse_tracking_code(body)
    if not code:
        return None, None

    result = (
        db.table("ad_creatives")
        .select("id,meta_ad_id,campaign_id,prefilled_message_code")
        .eq("tenant_id", tenant_id)
        .eq("meta_ad_account_id", meta_ad_account_id)
        .eq("is_click_to_whatsapp", True)
        .eq("prefilled_message_code", code)
        .limit(1)
        .execute()
    )
    creative = _first(result)
    return (creative, "prefilled_code") if creative else (None, None)


def ensure_creative_tracking_code(
    db,
    *,
    tenant_id: str,
    meta_ad_account_id: str,
    ad_creative_id: str,
) -> dict | None:
    """Return a creative with a stable tracking code, creating it when absent."""
    query = (
        db.table("ad_creatives")
        .select("id,creative_label,meta_ad_id,prefilled_message_code")
        .eq("id", ad_creative_id)
        .eq("tenant_id", tenant_id)
        .eq("meta_ad_account_id", meta_ad_account_id)
        .eq("is_click_to_whatsapp", True)
        .limit(1)
    )
    creative = _first(query.execute())
    if not creative:
        return None
    if creative.get("prefilled_message_code"):
        return creative

    for _ in range(8):
        code = generate_tracking_code()
        collision = (
            db.table("ad_creatives")
            .select("id")
            .eq("tenant_id", tenant_id)
            .eq("prefilled_message_code", code)
            .limit(1)
            .execute()
        )
        if collision.data:
            continue
        try:
            updated = (
                db.table("ad_creatives")
                .update({"prefilled_message_code": code})
                .eq("id", ad_creative_id)
                .eq("tenant_id", tenant_id)
                .eq("meta_ad_account_id", meta_ad_account_id)
                .execute()
            )
            row = _first(updated)
            if row:
                return {
                    **creative,
                    **row,
                    "prefilled_message_code": row.get("prefilled_message_code") or code,
                }
            return {**creative, "prefilled_message_code": code}
        except Exception:
            # A concurrent request may have set the code first.
            creative = _first(query.execute())
            if creative and creative.get("prefilled_message_code"):
                return creative
    raise RuntimeError("Could not generate a unique tracking code")


def record_lead_ad_attribution(
    db,
    *,
    tenant_id: str,
    lead_id: str,
    meta_ad_account_id: str,
    meta_ad_id: str,
    ad_creative_id: str | None,
    attribution_method: str,
    channel: str = "whatsapp",
) -> bool:
    """Insert once per lead/ad; repeat contacts only refresh last_seen_at.

    `channel` (whatsapp | instagram | messenger) is the chat app the lead used;
    a lead row belongs to one channel, so it never changes on repeat contacts.
    Returns True when this is the first relationship for the lead and ad.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    table = db.table("lead_meta_ad_attributions")
    existing = (
        table.select("attribution_method,ad_creative_id")
        .eq("tenant_id", tenant_id)
        .eq("lead_id", lead_id)
        .eq("meta_ad_id", meta_ad_id)
        .limit(1)
        .execute()
    )
    row = _first(existing)
    if row:
        update = {
            "last_seen_at": now_iso,
            "updated_at": now_iso,
        }
        if ad_creative_id and not row.get("ad_creative_id"):
            update["ad_creative_id"] = ad_creative_id
        if attribution_method == "meta_ad_id" and row.get("attribution_method") != "meta_ad_id":
            update["attribution_method"] = "meta_ad_id"
        (
            db.table("lead_meta_ad_attributions")
            .update(update)
            .eq("tenant_id", tenant_id)
            .eq("lead_id", lead_id)
            .eq("meta_ad_id", meta_ad_id)
            .execute()
        )
        return False

    payload = {
        "tenant_id": tenant_id,
        "lead_id": lead_id,
        "meta_ad_account_id": meta_ad_account_id,
        "meta_ad_id": meta_ad_id,
        "ad_creative_id": ad_creative_id,
        "attribution_method": attribution_method,
        "channel": channel,
        "first_seen_at": now_iso,
        "last_seen_at": now_iso,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    try:
        db.table("lead_meta_ad_attributions").insert(payload).execute()
        return True
    except Exception:
        # The unique key handles simultaneous deliveries for the same lead/ad.
        raced = (
            db.table("lead_meta_ad_attributions")
            .select("lead_id")
            .eq("tenant_id", tenant_id)
            .eq("lead_id", lead_id)
            .eq("meta_ad_id", meta_ad_id)
            .limit(1)
            .execute()
        )
        if not raced.data:
            raise
        (
            db.table("lead_meta_ad_attributions")
            .update({"last_seen_at": now_iso, "updated_at": now_iso})
            .eq("tenant_id", tenant_id)
            .eq("lead_id", lead_id)
            .eq("meta_ad_id", meta_ad_id)
            .execute()
        )
        return False


def attribute_chat_to_ad(
    db,
    *,
    tenant_id: str,
    lead_id: str,
    referral: dict | None,
    channel: str,
    platform: str,
) -> str | None:
    """Credit an Instagram/Messenger chat to the Meta ad it came from.

    Mirrors the WhatsApp webhook: one lead_meta_ad_attributions row per lead and
    ad (that is what the Messaging ads report counts), and the lead's campaign is
    set only when it has none yet. A brand-new ad that hasn't synced is still
    recorded by its ad id and joins to its creative after the next sync.
    Returns the ad id when the referral was an ad click, else None. Best-effort:
    a failure is logged and never blocks the message itself.
    """
    ad_id = parse_ad_referral(referral)
    if not ad_id:
        return None
    r = referral or {}
    # No PII: which ad, and which referral shape Meta sent.
    logger.info(
        "%s ad referral: tenant=%s lead=%s ad_id=%s source=%s type=%s",
        channel, tenant_id, lead_id, ad_id, r.get("source") or r.get("source_type"), r.get("type"),
    )
    try:
        from app.services.meta_ads_insights_sync import get_current_ads_account_id

        account_id = get_current_ads_account_id(db, tenant_id)
        creative = None
        if account_id:
            creative, _ = find_creative_for_message(
                db,
                tenant_id=tenant_id,
                meta_ad_account_id=account_id,
                referral_ad_id=ad_id,
                body=None,
                whatsapp_only=False,
            )
            record_lead_ad_attribution(
                db,
                tenant_id=tenant_id,
                lead_id=lead_id,
                meta_ad_account_id=account_id,
                meta_ad_id=ad_id,
                ad_creative_id=(creative or {}).get("id"),
                attribution_method="meta_ad_id",
                channel=channel,
            )

        campaign_id = (creative or {}).get("campaign_id")
        if not campaign_id:
            # Same fallback as WhatsApp: a placeholder campaign keyed by the ad id,
            # folded into the real campaign once the ad syncs.
            from app.services.growth import get_or_create_campaign

            placeholder = get_or_create_campaign(
                db,
                tenant_id=tenant_id,
                platform=platform,
                campaign_name=referral_ad_title(r) or ad_id,
                external_campaign_id=ad_id,
            )
            campaign_id = (placeholder or {}).get("id")
        if campaign_id:
            current = (
                db.table("leads").select("ad_campaign_id")
                .eq("id", lead_id).eq("tenant_id", tenant_id).limit(1).execute()
            )
            if current.data and not current.data[0].get("ad_campaign_id"):
                db.table("leads").update({"ad_campaign_id": campaign_id}).eq(
                    "id", lead_id
                ).eq("tenant_id", tenant_id).execute()
    except Exception as err:
        logger.warning("%s ad attribution failed for lead %s: %s", channel, lead_id, err)
    return ad_id
