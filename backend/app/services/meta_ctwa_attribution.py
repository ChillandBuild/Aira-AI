"""Simple Meta Click-to-WhatsApp attribution helpers.

One lead is counted once per Meta ad. Meta's webhook referral ad id is the
primary signal; a short code in the pre-filled message is only a fallback.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone


_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_TRACKING_RE = re.compile(
    r"(?:\[AIRA:([A-Z0-9]{6,12})\]|AIRA-([A-Z0-9]{6,12}))",
    re.IGNORECASE,
)
_DEFAULT_GREETING = "Hi, I'm interested in this service."


def parse_tracking_code(text: str | None) -> str | None:
    """Return the normalized Aira ad code in an inbound message, if present."""
    if not text:
        return None
    match = _TRACKING_RE.search(text)
    if not match:
        return None
    return (match.group(1) or match.group(2)).upper()


def generate_tracking_code(length: int = 6) -> str:
    """Generate a short human-readable code without ambiguous 0/O/1/I chars."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def build_prefilled_message(greeting: str | None, code: str) -> str:
    """Append one canonical tracking tag, replacing any older Aira tag."""
    clean = _TRACKING_RE.sub("", (greeting or "")).strip()
    clean = clean or _DEFAULT_GREETING
    return f"{clean}\nRef: [AIRA:{code.upper()}]"


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
) -> tuple[dict | None, str | None]:
    """Resolve the current-account creative, preferring Meta's referral ad id."""
    if referral_ad_id:
        result = (
            db.table("ad_creatives")
            .select("id,meta_ad_id,campaign_id,prefilled_message_code")
            .eq("tenant_id", tenant_id)
            .eq("meta_ad_account_id", meta_ad_account_id)
            .eq("is_click_to_whatsapp", True)
            .eq("meta_ad_id", referral_ad_id)
            .limit(1)
            .execute()
        )
        creative = _first(result)
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
) -> bool:
    """Insert once per lead/ad; repeat contacts only refresh last_seen_at.

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
