import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File

from app.config_dynamic import get_setting
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, require_permission
from app.services.catalog_retrieval import embed_and_store_catalog_item, reindex_catalog_items

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
        "attributes": payload.get("attributes") or {},
        "variant_group_id": payload.get("variant_group_id"),
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create catalog item")
    item = res.data[0]
    try:
        await embed_and_store_catalog_item(
            db, tenant_id, item["id"], item["name"], item["item_type"],
            item.get("description"), item.get("attributes") or {},
        )
    except Exception as e:
        logger.warning(f"Failed to embed catalog item {item['id']}: {e}")
    return item


@router.patch("/items/{item_id}")
async def update_item(
    item_id: UUID,
    payload: dict,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_catalog_manage),
):
    db = get_supabase()
    updates = {
        k: v for k, v in payload.items()
        if k in {"name", "item_type", "description", "status", "attributes", "variant_group_id"}
    }
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
    item = res.data[0]
    if {"name", "item_type", "description", "attributes"} & updates.keys():
        try:
            await embed_and_store_catalog_item(
                db, tenant_id, item["id"], item["name"], item["item_type"],
                item.get("description"), item.get("attributes") or {},
            )
        except Exception as e:
            logger.warning(f"Failed to re-embed catalog item {item['id']}: {e}")
    return item


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
    label: str | None = Form(None),
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

    existing_res = (
        db.table("catalog_media")
        .select("sort_order")
        .eq("catalog_item_id", str(item_id))
        .eq("tenant_id", tenant_id)
        .order("sort_order", desc=True)
        .limit(1)
        .execute()
    )
    next_sort_order = (existing_res.data[0]["sort_order"] + 1) if existing_res.data else 0

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
        "label": (label or "").strip() or file.filename,
        "sort_order": next_sort_order,
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to save catalog media record")

    return {**res.data[0], "url": url}


@router.patch("/media/{media_id}")
async def update_media(
    media_id: UUID,
    payload: dict,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_catalog_manage),
):
    db = get_supabase()
    updates: dict = {}
    if "label" in payload:
        updates["label"] = (payload.get("label") or "").strip() or None
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    res = (
        db.table("catalog_media")
        .update(updates)
        .eq("id", str(media_id))
        .eq("tenant_id", tenant_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Catalog media not found")
    return res.data[0]


@router.patch("/items/{item_id}/media/reorder")
async def reorder_item_media(
    item_id: UUID,
    payload: dict,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_catalog_manage),
):
    media_ids = payload.get("media_ids")
    if not isinstance(media_ids, list) or not media_ids:
        raise HTTPException(status_code=400, detail="media_ids must be a non-empty list")

    db = get_supabase()
    owned_res = (
        db.table("catalog_media")
        .select("id")
        .eq("catalog_item_id", str(item_id))
        .eq("tenant_id", tenant_id)
        .execute()
    )
    owned_ids = {row["id"] for row in (owned_res.data or [])}
    if not owned_ids.issuperset(set(media_ids)):
        raise HTTPException(status_code=400, detail="media_ids must all belong to this item")

    for index, media_id in enumerate(media_ids):
        db.table("catalog_media").update({"sort_order": index}).eq("id", media_id).eq("tenant_id", tenant_id).execute()

    return {"success": True}


@router.get("/media")
async def list_media(tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    media_res = (
        db.table("catalog_media")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("catalog_item_id")
        .order("sort_order")
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


def _catalog_ai_rules_stored(db, tenant_id: str) -> dict:
    """The client's own catalog_ai_rules preferences, merged with defaults -- no operator
    overlay. Operator controls (feature_enabled, max_images_ceiling) are surfaced
    separately so they never get written back into the client's stored blob."""
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


def _operator_media_recommendation_controls(tenant_id: str) -> tuple[bool, int]:
    """(feature_enabled, max_images_ceiling) as set by the operator console. The client
    can choose anything under the ceiling but never above it -- see decisions/log.md."""
    enabled = get_setting("ai_media_recommendations_enabled", fallback="true", tenant_id=tenant_id) == "true"
    ceiling_raw = get_setting("catalog_ai_max_images_ceiling", fallback="5", tenant_id=tenant_id) or "5"
    try:
        ceiling = max(0, int(float(ceiling_raw)))
    except (TypeError, ValueError):
        ceiling = 5
    return enabled, ceiling


@router.get("/ai-rules")
async def get_ai_rules(tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    rules = _catalog_ai_rules_stored(db, tenant_id)
    feature_enabled, ceiling = _operator_media_recommendation_controls(tenant_id)
    return {**rules, "feature_enabled": feature_enabled, "max_images_ceiling": ceiling}


@router.patch("/ai-rules")
async def update_ai_rules(
    payload: dict,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_catalog_manage),
):
    db = get_supabase()
    current = _catalog_ai_rules_stored(db, tenant_id)
    updates = {k: v for k, v in payload.items() if k in _AI_RULES_DEFAULTS}

    feature_enabled, ceiling = _operator_media_recommendation_controls(tenant_id)
    if "max_images_per_reply" in updates:
        try:
            requested = int(updates["max_images_per_reply"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="max_images_per_reply must be a whole number")
        if requested < 0:
            raise HTTPException(status_code=400, detail="max_images_per_reply cannot be negative")
        if requested > ceiling:
            raise HTTPException(status_code=400, detail=f"max_images_per_reply cannot exceed {ceiling}, the limit set for your account")

    merged = {**current, **updates}

    db.table("app_settings").upsert({
        "tenant_id": tenant_id,
        "key": "catalog_ai_rules",
        "value": json.dumps(merged),
        "is_secret": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="tenant_id,key").execute()

    return {**merged, "feature_enabled": feature_enabled, "max_images_ceiling": ceiling}


@router.post("/variant-groups")
async def create_variant_group(
    payload: dict,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_catalog_manage),
):
    db = get_supabase()
    res = db.table("catalog_variant_groups").insert({
        "tenant_id": tenant_id,
        "name": payload.get("name"),
        "item_type": payload.get("item_type") or "product",
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create variant group")
    return res.data[0]


@router.get("/variant-groups")
async def list_variant_groups(tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    res = (
        db.table("catalog_variant_groups")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .execute()
    )
    return {"data": res.data or []}


@router.post("/reindex")
async def reindex_catalog(
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_catalog_manage),
):
    """Backfill embeddings for existing catalog items (run once after grouping variants)."""
    result = await reindex_catalog_items(tenant_id)
    return {"success": True, **result}
