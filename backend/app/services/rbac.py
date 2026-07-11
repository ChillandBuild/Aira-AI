from __future__ import annotations

from datetime import datetime, timezone


PERMISSION_CATALOG: list[dict] = [
    {"key": "dashboard.view", "label": "Dashboard", "group": "Overview"},
    {"key": "conversations.view", "label": "View conversations", "group": "Messaging"},
    {"key": "conversations.reply", "label": "Reply to conversations", "group": "Messaging"},
    {"key": "leads.view", "label": "View segments", "group": "Leads"},
    {"key": "leads.manage", "label": "Manage leads", "group": "Leads"},
    {"key": "inbound_leads.view", "label": "View inbound leads", "group": "Leads"},
    {"key": "outbound_leads.manage", "label": "Manage outbound leads", "group": "Messaging"},
    {"key": "templates.manage", "label": "Manage templates", "group": "Messaging"},
    {"key": "numbers.manage", "label": "Manage numbers pool", "group": "Messaging"},
    {"key": "knowledge.manage", "label": "Manage knowledge base", "group": "AI"},
    {"key": "catalog.manage", "label": "Manage catalog", "group": "AI"},
    {"key": "analytics.view", "label": "View analytics", "group": "Reports"},
    {"key": "subscription.manage", "label": "Manage subscription", "group": "Admin"},
    {"key": "team.view", "label": "View team performance", "group": "Team"},
    {"key": "team.manage", "label": "Manage team performance", "group": "Team"},
    {"key": "roles.manage", "label": "Manage users and roles", "group": "Admin"},
    {"key": "settings.manage", "label": "Manage settings", "group": "Admin"},
    {"key": "telecalling.dialer", "label": "Use dialer", "group": "Telecalling"},
    {"key": "telecalling.upload", "label": "Upload call lists", "group": "Telecalling"},
    {"key": "telecalling.scheduled", "label": "Scheduled calls", "group": "Telecalling"},
    {"key": "telecalling.notes", "label": "Call notes", "group": "Telecalling"},
]

ALL_PERMISSION_KEYS = [p["key"] for p in PERMISSION_CATALOG]

DEFAULT_TELECALLER_PERMISSIONS = [
    "dashboard.view",
    "conversations.view",
    "telecalling.dialer",
    "telecalling.scheduled",
    "telecalling.notes",
]


def normalize_permissions(values: list[str] | None) -> list[str]:
    allowed = set(ALL_PERMISSION_KEYS)
    return sorted({v for v in (values or []) if v in allowed})


def ensure_default_roles(db, tenant_id: str) -> dict:
    existing = (
        db.table("tenant_roles")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("slug", "telecaller")
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]

    row = {
        "tenant_id": tenant_id,
        "name": "Telecaller",
        "slug": "telecaller",
        "description": "Default calling workspace role for agents.",
        "permissions": DEFAULT_TELECALLER_PERMISSIONS,
        "is_system_template": True,
    }
    created = db.table("tenant_roles").insert(row).execute()
    return created.data[0]


def is_telecaller_role(role: dict | None) -> bool:
    if not role:
        return False
    permissions = role.get("permissions") or []
    return role.get("slug") == "telecaller" or "telecalling.dialer" in permissions


def get_user_role(db, tenant_id: str, role_id: str | None) -> dict | None:
    if not role_id:
        return None
    result = (
        db.table("tenant_roles")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("id", role_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def resolve_permissions(db, tenant_id: str, user_id: str, legacy_role: str) -> dict:
    if legacy_role == "owner":
        return {
            "role_id": None,
            "role_name": "Owner",
            "role_slug": "owner",
            "permissions": ALL_PERMISSION_KEYS,
            "force_password_reset": False,
        }

    ensure_default_roles(db, tenant_id)
    membership = (
        db.table("tenant_users")
        .select("role_id, force_password_reset")
        .eq("tenant_id", tenant_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    row = membership.data[0] if membership.data else {}
    role = get_user_role(db, tenant_id, row.get("role_id"))
    if not role:
        role = ensure_default_roles(db, tenant_id)
        db.table("tenant_users").update({"role_id": role["id"]}).eq("tenant_id", tenant_id).eq("user_id", user_id).execute()

    return {
        "role_id": role["id"],
        "role_name": role["name"],
        "role_slug": role.get("slug"),
        "permissions": normalize_permissions(role.get("permissions")),
        "force_password_reset": bool(row.get("force_password_reset")),
    }


def touch_updated_at(row: dict) -> dict:
    return {**row, "updated_at": datetime.now(timezone.utc).isoformat()}
