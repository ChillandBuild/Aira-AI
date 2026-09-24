import logging
from typing import Literal, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel, Field
from app.config_dynamic import get_setting
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, require_permission
from app.services import knowledge_sort as ks
from app.services import knowledge_versions as kv
from app.services.knowledge_kit import readiness
from app.services.knowledge_service import DOCS_BUCKET, process_document, reindex_tenant

logger = logging.getLogger(__name__)
require_knowledge_read = require_permission("knowledge.view")
require_knowledge_manage = require_permission("knowledge.manage")

_DOCS_BUCKET = DOCS_BUCKET

# The list view never needs the large text columns (full_text / source_text can each
# be ~50,000 characters per document).
_DOC_LIST_COLUMNS = (
    "id,tenant_id,name,file_type,size_bytes,status,error_message,created_at,"
    "campaign_tag_id,storage_path,sorted_at,sort_state"
)

router = APIRouter(dependencies=[Depends(require_knowledge_read)])


def _http(e: ks.KnowledgeError) -> HTTPException:
    """Auto-sort errors carry their own status; detail is always a plain string because
    the frontend's apiFetch surfaces it with new Error(detail)."""
    return HTTPException(status_code=e.status, detail=str(e))


def _is_owner(ctx: dict) -> bool:
    return ctx.get("role") == "owner"


def _queue_rubric(tenant_id: str, result: dict) -> bool:
    if not result.get("description_changed"):
        return False
    from app.routes.ai_tune import queue_rubric_for_description

    return queue_rubric_for_description(
        tenant_id, result.get("final_description") or "", base_was_empty=bool(result.get("base_was_empty"))
    )


class ApplyReviewBody(BaseModel):
    base_version_id: str = Field(max_length=64)
    accepted_hunk_ids: list[str] = Field(default_factory=list, max_length=2_000)
    conflict_choices: dict[str, Literal["a", "b", "none"]] = Field(default_factory=dict, max_length=500)
    accepted_update_ids: list[str] = Field(default_factory=list, max_length=500)


class FactsBody(BaseModel):
    text: str = Field(max_length=100_000)


class DeleteDocumentBody(BaseModel):
    base_version_id: Optional[str] = Field(default=None, max_length=64)
    remove_edited: list[str] = Field(default_factory=list, max_length=2_000)


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


def _search_issue(doc: dict, *, has_chunks: bool, has_jina_key: bool) -> str | None:
    """None once a document is actually searchable; otherwise the one reason it isn't,
    so the client can tell "not indexed yet" from "no Jina key configured"."""
    if doc.get("status") != "indexed" or has_chunks:
        return None
    return "no_jina_key" if not has_jina_key else "not_indexed"


@router.get("/documents")
async def list_documents(tenant_id: str = Depends(get_tenant_id)):
    db = get_supabase()
    res = db.table("knowledge_documents").select(_DOC_LIST_COLUMNS).eq("tenant_id", tenant_id).order("created_at", desc=True).execute()
    docs = res.data or []
    pending = (
        db.table("knowledge_reviews")
        .select("document_id")
        .eq("tenant_id", tenant_id)
        .eq("status", "pending")
        .execute()
    )
    pending_ids = {r["document_id"] for r in (pending.data or [])}

    # One query for every document's chunk count instead of one per document (no N+1).
    chunk_rows = db.table("knowledge_chunks").select("document_id").eq("tenant_id", tenant_id).execute()
    chunked_ids = {r["document_id"] for r in (chunk_rows.data or [])}
    has_jina_key = bool(get_setting("jina_api_key", tenant_id=tenant_id))

    for doc in docs:
        doc["has_pending_review"] = doc["id"] in pending_ids
        has_chunks = doc["id"] in chunked_ids
        doc["searchable"] = doc.get("status") == "indexed" and has_chunks
        doc["search_issue"] = _search_issue(doc, has_chunks=has_chunks, has_jina_key=has_jina_key)
    return {"data": docs}


@router.get("/readiness")
async def get_readiness(tenant_id: str = Depends(get_tenant_id)):
    """Which of the 8 Business Kit headings Aira already has. Only live (indexed)
    documents count, since a file waiting for review isn't answering leads yet. Served
    here rather than under /ai-tune (owner-only) so a manager sees the real state."""
    db = get_supabase()
    live = (
        db.table("knowledge_documents")
        .select("full_text")
        .eq("tenant_id", tenant_id)
        .eq("status", "indexed")
        .execute()
    )
    return {"data": readiness(
        description=get_setting("business_description", tenant_id=tenant_id) or "",
        handover_line=get_setting("handover_line", tenant_id=tenant_id) or "",
        facts=[row.get("full_text") or "" for row in (live.data or [])],
    )}


@router.post("/upload-document")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    campaign_tag_id: Optional[str] = Form(None),
    replaces_document_id: Optional[str] = Form(None),
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_knowledge_manage),
):
    content = await file.read()
    db = get_supabase()

    # Empty-string from a multipart form means "All campaigns" → store as NULL.
    campaign_tag_id = campaign_tag_id or None

    # "Does this replace an existing file?" (auto-sort spec §6.4). The old file is only
    # removed when the new one's review is applied.
    replaces_document_id = replaces_document_id or None
    if replaces_document_id:
        try:
            replaces_document_id = str(UUID(replaces_document_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="The file you chose to replace wasn't found.")
        exists = (
            db.table("knowledge_documents")
            .select("id")
            .eq("id", replaces_document_id)
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
        if not exists.data:
            raise HTTPException(status_code=400, detail="The file you chose to replace wasn't found.")

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
        replaces_document_id=replaces_document_id,
        user_id=_ctx.get("user_id"),
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
    """The text the AI actually looks up for this document -- not the original file.
    For a sorted document that is its FACTS only; for a legacy (never sorted) document
    it is still the whole extracted text, and `sorted` is False so the UI can say so.
    `downloadable` tells the UI whether to offer a download button: documents uploaded
    before migration 144 have no stored original."""
    db = get_supabase()
    res = (
        db.table("knowledge_documents")
        .select("id,name,file_type,size_bytes,status,full_text,storage_path,created_at,sorted_at,sort_state")
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
        "sorted": bool(row.get("sorted_at")),
        "sort_state": row.get("sort_state"),
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


@router.get("/documents/{doc_id}/delete-preview")
async def delete_preview(doc_id: UUID, tenant_id: str = Depends(get_tenant_id)):
    """What deleting this file removes: its facts, and the Description lines only it
    added. Lines the client has since edited are listed separately (spec §6.3)."""
    try:
        return ks.build_delete_preview(get_supabase(), tenant_id, str(doc_id))
    except ks.KnowledgeError as e:
        raise _http(e)


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: UUID,
    body: Optional[DeleteDocumentBody] = Body(default=None),
    tenant_id: str = Depends(get_tenant_id),
    ctx: dict = Depends(require_knowledge_manage),
):
    """Delete a file, its stored original and its chunks, and take the Description
    lines only it added out of the Description. With no body, edited lines are kept and
    the staleness check is skipped."""
    body = body or DeleteDocumentBody()
    try:
        result = ks.delete_document(
            get_supabase(),
            tenant_id,
            str(doc_id),
            base_version_id=body.base_version_id,
            remove_edited=body.remove_edited,
            user_id=ctx.get("user_id"),
            is_owner=_is_owner(ctx),
        )
    except ks.KnowledgeError as e:
        raise _http(e)
    _queue_rubric(tenant_id, result)
    return {"success": True, "description_changed": result["description_changed"]}


# ─── Knowledge Auto-Sort: review, re-sort, facts, history ─────────────────────

@router.get("/documents/{doc_id}/review")
async def get_review(doc_id: UUID, tenant_id: str = Depends(get_tenant_id)):
    try:
        return ks.build_review_payload(get_supabase(), tenant_id, str(doc_id))
    except ks.KnowledgeError as e:
        raise _http(e)


@router.post("/documents/{doc_id}/review/apply")
async def apply_review(
    doc_id: UUID,
    body: ApplyReviewBody,
    background_tasks: BackgroundTasks,
    tenant_id: str = Depends(get_tenant_id),
    ctx: dict = Depends(require_knowledge_manage),
):
    try:
        result = ks.apply_review(
            get_supabase(),
            tenant_id,
            str(doc_id),
            ks.ApplyChoices(**body.model_dump()),
            user_id=ctx.get("user_id"),
            is_owner=_is_owner(ctx),
        )
    except ks.KnowledgeError as e:
        raise _http(e)
    # Embedding runs after the response; the full-text fallback serves the facts meanwhile.
    background_tasks.add_task(ks.index_facts, tenant_id, str(doc_id), result["facts"], result["campaign_tag_id"])
    rubric_queued = _queue_rubric(tenant_id, result)
    return {"success": True, "description_changed": result["description_changed"], "rubric_queued": rubric_queued}


@router.post("/documents/{doc_id}/review/discard")
async def discard_review(
    doc_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_knowledge_manage),
):
    try:
        ks.discard_review(get_supabase(), tenant_id, str(doc_id))
    except ks.KnowledgeError as e:
        raise _http(e)
    return {"success": True}


@router.post("/documents/{doc_id}/resort")
async def resort_document(
    doc_id: UUID,
    background_tasks: BackgroundTasks,
    tenant_id: str = Depends(get_tenant_id),
    ctx: dict = Depends(require_knowledge_manage),
):
    """Sort a legacy file for the first time, retry a failed sort, or rebuild a review
    that went stale. The file keeps serving replies while it's sorted."""
    try:
        ks.prepare_resort(get_supabase(), tenant_id, str(doc_id))
    except ks.KnowledgeError as e:
        raise _http(e)
    background_tasks.add_task(ks.sort_document, tenant_id=tenant_id, document_id=str(doc_id), user_id=ctx.get("user_id"))
    return {"success": True}


@router.put("/documents/{doc_id}/facts")
async def update_facts(
    doc_id: UUID,
    body: FactsBody,
    background_tasks: BackgroundTasks,
    tenant_id: str = Depends(get_tenant_id),
    ctx: dict = Depends(require_knowledge_manage),
):
    try:
        result = ks.update_facts(get_supabase(), tenant_id, str(doc_id), body.text, ctx.get("user_id"))
    except ks.KnowledgeError as e:
        raise _http(e)
    background_tasks.add_task(ks.index_facts, tenant_id, str(doc_id), result["facts"], result["campaign_tag_id"])
    return {"success": True, "full_text": result["facts"]}


@router.get("/versions")
async def list_versions(
    kind: Literal["description", "facts"],
    document_id: Optional[UUID] = None,
    tenant_id: str = Depends(get_tenant_id),
):
    db = get_supabase()
    if kind == "facts":
        if not document_id:
            raise HTTPException(status_code=400, detail="Choose a file to see its history.")
        return {"data": kv.list_versions(db, tenant_id, "facts", str(document_id))}
    # Make sure the Description in force right now appears in its own history.
    kv.current_description_version(db, tenant_id)
    return {"data": kv.list_versions(db, tenant_id, "description")}


@router.post("/versions/{version_id}/restore")
async def restore_version(
    version_id: UUID,
    background_tasks: BackgroundTasks,
    tenant_id: str = Depends(get_tenant_id),
    ctx: dict = Depends(require_knowledge_manage),
):
    try:
        result = ks.restore_version(
            get_supabase(), tenant_id, str(version_id), user_id=ctx.get("user_id"), is_owner=_is_owner(ctx)
        )
    except ks.KnowledgeError as e:
        raise _http(e)
    if result["kind"] == "facts":
        background_tasks.add_task(ks.index_facts, tenant_id, result["document_id"], result["facts"], result["campaign_tag_id"])
    else:
        _queue_rubric(tenant_id, result)
    return {"success": True, "kind": result["kind"]}
