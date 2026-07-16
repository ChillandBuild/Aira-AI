import logging
import re
from typing import Literal
import secrets
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.db.supabase import get_supabase
from app.config import settings as env_settings
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_id, require_permission
from app.services.audit_log import record_audit_event
from app.services.assignment import (
    get_inbox_config, get_telecalling_config,
    save_inbox_config, save_telecalling_config,
    _INBOX_CONFIG_DEFAULT, _TELECALLING_CONFIG_DEFAULT,
)

logger = logging.getLogger(__name__)
router = APIRouter()
require_settings_read = require_permission("settings.view")
require_settings_manage = require_permission("settings.manage")

class SettingsUpdate(BaseModel):
    updates: dict[str, str | None]


class ActivateChannelRequest(BaseModel):
    channel: str  # whatsapp | instagram | facebook | telegram


class EmbeddedSignupRequest(BaseModel):
    code: str
    waba_id: str
    phone_number_id: str
    business_id: str | None = None


class FacebookEmbeddedSignupRequest(BaseModel):
    code: str


class InboxConfigUpdate(BaseModel):
    enabled: bool | None = None
    auto_assign_enabled: bool | None = None
    segments: list[str] | None = None
    channels: list[str] | None = None
    triggers: list[str] | None = None


class TelecallingConfigUpdate(BaseModel):
    enabled: bool | None = None
    segments: list[str] | None = None
    channels: list[str] | None = None
    targets: dict[str, int] | None = None
    scripts: dict[str, str] | None = None
    max_call_attempts: int | None = None
    assignment_mode: Literal["push", "pull"] | None = None
    eval_daily_cap: int | None = None
    shift_mode: str | None = None
    shift_start_hour: int | None = None
    shift_end_hour: int | None = None
    recycle_enabled: bool | None = None
    recycle_delay_hours: int | None = None
    recycle_max_retries: int | None = None
    recycle_start_hour: int | None = None
    recycle_end_hour: int | None = None



def _get_setting_value(db, tenant_id: str, key: str) -> str | None:
    row = (
        db.table("app_settings")
        .select("value")
        .eq("tenant_id", tenant_id)
        .eq("key", key)
        .maybe_single()
        .execute()
    )
    return row.data["value"] if row and row.data else None


async def setup_telegram_webhook(bot_token: str, tenant_id: str) -> tuple[bool, str | None, str | None]:
    """Register Telegram webhook + return (success, secret_token, error_detail)."""
    from app.config_dynamic import get_setting
    # public_base_url is the host of the single shared deployment (global, not per-tenant);
    # only the webhook *path* is tenant-scoped. Source order: dynamic setting → env → last-resort default.
    _RENDER_BASE_URL = "https://aira-ai-5tfr.onrender.com"
    base_url = get_setting("public_base_url") or env_settings.public_base_url or _RENDER_BASE_URL
    if base_url == _RENDER_BASE_URL:
        logger.warning(
            "Telegram webhook base URL fell back to the hardcoded default — "
            "set PUBLIC_BASE_URL so webhooks register against the correct host."
        )
    webhook_url = f"{base_url.rstrip('/')}/webhook/telegram/{tenant_id}"
    secret_token = secrets.token_urlsafe(32)
    try:
        url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json={"url": webhook_url, "secret_token": secret_token},
                timeout=10.0,
            )
            if resp.status_code != 200:
                try:
                    data = resp.json()
                    desc = data.get("description", resp.text)
                except Exception:
                    desc = resp.text
                return False, None, f"Telegram API error ({resp.status_code}): {desc}"
            logger.info(f"Telegram webhook set to {webhook_url} for tenant {tenant_id}")
            return True, secret_token, None
    except httpx.RequestError as req_err:
        logger.error(f"Telegram webhook connection error: {req_err}")
        return False, None, f"Network error connecting to Telegram: {str(req_err)}"
    except Exception as e:
        logger.error(f"Failed to set Telegram webhook: {e}")
        return False, None, str(e)


@router.get("/")
async def list_settings(ctx: dict = Depends(require_settings_read)):
    tenant_id = ctx["tenant_id"]
    db = get_supabase()
    result = db.table("app_settings").select("*").eq("tenant_id", tenant_id).order("key").execute()
    rows = result.data or []
    settings = []
    for row in rows:
        db_value = row["value"]
        effective_value = db_value
        is_set = effective_value is not None
        source = "db" if db_value else None
        if row["is_secret"] and is_set and effective_value:
            v = str(effective_value)
            if len(v) > 12:
                display_value = f"{v[:4]}{'•' * 8}{v[-4:]}"
            else:
                display_value = "•" * len(v)
        else:
            display_value = effective_value or "Not set"
        settings.append({
            "key": row["key"],
            "display_value": display_value,
            "is_secret": row["is_secret"],
            "is_set": is_set,
            "source": source,
            "updated_at": row["updated_at"],
        })
    return {"settings": settings}


@router.patch("/")
async def update_settings(
    payload: SettingsUpdate,
    ctx: dict = Depends(require_settings_manage),
    user: dict = Depends(get_current_user),
):
    tenant_id = ctx["tenant_id"]
    if not payload.updates:
        raise HTTPException(status_code=400, detail="Nothing to update")

    db = get_supabase()

    if "telegram_bot_token" in payload.updates:
        tg_token = payload.updates["telegram_bot_token"]
        if tg_token:
            tg_token = tg_token.strip()
            payload.updates["telegram_bot_token"] = tg_token
            # Validate token format locally — no outbound call (avoids Render proxy
            # timeout killing the response). Webhook registration is deferred to the
            # Activate button (same pattern as WhatsApp / Instagram / Facebook).
            if not re.fullmatch(r"\d+:[A-Za-z0-9_-]+", tg_token):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid Telegram bot token. Copy the full token from @BotFather — it looks like 123456789:AA... (you may have pasted only the part after the colon).",
                )
            # Clear the old webhook secret when the token changes so a stale
            # secret can't accidentally validate inbound updates for the new token.
            db.table("app_settings").delete() \
                .eq("tenant_id", tenant_id) \
                .eq("key", "telegram_webhook_secret") \
                .execute()
            db.table("app_settings").upsert({
                "tenant_id": tenant_id,
                "key": "telegram_status",
                "value": "configured",
                "is_secret": False,
                "updated_at": "now()",
            }, on_conflict="tenant_id,key").execute()
        else:
            # Token is cleared/empty. Scrub the webhook secret and status.
            db.table("app_settings").delete().eq("tenant_id", tenant_id).eq("key", "telegram_webhook_secret").execute()
            db.table("app_settings").delete().eq("tenant_id", tenant_id).eq("key", "telegram_status").execute()

    _SECRET_KEYS = {
        "meta_access_token",
        "meta_webhook_verify_token",
        "meta_app_secret",
        "telecmi_secret",
        "telecmi_agent_password",
        "telecmi_webhook_secret",
        "sarvam_api_key",
        "groq_api_key",
        "razorpay_key_secret",
        "razorpay_webhook_secret",
        "telegram_bot_token",
        "telegram_webhook_secret",
        "instagram_access_token",
        "instagram_app_secret",
        "facebook_access_token",
    }
    updated = []
    for key, value in payload.updates.items():
        is_secret = key in _SECRET_KEYS
        result = (
            db.table("app_settings")
            .upsert({
                "tenant_id": tenant_id,
                "key": key,
                "value": value,
                "is_secret": is_secret,
                "updated_at": "now()",
            }, on_conflict="tenant_id,key")
            .execute()
        )
        if result.data:
            updated.append(key)

    # Reset status of the channel to "configured" if credentials are changed
    wa_keys = {"meta_access_token", "meta_phone_number_id", "meta_waba_id", "meta_app_secret", "meta_webhook_verify_token"}
    ig_keys = {"instagram_access_token", "instagram_page_id", "instagram_app_secret"}
    fb_keys = {"facebook_access_token", "facebook_page_id"}

    reset_wa = any(k in updated for k in wa_keys)
    reset_ig = any(k in updated for k in ig_keys)
    reset_fb = any(k in updated for k in fb_keys)

    if reset_wa:
        db.table("app_settings").upsert({
            "tenant_id": tenant_id,
            "key": "whatsapp_status",
            "value": "configured",
            "is_secret": False,
            "updated_at": "now()",
        }, on_conflict="tenant_id,key").execute()
    if reset_ig:
        db.table("app_settings").upsert({
            "tenant_id": tenant_id,
            "key": "instagram_status",
            "value": "configured",
            "is_secret": False,
            "updated_at": "now()",
        }, on_conflict="tenant_id,key").execute()
    if reset_fb:
        db.table("app_settings").upsert({
            "tenant_id": tenant_id,
            "key": "facebook_status",
            "value": "configured",
            "is_secret": False,
            "updated_at": "now()",
        }, on_conflict="tenant_id,key").execute()

    from app.config_dynamic import invalidate_cache
    invalidate_cache()
    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=user.get("user_id"),
        actor_role="tenant_user",
        action="settings.updated",
        target_type="app_settings",
        target_id=tenant_id,
        metadata={
            "updated_keys": updated,
            "secret_keys": [key for key in updated if key in _SECRET_KEYS],
        },
    )
    return {"updated": updated}


@router.get("/webhook-health")
async def webhook_health(ctx: dict = Depends(require_settings_read)):
    tenant_id = ctx["tenant_id"]
    """Return last inbound event timestamp per channel + recent token_invalid incidents."""
    from datetime import datetime, timezone, timedelta
    db = get_supabase()
    health: dict = {}

    for channel in ("whatsapp", "instagram", "facebook", "telegram"):
        row = (
            db.table("messages")
            .select("created_at")
            .eq("tenant_id", tenant_id)
            .eq("channel", channel)
            .eq("direction", "inbound")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        last_at = row.data[0]["created_at"] if row.data else None
        health[channel] = {"last_event": last_at}

    # Token alerts: any token_invalid incidents in last 48h
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    alerts = (
        db.table("incidents")
        .select("type,detail,created_at")
        .eq("tenant_id", tenant_id)
        .eq("type", "token_invalid")
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .execute()
    )
    token_alerts = []
    for inc in (alerts.data or []):
        detail = inc.get("detail") or {}
        token_alerts.append({
            "channel": detail.get("channel"),
            "error": detail.get("error"),
            "created_at": inc["created_at"],
        })

    return {"health": health, "token_alerts": token_alerts}


@router.post("/activate")
async def activate_channel(
    payload: ActivateChannelRequest,
    ctx: dict = Depends(require_settings_manage),
    user: dict = Depends(get_current_user),
):
    tenant_id = ctx["tenant_id"]
    """Validate Meta credentials and auto-subscribe webhook for whatsapp / instagram / facebook."""
    channel = payload.channel
    if channel not in ("whatsapp", "instagram", "facebook", "telegram"):
        raise HTTPException(status_code=400, detail="Invalid channel. Must be whatsapp, instagram, facebook, or telegram.")

    db = get_supabase()

    if channel == "telegram":
        token = _get_setting_value(db, tenant_id, "telegram_bot_token")
        if not token:
            raise HTTPException(status_code=400, detail="Save your Telegram bot token first.")

        # Re-register the webhook (refreshes the secret) without forcing the user to re-paste the token.
        success, secret_token, err_msg = await setup_telegram_webhook(token, tenant_id)
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Telegram rejected this bot token. Error details: {err_msg or 'Unknown error'}. Re-copy the full token from @BotFather and try again.",
            )
        if secret_token:
            db.table("app_settings").upsert({
                "tenant_id": tenant_id,
                "key": "telegram_webhook_secret",
                "value": secret_token,
                "is_secret": True,
                "updated_at": "now()",
            }, on_conflict="tenant_id,key").execute()

        # Confirm the bot identity to show the user which bot is connected.
        bot_name = None
        bot_id = None
        try:
            async with httpx.AsyncClient() as client:
                me_r = await client.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10.0)
            me = me_r.json()
            if me.get("ok"):
                result = me.get("result", {})
                username = result.get("username")
                bot_name = f"@{username}" if username else result.get("first_name")
                bot_id = str(result.get("id")) if result.get("id") is not None else None
        except Exception as me_err:
            logger.warning(f"Telegram getMe failed for tenant {tenant_id}: {me_err}")

        db.table("app_settings").upsert({
            "tenant_id": tenant_id,
            "key": "telegram_status",
            "value": "live",
            "is_secret": False,
            "updated_at": "now()",
        }, on_conflict="tenant_id,key").execute()

        from app.config_dynamic import invalidate_cache
        invalidate_cache()
        record_audit_event(
            db,
            tenant_id=tenant_id,
            actor_user_id=user.get("user_id"),
            actor_role="tenant_user",
            action="settings.channel_activated",
            target_type="channel",
            target_id="telegram",
            metadata={"channel": "telegram", "subscribed": True},
        )
        return {
            "channel": "telegram",
            "page_name": bot_name,
            "page_id": bot_id,
            "subscribed": True,
        }

    if channel == "whatsapp":
        token = _get_setting_value(db, tenant_id, "meta_access_token")
        phone_id = _get_setting_value(db, tenant_id, "meta_phone_number_id")
        waba_id = _get_setting_value(db, tenant_id, "meta_waba_id")
        if not token or not phone_id:
            raise HTTPException(status_code=400, detail="Save meta_access_token and meta_phone_number_id first.")

        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://graph.facebook.com/v21.0/{phone_id}",
                params={"fields": "display_phone_number,verified_name", "access_token": token},
                timeout=10.0,
            )
        data = r.json()
        if "error" in data:
            raise HTTPException(status_code=400, detail=data["error"].get("message", "Invalid credentials"))

        subscribed = False
        if waba_id:
            async with httpx.AsyncClient() as client:
                sub_r = await client.post(
                    f"https://graph.facebook.com/v21.0/{waba_id}/subscribed_apps",
                    params={"access_token": token},
                    timeout=10.0,
                )
            sub_data = sub_r.json()
            subscribed = sub_data.get("success", False)
            if "error" in sub_data:
                logger.warning(f"WA subscribed_apps failed for tenant {tenant_id}: {sub_data['error']}")

        logger.info(f"WhatsApp activated tenant={tenant_id} phone={data.get('display_phone_number')} subscribed={subscribed}")
        
        # Upsert number into phone_numbers table
        try:
            display_phone = data.get("display_phone_number")
            if display_phone:
                db.table("phone_numbers").upsert({
                    "provider": "meta_cloud",
                    "number": display_phone.strip(),
                    "display_name": data.get("verified_name") or "WhatsApp Primary",
                    "meta_phone_number_id": phone_id,
                    "role": "primary",
                    "status": "active",
                    "warm_up_day": 14,
                    "paused_outbound": False,
                    "tenant_id": tenant_id,
                }, on_conflict="number").execute()
                logger.info(f"Automatically registered active primary number {display_phone} for tenant {tenant_id}")
        except Exception as phone_reg_err:
            logger.warning(f"Failed to auto-register phone number on activation: {phone_reg_err}")

        # Save activation status to app_settings
        db.table("app_settings").upsert({
            "tenant_id": tenant_id,
            "key": "whatsapp_status",
            "value": "live",
            "is_secret": False,
            "updated_at": "now()",
        }, on_conflict="tenant_id,key").execute()

        record_audit_event(
            db,
            tenant_id=tenant_id,
            actor_user_id=user.get("user_id"),
            actor_role="tenant_user",
            action="settings.channel_activated",
            target_type="channel",
            target_id="whatsapp",
            metadata={"channel": "whatsapp", "subscribed": subscribed},
        )
        return {
            "channel": "whatsapp",
            "phone_number": data.get("display_phone_number"),
            "business_name": data.get("verified_name"),
            "subscribed": subscribed,
        }

    # instagram or facebook
    token_key = f"{channel}_access_token"
    page_id_key = f"{channel}_page_id"
    token = _get_setting_value(db, tenant_id, token_key)
    page_id = _get_setting_value(db, tenant_id, page_id_key)
    if not token or not page_id:
        raise HTTPException(status_code=400, detail=f"Save {token_key} and {page_id_key} first.")

    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://graph.facebook.com/v21.0/me",
            params={"fields": "name,id", "access_token": token},
            timeout=10.0,
        )
    data = r.json()
    if "error" in data:
        raise HTTPException(status_code=400, detail=data["error"].get("message", "Invalid credentials"))

    sub_fields = "messages,messaging_postbacks,message_deliveries,message_reads"
    async with httpx.AsyncClient() as client:
        sub_r = await client.post(
            f"https://graph.facebook.com/v21.0/{page_id}/subscribed_apps",
            params={"subscribed_fields": sub_fields, "access_token": token},
            timeout=10.0,
        )
    sub_data = sub_r.json()
    subscribed = sub_data.get("success", False)
    if "error" in sub_data:
        logger.warning(f"{channel} subscribed_apps failed tenant={tenant_id}: {sub_data['error']}")

    # Save activation status to app_settings
    db.table("app_settings").upsert({
        "tenant_id": tenant_id,
        "key": f"{channel}_status",
        "value": "live",
        "is_secret": False,
        "updated_at": "now()",
    }, on_conflict="tenant_id,key").execute()

    logger.info(f"{channel} activated tenant={tenant_id} page={data.get('name')} subscribed={subscribed}")
    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=user.get("user_id"),
        actor_role="tenant_user",
        action="settings.channel_activated",
        target_type="channel",
        target_id=channel,
        metadata={"channel": channel, "subscribed": subscribed, "page_id": page_id},
    )
    return {
        "channel": channel,
        "page_name": data.get("name"),
        "page_id": data.get("id"),
        "subscribed": subscribed,
    }


@router.post("/whatsapp/embedded-signup")
async def whatsapp_embedded_signup(
    payload: EmbeddedSignupRequest,
    ctx: dict = Depends(require_settings_manage),
    user: dict = Depends(get_current_user),
):
    """Finish WhatsApp Embedded Signup: exchange the popup's code for a token,
    register the phone number, subscribe the webhook, and save credentials —
    the automated replacement for manually pasting them in below."""
    from app.services.meta_cloud import exchange_embedded_signup_code, register_phone_number

    tenant_id = ctx["tenant_id"]
    db = get_supabase()

    exchange = await exchange_embedded_signup_code(payload.code)
    access_token = exchange["access_token"]

    pin = "".join(secrets.choice("0123456789") for _ in range(6))
    reg_result = await register_phone_number(payload.phone_number_id, access_token, pin)
    if "error" in reg_result:
        logger.warning(f"Embedded Signup: phone registration failed tenant={tenant_id}: {reg_result['error']}")

    async with httpx.AsyncClient() as client:
        sub_r = await client.post(
            f"https://graph.facebook.com/v21.0/{payload.waba_id}/subscribed_apps",
            params={"access_token": access_token},
            timeout=10.0,
        )
    sub_data = sub_r.json()
    subscribed = sub_data.get("success", False)
    if "error" in sub_data:
        logger.warning(f"Embedded Signup: subscribed_apps failed tenant={tenant_id}: {sub_data['error']}")

    async with httpx.AsyncClient() as client:
        info_r = await client.get(
            f"https://graph.facebook.com/v21.0/{payload.phone_number_id}",
            params={"fields": "display_phone_number,verified_name", "access_token": access_token},
            timeout=10.0,
        )
    info_data = info_r.json()
    display_phone = info_data.get("display_phone_number")

    creds_to_save = {
        "meta_access_token": access_token,
        "meta_phone_number_id": payload.phone_number_id,
        "meta_waba_id": payload.waba_id,
        # Same Meta app for every tenant — save it here too so this tenant's inbound
        # webhook signature verification (which reads meta_app_secret per-tenant) works
        # immediately, without anyone manually pasting it in.
        "meta_app_secret": env_settings.meta_app_secret,
    }
    for key, value in creds_to_save.items():
        if not value:
            continue
        db.table("app_settings").upsert({
            "tenant_id": tenant_id,
            "key": key,
            "value": value,
            "is_secret": key in {"meta_access_token", "meta_app_secret"},
            "updated_at": "now()",
        }, on_conflict="tenant_id,key").execute()

    db.table("app_settings").upsert({
        "tenant_id": tenant_id,
        "key": "whatsapp_status",
        "value": "live",
        "is_secret": False,
        "updated_at": "now()",
    }, on_conflict="tenant_id,key").execute()

    if display_phone:
        db.table("phone_numbers").upsert({
            "provider": "meta_cloud",
            "number": display_phone.strip(),
            "display_name": info_data.get("verified_name") or "WhatsApp Primary",
            "meta_phone_number_id": payload.phone_number_id,
            "role": "primary",
            "status": "active",
            "warm_up_day": 14,
            "paused_outbound": False,
            "tenant_id": tenant_id,
        }, on_conflict="number").execute()

    from app.config_dynamic import invalidate_cache
    invalidate_cache()

    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=user.get("user_id"),
        actor_role="tenant_user",
        action="settings.whatsapp_embedded_signup_connected",
        target_type="channel",
        target_id="whatsapp",
        metadata={"channel": "whatsapp", "waba_id": payload.waba_id, "subscribed": subscribed},
    )

    return {
        "success": True,
        "phone_number": display_phone,
        "business_name": info_data.get("verified_name"),
        "subscribed": subscribed,
    }


@router.post("/facebook/embedded-signup")
async def facebook_embedded_signup(
    payload: FacebookEmbeddedSignupRequest,
    ctx: dict = Depends(require_settings_manage),
    user: dict = Depends(get_current_user),
):
    """Finish Facebook Login for Business signup for Messenger + linked Instagram:
    exchange the popup's code for a user token, find the granted Page, subscribe it
    to webhooks, and save Page/Instagram credentials — the automated replacement for
    manually pasting facebook_access_token/page_id and instagram_access_token/page_id."""
    from app.services.meta_cloud import exchange_embedded_signup_code

    tenant_id = ctx["tenant_id"]
    db = get_supabase()

    exchange = await exchange_embedded_signup_code(payload.code)
    user_token = exchange["access_token"]

    async with httpx.AsyncClient() as client:
        pages_r = await client.get(
            "https://graph.facebook.com/v21.0/me/accounts",
            params={
                "fields": "id,name,access_token,instagram_business_account",
                "access_token": user_token,
            },
            timeout=10.0,
        )
    pages_data = pages_r.json()
    if "error" in pages_data:
        raise HTTPException(status_code=400, detail=pages_data["error"].get("message", "Could not list granted Facebook Pages"))
    pages = pages_data.get("data", [])
    if not pages:
        raise HTTPException(status_code=400, detail="No Facebook Page was granted — select a Page during signup.")

    # Only one Page/tenant is supported today — same single-asset shape as the WhatsApp flow.
    page = pages[0]
    if len(pages) > 1:
        logger.info(f"Facebook embedded signup: tenant={tenant_id} granted {len(pages)} pages, connecting first ({page.get('name')}) only")

    page_id = page["id"]
    page_token = page["access_token"]
    ig_account = page.get("instagram_business_account")

    sub_fields = "messages,messaging_postbacks,message_deliveries,message_reads"
    async with httpx.AsyncClient() as client:
        sub_r = await client.post(
            f"https://graph.facebook.com/v21.0/{page_id}/subscribed_apps",
            params={"subscribed_fields": sub_fields, "access_token": page_token},
            timeout=10.0,
        )
    sub_data = sub_r.json()
    subscribed = sub_data.get("success", False)
    if "error" in sub_data:
        logger.warning(f"Facebook embedded signup: subscribed_apps failed tenant={tenant_id}: {sub_data['error']}")

    connected_instagram = bool(ig_account and ig_account.get("id"))
    creds_to_save = {
        "facebook_access_token": page_token,
        "facebook_page_id": page_id,
    }
    if connected_instagram:
        # Page-linked Instagram messaging is authenticated with the same Page access
        # token (Meta's Messenger Platform for Instagram) — not a separate IG token.
        creds_to_save["instagram_access_token"] = page_token
        creds_to_save["instagram_page_id"] = ig_account["id"]

    for key, value in creds_to_save.items():
        if not value:
            continue
        db.table("app_settings").upsert({
            "tenant_id": tenant_id,
            "key": key,
            "value": value,
            "is_secret": key.endswith("_access_token"),
            "updated_at": "now()",
        }, on_conflict="tenant_id,key").execute()

    db.table("app_settings").upsert({
        "tenant_id": tenant_id,
        "key": "facebook_status",
        "value": "live",
        "is_secret": False,
        "updated_at": "now()",
    }, on_conflict="tenant_id,key").execute()
    if connected_instagram:
        db.table("app_settings").upsert({
            "tenant_id": tenant_id,
            "key": "instagram_status",
            "value": "live",
            "is_secret": False,
            "updated_at": "now()",
        }, on_conflict="tenant_id,key").execute()

    from app.config_dynamic import invalidate_cache
    invalidate_cache()

    logger.info(f"Facebook embedded signup: tenant={tenant_id} page={page.get('name')} instagram_connected={connected_instagram} subscribed={subscribed}")
    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=user.get("user_id"),
        actor_role="tenant_user",
        action="settings.facebook_embedded_signup_connected",
        target_type="channel",
        target_id="facebook",
        metadata={"channel": "facebook", "page_id": page_id, "subscribed": subscribed, "instagram_connected": connected_instagram},
    )

    return {
        "success": True,
        "page_name": page.get("name"),
        "page_id": page_id,
        "subscribed": subscribed,
        "instagram_connected": connected_instagram,
    }


@router.get("/inbox-config")
async def get_inbox_config_route(ctx: dict = Depends(require_settings_read)):
    tenant_id = ctx["tenant_id"]
    return get_inbox_config(tenant_id)


@router.patch("/inbox-config")
async def patch_inbox_config(payload: InboxConfigUpdate, ctx: dict = Depends(require_settings_manage)):
    tenant_id = ctx["tenant_id"]
    current = get_inbox_config(tenant_id)
    patch = payload.model_dump(exclude_none=True)
    valid_segs = {"A", "B", "C"}
    if "segments" in patch:
        bad = [s for s in patch["segments"] if s not in valid_segs]
        if bad:
            raise HTTPException(status_code=400, detail=f"Invalid segments: {bad}")
    valid_ch = {"whatsapp", "instagram", "facebook", "telegram"}
    if "channels" in patch:
        bad = [c for c in patch["channels"] if c not in valid_ch]
        if bad:
            raise HTTPException(status_code=400, detail=f"Invalid channels: {bad}")
    valid_tr = {"A", "B", "C", "D", "F"}
    if "triggers" in patch:
        bad = [t for t in patch["triggers"] if t not in valid_tr]
        if bad:
            raise HTTPException(status_code=400, detail=f"Invalid triggers: {bad}")
    merged = {**current, **patch}
    save_inbox_config(tenant_id, merged)
    return merged


@router.get("/telecalling-config")
async def get_telecalling_config_route(ctx: dict = Depends(require_settings_read)):
    tenant_id = ctx["tenant_id"]
    return get_telecalling_config(tenant_id)


@router.patch("/telecalling-config")
async def patch_telecalling_config(payload: TelecallingConfigUpdate, ctx: dict = Depends(require_settings_manage)):
    tenant_id = ctx["tenant_id"]
    current = get_telecalling_config(tenant_id)
    patch = payload.model_dump(exclude_none=True)
    valid_segs = {"A", "B", "C"}
    if "segments" in patch:
        bad = [s for s in patch["segments"] if s not in valid_segs]
        if bad:
            raise HTTPException(status_code=400, detail=f"Invalid segments: {bad}")
    valid_ch = {"whatsapp", "instagram", "facebook", "telegram"}
    if "channels" in patch:
        bad = [c for c in patch["channels"] if c not in valid_ch]
        if bad:
            raise HTTPException(status_code=400, detail=f"Invalid channels: {bad}")
    if "max_call_attempts" in patch:
        patch["max_call_attempts"] = max(1, min(int(patch["max_call_attempts"]), 20))
    if "assignment_mode" in patch:
        if patch["assignment_mode"] not in ("push", "pull"):
            raise HTTPException(status_code=400, detail="Invalid assignment mode")
    merged = {**current, **patch}
    save_telecalling_config(tenant_id, merged)
    return merged
