"""Anril Brain in the operator console (services/operator_brain*). System admins only,
read-only: nothing here changes a client's data."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.db.supabase import get_supabase
from app.dependencies.system_admin import get_system_admin
from app.services.brain.lead_context import LeadNotFound, build_what_aira_saw
from app.services.operator_brain import TenantNotFound, build_operator_brain
from app.services.operator_brain_fleet import fleet_waiting

router = APIRouter()


@router.get("/clients/{tenant_id}/brain")
def client_brain(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    try:
        return build_operator_brain(tenant_id)
    except TenantNotFound:
        raise HTTPException(status_code=404, detail="Tenant not found")


@router.get("/brain/waiting")
def brain_waiting(_admin: dict = Depends(get_system_admin)):
    return fleet_waiting(get_supabase())


@router.get("/clients/{tenant_id}/leads/{lead_id}/what-aira-saw")
async def what_aira_saw(
    tenant_id: str,
    lead_id: str,
    retrieval: bool = False,
    _admin: dict = Depends(get_system_admin),
):
    """Read-only reconstruction of what Anril would see for this lead now. retrieval=true
    adds the knowledge block, which costs one embedding call. Never calls a model.
    A malformed id or a lead of another tenant is a 404, like the sibling brain route."""
    try:
        tenant, lead = str(UUID(tenant_id)), str(UUID(lead_id))
        return await build_what_aira_saw(get_supabase(), tenant, lead, retrieval=retrieval)
    except (ValueError, LeadNotFound):
        raise HTTPException(status_code=404, detail="Lead not found")
