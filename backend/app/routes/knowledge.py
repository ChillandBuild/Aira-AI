import logging
from typing import Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, require_permission
from app.services.knowledge_service import process_document, reindex_tenant

logger = logging.getLogger(__name__)
require_knowledge_read = require_permission("knowledge.view")
require_knowledge_manage = require_permission("knowledge.manage")

_DOCS_BUCKET = "knowledge-documents"

router = APIRouter(dependencies=[Depends(require_knowledge_read)])


def _doc_signed_url(db, path: str, expires_in: int = 300) -> str | None:
    """Short-lived signed URL for a private knowledge-document object. Supabase has
    returned this key under several spellings across client versions, so check all of
    them -- same defensive read as _create_csv_signed_url in upload.py."""
    result = db.storage.from_(_DOCS_BUCKET).create_signed_url(path, expires_in)
    if isinstance(result, dict):
        return (
            result.get("signedURL")
            or result.get("signedUrl")
            or result.get("signed_url")
            or result.get("url")
        )
    return None


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

    # Keep the original file so the client can download it later. Best-effort: a storage
    # failure must not block indexing -- the document still works for RAG without its
    # original, it just can't be downloaded (same state as every pre-migration-144 doc).
    storage_path: str | None = None
    try:
        candidate = f"{tenant_id}/{uuid4()}_{file.filename}"
        db.storage.from_(_DOCS_BUCKET).upload(
            candidate, content, {"content-type": file.content_type or "application/octet-stream"}
        )
        storage_path = candidate
    except Exception as e:
        logger.warning(f"Knowledge document storage upload failed for tenant {tenant_id}: {e}")

    # 1. Create document record
    doc_data = {
        "tenant_id": tenant_id,
        "name": file.filename,
        "file_type": file.content_type or "application/octet-stream",
        "size_bytes": len(content),
        "status": "processing",
        "campaign_tag_id": campaign_tag_id,
        "storage_path": storage_path,
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


@router.get("/documents/{doc_id}/content")
async def document_content(
    doc_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
):
    """The extracted text the AI actually reads for this document -- not the original
    file. `downloadable` tells the UI whether to offer a download button: documents
    uploaded before migration 144 have no stored original."""
    db = get_supabase()
    res = (
        db.table("knowledge_documents")
        .select("id,name,file_type,size_bytes,status,full_text,storage_path,created_at")
        .eq("id", str(doc_id))
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Document not found")

    row = res.data[0]
    return {
        "id": row["id"],
        "name": row["name"],
        "file_type": row["file_type"],
        "size_bytes": row["size_bytes"],
        "status": row["status"],
        "created_at": row["created_at"],
        "full_text": row.get("full_text") or "",
        "downloadable": bool(row.get("storage_path")),
    }


@router.get("/documents/{doc_id}/download")
async def document_download(
    doc_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
):
    """Short-lived signed URL for the original uploaded file. 404s for documents that
    predate migration 144 -- their originals were never stored and cannot be recovered."""
    db = get_supabase()
    res = (
        db.table("knowledge_documents")
        .select("storage_path,name")
        .eq("id", str(doc_id))
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Document not found")

    storage_path = res.data[0].get("storage_path")
    if not storage_path:
        raise HTTPException(
            status_code=404,
            detail="The original file for this document was not stored. Re-upload it to enable download.",
        )

    try:
        url = _doc_signed_url(db, storage_path)
    except Exception as e:
        logger.error(f"Knowledge document signed URL failed for doc {doc_id}: {e}")
        raise HTTPException(status_code=502, detail="Could not generate a download link")
    if not url:
        raise HTTPException(status_code=502, detail="Could not generate a download link")

    return {"url": url, "name": res.data[0].get("name")}


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_knowledge_manage),
):
    db = get_supabase()

    # Remove the stored original first so deleting a document doesn't orphan its file in
    # the bucket. Best-effort -- a storage failure must not block the row delete.
    existing = (
        db.table("knowledge_documents")
        .select("storage_path")
        .eq("id", str(doc_id))
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    storage_path = (existing.data[0].get("storage_path") if existing.data else None)
    if storage_path:
        try:
            db.storage.from_(_DOCS_BUCKET).remove([storage_path])
        except Exception as e:
            logger.warning(f"Knowledge document storage delete failed for {storage_path}: {e}")

    # Chunks are deleted via CASCADE
    db.table("knowledge_documents").delete().eq("id", str(doc_id)).eq("tenant_id", tenant_id).execute()
    return {"success": True}
