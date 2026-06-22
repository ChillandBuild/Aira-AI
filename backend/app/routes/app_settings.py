import logging
from typing import Literal
import secrets
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.db.supabase import get_supabase
from app.config import settings as env_settings
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_id, require_owner
from app.services.audit_log import record_audit_event
from app.services.assignment import (
    get_inbox_config, get_telecalling_config,
    save_inbox_config, save_telecalling_config,
    _INBOX_CONFIG_DEFAULT, _TELECALLING_CONFIG_DEFAULT,
)

logger = logging.getLogger(__name__)
router = APIRouter()

class SettingsUpdate(BaseModel):
    updates: dict[str, str | None]


class ActivateChannelRequest(BaseModel):
    channel: str  # whatsapp | instagram | facebook


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


async def setup_telegram_webhook(bot_token: str, tenant_id: str) -> tuple[bool, str | None]:
    """Register Telegram webhook + return generated secret (None if base_url missing)."""
    from app.config_dynamic import get_setting
    base_url = get_setting("public_base_url") or env_settings.public_base_url
    if not base_url:
        logger.warning("public_base_url not set — cannot register Telegram webhook")
        return True, None
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
            resp.raise_for_status()
            logger.info(f"Telegram webhook set to {webhook_url} for tenant {tenant_id}")
            return True, secret_token
    except Exception as e:
        logger.error(f"Failed to set Telegram webhook: {e}")
        return False, None


@router.get("/")
async def list_settings(ctx: dict = Depends(require_owner)):
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
    ctx: dict = Depends(require_owner),
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
            success, secret_token = await setup_telegram_webhook(tg_token, tenant_id)
            if not success:
                raise HTTPException(
                    status_code=400,
                    detail="Failed to set Telegram webhook. Please verify your Bot Token is correct."
                )
            if secret_token:
                # Persist webhook secret so the route can validate inbound updates
                existing = (
                    db.table("app_settings")
                    .select("id")
                    .eq("tenant_id", tenant_id)
                    .eq("key", "telegram_webhook_secret")
                    .maybe_single()
                    .execute()
                )
                if existing and existing.data:
                    db.table("app_settings").update(
                        {"value": secret_token, "updated_at": "now()"}
                    ).eq("tenant_id", tenant_id).eq("key", "telegram_webhook_secret").execute()
                else:
                    db.table("app_settings").insert({
                        "tenant_id": tenant_id,
                        "key": "telegram_webhook_secret",
                        "value": secret_token,
                        "is_secret": True,
                    }).execute()

    _SECRET_KEYS = {
        "meta_access_token",
        "meta_webhook_verify_token",
        "telecmi_secret",
        "groq_api_key",
        "razorpay_key_secret",
        "razorpay_webhook_secret",
        "telegram_webhook_secret",
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
            })
            .execute()
        )
        if result.data:
            updated.append(key)
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
async def webhook_health(ctx: dict = Depends(require_owner)):
    tenant_id = ctx["tenant_id"]
    """Return last inbound event timestamp per channel + recent token_invalid incidents."""
    from datetime import datetime, timezone, timedelta
    db = get_supabase()
    health: dict = {}

    for channel in ("whatsapp", "instagram", "facebook"):
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
    ctx: dict = Depends(require_owner),
    user: dict = Depends(get_current_user),
):
    tenant_id = ctx["tenant_id"]
    """Validate Meta credentials and auto-subscribe webhook for whatsapp / instagram / facebook."""
    channel = payload.channel
    if channel not in ("whatsapp", "instagram", "facebook"):
        raise HTTPException(status_code=400, detail="Invalid channel. Must be whatsapp, instagram, or facebook.")

    db = get_supabase()

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


@router.get("/inbox-config")
async def get_inbox_config_route(ctx: dict = Depends(require_owner)):
    tenant_id = ctx["tenant_id"]
    return get_inbox_config(tenant_id)


@router.patch("/inbox-config")
async def patch_inbox_config(payload: InboxConfigUpdate, ctx: dict = Depends(require_owner)):
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
    valid_tr = {"A", "B", "C", "D", "E", "F"}
    if "triggers" in patch:
        bad = [t for t in patch["triggers"] if t not in valid_tr]
        if bad:
            raise HTTPException(status_code=400, detail=f"Invalid triggers: {bad}")
    merged = {**current, **patch}
    save_inbox_config(tenant_id, merged)
    return merged


@router.get("/telecalling-config")
async def get_telecalling_config_route(ctx: dict = Depends(require_owner)):
    tenant_id = ctx["tenant_id"]
    return get_telecalling_config(tenant_id)


@router.patch("/telecalling-config")
async def patch_telecalling_config(payload: TelecallingConfigUpdate, ctx: dict = Depends(require_owner)):
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
