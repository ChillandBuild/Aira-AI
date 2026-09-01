"""httpx must not log request URLs.

Meta's Graph API takes credentials as query parameters, so httpx's INFO-level
"HTTP Request: GET <full url>" line wrote the Meta app secret (inside the
`{app_id}|{secret}` app access token) and every Page access token into Render's
logs in plaintext. Observed in production logs on 2026-08-30 12:21.
"""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_main_mutes_httpx_request_logging():
    assert 'logging.getLogger("httpx").setLevel(logging.WARNING)' in _read("app/main.py")


def test_mute_is_applied_after_basicconfig():
    """basicConfig configures the root logger; the mute must not be overwritten."""
    source = _read("app/main.py")
    assert source.index("logging.basicConfig(") < source.index('logging.getLogger("httpx")')


def test_httpx_logger_is_quiet_at_info_once_main_is_imported():
    import app.main  # noqa: F401  — importing applies the configuration

    httpx_logger = logging.getLogger("httpx")
    assert not httpx_logger.isEnabledFor(logging.INFO)
    # Real failures must still surface.
    assert httpx_logger.isEnabledFor(logging.WARNING)
