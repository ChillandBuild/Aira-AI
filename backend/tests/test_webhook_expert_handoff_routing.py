import inspect

from app.routes import webhook


def test_inbound_text_goes_straight_to_generate_reply_with_the_tapped_option():
    """Static check of the AI-native wiring: the fixed intake state machine no longer
    intercepts inbound turns, and the WhatsApp button/list row id the lead tapped is
    handed to generate_reply so the model can tell which option was chosen. A wiring
    concern, better verified statically than via a heavy background-task mock."""
    source = inspect.getsource(webhook._process_inbound_message_background)
    assert "route_intake(" not in source, "route_intake must not intercept turns before the AI"
    assert "interactive_id=interactive_id" in source
    assert "generate_reply(" in source
