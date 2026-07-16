import logging
import asyncio
from datetime import datetime, timezone
from groq import Groq
from app.config import settings
from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

from app.services.groq_client import get_groq_client
_COMPACTOR_MODEL = "llama-3.1-8b-instant"

INITIAL_COMPACT_PROMPT = """You are summarizing a WhatsApp conversation for a sales lead scoring system.

CONVERSATION (most recent first):
{messages}

Extract and summarize:
1. Lead's name and contact intent (inquiry, complaint, purchase, etc.)
2. Key facts provided (rasi, nakshatram, address, etc.)
3. Engagement level (high/medium/low based on responsiveness)
5. Any objections or concerns

Keep summary under 150 words. Be factual, not interpretive.
Return ONLY the summary text."""

ROLLING_COMPACT_PROMPT = """You are updating a conversation summary for a sales lead.

PREVIOUS SUMMARY:
{existing_summary}

NEW MESSAGES (most recent first):
{new_messages}

Update the summary:
1. Preserve key facts (name, rasi, nakshatram, address, etc.)
2. Add new information from recent messages
3. Remove outdated/transient details
4. Keep under 200 words
5. Be factual, not interpretive

Return ONLY the updated summary text."""


def _format_messages(messages: list[dict]) -> str:
    """Format messages for LLM context."""
    lines = []
    for msg in reversed(messages):
        direction = "Bot" if msg.get("direction") == "outbound" else "User"
        content = (msg.get("content") or "").strip()[:200]
        if content and not content.startswith("[Template"):
            lines.append(f"{direction}: {content}")
    return "\n".join(lines) if lines else "No messages available."


async def compact_conversation(
    lead_id: str,
    tenant_id: str,
    db=None,
    mode: str = "rolling"
) -> str:
    """
    Compact conversation messages into a summary.
    
    Args:
        lead_id: Lead UUID
        tenant_id: Tenant UUID
        db: Supabase client (optional)
        mode: "initial" for first compaction, "rolling" for updates
    
    Returns:
        The new summary text
    """
    db = db or get_supabase()
    existing_summary = None

    try:
        client = get_groq_client(tenant_id, is_async=False)
    except Exception as e:
        logger.warning(f"Groq API key not configured for tenant {tenant_id}: {e}")
        return existing_summary or ""
    
    try:
        # Fetch current state
        state_row = (
            db.table("lead_conversation_state")
            .select("conversation_summary, summary_version")
            .eq("lead_id", lead_id)
            .maybe_single()
            .execute()
        )
        state_data = state_row.data or {}
        existing_summary = state_data.get("conversation_summary")
        
        if mode == "initial" or not existing_summary:
            # Fetch last 10 messages for initial compaction
            messages = (
                db.table("messages")
                .select("direction, content, created_at")
                .eq("lead_id", lead_id)
                .order("created_at", desc=True)
                .limit(10)
                .execute()
            )
            messages_text = _format_messages(messages.data or [])
            prompt = INITIAL_COMPACT_PROMPT.format(messages=messages_text)
        else:
            # Fetch last 10 new messages for rolling update
            last_compacted = state_data.get("last_compacted_at")
            query = (
                db.table("messages")
                .select("direction, content, created_at")
                .eq("lead_id", lead_id)
                .order("created_at", desc=True)
                .limit(10)
            )
            if last_compacted:
                query = query.gt("created_at", last_compacted)
            
            messages = query.execute()
            messages_text = _format_messages(messages.data or [])
            
            if not messages.data:
                logger.info(f"No new messages to compact for lead {lead_id}")
                return existing_summary
            
            prompt = ROLLING_COMPACT_PROMPT.format(
                existing_summary=existing_summary,
                new_messages=messages_text
            )
        
        # Call Groq for summarization
        response = client.chat.completions.create(
            model=_COMPACTOR_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=300,
        )
        new_summary = response.choices[0].message.content.strip()
        
        # Update state
        db.table("lead_conversation_state").update({
            "conversation_summary": new_summary,
            "last_compacted_at": datetime.now(timezone.utc).isoformat(),
            "summary_version": (state_data.get("summary_version") or 0) + 1,
            "message_count": 0,
        }).eq("lead_id", lead_id).execute()
        
        logger.info(f"Conversation compacted for lead {lead_id} (mode={mode}, version={state_data.get('summary_version', 0) + 1})")
        return new_summary
        
    except Exception as e:
        logger.error(f"Compaction failed for lead {lead_id}: {e}")
        return existing_summary or ""
