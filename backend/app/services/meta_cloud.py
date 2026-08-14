import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import HTTPException

from app.config import settings as env_settings
from app.config_dynamic import get_setting

logger = logging.getLogger(__name__)


_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),
    (0x1F100, 0x1F1FF),
    (0x1F300, 0x1F5FF),
    (0x1F900, 0x1F9FF),
    (0x1FA70, 0x1FAFF),
    (0x2600, 0x27BF),
    (0x2300, 0x23FF),
    (0x2700, 0x27BF),
    (0x1F1E6, 0x1F1FF),
    (0xFE0F, 0xFE0F),
    (0x200D, 0x200D),
)


def _strip_emojis(text: str) -> str:
    """Drop emoji code points (and ZWJ / variation selectors) from a string."""
    out = []
    for ch in text:
        cp = ord(ch)
        if cp < 0x80:
            out.append(ch)
            continue
        cat = unicodedata.category(ch)
        if cat in ("So", "Sk") and any(s <= cp <= e for s, e in _EMOJI_RANGES):
            continue
        if any(s <= cp <= e for s, e in _EMOJI_RANGES):
            continue
        if cp in (0xFE0F, 0x200D):
            continue
        out.append(ch)
    return "".join(out)


def _sanitize_header_or_footer(text: str) -> str:
    """Meta rejects newlines, formatting characters, and emojis in HEADER/FOOTER
    template components. Returns the cleaned text, truncated to 60 chars.

    Logs a warning when characters are stripped so the operator can see what
    was sanitized and adjust the source copy.
    """
    if not text:
        return ""
    original = text
    text = re.sub(r"[\r\n\t\v\f]+", " ", text)
    text = re.sub(r"[*_~`]+", "", text)
    text = _strip_emojis(text)
    text = re.sub(r"\s+", " ", text).strip()
    cleaned = text[:60]
    if cleaned != original.strip()[:60]:
        logger.warning(
            "Template header/footer sanitized: %r -> %r",
            original[:60],
            cleaned,
        )
    return cleaned


class TemplateContentExistsError(HTTPException):
    """Raised when Meta rejects template creation because name+language already exists."""
    pass


_GRAPH_BASE = "https://graph.facebook.com/v21.0"
_BUSINESS_LOGIN_GRAPH_BASE = "https://graph.facebook.com/v25.0"

_TIER_MAP = {
    "TIER_1000": 1000,
    "TIER_10000": 10000,
    "TIER_100000": 100000,
}

# Allowed MIME types and their WhatsApp message type
_MIME_TO_WA_TYPE: dict[str, str] = {
    # Images
    "image/jpeg": "image",
    "image/jpg": "image",
    "image/png": "image",
    "image/webp": "image",
    # Documents
    "application/pdf": "document",
    "application/msword": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
    "application/vnd.ms-excel": "document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "document",
    "application/vnd.ms-powerpoint": "document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "document",
    "text/plain": "document",
    "text/csv": "document",
    # Audio
    "audio/ogg": "audio",
    "audio/mpeg": "audio",
    "audio/mp3": "audio",
    "audio/aac": "audio",
    "audio/amr": "audio",
    "audio/wav": "audio",
    "audio/webm": "audio",
    # Video
    "video/mp4": "video",
    "video/3gpp": "video",
}


def get_wa_type_for_mime(mime_type: str) -> str:
    """Return WhatsApp message type for a given MIME type."""
    return _MIME_TO_WA_TYPE.get(mime_type.lower().split(";")[0].strip(), "document")


def _creds(phone_number_id: Optional[str], access_token: Optional[str], tenant_id: Optional[str] = None) -> tuple[str, str]:
    pid = phone_number_id or get_setting("meta_phone_number_id", tenant_id=tenant_id)
    tok = access_token or get_setting("meta_access_token", tenant_id=tenant_id)
    if not pid or not tok:
        raise HTTPException(status_code=400, detail="Meta credentials not configured. Set them in Settings.")
    return pid, tok


async def exchange_embedded_signup_code(code: str) -> dict:
    """Exchange a Facebook Login for Business authorization code for an access token.

    Shared by WhatsApp Embedded Signup and the Facebook/Instagram Connect flow —
    both are the same underlying OAuth exchange, just different Configurations.
    The code expires ~30 seconds after the frontend receives it from the signup
    popup, so this must run immediately once the flow completes. Uses our own
    Meta app's id/secret (the same app every tenant's signup runs through), not
    a per-tenant credential.
    """
    if not env_settings.meta_app_id or not env_settings.meta_app_secret:
        raise HTTPException(
            status_code=500,
            detail="Embedded Signup is not configured on the server (missing meta_app_id/meta_app_secret).",
        )
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.facebook.com/v25.0/oauth/access_token",
            params={
                "client_id": env_settings.meta_app_id,
                "client_secret": env_settings.meta_app_secret,
                "code": code,
            },
            timeout=10.0,
        )
    data = resp.json()
    if "error" in data:
        raise HTTPException(status_code=400, detail=data["error"].get("message", "Embedded Signup code exchange failed"))
    access_token = data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Meta did not return an access token for this signup code")
    return {"access_token": access_token}


_PAGE_FIELDS = "id,name,access_token,instagram_business_account{id,username}"
_AD_ACCOUNT_FIELDS = "id,name,account_id,account_status,currency,timezone_name"
_CATALOG_FIELDS = "id,name"

# Which granular scopes carry which kind of asset id. Instagram scopes are granted
# against the linked Page, so they belong with the Page scopes.
_PAGE_GRANT_SCOPES = (
    "pages_show_list",
    "pages_messaging",
    "pages_manage_metadata",
    "pages_read_engagement",
    "pages_manage_engagement",
    "pages_read_user_content",
    "pages_manage_posts",
    "instagram_basic",
    "instagram_manage_messages",
    "instagram_manage_comments",
)
_AD_ACCOUNT_GRANT_SCOPES = ("ads_read", "ads_management")
_CATALOG_GRANT_SCOPES = ("catalog_management",)


async def _debug_token_granular_scopes(client: httpx.AsyncClient, access_token: str) -> dict[str, list[str]]:
    """Map each granted scope to the asset ids it was granted on.

    Facebook Login for Business hands back a business-integration *system user*
    token, not a personal one. That token is not a person, so `me/accounts`,
    `me/adaccounts` and `me/product_catalogs` resolve to nothing no matter what
    the operator picked in the signup window — verified against Meta on
    2026-08-14, where a live signup token reported `type: SYSTEM_USER` and
    `me/accounts` returned `{"data": []}` while the Page was plainly granted.
    The granted asset ids only exist in the token's granular scopes.
    """
    if not env_settings.meta_app_id or not env_settings.meta_app_secret:
        logger.warning("Cannot read Meta granular scopes: meta_app_id/meta_app_secret are not configured")
        return {}
    try:
        response = await client.get(
            f"{_BUSINESS_LOGIN_GRAPH_BASE}/debug_token",
            params={
                "input_token": access_token,
                "access_token": f"{env_settings.meta_app_id}|{env_settings.meta_app_secret}",
            },
            timeout=10.0,
        )
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Could not read the assets granted during Meta signup.") from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or payload.get("error"):
        raise HTTPException(status_code=502, detail="Could not read the assets granted during Meta signup.")

    grants: dict[str, list[str]] = {}
    for grant in data.get("granular_scopes") or []:
        if not isinstance(grant, dict):
            continue
        scope = grant.get("scope")
        if not scope:
            continue
        targets = [str(target) for target in grant.get("target_ids") or [] if target]
        grants.setdefault(scope, []).extend(targets)
    logger.info(
        "Meta signup token type=%s scopes=%s granted_assets=%s",
        data.get("type"),
        ",".join(data.get("scopes") or []),
        {scope: len(ids) for scope, ids in grants.items()},
    )
    return grants


def _granted_ids(grants: dict[str, list[str]], scopes: tuple[str, ...]) -> list[str]:
    """Collect the ids granted under any of `scopes`, first-seen order, deduped."""
    ordered: dict[str, None] = {}
    for scope in scopes:
        for target in grants.get(scope, []):
            ordered.setdefault(target, None)
    return list(ordered)


def _as_ad_account_id(target_id: str) -> str:
    """Meta reports ad account grants with and without the act_ prefix."""
    return target_id if target_id.startswith("act_") else f"act_{target_id}"


async def _read_granted_asset(
    client: httpx.AsyncClient,
    node_id: str,
    access_token: str,
    fields: str,
) -> dict | None:
    """Read one granted asset by id. Returns None when Meta will not hand it over."""
    try:
        response = await client.get(
            f"{_BUSINESS_LOGIN_GRAPH_BASE}/{node_id}",
            params={"fields": fields, "access_token": access_token},
            timeout=10.0,
        )
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Granted Meta asset %s could not be read during signup: %s", node_id, exc)
        return None
    if not isinstance(data, dict) or data.get("error") or not data.get("id"):
        logger.warning(
            "Granted Meta asset %s is not readable during signup: %s",
            node_id,
            (data or {}).get("error") if isinstance(data, dict) else data,
        )
        return None
    return data


async def _read_granted_assets(
    client: httpx.AsyncClient,
    node_ids: list[str],
    access_token: str,
    fields: str,
) -> list[dict]:
    assets = []
    for node_id in node_ids:
        asset = await _read_granted_asset(client, node_id, access_token, fields)
        if asset:
            assets.append(asset)
    return assets


async def _list_user_token_pages(client: httpx.AsyncClient, access_token: str) -> list[dict]:
    """Best-effort me/accounts read, for Login configurations that issue a user token.

    A system user token returns an empty list here, so this only ever adds Pages —
    it can never be the reason a signup fails.
    """
    url = f"{_BUSINESS_LOGIN_GRAPH_BASE}/me/accounts"
    params: dict | None = {"fields": _PAGE_FIELDS, "access_token": access_token, "limit": 100}
    pages: list[dict] = []
    while url:
        try:
            response = await client.get(url, params=params, timeout=10.0)
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.info("me/accounts lookup skipped during Meta signup: %s", exc)
            return pages
        if getattr(response, "status_code", 200) >= 400 or data.get("error"):
            logger.info("me/accounts is not readable for this Meta signup token (expected for system user tokens)")
            return pages
        pages.extend(item for item in data.get("data", []) if isinstance(item, dict) and item.get("id"))
        url = data.get("paging", {}).get("next")
        # Meta's paging URL already carries the cursor and access token.
        params = None
    return pages


async def discover_business_login_assets(access_token: str) -> dict[str, list[dict]]:
    """Discover assets granted by a Facebook Login for Business configuration.

    Reads the token's granular scopes for the granted ids, then fetches each asset
    by id. Page access tokens remain in this server-side result — route handlers
    must strip them before returning assets to the browser.
    """
    async with httpx.AsyncClient() as client:
        grants = await _debug_token_granular_scopes(client, access_token)
        pages = await _read_granted_assets(
            client, _granted_ids(grants, _PAGE_GRANT_SCOPES), access_token, _PAGE_FIELDS
        )
        ad_accounts = await _read_granted_assets(
            client,
            [_as_ad_account_id(target) for target in _granted_ids(grants, _AD_ACCOUNT_GRANT_SCOPES)],
            access_token,
            _AD_ACCOUNT_FIELDS,
        )
        catalogs = await _read_granted_assets(
            client, _granted_ids(grants, _CATALOG_GRANT_SCOPES), access_token, _CATALOG_FIELDS
        )
        known_page_ids = {page["id"] for page in pages if page.get("id")}
        pages.extend(
            page for page in await _list_user_token_pages(client, access_token)
            if page["id"] not in known_page_ids
        )
    return {"pages": pages, "ad_accounts": ad_accounts, "catalogs": catalogs}


async def verify_waba_phone_number(waba_id: str, phone_number_id: str, access_token: str) -> bool:
    """Return whether Meta confirms that a phone number belongs to this WABA.

    Both IDs originate in the browser's Embedded Signup event, so this must be
    checked with the server-held token before a tenant can claim either asset.
    """
    url = f"{_BUSINESS_LOGIN_GRAPH_BASE}/{waba_id}/phone_numbers"
    params: dict | None = {"fields": "id", "limit": 100, "access_token": access_token}
    try:
        async with httpx.AsyncClient() as client:
            while url:
                response = await client.get(url, params=params, timeout=10.0)
                data = response.json()
                if getattr(response, "status_code", 200) >= 400 or data.get("error"):
                    raise HTTPException(status_code=502, detail="Meta could not verify the WhatsApp business number.")
                if any(phone.get("id") == phone_number_id for phone in data.get("data", []) if isinstance(phone, dict)):
                    return True
                url = data.get("paging", {}).get("next")
                params = None
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Meta could not verify the WhatsApp business number.") from exc
    return False


async def register_phone_number(phone_number_id: str, access_token: str, pin: str) -> dict:
    """Register a newly-onboarded Cloud API number so it can send/receive messages.
    Required once per phone number after Embedded Signup, before it can be used.

    Non-fatal by design: registration failing (timeout, wrong PIN on an already-registered
    number, etc.) shouldn't block saving the rest of the connection, since the OAuth code
    that got us here is already single-use and consumed either way.
    """
    url = f"{_GRAPH_BASE}/{phone_number_id}/register"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json={"messaging_product": "whatsapp", "pin": pin},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=20.0,
            )
        data = resp.json()
    except httpx.HTTPError as e:
        logger.warning("Phone number registration request failed for %s: %s", phone_number_id, e)
        return {"error": {"message": str(e)}}
    error = data.get("error")
    if error and error.get("code") == 133005:
        # Number already has a 2-step verification PIN set from a prior registration.
        # Meta has no API to reset it (only WhatsApp Manager's UI can) — this isn't a
        # failure, the number is already registered and usable.
        logger.info("Phone number %s already registered (PIN set previously) — skipping re-registration", phone_number_id)
    elif error:
        logger.warning("Phone number registration failed for %s: %s", phone_number_id, error)
    return data


async def send_text_message(
    to_number: str,
    text: str,
    phone_number_id: Optional[str] = None,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    pid, tok = _creds(phone_number_id, access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{pid}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {tok}"})
    if not resp.is_success:
        logger.error("send_text_message failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data = resp.json()
    logger.info("Meta text sent to %s", to_number)
    return data


async def upload_media_to_meta(
    file_bytes: bytes,
    mime_type: str,
    filename: str,
    phone_number_id: Optional[str] = None,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> str:
    """Upload a file to Meta's media hosting and return the media ID."""
    pid, tok = _creds(phone_number_id, access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{pid}/media"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {tok}"},
            data={"messaging_product": "whatsapp"},
            files={"file": (filename, file_bytes, mime_type)},
        )
    if not resp.is_success:
        logger.error("upload_media_to_meta failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=f"Media upload failed: {resp.text}")
    data = resp.json()
    media_id = data.get("id")
    if not media_id:
        raise HTTPException(status_code=500, detail="No media ID returned from Meta")
    logger.info("Media uploaded to Meta, id=%s", media_id)
    return media_id


async def send_media_message(
    to_number: str,
    media_id: Optional[str] = None,
    wa_type: str = "image",
    filename: Optional[str] = None,
    caption: Optional[str] = None,
    phone_number_id: Optional[str] = None,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
    media_link: Optional[str] = None,
) -> dict:
    """
    Send a media message via Meta Cloud API.
    wa_type: 'image' | 'document' | 'audio' | 'video'
    Pass media_link for a public URL, or media_id for an uploaded Meta media handle.
    """
    pid, tok = _creds(phone_number_id, access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{pid}/messages"

    media_obj: dict = {"link": media_link} if media_link else {"id": media_id}
    if caption and wa_type in ("image", "video", "document"):
        media_obj["caption"] = caption
    if filename and wa_type == "document":
        media_obj["filename"] = filename

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": wa_type,
        wa_type: media_obj,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {tok}"})
    if not resp.is_success:
        logger.error("send_media_message failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data = resp.json()
    logger.info("Meta %s sent to %s", wa_type, to_number)
    return data


async def send_location_message(
    to_number: str,
    latitude: float,
    longitude: float,
    name: Optional[str] = None,
    address: Optional[str] = None,
    phone_number_id: Optional[str] = None,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    pid, tok = _creds(phone_number_id, access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{pid}/messages"
    location: dict = {"latitude": latitude, "longitude": longitude}
    if name:
        location["name"] = name
    if address:
        location["address"] = address
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "location",
        "location": location,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {tok}"})
    if not resp.is_success:
        logger.error("send_location_message failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data = resp.json()
    logger.info("Meta location sent to %s", to_number)
    return data


async def send_cta_url_message(
    to_number: str,
    body_text: str,
    button_text: str,
    button_url: str,
    phone_number_id: Optional[str] = None,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    pid, tok = _creds(phone_number_id, access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{pid}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
            "body": {"text": body_text},
            "action": {
                "name": "cta_url",
                "parameters": {"display_text": button_text, "url": button_url},
            },
        },
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {tok}"})
    if not resp.is_success:
        logger.error("send_cta_url_message failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data = resp.json()
    logger.info("Meta cta_url sent to %s", to_number)
    return data


async def send_interactive_buttons(
    to_number: str,
    body_text: str,
    buttons: list,
    phone_number_id: Optional[str] = None,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    pid, tok = _creds(phone_number_id, access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{pid}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
                    for b in buttons[:3]
                ],
            },
        },
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {tok}"})
    if not resp.is_success:
        logger.error("send_interactive_buttons failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data = resp.json()
    logger.info("Meta interactive buttons sent to %s", to_number)
    return data


async def send_audio_message(
    to_number: str,
    audio_url: str,
    phone_number_id: Optional[str] = None,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    """Send an audio message. WhatsApp does not support captions on audio."""
    return await send_media_message(
        to_number=to_number,
        wa_type="audio",
        media_link=audio_url,
        phone_number_id=phone_number_id,
        access_token=access_token,
        tenant_id=tenant_id,
    )


async def send_list_message(
    to_number: str,
    body_text: str,
    button_text: str,
    sections: list[dict],
    header_text: Optional[str] = None,
    footer_text: Optional[str] = None,
    phone_number_id: Optional[str] = None,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    """Send a WhatsApp interactive list message (up to 10 rows across sections)."""
    pid, tok = _creds(phone_number_id, access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{pid}/messages"
    interactive: dict = {
        "type": "list",
        "body": {"text": body_text},
        "action": {
            "button": button_text[:20],
            "sections": sections,
        },
    }
    if header_text:
        interactive["header"] = {"type": "text", "text": header_text[:60]}
    if footer_text:
        interactive["footer"] = {"text": footer_text[:60]}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "interactive",
        "interactive": interactive,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {tok}"})
    if not resp.is_success:
        logger.error("send_list_message failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    logger.info("Meta list message sent to %s", to_number)
    return resp.json()


async def send_catalog_message(
    to_number: str,
    body_text: str,
    catalog_id: str,
    sections: list[dict],
    phone_number_id: Optional[str] = None,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    """Send a WhatsApp product catalog message (product_list interactive type)."""
    pid, tok = _creds(phone_number_id, access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{pid}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "interactive",
        "interactive": {
            "type": "product_list",
            "body": {"text": body_text},
            "action": {
                "catalog_id": catalog_id,
                "sections": sections,
            },
        },
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {tok}"})
    if not resp.is_success:
        logger.error("send_catalog_message failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    logger.info("Meta catalog message sent to %s", to_number)
    return resp.json()


async def download_media_from_meta(
    media_id: str,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> tuple[bytes, str, str]:
    """
    Download media from Meta by media_id.
    Returns: (bytes, mime_type, url)
    """
    _, tok = _creds("placeholder", access_token, tenant_id)
    # First get the media URL
    async with httpx.AsyncClient(timeout=15.0) as client:
        info_resp = await client.get(
            f"{_GRAPH_BASE}/{media_id}",
            headers={"Authorization": f"Bearer {tok}"},
        )
    if not info_resp.is_success:
        raise HTTPException(status_code=info_resp.status_code, detail="Failed to get media info")
    info = info_resp.json()
    media_url = info.get("url", "")
    mime_type = info.get("mime_type", "application/octet-stream")

    # Download the actual file
    async with httpx.AsyncClient(timeout=60.0) as client:
        file_resp = await client.get(media_url, headers={"Authorization": f"Bearer {tok}"})
    if not file_resp.is_success:
        raise HTTPException(status_code=file_resp.status_code, detail="Failed to download media")

    return file_resp.content, mime_type, media_url


async def send_template_message(
    to_number: str,
    template_name: str,
    lang_code: str = "en",
    components: Optional[list] = None,
    phone_number_id: Optional[str] = None,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    pid, tok = _creds(phone_number_id, access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{pid}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": lang_code},
            "components": components or [],
        },
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {tok}"})
    if not resp.is_success:
        logger.error("send_template_message failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data = resp.json()
    logger.info("Meta template '%s' sent to %s", template_name, to_number)
    return data


def _extract_variable_examples(body_text: str) -> list[str]:
    """Return placeholder example values for every {{N}} variable in the body."""
    indices = sorted(set(int(m) for m in re.findall(r"\{\{(\d+)\}\}", body_text)))
    examples = ["Sample text"] * len(indices)
    # Use a descriptive placeholder for {{1}} which is almost always the customer name
    if indices and indices[0] == 1:
        examples[0] = "Rajan Kumar"
    return examples


def _build_button_components(buttons: list[dict], max_btn: int, category: Optional[str] = None) -> list[dict]:
    """Shared button-component builder used by main template + carousel cards."""
    _emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    def _strip_emojis(text: str) -> str:
        return _emoji_pattern.sub("", text).strip()

    is_auth = (category == "AUTHENTICATION")
    out: list[dict] = []
    for btn in buttons[:max_btn]:
        btn_type = btn.get("type", "QUICK_REPLY")
        btn_text = _strip_emojis((btn.get("text") or "")[:25])
        if btn_type == "QUICK_REPLY":
            out.append({"type": "QUICK_REPLY", "text": btn_text})
        elif btn_type == "URL":
            url_val = btn.get("url", "")
            out.append({"type": "URL", "text": btn_text, "url": url_val, "example": [url_val]})
        elif btn_type in ("PHONE_NUMBER", "WHATSAPP_CALL"):
            phone = btn.get("phone", "")
            country = btn.get("country", "+1")
            btn_obj: dict = {"type": "PHONE_NUMBER", "text": btn_text, "phone_number": f"{country} {phone}"}
            if btn_type == "WHATSAPP_CALL" and btn.get("active_for_days"):
                btn_obj["active_for_days"] = btn["active_for_days"]
            out.append(btn_obj)
        elif btn_type == "COPY_CODE":
            if is_auth:
                out.append({"type": "OTP", "otp_type": "COPY_CODE", "text": btn_text or "Copy Code"})
            else:
                offer_code = btn.get("offer_code", "")
                out.append({"type": "COPY_CODE", "text": "Copy offer code", "example": [offer_code]})
        elif btn_type == "ONE_TAP":
            if is_auth:
                out.append({
                    "type": "OTP",
                    "otp_type": "ONE_TAP",
                    "text": btn_text or "Autofill",
                    "autofill_text": btn.get("autofill_text") or "Autofill",
                    "package_name": btn.get("package_name") or "",
                    "signature_hash": btn.get("signature_hash") or ""
                })
            else:
                out.append({"type": "QUICK_REPLY", "text": btn_text or "Autofill"})
    return out


async def submit_template(
    waba_id: str,
    name: str,
    category: str,
    language: str,
    body_text: str,
    header_text: Optional[str] = None,
    header_media_type: Optional[str] = None,  # IMAGE | VIDEO | DOCUMENT | LOCATION
    header_media_url: Optional[str] = None,
    footer_text: Optional[str] = None,
    buttons: list[dict] | None = None,  # Structured buttons
    carousel_cards: list[dict] | None = None,  # 2-10 cards for CAROUSEL templates
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    _, tok = _creds("placeholder", access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{waba_id}/message_templates"

    body_component: dict = {"type": "BODY", "text": body_text}
    examples = _extract_variable_examples(body_text)
    if examples:
        body_component["example"] = {"body_text": [examples]}

    components: list[dict] = [body_component]

    # Handle header (text or media)
    if header_media_type and header_media_type != "NONE":
        # Media header
        media_format = header_media_type.upper()
        header_component: dict = {"type": "HEADER", "format": media_format}
        if header_media_url:
            header_component["example"] = {"header_handle": [header_media_url]}
        components.append(header_component)
    elif header_text and header_text.strip():
        # Text header
        components.append({
            "type": "HEADER",
            "format": "TEXT",
            "text": _sanitize_header_or_footer(header_text)
        })

    if footer_text and footer_text.strip():
        components.append({
            "type": "FOOTER",
            "text": _sanitize_header_or_footer(footer_text)
        })

    if buttons:
        max_btn = 1 if category == "AUTHENTICATION" else 10
        built_buttons = _build_button_components(buttons, max_btn, category)
        # Group CTA buttons first, then Quick Reply / OTP buttons
        ctas = [b for b in built_buttons if b.get("type") in ("URL", "PHONE_NUMBER", "COPY_CODE")]
        qrs = [b for b in built_buttons if b.get("type") not in ("URL", "PHONE_NUMBER", "COPY_CODE")]
        grouped_buttons = ctas + qrs
        if grouped_buttons:
            components.append({"type": "BUTTONS", "buttons": grouped_buttons})

    if carousel_cards:
        cards_payload: list[dict] = []
        for card in carousel_cards[:10]:
            card_components: list[dict] = []
            c_media_type = (card.get("header_media_type") or "IMAGE").upper()
            c_media_url = card.get("header_media_url") or ""
            if c_media_url:
                card_components.append({
                    "type": "HEADER",
                    "format": c_media_type,
                    "example": {"header_handle": [c_media_url]},
                })
            c_body = (card.get("body_text") or "").strip()
            if c_body:
                card_components.append({"type": "BODY", "text": c_body})
            c_buttons = [b for b in (card.get("buttons") or []) if b.get("type") in ("URL", "QUICK_REPLY")]
            if c_buttons:
                card_btn_components = _build_button_components(c_buttons, 2)
                if card_btn_components:
                    card_components.append({"type": "BUTTONS", "buttons": card_btn_components})
            if card_components:
                cards_payload.append({"components": card_components})
        if len(cards_payload) >= 2:
            components.append({"type": "CAROUSEL", "cards": cards_payload})
        else:
            logger.warning("Carousel needs ≥2 valid cards — got %d, skipping carousel component", len(cards_payload))

    payload = {
        "name": name,
        "category": category.upper(),
        "language": language,
        "components": components,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {tok}"})
    if not resp.is_success:
        logger.error("submit_template failed: %s %s", resp.status_code, resp.text)
        try:
            err_body = json.loads(resp.text)
            err_subcode = err_body.get("error", {}).get("error_subcode")
            if err_subcode == 2388024:
                user_msg = err_body.get("error", {}).get("error_user_msg", "Content already exists")
                raise TemplateContentExistsError(
                    status_code=409,
                    detail=f"A template with this name and language already exists on Meta. {user_msg}",
                )
        except json.JSONDecodeError:
            pass
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


async def get_number_quality(
    phone_number_id: Optional[str] = None,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    pid, tok = _creds(phone_number_id, access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{pid}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            url,
            params={"fields": "quality_rating,messaging_limit_tier"},
            headers={"Authorization": f"Bearer {tok}"},
        )
    if not resp.is_success:
        logger.error("get_number_quality failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data = resp.json()
    return {
        "quality_rating": data.get("quality_rating", "UNKNOWN"),
        "messaging_tier": _TIER_MAP.get(data.get("messaging_limit_tier", ""), 0),
    }


async def get_template_status(
    waba_id: str,
    template_name: str,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict | None:
    """
    Fetch current template status from Meta.
    Returns the first matching template dict or None if not found.
    """
    _, tok = _creds("placeholder", access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{waba_id}/message_templates"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            url,
            params={"name": template_name, "fields": "name,status,rejected_reason"},
            headers={"Authorization": f"Bearer {tok}"},
        )
    if not resp.is_success:
        logger.error("get_template_status failed: %s %s", resp.status_code, resp.text)
        return None
    data = resp.json().get("data", [])
    return data[0] if data else None


async def list_all_templates(
    waba_id: str,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> list[dict]:
    """
    Fetch all templates from Meta for a WABA, handling pagination.
    Returns list of template dicts with name, status, category, language, components, rejected_reason.
    """
    _, tok = _creds("placeholder", access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{waba_id}/message_templates"
    params = {
        "fields": "name,status,category,language,components,rejected_reason",
        "limit": 100,
    }
    templates: list[dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        while url:
            resp = await client.get(url, params=params, headers={"Authorization": f"Bearer {tok}"})
            if not resp.is_success:
                logger.error("list_all_templates failed: %s %s", resp.status_code, resp.text)
                break
            body = resp.json()
            templates.extend(body.get("data", []))
            next_url = body.get("paging", {}).get("next")
            url = next_url  # type: ignore[assignment]
            params = {}  # params are embedded in next_url cursor

    return templates


async def list_waba_phone_numbers(
    waba_id: str,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> list[dict]:
    """
    Fetch every phone number registered on a WABA, handling pagination.
    Returns Meta's raw phone-number dicts (id, display_phone_number,
    verified_name, quality_rating, messaging_limit_tier).
    """
    _, tok = _creds("placeholder", access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{waba_id}/phone_numbers"
    params = {
        "fields": "id,display_phone_number,verified_name,quality_rating,messaging_limit_tier",
        "limit": 100,
    }
    numbers: list[dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        while url:
            resp = await client.get(url, params=params, headers={"Authorization": f"Bearer {tok}"})
            if not resp.is_success:
                logger.error("list_waba_phone_numbers failed: %s %s", resp.status_code, resp.text)
                break
            body = resp.json()
            numbers.extend(body.get("data", []))
            next_url = body.get("paging", {}).get("next")
            url = next_url  # type: ignore[assignment]
            params = {}  # params are embedded in next_url cursor

    return numbers


async def delete_template_from_meta(
    template_name: str,
    waba_id: str,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    """
    Delete a template from Meta by name.
    Calls DELETE https://graph.facebook.com/v21.0/{waba_id}/message_templates?name={template_name}
    """
    _, tok = _creds("placeholder", access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{waba_id}/message_templates"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.delete(
            url,
            params={"name": template_name},
            headers={"Authorization": f"Bearer {tok}"},
        )
    if not resp.is_success:
        logger.error("delete_template_from_meta failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=f"Meta template delete failed: {resp.text}")
    logger.info("Deleted template '%s' from Meta (WABA %s)", template_name, waba_id)
    return resp.json()


async def update_template_on_meta(
    meta_template_id: str,
    components: list[dict],
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    """
    Update a rejected/paused template on Meta.
    Calls POST https://graph.facebook.com/v21.0/{template_id} with updated components.
    """
    _, tok = _creds("placeholder", access_token, tenant_id)
    url = f"{_GRAPH_BASE}/{meta_template_id}"
    payload = {"components": components}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {tok}"})
    if not resp.is_success:
        logger.error("update_template_on_meta failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=f"Meta template update failed: {resp.text}")
    logger.info("Updated template %s on Meta", meta_template_id)
    return resp.json()


async def upload_media_for_template(
    file_bytes: bytes,
    file_type: str,
    file_length: int,
    app_id: str,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> str:
    """
    Upload media for template headers using Meta's Resumable Upload API.

    Step 1: Create an upload session → get session ID.
    Step 2: Upload the file bytes to the session → get the `h` handle.
    Returns the handle string for use in template header_handle.
    """
    _, tok = _creds("placeholder", access_token, tenant_id)

    # Step 1: Create upload session
    session_url = f"{_GRAPH_BASE}/{app_id}/uploads"
    async with httpx.AsyncClient(timeout=30.0) as client:
        session_resp = await client.post(
            session_url,
            params={
                "file_length": file_length,
                "file_type": file_type,
                "access_token": tok,
            },
        )
    if not session_resp.is_success:
        logger.error("upload_media_for_template session failed: %s %s", session_resp.status_code, session_resp.text)
        raise HTTPException(status_code=session_resp.status_code, detail=f"Upload session creation failed: {session_resp.text}")
    upload_session_id = session_resp.json().get("id")
    if not upload_session_id:
        raise HTTPException(status_code=500, detail="No upload session ID returned from Meta")

    # Step 2: Upload file bytes
    upload_url = f"{_GRAPH_BASE}/{upload_session_id}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        upload_resp = await client.post(
            upload_url,
            content=file_bytes,
            headers={
                "Authorization": f"OAuth {tok}",
                "file_offset": "0",
                "Content-Type": file_type,
            },
        )
    if not upload_resp.is_success:
        logger.error("upload_media_for_template upload failed: %s %s", upload_resp.status_code, upload_resp.text)
        raise HTTPException(status_code=upload_resp.status_code, detail=f"File upload failed: {upload_resp.text}")
    handle = upload_resp.json().get("h")
    if not handle:
        raise HTTPException(status_code=500, detail="No media handle returned from Meta upload")
    logger.info("Media uploaded for template, handle=%s", handle)
    return handle


async def request_coexistence_sync(phone_number_id: str, access_token: str) -> None:
    """Trigger Meta's SMB App Data API to backfill a coexistence number's existing
    phone contacts and message history. Fire-and-forget: this follows a signup
    that already succeeded, so a failed sync *request* shouldn't read as a failed
    connection -- errors are logged, never raised.
    """
    url = f"{_GRAPH_BASE}/{phone_number_id}/smb_app_data"
    headers = {"Authorization": f"Bearer {access_token}"}
    for sync_type in ("smb_app_state_sync", "history"):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    json={"messaging_product": "whatsapp", "sync_type": sync_type},
                    headers=headers,
                    timeout=20.0,
                )
            data = resp.json()
            if "error" in data:
                logger.warning("Coexistence %s sync request failed for %s: %s", sync_type, phone_number_id, data["error"])
            else:
                logger.info("Coexistence %s sync requested for %s: request_id=%s", sync_type, phone_number_id, data.get("request_id"))
        except httpx.HTTPError as e:
            logger.warning("Coexistence %s sync request failed for %s: %s", sync_type, phone_number_id, e)
