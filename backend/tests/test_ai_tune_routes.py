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
