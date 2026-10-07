"""Private Send plug-in endpoints (license-key auth, no user session).

The client's server runs the Anril plug-in: it pulls a signed rule bundle from here and
reports send COUNTS back. No name or phone number ever reaches these routes: the usage
body rejects unknown fields, so a phone can't be smuggled in. Contract: sdk/spec/CONTRACT.md.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.supabase import get_supabase
from app.routes.auto_messages import _client_ip, _SlidingWindow
from app.services import private_send as svc

logger = logging.getLogger(__name__)

public_router = APIRouter()

BUNDLE_LIMIT_PER_MINUTE = 60
USAGE_LIMIT_PER_MINUTE = 30
IP_LIMIT_PER_MINUTE = 120
MAX_USAGE_ROWS = 500
MAX_USAGE_DAYS_BACK = 7
_NO_STORE = {"Cache-Control": "no-store"}

# slowapi in main.py is per IP only; the contract limits per license key.
_bundle_limiter = _SlidingWindow(BUNDLE_LIMIT_PER_MINUTE, 60)
_usage_limiter = _SlidingWindow(USAGE_LIMIT_PER_MINUTE, 60)
# Runs BEFORE the key lookup, so someone guessing keys can't hammer the database.
_ip_limiter = _SlidingWindow(IP_LIMIT_PER_MINUTE, 60)


class UsageRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: date
    event: str = Field(pattern="^(interested|signed_up|purchased)$")
    template_id: UUID
    sent: int = Field(ge=0, le=svc.MAX_DAILY_PER_TEMPLATE)
    failed: int = Field(ge=0, le=svc.MAX_DAILY_PER_TEMPLATE)

    @field_validator("day")
    @classmethod
    def _recent_day(cls, value: date) -> date:
        today = datetime.now(timezone.utc).date()
        if value > today or value < today - timedelta(days=MAX_USAGE_DAYS_BACK):
            raise ValueError("day must be within the last 7 days (UTC) and not in the future")
        return value


class UsageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[UsageRow] = Field(min_length=1, max_length=MAX_USAGE_ROWS)


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def _plugin_version(request: Request) -> str | None:
    """The plug-in's version header: X-Anril-Plugin, or X-Aira-Plugin from plug-ins already installed."""
    return request.headers.get("x-anril-plugin") or request.headers.get("x-aira-plugin")


def _error(e: svc.PrivateSendError) -> JSONResponse:
    return JSONResponse(status_code=e.status_code, content={"error": e.message, "code": e.code}, headers=_NO_STORE)


def _rate_limited() -> JSONResponse:
    return JSONResponse(
        status_code=429, content={"error": "Too many requests", "code": "rate_limited"},
        headers={**_NO_STORE, "Retry-After": "60"},
    )


@public_router.get("/bundle")
def get_bundle(request: Request):
    if not _ip_limiter.allow(_client_ip(request)):
        return _rate_limited()
    db = get_supabase()
    try:
        key = svc.find_key(db, _bearer(request))
        if not _bundle_limiter.allow(key["id"]):
            return _rate_limited()
        svc.authorize_key(db, key, _plugin_version(request))
        return JSONResponse(content=svc.signed_bundle(db, key["tenant_id"]), headers=_NO_STORE)
    except svc.PrivateSendError as e:
        return _error(e)


@public_router.post("/usage")
def post_usage(body: UsageIn, request: Request):
    if not _ip_limiter.allow(_client_ip(request)):
        return _rate_limited()
    db = get_supabase()
    try:
        key = svc.find_key(db, _bearer(request))
        if not _usage_limiter.allow(key["id"]):
            return _rate_limited()
        svc.authorize_key(db, key, _plugin_version(request))
        rows = [
            {
                "day": r.day.isoformat(), "event": r.event, "template_id": str(r.template_id),
                "sent": r.sent, "failed": r.failed,
            }
            for r in body.rows
        ]
        accepted = svc.record_usage(db, key["tenant_id"], rows)
    except svc.PrivateSendError as e:
        return _error(e)
    return JSONResponse(content={"ok": True, "accepted": accepted}, headers=_NO_STORE)
