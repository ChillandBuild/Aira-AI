import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import settings as env_settings
from app.config_dynamic import get_setting, save_setting
from app.db.supabase import get_supabase
from app.dependencies.tenant import require_permission
from app.services.inbound_lead import create_inbound_lead

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
    # save_setting() always writes is_secret=False; that column only controls
    # masking on the general PATCH/GET /api/v1/settings surface, which this
    # route never goes through. The generate-token/get-token pair below are
    # this value's only read path, and neither echoes it unmasked to anyone
    # but the tenant that generated it. _SECRET_KEYS in app_settings.py is
    # extended separately so the general settings screen masks it too, for
    # consistency, in case it's ever listed there.
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


@public_router.post("/{provider}/{ingest_token}")
async def marketplace_webhook(provider: str, ingest_token: str, request: Request):
    if provider not in PROVIDERS:
        return _unauthorized()

    db = get_supabase()
    tenant_id = _resolve_tenant_by_token(db, provider, ingest_token)
    if not tenant_id:
        logger.warning(f"marketplace_intake: unknown {provider} ingest token")
        return _unauthorized()

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    phone, name = _extract_contact(provider, payload)
    if not phone:
        logger.warning(f"marketplace_intake: no phone in {provider} payload for tenant {tenant_id}")
        return {"status": "ignored", "detail": "no phone in payload"}

    lead_id = create_inbound_lead(
        tenant_id,
        phone,
        provider,
        name=name,
        collected_data={"raw_payload": payload},
        opt_in_source=provider,
        db=db,
    )
    if not lead_id:
        return {"status": "ignored", "detail": "unusable phone"}

    return {"status": "ok", "lead_id": lead_id}


def _extract_contact(provider: str, payload: dict) -> tuple[str | None, str | None]:
    """Each provider's enquiry payload shape. Both are documented as flat
    JSON objects with the lead's mobile number and name as top-level keys;
    field names differ between the two."""
    if provider == "indiamart":
        phone = payload.get("SENDER_MOBILE") or payload.get("mobile")
        name = payload.get("SENDER_NAME") or payload.get("name")
        return phone, name
    if provider == "justdial":
        phone = payload.get("mobile") or payload.get("phone")
        name = payload.get("name")
        return phone, name
    return None, None
