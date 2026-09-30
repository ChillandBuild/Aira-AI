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
