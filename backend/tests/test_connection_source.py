from unittest.mock import MagicMock, patch

import pytest


def _upserted(db):
    """Every row app_settings upserted during the call, keyed by setting key."""
    rows = [call.args[0] for call in db.table.return_value.upsert.call_args_list]
    return {row["key"]: row for row in rows if "key" in row}


@pytest.mark.asyncio
async def test_manual_credential_save_marks_only_the_touched_channel_as_manual():
    """Breaks if a manual token save silently keeps an 'embedded' badge on the card."""
    from app.routes.app_settings import SettingsUpdate, update_settings

    db = MagicMock()
    db.table.return_value.upsert.return_value.execute.return_value.data = [{"key": "x"}]

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings.record_audit_event"):
        await update_settings(
            SettingsUpdate(updates={"instagram_access_token": "IGQV-token"}),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    rows = _upserted(db)
    assert rows["instagram_connection_source"]["value"] == "manual"
    assert rows["instagram_connection_source"]["is_secret"] is False
    assert "whatsapp_connection_source" not in rows
    assert "facebook_connection_source" not in rows
    assert "meta_ads_connection_source" not in rows


@pytest.mark.asyncio
async def test_manual_credential_save_still_resets_channel_status_to_configured():
    """Breaks if folding the status reset into the shared channel map loses the reset."""
    from app.routes.app_settings import SettingsUpdate, update_settings

    db = MagicMock()
    db.table.return_value.upsert.return_value.execute.return_value.data = [{"key": "x"}]

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings.record_audit_event"):
        await update_settings(
            SettingsUpdate(updates={"meta_access_token": "EAAG-token"}),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    rows = _upserted(db)
    assert rows["whatsapp_status"]["value"] == "configured"
    assert rows["whatsapp_connection_source"]["value"] == "manual"


@pytest.mark.asyncio
async def test_non_channel_settings_never_stamp_a_connection_source():
    """Breaks if unrelated settings writes pollute the channel source markers."""
    from app.routes.app_settings import SettingsUpdate, update_settings

    db = MagicMock()
    db.table.return_value.upsert.return_value.execute.return_value.data = [{"key": "x"}]

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings.record_audit_event"):
        await update_settings(
            SettingsUpdate(updates={"groq_api_key": "gsk-token"}),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    assert not [key for key in _upserted(db) if key.endswith("_connection_source")]
