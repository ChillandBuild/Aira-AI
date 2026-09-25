"""The tenant's own business details (legal name, address, GSTIN) -- printed on
the monthly sales export so the file belongs to the client, not Aira."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.dependencies.tenant import require_permission
from app.services.business_details import GSTIN_RE, get_business_details, save_business_details

logger = logging.getLogger(__name__)
router = APIRouter()
require_settings_view = require_permission("settings.view")
require_settings_manage = require_permission("settings.manage")


class BusinessProfileIn(BaseModel):
    legal_name: str = Field("", max_length=200)
    address: str = Field("", max_length=400)
    city: str = Field("", max_length=100)
    state: str = Field("", max_length=100)
    pincode: str = Field("", max_length=12)
    gstin: str = Field("", max_length=15)
    email: str = Field("", max_length=200)
    phone: str = Field("", max_length=32)
    prices_include_gst: bool = True


@router.get("")
def read_profile(ctx: dict = Depends(require_settings_view)):
    return get_business_details(ctx["tenant_id"])


@router.put("")
def update_profile(payload: BusinessProfileIn, ctx: dict = Depends(require_settings_manage)):
    profile = {k: v.strip() if isinstance(v, str) else v for k, v in payload.model_dump().items()}
    profile["gstin"] = profile["gstin"].upper()
    if profile["gstin"] and not GSTIN_RE.match(profile["gstin"]):
        raise HTTPException(status_code=400, detail="GSTIN doesn't look right — it should be 15 characters like 33ABCDE1234F1Z5")
    try:
        return save_business_details(ctx["tenant_id"], profile)
    except Exception as e:
        logger.error(f"business_details save failed for tenant {ctx['tenant_id']}: {e}")
        raise HTTPException(status_code=500, detail="Couldn't save your business details — please try again")
