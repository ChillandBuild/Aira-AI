import logging
import sys
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED
from app.dependencies.auth import get_current_user

import os
from app.config import settings
from app.routes import webhook, leads, messages, analytics, upload, segments, calls, callers, ai_tune, knowledge, system, follow_ups, numbers, incidents, lead_notes, voice_numbers, app_settings, templates, onboarding, team, media, todos, bookings, conversations, operator, chat_handovers, telegram, instagram, facebook, tags, inbound_leads, reengagement, notifications, assignment_log, call_scripts
from app.routes.calls import public_router as calls_public_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Initialize Sentry
if settings.sentry_dsn:
    import sentry_sdk
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=1.0,
    )
    logger.info("Sentry SDK initialized successfully.")

from datetime import datetime, timezone, timedelta
_startup_time = datetime.now(timezone.utc)
_heartbeats = {
    "scheduled-broadcasts": None,
}


async def _process_scheduled_broadcasts() -> None:
    """APScheduler job: fire scheduled_broadcasts rows whose fire_at has passed."""
    _heartbeats["scheduled-broadcasts"] = datetime.now(timezone.utc)
    try:
        from app.db.supabase import get_supabase
        from app.services.broadcast_executor import execute_broadcast
        db = get_supabase()
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        rows = (
            db.table("scheduled_broadcasts")
            .select("*")
            .eq("status", "pending")
            .lte("fire_at", now)
            .limit(10)
            .execute()
        )
        for row in (rows.data or []):
            logger.info(f"Scheduled broadcast firing: id={row['id']} tenant={row['tenant_id']}")
            await execute_broadcast(row)
    except Exception as e:
        logger.error(f"Scheduled broadcast executor error: {e}")


async def _process_broadcast_retries() -> None:
    """APScheduler job: advance broadcast auto-retry chains that are due."""
    _heartbeats["broadcast-retries"] = datetime.now(timezone.utc)
    try:
        from app.services.broadcast_retry import process_due_retries
        process_due_retries()
    except Exception as e:
        logger.error(f"Broadcast retry orchestrator error: {e}")


async def _check_token_health() -> None:
    """APScheduler daily job: validate Meta tokens for all tenants, create incidents if invalid."""
    import httpx
    from app.db.supabase import get_supabase

    db = get_supabase()
    rows = (
        db.table("app_settings")
        .select("tenant_id,key,value")
        .in_("key", [
            "meta_access_token", "meta_phone_number_id",
            "instagram_access_token", "instagram_page_id",
            "facebook_access_token", "facebook_page_id",
        ])
        .not_.is_("value", "null")
        .execute()
    )
    if not rows.data:
        return

    tenant_cfg: dict[str, dict] = {}
    for row in rows.data:
        tid = row["tenant_id"]
        if tid not in tenant_cfg:
            tenant_cfg[tid] = {}
        tenant_cfg[tid][row["key"]] = row["value"]

    async with httpx.AsyncClient(timeout=10.0) as client:
        for tenant_id, cfg in tenant_cfg.items():
            # WhatsApp
            wa_token = cfg.get("meta_access_token")
            wa_phone_id = cfg.get("meta_phone_number_id")
            if wa_token and wa_phone_id:
                try:
                    r = await client.get(
                        f"https://graph.facebook.com/v21.0/{wa_phone_id}",
                        params={"fields": "display_phone_number", "access_token": wa_token},
                    )
                    data = r.json()
                    if "error" in data:
                        _create_token_incident(db, tenant_id, "whatsapp", data["error"].get("message", "Token invalid"))
                except Exception as e:
                    logger.warning(f"Token health check error tenant={tenant_id} channel=whatsapp: {e}")

            # Instagram
            ig_token = cfg.get("instagram_access_token")
            if ig_token:
                try:
                    r = await client.get(
                        "https://graph.facebook.com/v21.0/me",
                        params={"fields": "name", "access_token": ig_token},
                    )
                    data = r.json()
                    if "error" in data:
                        _create_token_incident(db, tenant_id, "instagram", data["error"].get("message", "Token invalid"))
                except Exception as e:
                    logger.warning(f"Token health check error tenant={tenant_id} channel=instagram: {e}")

            # Facebook
            fb_token = cfg.get("facebook_access_token")
            if fb_token:
                try:
                    r = await client.get(
                        "https://graph.facebook.com/v21.0/me",
                        params={"fields": "name", "access_token": fb_token},
                    )
                    data = r.json()
                    if "error" in data:
                        _create_token_incident(db, tenant_id, "facebook", data["error"].get("message", "Token invalid"))
                except Exception as e:
                    logger.warning(f"Token health check error tenant={tenant_id} channel=facebook: {e}")

    logger.info(f"Token health check complete for {len(tenant_cfg)} tenant(s)")


async def _apply_engagement_decay() -> None:
    """APScheduler 6h job: decay scores for leads silent >24h."""
    try:
        from app.db.supabase import get_supabase
        from app.services.scoring_engine import apply_engagement_decay_all
        db = get_supabase()
        count = await apply_engagement_decay_all(db)
        if count:
            logger.info(f"Engagement decay: updated {count} lead(s)")
    except Exception as e:
        logger.error(f"Engagement decay scheduler error: {e}")


def _create_token_incident(db, tenant_id: str, channel: str, error_msg: str) -> None:
    try:
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=23)).isoformat()
        existing = (
            db.table("incidents")
            .select("id")
            .eq("tenant_id", tenant_id)
            .eq("type", "token_invalid")
            .gte("created_at", cutoff)
            .execute()
        )
        if existing.data:
            return
        db.table("incidents").insert({
            "tenant_id": tenant_id,
            "type": "token_invalid",
            "detail": {"channel": channel, "error": error_msg},
        }).execute()
        logger.warning(f"Token invalid incident created: tenant={tenant_id} channel={channel}")
    except Exception as e:
        logger.error(f"Failed to create token incident: {e}")


async def _process_reengagement_rules() -> None:
    """APScheduler job: process due automated re-engagement steps."""
    try:
        from app.services.reengagement_service import process_due_reengagements
        count = await process_due_reengagements()
        if count:
            logger.info(f"Re-engagement scheduler: processed {count} re-engagement message(s)")
    except Exception as e:
        logger.error(f"Re-engagement scheduler error: {e}")


async def _sweep_unassigned_leads() -> None:
    """APScheduler job: state-based safety net that assigns any unassigned lead
    whose current segment qualifies under the tenant's telecalling_config."""
    try:
        from app.services.assignment import sweep_unassigned_leads
        sweep_unassigned_leads()
    except Exception as e:
        logger.error(f"Assignment sweep scheduler error: {e}")


_scheduler = AsyncIOScheduler()


def _record_scheduler_event(event) -> None:
    """Persist every job run to scheduler_runs for the operator Scheduler Health
    view. Best-effort: must never raise into the scheduler."""
    try:
        if event.code == EVENT_JOB_ERROR:
            status = "error"
            error = str(getattr(event, "exception", "") or "")[:2000]
        elif event.code == EVENT_JOB_MISSED:
            status, error = "missed", None
        else:
            status, error = "success", None
        scheduled = getattr(event, "scheduled_run_time", None)
        ran_at = datetime.now(timezone.utc)
        lateness_ms = int((ran_at - scheduled).total_seconds() * 1000) if scheduled else None
        from app.db.supabase import get_supabase
        get_supabase().table("scheduler_runs").insert({
            "job_id": event.job_id,
            "status": status,
            "scheduled_at": scheduled.isoformat() if scheduled else None,
            "ran_at": ran_at.isoformat(),
            "lateness_ms": lateness_ms,
            "error": error,
        }).execute()
    except Exception as e:
        logger.warning(f"scheduler_runs record failed (non-fatal): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Aira AI backend starting up...")
    logger.info(f"Supabase: {settings.supabase_url}")
    logger.info("Voice: TeleCMI")

    _scheduler.add_job(
        _process_scheduled_broadcasts,
        trigger="interval",
        minutes=1,
        id="scheduled-broadcasts",
        replace_existing=True,
    )
    _scheduler.add_job(
        _process_broadcast_retries,
        trigger="interval",
        minutes=5,
        id="broadcast-retries",
        replace_existing=True,
    )
    _scheduler.add_job(
        _check_token_health,
        trigger="interval",
        hours=24,
        id="token-health-check",
        replace_existing=True,
    )
    _scheduler.add_job(
        _apply_engagement_decay,
        trigger="interval",
        hours=6,
        id="engagement-decay",
        replace_existing=True,
    )
    _scheduler.add_job(
        _process_reengagement_rules,
        trigger="interval",
        minutes=1,
        id="reengagement-rules",
        replace_existing=True,
    )
    _scheduler.add_job(
        _sweep_unassigned_leads,
        trigger="interval",
        minutes=2,
        id="assignment-sweep",
        replace_existing=True,
    )
    _scheduler.add_listener(
        _record_scheduler_event,
        EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED,
    )
    _scheduler.start()
    logger.info("Schedulers started: broadcasts(1m) + broadcast-retries(5m) + token-health(24h) + engagement-decay(6h) + reengagement(1m) + assignment-sweep(2m)")

    yield

    _scheduler.shutdown(wait=False)
    logger.info("Aira AI backend shutting down.")


app = FastAPI(
    title="Aira AI",
    version="0.1.0",
    description="B2B SaaS Lead Intelligence Platform for Education Consultancies",
    lifespan=lifespan,
)

# CORS — allow frontend origins
_allowed = ["http://localhost:3000", "http://localhost:3001"]
_frontend_url = os.environ.get("FRONTEND_URL", "")
if _frontend_url:
    _allowed.append(_frontend_url)
# Allow all *.vercel.app subdomains for preview deployments
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check (no auth, no prefix)
@app.get("/health", tags=["system"])
async def health():
    from fastapi.responses import JSONResponse
    from datetime import datetime, timezone
    
    # 1. Ping the Supabase database
    db_ok = False
    db_error = None
    try:
        from app.db.supabase import get_supabase
        db = get_supabase()
        db.table("app_settings").select("key").limit(1).execute()
        db_ok = True
    except Exception as e:
        db_error = str(e)
        logger.error(f"Health check database ping failed: {db_error}")

    # 2. Check scheduled jobs heartbeats
    now = datetime.now(timezone.utc)
    
    # scheduled-broadcasts (runs every 1 minute)
    sb_heartbeat = _heartbeats["scheduled-broadcasts"]
    sb_ok = False
    if sb_heartbeat is not None:
        if (now - sb_heartbeat).total_seconds() <= 180: # 3 minutes threshold
            sb_ok = True
    else:
        # Grace period since startup
        if (now - _startup_time).total_seconds() <= 180:
            sb_ok = True

    details = {
        "database": "ok" if db_ok else f"error: {db_error}",
        "scheduler_jobs": {
            "scheduled-broadcasts": {
                "status": "healthy" if sb_ok else "unhealthy",
                "last_heartbeat": sb_heartbeat.isoformat() if sb_heartbeat else None,
            }
        }
    }

    if db_ok and sb_ok:
        return {
            "status": "healthy",
            "service": "aira-ai",
            "details": details
        }
    else:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "aira-ai",
                "details": details
            }
        )

@app.get("/sentry-debug")
async def trigger_error():
    division_by_zero = 1 / 0

_auth = [Depends(get_current_user)]

# Webhook routes — no auth (Meta calls directly)
app.include_router(webhook.router, prefix="/webhook/whatsapp", tags=["webhook"])
app.include_router(telegram.router, prefix="/webhook/telegram", tags=["telegram-webhook"])
app.include_router(instagram.router, prefix="/webhook/instagram", tags=["instagram-webhook"])
app.include_router(facebook.router, prefix="/webhook/facebook", tags=["facebook-webhook"])
app.include_router(calls_public_router, prefix="/api/v1/calls", tags=["calls-telecmi"])
app.include_router(bookings.public_router, prefix="/api/v1/bookings", tags=["bookings-webhook"])

# API routes — all require auth
app.include_router(leads.router, prefix="/api/v1/leads", tags=["leads"], dependencies=_auth)
app.include_router(messages.router, prefix="/api/v1/messages", tags=["messages"], dependencies=_auth)
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"], dependencies=_auth)
app.include_router(upload.router, prefix="/api/v1/upload", tags=["upload"], dependencies=_auth)
app.include_router(segments.router, prefix="/api/v1/segments", tags=["segments"], dependencies=_auth)
app.include_router(calls.router, prefix="/api/v1/calls", tags=["calls"], dependencies=_auth)
app.include_router(callers.router, prefix="/api/v1/callers", tags=["callers"], dependencies=_auth)
app.include_router(ai_tune.router, prefix="/api/v1/ai-tune", tags=["ai-tune"], dependencies=_auth)
app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["knowledge"], dependencies=_auth)
app.include_router(system.router, prefix="/api/v1/system", tags=["system"], dependencies=_auth)
app.include_router(follow_ups.router, prefix="/api/v1/follow-ups", tags=["follow-ups"], dependencies=_auth)
app.include_router(numbers.router, prefix="/api/v1/numbers", tags=["numbers"], dependencies=_auth)
app.include_router(incidents.router, prefix="/api/v1/incidents", tags=["incidents"], dependencies=_auth)
app.include_router(lead_notes.router, prefix="/api/v1/lead-notes", tags=["lead-notes"], dependencies=_auth)
app.include_router(voice_numbers.router, prefix="/api/v1/voice-numbers", tags=["voice-numbers"], dependencies=_auth)
app.include_router(app_settings.router, prefix="/api/v1/settings", tags=["settings"], dependencies=_auth)
app.include_router(templates.public_router, prefix="/api/v1/templates", tags=["templates-webhook"])
app.include_router(templates.router, prefix="/api/v1/templates", tags=["templates"], dependencies=_auth)
app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["onboarding"], dependencies=_auth)
app.include_router(team.router, prefix="/api/v1/team", tags=["team"], dependencies=_auth)
app.include_router(media.router, prefix="/api/v1/leads", tags=["media"], dependencies=_auth)
app.include_router(todos.router, prefix="/api/v1/todos", tags=["todos"], dependencies=_auth)
app.include_router(bookings.router, prefix="/api/v1/bookings", tags=["bookings"], dependencies=_auth)
app.include_router(conversations.router, prefix="/api/v1/conversations", tags=["conversations"], dependencies=_auth)
app.include_router(operator.router, prefix="/api/v1/operator", tags=["operator"])
app.include_router(chat_handovers.router, prefix="/api/v1/chat-handovers", tags=["chat-handovers"], dependencies=_auth)
app.include_router(tags.router, prefix="/api/v1/broadcast-tags", tags=["broadcast-tags"], dependencies=_auth)
app.include_router(inbound_leads.router, prefix="/api/v1/inbound-leads", tags=["inbound-leads"], dependencies=_auth)
app.include_router(reengagement.router, prefix="/api/v1/reengagement", tags=["reengagement"], dependencies=_auth)
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["notifications"], dependencies=_auth)
app.include_router(assignment_log.router, prefix="/api/v1/assignment-log", tags=["assignment-log"], dependencies=_auth)
app.include_router(call_scripts.router, prefix="/api/v1/call-scripts", tags=["call-scripts"], dependencies=_auth)


