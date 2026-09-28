"""SIM clients get no telecaller evaluation anywhere (2026-09-28 decision): no
scores, no winners, no QA review -- and "no evidence" means not even a null
score field on a call-log row. Every endpoint that returns call_logs rows
(recent calls, a caller's own log, a lead's call history, the CSV export)
strips these fields for a SIM tenant with this one helper instead of each
duplicating the field list and the provider check."""

EVALUATION_FIELDS = (
    "score", "score_status", "score_final", "evaluation", "call_group",
    "talk_share", "interruption_count", "interruptions_per_5min",
    "ai_call_status", "rules_version",
)


def _without_evaluation(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in EVALUATION_FIELDS}


def strip_evaluation(rows: list[dict] | dict | None, is_sim: bool) -> list[dict] | dict | None:
    """Return call-log row(s) with every evaluation field removed when `is_sim`
    is True. Returns new dict(s) -- the row(s) passed in are never mutated, so
    this is safe to call on rows a caller still holds a reference to. For
    TeleCMI tenants this is a no-op: the same object comes back unchanged.
    Callers do the `calling_provider` lookup once per request and pass the
    result in, rather than this helper looking it up itself on every row."""
    if not is_sim or rows is None:
        return rows
    if isinstance(rows, dict):
        return _without_evaluation(rows)
    return [_without_evaluation(row) if isinstance(row, dict) else row for row in rows]
