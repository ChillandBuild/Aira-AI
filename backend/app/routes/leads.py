import csv
import io
import json
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from groq import Groq
from pydantic import BaseModel
from app.config import settings
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, get_tenant_and_role, get_owner_tenant_id
from app.models.schemas import Lead, LeadUpdate, LeadWithMessages, Message, PaginatedResponse
from app.services.ai_reply import send_whatsapp, send_instagram, send_facebook, get_last_send_error
from app.services.growth import record_stage_event, sync_follow_up_jobs
from app.services.assignment import record_assignment_event

logger = logging.getLogger(__name__)
router = APIRouter()


from app.services.groq_client import get_groq_client
_BRIEF_MODEL = "llama-3.3-70b-versatile"


class PreCallBriefResponse(BaseModel):
    brief: str
    opener: str


class ConvertPayload(BaseModel):
    notes: str | None = None


class AiToggle(BaseModel):
    enabled: bool


class HumanMessage(BaseModel):
    content: str


class AssignPayload(BaseModel):
    caller_id: str | None = None


class BulkAssignPayload(BaseModel):
    lead_ids: list[UUID]
    caller_id: str | None = None


class CustomBroadcastRequest(BaseModel):
    message: str
    segment: str | None = None
    source_filter: str | None = None
    broadcast_id: str | None = None
    ad_campaign_id: str | None = None


@router.get("/", response_model=PaginatedResponse)
async def list_leads(
    segment: str | None = Query(None, pattern="^[ABCD]$"),
    assigned_to: str | None = Query(None),
    source_filter: str | None = Query(None),
    broadcast_id: str | None = Query(None),
    ad_campaign_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    ctx: dict = Depends(get_tenant_and_role),
):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    offset = (page - 1) * limit
    query = (db.table("leads").select("*", count="exact")
             .eq("tenant_id", tenant_id)
             .is_("deleted_at", "null")
             .neq("opted_out", True)
             .neq("whatsapp_undeliverable", True))
    if segment:
        query = query.eq("segment", segment)
    if ctx.get("role") == "caller" and ctx.get("caller_id"):
        query = query.eq("assigned_to", ctx["caller_id"])
    elif assigned_to:
        query = query.eq("assigned_to", assigned_to)

    # Apply medium / campaign / broadcast filters
    INBOUND_SOURCES = ('whatsapp', 'instagram', 'facebook', 'telegram')
    if source_filter == "inbound":
        query = query.in_("source", list(INBOUND_SOURCES))
    elif source_filter == "organic":
        query = query.in_("source", list(INBOUND_SOURCES)).is_("ad_campaign_id", "null")
    elif source_filter == "meta_ads":
        query = query.in_("source", list(INBOUND_SOURCES)).not_.is_("ad_campaign_id", "null")
        if ad_campaign_id:
            query = query.eq("ad_campaign_id", ad_campaign_id)
    elif source_filter == "broadcast":
        if broadcast_id:
            br_result = db.table("broadcast_recipients").select("lead_id").eq("broadcast_id", broadcast_id).eq("tenant_id", tenant_id).execute()
            lead_ids = [r["lead_id"] for r in (br_result.data or []) if r.get("lead_id")]
            if not lead_ids:
                return PaginatedResponse(
                    data=[],
                    total=0,
                    page=page,
                    limit=limit,
                )
            query = query.in_("id", lead_ids)

    result = query.order("score", desc=True).range(offset, offset + limit - 1).execute()
    leads_data = result.data or []

    # Enrichment
    lead_ids = [l["id"] for l in leads_data]
    if lead_ids:
        # 1. Fetch latest inbound message time for 24h window
        inbound_msgs = (
            db.table("messages")
            .select("lead_id,created_at")
            .in_("lead_id", lead_ids)
            .eq("direction", "inbound")
            .eq("tenant_id", tenant_id)
            .execute()
        )
        last_inbound_by_lead = {}
        for m in (inbound_msgs.data or []):
            lid = m["lead_id"]
            msg_time = m["created_at"]
            if lid not in last_inbound_by_lead or msg_time > last_inbound_by_lead[lid]:
                last_inbound_by_lead[lid] = msg_time

        # 2. Fetch broadcast sent time if filtered by broadcast
        br_time_by_lead = {}
        if source_filter == "broadcast" and broadcast_id:
            br_times = (
                db.table("broadcast_recipients")
                .select("lead_id,created_at")
                .eq("broadcast_id", broadcast_id)
                .in_("lead_id", lead_ids)
                .eq("tenant_id", tenant_id)
                .execute()
            )
            br_time_by_lead = {r["lead_id"]: r["created_at"] for r in (br_times.data or []) if r.get("lead_id")}

        for lead in leads_data:
            lead["last_inbound_at"] = last_inbound_by_lead.get(lead["id"])
            if lead["id"] in br_time_by_lead:
                lead["broadcast_sent_at"] = br_time_by_lead[lead["id"]]

    return PaginatedResponse(
        data=leads_data,
        total=result.count or 0,
        page=page,
        limit=limit,
    )


@router.post("/broadcast")
async def broadcast_custom_message(
    body: CustomBroadcastRequest,
    ctx: dict = Depends(get_tenant_and_role),
):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]

    # Step 1: Query all leads matching filters (no pagination)
    query = (db.table("leads").select("id,phone,source,ig_user_id,tg_user_id,fb_user_id")
             .eq("tenant_id", tenant_id)
             .is_("deleted_at", "null")
             .neq("opted_out", True)
             .neq("whatsapp_undeliverable", True))

    if body.segment:
        query = query.eq("segment", body.segment)

    # Apply source filter
    INBOUND_SOURCES = ('whatsapp', 'instagram', 'facebook', 'telegram')
    if body.source_filter == "inbound":
        query = query.in_("source", list(INBOUND_SOURCES))
    elif body.source_filter == "organic":
        query = query.in_("source", list(INBOUND_SOURCES)).is_("ad_campaign_id", "null")
    elif body.source_filter == "meta_ads":
        query = query.in_("source", list(INBOUND_SOURCES)).not_.is_("ad_campaign_id", "null")
        if body.ad_campaign_id:
            query = query.eq("ad_campaign_id", body.ad_campaign_id)
    elif body.source_filter == "broadcast":
        if body.broadcast_id:
            br_result = db.table("broadcast_recipients").select("lead_id").eq("broadcast_id", body.broadcast_id).eq("tenant_id", tenant_id).execute()
            lead_ids = [r["lead_id"] for r in (br_result.data or []) if r.get("lead_id")]
            if not lead_ids:
                return {"sent": 0, "failed": 0, "skipped_window": 0, "total": 0}
            query = query.in_("id", lead_ids)

    # Hard Invariant: bulk-send rejects leads with null opt_in_source
    query = query.not_.is_("opt_in_source", "null")

    result = query.execute()
    targets = result.data or []
    if not targets:
        return {"sent": 0, "failed": 0, "skipped_window": 0, "total": 0}

    # Step 2: Fetch leads with inbound message in the last 24h
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    lead_ids = [t["id"] for t in targets]

    recent = (
        db.table("messages")
        .select("lead_id")
        .eq("direction", "inbound")
        .eq("tenant_id", tenant_id)
        .gte("created_at", cutoff)
        .in_("lead_id", lead_ids)
        .execute()
    )
    eligible_ids = {r["lead_id"] for r in (recent.data or [])}

    sent = 0
    failed = 0
    skipped_window = 0

    for t in targets:
        lead_id = t["id"]
        source = t.get("source", "whatsapp")

        # Telegram has no 24h window
        if source != "telegram" and lead_id not in eligible_ids:
            skipped_window += 1
            continue

        channel = (
            "instagram" if source == "instagram"
            else "telegram" if source == "telegram"
            else "facebook" if source == "facebook"
            else "whatsapp"
        )

        sid = None
        try:
            if channel == "instagram":
                ig_id = t.get("ig_user_id")
                if ig_id:
                    sid = await send_instagram(ig_id, body.message, tenant_id=tenant_id)
            elif channel == "telegram":
                tg_id = t.get("tg_user_id")
                if tg_id:
                    from app.services.ai_reply import send_telegram
                    sid = await send_telegram(tg_id, body.message, tenant_id=tenant_id)
            elif channel == "facebook":
                fb_id = t.get("fb_user_id")
                if fb_id:
                    sid = await send_facebook(fb_id, body.message, tenant_id=tenant_id)
            else:
                phone = t.get("phone")
                if phone:
                    sid = await send_whatsapp(phone, body.message, tenant_id=tenant_id)
        except Exception as e:
            logger.error(f"Failed to send broadcast message to lead {lead_id} on {channel}: {e}")

        if sid:
            sent += 1
            sid_field = (
                "tg_message_id" if channel == "telegram"
                else "fb_message_id" if channel == "facebook"
                else "meta_message_id"
            )
            db.table("messages").insert({
                "lead_id": str(lead_id),
                "tenant_id": tenant_id,
                "direction": "outbound",
                "channel": channel,
                "content": body.message,
                "is_ai_generated": False,
                sid_field: sid,
            }).execute()
            db.table("leads").update({"needs_human_intervention": False}).eq("id", str(lead_id)).eq("tenant_id", tenant_id).execute()
        else:
            failed += 1

    return {
        "total": len(targets),
        "sent": sent,
        "failed": failed,
        "skipped_window": skipped_window,
    }


@router.patch("/{lead_id}/assign")
async def assign_lead(
    lead_id: str,
    payload: AssignPayload,
    ctx: dict = Depends(get_tenant_and_role),
):
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner only")
    db = get_supabase()
    
    # Fetch current lead info to check previous caller and other meta
    lead = db.table("leads").select("name, segment, score, assigned_to").eq("id", lead_id).eq("tenant_id", ctx["tenant_id"]).maybe_single().execute()
    if not lead.data:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    prev_caller_id = lead.data.get("assigned_to")
    segment = lead.data.get("segment")
    score = lead.data.get("score")
    
    caller_name = None
    if payload.caller_id:
        caller = db.table("callers").select("name").eq("id", payload.caller_id).eq("tenant_id", ctx["tenant_id"]).maybe_single().execute()
        if caller.data:
            caller_name = caller.data.get("name")
            
    prev_caller_name = None
    if prev_caller_id:
        prev_caller = db.table("callers").select("name").eq("id", prev_caller_id).eq("tenant_id", ctx["tenant_id"]).maybe_single().execute()
        if prev_caller.data:
            prev_caller_name = prev_caller.data.get("name")

    assigned_at = datetime.now(timezone.utc).isoformat() if payload.caller_id else None
    db.table("leads").update({
        "assigned_to": payload.caller_id,
        "assigned_at": assigned_at
    }).eq("id", lead_id).eq("tenant_id", ctx["tenant_id"]).execute()
    
    if payload.caller_id:
        event_type = "reassigned" if prev_caller_id and str(prev_caller_id) != str(payload.caller_id) else "assigned"
        record_assignment_event(
            lead_id=lead_id,
            tenant_id=ctx["tenant_id"],
            segment=segment,
            caller_id=payload.caller_id,
            caller_name=caller_name,
            reason="manual_assign",
            method="admin",
            score=score,
            event_type=event_type,
            prev_caller_id=prev_caller_id,
            prev_caller_name=prev_caller_name,
            db=db
        )
        try:
            new_caller_uid = None
            new_caller_res = db.table("callers").select("user_id").eq("id", payload.caller_id).eq("tenant_id", ctx["tenant_id"]).maybe_single().execute()
            if new_caller_res.data:
                new_caller_uid = new_caller_res.data.get("user_id")

            prev_caller_uid = None
            if prev_caller_id:
                prev_caller_res = db.table("callers").select("user_id").eq("id", prev_caller_id).eq("tenant_id", ctx["tenant_id"]).maybe_single().execute()
                if prev_caller_res.data:
                    prev_caller_uid = prev_caller_res.data.get("user_id")

            from app.services.notify import notify_user
            lead_name = lead.data.get("name") or "Unknown Lead"
            
            if new_caller_uid:
                notify_user(
                    ctx["tenant_id"],
                    new_caller_uid,
                    "lead_assigned",
                    "New Lead Assigned" if event_type == "assigned" else "Lead Reassigned",
                    f"Lead '{lead_name}' was assigned to you by Admin." if event_type == "assigned" else f"Lead '{lead_name}' was reassigned to you by Admin.",
                    db=db,
                )
                
            if prev_caller_uid and prev_caller_uid != new_caller_uid:
                notify_user(
                    ctx["tenant_id"],
                    prev_caller_uid,
                    "lead_reassigned",
                    "Lead Reassigned",
                    f"Lead '{lead_name}' has been reassigned to another caller.",
                    db=db,
                )
        except Exception as notify_err:
            logger.warning(f"Failed to notify caller on manual assign: {notify_err}")

    try:
        from app.services.notify import clear_pool_notifications_for_lead
        clear_pool_notifications_for_lead(ctx["tenant_id"], lead_id, db=db)
    except Exception:
        pass
        
    return {"success": True}


@router.post("/bulk-assign")
async def bulk_assign(
    payload: BulkAssignPayload,
    ctx: dict = Depends(get_tenant_and_role),
):
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner only")
    if not payload.lead_ids:
        return {"success": True, "count": 0}
        
    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    
    # Fetch all leads details to be assigned
    lead_ids_str = [str(lid) for lid in payload.lead_ids]
    leads = db.table("leads").select("id, segment, score, assigned_to").in_("id", lead_ids_str).eq("tenant_id", tenant_id).execute().data or []
    
    caller_name = None
    if payload.caller_id:
        caller = db.table("callers").select("name").eq("id", payload.caller_id).eq("tenant_id", tenant_id).maybe_single().execute()
        if caller.data:
            caller_name = caller.data.get("name")
            
    # Batch query caller names for prev_caller names to avoid N queries
    prev_caller_ids = list({l["assigned_to"] for l in leads if l.get("assigned_to")})
    prev_caller_names = {}
    if prev_caller_ids:
        callers = db.table("callers").select("id, name").in_("id", prev_caller_ids).eq("tenant_id", tenant_id).execute().data or []
        prev_caller_names = {c["id"]: c["name"] for c in callers}
        
    assigned_at = datetime.now(timezone.utc).isoformat() if payload.caller_id else None
    
    for lead in leads:
        lead_id = lead["id"]
        prev_caller_id = lead.get("assigned_to")
        segment = lead.get("segment")
        score = lead.get("score")
        
        db.table("leads").update({
            "assigned_to": payload.caller_id,
            "assigned_at": assigned_at
        }).eq("id", lead_id).eq("tenant_id", tenant_id).execute()
        
        if payload.caller_id:
            event_type = "reassigned" if prev_caller_id and str(prev_caller_id) != str(payload.caller_id) else "assigned"
            record_assignment_event(
                lead_id=lead_id,
                tenant_id=tenant_id,
                segment=segment,
                caller_id=payload.caller_id,
                caller_name=caller_name,
                reason="bulk_assign",
                method="admin",
                score=score,
                event_type=event_type,
                prev_caller_id=prev_caller_id,
                prev_caller_name=prev_caller_names.get(prev_caller_id),
                db=db
            )
            try:
                from app.services.notify import clear_pool_notifications_for_lead
                clear_pool_notifications_for_lead(tenant_id, lead_id, db=db)
            except Exception:
                pass
            
    if payload.caller_id and leads:
        try:
            caller_res = db.table("callers").select("user_id").eq("id", payload.caller_id).eq("tenant_id", tenant_id).maybe_single().execute()
            if caller_res.data and caller_res.data.get("user_id"):
                from app.services.notify import notify_user
                count = len(leads)
                notify_user(
                    tenant_id,
                    caller_res.data["user_id"],
                    "lead_assigned",
                    "New Leads Assigned",
                    f"You have been assigned {count} leads by Admin." if count > 1 else f"You have been assigned a lead by Admin.",
                    db=db,
                    push_url="/dashboard/telecalling",
                )
        except Exception as e:
            logger.warning(f"Bulk assign notification failed: {e}")
            
    return {"success": True, "count": len(leads)}

@router.get("/export")
async def export_leads(
    segment: str | None = Query(None, pattern="^[ABCD]$"),
    tenant_id: str = Depends(get_owner_tenant_id),
):
    db = get_supabase()
    query = db.table("leads").select("id,phone,name,source,score,segment,notes,created_at").eq("tenant_id", tenant_id).is_("deleted_at", "null").neq("opted_out", True).neq("whatsapp_undeliverable", True)
    if segment:
        query = query.eq("segment", segment)
    result = query.order("score", desc=True).execute()
    leads = result.data or []

    # Exclude leads that appear only in failed broadcasts (never successfully sent to)
    any_br = db.table("broadcast_recipients").select("lead_id").eq("tenant_id", tenant_id).execute()
    any_br_ids = {r["lead_id"] for r in (any_br.data or []) if r.get("lead_id")}
    sent_br = db.table("broadcast_recipients").select("lead_id").eq("tenant_id", tenant_id).eq("send_status", "sent").execute()
    sent_br_ids = {r["lead_id"] for r in (sent_br.data or []) if r.get("lead_id")}
    leads = [l for l in leads if l["id"] not in any_br_ids or l["id"] in sent_br_ids]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id","phone","name","source","score","segment","notes","created_at"])
    writer.writeheader()
    writer.writerows(leads)

    filename = f"leads_{segment or 'all'}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

@router.get("/export-assigned")
async def export_assigned_leads(
    ctx: dict = Depends(get_tenant_and_role),
):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    caller_id = ctx.get("caller_id")
    
    if not caller_id:
        raise HTTPException(status_code=400, detail="Caller profile not found")
        
    # Query leads assigned to caller
    leads_res = db.table("leads").select("*").eq("tenant_id", tenant_id).eq("assigned_to", caller_id).is_("deleted_at", "null").order("score", desc=True).execute()
    leads = leads_res.data or []
    
    # Collect lead IDs for batch fetching
    lead_ids = [l["id"] for l in leads]
    
    # Fetch latest broadcast recipients for all these leads
    br_map = {}
    if lead_ids:
        br_recs = db.table("broadcast_recipients").select("lead_id, broadcast_id, tag_id").in_("lead_id", lead_ids).eq("tenant_id", tenant_id).order("created_at").execute()
        # Group by lead_id, keeping the latest (since ordered by created_at ascending, the last one is the latest)
        for rec in (br_recs.data or []):
            br_map[rec["lead_id"]] = rec
            
    # Collect all unique broadcast_ids, tag_ids, ad_campaign_ids
    broadcast_ids = list({str(rec["broadcast_id"]) for rec in br_map.values() if rec.get("broadcast_id")})
    tag_ids = list({str(rec["tag_id"]) for rec in br_map.values() if rec.get("tag_id")})
    ad_campaign_ids = list({str(l["ad_campaign_id"]) for l in leads if l.get("ad_campaign_id")})
    
    # Fetch scheduled_broadcasts templates
    sb_map = {}
    if broadcast_ids:
        sb_recs = db.table("scheduled_broadcasts").select("id, template_name").in_("id", broadcast_ids).eq("tenant_id", tenant_id).execute()
        sb_map = {str(r["id"]): r["template_name"] for r in (sb_recs.data or [])}
        
    # Fetch tag names
    tag_map = {}
    if tag_ids:
        tag_recs = db.table("broadcast_tags").select("id, name").in_("id", tag_ids).eq("tenant_id", tenant_id).execute()
        tag_map = {str(r["id"]): r["name"] for r in (tag_recs.data or [])}
        
    # Fetch ad campaigns
    campaign_map = {}
    if ad_campaign_ids:
        campaign_recs = db.table("ad_campaigns").select("id, campaign_name, platform").in_("id", ad_campaign_ids).eq("tenant_id", tenant_id).execute()
        campaign_map = {str(r["id"]): r for r in (campaign_recs.data or [])}
        
    # Generate rows
    rows = []
    for l in leads:
        lead_id = l["id"]
        br_rec = br_map.get(lead_id)
        
        broadcast_id = str(br_rec["broadcast_id"]) if br_rec else ""
        template_name = sb_map.get(broadcast_id, "") if broadcast_id else ""
        tag_name = tag_map.get(str(br_rec["tag_id"]), "") if br_rec and br_rec.get("tag_id") else ""
        
        ad_campaign_id = str(l.get("ad_campaign_id")) if l.get("ad_campaign_id") else ""
        ad_campaign_name = campaign_map.get(ad_campaign_id, {}).get("campaign_name", "") if ad_campaign_id else ""
        channel = campaign_map.get(ad_campaign_id, {}).get("platform", l.get("source", "")) if ad_campaign_id else l.get("source", "")
        
        lead_type = "inbound" if l.get("source") in ('whatsapp', 'instagram', 'facebook', 'telegram') and not broadcast_id else "outbound"
        
        rows.append({
            "name": l.get("name") or "",
            "phone": l.get("phone") or "",
            "type": lead_type,
            "broadcast_id": broadcast_id,
            "template_name": template_name,
            "ad_campaign": ad_campaign_name,
            "channel": channel,
            "tag": tag_name,
            "score": l.get("score", 5),
            "segment": l.get("segment", "C"),
            "assigned_at": l.get("assigned_at") or ""
        })
        
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["name", "phone", "type", "broadcast_id", "template_name", "ad_campaign", "channel", "tag", "score", "segment", "assigned_at"])
    writer.writeheader()
    writer.writerows(rows)
    
    filename = f"assigned_leads_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

@router.get("/{lead_id}/messages", response_model=list[Message])
async def get_lead_messages(lead_id: UUID, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    result = db.table("messages").select("*").eq("lead_id", str(lead_id)).eq("tenant_id", tenant_id).order("created_at").execute()
    return result.data or []

@router.get("/{lead_id}", response_model=LeadWithMessages)
async def get_lead(lead_id: UUID, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    lead_result = db.table("leads").select("*").eq("id", str(lead_id)).eq("tenant_id", tenant_id).is_("deleted_at", "null").maybe_single().execute()
    if not lead_result or not lead_result.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    msgs_result = db.table("messages").select("*").eq("lead_id", str(lead_id)).eq("tenant_id", tenant_id).order("created_at").execute()
    lead = lead_result.data
    lead["messages"] = msgs_result.data or []
    
    # Enrichment
    lead["broadcast_id"] = None
    lead["template_name"] = None
    lead["tag_name"] = None
    lead["ad_campaign_name"] = None
    lead["channel"] = lead.get("source")
    
    # 1. Fetch latest broadcast recipient entry
    br_rec = db.table("broadcast_recipients").select("broadcast_id, tag_id").eq("lead_id", str(lead_id)).eq("tenant_id", tenant_id).order("created_at", desc=True).limit(1).execute()
    if br_rec.data:
        rec = br_rec.data[0]
        lead["broadcast_id"] = str(rec["broadcast_id"])
        
        # Look up template name
        sb_rec = db.table("scheduled_broadcasts").select("template_name").eq("id", rec["broadcast_id"]).eq("tenant_id", tenant_id).maybe_single().execute()
        if sb_rec and sb_rec.data:
            lead["template_name"] = sb_rec.data["template_name"]

        # Look up tag name
        if rec.get("tag_id"):
            tag_rec = db.table("broadcast_tags").select("name").eq("id", rec["tag_id"]).eq("tenant_id", tenant_id).maybe_single().execute()
            if tag_rec and tag_rec.data:
                lead["tag_name"] = tag_rec.data["name"]

    # 2. Check for ad campaign
    if lead.get("ad_campaign_id"):
        campaign = db.table("ad_campaigns").select("campaign_name, platform").eq("id", lead["ad_campaign_id"]).eq("tenant_id", tenant_id).maybe_single().execute()
        if campaign and campaign.data:
            lead["ad_campaign_name"] = campaign.data["campaign_name"]
            lead["channel"] = campaign.data["platform"]
            
    return lead

@router.patch("/{lead_id}", response_model=Lead)
async def update_lead(lead_id: UUID, updates: LeadUpdate, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    existing = (
        db.table("leads")
        .select("segment,phone,ai_enabled,converted_at")
        .eq("id", str(lead_id))
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    update_data = updates.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = db.table("leads").update(update_data).eq("id", str(lead_id)).eq("tenant_id", tenant_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    updated = result.data[0]
    if updated.get("segment") != existing.data.get("segment"):
        record_stage_event(
            str(lead_id),
            from_segment=existing.data.get("segment"),
            to_segment=updated.get("segment") or existing.data.get("segment") or "C",
            event_type="manual_update",
            metadata={"source": "dashboard"},
            tenant_id=tenant_id,
            db=db,
        )
        # Manually moving a lead into a qualifying segment should queue it for
        # telecalling, same as an AI-driven promotion.
        if not updated.get("assigned_to") and not updated.get("converted_at"):
            from app.services.assignment import maybe_assign_lead
            maybe_assign_lead(
                str(lead_id), tenant_id, updated.get("segment"), None,
                reason="manual",
            )
    sync_follow_up_jobs(
        str(lead_id),
        segment=updated.get("segment"),
        phone=updated.get("phone") or existing.data.get("phone"),
        converted_at=updated.get("converted_at"),
        ai_enabled=updated.get("ai_enabled", existing.data.get("ai_enabled", True)),
        reason="manual_update",
        tenant_id=tenant_id,
        db=db,
    )
    return updated

@router.post("/{lead_id}/convert", response_model=Lead)
async def mark_converted(lead_id: UUID, payload: ConvertPayload | None = None, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    existing = (
        db.table("leads")
        .select("segment,phone,ai_enabled")
        .eq("id", str(lead_id))
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    notes = (payload.notes if payload else None) or None
    update = {
        "converted_at": datetime.now(timezone.utc).isoformat(),
        "call_status": "converted",
    }
    if notes:
        update["conversion_notes"] = notes
    result = db.table("leads").update(update).eq("id", str(lead_id)).eq("tenant_id", tenant_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    updated = result.data[0]
    record_stage_event(
        str(lead_id),
        from_segment=existing.data.get("segment"),
        to_segment=existing.data.get("segment"),
        event_type="converted",
        metadata={"notes": notes} if notes else {},
        tenant_id=tenant_id,
        db=db,
    )
    sync_follow_up_jobs(
        str(lead_id),
        segment=existing.data.get("segment"),
        phone=updated.get("phone") or existing.data.get("phone"),
        converted_at=updated.get("converted_at"),
        ai_enabled=updated.get("ai_enabled", existing.data.get("ai_enabled", True)),
        reason="converted",
        tenant_id=tenant_id,
        db=db,
    )
    return updated


@router.patch("/{lead_id}/ai", response_model=Lead)
async def toggle_ai(lead_id: UUID, payload: AiToggle, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    existing = (
        db.table("leads")
        .select("segment,phone,converted_at")
        .eq("id", str(lead_id))
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    result = db.table("leads").update({"ai_enabled": payload.enabled}).eq("id", str(lead_id)).eq("tenant_id", tenant_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    updated = result.data[0]
    sync_follow_up_jobs(
        str(lead_id),
        segment=updated.get("segment") or existing.data.get("segment"),
        phone=updated.get("phone") or existing.data.get("phone"),
        converted_at=updated.get("converted_at") or existing.data.get("converted_at"),
        ai_enabled=payload.enabled,
        reason="ai_toggle",
        tenant_id=tenant_id,
        db=db,
    )
    return updated


@router.patch("/{lead_id}/pin")
async def toggle_pin(lead_id: UUID, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    result = db.rpc("toggle_lead_pin", {"p_lead_id": str(lead_id), "p_tenant_id": tenant_id}).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    return result.data[0]


@router.patch("/{lead_id}/archive")
async def toggle_archive(lead_id: UUID, tenant_id: str = Depends(get_tenant_id)):
    """Toggle a conversation's archived state (inbox tidy — does not stop AI)."""
    db = get_supabase()
    cur = db.table("leads").select("archived_at").eq("id", str(lead_id)).eq("tenant_id", tenant_id).maybe_single().execute()
    if not cur.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    new_val = None if cur.data.get("archived_at") else datetime.now(timezone.utc).isoformat()
    res = db.table("leads").update({"archived_at": new_val}).eq("id", str(lead_id)).eq("tenant_id", tenant_id).execute()
    return res.data[0] if res.data else {"archived_at": new_val}


@router.patch("/{lead_id}/block")
async def toggle_block(lead_id: UUID, tenant_id: str = Depends(get_tenant_id)):
    """Toggle a contact's blocked state — hides from active inbox and stops AI auto-reply."""
    db = get_supabase()
    cur = db.table("leads").select("blocked_at").eq("id", str(lead_id)).eq("tenant_id", tenant_id).maybe_single().execute()
    if not cur.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    blocking = not cur.data.get("blocked_at")
    update: dict = {"blocked_at": datetime.now(timezone.utc).isoformat() if blocking else None}
    if blocking:
        update["ai_enabled"] = False  # blocked contacts must not get auto-replies
    res = db.table("leads").update(update).eq("id", str(lead_id)).eq("tenant_id", tenant_id).execute()
    return res.data[0] if res.data else update


@router.post("/{lead_id}/send")
async def send_human_message(lead_id: UUID, payload: HumanMessage, tenant_id: str = Depends(get_tenant_id)):
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message is empty")

    db = get_supabase()
    lead = db.table("leads").select("phone,source,ig_user_id,tg_user_id,fb_user_id").eq("id", str(lead_id)).eq("tenant_id", tenant_id).maybe_single().execute()
    if not lead.data:
        raise HTTPException(status_code=404, detail="Lead not found")

    source = lead.data.get("source")
    channel = (
        "instagram" if source == "instagram"
        else "telegram" if source == "telegram"
        else "facebook" if source == "facebook"
        else "whatsapp"
    )
    sid: str | None = None
    if channel == "instagram":
        ig_id = lead.data.get("ig_user_id")
        if not ig_id:
            raise HTTPException(status_code=400, detail="Instagram lead missing ig_user_id")
        sid = await send_instagram(ig_id, content, tenant_id=tenant_id)
    elif channel == "telegram":
        tg_id = lead.data.get("tg_user_id")
        if not tg_id:
            raise HTTPException(status_code=400, detail="Telegram lead missing tg_user_id")
        from app.services.ai_reply import send_telegram
        sid = await send_telegram(tg_id, content, tenant_id=tenant_id)
    elif channel == "facebook":
        fb_id = lead.data.get("fb_user_id")
        if not fb_id:
            raise HTTPException(status_code=400, detail="Facebook lead missing fb_user_id")
        sid = await send_facebook(fb_id, content, tenant_id=tenant_id)
    else:
        phone = lead.data.get("phone")
        if not phone:
            raise HTTPException(status_code=400, detail="Lead has no phone number")
        sid = await send_whatsapp(phone, content, tenant_id=tenant_id)

    if not sid:
        meta_err = get_last_send_error() or "unknown error"
        raise HTTPException(status_code=502, detail=f"Channel send failed: {meta_err}")

    if channel == "telegram":
        sid_field = "tg_message_id"
    elif channel == "facebook":
        sid_field = "fb_message_id"
    else:
        sid_field = "meta_message_id"  # whatsapp and instagram both use meta_message_id
    row = db.table("messages").insert({
        "lead_id": str(lead_id),
        "tenant_id": tenant_id,
        "direction": "outbound",
        "channel": channel,
        "content": content,
        "is_ai_generated": False,
        sid_field: sid,
    }).execute()
    
    # Clear needs_human_intervention flag
    db.table("leads").update({"needs_human_intervention": False}).eq("id", str(lead_id)).eq("tenant_id", tenant_id).execute()
    
    return row.data[0] if row.data else {"sent": True, "sid": sid}


class ComposeMessage(BaseModel):
    phone: str
    content: str
    name: str | None = None


@router.post("/compose")
async def compose_new_message(payload: ComposeMessage, background_tasks: BackgroundTasks, tenant_id: str = Depends(get_tenant_id)):
    """Send a WhatsApp message to any phone — creates lead if it doesn't exist."""
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message is empty")

    phone = payload.phone.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        phone = "+" + phone
    if len(phone) < 8:
        raise HTTPException(status_code=400, detail="Invalid phone number")

    db = get_supabase()
    existing = db.table("leads").select("id").eq("phone", phone).eq("tenant_id", tenant_id).limit(1).execute()
    if existing.data:
        lead_id = existing.data[0]["id"]
        if payload.name:
            db.table("leads").update({"name": payload.name}).eq("id", lead_id).eq("tenant_id", tenant_id).execute()
    else:
        insert_data = {"phone": phone, "source": "manual", "score": 5, "segment": "C", "tenant_id": tenant_id}
        if payload.name:
            insert_data["name"] = payload.name
        new_lead = db.table("leads").insert(insert_data).execute()
        lead_id = new_lead.data[0]["id"]
        record_stage_event(lead_id, to_segment="C", event_type="created", metadata={"source": "manual"}, tenant_id=tenant_id, db=db)

    sid = await send_whatsapp(phone, content, tenant_id=tenant_id)
    if not sid:
        meta_err = get_last_send_error() or "unknown error"
        # Note: outside 24h window, freeform text fails — Meta requires templates
        raise HTTPException(
            status_code=502,
            detail=(
                f"Send failed: {meta_err}. "
                "If recipient hasn't messaged you in 24h, you must use an approved template."
            ),
        )

    db.table("messages").insert({
        "lead_id": lead_id,
        "tenant_id": tenant_id,
        "direction": "outbound",
        "channel": "whatsapp",
        "content": content,
        "is_ai_generated": False,
        "meta_message_id": sid,
    }).execute()
    return {"lead_id": lead_id, "sid": sid, "phone": phone}


@router.delete("/{lead_id}/clear-chat")
async def clear_chat(lead_id: UUID, tenant_id: str = Depends(get_tenant_id)):
    """Delete all messages for a lead and reset AI to enabled. The lead itself is preserved."""
    db = get_supabase()
    # Verify the lead belongs to this tenant
    lead = db.table("leads").select("id").eq("id", str(lead_id)).eq("tenant_id", tenant_id).maybe_single().execute()
    if not lead.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    # Hard-delete all messages for this lead
    db.table("messages").delete().eq("lead_id", str(lead_id)).eq("tenant_id", tenant_id).execute()
    # Re-enable AI so the bot picks up from a fresh start
    db.table("leads").update({"ai_enabled": True}).eq("id", str(lead_id)).eq("tenant_id", tenant_id).execute()
    return {"success": True, "message": "Chat cleared"}


@router.delete("/{lead_id}")
async def delete_lead(lead_id: UUID, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    result = db.table("leads").update({"deleted_at": now, "ai_enabled": False}).eq("id", str(lead_id)).eq("tenant_id", tenant_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    db.table("follow_up_jobs").update({"status": "skipped", "skip_reason": "Lead deleted."}).eq("lead_id", str(lead_id)).eq("status", "pending").execute()
    return {"success": True, "message": "Lead deleted"}

@router.post("/{lead_id}/pre-call-brief", response_model=PreCallBriefResponse)
async def pre_call_brief(lead_id: UUID, ctx: dict = Depends(get_tenant_and_role)):
    role = ctx.get("role")
    if role not in ("caller", "owner"):
        raise HTTPException(status_code=403, detail="Caller or owner role required")

    tenant_id = ctx["tenant_id"]
    db = get_supabase()

    lead_res = (
        db.table("leads")
        .select("name,score,segment,source,ad_campaign_id,assigned_at")
        .eq("id", str(lead_id))
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    if not lead_res.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead = lead_res.data

    campaign_name = None
    if lead.get("ad_campaign_id"):
        camp_res = (
            db.table("ad_campaigns")
            .select("campaign_name")
            .eq("id", lead["ad_campaign_id"])
            .eq("tenant_id", tenant_id)
            .maybe_single()
            .execute()
        )
        if camp_res.data:
            campaign_name = camp_res.data.get("campaign_name")

    msgs_res = (
        db.table("messages")
        .select("content,direction,created_at")
        .eq("lead_id", str(lead_id))
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )
    messages = list(reversed(msgs_res.data or []))

    calls_res = (
        db.table("call_logs")
        .select("outcome,duration_seconds,created_at")
        .eq("lead_id", str(lead_id))
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(3)
        .execute()
    )
    call_logs = calls_res.data or []

    if messages:
        messages_text = "\n".join(
            f"[{m['direction']}] {m['content']}" for m in messages
        )
    else:
        messages_text = None

    if call_logs:
        call_history_text = "\n".join(
            f"- {c['outcome']} ({c['duration_seconds']}s) on {c['created_at'][:10]}"
            for c in call_logs
        )
    else:
        call_history_text = None

    name = lead.get("name") or "Unknown"
    score = lead.get("score") or 5
    segment = lead.get("segment") or "C"
    channel = lead.get("source") or "unknown"
    campaign = campaign_name or "N/A"
    assigned_at = lead.get("assigned_at") or "N/A"

    prompt = f"""You are a sales coach briefing a telecaller before they dial.

Lead profile:
- Name: {name}
- Score: {score}/10 (Segment {segment})
- Source: {channel} — {campaign}
- Assigned: {assigned_at}

Recent WhatsApp messages (newest last):
{messages_text or "No WhatsApp activity"}

Recent call history:
{call_history_text or "No calls yet"}

Write EXACTLY this JSON (no markdown, no explanation):
{{"brief": "2-3 sentence summary of who this lead is, where they came from, and what context the caller should know", "opener": "one natural opening line the caller can use to start the conversation"}}"""

    try:
        client = get_groq_client(tenant_id, is_async=False)
    except Exception as e:
        logger.error(f"Failed to configure Groq API Key for tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail="Brief generation failed")

    try:
        response = client.chat.completions.create(
            model=_BRIEF_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )
        raw = response.choices[0].message.content.strip()
        parsed = json.loads(raw)
        return PreCallBriefResponse(brief=parsed["brief"], opener=parsed["opener"])
    except Exception as e:
        logger.error(f"Pre-call brief generation failed for lead {lead_id}: {e}")
        raise HTTPException(status_code=500, detail="Brief generation failed")


@router.get("/{lead_id}/call-logs")
async def get_lead_call_logs(lead_id: UUID, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    result = (
        db.table("call_logs")
        .select("id,call_sid,status,outcome,duration_seconds,recording_url,score,ai_summary,transcript,created_at,callers(name)")
        .eq("lead_id", str(lead_id))
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    return {"data": result.data or []}


@router.post("/{lead_id}/compact")
async def manual_compact(lead_id: UUID, tenant_id: str = Depends(get_tenant_id)):
    """Manually trigger conversation compaction for debugging/admin purposes."""
    db = get_supabase()
    try:
        from app.services.conversation_compactor import compact_conversation
        summary = await compact_conversation(str(lead_id), tenant_id, db, mode="rolling")
        return {"summary": summary, "status": "compacted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Compaction failed: {str(e)}")


@router.get("/{lead_id}/score-history")
async def score_history(lead_id: UUID, ctx: dict = Depends(get_tenant_and_role)):
    """Return score change events for a lead, newest first. Max 20."""
    tenant_id = ctx["tenant_id"]
    db = get_supabase()
    result = (
        db.table("lead_stage_events")
        .select("id,event_type,from_segment,to_segment,metadata,created_at")
        .eq("lead_id", str(lead_id))
        .eq("tenant_id", tenant_id)
        .in_("event_type", ["segment_changed", "score_updated"])
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    return {"data": result.data or []}


@router.patch("/{lead_id}/release")
async def release_lead(lead_id: UUID, tenant_id: str = Depends(get_tenant_id)):
    """Unassign a lead from its caller — caller marks it as 'done'.
    Drops it from their queue so the next auto-assign can pick it up."""
    db = get_supabase()
    result = (
        db.table("leads")
        .update({"assigned_to": None})
        .eq("id", str(lead_id))
        .eq("tenant_id", tenant_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"released": True}


@router.post("/{lead_id}/takeover")
async def takeover_lead(lead_id: UUID, ctx: dict = Depends(get_tenant_and_role)):
    """Allow a telecaller to claim an overdue callback from an unavailable caller."""
    tenant_id = ctx["tenant_id"]
    caller_id = ctx.get("caller_id")
    if not caller_id:
        raise HTTPException(status_code=400, detail="Only telecallers can claim callbacks")

    db = get_supabase()
    
    # 1. Fetch lead and its assigned caller status
    lead_res = (
        db.table("leads")
        .select("id,name,assigned_to,segment,score")
        .eq("id", str(lead_id))
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    if not lead_res or not lead_res.data:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead_data = lead_res.data
    assigned_to = lead_data.get("assigned_to")
    if str(assigned_to) == str(caller_id):
        raise HTTPException(status_code=400, detail="This lead is already assigned to you")

    # 2. Fetch pending callback details
    job_res = (
        db.table("follow_up_jobs")
        .select("id,scheduled_for")
        .eq("lead_id", str(lead_id))
        .eq("tenant_id", tenant_id)
        .eq("cadence", "callback")
        .eq("status", "pending")
        .limit(1)
        .execute()
    )
    if not job_res.data:
        raise HTTPException(status_code=400, detail="Lead has no pending callback scheduled")

    job_data = job_res.data[0]
    scheduled_for = datetime.fromisoformat(job_data["scheduled_for"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    
    # Look up the previous owner only to notify them after the claim.
    prev_caller_name = "Unknown"
    prev_caller_user_id = None
    if assigned_to:
        caller_res = (
            db.table("callers")
            .select("name,user_id")
            .eq("id", assigned_to)
            .maybe_single()
            .execute()
        )
        if caller_res and caller_res.data:
            prev_caller_name = caller_res.data.get("name") or "Unknown"
            prev_caller_user_id = caller_res.data.get("user_id")

    # Claimable purely on time: 15 minutes past the scheduled slot, regardless of status.
    if now < scheduled_for + timedelta(minutes=15):
        raise HTTPException(
            status_code=400,
            detail="Cannot claim yet: callback is not 15 minutes overdue",
        )

    # 3. Perform takeover atomically
    # CAS guard: only succeeds if assigned_to still matches what we read
    update_query = db.table("leads").update({
        "assigned_to": caller_id,
        "assigned_at": now.isoformat(),
    }).eq("id", str(lead_id)).eq("tenant_id", tenant_id)
    if assigned_to is None:
        update_query = update_query.is_("assigned_to", "null")
    else:
        update_query = update_query.eq("assigned_to", assigned_to)
    update_result = update_query.execute()
    if not update_result.data:
        raise HTTPException(status_code=409, detail="Lead already claimed by another caller")

    # Update callback scheduled_for to now (so it shows as due now for the claiming caller)
    db.table("follow_up_jobs").update({
        "scheduled_for": now.isoformat(),
    }).eq("id", job_data["id"]).eq("tenant_id", tenant_id).execute()

    # Get claiming caller's name
    me_res = db.table("callers").select("name").eq("id", caller_id).maybe_single().execute()
    me_name = me_res.data.get("name") if me_res and me_res.data else "Another Caller"

    # Log assignment event
    record_assignment_event(
        lead_id=str(lead_id),
        tenant_id=tenant_id,
        segment=lead_data.get("segment"),
        caller_id=caller_id,
        caller_name=me_name,
        reason="caller_unavailable",
        method="takeover",
        score=lead_data.get("score"),
        matched_segments=[lead_data.get("segment")] if lead_data.get("segment") else [],
        prev_caller_id=assigned_to,
        prev_caller_name=prev_caller_name,
        event_type="reassigned",
        db=db,
    )

    if prev_caller_user_id:
        from app.services.notify import notify_user
        notify_user(
            tenant_id,
            prev_caller_user_id,
            "callback_taken_over",
            "Callback claimed",
            f"{me_name} claimed your callback for '{lead_data.get('name') or 'Unknown'}'.",
            db=db,
            push_url="/dashboard/telecalling/scheduled",
        )

    try:
        from app.services.notify import clear_pool_notifications_for_lead
        clear_pool_notifications_for_lead(tenant_id, str(lead_id), db=db)
    except Exception:
        pass

    return {"success": True, "assigned_to": caller_id}
