from app.services.knowledge_kit import readiness, scrub_placeholders, split_kit, strip_example

PROFILE = """ABOUT US
Vetri NEET Academy, Madurai. NEET coaching since 2016.

HOW CUSTOMERS BUY
Book a free demo class, then pay the registration fee.

WHO WE TALK TO
Parents of Class 11 and 12 students."""


def _by_key(items):
    return {i["key"]: i for i in items}


# ─── strip_example ────────────────────────────────────────────────────────────

def test_everything_from_the_example_marker_on_is_cut():
    text = "1. ABOUT YOUR BUSINESS\nOur real shop.\n\n=== EXAMPLE BELOW - DELETE BEFORE UPLOADING ===\nMade-up shop, Rs 999"
    assert strip_example(text) == "1. ABOUT YOUR BUSINESS\nOur real shop."


def test_marker_is_found_whatever_the_case_and_dashes():
    text = "Real text\nexample below — delete before uploading\nFake price Rs 50"
    assert strip_example(text) == "Real text"


def test_text_without_the_marker_is_unchanged():
    text = "An example of our work: 400 homes."
    assert strip_example(text) == text


# ─── scrub_placeholders ───────────────────────────────────────────────────────

def test_owner_to_check_line_is_removed_and_reported_as_a_gap():
    clean, gaps = scrub_placeholders("Fee: Rs 85,000\nHostel fee: [OWNER TO CHECK]\nBatch: June")
    assert clean == "Fee: Rs 85,000\nBatch: June"
    assert gaps == ["Hostel fee:"]


def test_an_unanswered_question_drops_its_q_line_too():
    text = "Q: Can I pay in parts?\nA: Yes, in 3 parts.\n\nQ: Refund if my child leaves?\nA: [OWNER TO CHECK]"
    clean, gaps = scrub_placeholders(text)
    assert "Refund" not in clean
    assert "Can I pay in parts?" in clean and "Yes, in 3 parts." in clean
    assert gaps == ["Refund if my child leaves?"]


def test_unfilled_template_hints_are_gaps():
    clean, gaps = scrub_placeholders("Name: Vetri Academy\n[WRITE your prices here, one line per item]")
    assert clean == "Name: Vetri Academy"
    assert gaps == ["Your prices here, one line per item"]


def test_ordinary_brackets_are_kept():
    text = "Sessions are in Tamil [or English on request]. Price [incl. GST]: Rs 500"
    assert scrub_placeholders(text) == (text, [])


def test_placeholder_matching_ignores_case():
    clean, gaps = scrub_placeholders("Parking: [owner to check]\nOpen daily")
    assert clean == "Open daily"
    assert gaps == ["Parking:"]


# ─── readiness ────────────────────────────────────────────────────────────────

def test_full_setup_is_ready():
    items = readiness(
        description=PROFILE + "\n\nWHAT YOU MUST NEVER DO\n- Never promise a seat.\n\nHOW TO SOUND\nWarm.",
        handover_line="Call our office on 90000 12345.",
        facts=["NEET Long Term: Rs 85,000 per year.", "Q: Is there a hostel?\nA: No."],
    )
    assert all(i["ok"] for i in items)
    assert len(items) == 8


def test_missing_prices_handover_and_questions_are_flagged():
    items = _by_key(readiness(description=PROFILE, handover_line="", facts=["We are open Monday to Saturday."]))
    assert items["about"]["ok"] and items["how_to_buy"]["ok"] and items["who"]["ok"]
    assert not items["prices"]["ok"] and items["prices"]["level"] == "must"
    assert not items["handover"]["ok"] and items["handover"]["level"] == "must"
    assert not items["questions"]["ok"] and items["questions"]["level"] == "nice"
    assert not items["voice"]["ok"] and items["voice"]["level"] == "optional"


def test_price_detection_covers_common_indian_formats():
    for fact in ["Basic plan ₹1,999", "Fee Rs. 500", "INR 2500 per month", "Haircut 300/-", "Loan at 10.5% interest"]:
        assert _by_key(readiness(description="", handover_line="", facts=[fact]))["prices"]["ok"], fact


def test_policy_words_count_as_customer_questions():
    items = _by_key(readiness(description="", handover_line="", facts=["Refund within 7 days of joining."]))
    assert items["questions"]["ok"]


def test_empty_everything_is_not_ready():
    items = readiness(description="", handover_line="", facts=[])
    assert not any(i["ok"] for i in items)
    assert [i["key"] for i in items] == [
        "about", "how_to_buy", "prices", "handover", "who", "never", "questions", "voice",
    ]


def test_an_answer_typed_next_to_a_hint_is_kept():
    clean, gaps = scrub_placeholders("[WRITE your fee for one class] Rs 500 per class")
    assert clean == "Rs 500 per class"
    assert gaps == []


def test_a_hint_left_behind_a_bare_label_is_still_a_gap():
    clean, gaps = scrub_placeholders("Q: [WRITE a question customers ask]\n- [WRITE one rule]\nOpen daily")
    assert clean == "Open daily"
    assert gaps == ["A question customers ask", "One rule"]


# ─── split_kit ────────────────────────────────────────────────────────────────

KIT = """Aira Business Kit
Template for: Coaching & education

ABOUT YOUR BUSINESS
Vetri NEET Academy, Madurai.

## Who your customers are
Parents of Class 12 students.

**HOW A CUSTOMER BUYS FROM YOU:**
Book a demo, then pay Rs 5,000.

1. WHEN TO HAND OVER TO A PERSON
Call 90000 12345.

PRODUCTS, SERVICES, PRICES
Long Term: Rs 85,000.

CUSTOMER QUESTIONS AND POLICIES
Q: Hostel?
A: No."""


def test_a_kit_file_is_cut_on_its_headings_whatever_the_formatting():
    parts = split_kit(KIT)
    assert [label for label, _ in parts] == ["RULE", "RULE", "RULE", "RULE", "FACT", "FACT"]
    assert parts[0][1] == "ABOUT YOUR BUSINESS\nVetri NEET Academy, Madurai."
    assert parts[4][1] == "PRODUCTS, SERVICES, PRICES\nLong Term: Rs 85,000."


def test_text_before_the_first_heading_is_kept_unlabelled_without_the_template_title():
    parts = split_kit("Some notes from the owner.\n\n" + KIT)
    assert parts[0] == (None, "Some notes from the owner.")
    assert split_kit(KIT)[0][0] == "RULE"


def test_a_heading_with_nothing_under_it_is_dropped():
    parts = split_kit(KIT.replace("Call 90000 12345.", ""))
    assert all("HAND OVER" not in text for _, text in parts)


def test_a_file_with_fewer_than_four_kit_headings_is_not_a_kit():
    assert split_kit("ABOUT YOUR BUSINESS\nA shop.\n\nPRODUCTS, SERVICES, PRICES\nRs 5") is None
