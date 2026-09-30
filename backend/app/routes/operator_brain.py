"""Aira Brain in the operator console (services/operator_brain*). System admins only,
read-only: nothing here changes a client's data."""
from fastapi import APIRouter, Depends, HTTPException

from app.db.supabase import get_supabase
from app.dependencies.system_admin import get_system_admin
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
