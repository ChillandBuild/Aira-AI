from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_sim_manual_status_migration_contract():
    source = _read("supabase/migrations/121_sim_manual_call_statuses.sql")
    for status in [
        "connected",
        "not_picked",
        "busy",
        "wrong_number",
        "interested",
        "not_interested",
        "callback",
    ]:
        assert f"'{status}'" in source
    assert "add column if not exists manual_status text" in source
    assert "'interested'" in source
    assert "'sim_started'" in source


def test_calls_route_maps_all_manual_statuses():
    source = _read("app/routes/calls.py")
    assert "ManualStatus = Literal" in source
    assert "_MANUAL_STATUS_TO_DISPOSITION" in source
    assert "_MANUAL_STATUS_TO_OUTCOME" in source
    assert '"wrong_number": None' in source
    assert 'dnc_outcome = "wrong_number"' in source
    assert 'lead_updates["do_not_call"] = True' in source
    assert 'effective_outcome == "interested"' in source


def test_push_missing_keys_are_graceful_in_frontend():
    frontend = ROOT.parent / "frontend"
    cockpit = (frontend / "app/dashboard/telecalling/lib/useCallingCockpit.ts").read_text(encoding="utf-8")
    bell = (frontend / "components/NotificationBell.tsx").read_text(encoding="utf-8")
    assert "Mobile push is not configured yet" in cockpit
    assert "Use the QR code or copy the number" in cockpit
    assert "In-app notifications still work" in bell
