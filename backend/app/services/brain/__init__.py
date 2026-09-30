"""Aira Brain: one read-only view of what Aira knows, what is waiting on the client, and
how customers are being handled. One small module per source; build_brain() assembles them.

Everything takes plain values (tenant_id, role, permissions), never a request object, so
the operator route can call the same functions for any client."""
from collections.abc import Iterable
from datetime import datetime

from app.db.supabase import get_supabase
from app.services.brain import handovers, headline, inputs, status, waiting


def build_brain(tenant_id: str, *, role: str | None, permissions: Iterable[str] | None, db=None) -> dict:
    db = db or get_supabase()
    now = datetime.now(headline.IST)
    since = headline.window_start(now).isoformat()
    return {
        "headline": headline.build_headline(db, tenant_id, now=now),
        "waiting": waiting.waiting_summary(db, tenant_id),
        "inputs": inputs.build_inputs(db, tenant_id, role=role, permissions=permissions),
        "handovers": handovers.recent_handovers(db, tenant_id, since),
        "status": status.build_status(db, tenant_id, role=role, permissions=permissions),
    }


def brain_count(tenant_id: str, *, db=None) -> dict:
    """The sidebar badge (polled every 60s). Same helper as the hub's waiting block."""
    summary = waiting.waiting_summary(db or get_supabase(), tenant_id)
    return {
        "count": summary["count"],
        "sort_count": len(summary["sort_reviews"]),
        "consistency_count": summary["consistency_count"],
    }
