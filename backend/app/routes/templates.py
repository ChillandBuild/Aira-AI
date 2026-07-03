import logging
import json
import re
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from pydantic import BaseModel, field_validator
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id
from app.services import meta_cloud
from app.services.meta_cloud import (
    submit_template,
    get_template_status,
    list_all_templates,
    delete_template_from_meta,
    update_template_on_meta,
    upload_media_for_template,
    TemplateContentExistsError,
    _sanitize_header_or_footer,
    _extract_variable_examples,
    _build_button_components,
    _strip_emojis,
)
from app.config_dynamic import get_setting
from app.services.meta_webhook_verify import verify_meta_signature

logger = logging.getLogger(__name__)
router = APIRouter()
public_router = APIRouter()  # No auth — Meta calls these endpoints directly


class Button(BaseModel):
    type: str  # QUICK_REPLY | URL | PHONE_NUMBER | WHATSAPP_CALL | COPY_CODE | ONE_TAP
    text: str
    url: str | None = None
    phone: str | None = None
    country: str | None = None
    offer_code: str | None = None
    active_for_days: int | None = None
    autofill_text: str | None = None
    package_name: str | None = None
    signature_hash: str | None = None


class CarouselCard(BaseModel):
    header_media_type: str = "IMAGE"  # IMAGE | VIDEO
    header_media_url: str
    body_text: str
    buttons: list[Button] | None = None  # 1-2 per card


_SUPPORTED_TEMPLATE_LANGUAGES = {"en", "en_US", "en_IN", "hi", "kn", "ml", "ta", "te"}


def _validate_body_variables(body_text: str) -> str:
    """Mirrors Meta's hard template rules (subcode 2388299: leading/trailing
    variables; sequential numbering) so bad submissions fail fast with a
    clear message instead of round-tripping to the Graph API."""
    trimmed = body_text.strip()
    if not trimmed:
        return body_text
    if re.match(r"^\{\{\d+\}\}", trimmed):
        raise ValueError("Variables can't be at the start of the template.")
    if re.search(r"\{\{\d+\}\}$", trimmed):
        raise ValueError("Variables can't be at the end of the template.")

    indices = sorted(set(int(m) for m in re.findall(r"\{\{(\d+)\}\}", trimmed)))
    if indices and indices != list(range(1, len(indices) + 1)):
        raise ValueError(
            f"Variables must be numbered sequentially starting from {{1}} with no gaps "
            f"(found {', '.join('{{' + str(i) + '}}' for i in indices)})."
        )
    return body_text


class CreateTemplate(BaseModel):
    name: str
    category: str
    language: str = "en"
    body_text: str
    header_text: str | None = None
    header_media_type: str | None = None  # IMAGE | VIDEO | DOCUMENT | LOCATION
    header_media_url: str | None = None
    footer_text: str | None = None
    buttons: list[Button] | None = None
    carousel_cards: list[CarouselCard] | None = None

    @field_validator("language")
    @classmethod
    def _validate_language(cls, v: str) -> str:
        if v not in _SUPPORTED_TEMPLATE_LANGUAGES:
            raise ValueError(f"Unsupported language '{v}'. Supported: {sorted(_SUPPORTED_TEMPLATE_LANGUAGES)}")
        return v

    @field_validator("body_text")
    @classmethod
    def _validate_body_text(cls, v: str) -> str:
        return _validate_body_variables(v)


@router.get("/")
async def list_templates(tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    result = db.table("message_templates").select("*").eq("tenant_id", tenant_id).order("submitted_at", desc=True).execute()
    return {"data": result.data or []}


@router.post("/")
async def create_template(payload: CreateTemplate, tenant_id: str = Depends(get_tenant_id)):
    name = payload.name.strip().lower().replace(" ", "_")
    category = payload.category.upper()
    if category not in ("MARKETING", "UTILITY", "AUTHENTICATION"):
        raise HTTPException(status_code=400, detail="Invalid category")

    # Validate header text emoji presence
    if payload.header_text and _strip_emojis(payload.header_text) != payload.header_text:
        raise HTTPException(status_code=400, detail="Emojis are not allowed in the header text.")

    # Validate duplicate button texts
    if payload.buttons:
        btn_texts = [b.text.strip().lower() for b in payload.buttons if b.text]
        if len(btn_texts) != len(set(btn_texts)):
            raise HTTPException(status_code=400, detail="You can't enter the same text for multiple buttons.")

    waba_id = get_setting("meta_waba_id", tenant_id=tenant_id)

    db = get_supabase()
    existing = db.table("message_templates").select("id").eq("name", name).eq("tenant_id", tenant_id).limit(1).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail=f"Template '{name}' already exists")

    meta_template_id = None
    status = "PENDING"
    if waba_id:
        try:
            buttons_dict = [b.model_dump() for b in payload.buttons] if payload.buttons else None
            carousel_dict = None
            if payload.carousel_cards:
                carousel_dict = []
                for c in payload.carousel_cards:
                    raw = c.model_dump()
                    if c.buttons:
                        raw["buttons"] = [b.model_dump() for b in c.buttons]
                    carousel_dict.append(raw)
            meta_response = await submit_template(
                waba_id=waba_id,
                name=name,
                category=category,
                language=payload.language,
                body_text=payload.body_text,
                header_text=payload.header_text,
                header_media_type=payload.header_media_type,
                header_media_url=payload.header_media_url,
                footer_text=payload.footer_text,
                buttons=buttons_dict,
                carousel_cards=carousel_dict,
                tenant_id=tenant_id,
            )
            meta_template_id = str(meta_response.get("id", ""))
        except TemplateContentExistsError:
            raise
        except Exception as e:
            status = "REJECTED"
            logger.warning(f"Meta template submission failed for {name}: {e}, saved as REJECTED")
    else:
        logger.info(f"No meta_waba_id configured — saving template '{name}' locally as PENDING")

    db_insert = {
        "name": name,
        "category": category,
        "language": payload.language,
        "body_text": payload.body_text,
        "header_media_type": payload.header_media_type,
        "header_media_url": payload.header_media_url,
        "buttons": [b.model_dump() for b in payload.buttons] if payload.buttons else None,
        "carousel_cards": (
            [
                {**c.model_dump(), "buttons": [b.model_dump() for b in c.buttons] if c.buttons else None}
                for c in payload.carousel_cards
            ]
            if payload.carousel_cards
            else None
        ),
        "status": status,
        "meta_template_id": meta_template_id,
        "tenant_id": tenant_id,
    }
    if payload.header_text:
        db_insert["header_text"] = payload.header_text
    if payload.footer_text:
        db_insert["footer_text"] = payload.footer_text

    result = db.table("message_templates").insert(db_insert).execute()

    return result.data[0]


@router.delete("/{template_id}")
async def delete_template(template_id: str, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    # Fetch the template first so we can delete from Meta too
    row = db.table("message_templates").select("name,meta_template_id").eq("id", template_id).eq("tenant_id", tenant_id).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="Template not found")

    template_name = row.data[0].get("name", "")

    # Delete from local DB
    db.table("message_templates").delete().eq("id", template_id).eq("tenant_id", tenant_id).execute()

    # Best-effort: also delete from Meta
    try:
        waba_id = get_setting("meta_waba_id", tenant_id=tenant_id)
        if waba_id and template_name:
            await delete_template_from_meta(
                template_name=template_name,
                waba_id=waba_id,
                tenant_id=tenant_id,
            )
    except Exception as e:
        logger.warning(f"Best-effort Meta template delete failed for '{template_name}': {e}")

    return {"deleted": True}


@router.post("/{template_id}/sync")
async def sync_template_status(template_id: str, tenant_id: str = Depends(get_tenant_id)):
    """Pull current status from Meta API and update the local record."""
    db = get_supabase()
    row = db.table("message_templates").select("name,meta_template_id").eq("id", template_id).eq("tenant_id", tenant_id).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="Template not found")

    waba_id = get_setting("meta_waba_id", tenant_id=tenant_id)
    if not waba_id:
        raise HTTPException(status_code=400, detail="meta_waba_id not configured in Settings")

    meta_info = await get_template_status(waba_id=waba_id, template_name=row.data[0]["name"], tenant_id=tenant_id)
    if not meta_info:
        raise HTTPException(status_code=502, detail="Template not found on Meta — check WABA ID and access token in Settings")

    new_status = meta_info.get("status", "PENDING").upper()
    updates: dict = {"status": new_status}
    if new_status == "APPROVED":
        updates["approved_at"] = datetime.now(timezone.utc).isoformat()
    if meta_info.get("rejected_reason"):
        updates["rejection_reason"] = meta_info["rejected_reason"]

    db.table("message_templates").update(updates).eq("id", template_id).execute()
    updated = db.table("message_templates").select("*").eq("id", template_id).limit(1).execute()
    return updated.data[0] if updated.data else None


@router.post("/sync-from-meta")
async def sync_templates_from_meta(tenant_id: str = Depends(get_tenant_id)):
    """Pull all templates from Meta and upsert into local DB. Returns added/updated counts."""
    waba_id = get_setting("meta_waba_id", tenant_id=tenant_id)
    if not waba_id:
        raise HTTPException(status_code=400, detail="meta_waba_id not configured in Settings")

    meta_templates = await list_all_templates(waba_id=waba_id, tenant_id=tenant_id)
    if not meta_templates:
        return {"added": 0, "updated": 0, "total": 0}

    db = get_supabase()
    existing_rows = db.table("message_templates").select("name,status,meta_template_id").eq("tenant_id", tenant_id).execute()
    existing_by_name = {r["name"]: r for r in (existing_rows.data or [])}

    added = 0
    updated = 0

    for t in meta_templates:
        name = t.get("name", "")
        status = (t.get("status") or "PENDING").upper()
        category = (t.get("category") or "MARKETING").upper()
        language = t.get("language", "en")
        rejection_reason = t.get("rejected_reason") or None
        meta_id = str(t.get("id", "")) if t.get("id") else None

        # Parse the full components array from Meta
        body_text = ""
        header_text = None
        header_media_type = None
        header_media_url = None
        footer_text = None
        buttons = None
        for comp in (t.get("components") or []):
            comp_type = comp.get("type", "").upper()
            if comp_type == "BODY":
                body_text = comp.get("text", "")
            elif comp_type == "HEADER":
                fmt = (comp.get("format") or "").upper()
                if fmt == "TEXT":
                    header_text = comp.get("text", "")
                elif fmt in ("IMAGE", "VIDEO", "DOCUMENT", "LOCATION"):
                    header_media_type = fmt
                    # Extract example URL if present
                    example = comp.get("example", {})
                    header_handle = example.get("header_handle", [])
                    if header_handle:
                        header_media_url = header_handle[0] if isinstance(header_handle, list) else header_handle
            elif comp_type == "FOOTER":
                footer_text = comp.get("text", "")
            elif comp_type == "BUTTONS":
                buttons = comp.get("buttons", [])

        if name in existing_by_name:
            # Update status and rejection reason if changed
            current = existing_by_name[name]
            if current.get("status") != status or (rejection_reason and not current.get("rejection_reason")):
                updates: dict = {"status": status}
                if rejection_reason:
                    updates["rejection_reason"] = rejection_reason
                if status == "APPROVED":
                    updates["approved_at"] = datetime.now(timezone.utc).isoformat()
                if meta_id and not current.get("meta_template_id"):
                    updates["meta_template_id"] = meta_id
                db.table("message_templates").update(updates).eq("name", name).eq("tenant_id", tenant_id).execute()
                updated += 1
        else:
            # Insert new template with full component data
            insert_row: dict = {
                "name": name,
                "category": category,
                "language": language,
                "body_text": body_text,
                "status": status,
                "meta_template_id": meta_id,
                "rejection_reason": rejection_reason,
                "approved_at": datetime.now(timezone.utc).isoformat() if status == "APPROVED" else None,
                "tenant_id": tenant_id,
            }
            if header_text:
                insert_row["header_text"] = header_text
            if header_media_type:
                insert_row["header_media_type"] = header_media_type
            if header_media_url:
                insert_row["header_media_url"] = header_media_url
            if footer_text:
                insert_row["footer_text"] = footer_text
            if buttons:
                insert_row["buttons"] = buttons
            db.table("message_templates").insert(insert_row).execute()
            added += 1

    return {"added": added, "updated": updated, "total": len(meta_templates)}


@public_router.post("/webhook-status")
async def template_status_webhook(request: Request):
    """Meta calls this when template status changes (APPROVED/REJECTED). No auth."""
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body)
    except Exception as e:
        logger.warning(f"Template status webhook: invalid JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    signature = request.headers.get("X-Hub-Signature-256")

    meta_id = None
    entry = payload.get("entry", [])
    for e in entry:
        for change in e.get("changes", []):
            if change.get("field") == "message_template_status_update":
                value = change.get("value", {})
                if value.get("message_template_id"):
                    meta_id = str(value["message_template_id"])
                    break
        if meta_id:
            break

    if not meta_id:
        logger.warning("Template status webhook: message_template_id not found in payload")
        return {"status": "ok"}

    db = get_supabase()
    row = db.table("message_templates").select("tenant_id").eq("meta_template_id", meta_id).limit(1).execute()
    if not row.data:
        logger.warning(f"Template status webhook: tenant not found for meta_template_id: {meta_id}")
        raise HTTPException(status_code=404, detail="Template not found")
    
    tenant_id = row.data[0]["tenant_id"]

    if not signature:
        logger.warning("Template status webhook: missing signature header")
        raise HTTPException(status_code=403, detail="Missing signature")

    if not verify_meta_signature(raw_body, signature, tenant_id):
        logger.warning(f"Template status webhook: invalid signature for tenant {tenant_id}")
        raise HTTPException(status_code=403, detail="Invalid signature")

    for e in entry:
        for change in e.get("changes", []):
            value = change.get("value", {})
            if change.get("field") != "message_template_status_update":
                continue
            meta_id = str(value.get("message_template_id", ""))
            new_status = value.get("event", "").upper()
            reason = value.get("reason")
            if not meta_id or new_status not in ("APPROVED", "REJECTED", "PAUSED"):
                continue
            
            updates: dict = {"status": new_status}
            if reason:
                updates["rejection_reason"] = reason
            if new_status == "APPROVED":
                updates["approved_at"] = datetime.now(timezone.utc).isoformat()
            db.table("message_templates").update(updates).eq("meta_template_id", meta_id).execute()
            logger.info(f"Template {meta_id} status → {new_status}")
    return {"status": "ok"}


class VariationsPayload(BaseModel):
    variations: list[str]


@router.get("/{template_id}/variations")
async def get_template_variations(template_id: str, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    row = db.table("message_templates").select("id,name,variations").eq("id", template_id).eq("tenant_id", tenant_id).execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"id": template_id, "variations": row.data[0].get("variations") or []}


@router.put("/{template_id}/variations")
async def update_template_variations(template_id: str, payload: VariationsPayload, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    result = db.table("message_templates").update({"variations": payload.variations}).eq("id", template_id).eq("tenant_id", tenant_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"id": template_id, "variations": payload.variations}


class UpdateTemplate(BaseModel):
    body_text: Optional[str] = None
    header_text: Optional[str] = None
    header_media_type: Optional[str] = None
    header_media_url: Optional[str] = None
    footer_text: Optional[str] = None
    buttons: Optional[list[Button]] = None

    @field_validator("body_text")
    @classmethod
    def _validate_body_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_body_variables(v)


@router.patch("/{template_id}")
async def update_template(template_id: str, payload: UpdateTemplate, tenant_id: str = Depends(get_tenant_id)):
    """Edit a REJECTED or PAUSED template. Updates local DB and pushes changes to Meta if linked."""
    db = get_supabase()
    row = db.table("message_templates").select("*").eq("id", template_id).eq("tenant_id", tenant_id).limit(1).execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="Template not found")

    template = row.data[0]
    if template.get("status") not in ("REJECTED", "PAUSED"):
        raise HTTPException(
            status_code=400,
            detail=f"Only REJECTED or PAUSED templates can be edited. Current status: {template.get('status')}",
        )

    if payload.header_text is not None and _strip_emojis(payload.header_text) != payload.header_text:
        raise HTTPException(status_code=400, detail="Emojis are not allowed in the header text.")

    if payload.buttons is not None:
        btn_texts = [b.text.strip().lower() for b in payload.buttons if b.text]
        if len(btn_texts) != len(set(btn_texts)):
            raise HTTPException(status_code=400, detail="You can't enter the same text for multiple buttons.")

    # Build DB updates from payload
    updates: dict = {"status": "PENDING"}
    if payload.body_text is not None:
        updates["body_text"] = payload.body_text
    if payload.header_text is not None:
        updates["header_text"] = payload.header_text
    if payload.header_media_type is not None:
        updates["header_media_type"] = payload.header_media_type
    if payload.header_media_url is not None:
        updates["header_media_url"] = payload.header_media_url
    if payload.footer_text is not None:
        updates["footer_text"] = payload.footer_text
    if payload.buttons is not None:
        updates["buttons"] = [b.model_dump() for b in payload.buttons]

    # If the template has a meta_template_id, push update to Meta
    meta_template_id = template.get("meta_template_id")
    if meta_template_id:
        # Build Meta components from the merged template data
        merged_body = updates.get("body_text", template.get("body_text", ""))
        merged_header_text = updates.get("header_text", template.get("header_text"))
        merged_header_media_type = updates.get("header_media_type", template.get("header_media_type"))
        merged_header_media_url = updates.get("header_media_url", template.get("header_media_url"))
        merged_footer_text = updates.get("footer_text", template.get("footer_text"))
        merged_buttons = updates.get("buttons", template.get("buttons"))

        body_component: dict = {"type": "BODY", "text": merged_body}
        examples = _extract_variable_examples(merged_body)
        if examples:
            body_component["example"] = {"body_text": [examples]}
        components: list[dict] = [body_component]

        if merged_header_media_type and merged_header_media_type != "NONE":
            header_comp: dict = {"type": "HEADER", "format": merged_header_media_type.upper()}
            if merged_header_media_url:
                header_comp["example"] = {"header_handle": [merged_header_media_url]}
            components.append(header_comp)
        elif merged_header_text and merged_header_text.strip():
            components.append({
                "type": "HEADER",
                "format": "TEXT",
                "text": _sanitize_header_or_footer(merged_header_text),
            })

        if merged_footer_text and merged_footer_text.strip():
            components.append({
                "type": "FOOTER",
                "text": _sanitize_header_or_footer(merged_footer_text),
            })

        if merged_buttons:
            button_components = _build_button_components(merged_buttons, 3)
            if button_components:
                components.append({"type": "BUTTONS", "buttons": button_components})

        try:
            await update_template_on_meta(
                meta_template_id=meta_template_id,
                components=components,
                tenant_id=tenant_id,
            )
        except Exception as e:
            logger.warning(f"Meta template update failed for {meta_template_id}: {e}")
            # Still update locally even if Meta push fails

    db.table("message_templates").update(updates).eq("id", template_id).eq("tenant_id", tenant_id).execute()
    updated = db.table("message_templates").select("*").eq("id", template_id).limit(1).execute()
    return updated.data[0] if updated.data else None


@router.post("/upload-media")
async def upload_template_media(
    file: UploadFile = File(...),
    tenant_id: str = Depends(get_tenant_id),
):
    """Upload a media file for use in template headers. Returns the Meta header_handle."""
    access_token = get_setting("meta_access_token", tenant_id=tenant_id)
    if not access_token:
        raise HTTPException(status_code=400, detail="meta_access_token not configured in Settings")

    app_id = get_setting("meta_app_id", tenant_id=tenant_id)
    if not app_id:
        raise HTTPException(
            status_code=400,
            detail="meta_app_id not configured in Settings. Add it under Settings → Meta App ID.",
        )

    file_bytes = await file.read()
    file_type = file.content_type or "application/octet-stream"
    file_length = len(file_bytes)

    handle = await upload_media_for_template(
        file_bytes=file_bytes,
        file_type=file_type,
        file_length=file_length,
        app_id=app_id,
        access_token=access_token,
        tenant_id=tenant_id,
    )
    return {"header_handle": handle}
