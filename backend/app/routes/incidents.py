import logging
from fastapi import APIRouter, Depends
from app.db.supabase import get_supabase
from app.dependencies.tenant import require_owner

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_owner)])


@router.get("/")
async def list_incidents(limit: int = 50, offset: int = 0, ctx: dict = Depends(require_owner)):
    tenant_id = ctx["tenant_id"]
    db = get_supabase()

    incidents_result = (
        db.table("incidents")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )

    quality_result = (
        db.table("phone_number_quality_history")
        .select("id, phone_number_id, quality_rating, messaging_tier, recorded_at, tenant_id")
        .eq("tenant_id", tenant_id)
        .order("recorded_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )

    incidents = [
        {**row, "feed_type": "incident", "created_at": row["created_at"]}
        for row in (incidents_result.data or [])
    ]

    quality_rows = [
        {
            "id": row["id"],
            "feed_type": "quality_snapshot",
            "type": "quality_snapshot",
            "phone_number_id": row["phone_number_id"],
            "tenant_id": row["tenant_id"],
            "detail": {
                "quality_rating": row["quality_rating"],
                "messaging_tier": row["messaging_tier"],
            },
            "created_at": row["recorded_at"],
        }
        for row in (quality_result.data or [])
    ]

    merged = sorted(incidents + quality_rows, key=lambda r: r["created_at"], reverse=True)[:limit]

    return {"data": merged}
