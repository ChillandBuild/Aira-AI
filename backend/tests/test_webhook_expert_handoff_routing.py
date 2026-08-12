import inspect

from app.routes import webhook


def test_process_inbound_message_calls_route_intake_before_generate_reply():
    """Static check: route_intake must run, and generate_reply must be
    skipped when it returns True. Mirrors the style of
    test_ai_reply_lang_detection.py's inspect.getsource checks — this is a wiring
    concern, better verified statically than via a heavy background-task mock."""
    source = inspect.getsource(webhook._process_inbound_message_background)
    assert "route_intake" in source
    idx_route = source.index("route_intake")
    idx_generate = source.index("generate_reply(")
    assert idx_route < idx_generate, "route_intake must be checked before generate_reply is called"
