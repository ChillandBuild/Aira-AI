"""Body parameters for a broadcast template send.

Meta rejects a template send whose parameter count doesn't match the
template, so every {{n}} gets a value, in position: the mapped CSV column's
value, else the lead's name for {{1}}, else "Customer".
"""
import re

_VAR = re.compile(r"\{\{(\d+)\}\}")


def template_var_count(body: str | None) -> int:
    return max((int(n) for n in _VAR.findall(body or "")), default=0)


def body_parameters(body: str | None, mapping: list[str] | None, values: dict | None, lead_name: str | None) -> list[dict]:
    mapping = mapping or []
    values = values or {}
    params = []
    for i in range(template_var_count(body)):
        col = mapping[i] if i < len(mapping) else ""
        val = str(values.get(col) or "").strip() if col else ""
        if not val:
            val = (lead_name or "Customer") if i == 0 else "Customer"
        params.append({"type": "text", "text": val})
    return params


def approved_template(db, tenant_id: str, name: str) -> dict | None:
    """The tenant's template by name, only if Meta has it APPROVED right now.
    A template under review (e.g. after an edit), rejected or paused is not
    used anywhere -- Meta would refuse the send, or send wording not yet approved."""
    rows = (
        db.table("message_templates").select("name,language,body_text,status,variations")
        .eq("tenant_id", tenant_id).eq("name", name).limit(1).execute().data or []
    )
    if rows and (rows[0].get("status") or "").upper() == "APPROVED":
        return rows[0]
    return None


def template_status(db, tenant_id: str, name: str) -> str | None:
    rows = (
        db.table("message_templates").select("status")
        .eq("tenant_id", tenant_id).eq("name", name).limit(1).execute().data or []
    )
    return (rows[0].get("status") or "").upper() if rows else None
