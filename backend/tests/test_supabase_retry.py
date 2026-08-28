import httpx
import pytest

from app.db.supabase import _RetryTransport


class _ScriptedTransport(httpx.BaseTransport):
    """Raises the queued exceptions in order, then answers 200."""

    def __init__(self, failures):
        self.failures = list(failures)
        self.calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return httpx.Response(200, json={"ok": True}, request=request)


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr("app.db.supabase._BACKOFF_SECONDS", 0)


def _request(inner, method="GET"):
    client = httpx.Client(transport=_RetryTransport(inner), base_url="https://example.test")
    return client.request(method, "/rest/v1/leads")


def _disconnected():
    return httpx.RemoteProtocolError("Server disconnected")


def test_dropped_read_is_retried_and_succeeds():
    inner = _ScriptedTransport([_disconnected()])
    assert _request(inner).status_code == 200
    assert inner.calls == 2


def test_read_gives_up_after_max_attempts():
    inner = _ScriptedTransport([_disconnected(), _disconnected(), _disconnected()])
    with pytest.raises(httpx.RemoteProtocolError):
        _request(inner)
    assert inner.calls == 3


def test_write_is_never_replayed():
    inner = _ScriptedTransport([_disconnected()])
    with pytest.raises(httpx.RemoteProtocolError):
        _request(inner, method="POST")
    assert inner.calls == 1
