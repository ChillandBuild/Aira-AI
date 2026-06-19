import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_and_role
from app.services.attendance import build_attendance_map, compute_team_summary, date_range

logger = logging.getLogger(__name__)
router = APIRouter()


class InvitePayload(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None
    phone: str | None = None
    telecmi_agent_id: str | None = None


class AttendancePayload(BaseModel):
    date: str
    status: str


class MarkHolidayPayload(BaseModel):
    date: str


def _active_team_callers(db, tenant_id: str) -> list[dict]:
    """Active, non-owner callers for a tenant (mirrors list_callers filtering)."""
    owner = (
        db.table("tenant_users")
        .select("user_id")
        .eq("tenant_id", tenant_id)
        .eq("role", "owner")
        .maybe_single()
        .execute()
    )
    owner_user_id = (owner.data or {}).get("user_id")

    query = (
        db.table("callers")
        .select("id, name")
        .eq("tenant_id", tenant_id)
        .eq("active", True)
    )
    if owner_user_id:
        query = query.neq("user_id", owner_user_id)
    return query.execute().data or []


@router.get("/me")
def get_me(ctx: dict = Depends(get_tenant_and_role)):
    db = get_supabase()

    # Enabled features for this tenant
    tenant = (
        db.table("tenants")
        .select("enabled_features")
        .eq("id", ctx["tenant_id"])
        .limit(1)
        .execute()
    )
    tenant_row = tenant.data[0] if tenant and tenant.data else {}
    enabled_features: list[str] = (
        tenant_row.get("enabled_features") or ["whatsapp", "telecalling"]
    )

    # Check system admin — use limit(1) instead of maybe_single() to avoid
    # PostgREST 406 on zero rows, which causes the client to return None and
    # crash the `.data` access (was the cause of /api/v1/team/me 500s for
    # non-admin users like callers).
    admin = (
        db.table("system_admins")
        .select("user_id")
        .eq("user_id", ctx["user_id"])
        .limit(1)
        .execute()
    )
    is_system_admin = bool(admin and admin.data)

    caller = (
        db.table("callers")
        .select("id, name, phone, overall_score")
        .eq("user_id", ctx["user_id"])
        .eq("tenant_id", ctx["tenant_id"])
        .limit(1)
        .execute()
    )
    profile = caller.data[0] if caller and caller.data else None

    return {
        "tenant_id": ctx["tenant_id"],
        "role": ctx["role"],
        "caller_id": ctx.get("caller_id"),
        "caller_profile": profile,
        "enabled_features": enabled_features,
        "is_system_admin": is_system_admin,
    }


@router.get("/")
def list_team(ctx: dict = Depends(get_tenant_and_role)):
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can view team")
    db = get_supabase()
    members = (
        db.table("tenant_users")
        .select("user_id, role, created_at")
        .eq("tenant_id", ctx["tenant_id"])
        .execute()
    )
    user_ids = [m["user_id"] for m in (members.data or [])]
    callers = {}
    if user_ids:
        caller_rows = (
            db.table("callers")
            .select("user_id, id, name, phone, overall_score, active, telecmi_agent_id")
            .in_("user_id", user_ids)
            .eq("tenant_id", ctx["tenant_id"])
            .execute()
        )
        callers = {r["user_id"]: r for r in (caller_rows.data or [])}
    result = []
    for m in (members.data or []):
        result.append({
            **m,
            "caller_profile": callers.get(m["user_id"]),
        })
    return {"data": result}


@router.post("/invite")
async def invite_member(payload: InvitePayload, ctx: dict = Depends(get_tenant_and_role)):
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can invite members")

    db = get_supabase()
    try:
        result = db.auth.admin.create_user({
            "email": payload.email,
            "password": payload.password,
            "email_confirm": True,
        })
        user = result.user
        invited_user_id = user.id if hasattr(user, "id") else user["id"]
    except Exception as e:
        msg = str(e)
        if "already" in msg.lower() or "duplicate" in msg.lower() or "registered" in msg.lower():
            raise HTTPException(status_code=400, detail="A user with this email already exists")
        logger.error(f"create_user failed: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to create user: {msg}")

    try:
        existing = (
            db.table("tenant_users")
            .select("id")
            .eq("user_id", invited_user_id)
            .eq("tenant_id", ctx["tenant_id"])
            .limit(1)
            .execute()
        )
        if not existing.data:
            db.table("tenant_users").insert({
                "tenant_id": ctx["tenant_id"],
                "user_id": invited_user_id,
                "role": "caller",
            }).execute()

        caller_existing = (
            db.table("callers")
            .select("id")
            .eq("user_id", invited_user_id)
            .eq("tenant_id", ctx["tenant_id"])
            .limit(1)
            .execute()
        )
        if not caller_existing.data:
            caller_row = {
                "tenant_id": ctx["tenant_id"],
                "user_id": invited_user_id,
                "name": payload.name or payload.email.split("@")[0],
                "phone": payload.phone,
                "active": True,
            }
            if payload.telecmi_agent_id:
                caller_row["telecmi_agent_id"] = payload.telecmi_agent_id
            db.table("callers").insert(caller_row).execute()
    except Exception as e:
        logger.error(f"tenant_users/callers insert failed: {e}")
        raise HTTPException(status_code=500, detail=f"User created but assignment failed: {e}")

    logger.info(f"Created telecaller {payload.email} for tenant {ctx['tenant_id']}")
    return {"invited": True, "email": payload.email, "user_id": invited_user_id}


@router.delete("/{user_id}")
def remove_member(user_id: str, ctx: dict = Depends(get_tenant_and_role)):
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can remove members")
    db = get_supabase()
    db.table("tenant_users").delete().eq("user_id", user_id).eq("tenant_id", ctx["tenant_id"]).execute()
    db.table("callers").delete().eq("user_id", user_id).eq("tenant_id", ctx["tenant_id"]).execute()
    return {"removed": True}


@router.get("/attendance")
def get_team_attendance(
    month: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    ctx: dict = Depends(get_tenant_and_role),
):
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can view attendance")
    db = get_supabase()
    today = datetime.utcnow().date()

    if from_date and to_date:
        try:
            range_start = date.fromisoformat(from_date)
            range_end = date.fromisoformat(to_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="from/to must be in YYYY-MM-DD format")
        if range_end < range_start:
            range_start, range_end = range_end, range_start
        month_start, month_end = range_start, range_end
    else:
        if month:
            try:
                year_str, mon_str = month.split("-")
                month_start = date(int(year_str), int(mon_str), 1)
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail="month must be in YYYY-MM format")
        else:
            month_start = today.replace(day=1)

        if month_start.month == 12:
            next_month = date(month_start.year + 1, 1, 1)
        else:
            next_month = date(month_start.year, month_start.month + 1, 1)
        month_end = next_month - timedelta(days=1)

    callers = _active_team_callers(db, ctx["tenant_id"])
    caller_ids = [c["id"] for c in callers]

    days = date_range(month_start, month_end)
    overrides_by_caller: dict[str, dict[str, str]] = {cid: {} for cid in caller_ids}
    active_by_caller: dict[str, set[str]] = {cid: set() for cid in caller_ids}

    if caller_ids:
        override_rows = (
            db.table("caller_attendance_overrides")
            .select("caller_id, date, status")
            .in_("caller_id", caller_ids)
            .gte("date", month_start.isoformat())
            .lte("date", month_end.isoformat())
            .execute()
        )
        for r in (override_rows.data or []):
            overrides_by_caller.setdefault(r["caller_id"], {})[r["date"]] = r["status"]

        log_rows = (
            db.table("caller_status_logs")
            .select("caller_id, started_at")
            .in_("caller_id", caller_ids)
            .gte("started_at", f"{month_start.isoformat()}T00:00:00")
            .lt("started_at", f"{(month_end + timedelta(days=1)).isoformat()}T00:00:00")
            .execute()
        )
        for r in (log_rows.data or []):
            active_by_caller.setdefault(r["caller_id"], set()).add(r["started_at"][:10])

    grid = {
        cid: build_attendance_map(days, today, overrides_by_caller.get(cid, {}), active_by_caller.get(cid, set()))
        for cid in caller_ids
    }
    summary = compute_team_summary(grid, today.isoformat())

    return {
        "data": {
            "callers": [{"caller_id": c["id"], "name": c["name"]} for c in callers],
            "days": [d.isoformat() for d in days],
            "grid": grid,
            "summary": summary,
        }
    }


@router.get("/attendance/{caller_id}")
def get_caller_attendance(caller_id: str, months: int = 4, ctx: dict = Depends(get_tenant_and_role)):
    if ctx["role"] != "owner" and ctx.get("caller_id") != caller_id:
        raise HTTPException(status_code=403, detail="Only owners or the telecaller themselves can view this attendance")
    db = get_supabase()

    caller = (
        db.table("callers")
        .select("id")
        .eq("id", caller_id)
        .eq("tenant_id", ctx["tenant_id"])
        .limit(1)
        .execute()
    )
    if not caller.data:
        raise HTTPException(status_code=404, detail="Caller not found")

    today = datetime.utcnow().date()
    start = today - timedelta(days=30 * months)
    end = today + timedelta(days=14)
    days = date_range(start, end)

    override_rows = (
        db.table("caller_attendance_overrides")
        .select("date, status")
        .eq("caller_id", caller_id)
        .gte("date", start.isoformat())
        .lte("date", end.isoformat())
        .execute()
    )
    overrides = {r["date"]: r["status"] for r in (override_rows.data or [])}

    log_rows = (
        db.table("caller_status_logs")
        .select("started_at")
        .eq("caller_id", caller_id)
        .gte("started_at", f"{start.isoformat()}T00:00:00")
        .lt("started_at", f"{(today + timedelta(days=1)).isoformat()}T00:00:00")
        .execute()
    )
    active_dates = {r["started_at"][:10] for r in (log_rows.data or [])}

    day_map = build_attendance_map(days, today, overrides, active_dates)

    return {
        "data": {
            "caller_id": caller_id,
            "days": [{"date": d, "status": s} for d, s in day_map.items()],
            "today_status": day_map.get(today.isoformat(), "absent"),
        }
    }


@router.post("/attendance/holiday")
def mark_holiday(payload: MarkHolidayPayload, ctx: dict = Depends(get_tenant_and_role)):
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can mark holidays")
    try:
        holiday_date = date.fromisoformat(payload.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be in YYYY-MM-DD format")
    if holiday_date > datetime.utcnow().date() + timedelta(days=14):
        raise HTTPException(status_code=400, detail="Holidays can only be marked up to 14 days in advance")

    db = get_supabase()

    caller_ids = [c["id"] for c in _active_team_callers(db, ctx["tenant_id"])]

    if not caller_ids:
        return {"data": {"date": payload.date, "status": "holiday", "caller_count": 0}}

    existing = (
        db.table("caller_attendance_overrides")
        .select("id, caller_id")
        .in_("caller_id", caller_ids)
        .eq("date", payload.date)
        .execute()
    )
    existing_by_caller = {r["caller_id"]: r["id"] for r in (existing.data or [])}

    for cid in caller_ids:
        row = {
            "tenant_id": ctx["tenant_id"],
            "caller_id": cid,
            "date": payload.date,
            "status": "holiday",
            "marked_by": ctx["user_id"],
            "updated_at": datetime.utcnow().isoformat(),
        }
        existing_id = existing_by_caller.get(cid)
        if existing_id:
            db.table("caller_attendance_overrides").update(row).eq("id", existing_id).execute()
        else:
            db.table("caller_attendance_overrides").insert(row).execute()

    logger.info(f"Marked holiday {payload.date} for {len(caller_ids)} callers in tenant {ctx['tenant_id']}")
    return {"data": {"date": payload.date, "status": "holiday", "caller_count": len(caller_ids)}}


@router.post("/attendance/{caller_id}")
def mark_attendance(caller_id: str, payload: AttendancePayload, ctx: dict = Depends(get_tenant_and_role)):
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can mark attendance")
    if payload.status not in ("present", "absent"):
        raise HTTPException(status_code=400, detail="status must be 'present' or 'absent'")
    try:
        date.fromisoformat(payload.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be in YYYY-MM-DD format")

    db = get_supabase()
    caller = (
        db.table("callers")
        .select("id")
        .eq("id", caller_id)
        .eq("tenant_id", ctx["tenant_id"])
        .limit(1)
        .execute()
    )
    if not caller.data:
        raise HTTPException(status_code=404, detail="Caller not found")

    existing = (
        db.table("caller_attendance_overrides")
        .select("id")
        .eq("caller_id", caller_id)
        .eq("date", payload.date)
        .limit(1)
        .execute()
    )
    row = {
        "tenant_id": ctx["tenant_id"],
        "caller_id": caller_id,
        "date": payload.date,
        "status": payload.status,
        "marked_by": ctx["user_id"],
        "updated_at": datetime.utcnow().isoformat(),
    }
    if existing.data:
        db.table("caller_attendance_overrides").update(row).eq("id", existing.data[0]["id"]).execute()
    else:
        db.table("caller_attendance_overrides").insert(row).execute()

    return {"data": {"date": payload.date, "status": payload.status}}
