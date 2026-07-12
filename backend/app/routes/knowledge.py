import logging
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, require_permission
from app.services.knowledge_service import process_document, reindex_tenant

logger = logging.getLogger(__name__)
require_knowledge_read = require_permission("knowledge.view")
require_knowledge_manage = require_permission("knowledge.manage")

router = APIRouter(dependencies=[Depends(require_knowledge_read)])


@router.get("/documents")
async def list_documents(tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    res = db.table("knowledge_documents").select("*").eq("tenant_id", tenant_id).order("created_at", desc=True).execute()
    return {"data": res.data or []}


@router.post("/upload-document")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    campaign_tag_id: Optional[str] = Form(None),
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_knowledge_manage),
):
    content = await file.read()
    db = get_supabase()

    # Empty-string from a multipart form means "All campaigns" → store as NULL.
    campaign_tag_id = campaign_tag_id or None

    # 1. Create document record
    doc_data = {
        "tenant_id": tenant_id,
        "name": file.filename,
        "file_type": file.content_type or "application/octet-stream",
        "size_bytes": len(content),
        "status": "processing",
        "campaign_tag_id": campaign_tag_id,
    }
    res = db.table("knowledge_documents").insert(doc_data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create document record")

    doc_id = res.data[0]["id"]

    # 2. Process in background
    background_tasks.add_task(
        process_document,
        document_id=doc_id,
        tenant_id=tenant_id,
        file_content=content,
        filename=file.filename,
        mime_type=file.content_type,
        campaign_tag_id=campaign_tag_id,
    )
    
    return res.data[0]



@router.post("/reindex")
async def reindex_documents(
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_knowledge_manage),
):
    """Backfill RAG embeddings for all indexed documents (run once after enabling RAG)."""
    result = await reindex_tenant(tenant_id)
    return {"success": True, **result}


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_knowledge_manage),
):
    db = get_supabase()
    # Chunks are deleted via CASCADE
    db.table("knowledge_documents").delete().eq("id", str(doc_id)).eq("tenant_id", tenant_id).execute()
    return {"success": True}
