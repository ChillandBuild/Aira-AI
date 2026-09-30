"""Test Aira: answers-only sandbox (services/brain_sandbox). Nothing is saved or sent.

Two mounts share one handler: the client route runs against the caller's own tenant
(knowledge.manage, because every call costs tokens); the operator route takes any
client's id and is system-admin only."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from app.db.supabase import get_supabase
from app.dependencies.system_admin import get_system_admin
from app.dependencies.tenant import require_permission
from app.services.brain_sandbox import MAX_MESSAGE_CHARS, MAX_TURNS, SandboxError, run_sandbox
from app.services.operator_brain import TenantNotFound, load_tenant

client_router = APIRouter()
operator_router = APIRouter()
require_manage = require_permission("knowledge.manage")


class SandboxTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=MAX_MESSAGE_CHARS)

    @field_validator("content")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message is empty")
        return value


class SandboxBody(BaseModel):
    messages: list[SandboxTurn] = Field(min_length=1, max_length=MAX_TURNS)

    @model_validator(mode="after")
    def _last_is_user(self) -> "SandboxBody":
        if self.messages[-1].role != "user":
            raise ValueError("the last message must be from the user")
        return self


async def _answer(tenant_id: str, body: SandboxBody, source: str) -> dict:
    messages = [turn.model_dump() for turn in body.messages]
    try:
        return await run_sandbox(tenant_id, messages, source=source)
    except SandboxError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None


@client_router.post("/sandbox")
async def client_sandbox(body: SandboxBody, ctx: dict = Depends(require_manage)):
    return await _answer(ctx["tenant_id"], body, "client")


@operator_router.post("/clients/{tenant_id}/brain/sandbox")
async def operator_sandbox(tenant_id: str, body: SandboxBody, _admin: dict = Depends(get_system_admin)):
    try:
        load_tenant(get_supabase(), tenant_id)
    except TenantNotFound:
        raise HTTPException(status_code=404, detail="Tenant not found") from None
    return await _answer(tenant_id, body, "operator")
