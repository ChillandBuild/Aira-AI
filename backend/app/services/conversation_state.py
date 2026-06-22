"""Conversation state tracking for lead inactivity, compaction, and message counting."""

import logging
from datetime import datetime, timezone, timedelta

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)


def get_or_create_state(lead_id: str, tenant_id: str, db=None) -> dict:
    """Fetch the conversation state for a lead, or return a fresh idle state.

    Also checks for inactivity gaps:
    - >1hr: triggers auto-compaction (fire-and-forget)
    - >6hr: session reset (state → idle, summary retained)
    """
    db = db or get_supabase()
    try:
        response = (
            db.table("lead_conversation_state")
            .select("*")
            .eq("lead_id", lead_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.warning(f"lead_conversation_state query failed for lead {lead_id}: {e}. Defaulting to idle state.")
        response = None

    if response and response.data:
        state = response.data[0]

        last_activity = state.get("last_activity_at")
        if last_activity:
            try:
                last_dt = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
                now_dt = datetime.now(timezone.utc)
                gap = now_dt - last_dt

                if gap > timedelta(hours=1):
                    import asyncio
                    try:
                        from app.services.conversation_compactor import compact_conversation
                        asyncio.create_task(compact_conversation(lead_id, tenant_id, db, mode="rolling"))
                        logger.info(f"Auto-compaction triggered for lead {lead_id} after {gap} inactivity")
                    except Exception as compact_err:
                        logger.error(f"Auto-compaction failed for lead {lead_id}: {compact_err}")

                if gap > timedelta(hours=6):
                    state["state"] = "idle"
                    logger.info(f"Session reset for lead {lead_id} after {gap} inactivity — summary retained for context")
            except Exception as parse_err:
                logger.warning(f"Failed to parse last_activity_at for lead {lead_id}: {parse_err}")

        return state

    logger.info(f"No conversation state found for lead {lead_id}. Initialising idle state.")
    return {
        "id": None,
        "lead_id": lead_id,
        "tenant_id": tenant_id,
        "state": "idle",
        "draft_data": {},
    }
