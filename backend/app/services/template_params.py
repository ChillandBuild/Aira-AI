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
