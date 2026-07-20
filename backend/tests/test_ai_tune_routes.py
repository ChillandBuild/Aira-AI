from unittest.mock import patch

from app.routes import ai_tune


def test_removed_endpoints_are_gone():
    """The analyze/suggestions endpoints were unreachable dead code -- no frontend
    caller existed. Assert they are not re-added."""
    paths = {route.path for route in ai_tune.router.routes}
    assert "/analyze" not in paths
    assert "/suggestions" not in paths
    assert not any("suggestions" in p for p in paths)
    assert not hasattr(ai_tune, "META_PROMPT")


def test_description_endpoints_exist():
    paths = {route.path for route in ai_tune.router.routes}
    assert "/description" in paths


def test_rubric_prompt_is_built_from_the_description():
    """The rubric captures THIS business's conversion signals, which now live in the
    client's description, not in the developer's generic master prompt."""
    built = ai_tune._rubric_prompt("We are a Vedic astrology consultancy.")
    assert "We are a Vedic astrology consultancy." in built
    assert "9-10" in built


def test_rubric_auto_update_defaults_to_off():
    """Off by default so saving a description never silently overwrites a hand-tuned
    rubric. A tenant that has never touched the setting must not regenerate."""
    with patch.object(ai_tune, "get_setting", return_value=None):
        assert ai_tune._rubric_auto_update_enabled("tenant-1") is False


def test_rubric_auto_update_reads_the_setting():
    with patch.object(ai_tune, "get_setting", return_value="true") as mock_get:
        assert ai_tune._rubric_auto_update_enabled("tenant-1") is True
    mock_get.assert_called_once_with("rubric_auto_update", fallback="false", tenant_id="tenant-1")

    with patch.object(ai_tune, "get_setting", return_value="false"):
        assert ai_tune._rubric_auto_update_enabled("tenant-1") is False
