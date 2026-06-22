import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, get_tenant_and_role, require_owner, get_owner_tenant_id
from app.services.assignment import (
    is_round_robin_enabled,
    set_round_robin_enabled,
    reassign_backlog,
    get_telecalling_config,
    save_telecalling_config,
)
from app.services.call_coach import coaching_tip
from app.services.call_scorer import MIN_MONTHLY_CALLS

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateCaller(BaseModel):
    name: str
    phone: str


class UpdateCaller(BaseModel):
    name: str | None = None
    phone: str | None = None
    telecmi_agent_id: str | None = None
    shift_start_hour: int | None = None
    shift_end_hour: int | None = None


class RoundRobinToggle(BaseModel):
    enabled: bool


class StatusToggle(BaseModel):
    status: str  # "active" | "break" | "logged_out"


# ── Round-robin toggle ───────────────────────────────────────────────────────


@router.get("/round-robin")
async def get_round_robin(tenant_id: str = Depends(get_tenant_id)):
    """Return whether auto round-robin assignment is currently enabled."""
    return {"enabled": is_round_robin_enabled(tenant_id)}


@router.patch("/round-robin")
async def toggle_round_robin(payload: RoundRobinToggle, tenant_id: str = Depends(get_owner_tenant_id)):
    """Enable or disable automatic round-robin lead assignment for new inbound leads."""
    set_round_robin_enabled(tenant_id, payload.enabled)
    return {"enabled": payload.enabled}



# ── Caller status (idle/active) ──────────────────────────────────────────────


@router.patch("/my-status")
async def update_my_status(payload: StatusToggle, ctx: dict = Depends(get_tenant_and_role)):
    """Caller toggles their own status."""
    if payload.status not in ("active", "break", "logged_out"):
        raise HTTPException(status_code=400, detail="Status must be 'active', 'break', or 'logged_out'")

    caller_id = ctx.get("caller_id")
    if not caller_id:
        raise HTTPException(status_code=403, detail="Only callers can toggle status")

    db = get_supabase()

    current = (
        db.table("callers")
        .select("status,status_changed_at")
        .eq("id", caller_id)
        .single()
        .execute()
    ).data

    if current and current["status"] == payload.status:
        return {"status": payload.status, "changed_at": current["status_changed_at"]}

    now = datetime.now(timezone.utc).isoformat()

    # Close the previous status log entry
    db.table("caller_status_logs").update(
        {"ended_at": now}
    ).eq("caller_id", caller_id).is_("ended_at", "null").execute()

    # Insert new status log entry
    insert_data = {
        "caller_id": caller_id,
        "tenant_id": ctx["tenant_id"],
        "status": payload.status,
        "started_at": now,
    }
    if payload.status == "logged_out":
        insert_data["ended_at"] = now
    db.table("caller_status_logs").insert(insert_data).execute()

    # Update caller record
    db.table("callers").update({
        "status": payload.status,
        "status_changed_at": now,
    }).eq("id", caller_id).execute()

    if payload.status == "active":
        reassign_backlog(caller_id, ctx["tenant_id"])

    return {"status": payload.status, "changed_at": now}


@router.get("/my-status")
async def get_my_status(ctx: dict = Depends(get_tenant_and_role)):
    """Get the current caller's status."""
    caller_id = ctx.get("caller_id")
    if not caller_id:
        # For owners, return active always
        return {"status": "active", "caller_id": None}

    db = get_supabase()
    result = (
        db.table("callers")
        .select("id,status,status_changed_at")
        .eq("id", caller_id)
        .single()
        .execute()
    )
    return result.data


@router.get("/my-calls-today")
async def get_my_calls_today(ctx: dict = Depends(get_tenant_and_role)):
    caller_id = ctx.get("caller_id")
    if not caller_id:
        return {"data": []}

    db = get_supabase()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    result = (
        db.table("call_logs")
        .select("id,lead_id,call_sid,duration_seconds,outcome,recording_url,score,status,ai_summary,transcript,created_at,leads(phone,name)")
        .eq("caller_id", caller_id)
        .eq("tenant_id", ctx["tenant_id"])
        .gte("created_at", today_start)
        .order("created_at", desc=True)
        .execute()
    )
    return {"data": result.data or []}


@router.get("/my-performance")
async def get_my_performance(ctx: dict = Depends(get_tenant_and_role)):
    caller_id = ctx.get("caller_id")
    if not caller_id:
        return {"target": 0, "achieved": 0, "scripts": {}}

    db = get_supabase()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    # Fetch achieved calls count today
    achieved_res = (
        db.table("call_logs")
        .select("id", count="exact")
        .eq("caller_id", caller_id)
        .eq("tenant_id", ctx["tenant_id"])
        .gte("created_at", today_start)
        .execute()
    )
    achieved = achieved_res.count or 0

    # Fetch target and scripts from config
    cfg = get_telecalling_config(ctx["tenant_id"])

    targets = cfg.get("targets") or {}
    target = targets.get(str(caller_id)) or targets.get(caller_id) or targets.get("daily_calls", 50)

    scripts = cfg.get("scripts") or {}

    return {
        "achieved": achieved,
        "target": target,
        "scripts": scripts,
    }


# ── Caller stats (for profile page) ──────────────────────────────────────────


@router.get("/my-stats")
async def get_my_stats(ctx: dict = Depends(get_tenant_and_role)):
    """Return the current caller's performance stats."""
    caller_id = ctx.get("caller_id")
    if not caller_id:
        raise HTTPException(status_code=403, detail="Only callers can view their stats")

    db = get_supabase()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_start = (now - timedelta(days=7)).isoformat()

    # Calls today
    calls_today_res = (
        db.table("call_logs")
        .select("id", count="exact")
        .eq("caller_id", caller_id)
        .eq("tenant_id", ctx["tenant_id"])
        .gte("created_at", today_start)
        .execute()
    )

    # Calls this week
    calls_week_res = (
        db.table("call_logs")
        .select("id,outcome,duration_seconds", count="exact")
        .eq("caller_id", caller_id)
        .eq("tenant_id", ctx["tenant_id"])
        .gte("created_at", week_start)
        .execute()
    )
    week_logs = calls_week_res.data or []
    total_week = calls_week_res.count or 0
    converted_week = sum(1 for l in week_logs if l.get("outcome") == "converted")
    durations = [l["duration_seconds"] for l in week_logs if l.get("duration_seconds")]
    avg_duration = round(sum(durations) / len(durations)) if durations else None

    # Pending hot leads assigned to this caller
    pending_hot_res = (
        db.table("leads")
        .select("id", count="exact")
        .eq("assigned_to", caller_id)
        .eq("tenant_id", ctx["tenant_id"])
        .gte("score", 7)
        .is_("converted_at", "null")
        .execute()
    )

    # Overall score
    caller_res = (
        db.table("callers")
        .select("overall_score,name,phone,status")
        .eq("id", caller_id)
        .single()
        .execute()
    )

    return {
        "calls_today": calls_today_res.count or 0,
        "calls_this_week": total_week,
        "conversion_rate_week": round(converted_week / total_week, 2) if total_week > 0 else 0,
        "avg_duration_seconds": avg_duration,
        "pending_hot_leads": pending_hot_res.count or 0,
        "overall_score": float(caller_res.data.get("overall_score", 0)),
        "name": caller_res.data.get("name"),
        "phone": caller_res.data.get("phone"),
        "status": caller_res.data.get("status", "active"),
        "caller_id": caller_id,
    }


# ── Status summary (admin view) ──────────────────────────────────────────────


@router.get("/{caller_id}/status-summary")
async def get_status_summary(caller_id: UUID, tenant_id: str = Depends(get_owner_tenant_id)):
    """Admin views a caller's status breakdown for today."""
    db = get_supabase()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    logs = (
        db.table("caller_status_logs")
        .select("status,started_at,ended_at")
        .eq("caller_id", str(caller_id))
        .eq("tenant_id", tenant_id)
        .gte("started_at", today_start)
        .order("started_at")
        .execute()
    )

    active_minutes = 0
    break_minutes = 0
    idle_minutes = 0
    first_login_at = None
    last_logout_at = None
    breaks = []

    for log in (logs.data or []):
        start = datetime.fromisoformat(log["started_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(log["ended_at"].replace("Z", "+00:00")) if log["ended_at"] else now
        delta = (end - start).total_seconds() / 60

        if log["status"] == "active":
            active_minutes += delta
            if first_login_at is None:
                first_login_at = log["started_at"]
        elif log["status"] == "break":
            break_minutes += delta
            breaks.append({
                "started_at": log["started_at"],
                "ended_at": log["ended_at"],
                "duration_minutes": round(delta),
            })
        elif log["status"] == "logged_out":
            last_logout_at = log["started_at"]
        else:
            idle_minutes += delta

    # Current status
    caller = (
        db.table("callers")
        .select("status,status_changed_at")
        .eq("id", str(caller_id))
        .single()
        .execute()
    )

    # Scheduled callbacks count
    assigned_leads = (
        db.table("leads")
        .select("id")
        .eq("assigned_to", str(caller_id))
        .eq("tenant_id", tenant_id)
        .execute()
    )
    lead_ids = [l["id"] for l in (assigned_leads.data or [])]

    scheduled_count = 0
    if lead_ids:
        sched = (
            db.table("follow_up_jobs")
            .select("id", count="exact")
            .eq("cadence", "callback")
            .eq("status", "pending")
            .eq("tenant_id", tenant_id)
            .in_("lead_id", lead_ids)
            .execute()
        )
        scheduled_count = sched.count or 0

    return {
        "active_minutes_today": round(active_minutes),
        "break_minutes_today": round(break_minutes),
        "idle_minutes_today": round(idle_minutes),
        "current_status": caller.data.get("status", "active"),
        "since": caller.data.get("status_changed_at"),
        "first_login_at": first_login_at,
        "last_logout_at": last_logout_at,
        "breaks": breaks,
        "scheduled_count": scheduled_count,
    }



@router.get("/{caller_id}/timeline")
async def get_caller_timeline(
    caller_id: UUID,
    date: str = Query(None),
    tenant_id: str = Depends(get_owner_tenant_id)
):
    """Admin views a caller's exact timeline for a specific day."""
    db = get_supabase()
    
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
    try:
        day_start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(400, "Invalid date format, use YYYY-MM-DD")
        
    day_end = day_start + timedelta(days=1)
    
    status_logs = (
        db.table("caller_status_logs")
        .select("id,status,started_at,ended_at")
        .eq("caller_id", str(caller_id))
        .eq("tenant_id", tenant_id)
        .gte("started_at", day_start.isoformat())
        .lt("started_at", day_end.isoformat())
        .order("started_at")
        .execute()
    ).data or []
    
    calls = (
        db.table("call_logs")
        .select("id,created_at,duration_seconds,outcome,lead_id")
        .eq("caller_id", str(caller_id))
        .eq("tenant_id", tenant_id)
        .gte("created_at", day_start.isoformat())
        .lt("created_at", day_end.isoformat())
        .order("created_at")
        .execute()
    ).data or []
    
    lead_ids = list({c["lead_id"] for c in calls if c.get("lead_id")})
    lead_map = {}
    if lead_ids:
        leads = db.table("leads").select("id,name,phone").in_("id", lead_ids).execute().data or []
        lead_map = {l["id"]: l for l in leads}
        
    events = []
    
    for s in status_logs:
        events.append({
            "type": "status",
            "id": s["id"],
            "status": s["status"],
            "started_at": s["started_at"],
            "ended_at": s["ended_at"],
            "duration_seconds": None,
        })
        
    for c in calls:
        lead = lead_map.get(c["lead_id"], {})
        events.append({
            "type": "call",
            "id": c["id"],
            "started_at": c["created_at"],
            "duration_seconds": c.get("duration_seconds") or 0,
            "outcome": c.get("outcome"),
            "lead_name": lead.get("name") or "Unknown",
            "lead_phone": lead.get("phone") or "",
        })
        
    events.sort(key=lambda x: x["started_at"])
    
    return {"data": events}

# ── CRUD (existing) ──────────────────────────────────────────────────────────


@router.post("/")
async def create_caller(payload: CreateCaller, tenant_id: str = Depends(get_owner_tenant_id)):
    db = get_supabase()
    result = db.table("callers").insert({
        "name": payload.name.strip(),
        "phone": payload.phone.strip(),
        "active": True,
        "status": "active",
        "overall_score": 7.0,
        "tenant_id": tenant_id,
    }).execute()
    return result.data[0]


@router.get("/")
async def list_callers(tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    owner = db.table("tenant_users").select("user_id").eq("tenant_id", tenant_id).eq("role", "owner").maybe_single().execute()
    owner_user_id = (owner.data or {}).get("user_id")
    all_callers = db.table("callers").select("*").eq("tenant_id", tenant_id).eq("active", True).order("overall_score", desc=True).execute()
    rows = all_callers.data or []
    admin_caller = None
    team = []
    for c in rows:
        if owner_user_id and c.get("user_id") == owner_user_id:
            admin_caller = c
        else:
            team.append(c)
    return {"data": team, "admin_caller": admin_caller}


@router.patch("/{caller_id}")
async def update_caller(caller_id: UUID, payload: UpdateCaller, tenant_id: str = Depends(get_owner_tenant_id)):
    db = get_supabase()
    updates = {}
    if payload.name is not None:
        updates["name"] = payload.name.strip()
    if payload.phone is not None:
        updates["phone"] = payload.phone.strip()
    if payload.telecmi_agent_id is not None:
        updates["telecmi_agent_id"] = payload.telecmi_agent_id.strip() or None
    if payload.shift_start_hour is not None:
        updates["shift_start_hour"] = payload.shift_start_hour if 0 <= payload.shift_start_hour <= 23 else None
    if payload.shift_end_hour is not None:
        updates["shift_end_hour"] = payload.shift_end_hour if 0 <= payload.shift_end_hour <= 23 else None
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    result = db.table("callers").update(updates).eq("id", str(caller_id)).eq("tenant_id", tenant_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Caller not found")
    return result.data[0]


class TargetUpdate(BaseModel):
    target: int


@router.patch("/{caller_id}/target")
async def update_caller_target(
    caller_id: UUID,
    payload: TargetUpdate,
    ctx: dict = Depends(require_owner)
):
    tenant_id = ctx["tenant_id"]
    db = get_supabase()
    
    # Optional: check if caller exists and belongs to tenant
    caller = (
        db.table("callers")
        .select("id")
        .eq("id", str(caller_id))
        .eq("tenant_id", tenant_id)
        .eq("active", True)
        .maybe_single()
        .execute()
    )
    if not caller.data:
        raise HTTPException(status_code=404, detail="Caller not found")
        
    cfg = get_telecalling_config(tenant_id)
    if "targets" not in cfg or cfg["targets"] is None:
        cfg["targets"] = {}
    cfg["targets"][str(caller_id)] = payload.target
    save_telecalling_config(tenant_id, cfg)
    
    return {"caller_id": caller_id, "target": payload.target}


@router.delete("/{caller_id}")
async def delete_caller(caller_id: UUID, tenant_id: str = Depends(get_owner_tenant_id)):
    db = get_supabase()
    db.table("callers").update({"active": False}).eq("id", str(caller_id)).eq("tenant_id", tenant_id).execute()
    return {"deleted": True}


@router.get("/{caller_id}/logs")
async def list_caller_logs(caller_id: UUID, tenant_id: str = Depends(get_owner_tenant_id)):
    db = get_supabase()
    result = (
        db.table("call_logs")
        .select("id,lead_id,call_sid,duration_seconds,outcome,recording_url,score,status,ai_summary,transcript,created_at,leads(phone,name)")
        .eq("caller_id", str(caller_id))
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    return {"data": result.data or []}


# ── Winners (daily & monthly leaderboard) ────────────────────────────────────


@router.get("/winners")
async def get_winners(tenant_id: str = Depends(get_owner_tenant_id)):
    """
    Return the daily winner (most conversions today) and monthly winner
    (highest overall_score this month) for the tenant's callers.
    Both fields can be None if no eligible callers exist.
    """
    db = get_supabase()
    now = datetime.now(timezone.utc)

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    # Exclude owner from leaderboard (same pattern as list_callers)
    owner = db.table("tenant_users").select("user_id").eq("tenant_id", tenant_id).eq("role", "owner").maybe_single().execute()
    owner_user_id = (owner.data or {}).get("user_id")
    excluded_caller_ids: set[str] = set()
    if owner_user_id:
        owner_callers = db.table("callers").select("id").eq("tenant_id", tenant_id).eq("user_id", owner_user_id).execute()
        excluded_caller_ids = {c["id"] for c in (owner_callers.data or [])}

    # ── Daily winner: most conversions today ──────────────────────────────────
    daily_logs = (
        db.table("call_logs")
        .select("caller_id")
        .eq("tenant_id", tenant_id)
        .eq("outcome", "converted")
        .gte("created_at", today_start)
        .execute()
    )

    daily_winner = None
    if daily_logs.data:
        counts: dict[str, int] = {}
        for row in daily_logs.data:
            cid = row.get("caller_id")
            if cid and cid not in excluded_caller_ids:
                counts[cid] = counts.get(cid, 0) + 1
        if counts:
            top_cid = max(counts, key=lambda k: counts[k])
            caller_row = (
                db.table("callers")
                .select("id,name,overall_score")
                .eq("id", top_cid)
                .eq("tenant_id", tenant_id)
                .eq("active", True)
                .maybe_single()
                .execute()
            )
            if caller_row.data:
                daily_winner = {
                    "caller_id": top_cid,
                    "name": caller_row.data.get("name", "Unknown"),
                    "value": counts[top_cid],
                    "label": "conversions today",
                }

    # ── Monthly winner: highest overall_score (active callers) ────────────────
    # Also compute calls this month for display
    month_logs = (
        db.table("call_logs")
        .select("caller_id")
        .eq("tenant_id", tenant_id)
        .gte("created_at", month_start)
        .execute()
    )

    month_call_counts: dict[str, int] = {}
    for row in (month_logs.data or []):
        cid = row.get("caller_id")
        if cid and cid not in excluded_caller_ids:
            month_call_counts[cid] = month_call_counts.get(cid, 0) + 1

    # Only callers who have done enough calls this month are eligible.
    # Prevents a caller with 2 lucky converted calls from beating someone
    # who worked the full month.
    eligible_ids = [
        cid for cid, count in month_call_counts.items()
        if count >= MIN_MONTHLY_CALLS
    ]

    monthly_winner = None
    if eligible_ids:
        top_callers = (
            db.table("callers")
            .select("id,name,overall_score")
            .eq("tenant_id", tenant_id)
            .eq("active", True)
            .in_("id", eligible_ids)
            .order("overall_score", desc=True)
            .limit(1)
            .execute()
        )
        if top_callers.data:
            best = top_callers.data[0]
            cid = best["id"]
            monthly_winner = {
                "caller_id": cid,
                "name": best.get("name", "Unknown"),
                "value": float(best.get("overall_score") or 0),
                "calls_this_month": month_call_counts.get(cid, 0),
                "label": "overall score",
            }

    return {"daily": daily_winner, "monthly": monthly_winner}


# ── Daily coaching digest ─────────────────────────────────────────────────────

@router.get("/{caller_id}/digest")
async def get_digest(
    caller_id: UUID,
    tenant_id: str = Depends(get_owner_tenant_id),
    days: int = 7,
):
    """Return the last N days of coaching digests for a caller."""
    db = get_supabase()
    rows = (
        db.table("caller_digests")
        .select("digest_date,call_count,stats,coaching_report,created_at")
        .eq("caller_id", str(caller_id))
        .eq("tenant_id", tenant_id)
        .order("digest_date", desc=True)
        .limit(days)
        .execute()
    )
    return {"data": rows.data or []}


@router.post("/{caller_id}/digest/generate")
async def trigger_digest(
    caller_id: UUID,
    tenant_id: str = Depends(get_owner_tenant_id),
):
    """Manually trigger today's digest for a caller (owner only, for testing)."""
    from datetime import date as _date
    from app.services.call_digest import generate_daily_digest
    await generate_daily_digest(str(caller_id), tenant_id, _date.today())
    return {"ok": True}


@router.get("/{caller_id}/coaching")
async def get_coaching(caller_id: UUID, tenant_id: str = Depends(get_owner_tenant_id)):
    db = get_supabase()
    caller = db.table("callers").select("id").eq("id", str(caller_id)).eq("tenant_id", tenant_id).maybe_single().execute()
    if not caller.data:
        raise HTTPException(status_code=404, detail="Caller not found")
    tip = await coaching_tip(str(caller_id))
    return {"caller_id": str(caller_id), "tip": tip}




