"""Fleet view of Aira Brain for the operator clients list: how much is waiting on each client
and which sorted-file approvals have been stuck too long.

Computed in a fixed number of bulk queries (one per source, paged), not one round of
queries per tenant. It applies the same rules as services/brain/waiting.waiting_summary
(one pending review per document, forged rows dropped, dismissed conflicts hidden), and a
parity test keeps the two from drifting."""
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.services import consistency
from app.services.brain.paging import fetch_bounded

logger = logging.getLogger(__name__)

STUCK_APPROVAL_DAYS = 7
_ID_CHUNK = 100


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _pending_reviews(db) -> dict[str, list[str]]:
    """tenant_id -> created_at of each pending review, one per document (the latest), for
    documents that really belong to that tenant."""
    reviews = fetch_bounded(
        lambda: db.table("knowledge_reviews").select("id,tenant_id,document_id,created_at")
        .eq("status", "pending").order("created_at", desc=True).order("id"),
        "fleet pending reviews",
    )
    latest: dict[tuple[str, str], str] = {}
    for review in reviews:
        latest.setdefault((review["tenant_id"], review["document_id"]), review["created_at"])
    owners = _document_owners(db, sorted({document_id for _, document_id in latest}))
    by_tenant: dict[str, list[str]] = defaultdict(list)
    for (tenant_id, document_id), created_at in latest.items():
        if owners.get(document_id) == tenant_id:
            by_tenant[tenant_id].append(created_at)
    return by_tenant


def _document_owners(db, document_ids: list[str]) -> dict[str, str]:
    owners: dict[str, str] = {}
    for start in range(0, len(document_ids), _ID_CHUNK):
        chunk = document_ids[start:start + _ID_CHUNK]
        rows = db.table("knowledge_documents").select("id,tenant_id").in_("id", chunk).execute().data or []
        owners.update({r["id"]: r["tenant_id"] for r in rows})
    return owners


def _conflict_counts(db) -> dict[str, int]:
    """Visible (not dismissed) issues in each tenant's stored report. A missing, empty or
    malformed report counts 0, exactly as the per-tenant count does."""
    rows = fetch_bounded(
        lambda: db.table("app_settings").select("tenant_id,value").eq("key", consistency.REPORT_KEY).order("tenant_id"),
        "fleet consistency reports",
    )
    counts: dict[str, int] = {}
    for row in rows:
        try:
            report = json.loads(row.get("value") or "{}")
            issues = consistency.visible(report).get("issues")
        except (ValueError, TypeError, KeyError, AttributeError):
            logger.warning("fleet brain: malformed consistency report for tenant %s; counting 0", row.get("tenant_id"))
            continue
        if isinstance(issues, list) and issues:
            counts[row["tenant_id"]] = len(issues)
    return counts


def _failed_file_counts(db) -> dict[str, int]:
    rows = fetch_bounded(
        lambda: db.table("knowledge_documents").select("id,tenant_id")
        .or_("status.eq.failed,sort_state.eq.failed").order("id"),
        "fleet failed files",
    )
    return _tally(rows)


def _rejected_template_counts(db) -> dict[str, int]:
    rows = fetch_bounded(
        lambda: db.table("message_templates").select("id,tenant_id").eq("status", "REJECTED").order("id"),
        "fleet rejected templates",
    )
    return _tally(rows)


def _tally(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["tenant_id"]] += 1
    return counts


def _tenant_names(db) -> dict[str, str]:
    rows = fetch_bounded(lambda: db.table("tenants").select("id,name").order("id"), "fleet tenant names")
    return {r["id"]: r.get("name") or "" for r in rows}


def stuck_approval_alerts(rows: list[dict], names: dict[str, str], now: datetime) -> list[dict]:
    """Same shape as operator.compute_alerts entries, so the alert bell can take them as-is."""
    alerts = []
    for row in rows:
        days = row["oldest_review_days"]
        if days is None or row["oldest_review_at"] is None:
            continue
        if now - _parse_time(row["oldest_review_at"]) <= timedelta(days=STUCK_APPROVAL_DAYS):
            continue
        tenant_id = row["tenant_id"]
        name = names.get(tenant_id) or "A client"
        count = row["pending_reviews"]
        alerts.append({
            "id": f"brain:stuck_approval:{tenant_id}",
            "severity": "warning",
            "title": "Approval waiting over a week",
            "detail": f"{name} has {count} sorted file{'s' if count != 1 else ''} waiting for approval, the oldest for {days} days.",
            "tenant_id": tenant_id,
            "tenant_name": name,
            "source": "brain",
            "created_at": row["oldest_review_at"],
            "href": f"/operator/client/{tenant_id}?section=brain",
        })
    return sorted(alerts, key=lambda a: a["created_at"])


def fleet_waiting(db, *, now: datetime | None = None) -> dict:
    """{data: [{tenant_id, waiting_count, pending_reviews, oldest_review_days, oldest_review_at}],
    alerts: [...]}. Only tenants with something waiting appear; the list page treats a
    missing tenant as zero."""
    now = now or datetime.now(timezone.utc)
    reviews = _pending_reviews(db)
    conflicts = _conflict_counts(db)
    failed = _failed_file_counts(db)
    templates = _rejected_template_counts(db)
    rows = []
    for tenant_id in sorted({*reviews, *conflicts, *failed, *templates}):
        created = sorted(reviews.get(tenant_id, []), key=lambda value: _parse_time(value) or now)
        oldest = created[0] if created else None
        oldest_time = _parse_time(oldest)
        rows.append({
            "tenant_id": tenant_id,
            "waiting_count": len(created) + conflicts.get(tenant_id, 0) + failed.get(tenant_id, 0) + templates.get(tenant_id, 0),
            "pending_reviews": len(created),
            "oldest_review_days": max((now - oldest_time).days, 0) if oldest_time else None,
            "oldest_review_at": oldest,
        })
    alerts = stuck_approval_alerts(rows, _tenant_names(db), now) if any(r["pending_reviews"] for r in rows) else []
    return {"data": rows, "alerts": alerts, "stuck_after_days": STUCK_APPROVAL_DAYS}
