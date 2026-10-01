"""Clear Data: erase one lead and everything that hangs off it, money records included, so the
next message from that number arrives as a brand-new lead.

Deleting the leads row does most of the work: 18 tables reference leads ON DELETE CASCADE
(messages, intake_sessions, deals -> deal_items, bookings, call_logs, notes, follow-ups,
conversation state, ...). The tables below do not, so they are cleared by hand first:
chat_handovers and broadcast_recipients are NO ACTION and would block the delete,
automation_logs is SET NULL and would keep the rows, and the rest have no foreign key at all.
"""
import logging

from app.services.deals import _cancel_replaced_link
from app.services.intake import cancel_session_link

logger = logging.getLogger(__name__)

NON_CASCADING_TABLES = (
    "chat_handovers",
    "broadcast_recipients",
    "automation_logs",
    "broadcast_lead_scores",
    "lead_tag_interest",
    "silence_nudge_jobs",
)


async def _cancel_open_links(db, lead_id: str, tenant_id: str) -> int:
    """Cancel every payment link still payable, before the rows that own them go. A link paid
    after the wipe would take the money while the webhook rejects it as an unknown session."""
    cancelled = 0
    sessions = (
        db.table("intake_sessions")
        .select("id, tenant_id, status, payment_link, razorpay_payment_link_id, payment_link_expires_at")
        .eq("lead_id", lead_id).eq("tenant_id", tenant_id).eq("status", "awaiting_payment")
        .execute()
    )
    for session in sessions.data or []:
        cancelled += await cancel_session_link(db, session)
    deals = (
        db.table("deals")
        .select("id, tenant_id, stage, payment_link, razorpay_payment_link_id, link_expires_at")
        .eq("lead_id", lead_id).eq("tenant_id", tenant_id).eq("stage", "awaiting_payment")
        .execute()
    )
    for deal in deals.data or []:
        cancelled += await _cancel_replaced_link(deal, None)
    return cancelled


async def wipe_lead(db, lead_id: str, tenant_id: str) -> int:
    """Erase the lead. Returns how many payment links were cancelled. The caller has already
    checked the lead belongs to tenant_id."""
    cancelled = await _cancel_open_links(db, lead_id, tenant_id)
    for table in NON_CASCADING_TABLES:
        db.table(table).delete().eq("lead_id", lead_id).eq("tenant_id", tenant_id).execute()
    db.table("leads").delete().eq("id", lead_id).eq("tenant_id", tenant_id).execute()
    logger.info(f"Clear Data: wiped lead {lead_id} for tenant {tenant_id} ({cancelled} payment link(s) cancelled)")
    return cancelled
