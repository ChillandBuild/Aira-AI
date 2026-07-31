"""Write-capable Meta Marketing API client for Click-to-WhatsApp campaign
creation and management. Requires ads_management + pages_manage_ads. Standard
Access works against Aira's own ad account; client accounts need Advanced Access.
"""
import logging
import httpx

from app.services.meta_ads_insights_sync import _get_ads_credentials
from app.services.meta_ads_payloads import (
    build_campaign_payload, build_adset_payload, build_targeting,
    build_creative_payload, build_ad_payload,
)

logger = logging.getLogger(__name__)
_GRAPH_BASE = "https://graph.facebook.com/v21.0"


def _post(path: str, token: str, payload: dict) -> dict:
    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{_GRAPH_BASE}/{path}",
                           data={**payload, "access_token": token})
        resp.raise_for_status()
        return resp.json()


def _get(path: str, token: str, params: dict) -> dict:
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{_GRAPH_BASE}/{path}", params={**params, "access_token": token})
        resp.raise_for_status()
        return resp.json()


def list_pages(token: str, account: str) -> list[dict]:
    body = _get(f"{account}/promote_pages", token, {"fields": "id,name", "limit": "100"})
    return body.get("data", [])


def upload_image(token: str, account: str, image_bytes: bytes, filename: str) -> str:
    with httpx.Client(timeout=60) as client:
        resp = client.post(f"{_GRAPH_BASE}/{account}/adimages",
                           data={"access_token": token},
                           files={"filename": (filename, image_bytes)})
        resp.raise_for_status()
        images = resp.json().get("images", {})
        first = next(iter(images.values()), {})
        return first.get("hash", "")


def create_full_campaign(db, tenant_id: str, *, spec: dict) -> dict:
    creds = _get_ads_credentials(db, tenant_id)
    if not creds:
        return {"ok": False, "error": "No Ads Account ID / token configured for this tenant.",
                "campaign_id": None, "meta_campaign_id": None}
    token, account = creds
    try:
        camp = _post(f"{account}/campaigns", token, build_campaign_payload(
            spec["name"],
            daily_budget_inr=spec.get("daily_budget_inr"),
            lifetime_budget_inr=spec.get("lifetime_budget_inr"),
            special_ad_category=spec.get("special_ad_category")))
        targeting = build_targeting(spec["location_countries"], spec["age_min"],
                                    spec["age_max"], spec["gender"])
        adset = _post(f"{account}/adsets", token, build_adset_payload(
            f"{spec['name']} — Ad set", camp["id"], spec["page_id"], targeting))
        creative = _post(f"{account}/adcreatives", token, build_creative_payload(
            spec["creative_label"], spec["page_id"], spec["message"], spec["headline"],
            spec["image_hash"], spec["greeting"]))
        ad = _post(f"{account}/ads", token, build_ad_payload(
            spec["creative_label"], adset["id"], creative["id"]))
    except Exception as e:
        logger.error(f"create_full_campaign failed (tenant {tenant_id}): {e}")
        return {"ok": False, "error": str(e), "campaign_id": None, "meta_campaign_id": None}

    meta_ids = {"campaign_id": camp["id"], "adset_id": adset["id"],
                "ad_id": ad["id"], "creative_id": creative["id"]}
    row = persist_created_campaign(db, tenant_id, meta_ids, spec, account=account)
    return {"ok": True, "error": None, "campaign_id": row["id"], "meta_campaign_id": camp["id"]}


def persist_created_campaign(
    db,
    tenant_id: str,
    meta_ids: dict,
    spec: dict,
    *,
    account: str | None = None,
) -> dict:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    camp_row = db.table("ad_campaigns").insert({
        "tenant_id": tenant_id, "platform": "whatsapp",
        "campaign_name": spec["name"], "external_campaign_id": meta_ids["campaign_id"],
        "objective": "OUTCOME_ENGAGEMENT", "created_via": "aira",
        "page_id": spec.get("page_id"), "special_ad_category": spec.get("special_ad_category"),
        "daily_budget": spec.get("daily_budget_inr"),
        "lifetime_budget": spec.get("lifetime_budget_inr"),
        "effective_status": "IN_PROCESS",
        "meta_ad_account_id": account,
    }).execute().data[0]

    db.table("ad_sets").insert({
        "tenant_id": tenant_id, "campaign_id": camp_row["id"],
        "meta_adset_id": meta_ids["adset_id"], "adset_name": f"{spec['name']} — Ad set",
        "optimization_goal": "CONVERSATIONS", "created_via": "aira",
        "targeting": {"age_min": spec.get("age_min"), "age_max": spec.get("age_max"),
                      "gender": spec.get("gender"), "countries": spec.get("location_countries")},
        "created_at": now, "updated_at": now,
    }).execute()

    db.table("ad_creatives").insert({
        "tenant_id": tenant_id, "campaign_id": camp_row["id"],
        "meta_ad_id": meta_ids["ad_id"], "meta_adset_id": meta_ids["adset_id"],
        "meta_campaign_id": meta_ids["campaign_id"], "creative_label": spec["creative_label"],
        "created_by_aira": True, "prefilled_greeting": spec.get("greeting"),
        "media_asset_ref": meta_ids.get("creative_id"), "cta_type": "WHATSAPP_MESSAGE",
        "meta_ad_account_id": account, "is_click_to_whatsapp": True,
        "optimization_goal": "CONVERSATIONS", "effective_status": "IN_PROCESS",
        "created_at": now, "updated_at": now,
    }).execute()
    return camp_row


def _meta_campaign_id(db, tenant_id: str, campaign_id: str) -> str | None:
    row = (db.table("ad_campaigns").select("external_campaign_id")
           .eq("id", campaign_id).eq("tenant_id", tenant_id).limit(1).execute().data or [None])[0]
    return row.get("external_campaign_id") if row else None


def set_campaign_status(db, tenant_id: str, campaign_id: str, active: bool) -> dict:
    creds = _get_ads_credentials(db, tenant_id)
    if not creds:
        return {"ok": False, "error": "No credentials configured."}
    token, _ = creds
    mid = _meta_campaign_id(db, tenant_id, campaign_id)
    if not mid:
        return {"ok": False, "error": "Campaign not found."}
    status = "ACTIVE" if active else "PAUSED"
    try:
        _post(mid, token, {"status": status})
    except Exception as e:
        return {"ok": False, "error": str(e)}
    db.table("ad_campaigns").update({"effective_status": status}).eq(
        "id", campaign_id).eq("tenant_id", tenant_id).execute()
    return {"ok": True, "error": None, "status": status}


def update_campaign_budget(db, tenant_id: str, campaign_id: str, *,
                           daily_budget_inr=None, lifetime_budget_inr=None) -> dict:
    creds = _get_ads_credentials(db, tenant_id)
    if not creds:
        return {"ok": False, "error": "No credentials configured."}
    token, _ = creds
    mid = _meta_campaign_id(db, tenant_id, campaign_id)
    if not mid:
        return {"ok": False, "error": "Campaign not found."}
    payload, updates = {}, {}
    if daily_budget_inr is not None:
        payload["daily_budget"] = int(round(daily_budget_inr * 100))
        updates["daily_budget"] = daily_budget_inr
    if lifetime_budget_inr is not None:
        payload["lifetime_budget"] = int(round(lifetime_budget_inr * 100))
        updates["lifetime_budget"] = lifetime_budget_inr
    if not payload:
        return {"ok": False, "error": "No budget provided."}
    try:
        _post(mid, token, payload)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    db.table("ad_campaigns").update(updates).eq("id", campaign_id).eq("tenant_id", tenant_id).execute()
    return {"ok": True, "error": None}
