"""'What you told Anril': five rows, one function each. A row is
{key, label, state, detail, edit_href, can_edit, reason}; state is ok | missing | off |
attention. Rows may carry one extra key (description: sections, products: flag).
Adding an input is one function here plus one test."""
import json
import logging
from collections.abc import Iterable

from app.config_dynamic import get_setting
from app.services import business_details, business_profile, deal_engine, intake
from app.services.brain.access import OWNER_ROLE, has_permission

logger = logging.getLogger(__name__)

OWNER_ONLY = "Owner only"
NEEDS_MANAGE = "Needs manage access"


def _row(key: str, label: str, state: str, detail: str, edit_href: str, can_edit: bool, reason: str) -> dict:
    return {
        "key": key, "label": label, "state": state, "detail": detail,
        "edit_href": edit_href, "can_edit": can_edit, "reason": None if can_edit else reason,
    }


def _count(db, table: str, tenant_id: str, **equals: str) -> int:
    query = db.table(table).select("id", count="exact").eq("tenant_id", tenant_id)
    for column, value in equals.items():
        query = query.eq(column, value)
    return query.limit(1).execute().count or 0


def description_row(tenant_id: str, role: str | None) -> dict:
    """Filled or empty per section. The section list comes from business_profile.SECTIONS."""
    text = (get_setting("business_description", tenant_id=tenant_id) or "").strip()
    filled = business_profile.parse(text).sections
    sections = [
        {"key": s.key, "label": s.label, "filled": bool(filled.get(s.key))}
        for s in business_profile.SECTIONS
    ]
    done = sum(1 for s in sections if s["filled"])
    total = len(sections)
    if done == total:
        state, detail = "ok", f"All {total} sections filled"
    elif done:
        state, detail = "attention", f"{done} of {total} sections filled"
    elif text:
        state, detail = "attention", "Not in sections yet"
    else:
        state, detail = "missing", "Not written yet"
    row = _row(
        "description", f"Description ({total} sections)", state, detail,
        "/dashboard/knowledge?tab=description", role == OWNER_ROLE, OWNER_ONLY,
    )
    return {**row, "sections": sections}


def knowledge_files_row(db, tenant_id: str, can_edit: bool) -> dict:
    live = _count(db, "knowledge_documents", tenant_id, status="indexed")
    state, detail = ("ok", f"{live} file{'s' if live != 1 else ''} live") if live else ("missing", "No files live")
    return _row("knowledge_files", "Knowledge files", state, detail, "/dashboard/knowledge?tab=documents", can_edit, NEEDS_MANAGE)


def services_row(tenant_id: str, db, can_edit: bool) -> dict:
    config = intake.get_intake_config(tenant_id, db=db)
    packages = len(intake.normalize_packages(config))
    if deal_engine.is_enabled(config):
        state, detail = "ok", f"On, {packages} package{'s' if packages != 1 else ''}"
    elif config.get("enabled"):
        state, detail = "attention", "On, but nothing to buy yet"
    elif packages:
        state, detail = "off", "Switched off"
    else:
        state, detail = "missing", "Not set up"
    return _row("services", "Services", state, detail, "/dashboard/services", can_edit, NEEDS_MANAGE)


def products_row(db, tenant_id: str, can_edit: bool) -> dict:
    """Only ready items reach Anril; draft ones are a flag on this row, not their own card."""
    ready = _count(db, "catalog_items", tenant_id, status="ready")
    drafts = _count(db, "catalog_items", tenant_id, status="draft")
    state, detail = ("ok", f"{ready} ready") if ready else ("missing", "No ready products")
    row = _row("products", "Products and AI rules", state, detail, "/dashboard/catalog", can_edit, NEEDS_MANAGE)
    flag = f"{drafts} draft product{'s' if drafts != 1 else ''} Anril can't see yet" if drafts else None
    return {**row, "flag": flag}


def business_details_row(tenant_id: str, can_edit: bool) -> dict:
    stored = _stored_business_details(tenant_id)
    filled = any(str(stored.get(field) or "").strip() for field in business_details.TEXT_FIELDS)
    state, detail = ("ok", "Set") if filled else ("missing", "Not filled in")
    return _row("business_details", "Business details", state, detail, "/dashboard/settings/business", can_edit, NEEDS_MANAGE)


def _stored_business_details(tenant_id: str) -> dict:
    raw = get_setting(business_details.SETTING_KEY, tenant_id=tenant_id)
    try:
        data = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        logger.warning("brain: unparseable business_details for tenant %s", tenant_id)
        return {}
    return data if isinstance(data, dict) else {}


def build_inputs(db, tenant_id: str, *, role: str | None, permissions: Iterable[str] | None) -> list[dict]:
    perms = list(permissions or [])
    can_manage_knowledge = has_permission(role, perms, "knowledge.manage")
    can_manage_settings = has_permission(role, perms, "settings.manage")
    can_manage_catalog = has_permission(role, perms, "catalog.manage")
    return [
        description_row(tenant_id, role),
        knowledge_files_row(db, tenant_id, can_manage_knowledge),
        services_row(tenant_id, db, can_manage_settings),
        products_row(db, tenant_id, can_manage_catalog),
        business_details_row(tenant_id, can_manage_settings),
    ]
