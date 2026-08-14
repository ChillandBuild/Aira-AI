# backend/tests/test_templates.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


# ── Bug 1: WABA ID ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_template_uses_waba_id_not_phone_number_id():
    """create_template must read meta_waba_id, not meta_phone_number_id."""
    from app.routes.templates import create_template, CreateTemplate

    payload = CreateTemplate(name="test_template", category="UTILITY", language="en", body_text="Hello {{1}}, welcome!")

    captured_waba_id = []

    async def mock_submit(*args, **kwargs):
        waba_id = kwargs.get("waba_id") or (args[0] if args else None)
        captured_waba_id.append(waba_id)
        return {"id": "meta-123"}

    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    mock_db.table.return_value.insert.return_value.execute.return_value.data = [{
        "id": "row-1", "name": "test_template", "category": "UTILITY",
        "language": "en", "body_text": "Hello {{1}}, welcome!", "status": "PENDING",
        "meta_template_id": "meta-123", "tenant_id": "tenant-1",
        "submitted_at": "2026-05-13T00:00:00Z", "approved_at": None, "rejection_reason": None,
    }]

    with patch("app.routes.templates.get_setting", side_effect=lambda k, **kwargs: "waba-999" if k == "meta_waba_id" else None), \
         patch("app.routes.templates.get_supabase", return_value=mock_db), \
         patch("app.routes.templates.submit_template", side_effect=mock_submit):

        result = await create_template(payload, tenant_id="tenant-1")

    assert captured_waba_id == ["waba-999"], f"Expected waba-999, got {captured_waba_id}"


# ── Bug 2: public_router ──────────────────────────────────────────────────────

def test_webhook_status_is_on_public_router():
    """webhook-status must be on public_router, not the auth-gated router."""
    from app.routes import templates

    public_paths = [r.path for r in templates.public_router.routes]
    auth_paths = [r.path for r in templates.router.routes]

    assert "/webhook-status" in public_paths, \
        f"webhook-status not found in public_router paths: {public_paths}"
    assert "/webhook-status" not in auth_paths, \
        f"webhook-status must NOT be in auth-gated router: {auth_paths}"


def test_waba_filter_hides_legacy_remote_templates():
    """Rows from an old unknown WABA must not remain visible after account switch."""
    from app.routes.templates import _filter_templates_for_waba

    rows = [
        {"name": "old_remote", "status": "APPROVED", "meta_template_id": "old-meta", "meta_waba_id": None},
        {"name": "old_remote_without_id", "status": "APPROVED", "meta_template_id": None, "meta_waba_id": None},
        {"name": "current_remote", "status": "APPROVED", "meta_template_id": "new-meta", "meta_waba_id": "waba-new"},
        {"name": "local_draft", "status": "PENDING", "meta_template_id": None, "meta_waba_id": None},
    ]

    visible = _filter_templates_for_waba(rows, "waba-new")

    assert [r["name"] for r in visible] == ["current_remote", "local_draft"]


def test_waba_filter_hides_everything_when_no_waba_configured():
    """A tenant with no WhatsApp connection has no templates to show — fail closed."""
    from app.routes.templates import _filter_templates_for_waba

    rows = [
        {"name": "old_remote", "meta_template_id": "old-meta", "meta_waba_id": None},
        {"name": "other_account", "meta_template_id": "other-meta", "meta_waba_id": "waba-other"},
    ]

    assert _filter_templates_for_waba(rows, None) == []


def test_belongs_to_current_waba_still_answers_ownership_without_a_waba():
    """Visibility fails closed, but the ownership check must not — it guards duplicate names."""
    from app.routes.templates import _belongs_to_current_waba

    assert _belongs_to_current_waba({"name": "x", "meta_template_id": "m", "meta_waba_id": "w"}, None) is True


@pytest.mark.asyncio
async def test_create_template_rejected_when_no_waba_connected():
    """Saving locally would strand a template that never reaches Meta and never renders."""
    from app.routes.templates import create_template, CreateTemplate
    from fastapi import HTTPException

    payload = CreateTemplate(name="orphan", category="UTILITY", language="en", body_text="Hi {{1}}, welcome!")

    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

    with patch("app.routes.templates.get_setting", return_value=None), \
         patch("app.routes.templates.get_supabase", return_value=mock_db):

        with pytest.raises(HTTPException) as exc:
            await create_template(payload, tenant_id="tenant-1")

    assert exc.value.status_code == 400
    assert "meta_waba_id" in exc.value.detail
    mock_db.table.return_value.insert.assert_not_called()


# ── Lifecycle timestamps ──────────────────────────────────────────────────────

def test_clean_rejection_reason_drops_metas_none_sentinel():
    """Meta sends the literal string 'NONE' when a template was never rejected."""
    from app.routes.templates import _clean_rejection_reason

    assert _clean_rejection_reason("NONE") is None
    assert _clean_rejection_reason("none") is None
    assert _clean_rejection_reason("") is None
    assert _clean_rejection_reason(None) is None
    assert _clean_rejection_reason("INVALID_FORMAT") == "INVALID_FORMAT"


@pytest.mark.asyncio
async def test_create_template_resets_lifecycle_on_stale_row_reuse():
    """Re-submitting a name whose row belongs to an old WABA must clear the old approval."""
    from app.routes.templates import create_template, CreateTemplate

    payload = CreateTemplate(
        name="escalation_alert", category="UTILITY", language="en", body_text="Lead {{1}} needs an agent"
    )

    captured: dict = {}

    mock_db = MagicMock()
    # Stale row: same name, bound to a previous WABA, carrying an old approval.
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "row-old", "meta_template_id": "old-meta", "meta_waba_id": "waba-old"}
    ]

    def capture_update(values):
        captured.update(values)
        chain = MagicMock()
        chain.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "row-old"}]
        return chain

    mock_db.table.return_value.update.side_effect = capture_update

    async def mock_submit(*args, **kwargs):
        return {"id": "new-meta"}

    with patch("app.routes.templates.get_setting", side_effect=lambda k, **kwargs: "waba-new" if k == "meta_waba_id" else None), \
         patch("app.routes.templates.get_supabase", return_value=mock_db), \
         patch("app.routes.templates.submit_template", side_effect=mock_submit):

        await create_template(payload, tenant_id="tenant-1")

    assert captured["approved_at"] is None, "stale approval date must be cleared on resubmit"
    assert captured["rejection_reason"] is None, "stale rejection reason must be cleared on resubmit"
    assert captured.get("submitted_at"), "submitted_at must be refreshed on resubmit"


@pytest.mark.asyncio
async def test_sync_status_clears_approval_when_meta_says_pending():
    """A PENDING template must not keep an approved_at from a previous life."""
    from app.routes.templates import sync_template_status

    captured: dict = {}

    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"name": "escalation_alert", "meta_template_id": "meta-1", "meta_waba_id": "waba-new", "approved_at": "2026-08-05T16:48:07Z"}
    ]

    def capture_update(values):
        captured.update(values)
        chain = MagicMock()
        chain.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "row-1"}]
        return chain

    mock_db.table.return_value.update.side_effect = capture_update

    async def mock_status(*args, **kwargs):
        return {"status": "PENDING", "id": "meta-1", "rejected_reason": "NONE"}

    with patch("app.routes.templates.get_setting", side_effect=lambda k, **kwargs: "waba-new" if k == "meta_waba_id" else None), \
         patch("app.routes.templates.get_supabase", return_value=mock_db), \
         patch("app.routes.templates.get_template_status", side_effect=mock_status):

        await sync_template_status("row-1", tenant_id="tenant-1")

    assert captured["approved_at"] is None
    assert captured["rejection_reason"] is None


@pytest.mark.asyncio
async def test_sync_status_preserves_original_approval_date():
    """Re-syncing an approved template must not bump approved_at to today."""
    from app.routes.templates import sync_template_status

    captured: dict = {}

    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"name": "hot_lead_check", "meta_template_id": "meta-2", "meta_waba_id": "waba-new", "approved_at": "2026-07-21T14:06:20Z"}
    ]

    def capture_update(values):
        captured.update(values)
        chain = MagicMock()
        chain.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "row-2"}]
        return chain

    mock_db.table.return_value.update.side_effect = capture_update

    async def mock_status(*args, **kwargs):
        return {"status": "APPROVED", "id": "meta-2", "rejected_reason": "NONE"}

    with patch("app.routes.templates.get_setting", side_effect=lambda k, **kwargs: "waba-new" if k == "meta_waba_id" else None), \
         patch("app.routes.templates.get_supabase", return_value=mock_db), \
         patch("app.routes.templates.get_template_status", side_effect=mock_status):

        await sync_template_status("row-2", tenant_id="tenant-1")

    assert "approved_at" not in captured, "an existing approval date must be left untouched"


# ── get_template_status ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_template_status_returns_status():
    """get_template_status fetches template status from Meta API."""
    from app.services.meta_cloud import get_template_status

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {
        "data": [{"name": "my_template", "status": "APPROVED", "id": "meta-123"}]
    }

    with patch("httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)

        with patch("app.services.meta_cloud.get_setting", return_value="test_token"):
            result = await get_template_status(
                waba_id="1190331789463566",
                template_name="my_template",
            )

    assert result is not None
    assert result["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_get_template_status_returns_none_when_not_found():
    """get_template_status returns None when Meta has no matching template."""
    from app.services.meta_cloud import get_template_status

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"data": []}

    with patch("httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)

        with patch("app.services.meta_cloud.get_setting", return_value="test_token"):
            result = await get_template_status(
                waba_id="1190331789463566",
                template_name="nonexistent_template",
            )

    assert result is None
