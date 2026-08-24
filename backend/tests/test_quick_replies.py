import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.quick_replies import (
    QUICK_REPLY_TOOL_NAME,
    build_quick_reply_tool,
    format_block_log,
    last_outbound_was_block,
    load_active_blocks,
    resolve_block,
    should_offer_quick_replies,
    to_send_buttons,
)


def _block(name="Menu options", use_when="lead asks about food", body="What would you like?"):
    return {
        "id": "b1",
        "name": name,
        "use_when": use_when,
        "body_text": body,
        "buttons": [{"id": "menu", "label": "Menu card"}, {"id": "book", "label": "Book table"}],
        "is_active": True,
    }


# --- build_quick_reply_tool ---

def test_tool_is_empty_without_blocks():
    assert build_quick_reply_tool([]) == []


def test_tool_lists_names_as_enum():
    tools = build_quick_reply_tool([_block(), _block(name="Location", use_when="asks address")])
    fn = tools[0]["function"]
    assert fn["name"] == QUICK_REPLY_TOOL_NAME
    assert fn["parameters"]["properties"]["block_name"]["enum"] == ["Menu options", "Location"]


def test_tool_description_carries_use_when():
    tools = build_quick_reply_tool([_block()])
    assert "lead asks about food" in tools[0]["function"]["description"]
    assert "Menu options" in tools[0]["function"]["description"]


# --- resolve_block ---

def test_resolve_block_is_case_insensitive():
    blocks = [_block()]
    assert resolve_block(blocks, "menu OPTIONS")["name"] == "Menu options"


def test_resolve_block_returns_none_for_hallucinated_name():
    assert resolve_block([_block()], "Nonexistent") is None


def test_resolve_block_returns_none_for_empty_name():
    assert resolve_block([_block()], None) is None
    assert resolve_block([_block()], "") is None


# --- to_send_buttons ---

def test_to_send_buttons_maps_label_to_title():
    assert to_send_buttons(_block()) == [
        {"id": "menu", "title": "Menu card"},
        {"id": "book", "title": "Book table"},
    ]


# --- format_block_log ---

def test_format_block_log_appends_labels():
    assert format_block_log(_block()) == "What would you like?\n\n[Menu card] [Book table]"


# --- last_outbound_was_block ---

def test_last_outbound_was_block_true_when_body_matches():
    thread = [
        {"direction": "outbound", "content": "What would you like?\n\n[Menu card] [Book table]"},
        {"direction": "inbound", "content": "hi"},
    ]
    assert last_outbound_was_block([_block()], thread) is True


def test_last_outbound_was_block_false_for_ordinary_reply():
    thread = [
        {"direction": "outbound", "content": "Sure, we open at 9am."},
        {"direction": "inbound", "content": "what time"},
    ]
    assert last_outbound_was_block([_block()], thread) is False


def test_last_outbound_was_block_ignores_inbound_messages():
    # The lead echoing the body text back must not suppress the block.
    thread = [
        {"direction": "inbound", "content": "What would you like?"},
        {"direction": "outbound", "content": "Sure, we open at 9am."},
    ]
    assert last_outbound_was_block([_block()], thread) is False


def test_last_outbound_was_block_false_on_empty_thread():
    assert last_outbound_was_block([_block()], []) is False


# --- should_offer_quick_replies ---

def test_offer_true_on_whatsapp_with_blocks():
    assert should_offer_quick_replies("whatsapp", False, [_block()], []) is True


def test_offer_false_when_intake_active():
    assert should_offer_quick_replies("whatsapp", True, [_block()], []) is False


def test_offer_false_on_other_channels():
    for ch in ("instagram", "telegram", "facebook"):
        assert should_offer_quick_replies(ch, False, [_block()], []) is False


def test_offer_false_without_blocks():
    assert should_offer_quick_replies("whatsapp", False, [], []) is False


def test_offer_false_when_block_was_just_sent():
    thread = [{"direction": "outbound", "content": "What would you like?\n\n[Menu card] [Book table]"}]
    assert should_offer_quick_replies("whatsapp", False, [_block()], thread) is False


# --- load_active_blocks ---

def test_load_active_blocks_returns_rows():
    db = MagicMock()
    chain = db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value
    chain.execute.return_value = MagicMock(data=[_block()])
    assert load_active_blocks(db, "t1")[0]["name"] == "Menu options"


def test_load_active_blocks_returns_empty_on_db_error():
    db = MagicMock()
    db.table.side_effect = RuntimeError("db down")
    assert load_active_blocks(db, "t1") == []


def test_ai_reply_wires_quick_replies_into_the_shared_tool_list():
    """Guard against the block tool being sent in a second, separate LLM call, and
    against the early-return that would skip scoring (see the plan's spec correction)."""
    source = (Path(__file__).resolve().parents[1] / "app" / "services" / "ai_reply.py").read_text(
        encoding="utf-8"
    )
    assert "should_offer_quick_replies" in source
    assert "quick_reply_tool" in source
    # One merged tool list, one LLM call.
    assert "catalog_tools + quick_reply_tool" in source
    # The block overrides the reply rather than returning early.
    assert 'reply_source = "quick_reply_block"' in source


def test_generate_reply_binds_fallthrough_vars_outside_the_try():
    """The LLM try/except does not return -- it falls through to the channel
    dispatch, which reads chosen_block and catalog_images_to_send. Binding either
    only inside the try turns any LLM failure into a NameError and a lost reply.
    """
    source = (Path(__file__).resolve().parents[1] / "app" / "services" / "ai_reply.py").read_text(
        encoding="utf-8"
    )
    init_block = source.index("chosen_block: dict | None = None")
    init_images = source.index("catalog_images_to_send: list[tuple[str, bytes]] = []")
    # The try that wraps build_reply_system_prompt + the LLM call.
    llm_try = source.index("system_prompt, reply_language_mode, intake_active = build_reply_system_prompt")
    assert init_block < llm_try, "chosen_block must be bound before the LLM try block"
    assert init_images < llm_try, "catalog_images_to_send must be bound before the LLM try block"
