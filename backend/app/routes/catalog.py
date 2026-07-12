import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, require_permission

logger = logging.getLogger(__name__)
require_catalog_read = require_permission("catalog.view")
require_catalog_manage = require_permission("catalog.manage")

router = APIRouter(dependencies=[Depends(require_catalog_read)])

_VALID_STATUSES = {"draft", "ready"}
_AI_RULES_DEFAULTS = {"can_recommend": True, "can_send_images": True, "max_images_per_reply": 3}


@router.get("/items")
async def list_items(q: str | None = None, tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    query = db.table("catalog_items").select("*").eq("tenant_id", tenant_id)
    if q:
        query = query.ilike("name", f"%{q}%")
    res = query.order("created_at", desc=True).execute()
    return {"data": res.data or []}


@router.post("/items")
async def create_item(
    payload: dict,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_catalog_manage),
):
    db = get_supabase()
    res = db.table("catalog_items").insert({
        "tenant_id": tenant_id,
        "name": payload.get("name"),
        "item_type": payload.get("item_type") or "product",
        "description": payload.get("description"),
        "status": "draft",
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create catalog item")
    return res.data[0]


@router.patch("/items/{item_id}")
async def update_item(
    item_id: UUID,
    payload: dict,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_catalog_manage),
):
    db = get_supabase()
    updates = {k: v for k, v in payload.items() if k in {"name", "item_type", "description", "status"}}
    if "status" in updates and updates["status"] not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {_VALID_STATUSES}")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    res = (
        db.table("catalog_items")
        .update(updates)
        .eq("id", str(item_id))
        .eq("tenant_id", tenant_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Catalog item not found")
    return res.data[0]


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_catalog_manage),
):
    db = get_supabase()
    res = (
        db.table("catalog_items")
        .delete()
        .eq("id", str(item_id))
        .eq("tenant_id", tenant_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Catalog item not found")
    return {"success": True}


@router.post("/items/{item_id}/media")
async def upload_item_media(
    item_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    file: UploadFile = File(...),
    _ctx: dict = Depends(require_catalog_manage),
):
    db = get_supabase()
    item_res = (
        db.table("catalog_items")
        .select("id")
        .eq("id", str(item_id))
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    if not item_res.data:
        raise HTTPException(status_code=404, detail="Catalog item not found")

    content = await file.read()
    storage_path = f"{tenant_id}/{item_id}/{uuid4()}_{file.filename}"
    db.storage.from_("catalog-media").upload(
        storage_path, content, {"content-type": file.content_type or "application/octet-stream"}
    )
    url = db.storage.from_("catalog-media").get_public_url(storage_path)

    res = db.table("catalog_media").insert({
        "tenant_id": tenant_id,
        "catalog_item_id": str(item_id),
        "storage_path": storage_path,
        "label": file.filename,
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to save catalog media record")

    return {**res.data[0], "url": url}


@router.get("/media")
async def list_media(tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    media_res = (
        db.table("catalog_media")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .execute()
    )
    media_rows = media_res.data or []
    if not media_rows:
        return {"data": []}

    item_ids = list({row["catalog_item_id"] for row in media_rows})
    items_res = (
        db.table("catalog_items")
        .select("id,name")
        .in_("id", item_ids)
        .execute()
    )
    item_names = {row["id"]: row["name"] for row in (items_res.data or [])}

    data = [
        {
            **row,
            "item_name": item_names.get(row["catalog_item_id"]),
            "url": db.storage.from_("catalog-media").get_public_url(row["storage_path"]),
        }
        for row in media_rows
    ]
    return {"data": data}


@router.delete("/media/{media_id}")
async def delete_media(
    media_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_catalog_manage),
):
    db = get_supabase()
    media_res = (
        db.table("catalog_media")
        .select("storage_path")
        .eq("id", str(media_id))
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    if not media_res.data:
        raise HTTPException(status_code=404, detail="Catalog media not found")

    storage_path = media_res.data[0]["storage_path"]
    db.table("catalog_media").delete().eq("id", str(media_id)).eq("tenant_id", tenant_id).execute()
    try:
        db.storage.from_("catalog-media").remove([storage_path])
    except Exception as e:
        logger.warning(f"Failed to remove catalog media object {storage_path}: {e}")

    return {"success": True}


@router.get("/ai-rules")
async def get_ai_rules(tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    row = (
        db.table("app_settings")
        .select("value")
        .eq("tenant_id", tenant_id)
        .eq("key", "catalog_ai_rules")
        .limit(1)
        .execute()
    )
    stored = {}
    if row.data:
        try:
            stored = json.loads(row.data[0]["value"])
        except (ValueError, TypeError):
            stored = {}
    return {**_AI_RULES_DEFAULTS, **stored}


@router.patch("/ai-rules")
async def update_ai_rules(
    payload: dict,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_catalog_manage),
):
    db = get_supabase()
    current = await get_ai_rules(tenant_id)
    updates = {k: v for k, v in payload.items() if k in _AI_RULES_DEFAULTS}
    merged = {**current, **updates}

    db.table("app_settings").upsert({
        "tenant_id": tenant_id,
        "key": "catalog_ai_rules",
        "value": json.dumps(merged),
        "is_secret": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="tenant_id,key").execute()

    return merged
