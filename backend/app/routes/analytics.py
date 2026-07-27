"""
Analytics routes — service metrics for WhatsApp, telecalling, and lead funnel.
"""

import asyncio
import csv
import io
import logging
import statistics
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_and_role
from app.services.inbound_leads_logic import INBOUND_SOURCES, aggregate_inbound
from app.services.assignment import get_telecalling_config

logger = logging.getLogger(__name__)
router = APIRouter()

IST_OFFSET = timedelta(hours=5, minutes=30)
MANUAL_STATUS_KEYS = ("connected", "not_picked", "busy", "wrong_number", "interested", "not_interested", "callback")


def _tenant_id_for_permission(ctx: dict, permissions: set[str]) -> str:
    user_permissions = set(ctx.get("permissions") or [])
    if ctx.get("role") == "owner" or user_permissions.intersection(permissions):
        return ctx["tenant_id"]
    required = " or ".join(sorted(permissions))
    raise HTTPException(status_code=403, detail=f"Permission required: {required}")


def get_dashboard_analytics_tenant_id(ctx: dict = Depends(get_tenant_and_role)) -> str:
    return _tenant_id_for_permission(ctx, {"dashboard.view", "analytics.view"})


def get_analytics_tenant_id(ctx: dict = Depends(get_tenant_and_role)) -> str:
    return _tenant_id_for_permission(ctx, {"analytics.view"})


def require_analytics_view(ctx: dict = Depends(get_tenant_and_role)) -> dict:
    _tenant_id_for_permission(ctx, {"analytics.view"})
    return ctx


def _today_start() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _week_start() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()


def _range_params(range_str: str) -> tuple[datetime, list[str]]:
    """Return (window_start_utc, list_of_date_iso_strings) for a range value."""
    now = datetime.now(timezone.utc)
    if range_str == "today":
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        days_iso = [now.date().isoformat()]
    elif range_str == "30d":
        start_dt = now - timedelta(days=30)
        days_iso = [(now - timedelta(days=i)).date().isoformat() for i in range(29, -1, -1)]
    else:  # default "7d"
        start_dt = now - timedelta(days=7)
        days_iso = [(now - timedelta(days=i)).date().isoformat() for i in range(6, -1, -1)]
    return start_dt, days_iso


def _ist_hour(utc_iso: str) -> int:
    """Convert a UTC ISO string to IST hour (int)."""
    try:
        dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
        ist = dt + IST_OFFSET
        return ist.hour
    except Exception:
        return -1


def _ist_today_start_utc() -> datetime:
    """Midnight IST expressed as a UTC datetime."""
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc + IST_OFFSET
    midnight_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight_ist - IST_OFFSET


def _is_connected(log: dict) -> bool:
    """A call is 'connected' if it had talk time or a non-no_answer outcome."""
    manual_status = log.get("manual_status")
    if manual_status in {"connected", "interested", "not_interested", "callback"}:
        return True
    if manual_status in {"not_picked", "busy", "wrong_number"}:
        return False
    disposition = log.get("disposition")
    if disposition in {"answered", "followup_required"}:
        return True
    if disposition in {"no_answer", "busy", "switched_off"}:
        return False
    return (log.get("duration_seconds") or 0) > 0 or (
        log.get("outcome") is not None and log.get("outcome") != "no_answer"
    )


def _manual_status_breakdown(logs: list[dict]) -> dict[str, int]:
    counts = {key: 0 for key in MANUAL_STATUS_KEYS}
    for log in logs:
        status = log.get("manual_status")
        if status in counts:
            counts[status] += 1
    return counts


def _caller_idle_minutes(
    caller_logs: list[dict],
    caller_status_logs: list[dict],
    window_start: datetime,
    window_end: datetime,
) -> float:
    """Idle minutes for one caller in [window_start, window_end): merged 'active'
    interval minutes minus talk minutes. Mirrors the per-caller logic in the main
    telecalling endpoint."""
    intervals = []
    for sl in caller_status_logs:
        if sl.get("status") != "active":
            continue
        s_time = datetime.fromisoformat(sl["started_at"].replace("Z", "+00:00"))
        s_time = max(s_time, window_start)
        e_time = (
            datetime.fromisoformat(sl["ended_at"].replace("Z", "+00:00"))
            if sl.get("ended_at")
            else window_end
        )
        e_time = min(e_time, window_end)
        if s_time < e_time:
            intervals.append((s_time, e_time))

    intervals.sort(key=lambda x: x[0])
    merged: list[tuple[datetime, datetime]] = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))

    active_minutes = sum((e - s).total_seconds() for s, e in merged) / 60.0
    talk_seconds = sum(l["duration_seconds"] for l in caller_logs if l.get("duration_seconds") is not None)
    talk_minutes = talk_seconds / 60.0
    return max(0.0, active_minutes - talk_minutes)


def _window_aggregate(
    logs: list[dict],
    status_logs: list[dict],
    caller_ids: list[str],
    window_start: datetime,
    window_end: datetime,
    day_count: int,
) -> dict:
    """Aggregate metrics for a window, comparable in magnitude to the daily 'today'
    headline. Count metrics (calls, conversions, idle_minutes) are divided by
    day_count to yield a per-day figure; rate/mean metrics are window-wide."""
    win_logs = [
        l for l in logs
        if window_start <= datetime.fromisoformat(l["created_at"].replace("Z", "+00:00")) < window_end
    ]
    win_status = [
        sl for sl in status_logs
        if window_start <= datetime.fromisoformat(sl["started_at"].replace("Z", "+00:00")) < window_end
    ]

    calls = len(win_logs)
    connected = sum(1 for l in win_logs if _is_connected(l))
    connect_rate = round(connected / calls, 4) if calls > 0 else 0.0
    conversions = sum(1 for l in win_logs if l.get("outcome") == "converted")

    durations = [l["duration_seconds"] for l in win_logs if l.get("duration_seconds") is not None]
    avg_talk_seconds = round(sum(durations) / len(durations), 1) if durations else 0.0

    total_idle = 0.0
    for cid in caller_ids:
        c_logs = [l for l in win_logs if str(l.get("caller_id")) == cid]
        c_status = [sl for sl in win_status if str(sl.get("caller_id")) == cid]
        total_idle += _caller_idle_minutes(c_logs, c_status, window_start, window_end)

    days = max(day_count, 1)
    return {
        "calls": round(calls / days, 1),
        "connect_rate": connect_rate,
        "conversions": round(conversions / days, 1),
        "avg_talk_seconds": avg_talk_seconds,
        "idle_minutes": round(total_idle / days, 1),
    }


@router.get("/whatsapp")
async def whatsapp_analytics(tenant_id: str = Depends(get_analytics_tenant_id)):
    db = get_supabase()
    today = _today_start()

    msgs_today_res = await asyncio.to_thread(
        db.table("messages")
        .select("id,direction,is_ai_generated")
        .eq("tenant_id", tenant_id)
        .gte("created_at", today)
        .execute
    )
    msgs_today = msgs_today_res.data or []

    messages_sent_today = sum(1 for m in msgs_today if m.get("direction") == "outbound")
    messages_received_today = sum(1 for m in msgs_today if m.get("direction") == "inbound")
    ai_reply_count_today = sum(
        1 for m in msgs_today
        if m.get("direction") == "outbound" and m.get("is_ai_generated")
    )

    return {
        "messages_sent_today": messages_sent_today,
        "messages_received_today": messages_received_today,
        "ai_reply_count_today": ai_reply_count_today,
        "avg_reply_time_seconds": None,
    }


@router.get("/template-performance")
async def template_performance(tenant_id: str = Depends(get_analytics_tenant_id)):
    """Per-template broadcast performance: Sent / Read / Replied / Hot leads."""
    db = get_supabase()
    try:
        res = await asyncio.to_thread(
            db.rpc("template_performance", {"p_tenant_id": tenant_id}).execute
        )
        return {"data": res.data or []}
    except Exception as e:
        logger.error(f"template_performance failed for tenant {tenant_id}: {e}")
        return {"data": []}


@router.get("/telecalling")
async def telecalling_analytics(
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    tenant_id: str = Depends(get_analytics_tenant_id),
):
    db = get_supabase()

    # Day bounds must use UTC midnight
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = _week_start()

    # Reporting window: defaults to "today" when no from/to given.
    if from_date and to_date:
        try:
            range_start = datetime.combine(date.fromisoformat(from_date), datetime.min.time()).replace(tzinfo=timezone.utc)
            range_end_exclusive = datetime.combine(date.fromisoformat(to_date), datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(days=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="from/to must be in YYYY-MM-DD format")
    else:
        range_start = today_start
        range_end_exclusive = None
    range_start_iso = range_start.isoformat()
    range_end_for_clip = min(range_end_exclusive, now) if range_end_exclusive else now

    logs_today_query = (
        db.table("call_logs")
        .select("id,duration_seconds,outcome,disposition,manual_status,provider,feedback_source,caller_id,created_at,evaluation,lead_id,leads(created_at,assigned_at)")
        .eq("tenant_id", tenant_id)
        .gte("created_at", range_start_iso)
    )
    if range_end_exclusive:
        logs_today_query = logs_today_query.lt("created_at", range_end_exclusive.isoformat())

    status_logs_query = (
        db.table("caller_status_logs")
        .select("id,caller_id,status,started_at,ended_at")
        .eq("tenant_id", tenant_id)
        .gte("started_at", range_start_iso)
    )
    if range_end_exclusive:
        status_logs_query = status_logs_query.lt("started_at", range_end_exclusive.isoformat())

    # These five reads are independent — run them concurrently off the event loop.
    logs_today_exec, logs_week_exec, all_time_res, status_logs_exec, callers_exec = await asyncio.gather(
        asyncio.to_thread(logs_today_query.execute),
        asyncio.to_thread(
            db.table("call_logs")
            .select("id,caller_id,manual_status,outcome,disposition,duration_seconds")
            .eq("tenant_id", tenant_id)
            .gte("created_at", week)
            .execute
        ),
        asyncio.to_thread(
            db.rpc("get_telecalling_all_time_stats", {"p_tenant_id": tenant_id}).execute
        ),
        asyncio.to_thread(status_logs_query.execute),
        asyncio.to_thread(
            db.table("callers")
            .select("id,name,overall_score,user_id")
            .eq("tenant_id", tenant_id)
            .eq("active", True)
            .execute
        ),
    )
    logs_today_res = logs_today_exec.data or []
    logs_week_res = logs_week_exec.data or []
    all_time_data = (all_time_res.data or {}) if all_time_res else {}
    status_logs_today = status_logs_exec.data or []
    all_callers = callers_exec.data or []

    owner_row = db.table("tenant_users").select("user_id").eq("tenant_id", tenant_id).eq("role", "owner").limit(1).execute()
    owner_user_id = (owner_row.data[0] if owner_row.data else {}).get("user_id")
    callers_res = [c for c in all_callers if c.get("user_id") != owner_user_id] if owner_user_id else all_callers

    # Exclude the owner/admin's own calls from team aggregates (Invariant 13: admin is
    # excluded from ALL telecaller metrics). A null caller_id can only be an owner direct
    # call — telecallers always carry a caller_id — so drop those plus any owner caller-record
    # calls. Keeps the banner consistent with the owner-excluded leaderboard below.
    owner_caller_ids = {c["id"] for c in all_callers if c.get("user_id") == owner_user_id}
    logs_today_res = [l for l in logs_today_res if l.get("caller_id") is not None and l.get("caller_id") not in owner_caller_ids]
    logs_week_res = [l for l in logs_week_res if l.get("caller_id") is not None and l.get("caller_id") not in owner_caller_ids]

    calls_today = len(logs_today_res)
    calls_this_week = len(logs_week_res)
    conversions_today = sum(1 for l in logs_today_res if l.get("outcome") == "converted")

    # All-time durations and outcomes from RPC
    avg_duration_seconds = all_time_data.get("avg_duration_seconds")
    if avg_duration_seconds == 0:
        avg_duration_seconds = None

    outcome_breakdown = {"converted": 0, "interested": 0, "callback": 0, "not_interested": 0, "no_answer": 0}
    rpc_breakdown = all_time_data.get("outcome_breakdown") or {}
    for k, v in rpc_breakdown.items():
        if k in outcome_breakdown:
            outcome_breakdown[k] = v

    manual_status_breakdown = _manual_status_breakdown(logs_today_res)
    rpc_manual_breakdown = all_time_data.get("manual_status_breakdown") or {}
    manual_status_all_time_breakdown = {key: 0 for key in MANUAL_STATUS_KEYS}
    for k, v in rpc_manual_breakdown.items():
        if k in manual_status_all_time_breakdown:
            manual_status_all_time_breakdown[k] = v

    # calls_per_hour — IST hours 9–18, today's calls
    hour_counts: dict[int, int] = {h: 0 for h in range(9, 19)}
    # calls_per_slot — 30-min slots 09:00–17:30 (18 slots)
    slots = [f"{h:02d}:{m:02d}" for h in range(9, 18) for m in (0, 30)]
    slot_counts: dict[str, int] = {s: 0 for s in slots}
    slot_caller_counts: dict[str, dict[str, int]] = {s: {} for s in slots}

    for log in logs_today_res:
        raw_ts = log.get("created_at") or ""
        if not raw_ts:
            continue
        ist_h = _ist_hour(raw_ts)
        if ist_h in hour_counts:
            hour_counts[ist_h] += 1
        # determine slot
        try:
            dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            ist_dt = dt + IST_OFFSET
            slot_min = 0 if ist_dt.minute < 30 else 30
            slot_key = f"{ist_dt.hour:02d}:{slot_min:02d}"
            if slot_key in slot_counts:
                slot_counts[slot_key] += 1
                cid = log.get("caller_id")
                if cid:
                    slot_caller_counts[slot_key][str(cid)] = slot_caller_counts[slot_key].get(str(cid), 0) + 1
        except Exception:
            pass

    hour_labels = {
        9: "9 AM", 10: "10 AM", 11: "11 AM", 12: "12 PM",
        13: "1 PM", 14: "2 PM", 15: "3 PM", 16: "4 PM",
        17: "5 PM", 18: "6 PM",
    }
    calls_per_hour = [
        {"hour": h, "label": hour_labels[h], "count": hour_counts[h]}
        for h in range(9, 19)
    ]
    calls_per_slot = [
        {"slot": s, "count": slot_counts[s], "caller_counts": slot_caller_counts[s]}
        for s in slots
    ]

    # per-caller conversion rates (all-time) from RPC
    caller_total: dict[str, int] = {}
    caller_converted: dict[str, int] = {}
    rpc_caller_stats = all_time_data.get("caller_stats") or {}
    for cid_str, stats_dict in rpc_caller_stats.items():
        caller_total[cid_str] = stats_dict.get("total", 0)
        caller_converted[cid_str] = stats_dict.get("converted", 0)

    # Team-wide aggregates
    team_connected_calls = [l for l in logs_today_res if _is_connected(l)]
    team_connect_rate = round(len(team_connected_calls) / calls_today, 4) if calls_today > 0 else 0.0

    today_dur_all = [l["duration_seconds"] for l in logs_today_res if l.get("duration_seconds") is not None]
    team_avg_talk_seconds = round(sum(today_dur_all) / len(today_dur_all), 1) if today_dur_all else 0.0
    team_talk_minutes_today = round(sum(today_dur_all) / 60, 1) if today_dur_all else 0.0

    all_idle_minutes = []
    all_gaps = []
    all_longest_idles = []
    all_bunking_flags = []
    all_speed_to_leads = []
    all_quality_scores = []

    per_caller = []
    for c in callers_res:
        cid = c["id"]
        cid_str = str(cid)

        caller_calls = [l for l in logs_today_res if str(l.get("caller_id")) == cid_str]
        c_calls_count = len(caller_calls)
        c_connected = [l for l in caller_calls if _is_connected(l)]
        c_connect_rate = round(len(c_connected) / c_calls_count, 4) if c_calls_count > 0 else 0.0

        c_talk_durations = [l["duration_seconds"] for l in caller_calls if l.get("duration_seconds") is not None]
        c_avg_talk_seconds = round(sum(c_talk_durations) / len(c_talk_durations), 1) if c_talk_durations else 0.0
        c_talk_minutes_today = round(sum(c_talk_durations) / 60, 1) if c_talk_durations else 0.0

        # Status intervals clipping
        c_status_logs = [log for log in status_logs_today if str(log.get("caller_id")) == cid_str]
        c_active_intervals = []
        for log in c_status_logs:
            s_time = datetime.fromisoformat(log["started_at"].replace("Z", "+00:00"))
            s_time = max(s_time, range_start)
            e_time = datetime.fromisoformat(log["ended_at"].replace("Z", "+00:00")) if log.get("ended_at") else range_end_for_clip
            e_time = max(e_time, range_start)
            if s_time < e_time and log["status"] == "active":
                c_active_intervals.append((s_time, e_time))

        # Merge active intervals
        c_active_intervals.sort(key=lambda x: x[0])
        merged_active = []
        for start, end in c_active_intervals:
            if not merged_active:
                merged_active.append((start, end))
            else:
                prev_start, prev_end = merged_active[-1]
                if start <= prev_end:
                    merged_active[-1] = (prev_start, max(prev_end, end))
                else:
                    merged_active.append((start, end))

        total_active_seconds = sum((end - start).total_seconds() for start, end in merged_active)
        c_active_minutes_today = total_active_seconds / 60.0
        c_idle_minutes_today = max(0.0, c_active_minutes_today - c_talk_minutes_today)
        all_idle_minutes.append(c_idle_minutes_today)

        # Gaps
        c_gaps = []
        c_longest_idle = 0.0
        sorted_calls = sorted(caller_calls, key=lambda x: x["created_at"])

        def get_active_overlap(gs, ge):
            if gs >= ge:
                return 0.0
            overlap = 0.0
            for as_, ae_ in merged_active:
                os = max(gs, as_)
                oe = min(ge, ae_)
                if os < oe:
                    overlap += (oe - os).total_seconds()
            return overlap

        if merged_active:
            first_active_start = merged_active[0][0]
            if sorted_calls:
                first_call_start = datetime.fromisoformat(sorted_calls[0]["created_at"].replace("Z", "+00:00"))
                gap_before = get_active_overlap(first_active_start, first_call_start)
                if gap_before > 0:
                    c_gaps.append(gap_before)
                for i in range(1, len(sorted_calls)):
                    prev_call_end = datetime.fromisoformat(sorted_calls[i-1]["created_at"].replace("Z", "+00:00")) + timedelta(seconds=sorted_calls[i-1].get("duration_seconds") or 0)
                    curr_call_start = datetime.fromisoformat(sorted_calls[i]["created_at"].replace("Z", "+00:00"))
                    gap = get_active_overlap(prev_call_end, curr_call_start)
                    if gap > 0:
                        c_gaps.append(gap)
                last_call_end = datetime.fromisoformat(sorted_calls[-1]["created_at"].replace("Z", "+00:00")) + timedelta(seconds=sorted_calls[-1].get("duration_seconds") or 0)
                gap_after = get_active_overlap(last_call_end, range_end_for_clip)
                if gap_after > 0:
                    c_gaps.append(gap_after)
            else:
                c_gaps.append(total_active_seconds)

            c_longest_idle = max(c_gaps) if c_gaps else 0.0

        c_avg_gap_seconds = sum(c_gaps) / len(c_gaps) if c_gaps else 0.0
        all_gaps.extend(c_gaps)
        all_longest_idles.append(c_longest_idle)

        # Bunking: idle ≥15 min between calls while the caller was active.
        c_bunking_flag = c_longest_idle >= 900
        all_bunking_flags.append(c_bunking_flag)

        # speed_to_lead_min
        # speed_to_lead: minutes from assignment → the FIRST call per lead, median.
        first_call_by_lead: dict = {}
        for log in caller_calls:
            lid = log.get("lead_id")
            if not lid:
                continue
            if lid not in first_call_by_lead or log["created_at"] < first_call_by_lead[lid]["created_at"]:
                first_call_by_lead[lid] = log
        c_speed_to_lead_list = []
        for log in first_call_by_lead.values():
            assigned_str = (log.get("leads") or {}).get("assigned_at")
            if assigned_str:
                assigned_dt = datetime.fromisoformat(assigned_str.replace("Z", "+00:00"))
                call_created = datetime.fromisoformat(log["created_at"].replace("Z", "+00:00"))
                diff = (call_created - assigned_dt).total_seconds() / 60.0
                if diff >= 0:
                    c_speed_to_lead_list.append(diff)
                    all_speed_to_leads.append(diff)
        c_speed_to_lead_min = round(statistics.median(c_speed_to_lead_list), 1) if c_speed_to_lead_list else None

        # quality_avg
        c_quality_scores = []
        for log in caller_calls:
            eval_data = log.get("evaluation")
            if isinstance(eval_data, dict) and "overall_score" in eval_data:
                try:
                    val = float(eval_data["overall_score"])
                    c_quality_scores.append(val)
                    all_quality_scores.append(val)
                except (ValueError, TypeError):
                    pass
        c_quality_avg = round(sum(c_quality_scores) / len(c_quality_scores), 1) if c_quality_scores else None

        total = caller_total.get(cid_str, 0)
        converted = caller_converted.get(cid_str, 0)
        conv_rate = round(converted / total, 4) if total > 0 else None

        per_caller.append({
            "caller_id": cid,
            "name": c.get("name"),
            "calls_today": c_calls_count,
            "overall_score": c.get("overall_score"),
            "total_minutes_today": c_talk_minutes_today,
            "conversion_rate": conv_rate,
            "connect_rate": c_connect_rate,
            "avg_talk_seconds": c_avg_talk_seconds,
            "talk_minutes_today": c_talk_minutes_today,
            "idle_minutes_today": round(c_idle_minutes_today, 1),
            "avg_gap_seconds": round(c_avg_gap_seconds, 1),
            "longest_idle_seconds": round(c_longest_idle, 1),
            "bunking_flag": c_bunking_flag,
            "speed_to_lead_min": c_speed_to_lead_min,
            "quality_avg": c_quality_avg,
        })

    # Comparison block — fixed daily-report baselines anchored to REAL today (UTC),
    # independent of the from/to reporting window. yesterday = the day before today;
    # avg_7d = trailing 7 full days before today (today excluded), per-day averaged.
    caller_id_strs = [str(c["id"]) for c in callers_res]
    comp_window_start = today_start - timedelta(days=7)
    comp_window_start_iso = comp_window_start.isoformat()
    yesterday_start = today_start - timedelta(days=1)

    comp_logs = (
        await asyncio.to_thread(
            db.table("call_logs")
            .select("id,duration_seconds,outcome,caller_id,created_at")
            .eq("tenant_id", tenant_id)
            .gte("created_at", comp_window_start_iso)
            .lt("created_at", today_start.isoformat())
            .execute
        )
    ).data or []
    comp_status = (
        await asyncio.to_thread(
            db.table("caller_status_logs")
            .select("id,caller_id,status,started_at,ended_at")
            .eq("tenant_id", tenant_id)
            .gte("started_at", comp_window_start_iso)
            .lt("started_at", today_start.isoformat())
            .execute
        )
    ).data or []

    comparison = {
        "yesterday": _window_aggregate(
            comp_logs, comp_status, caller_id_strs, yesterday_start, today_start, 1
        ),
        "avg_7d": _window_aggregate(
            comp_logs, comp_status, caller_id_strs, comp_window_start, today_start, 7
        ),
    }

    team_idle_minutes_today = round(sum(all_idle_minutes), 1) if all_idle_minutes else 0.0
    team_avg_gap_seconds = round(sum(all_gaps) / len(all_gaps), 1) if all_gaps else 0.0
    team_longest_idle_seconds = round(max(all_longest_idles), 1) if all_longest_idles else 0.0
    team_bunking_flag = any(all_bunking_flags) if all_bunking_flags else False
    team_speed_to_lead_min = round(statistics.median(all_speed_to_leads), 1) if all_speed_to_leads else None
    team_quality_avg = round(sum(all_quality_scores) / len(all_quality_scores), 1) if all_quality_scores else None

    return {
        "calls_today": calls_today,
        "calls_attempted": calls_today,
        "connected_calls": len(team_connected_calls),
        "not_picked_calls": manual_status_breakdown["not_picked"] + sum(
            1 for l in logs_today_res
            if not l.get("manual_status") and (l.get("disposition") == "no_answer" or l.get("outcome") == "no_answer")
        ),
        "busy_calls": manual_status_breakdown["busy"] + sum(
            1 for l in logs_today_res
            if not l.get("manual_status") and l.get("disposition") == "busy"
        ),
        "wrong_number_calls": manual_status_breakdown["wrong_number"],
        "interested_leads": manual_status_breakdown["interested"] + sum(
            1 for l in logs_today_res
            if not l.get("manual_status") and l.get("outcome") == "interested"
        ),
        "followups_scheduled": manual_status_breakdown["callback"] + sum(
            1 for l in logs_today_res
            if not l.get("manual_status") and l.get("outcome") == "callback"
        ),
        "calls_this_week": calls_this_week,
        "avg_duration_seconds": avg_duration_seconds,
        "outcome_breakdown": outcome_breakdown,
        "manual_status_breakdown": manual_status_breakdown,
        "manual_status_all_time_breakdown": manual_status_all_time_breakdown,
        "conversions_today": conversions_today,
        "per_caller": per_caller,
        "total_minutes_today": team_talk_minutes_today,
        "calls_per_hour": calls_per_hour,
        "calls_per_slot": calls_per_slot,
        "connect_rate": team_connect_rate,
        "avg_talk_seconds": team_avg_talk_seconds,
        "talk_minutes_today": team_talk_minutes_today,
        "idle_minutes_today": team_idle_minutes_today,
        "avg_gap_seconds": team_avg_gap_seconds,
        "longest_idle_seconds": team_longest_idle_seconds,
        "bunking_flag": team_bunking_flag,
        "speed_to_lead_min": team_speed_to_lead_min,
        "quality_avg": team_quality_avg,
        "comparison": comparison,
    }


@router.get("/caller-timeline")
async def caller_timeline(
    caller_id: UUID = Query(...),
    date: str | None = Query(None),
    ctx: dict = Depends(require_analytics_view),
):
    tenant_id = ctx["tenant_id"]
    db = get_supabase()
    
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
    try:
        day_start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")
        
    day_end = day_start + timedelta(days=1)
    day_start_iso = day_start.isoformat()
    day_end_iso = day_end.isoformat()
    
    calls = (
        await asyncio.to_thread(
            db.table("call_logs")
            .select("id,created_at,duration_seconds,outcome,manual_status,lead_id,leads(name,phone)")
            .eq("caller_id", str(caller_id))
            .eq("tenant_id", tenant_id)
            .gte("created_at", day_start_iso)
            .lt("created_at", day_end_iso)
            .order("created_at")
            .execute
        )
    ).data or []
    
    status_logs = (
        await asyncio.to_thread(
            db.table("caller_status_logs")
            .select("id,status,started_at,ended_at")
            .eq("caller_id", str(caller_id))
            .eq("tenant_id", tenant_id)
            .gte("started_at", day_start_iso)
            .lt("started_at", day_end_iso)
            .order("started_at")
            .execute
        )
    ).data or []
    
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
        lead = c.get("leads") or {}
        events.append({
            "type": "call",
            "id": c["id"],
            "started_at": c["created_at"],
            "duration_seconds": c.get("duration_seconds") or 0,
            "outcome": c.get("outcome"),
            "manual_status": c.get("manual_status"),
            "lead_name": lead.get("name") or "Unknown",
            "lead_phone": lead.get("phone") or "",
        })
        
    events.sort(key=lambda x: x["started_at"])
    
    return {"data": events}


@router.get("/qa-queue")
async def qa_queue(
    limit: int = Query(20, ge=1, le=100),
    ctx: dict = Depends(require_analytics_view),
):
    tenant_id = ctx["tenant_id"]
    db = get_supabase()
    
    res = (
        await asyncio.to_thread(
            db.table("call_logs")
            .select("id,created_at,duration_seconds,outcome,manual_status,recording_url,transcript,ai_summary,evaluation,lead_id,caller_id,leads(name,phone)")
            .eq("tenant_id", tenant_id)
            .not_.is_("evaluation", "null")
            .order("created_at", desc=True)
            .limit(200)
            .execute
        )
    ).data or []
    
    valid_calls = []
    for call in res:
        eval_data = call.get("evaluation")
        if isinstance(eval_data, dict) and "overall_score" in eval_data:
            try:
                call["overall_score"] = float(eval_data["overall_score"])
                valid_calls.append(call)
            except (ValueError, TypeError):
                pass
                
    valid_calls.sort(key=lambda x: x["overall_score"])
    return {"queue": valid_calls[:limit]}


@router.get("/telecalling/export")
async def export_telecalling(
    ctx: dict = Depends(require_analytics_view)
):
    tenant_id = ctx["tenant_id"]
    db = get_supabase()
    
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=90)).isoformat()
    
    rows = (
        await asyncio.to_thread(
            db.table("call_logs")
            .select("id,created_at,caller_id,lead_id,duration_seconds,outcome,disposition,manual_status,status,provider,feedback_source,recording_url,score,transcript,ai_summary,evaluation,callers(name),leads(name,phone)")
            .eq("tenant_id", tenant_id)
            .gte("created_at", start_date)
            .order("created_at", desc=True)
            .limit(5000)
            .execute
        )
    ).data or []
    
    output = io.StringIO()
    fieldnames = [
        "call_log_id", "created_at", "caller_id", "caller_name",
        "lead_id", "lead_name", "lead_phone", "duration_seconds",
        "outcome", "disposition", "manual_status", "status", "provider", "feedback_source", "recording_url", "score",
        "overall_score"
    ]
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for row in rows:
        eval_data = row.get("evaluation")
        overall_score = None
        if isinstance(eval_data, dict) and "overall_score" in eval_data:
            overall_score = eval_data.get("overall_score")
            
        writer.writerow({
            "call_log_id": row["id"],
            "created_at": row["created_at"],
            "caller_id": row.get("caller_id") or "",
            "caller_name": (row.get("callers") or {}).get("name") or "",
            "lead_id": row.get("lead_id") or "",
            "lead_name": (row.get("leads") or {}).get("name") or "",
            "lead_phone": (row.get("leads") or {}).get("phone") or "",
            "duration_seconds": row.get("duration_seconds") or 0,
            "outcome": row.get("outcome") or "",
            "disposition": row.get("disposition") or "",
            "manual_status": row.get("manual_status") or "",
            "status": row.get("status") or "",
            "provider": row.get("provider") or "",
            "feedback_source": row.get("feedback_source") or "",
            "recording_url": row.get("recording_url") or "",
            "score": row.get("score") or "",
            "overall_score": overall_score or ""
        })
        
    filename = f"telecalling_calls_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/funnel")
async def funnel_analytics(tenant_id: str = Depends(get_analytics_tenant_id)):
    db = get_supabase()
    week = _week_start()

    leads_all = (
        await asyncio.to_thread(
            db.table("leads")
            .select("id,segment,source,score,created_at")
            .eq("tenant_id", tenant_id)
            .execute
        )
    ).data or []

    total_leads = len(leads_all)

    by_segment: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    by_source: dict[str, int] = {
        "whatsapp": 0, "instagram": 0, "facebook": 0,
        "telegram": 0, "upload": 0, "manual": 0,
    }
    scores = []
    leads_this_week = 0
    score_histogram_raw: dict[str, int] = {
        "1-2": 0, "3-4": 0, "5-6": 0, "7-8": 0, "9-10": 0,
    }

    now = datetime.now(timezone.utc)
    hot_aging: dict[str, int] = {"<1d": 0, "1-3d": 0, "3-7d": 0, "7d+": 0}

    for lead in leads_all:
        seg = lead.get("segment")
        if seg in by_segment:
            by_segment[seg] += 1

        src = lead.get("source")
        if src in by_source:
            by_source[src] += 1

        score = lead.get("score")
        if score is not None:
            scores.append(score)
            if 1 <= score <= 2:
                score_histogram_raw["1-2"] += 1
            elif 3 <= score <= 4:
                score_histogram_raw["3-4"] += 1
            elif 5 <= score <= 6:
                score_histogram_raw["5-6"] += 1
            elif 7 <= score <= 8:
                score_histogram_raw["7-8"] += 1
            elif 9 <= score <= 10:
                score_histogram_raw["9-10"] += 1

        if (lead.get("created_at") or "") >= week:
            leads_this_week += 1

        # hot lead aging for segment A
        if seg == "A":
            created_str = lead.get("created_at") or ""
            if created_str:
                try:
                    created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    age_days = (now - created_dt.replace(tzinfo=timezone.utc if created_dt.tzinfo is None else created_dt.tzinfo)).days
                    if age_days < 1:
                        hot_aging["<1d"] += 1
                    elif age_days <= 3:
                        hot_aging["1-3d"] += 1
                    elif age_days <= 7:
                        hot_aging["3-7d"] += 1
                    else:
                        hot_aging["7d+"] += 1
                except Exception:
                    pass

    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    score_histogram = [
        {"range": r, "count": score_histogram_raw[r]}
        for r in ("1-2", "3-4", "5-6", "7-8", "9-10")
    ]
    hot_lead_aging = [
        {"bucket": b, "count": hot_aging[b]}
        for b in ("<1d", "1-3d", "3-7d", "7d+")
    ]

    return {
        "total_leads": total_leads,
        "by_segment": by_segment,
        "by_source": by_source,
        "leads_this_week": leads_this_week,
        "avg_score": avg_score,
        "score_histogram": score_histogram,
        "hot_lead_aging": hot_lead_aging,
    }


@router.get("/overview")
async def overview_analytics(
    tenant_id: str = Depends(get_dashboard_analytics_tenant_id),
    range: str = Query("7d"),
):
    """Dashboard root — KPIs and N-day series."""
    db = get_supabase()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    window_start_dt, days_iso = _range_params(range)

    leads_rows = (
        await asyncio.to_thread(
            db.table("leads")
            .select("id,phone,segment,score,source,created_at,converted_at,ai_enabled,deleted_at")
            .eq("tenant_id", tenant_id)
            .is_("deleted_at", "null")
            .execute
        )
    ).data or []

    daily_leads_map = {d: 0 for d in days_iso}
    by_segment = {"A": 0, "B": 0, "C": 0, "D": 0}
    channel_breakdown = {
        "whatsapp": 0, "instagram": 0, "facebook": 0,
        "telegram": 0, "upload": 0, "manual": 0,
    }
    converted_7d = 0
    converted_today = 0
    funnel_inquiries = 0
    funnel_engaged = 0
    funnel_hot = 0
    funnel_converted = 0
    week_start_for_funnel = now - timedelta(days=7)

    for lead in leads_rows:
        created = (lead.get("created_at") or "")[:10]
        if created in daily_leads_map:
            daily_leads_map[created] += 1
        converted_at = lead.get("converted_at")
        if converted_at:
            funnel_converted += 1
            if converted_at >= week_start_for_funnel.isoformat():
                converted_7d += 1
            if converted_at >= today_start.isoformat():
                converted_today += 1
        seg = lead.get("segment")
        if seg in by_segment:
            by_segment[seg] += 1
        src = lead.get("source")
        if src in channel_breakdown:
            channel_breakdown[src] += 1
        funnel_inquiries += 1
        if seg in ("A", "B"):
            funnel_engaged += 1
        if seg == "A":
            funnel_hot += 1

    total_leads = len(leads_rows)

    msgs_window = (
        await asyncio.to_thread(
            db.table("messages")
            .select("id,direction,is_ai_generated,created_at,lead_id")
            .eq("tenant_id", tenant_id)
            .gte("created_at", window_start_dt.isoformat())
            .execute
        )
    ).data or []

    daily_msgs_map = {d: {"inbound": 0, "outbound": 0, "ai": 0, "human": 0} for d in days_iso}
    ai_count = 0
    human_count = 0
    ai_handled_today = 0
    for m in msgs_window:
        day = (m.get("created_at") or "")[:10]
        direction = m.get("direction")
        if day in daily_msgs_map:
            if direction == "inbound":
                daily_msgs_map[day]["inbound"] += 1
            elif direction == "outbound":
                daily_msgs_map[day]["outbound"] += 1
                if m.get("is_ai_generated"):
                    daily_msgs_map[day]["ai"] += 1
                else:
                    daily_msgs_map[day]["human"] += 1
        if direction == "outbound":
            if m.get("is_ai_generated"):
                ai_count += 1
                if (m.get("created_at") or "") >= today_start.isoformat():
                    ai_handled_today += 1
            else:
                human_count += 1

    last_inbound: dict[str, str] = {}
    last_outbound: dict[str, str] = {}
    day_ago_iso = (now - timedelta(hours=24)).isoformat()
    for m in msgs_window:
        ts = m.get("created_at") or ""
        if ts < day_ago_iso:
            continue
        lid = m.get("lead_id")
        if not lid:
            continue
        if m.get("direction") == "inbound":
            if ts > last_inbound.get(lid, ""):
                last_inbound[lid] = ts
        elif m.get("direction") == "outbound":
            if ts > last_outbound.get(lid, ""):
                last_outbound[lid] = ts

    unreplied_24h = sum(
        1 for lid, ts in last_inbound.items()
        if last_outbound.get(lid, "") < ts
    )

    return {
        "daily_leads": [{"day": d, "count": daily_leads_map[d]} for d in days_iso],
        "daily_messages": [
            {
                "day": d,
                "inbound": daily_msgs_map[d]["inbound"],
                "outbound": daily_msgs_map[d]["outbound"],
                "ai": daily_msgs_map[d]["ai"],
                "human": daily_msgs_map[d]["human"],
            }
            for d in days_iso
        ],
        "funnel": {
            "inquiries": funnel_inquiries,
            "engaged": funnel_engaged,
            "hot": funnel_hot,
            "converted": funnel_converted,
        },
        "ai_vs_human": {"ai": ai_count, "human": human_count},
        "unreplied_24h": unreplied_24h,
        "converted_7d": converted_7d,
        "converted_today": converted_today,
        "ai_handled_today": ai_handled_today,
        "by_segment": by_segment,
        "channel_breakdown": channel_breakdown,
        "total_leads": total_leads,
    }


@router.get("/messaging")
async def messaging_analytics(
    tenant_id: str = Depends(get_analytics_tenant_id),
    channel: str = Query("all"),
    range: str = Query("7d"),
):
    """Messaging analytics with optional channel filter and date range."""
    db = get_supabase()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    window_start_dt, days_iso = _range_params(range)

    # Fetch messages within window
    q = (
        db.table("messages")
        .select("id,direction,is_ai_generated,reply_source,created_at,channel")
        .eq("tenant_id", tenant_id)
        .gte("created_at", window_start_dt.isoformat())
    )
    if channel != "all":
        q = q.eq("channel", channel)
    msgs = (await asyncio.to_thread(q.execute)).data or []

    # sent_today / received_today — always from today regardless of range
    today_q = (
        db.table("messages")
        .select("id,direction")
        .eq("tenant_id", tenant_id)
        .gte("created_at", today_start.isoformat())
    )
    if channel != "all":
        today_q = today_q.eq("channel", channel)
    msgs_today = (await asyncio.to_thread(today_q.execute)).data or []

    sent_today = sum(1 for m in msgs_today if m.get("direction") == "outbound")
    received_today = sum(1 for m in msgs_today if m.get("direction") == "inbound")

    # daily_messages series
    daily_msgs_map = {d: {"inbound": 0, "outbound": 0} for d in days_iso}
    outbound_total = 0
    outbound_ai = 0
    reply_source_counts: dict[str, int] = {"ai": 0, "knowledge": 0, "manual": 0, "unknown": 0}

    for m in msgs:
        day = (m.get("created_at") or "")[:10]
        if day in daily_msgs_map:
            direction = m.get("direction")
            if direction == "inbound":
                daily_msgs_map[day]["inbound"] += 1
            elif direction == "outbound":
                daily_msgs_map[day]["outbound"] += 1

        if m.get("direction") == "outbound":
            outbound_total += 1
            if m.get("is_ai_generated"):
                outbound_ai += 1

            # reply_source breakdown — outbound only (inbound has null reply_source)
            rs = m.get("reply_source")
            if rs in ("ai", "knowledge", "automation"):
                # treat "automation" as a sub-type; map to "ai" bucket if not already named
                key = rs if rs in reply_source_counts else "ai"
                reply_source_counts[key] += 1
            elif rs == "manual":
                reply_source_counts["manual"] += 1
            elif rs is None:
                if not m.get("is_ai_generated"):
                    reply_source_counts["manual"] += 1
                else:
                    reply_source_counts["unknown"] += 1

    ai_reply_rate: float | None = round(outbound_ai / outbound_total, 4) if outbound_total > 0 else None

    return {
        "sent_today": sent_today,
        "received_today": received_today,
        "ai_reply_rate": ai_reply_rate,
        "reply_source_breakdown": reply_source_counts,
        "daily_messages": [
            {"day": d, "inbound": daily_msgs_map[d]["inbound"], "outbound": daily_msgs_map[d]["outbound"]}
            for d in days_iso
        ],
    }


@router.get("/ad-performance")
async def ad_performance_summary(tenant_id: str = Depends(get_analytics_tenant_id)):
    db = get_supabase()
    from app.services.growth import build_ad_performance
    return build_ad_performance(tenant_id=tenant_id, db=db)


@router.get("/inbound")
async def inbound_analytics(
    range: str = Query("7d"),
    tenant_id: str = Depends(get_analytics_tenant_id),
):
    """New inbound leads acquired, split organic vs ad. Range: today|7d|30d."""
    db = get_supabase()
    start_dt, days_iso = _range_params(range)
    today_iso = datetime.now(timezone.utc).date().isoformat()

    try:
        rows = await asyncio.to_thread(
            db.table("leads")
            .select("id,source,ad_campaign_id,segment,created_at")
            .eq("tenant_id", tenant_id)
            .in_("source", list(INBOUND_SOURCES))
            .is_("deleted_at", "null")
            .gte("created_at", start_dt.isoformat())
            .execute
        )
        leads = rows.data or []
    except Exception as e:
        logger.error(f"inbound analytics error: {e}")
        leads = []
    return aggregate_inbound(leads, days_iso, today_iso)
