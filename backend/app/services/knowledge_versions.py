"""Version history for the Description and each document's facts (spec §7).

Every write to either goes through this module, so any change can be undone. The
Description itself still lives in app_settings.business_description -- the reply path
(_build_base_prompt) is unchanged; this only records each value it has held.

A restore never rewrites history: it saves the old text as a new "restore" version."""
from app.config_dynamic import get_setting, invalidate_cache, save_setting

DESCRIPTION_KEY = "business_description"
_COLUMNS = "id,tenant_id,kind,document_id,content,reason,created_by,created_at"


def _insert(db, tenant_id: str, kind: str, document_id: str | None, content: str, reason: str, user_id: str | None) -> dict:
    row = {
        "tenant_id": tenant_id,
        "kind": kind,
        "document_id": document_id,
        "content": content,
        "reason": reason,
        "created_by": user_id,
    }
    return db.table("knowledge_versions").insert(row).execute().data[0]


def latest_version(db, tenant_id: str, kind: str, document_id: str | None = None) -> dict | None:
    q = db.table("knowledge_versions").select(_COLUMNS).eq("tenant_id", tenant_id).eq("kind", kind)
    q = q.eq("document_id", document_id) if document_id else q.is_("document_id", "null")
    res = q.order("created_at", desc=True).limit(1).execute()
    return (res.data or [None])[0]


def current_description(tenant_id: str) -> str:
    return (get_setting(DESCRIPTION_KEY, tenant_id=tenant_id) or "").strip()


def current_description_version(db, tenant_id: str) -> dict:
    """The version row matching the live Description. Writes a "baseline" row when
    there is no history yet, or when the live text changed outside this module -- so the
    text in force before any change is always recoverable."""
    text = current_description(tenant_id)
    latest = latest_version(db, tenant_id, "description")
    if latest is None or (latest.get("content") or "") != text:
        latest = _insert(db, tenant_id, "description", None, text, "baseline", None)
    return latest


def save_description(db, tenant_id: str, text: str, reason: str, user_id: str | None) -> dict:
    """The one write path for the Description: settings row + version row + cache."""
    current_description_version(db, tenant_id)
    text = (text or "").strip()
    save_setting(DESCRIPTION_KEY, text, tenant_id=tenant_id)
    invalidate_cache(DESCRIPTION_KEY)
    return _insert(db, tenant_id, "description", None, text, reason, user_id)


def save_facts_version(db, tenant_id: str, document_id: str, text: str, reason: str, user_id: str | None) -> dict:
    return _insert(db, tenant_id, "facts", document_id, (text or "").strip(), reason, user_id)


def list_versions(db, tenant_id: str, kind: str, document_id: str | None = None, limit: int = 50) -> list[dict]:
    q = db.table("knowledge_versions").select(_COLUMNS).eq("tenant_id", tenant_id).eq("kind", kind)
    q = q.eq("document_id", document_id) if document_id else q.is_("document_id", "null")
    return q.order("created_at", desc=True).limit(limit).execute().data or []


def get_version(db, tenant_id: str, version_id: str) -> dict | None:
    res = (
        db.table("knowledge_versions")
        .select(_COLUMNS)
        .eq("id", version_id)
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    return (res.data or [None])[0]
