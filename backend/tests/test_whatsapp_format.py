"""The model writes Markdown; WhatsApp has its own, smaller syntax. Live 2026-09-30: "**One
Question (₹1):**" arrived as "*One Question (₹1):*" with the inner stars showing."""
from app.services.whatsapp_format import to_whatsapp


def test_live_reply_bold_and_bullets():
    text = ("Enga kitta irukura options idho:\n\n"
            "* **One Question (₹1):** Simple-ana kelvi-ku accurate-ana prediction.\n"
            "* **Detailed Question (₹99):** Unga life situation-ah pathi detailed-ana prediction.")
    assert to_whatsapp(text) == (
        "Enga kitta irukura options idho:\n\n"
        "• *One Question (₹1):* Simple-ana kelvi-ku accurate-ana prediction.\n"
        "• *Detailed Question (₹99):* Unga life situation-ah pathi detailed-ana prediction.")


def test_dash_bullets_and_indented_bullets():
    assert to_whatsapp("- One\n  - Two") == "• One\n  • Two"


def test_headings_become_bold():
    assert to_whatsapp("### Our plans\nPick one") == "*Our plans*\nPick one"


def test_underscore_bold_and_strikethrough():
    assert to_whatsapp("__Note__ ~~₹149~~ ₹99") == "_Note_ ~₹149~ ₹99"


def test_whatsapp_formatting_is_left_alone():
    text = "*One Question* _today_ ~old~ • already a bullet\n2 * 3 = 6"
    assert to_whatsapp(text) == text


def test_bold_spanning_lines_is_not_joined():
    assert to_whatsapp("**a\nb**") == "**a\nb**"


def test_empty():
    assert to_whatsapp("") == ""
