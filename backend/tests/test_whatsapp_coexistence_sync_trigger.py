from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_request_coexistence_sync_posts_both_sync_types():
    from app.services.meta_cloud import request_coexistence_sync

    posted = []

    class _Resp:
        def json(self):
            return {"messaging_product": "whatsapp", "request_id": "req-1"}

    class _Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, **kwargs):
            posted.append((url, kwargs["json"], kwargs["headers"]))
            return _Resp()

    with patch("app.services.meta_cloud.httpx.AsyncClient", return_value=_Client()):
        await request_coexistence_sync("phone-1", "token-1")

    assert len(posted) == 2
    urls = {p[0] for p in posted}
    assert urls == {"https://graph.facebook.com/v21.0/phone-1/smb_app_data"}
    sync_types = {p[1]["sync_type"] for p in posted}
    assert sync_types == {"smb_app_state_sync", "history"}
    for _url, body, headers in posted:
        assert body["messaging_product"] == "whatsapp"
        assert headers == {"Authorization": "Bearer token-1"}


@pytest.mark.asyncio
async def test_request_coexistence_sync_does_not_raise_on_http_error():
    from app.services.meta_cloud import request_coexistence_sync
    import httpx

    class _Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, **kwargs):
            raise httpx.ConnectTimeout("timed out")

    with patch("app.services.meta_cloud.httpx.AsyncClient", return_value=_Client()):
        await request_coexistence_sync("phone-1", "token-1")  # must not raise


@pytest.mark.asyncio
async def test_request_coexistence_sync_logs_error_response_without_raising():
    from app.services.meta_cloud import request_coexistence_sync

    class _Resp:
        def json(self):
            return {"error": {"message": "bad token"}}

    class _Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, **kwargs):
            return _Resp()

    with patch("app.services.meta_cloud.httpx.AsyncClient", return_value=_Client()):
        await request_coexistence_sync("phone-1", "token-1")  # must not raise
