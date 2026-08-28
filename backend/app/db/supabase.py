import logging
import time

import httpx
from supabase import create_client, Client
from app.config import settings

logger = logging.getLogger(__name__)

_client: Client | None = None

# PostgREST's session is HTTP/2 (postgrest sets http2=True), so every query in
# the process shares one connection to Supabase's edge. When that edge recycles
# the connection, whichever request is holding it dies with
# `RemoteProtocolError: Server disconnected`. postgrest's own send_with_retry
# only covers HTTP 520/503 and httpx `NetworkError` — `RemoteProtocolError` is a
# `ProtocolError`, so it escapes and surfaces as a 500 (seen on
# GET /api/v1/subscriptions/me, 2026-08-28). Retrying here fixes every call site
# at once, since nothing in the app talks to postgrest directly.
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = 0.25
_TRANSIENT = (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError)
# Only replay what is safe to replay. A dropped POST/PATCH/DELETE may already
# have been applied server-side, so those keep raising.
_REPLAYABLE = frozenset({"GET", "HEAD", "OPTIONS"})


class _RetryTransport(httpx.BaseTransport):
    """Replays idempotent PostgREST requests when the pooled connection dies."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                return self._inner.handle_request(request)
            except _TRANSIENT as exc:
                if request.method not in _REPLAYABLE:
                    raise
                last_exc = exc
                if attempt + 1 < _MAX_ATTEMPTS:
                    logger.warning(
                        "Supabase %s %s dropped (%s) — retrying %d/%d",
                        request.method,
                        request.url.path,
                        type(exc).__name__,
                        attempt + 1,
                        _MAX_ATTEMPTS - 1,
                    )
                    time.sleep(_BACKOFF_SECONDS * (2 ** attempt))
        raise last_exc  # type: ignore[misc]

    def close(self) -> None:
        self._inner.close()


def _wrap_postgrest_session(client: Client) -> None:
    """Swap PostgREST's session for one whose transport retries dropped reads.

    Rebuilds the session rather than passing ClientOptions(httpx_client=...):
    that option hands the *same* httpx client to postgrest, storage and
    functions, and each one assigns its own `base_url` onto it — last writer
    wins, and the other two then talk to the wrong host.
    """
    old = client.postgrest.session
    client.postgrest.session = httpx.Client(
        base_url=old.base_url,
        headers=old.headers,
        timeout=old.timeout,
        follow_redirects=True,
        transport=_RetryTransport(httpx.HTTPTransport(http2=True)),
    )
    old.close()


def get_supabase() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_key)
        _wrap_postgrest_session(_client)
    return _client
