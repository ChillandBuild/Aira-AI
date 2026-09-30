"""The package-menu backstop works for any business, not only the astrology tenants it was
first fixed for: nested course categories, short plan names that hide inside other words,
prices written "12000/-", and every package costing the same."""
import pytest

from app.services import deal_actions, deal_turn


def _ctx(packages, fields=()):
    config = {"enabled": True, "fields": list(fields), "packages": packages}
    return deal_actions.DealContext(config=config, db=object(), lead_id="l", tenant_id="t", phone="",
                                    buttons_enabled=True)


@pytest.fixture(autouse=True)
def nothing_chosen(monkeypatch):
    monkeypatch.setattr(deal_actions, "_session", lambda ctx: {})


def _menu(packages, reply, fields=()):
    menu, _shown = deal_turn._package_menu(reply, _ctx(packages, fields), last_text="", customer_message="details?")
    return menu["options"] if menu else None


COACHING = [
    {"key": "long", "name": "Long Term Course", "options": [
        {"key": "y1", "name": "1 Year Program", "amount_paise": 5000000},
        {"key": "y2", "name": "2 Year Program", "amount_paise": 9000000}]},
    {"key": "crash", "name": "Crash Course", "options": [
        {"key": "d30", "name": "30 Day Crash", "amount_paise": 800000},
        {"key": "d60", "name": "60 Day Crash", "amount_paise": 1400000}]},
]
GYM = [
    {"key": "basic", "name": "Basic", "amount_paise": 99900},
    {"key": "pro", "name": "Pro", "amount_paise": 199900},
    {"key": "premium", "name": "Premium", "amount_paise": 299900},
]
SALON = [
    {"key": "cut", "name": "Haircut", "amount_paise": 30000},
    {"key": "spa", "name": "Hair Spa", "amount_paise": 80000},
    {"key": "facial", "name": "Facial", "amount_paise": 120000},
]
CLINIC = [
    {"key": "gen", "name": "General Consultation", "amount_paise": 50000},
    {"key": "fu", "name": "Follow-up Visit", "amount_paise": 50000},
]
FLATS = [
    {"key": "2bhk", "name": "2BHK Flat", "amount_paise": 450000000},
    {"key": "3bhk", "name": "3BHK Flat", "amount_paise": 650000000},
]


class TestGetsButtons:
    def test_coaching_top_level_categories(self):
        reply = "We run a Long Term Course and a Crash Course. Which suits your son?"
        assert _menu(COACHING, reply) == ["Long Term Course", "Crash Course"]

    def test_coaching_options_inside_one_category(self):
        reply = ("Long term course-la rendu options irukku: 1 Year Program ₹50,000, 2 Year Program ₹90,000. "
                 "Unga son-ku edhu suit aagum?")
        assert _menu(COACHING, reply) == ["1 Year Program", "2 Year Program"]

    def test_coaching_category_options_by_price_only(self):
        reply = "Crash course: 30 naal ₹8,000, 60 naal ₹14,000. Edhu venum?"
        assert _menu(COACHING, reply) == ["30 Day Crash", "60 Day Crash"]

    def test_gym_short_plan_names(self):
        reply = "Basic ₹999, Pro ₹1,999 and Premium ₹2,999 a month. Which one works for you?"
        assert _menu(GYM, reply) == ["Basic", "Pro", "Premium"]

    def test_salon_prices_written_with_slash_dash(self):
        reply = "Cutting 300/-, spa 800/-, face treatment 1200/-. Edhu venum?"
        assert _menu(SALON, reply) == ["Haircut", "Hair Spa", "Facial"]

    def test_clinic_every_package_same_price(self):
        reply = "General Consultation and Follow-up Visit are both ₹500. Which one do you need?"
        assert _menu(CLINIC, reply) == ["General Consultation", "Follow-up Visit"]

    def test_real_estate_names_with_lakh_prices(self):
        reply = "2BHK Flat ₹45 lakh, 3BHK Flat ₹65 lakh. Which one are you looking for?"
        assert _menu(FLATS, reply) == ["2BHK Flat", "3BHK Flat"]


class TestNoButtons:
    def test_plan_names_hidden_inside_other_words(self):
        reply = "Basically the process is simple: we check your fitness first. What's your goal?"
        assert _menu(GYM, reply) is None

    def test_question_asks_for_a_required_detail(self):
        fields = [{"key": "name", "label": "Full name", "type": "text"}]
        reply = "Basic is ₹999 and Pro is ₹1,999. Before I suggest one, may I have your full name?"
        assert _menu(GYM, reply, fields) is None

    def test_one_offering_and_a_question(self):
        assert _menu(SALON, "Haircut is ₹300. What time suits you?") is None

    def test_statement_without_question(self):
        assert _menu(GYM, "Basic ₹999, Pro ₹1,999, Premium ₹2,999.") is None
