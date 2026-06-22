from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_whatsapp_webhook_requires_meta_signature_header():
    source = read("app/routes/webhook.py")
    assert "if not signature:" in source
    assert "missing signature" in source.lower()


def test_whatsapp_webhook_does_not_fallback_to_default_tenant_for_meta_messages():
    source = read("app/routes/webhook.py")
    messages_block = source[source.index('elif field == "messages"'):source.index('return {"status": "ok"}')]
    assert "using default" not in messages_block
    assert "DEFAULT_TENANT" not in messages_block


def test_upload_campaign_lookup_is_tenant_scoped():
    source = read("app/routes/upload.py")
    assert '.select("id").eq("phone", phone).eq("tenant_id", tenant_id).limit(1)' in source


def test_voice_router_requires_tenant_id():
    source = read("app/services/voice_router.py")
    assert "async def get_best_voice_number(tenant_id: str)" in source
    assert '.eq("tenant_id", tenant_id)' in source


def test_call_delete_is_tenant_scoped():
    source = read("app/routes/calls.py")
    assert 'async def delete_call_log(call_log_id: str, ctx: dict = Depends(get_tenant_and_role))' in source
    assert '.eq("tenant_id", ctx["tenant_id"])' in source


def test_telecmi_callbacks_require_shared_secret():
    source = read("app/routes/calls.py")
    assert "def _verify_telecmi_webhook_secret(request: Request, tenant_id: str | None = None) -> bool:" in source
    assert 'request.query_params.get("webhook_secret")' in source
    assert 'raise HTTPException(status_code=403, detail="Invalid webhook secret")' in source
    assert "@public_router.post(\"/telecmi-cdr\")" in source
    assert "@public_router.post(\"/telecmi-events\")" in source


def test_telecmi_webhook_secret_is_dynamic_setting():
    # Resolved per-tenant from app_settings (no hardcoded constant, no global env fallback).
    source = read("app/routes/calls.py")
    assert 'get_setting("telecmi_webhook_secret", tenant_id=tenant_id)' in source


def test_owner_only_gated_routers():
    for router_file in ["upload.py", "knowledge.py", "numbers.py"]:
        source = read(f"app/routes/{router_file}")
        assert "require_owner" in source
        assert "APIRouter(dependencies=[Depends(require_owner)])" in source

    settings_source = read("app/routes/app_settings.py")
    assert "Depends(require_owner)" in settings_source


def test_segments_ensure_templates_scopes_by_tenant():
    source = read("app/routes/segments.py")
    assert 'def _ensure_templates(db, tenant_id: str) -> list[dict]:' in source
    assert '.eq("tenant_id", tenant_id)' in source


def test_template_webhook_status_requires_signature():
    source = read("app/routes/templates.py")
    assert "verify_meta_signature" in source
    assert "verify_meta_signature(raw_body, signature, tenant_id)" in source

