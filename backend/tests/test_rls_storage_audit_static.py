from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent


def read_project(path: str) -> str:
    return (PROJECT_ROOT / path).read_text()


def read_backend(path: str) -> str:
    return (ROOT / path).read_text()


def test_security_migration_uses_current_sequence_and_core_objects():
    migration = read_backend("supabase/migrations/089_security_hardening.sql")
    assert "create table if not exists public.app_audit_logs" in migration.lower()
    assert "alter table if exists public.leads enable row level security" in migration.lower()
    assert "public.is_tenant_member" in migration
    assert "public.is_tenant_owner" in migration
    assert "public.is_system_admin" in migration


def test_security_migration_covers_current_tables_and_private_csv_storage():
    migration = read_backend("supabase/migrations/089_security_hardening.sql").lower()
    for table in (
        "automation_flow_runs",
        "broadcast_tags",
        "lead_tag_interest",
        "broadcast_lead_scores",
        "lead_tag_opt_outs",
        "knowledge_chunks",
    ):
        assert f"alter table if exists public.{table} enable row level security" in migration
    assert "set public = false" in migration
    assert "where id = 'broadcast-csvs'" in migration
    assert 'drop policy if exists "allow public read access to csvs"' in migration


def test_operator_and_settings_write_audit_events():
    operator_source = read_backend("app/routes/operator.py")
    settings_source = read_backend("app/routes/app_settings.py")
    assert "record_audit_event" in operator_source
    assert "operator.client_created" in operator_source
    # Lead-wipe used to log its own "operator.leads_wiped" action via a
    # dedicated /wipe-leads endpoint; that endpoint was merged into the
    # generic /clients/{id}/clear/{data_type} endpoint, which audits every
    # data type (including leads) under this one prefix instead.
    assert "operator.data_cleared:" in operator_source
    assert "operator.password_reset" in operator_source
    assert "record_audit_event" in settings_source
    assert "settings.updated" in settings_source
    assert "settings.channel_activated" in settings_source


def test_upload_uses_signed_csv_path_contract():
    upload_source = read_backend("app/routes/upload.py")
    assert "csv_file_path" in upload_source
    assert '@router.get("/csv-signed-url")' in upload_source
    assert "create_signed_url" in upload_source
    assert "path.startswith(f\"{tenant_id}/\")" in upload_source


def test_frontend_uses_signed_csv_endpoint_for_history_links():
    page_source = read_project("frontend/app/dashboard/outbound-leads/page.tsx")
    assert "csv_file_path" in page_source
    assert "openBroadcastCsv" in page_source
    assert "/api/v1/upload/csv-signed-url" in page_source


def test_security_new_tables_rls_migration():
    migration = read_backend("supabase/migrations/113_security_and_new_tables_rls.sql").lower()
    for table in (
        "reengagement_steps",
        "reengagement_logs",
        "autopilot_runs",
        "call_scripts",
        "telecalling_upload_batches",
    ):
        assert f"alter table if exists public.{table} enable row level security" in migration
