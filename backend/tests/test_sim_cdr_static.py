import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_sim_sync_token_migration_contract():
    source = _read("supabase/migrations/122_sim_sync_token.sql")
    assert "add column if not exists sync_token text unique" in source
    assert "uq_call_logs_caller_sim_entry" in source
    assert "where provider = 'sim_basic' and call_sid is not null" in source


def test_sim_cdr_endpoint_exists():
    source = _read("app/routes/calls.py")
    # Endpoint + batch contract
    assert '@public_router.post("/sim-cdr")' in source
    assert "class SimCallEntry(BaseModel)" in source
    assert "calls: list[SimCallEntry]" in source
    # Auth by per-caller sync token
    assert 'request.headers.get("X-Sync-Token")' in source
    assert '.eq("sync_token", token)' in source
    # Dedup on (caller_id, call_sid) for sim_basic
    assert '.eq("call_sid", entry.entry_id)' in source
    assert '.eq("provider", "sim_basic")' in source
    # Provider tag + scoring reuse
    assert '"provider": "sim_basic"' in source
    assert "score_from_outcome(apply_outcome, entry.duration)" in source
    assert "recompute_caller_score(caller_id, db)" in source


def test_sim_cdr_enriches_pwa_row_not_duplicate():
    source = _read("app/routes/calls.py")
    # Reconcile against a pending PWA-created row instead of always inserting.
    assert '.is_("call_sid", "null")' in source
    assert '.in_("status", ["sim_started", "initiated"])' in source
    assert 'action = "enriched"' in source
    assert 'action = "created"' in source
    # Never clobber a human-tagged outcome from the wrap-up form.
    assert "not pending_outcome" in source


def test_sim_lead_numbers_endpoint_for_device_filter():
    source = _read("app/routes/calls.py")
    assert '@public_router.get("/sim-lead-numbers")' in source
    # Scoped to the caller's own assigned leads, tenant-isolated, non-deleted.
    assert '.eq("assigned_to", caller_id)' in source
    assert '.eq("tenant_id", tenant_id)' in source
    # Returns normalized numbers so the device can compare directly.
    assert "_normalize_sim_phone(r.get(\"phone\")" in source


def test_sim_status_mapping_contract():
    source = _read("app/routes/calls.py")
    assert "def _sim_status_from_type" in source
    # outgoing/incoming answered -> completed
    assert 'return "completed", "answered", None' in source
    # outgoing unanswered + missed -> no_answer
    assert 'return "no_answer", "no_answer", "no_answer"' in source


def test_sim_phone_normalization_strips_india_prefix():
    source = _read("app/routes/calls.py")
    assert "def _normalize_sim_phone" in source
    assert 're.sub(r"[^\\d]", "", phone or "")' in source
    assert 'digits.startswith("91")' in source


def test_sim_phone_normalization_matches_leads_phone_storage_format():
    """Regression test: leads.phone is stored as '+91XXXXXXXXXX' in this
    database (confirmed via live query 2026-07-02). _normalize_sim_phone must
    produce that exact format, or '.eq("phone", dialed)' lookups in
    _ingest_sim_call silently never match and every synced call creates a
    duplicate orphan lead instead of linking to the real one.
    """
    from app.routes.calls import _normalize_sim_phone

    # All these raw forms a phone dialer / Android call log might report for
    # the same number must normalize to the one format leads.phone uses.
    assert _normalize_sim_phone("+919345679286") == "+919345679286"
    assert _normalize_sim_phone("919345679286") == "+919345679286"
    assert _normalize_sim_phone("9345679286") == "+919345679286"
    assert _normalize_sim_phone("+91 93456 79286") == "+919345679286"
    assert _normalize_sim_phone("93456-79286") == "+919345679286"


def test_no_dead_secrets_import_in_calls():
    source = _read("app/routes/calls.py")
    # `secrets` is only used by the sync-token endpoint in callers.py, not here.
    assert "import secrets\n" not in source
