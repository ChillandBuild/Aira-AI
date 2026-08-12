"""Pure CSV assembly for intake sessions. No I/O so the header-union and
label-collision rules stay directly unit-testable."""

FIXED_HEADERS = ["Lead", "Phone", "Status", "Package", "Amount charged", "Submitted", "Paid at"]


def _prettify(key: str) -> str:
    return " ".join(word.capitalize() for word in key.split("_"))


def build_csv_headers(rows: list[dict]) -> list[tuple[str, str]]:
    """(field_key, header_label) pairs, in first-seen order across rows.

    A key's label comes from the most recent row whose snapshot defines it, so a
    renamed field reads under its current name while a deleted one keeps the
    name it was collected under. Keys colliding on a label get the key appended
    so the columns stay distinguishable."""
    ordered_keys: list[str] = []
    labels: dict[str, str] = {}
    label_source_date: dict[str, str] = {}

    for row in sorted(rows, key=lambda r: r.get("created_at") or ""):
        created = row.get("created_at") or ""
        schema = {f["key"]: f["label"] for f in (row.get("field_schema") or [])}
        for key in (row.get("collected_data") or {}):
            if key not in ordered_keys:
                ordered_keys.append(key)
            if key in schema and created >= label_source_date.get(key, ""):
                labels[key] = schema[key]
                label_source_date[key] = created

    resolved = {key: labels.get(key) or _prettify(key) for key in ordered_keys}
    counts: dict[str, int] = {}
    for label in resolved.values():
        counts[label] = counts.get(label, 0) + 1

    return [
        (key, f"{label} ({key})" if counts[label] > 1 else label)
        for key, label in resolved.items()
    ]


def build_csv_row(row: dict, field_keys: list[str]) -> list[str]:
    leads = row.get("leads") or {}
    collected = row.get("collected_data") or {}
    amount = row.get("amount_paise")
    return [
        leads.get("name") or collected.get("name") or "",
        leads.get("phone") or "",
        row.get("status") or "",
        row.get("package_name") or "",
        f"{amount / 100:.2f}" if amount else "",
        row.get("created_at") or "",
        row.get("paid_at") or "",
        *[str(collected.get(key) or "") for key in field_keys],
    ]
