import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.config import settings as env_settings
from app.config_dynamic import get_setting, save_setting
from app.db.supabase import get_supabase
from app.dependencies.tenant import require_permission
from app.services.marketplace_leads import WELCOME_TEMPLATE_KEY, handle_enquiry, parse_enquiry

logger = logging.getLogger(__name__)

# Unauthenticated: IndiaMART and JustDial push one enquiry at a time to a
# URL the customer pastes into their own marketplace dashboard. Neither
# provider lets the customer add custom headers, only a URL, so the tenant
# is identified by an opaque token in the path itself -- the URL IS the
# credential, the same shape as a Stripe-style webhook secret path.
public_router = APIRouter()

# Authenticated: lets a tenant generate/view the URL to paste into their
# marketplace account.
router = APIRouter()
require_settings_manage = require_permission("settings.manage")
require_settings_view = require_permission("settings.view")

PROVIDERS = ("indiamart", "justdial")
_RENDER_BASE_URL = "https://aira-ai-5tfr.onrender.com"


def _unauthorized() -> JSONResponse:
    # Identical body whether the token doesn't exist or belongs to no
    # tenant -- a partner probing the URL can't tell the difference.
    return JSONResponse(status_code=401, content={"error": "Unauthorized", "code": "unauthorized"})


def _token_key(provider: str) -> str:
    return f"{provider}_ingest_token"


def _resolve_tenant_by_token(db, provider: str, ingest_token: str) -> str | None:
    result = (
        db.table("app_settings")
        .select("tenant_id")
        .eq("key", _token_key(provider))
        .eq("value", ingest_token)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]["tenant_id"]


def _base_url() -> str:
    base_url = get_setting("public_base_url") or env_settings.public_base_url or _RENDER_BASE_URL
    return base_url.rstrip("/")


@router.post("/{provider}/token")
def generate_ingest_token(provider: str, ctx: dict = Depends(require_settings_manage)):
    """(Re)generates this tenant's ingest URL for one marketplace. Rotating
    invalidates the old URL immediately -- the tenant must re-paste the new
    one into their IndiaMART/JustDial dashboard."""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")

    token = secrets.token_urlsafe(24)
    # save_setting() marks this token is_secret (it is in SECRET_SETTING_KEYS); that
    # column only controls masking on the general GET /api/v1/settings surface. The
    # generate-token/get-token pair below are this value's only read path, and
    # neither echoes it unmasked to anyone but the tenant that generated it.
    save_setting(_token_key(provider), token, tenant_id=ctx["tenant_id"])
    return {"ingest_url": f"{_base_url()}/api/v1/marketplace/{provider}/{token}"}


@router.get("/{provider}/token")
def get_ingest_token(provider: str, ctx: dict = Depends(require_settings_manage)):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")

    token = get_setting(_token_key(provider), tenant_id=ctx["tenant_id"])
    if not token:
        return {"ingest_url": None}
    return {"ingest_url": f"{_base_url()}/api/v1/marketplace/{provider}/{token}"}


@router.get("/welcome-template")
def get_welcome_template(ctx: dict = Depends(require_settings_view)):
    return {"template_id": get_setting(WELCOME_TEMPLATE_KEY, tenant_id=ctx["tenant_id"]) or None}


@router.put("/welcome-template")
def set_welcome_template(payload: dict, ctx: dict = Depends(require_settings_manage)):
    """The approved template sent to every new marketplace enquiry. Only
    approved, text-only templates are accepted -- anything else would fail at
    send time, silently, for every lead."""
    template_id = (payload or {}).get("template_id") or ""
    db = get_supabase()
    if template_id:
        rows = (
            db.table("message_templates").select("status, header_media_type")
            .eq("id", template_id).eq("tenant_id", ctx["tenant_id"]).limit(1).execute()
        ).data or []
        if not rows:
            raise HTTPException(status_code=404, detail="Template not found")
        if (rows[0].get("status") or "").upper() != "APPROVED" or rows[0].get("header_media_type"):
            raise HTTPException(status_code=400, detail="Pick an approved template without an image or video header")
    db.table("app_settings").upsert(
        {"key": WELCOME_TEMPLATE_KEY, "value": template_id, "tenant_id": ctx["tenant_id"], "is_secret": False},
        on_conflict="tenant_id,key",
    ).execute()
    return {"template_id": template_id or None}


@router.get("/status")
def marketplace_status(ctx: dict = Depends(require_settings_view)):
    """Per provider: is a URL generated, when did the last enquiry arrive, and
    how many this month -- so the owner can see the connection is alive."""
    from datetime import datetime, timezone

    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    out = {}
    for provider in PROVIDERS:
        last = (
            db.table("leads").select("created_at").eq("tenant_id", tenant_id).eq("source", provider)
            .order("created_at", desc=True).limit(1).execute()
        ).data or []
        month = (
            db.table("leads").select("id").eq("tenant_id", tenant_id).eq("source", provider)
            .gte("created_at", month_start).limit(5000).execute()
        ).data or []
        out[provider] = {
            "connected": bool(get_setting(_token_key(provider), tenant_id=tenant_id)),
            "last_lead_at": last[0]["created_at"] if last else None,
            "leads_this_month": len(month),
        }
    return out


async def _read_payload(request: Request) -> dict:
    """JSON, form fields or query params -- JustDial's push format depends on
    how their team sets it up, so all three are accepted."""
    if request.method == "GET":
        return dict(request.query_params)
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        return {k: v for k, v in form.items() if isinstance(v, str)}
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Expected a JSON object")
    return payload


@public_router.api_route("/{provider}/{ingest_token}", methods=["GET", "POST"])
async def marketplace_webhook(provider: str, ingest_token: str, request: Request):
    if provider not in PROVIDERS:
        return _unauthorized()

    db = get_supabase()
    tenant_id = _resolve_tenant_by_token(db, provider, ingest_token)
    if not tenant_id:
        logger.warning(f"marketplace_intake: unknown {provider} ingest token")
        return _unauthorized()

    payload = await _read_payload(request)
    enquiry = parse_enquiry(provider, payload)
    result = await handle_enquiry(tenant_id, provider, enquiry, db=db)
    if result["status"] != "ok":
        logger.warning(f"marketplace_intake: {provider} enquiry ignored for tenant {tenant_id}: {result.get('detail')}")
    if provider == "justdial":
        # JustDial integrations conventionally expect this plain-text ack.
        return PlainTextResponse("RECEIVED")
    return result
