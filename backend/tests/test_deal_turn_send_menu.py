"""deal_turn.send_menu: the AI's reply with tappable options, sent over WhatsApp.

Regression: 7400cf7f deleted send_menu while ai_reply.py still called it, so every AI
reply carrying a menu died with AttributeError and the customer got silence.
"""
import ast
import asyncio
import importlib
from pathlib import Path

from app.services import choices, deal_turn, meta_cloud

APP_DIR = Path(__file__).resolve().parent.parent / "app"


def _run(coro):
    return asyncio.run(coro)


def test_button_menu_goes_out_as_interactive_buttons(monkeypatch):
    sent = {}

    async def fake_buttons(**kwargs):
        sent.update(kwargs)
        return {"messages": [{"id": "wamid.buttons"}]}

    monkeypatch.setattr(meta_cloud, "send_interactive_buttons", fake_buttons)
    menu = choices.build_menu(["Yes", "No"])

    sid, tappable = _run(deal_turn.send_menu("+91000", "Shall we book?", menu, tenant_id="t-1", phone_number_id="pn-1"))

    assert sid == "wamid.buttons" and tappable
    assert sent["body_text"] == "Shall we book?"
    assert [b["title"] for b in sent["buttons"]] == ["Yes", "No"]
    assert sent["tenant_id"] == "t-1" and sent["phone_number_id"] == "pn-1"


def test_long_menu_goes_out_as_a_list(monkeypatch):
    sent = {}

    async def fake_list(**kwargs):
        sent.update(kwargs)
        return {"messages": [{"id": "wamid.list"}]}

    monkeypatch.setattr(meta_cloud, "send_list_message", fake_list)
    menu = choices.build_menu(["One", "Two", "Three", "Four"])

    sid, tappable = _run(deal_turn.send_menu("+91000", "Pick one", menu, tenant_id="t-1"))

    assert sid == "wamid.list" and tappable
    assert sent["button_text"] == menu["button_text"]
    assert sent["sections"] == menu["sections"]


def test_interactive_failure_falls_back_to_plain_text_with_options(monkeypatch):
    from app.services import ai_reply

    async def broken_buttons(**kwargs):
        raise RuntimeError("Meta rejected the interactive message")

    sent = {}

    async def fake_send_whatsapp(phone, text, **kwargs):
        sent.update(phone=phone, text=text, **kwargs)
        return "wamid.text"

    monkeypatch.setattr(meta_cloud, "send_interactive_buttons", broken_buttons)
    monkeypatch.setattr(ai_reply, "send_whatsapp", fake_send_whatsapp)
    menu = choices.build_menu(["Yes", "No"])

    sid, tappable = _run(deal_turn.send_menu("+91000", "Shall we book?", menu, tenant_id="t-1"))

    assert sid == "wamid.text" and not tappable
    assert sent["text"].startswith("Shall we book?")
    assert "Yes" in sent["text"] and "No" in sent["text"]


def test_body_over_whatsapp_limit_is_sent_first_then_the_buttons(monkeypatch):
    from app.services import ai_reply

    bodies, texts = [], []

    async def fake_buttons(**kwargs):
        bodies.append(kwargs["body_text"])
        return {"messages": [{"id": "wamid.buttons"}]}

    async def fake_send_whatsapp(phone, text, **kwargs):
        texts.append(text)
        return "wamid.text"

    monkeypatch.setattr(meta_cloud, "send_interactive_buttons", fake_buttons)
    monkeypatch.setattr(ai_reply, "send_whatsapp", fake_send_whatsapp)
    long_body = "x" * (deal_turn.INTERACTIVE_BODY_MAX + 1)

    sid, tappable = _run(deal_turn.send_menu("+91000", long_body, choices.build_menu(["Yes", "No"]), tenant_id="t-1"))

    assert (sid, tappable) == ("wamid.buttons", True)
    assert texts == [long_body] and bodies == [deal_turn.CHOICE_BODY_FALLBACK]


def test_saved_record_matches_what_was_sent():
    """[tags] mean buttons went out; a fallback is saved as the typed list the customer saw."""
    menu = choices.build_menu(["Yes", "No"])
    assert deal_turn.menu_record("Pick", menu, tappable=True) == "Pick\n\n[Yes]  [No]"
    assert deal_turn.menu_record("Pick", menu, tappable=False) == "Pick\n\n• Yes\n• No"


def test_every_lazily_imported_service_attribute_exists():
    """`from app.services import x` inside a function escapes import-time checks, so a
    deleted x.y only fails when a customer reaches that line. Resolve every x.y now."""
    missing = []
    for path in APP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "app.services"
            for alias in node.names
        }
        # Parsed code only: comments and docstrings that name a module never count.
        used = {
            (node.value.id, node.attr)
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in modules
        }
        for name, attr in used:
            try:
                module = importlib.import_module(f"app.services.{name}")
            except ImportError:
                continue  # not a module (a function imported from the package) or optional
            if not hasattr(module, attr):
                missing.append(f"{path.relative_to(APP_DIR.parent)}: {name}.{attr}")
    assert not missing, "References to attributes that do not exist:\n" + "\n".join(sorted(missing))
