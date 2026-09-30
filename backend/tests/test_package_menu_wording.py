"""A reply that lays out the packages for the customer to pick gets them as buttons, whatever
words the model closes with. Live miss 2026-09-30: "Edhula book panna virumburinga?" named both
packages with prices but went out as plain text, because "Edhula" was not a known "which" word."""
import pytest

from app.services import deal_actions, deal_turn

# The live Astro Tamil catalog on 2026-09-30.
CONFIG = {"enabled": True, "fields": [], "packages": [
    {"key": "one_question", "name": "One Question", "amount_paise": 100, "button_label": "1 Rs"},
    {"key": "detailed_question", "name": "Detailed Question", "amount_paise": 9900, "button_label": "99Rs"},
    {"key": "marriage_compatability", "name": "Marriage Compatability", "amount_paise": 9900,
     "button_label": "Marriage 99Rs"},
]}
MENU = ["1 Rs", "99Rs", "Marriage 99Rs"]

GETS_BUTTONS = {
    "live_edhula": (
        "Job eppo kidaikum-nu therinjuka, neenga oru consultation book panni jothidar kitta analysis "
        "ketkalam. 😊\n\nEnga kitta irukura options idho:\n\n"
        "* **One Question (₹1):** Simple-ana kelvi-ku accurate-ana prediction.\n"
        "* **Detailed Question (₹99):** Unga life situation-ah pathi detailed-ana prediction.\n\n"
        "Edhula book panna virumburinga?"
    ),
    "enthe_consultation": (
        "One Question ₹1-ku simple kelvi, Detailed Question ₹99-ku full analysis.\n\n"
        "Enthe consultation book panne virumburinge?"
    ),
    "enthe_plan": (
        "One Question ₹1, Detailed Question ₹99.\n\nEnthe plan eh book panne virumburinge?"
    ),
    "tamil_script_question": (
        "One Question — ₹1\nDetailed Question — ₹99\n\nஎதை புக் செய்ய விரும்புகிறீர்கள்?"
    ),
    "names_translated_prices_only": (
        "Oru kelvi-ku ₹1, detailed-ana analysis-ku ₹99. Ungaluku yedhu seri?"
    ),
    "english_no_which_word": (
        "We have One Question for ₹1 and Detailed Question for ₹99. Shall I book one for you?"
    ),
    "hindi_mix": (
        "One Question ₹1 hai aur Detailed Question ₹99 hai. Aapko kaunsa chahiye?"
    ),
    "rupees_after_number": (
        "Simple kelvi 1 rupee, full life analysis 99 rupees. Ungalukku endhu venum?"
    ),
    "three_packages_bold": (
        "**One Question** – ₹1\n**Detailed Question** – ₹99\n**Marriage Compatability** – ₹99\n\n"
        "Ungalukku sariyaana onnu sollunga?"
    ),
    "rs_dot_no_names": (
        "Simple kelvi Rs.1, full analysis Rs.99, marriage porutham Rs.99. Yedha select pannuvinga?"
    ),
}

NO_BUTTONS = {
    "one_price_asks_detail": "One Question-ku ₹1 dhaan. Unga kelvi enna?",
    "statement_no_question": "Your consultation is confirmed. The astrologer will reply here within a day.",
    "payment_received_asks_dob": "₹99 payment kidaichiduchu. Unga date of birth enna?",
    "bigger_number_is_not_a_price": "Enga kitta 199 jothidargal irukanga, 1 nimishathula reply varum. Enna kelvi?",
}


def _ctx():
    return deal_actions.DealContext(config=CONFIG, db=object(), lead_id="l", tenant_id="t", phone="",
                                    buttons_enabled=True)


@pytest.fixture
def nothing_chosen(monkeypatch):
    monkeypatch.setattr(deal_actions, "_session", lambda ctx: {})


@pytest.mark.parametrize("reply", GETS_BUTTONS.values(), ids=GETS_BUTTONS.keys())
def test_package_menu_is_attached(reply, nothing_chosen):
    menu, shown = deal_turn._package_menu(reply, _ctx(), last_text="", customer_message="Enaku when job kidaikum")
    assert menu is not None and menu["options"] == MENU and not shown


@pytest.mark.parametrize("reply", NO_BUTTONS.values(), ids=NO_BUTTONS.keys())
def test_no_package_menu(reply, nothing_chosen):
    menu, _shown = deal_turn._package_menu(reply, _ctx(), last_text="", customer_message="ok")
    assert menu is None


def test_mid_booking_question_gets_no_package_menu(monkeypatch):
    monkeypatch.setattr(deal_actions, "_session", lambda ctx: {"package_key": "one_question", "status": "collecting"})
    reply = "One Question ₹1 select pannitinga, Detailed Question ₹99 illa. Unga peyar enna?"
    menu, _shown = deal_turn._package_menu(reply, _ctx(), last_text="", customer_message="One question")
    assert menu is None


def test_same_menu_is_not_resent_to_a_vague_reply(nothing_chosen):
    last = "Idho options:\n\n[1 Rs]  [99Rs]  [Marriage 99Rs]"
    menu, shown = deal_turn._package_menu(GETS_BUTTONS["live_edhula"], _ctx(), last_text=last, customer_message="hmm")
    assert menu is None and shown
