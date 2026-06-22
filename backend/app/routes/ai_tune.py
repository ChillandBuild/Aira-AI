import asyncio
import json
import logging
from typing import Literal
from groq import AsyncGroq, Groq
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.config import settings
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, require_owner
from app.services.ai_reply import invalidate_prompt_cache

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_owner)])

from app.services.groq_client import get_groq_client
_TUNE_MODEL = "llama-3.3-70b-versatile"

META_PROMPT = """You are a prompt-engineering coach. Below is the current SYSTEM PROMPT
used by a WhatsApp AI assistant for a B2B sales team, followed by transcripts of
CONVERSATIONS that successfully closed (lead converted).

Analyse the winning tone, pacing, phrasing, and next-step hooks. Suggest 2 to 3 concrete,
SHORT additions or tweaks to the system prompt that would make new replies better mimic
the winning patterns. Do NOT rewrite the whole prompt. Each suggestion must be a standalone
sentence or short paragraph that can be appended to the existing prompt as-is.

Return STRICT JSON only with the shape:
{{"suggestions": [{{"suggestion": "...", "rationale": "..."}}, ...]}}

=== CURRENT SYSTEM PROMPT ===
{prompt}

=== WINNING CONVERSATIONS ===
{conversations}
"""


class PromptUpdate(BaseModel):
    content: str


_DEFAULT_WHATSAPP_PROMPT = "You are a helpful AI assistant. Answer customer queries accurately and warmly. Keep replies concise (2-3 sentences). Always encourage the next step."


@router.get("/prompts")
async def list_prompts(tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    res = db.table("ai_prompts").select("*").eq("tenant_id", tenant_id).order("name").execute()
    existing_names = {row["name"] for row in (res.data or [])}
    
    missing_prompts = []
    if "whatsapp_reply" not in existing_names:
        missing_prompts.append({
            "name": "whatsapp_reply",
            "content": _DEFAULT_WHATSAPP_PROMPT,
            "tenant_id": tenant_id,
        })
    if "telegram_reply" not in existing_names:
        missing_prompts.append({
            "name": "telegram_reply",
            "content": "You are a helpful AI assistant. Answer customer queries accurately and warmly via Telegram. Keep replies concise (2-3 sentences). Always encourage the next step.",
            "tenant_id": tenant_id,
        })
    if "instagram_reply" not in existing_names:
        missing_prompts.append({
            "name": "instagram_reply",
            "content": "You are a helpful AI assistant. Answer customer queries accurately and warmly via Instagram. Keep replies concise (2-3 sentences). Always encourage the next step.",
            "tenant_id": tenant_id,
        })
    if "facebook_reply" not in existing_names:
        missing_prompts.append({
            "name": "facebook_reply",
            "content": "You are a helpful AI assistant. Answer customer queries accurately and warmly via Facebook Messenger. Keep replies concise (2-3 sentences). Always encourage the next step.",
            "tenant_id": tenant_id,
        })

    if missing_prompts:
        db.table("ai_prompts").insert(missing_prompts).execute()
        res = db.table("ai_prompts").select("*").eq("tenant_id", tenant_id).order("name").execute()
        
    return {"data": res.data or []}


async def _auto_generate_rubric(system_prompt: str, tenant_id: str, force: bool = False) -> None:
    """Generate a domain-appropriate scoring rubric from the tenant's system prompt."""
    try:
        from app.config_dynamic import get_setting, save_setting
        if not force:
            existing_rubric = get_setting("scoring_rubric", tenant_id=tenant_id)
            if existing_rubric and existing_rubric.strip():
                logger.info(f"Scoring rubric already exists for tenant {tenant_id} — skipping auto-generation")
                return

        try:
            client = get_groq_client(tenant_id, is_async=True)
        except Exception:
            return
        prompt = f"""You are configuring a lead scoring system for a B2B sales team.

Based on this business's AI assistant system prompt, write a lead scoring rubric (1-10 scale).
The rubric should reflect THIS specific business's conversion signals — not generic ones.

System prompt:
{system_prompt[:1500]}

Write a rubric in this exact format (5 lines, one per score band):
- 9-10: [High intent signals specific to this business]
- 7-8: [Warm signals specific to this business]
- 5-6: [Neutral signals]
- 3-4: [Low engagement signals]
- 1-2: [Disqualified / not interested signals]

Reply with ONLY the 5 rubric lines. No explanation, no preamble."""

        resp = await client.chat.completions.create(
            model=_TUNE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )
        rubric = resp.choices[0].message.content.strip()
        if rubric and "9-10" in rubric:
            save_setting("scoring_rubric", rubric, tenant_id=tenant_id)
            logger.info(f"Auto-generated scoring rubric for tenant {tenant_id}")
    except Exception as e:
        logger.warning(f"Auto-rubric generation failed for tenant {tenant_id}: {e}")


@router.put("/prompts/{name}")
async def update_prompt(name: str, payload: PromptUpdate, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    res = db.table("ai_prompts").update({"content": payload.content}).eq("name", name).eq("tenant_id", tenant_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail=f"Prompt '{name}' not found")
    invalidate_prompt_cache(name)
    _task = asyncio.create_task(_auto_generate_rubric(payload.content, tenant_id, force=True))
    _task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
    return res.data[0]


@router.post("/analyze")
async def analyze(for_prompt: str = "whatsapp_reply", limit: int = 5, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()

    prompt_row = db.table("ai_prompts").select("content").eq("name", for_prompt).eq("tenant_id", tenant_id).maybe_single().execute()
    if not prompt_row or not prompt_row.data:
        raise HTTPException(status_code=404, detail=f"Prompt '{for_prompt}' not found")
    active_prompt = prompt_row.data["content"]

    converted = (
        db.table("leads")
        .select("id,name,phone")
        .eq("tenant_id", tenant_id)
        .not_.is_("converted_at", "null")
        .order("converted_at", desc=True)
        .limit(limit)
        .execute()
    )
    lead_rows = converted.data or []
    if not lead_rows:
        raise HTTPException(status_code=400, detail="No converted leads to analyse. Mark at least one lead as converted first.")

    transcripts: list[str] = []
    for lead in lead_rows:
        msgs = (
            db.table("messages")
            .select("direction,content,created_at")
            .eq("lead_id", lead["id"])
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=False)
            .limit(40)
            .execute()
        )
        lines = [f"{m['direction'].upper()}: {m['content']}" for m in (msgs.data or [])]
        if lines:
            header = f"--- Lead {lead.get('name') or lead.get('phone') or lead['id'][:8]} ---"
            transcripts.append(header + "\n" + "\n".join(lines))

    if not transcripts:
        raise HTTPException(status_code=400, detail="Converted leads have no message history.")

    try:
        client = get_groq_client(tenant_id, is_async=False)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"GROQ_API_KEY not configured for tenant {tenant_id}: {e}")

    meta = (
        META_PROMPT
        .replace("{prompt}", active_prompt)
        .replace("{conversations}", "\n\n".join(transcripts))
    )
    try:
        resp = client.chat.completions.create(
            model=_TUNE_MODEL,
            messages=[{"role": "user", "content": meta}],
            response_format={"type": "json_object"},
            temperature=0.4,
            max_tokens=1000,
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error(f"Groq analyze failed: {e}")
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}")

    try:
        parsed = json.loads(text)
        items = parsed.get("suggestions") if isinstance(parsed, dict) else parsed
        if not isinstance(items, list):
            raise ValueError("expected a JSON list under 'suggestions'")
    except Exception as e:
        logger.error(f"Failed to parse LLM JSON: {e}\nText: {text[:500]}")
        raise HTTPException(status_code=502, detail=f"LLM returned non-JSON: {text[:200]}")

    inserted: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        suggestion = str(it.get("suggestion", "")).strip()
        rationale = str(it.get("rationale", "")).strip() or None
        if not suggestion:
            continue
        row = db.table("ai_tune_suggestions").insert({
            "for_prompt": for_prompt,
            "suggestion": suggestion,
            "rationale": rationale,
            "tenant_id": tenant_id,
        }).execute()
        if row.data:
            inserted.append(row.data[0])

    return {"analyzed_leads": len(lead_rows), "suggestions_created": len(inserted), "data": inserted}


@router.get("/suggestions")
async def list_suggestions(status: Literal["pending", "applied", "rejected", "all"] = "pending", tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    query = db.table("ai_tune_suggestions").select("*").eq("tenant_id", tenant_id).order("created_at", desc=True).limit(100)
    if status != "all":
        query = query.eq("status", status)
    res = query.execute()
    return {"data": res.data or []}


@router.post("/suggestions/{suggestion_id}/apply")
async def apply_suggestion(suggestion_id: str, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    sug = db.table("ai_tune_suggestions").select("*").eq("id", suggestion_id).eq("tenant_id", tenant_id).maybe_single().execute()
    if not sug or not sug.data:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if sug.data["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Suggestion already {sug.data['status']}")

    name = sug.data["for_prompt"]
    prompt_row = db.table("ai_prompts").select("content").eq("name", name).eq("tenant_id", tenant_id).maybe_single().execute()
    if not prompt_row or not prompt_row.data:
        raise HTTPException(status_code=404, detail=f"Prompt '{name}' not found")

    new_content = prompt_row.data["content"].rstrip() + "\n\n" + sug.data["suggestion"].strip() + "\n"
    db.table("ai_prompts").update({"content": new_content}).eq("name", name).eq("tenant_id", tenant_id).execute()
    db.table("ai_tune_suggestions").update({"status": "applied"}).eq("id", suggestion_id).eq("tenant_id", tenant_id).execute()
    invalidate_prompt_cache(name)
    return {"applied": True, "for_prompt": name, "new_length": len(new_content)}


@router.post("/suggestions/{suggestion_id}/reject")
async def reject_suggestion(suggestion_id: str, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    res = db.table("ai_tune_suggestions").update({"status": "rejected"}).eq("id", suggestion_id).eq("tenant_id", tenant_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return {"rejected": True}
