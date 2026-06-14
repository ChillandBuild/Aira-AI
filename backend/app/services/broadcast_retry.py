"""Broadcast auto-retry orchestrator.

Re-sends a broadcast's undelivered leads (Meta marketing-cap 131049 + silent drops)
at a client-chosen wall-clock time, up to a client-chosen number of attempts. Each
attempt is a child scheduled_broadcasts row executed by the existing
_process_scheduled_broadcasts job — this module only decides *who* and *when*.

Eligibility (a lead is retried only if ALL hold):
  - sent in a prior chain attempt with no delivered/read receipt anywhere in the chain
  - leads.whatsapp_undeliverable = false   (excludes wrong-number failures)
  - leads.opted_out = false
  - no inbound reply since the original send  (a reply bypasses the cap)
  - outbound_no_reply_count < 3              (existing disengagement suppression)
"""
import logging
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

DEFAULT_TZ = "Asia/Kolkata"
MIN_GAP_HOURS = 20  # marketing cap resets in 24h; guard so a chosen clock time has reset it
_REACHED_STATES = ("delivered", "read")
_CHUNK = 100


def _tenant_tz(db, tenant_id: str) -> ZoneInfo:
    try:
        row = (
            db.table("app_settings")
            .select("value")
            .eq("tenant_id", tenant_id)
            .eq("key", "timezone")
            .limit(1)
            .execute()
        )
        name = (row.data[0]["value"] if row.data else "") or DEFAULT_TZ
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def _parse_time(raw) -> dtime | None:
    if isinstance(raw, dtime):
        return raw
    if not raw:
        return None
    try:
        parts = str(raw).split(":")
        return dtime(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    except Exception:
        return None


def _parse_dt(raw) -> datetime | None:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _next_fire(last_sent_utc: datetime, retry_time: dtime, tz: ZoneInfo) -> datetime:
    """First occurrence of retry_time (tenant tz) that is >= last_sent + MIN_GAP_HOURS."""
    earliest_local = (last_sent_utc + timedelta(hours=MIN_GAP_HOURS)).astimezone(tz)
    cand = earliest_local.replace(
        hour=retry_time.hour, minute=retry_time.minute, second=0, microsecond=0
    )
    if cand < earliest_local:
        cand += timedelta(days=1)
    return cand.astimezone(timezone.utc)


def _eligible_leads(db, tenant_id: str, chain_ids: list[str], original_sent_utc: datetime) -> list[dict]:
    """Rebuild the undelivered-lead subset for the next attempt, newest recipient row per lead."""
    recips: list[dict] = []
    for i in range(0, len(chain_ids), _CHUNK):
        batch = chain_ids[i:i + _CHUNK]
        res = (
            db.table("broadcast_recipients")
            .select("lead_id,phone,name,meta_message_id,extra_cols,created_at")
            .eq("tenant_id", tenant_id)
            .in_("broadcast_id", batch)
            .execute()
        )
        recips.extend(res.data or [])

    # Latest recipient row per lead (for rebuilding the message) + all chain message ids.
    latest_by_lead: dict[str, dict] = {}
    msg_ids: list[str] = []
    msg_to_lead: dict[str, str] = {}
    for r in recips:
        lid = r.get("lead_id")
        mid = r.get("meta_message_id")
        if mid:
            msg_ids.append(mid)
            if lid:
                msg_to_lead[mid] = lid
        if not lid:
            continue
        prev = latest_by_lead.get(lid)
        if prev is None or (r.get("created_at") or "") > (prev.get("created_at") or ""):
            latest_by_lead[lid] = r

    if not latest_by_lead:
        return []

    # Leads that got a delivered/read receipt anywhere in the chain — already reached.
    reached: set[str] = set()
    for i in range(0, len(msg_ids), _CHUNK):
        batch = msg_ids[i:i + _CHUNK]
        res = (
            db.table("messages")
            .select("meta_message_id")
            .eq("tenant_id", tenant_id)
            .in_("meta_message_id", batch)
            .in_("delivery_status", list(_REACHED_STATES))
            .execute()
        )
        for m in (res.data or []):
            lid = msg_to_lead.get(m.get("meta_message_id"))
            if lid:
                reached.add(lid)

    candidates = [lid for lid in latest_by_lead if lid not in reached]
    if not candidates:
        return []

    # Apply exclusion rules against the live lead record.
    ok: set[str] = set()
    for i in range(0, len(candidates), _CHUNK):
        batch = candidates[i:i + _CHUNK]
        res = (
            db.table("leads")
            .select("id,whatsapp_undeliverable,opted_out,outbound_no_reply_count,last_inbound_at")
            .eq("tenant_id", tenant_id)
            .in_("id", batch)
            .execute()
        )
        for lead in (res.data or []):
            if lead.get("whatsapp_undeliverable") or lead.get("opted_out"):
                continue
            if (lead.get("outbound_no_reply_count") or 0) >= 3:
                continue
            last_in = _parse_dt(lead.get("last_inbound_at"))
            if last_in and last_in > original_sent_utc:
                continue  # replied since the original send — cap bypassed, don't re-spam
            ok.add(lead["id"])

    return [
        {
            "phone": latest_by_lead[lid].get("phone"),
            "name": latest_by_lead[lid].get("name"),
            "extra_cols": latest_by_lead[lid].get("extra_cols") or {},
        }
        for lid in candidates
        if lid in ok and latest_by_lead[lid].get("phone")
    ]


def _mark_completed(db, parent_id: str) -> None:
    db.table("scheduled_broadcasts").update(
        {"retry_completed_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", parent_id).execute()


def _process_chain(db, original: dict) -> None:
    parent_id = original["id"]
    tenant_id = original["tenant_id"]
    max_attempts = original.get("retry_max_attempts") or 2
    retry_time = _parse_time(original.get("retry_time"))
    if not retry_time:
        _mark_completed(db, parent_id)
        return

    children = (
        db.table("scheduled_broadcasts")
        .select("id,status,retry_attempt,executed_at,fire_at,created_at")
        .eq("retry_of", parent_id)
        .order("retry_attempt")
        .execute()
        .data or []
    )

    if len(children) >= max_attempts:
        _mark_completed(db, parent_id)
        return

    latest = children[-1] if children else original
    if (latest.get("status") or "done") in ("pending", "running"):
        return  # previous attempt still in flight; wait for it to finish + receipts
    # A "failed" latest attempt (e.g. no sending number available at the time) is
    # terminal but sent nothing — fall through and schedule the next window so the
    # chain self-heals once a number is available again, bounded by max_attempts.

    last_sent = _parse_dt(latest.get("executed_at")) or _parse_dt(latest.get("fire_at")) \
        or _parse_dt(latest.get("created_at"))
    if not last_sent:
        return

    tz = _tenant_tz(db, tenant_id)
    if datetime.now(timezone.utc) < _next_fire(last_sent, retry_time, tz):
        return

    original_sent = _parse_dt(original.get("executed_at")) or _parse_dt(original.get("fire_at")) or last_sent
    chain_ids = [parent_id] + [c["id"] for c in children]
    eligible = _eligible_leads(db, tenant_id, chain_ids, original_sent)

    if not eligible:
        _mark_completed(db, parent_id)
        logger.info(f"Broadcast retry chain {parent_id} completed — no eligible leads left")
        return

    attempt_no = len(children) + 1
    now = datetime.now(timezone.utc).isoformat()
    db.table("scheduled_broadcasts").insert({
        "tenant_id": tenant_id,
        "template_name": original["template_name"],
        "schedule_type": "scheduled",
        "fire_at": now,
        "status": "pending",
        "leads_json": eligible,
        "variable_mapping": original.get("variable_mapping") or [],
        "opt_in_source": original.get("opt_in_source"),
        "tag_id": original.get("tag_id"),
        "retry_of": parent_id,
        "retry_attempt": attempt_no,
    }).execute()
    logger.info(f"Broadcast retry chain {parent_id}: queued attempt {attempt_no} for {len(eligible)} leads")


def process_due_retries() -> None:
    """APScheduler entry — advance every active retry chain that is due."""
    db = get_supabase()
    originals = (
        db.table("scheduled_broadcasts")
        .select("id,tenant_id,template_name,variable_mapping,opt_in_source,tag_id,"
                "retry_max_attempts,retry_time,executed_at,fire_at")
        .eq("retry_enabled", True)
        .is_("retry_of", "null")
        .is_("retry_completed_at", "null")
        .eq("status", "done")
        .execute()
        .data or []
    )
    for original in originals:
        try:
            _process_chain(db, original)
        except Exception as exc:
            logger.error(f"Broadcast retry chain {original.get('id')} failed: {exc}")
