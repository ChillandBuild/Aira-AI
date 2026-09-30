"""What is waiting on the client: sorted-file reviews, stored conflicts, failed files and
rejected templates.

waiting_summary() is the ONE helper both GET /brain (waiting block) and GET /brain/count
use, so the sidebar badge and the hub total cannot disagree. It reads the stored
consistency report only (load_report + visible): never gather(), never current_report,
never a model call."""
import logging

from app.services import consistency

logger = logging.getLogger(__name__)

REVIEW_SCAN_LIMIT = 500
FAILED_FILES_LIMIT = 50
REJECTED_TEMPLATES_LIMIT = 50
_ID_CHUNK = 100


def consistency_issue_count(tenant_id: str) -> int:
    """Visible (not dismissed) issues in the stored report. Missing, empty or malformed
    report means 0."""
    report = consistency.load_report(tenant_id)
    try:
        issues = consistency.visible(report).get("issues")
    except (KeyError, TypeError, AttributeError):
        logger.warning("brain: malformed consistency report for tenant %s; counting 0", tenant_id)
        return 0
    return len(issues) if isinstance(issues, list) else 0


def _tenant_document_names(db, tenant_id: str, document_ids: list[str]) -> dict[str, str]:
    """id -> name for the ids that really belong to this tenant (drops forged rows)."""
    names: dict[str, str] = {}
    for start in range(0, len(document_ids), _ID_CHUNK):
        chunk = document_ids[start:start + _ID_CHUNK]
        rows = db.table("knowledge_documents").select("id,name").eq("tenant_id", tenant_id).in_("id", chunk).execute().data or []
        names.update({row["id"]: row.get("name") or "" for row in rows})
    return names


def pending_sort_reviews(db, tenant_id: str) -> list[dict]:
    """One pending review per document (the latest), newest first, only for documents that
    belong to this tenant. run_sort marks older pending rows discarded, but the database
    does not enforce it, and a forged row could name another tenant's document."""
    reviews = (
        db.table("knowledge_reviews")
        .select("id,document_id,created_at")
        .eq("tenant_id", tenant_id)
        .eq("status", "pending")
        .order("created_at", desc=True)
        .limit(REVIEW_SCAN_LIMIT)
        .execute()
    ).data or []
    latest_per_document: dict[str, dict] = {}
    for review in reviews:
        latest_per_document.setdefault(review["document_id"], review)
    names = _tenant_document_names(db, tenant_id, list(latest_per_document))
    return [
        {"id": r["id"], "document_id": r["document_id"], "title": names[r["document_id"]], "created_at": r["created_at"]}
        for r in latest_per_document.values()
        if r["document_id"] in names
    ]


def failed_files(db, tenant_id: str) -> list[dict]:
    """Documents whose upload or sort failed (status or sort_state 'failed')."""
    rows = (
        db.table("knowledge_documents")
        .select("id,name")
        .eq("tenant_id", tenant_id)
        .or_("status.eq.failed,sort_state.eq.failed")
        .order("created_at", desc=True)
        .limit(FAILED_FILES_LIMIT)
        .execute()
    ).data or []
    return [{"id": r["id"], "name": r.get("name") or ""} for r in rows]


def rejected_templates(db, tenant_id: str) -> list[dict]:
    """WhatsApp templates Meta rejected (message_templates.status is stored upper-case)."""
    rows = (
        db.table("message_templates")
        .select("id,name,rejection_reason")
        .eq("tenant_id", tenant_id)
        .eq("status", "REJECTED")
        .order("submitted_at", desc=True)
        .limit(REJECTED_TEMPLATES_LIMIT)
        .execute()
    ).data or []
    return [{"id": r["id"], "name": r.get("name") or "", "reason": r.get("rejection_reason")} for r in rows]


def waiting_summary(db, tenant_id: str) -> dict:
    """The waiting block of GET /brain. count = every item the client has to act on."""
    reviews = pending_sort_reviews(db, tenant_id)
    conflicts = consistency_issue_count(tenant_id)
    files = failed_files(db, tenant_id)
    templates = rejected_templates(db, tenant_id)
    return {
        "count": len(reviews) + conflicts + len(files) + len(templates),
        "sort_reviews": reviews,
        "consistency_count": conflicts,
        "failed_files": files,
        "rejected_templates": templates,
    }
