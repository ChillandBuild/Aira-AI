import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

_background_tasks: set = set()

SEGMENT_DEPTH = {"D": 0, "C": 1, "B": 2, "A": 3}
# 1d/1w/1m cadences retired in migration 095 — they sent freeform text outside
# the WhatsApp 24h window. Automated re-engagement is now handled by the
# reengagement_steps engine (migration 094). callback cadence stays.
FOLLOW_UP_CADENCES = ()
PLATFORMS = {"instagram", "facebook", "google", "whatsapp"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_platform(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in PLATFORMS:
        return normalized
    return None


def stage_depth(segment: str | None) -> int:
    return SEGMENT_DEPTH.get((segment or "D").upper(), 0)


def get_or_create_campaign(
    db,
    *,
    tenant_id: str,
    platform: str | None,
    campaign_name: str | None,
    external_campaign_id: str | None = None,
    spend_inr: float | None = None,
) -> dict[str, Any] | None:
    normalized_platform = normalize_platform(platform) or ("instagram" if campaign_name or external_campaign_id else None)
    normalized_name = (campaign_name or "").strip() or None
    normalized_external_id = (external_campaign_id or "").strip() or None
    if not normalized_platform or not (normalized_name or normalized_external_id):
        return None

    existing = None
    if normalized_external_id:
        result = (
            db.table("ad_campaigns")
            .select("*")
            .eq("external_campaign_id", normalized_external_id)
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
        existing = (result.data or [None])[0]
    if not existing and normalized_name:
        result = (
            db.table("ad_campaigns")
            .select("*")
            .eq("platform", normalized_platform)
            .eq("campaign_name", normalized_name)
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
        existing = (result.data or [None])[0]

    updates: dict[str, Any] = {}
    if normalized_name:
        updates["campaign_name"] = normalized_name
    if normalized_external_id:
        updates["external_campaign_id"] = normalized_external_id
    if spend_inr is not None:
        updates["spend_inr"] = spend_inr

    if existing:
        if updates:
            refreshed = (
                db.table("ad_campaigns")
                .update(updates)
                .eq("id", existing["id"])
                .eq("tenant_id", tenant_id)
                .execute()
            )
            if refreshed.data:
                return refreshed.data[0]
        return existing

    payload = {
        "platform": normalized_platform,
        "campaign_name": normalized_name or normalized_external_id,
        "external_campaign_id": normalized_external_id,
        "spend_inr": spend_inr or 0,
        "tenant_id": tenant_id,
    }
    created = db.table("ad_campaigns").insert(payload).execute()
    return (created.data or [None])[0]


def _fire_whatsapp_alert(tenant_id: str, lead_id: str, from_segment: str | None, to_segment: str) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("record_stage_event: no running event loop, skipping WhatsApp alert for lead %s", lead_id)
        try:
            get_supabase().table("incidents").insert({
                "tenant_id": tenant_id,
                "type": "whatsapp_alert_failed",
                "detail": {"lead_id": lead_id, "to_segment": to_segment, "reason": "no_running_event_loop"},
            }).execute()
        except Exception:
            logger.exception("Failed to record whatsapp_alert_failed incident for lead %s", lead_id)
        return

    async def _run() -> None:
        try:
            from app.services.whatsapp_notify import send_admin_whatsapp_alerts
            await send_admin_whatsapp_alerts(tenant_id, lead_id, from_segment, to_segment)
        except Exception:
            logger.exception("WhatsApp alert task failed for lead %s", lead_id)

    task = loop.create_task(_run())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def record_stage_event(
    lead_id: str,
    *,
    to_segment: str,
    event_type: str,
    from_segment: str | None = None,
    metadata: dict[str, Any] | None = None,
    tenant_id: str | None = None,
    db=None,
) -> None:
    db = db or get_supabase()
    payload: dict[str, Any] = {
        "lead_id": str(lead_id),
        "from_segment": from_segment,
        "to_segment": to_segment,
        "event_type": event_type,
        "metadata": metadata or {},
    }
    if tenant_id:
        payload["tenant_id"] = tenant_id
    db.table("lead_stage_events").insert(payload).execute()
    if event_type == "segment_changed" and tenant_id and from_segment and from_segment != to_segment:
        _fire_whatsapp_alert(tenant_id, lead_id, from_segment, to_segment)


def cancel_pending_follow_ups(
    lead_id: str,
    *,
    reason: str,
    db=None,
) -> None:
    db = db or get_supabase()
    db.table("follow_up_jobs").update(
        {
            "status": "canceled",
            "skip_reason": reason,
        }
    ).eq("lead_id", str(lead_id)).eq("status", "pending").execute()


def sync_follow_up_jobs(
    lead_id: str,
    *,
    segment: str | None,
    phone: str | None,
    converted_at: str | None,
    ai_enabled: bool,
    reason: str,
    tenant_id: str | None = None,
    anchor_time: datetime | None = None,
    db=None,
) -> list[dict[str, Any]]:
    db = db or get_supabase()
    if not FOLLOW_UP_CADENCES:
        return []
    current_segment = (segment or "D").upper()
    if converted_at or not ai_enabled or not phone or current_segment not in {"A", "B"}:
        cancel_pending_follow_ups(
            lead_id,
            reason=f"ineligible:{reason}",
            db=db,
        )
        return []

    cancel_pending_follow_ups(
        lead_id,
        reason=f"rescheduled:{reason}",
        db=db,
    )
    anchor = anchor_time or utcnow()
    rows = [
        {
            "lead_id": str(lead_id),
            "channel": "whatsapp",
            "cadence": cadence,
            "status": "pending",
            "scheduled_for": (anchor + offset).isoformat(),
            "tenant_id": tenant_id,
        }
        for cadence, offset in FOLLOW_UP_CADENCES
    ]
    inserted = db.table("follow_up_jobs").insert(rows).execute()
    return inserted.data or rows


def build_follow_up_summary(db=None) -> dict[str, Any]:
    db = db or get_supabase()
    now = utcnow()
    window_start = (now - timedelta(days=7)).isoformat()

    pending = db.table("follow_up_jobs").select("*").eq("status", "pending").order("scheduled_for").execute().data or []
    sent = db.table("follow_up_jobs").select("*").eq("status", "sent").gte("sent_at", window_start).execute().data or []
    failed = db.table("follow_up_jobs").select("*").eq("status", "failed").gte("updated_at", window_start).execute().data or []
    skipped = db.table("follow_up_jobs").select("*").in_("status", ["skipped", "canceled"]).gte("updated_at", window_start).execute().data or []

    lead_ids = list({job["lead_id"] for job in pending[:8]})
    lead_map: dict[str, dict[str, Any]] = {}
    if lead_ids:
        leads = (
            db.table("leads")
            .select("id,name,phone,segment")
            .in_("id", lead_ids)
            .execute()
            .data
            or []
        )
        lead_map = {lead["id"]: lead for lead in leads}

    by_cadence = []
    for cadence, _ in FOLLOW_UP_CADENCES:
        cadence_pending = [job for job in pending if job.get("cadence") == cadence]
        cadence_sent = [job for job in sent if job.get("cadence") == cadence]
        by_cadence.append(
            {
                "cadence": cadence,
                "pending": len(cadence_pending),
                "due_now": sum(1 for job in cadence_pending if (job.get("scheduled_for") or "") <= now.isoformat()),
                "sent_7d": len(cadence_sent),
            }
        )

    queue = []
    for job in pending[:8]:
        lead = lead_map.get(job["lead_id"], {})
        queue.append(
            {
                "id": job["id"],
                "lead_id": job["lead_id"],
                "cadence": job["cadence"],
                "status": job["status"],
                "scheduled_for": job["scheduled_for"],
                "sent_at": job.get("sent_at"),
                "message_preview": job.get("message_preview"),
                "skip_reason": job.get("skip_reason"),
                "last_error": job.get("last_error"),
                "lead_name": lead.get("name"),
                "phone": lead.get("phone"),
                "segment": lead.get("segment"),
            }
        )

    return {
        "pending": len(pending),
        "due_now": sum(1 for job in pending if (job.get("scheduled_for") or "") <= now.isoformat()),
        "sent_7d": len(sent),
        "failed_7d": len(failed),
        "skipped_7d": len(skipped),
        "by_cadence": by_cadence,
        "queue": queue,
    }


def build_ad_performance(*, tenant_id: str, db=None) -> dict[str, Any]:
    db = db or get_supabase()
    campaigns = db.table("ad_campaigns").select("*").eq("tenant_id", tenant_id).order("created_at", desc=True).execute().data or []
    if not campaigns:
        return {
            "totals": {
                "campaigns": 0,
                "tracked_leads": 0,
                "progressive_rate": 0,
                "conversion_rate": 0,
                "recommend_increase": 0,
                "recommend_decrease": 0,
            },
            "campaigns": [],
        }

    leads = db.table("leads").select(
        "id,ad_campaign_id,segment,converted_at,created_at,ad_name,ad_set_name"
    ).eq("tenant_id", tenant_id).execute().data or []
    tracked_leads = [lead for lead in leads if lead.get("ad_campaign_id")]
    lead_ids = [lead["id"] for lead in tracked_leads]
    events = []
    if lead_ids:
        events = (
            db.table("lead_stage_events")
            .select("lead_id,to_segment,event_type,created_at")
            .in_("lead_id", lead_ids)
            .eq("tenant_id", tenant_id)
            .order("created_at")
            .execute()
            .data
            or []
        )

    events_by_lead: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        events_by_lead.setdefault(event["lead_id"], []).append(event)

    campaign_rows = []
    increase = 0
    decrease = 0
    progressive_total = 0
    converted_total = 0

    for campaign in campaigns:
        rows = [lead for lead in tracked_leads if lead.get("ad_campaign_id") == campaign["id"]]
        if not rows:
            continue

        total = len(rows)
        progressive = 0
        converted = 0
        engaged = 0
        hot = 0
        segment_mix = {"A": 0, "B": 0, "C": 0, "D": 0}
        ad_sets: list[str] = []
        creatives: list[str] = []

        for lead in rows:
            segment = (lead.get("segment") or "D").upper()
            segment_mix[segment] += 1
            if segment in {"A", "B"}:
                engaged += 1
            if segment == "A":
                hot += 1
            if lead.get("converted_at"):
                converted += 1

            lead_events = events_by_lead.get(lead["id"]) or []
            initial_segment = lead_events[0]["to_segment"] if lead_events else segment
            deepest_segment = max(
                [stage_depth(initial_segment)] + [stage_depth(evt.get("to_segment")) for evt in lead_events]
            )
            if deepest_segment > stage_depth(initial_segment) or lead.get("converted_at"):
                progressive += 1

            if lead.get("ad_set_name"):
                ad_sets.append(lead["ad_set_name"])
            if lead.get("ad_name"):
                creatives.append(lead["ad_name"])

        progressive_rate = progressive / total if total else 0
        conversion_rate = converted / total if total else 0
        engaged_rate = engaged / total if total else 0
        hot_rate = hot / total if total else 0
        cd_share = (segment_mix["C"] + segment_mix["D"]) / total if total else 0
        spend = float(campaign.get("spend_inr") or 0)

        if total >= 3 and (conversion_rate >= 0.18 or progressive_rate >= 0.55 or hot_rate >= 0.25):
            recommendation = "increase"
            increase += 1
        elif total >= 3 and cd_share >= 0.65 and progressive_rate < 0.3:
            recommendation = "decrease"
            decrease += 1
        else:
            recommendation = "hold"

        suggestions: list[str] = []
        if total < 3:
            suggestions.append("Observe a little longer before changing budget; the sample is still small.")
        elif recommendation == "increase":
            suggestions.append("Budget up: this campaign is producing more progressive A/B leads and stronger conversion signals.")
        elif recommendation == "decrease":
            suggestions.append("Budget down: too many leads are stalling in C/D without enough depth or conversions.")
        else:
            suggestions.append("Hold budget: performance is mixed, so refine targeting and keep gathering signal.")

        if progressive_rate >= 0.45 and conversion_rate < 0.1:
            suggestions.append("Lead nurture gap: people are engaging, but they are not closing. Tighten callback speed and follow-up messaging.")
        if cd_share > 0.6:
            suggestions.append("Targeting tweak: narrow the audience or use stronger qualifying hooks in the creative.")
        if engaged_rate > 0.35 and hot_rate < 0.15:
            suggestions.append("Creative tweak: stronger proof, fee clarity, or visit CTA could move warm leads into Segment A.")

        campaign_rows.append(
            {
                "id": campaign["id"],
                "platform": campaign["platform"],
                "campaign_name": campaign["campaign_name"],
                "external_campaign_id": campaign.get("external_campaign_id"),
                "spend_inr": spend,
                "total_leads": total,
                "progressive_leads": progressive,
                "conversion_count": converted,
                "engaged_count": engaged,
                "hot_count": hot,
                "segment_mix": segment_mix,
                "progressive_rate": round(progressive_rate, 4),
                "conversion_rate": round(conversion_rate, 4),
                "engaged_rate": round(engaged_rate, 4),
                "cost_per_lead": round(spend / total, 2) if spend and total else None,
                "cost_per_conversion": round(spend / converted, 2) if spend and converted else None,
                "budget_recommendation": recommendation,
                "suggestions": suggestions,
                "adset_examples": list(dict.fromkeys(ad_sets))[:3],
                "creative_examples": list(dict.fromkeys(creatives))[:3],
            }
        )
        progressive_total += progressive
        converted_total += converted

    tracked_count = len(tracked_leads)
    return {
        "totals": {
            "campaigns": len(campaign_rows),
            "tracked_leads": tracked_count,
            "progressive_rate": round(progressive_total / tracked_count, 4) if tracked_count else 0,
            "conversion_rate": round(converted_total / tracked_count, 4) if tracked_count else 0,
            "recommend_increase": increase,
            "recommend_decrease": decrease,
        },
        "campaigns": sorted(
            campaign_rows,
            key=lambda row: (row["budget_recommendation"] == "increase", row["progressive_rate"], row["conversion_rate"]),
            reverse=True,
        ),
    }
