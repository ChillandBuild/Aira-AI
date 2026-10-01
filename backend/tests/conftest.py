"""Shared fixtures. Nothing here changes what a test sees except state that would otherwise
leak between tests."""
import pytest


@pytest.fixture(autouse=True)
def _clear_brain_headline_cache():
    """The Aira Brain headline is cached per tenant for a minute in-process; tests reuse the
    same tenant ids with different data, so each test starts and ends with an empty cache."""
    from app.services.brain import headline

    headline.clear_cache()
    yield
    headline.clear_cache()


@pytest.fixture(autouse=True)
def _no_live_astro_settings(monkeypatch):
    """"Is this tenant connected to AstroTamil?" is a settings read, which would reach the real
    database from any test that runs the deal flow. Default every test to "not connected"; a test
    about the connection patches astro_bridge.get_setting itself, after this runs."""
    from app.services import astro_bridge

    monkeypatch.setattr(astro_bridge, "get_setting", lambda key, fallback=None, tenant_id=None: fallback)
