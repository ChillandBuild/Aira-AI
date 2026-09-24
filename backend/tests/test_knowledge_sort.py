import pytest

from app.services import knowledge_sort as ks
from app.services.knowledge_sections import Section
from knowledge_sort_helpers import T, add_doc, env, fake_model  # noqa: F401  (env is a fixture)

RULES = "Greeting Rules\nAlways say vanakkam first.\nNever send voice notes."
FACTS = "Pricing\nConsultations start from 29 rupees. Link: https://astrotamil.co.in/app/consultation/"


async def _sort(env, doc, **kw):
    params = dict(
        tenant_id=T, document_id=doc["id"], source_text=kw.pop("source_text"), truncated=False,
        campaign_tag_id=None, replaces_document_id=None, origin="upload", user_id="u1",
    )
    params.update(kw)
    return await ks.run_sort(env.db, **params)


# ─── bucket_sections ──────────────────────────────────────────────────────────

def test_buckets_route_each_label():
    # s3 is deliberately MIXED: its price sentence is a verified FACT that must also be
    # cut out of the rules text (mixed_rules_text), leaving only the actual rule behind.
    sections = [
        Section("s1", "fact text 29"),
        Section("s2", "rule text"),
        Section("s3", "Always mention our tagline first.\n\nApproved reply: charges start from 29 rupees."),
        Section("s4", "I agree, I'd replace this section"),
        Section("s5", "unlabelled"),
    ]
    labels = {
        "s1": ks.Label("FACT", [], ""),
        "s2": ks.Label("RULE", [], ""),
        "s3": ks.Label("MIXED", ["charges start from 29 rupees.", "charges start from 49 rupees"], ""),
        "s4": ks.Label("JUNK", [], "pasted AI chat"),
    }
    b = ks.bucket_sections(sections, labels)
    assert b.facts == ["fact text 29", "charges start from 29 rupees."]
    assert b.rules == ["rule text", "Always mention our tagline first.\n\nApproved reply:"]
    assert b.unverified == ["charges start from 49 rupees"]
    assert [x["note"] for x in b.left_out] == ["pasted AI chat", "Aira couldn't tell what this part is, so it was left out."]


def test_mixed_rules_text_removes_copied_facts_and_collapses_blanks():
    section = "Always greet warmly.\n\nConsultations start from 29 rupees.\n\nNever rush the customer."
    result = ks.mixed_rules_text(section, ["Consultations start from 29 rupees."])
    assert result == "Always greet warmly.\n\nNever rush the customer."


def test_mixed_rules_text_removes_an_unverified_fact_too():
    """Even a fact that didn't verify is still text the section no longer needs as a
    rule -- it's cut out unconditionally, not only when it checks out."""
    section = "Follow up within a day.\n\nPrice is 49 rupees."
    assert ks.mixed_rules_text(section, ["Price is 49 rupees."]) == "Follow up within a day."


def test_mixed_rules_text_returns_empty_when_almost_nothing_but_facts():
    section = "Price 29 rupees only."
    assert ks.mixed_rules_text(section, ["Price 29 rupees only."]) == ""


# ─── run_sort ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_all_facts_file_goes_entirely_to_lookup(env, monkeypatch):
    env.set_description("ABOUT US\nWe are AstroTamil.")
    calls = fake_model(monkeypatch, labels=lambda sid, text: ("FACT", []))
    doc = add_doc(env.db)
    review = await _sort(env, doc, source_text=FACTS)

    assert "compile" not in calls
    assert review["proposed_description"] == "ABOUT US\nWe are AstroTamil."
    assert review["proposed_facts"] == FACTS
    assert review["status"] == "pending"


@pytest.mark.asyncio
async def test_kit_placeholders_and_the_example_never_reach_facts(env, monkeypatch):
    fake_model(monkeypatch, labels=lambda sid, text: ("FACT", []))
    doc = add_doc(env.db)
    source = (
        "Pricing\nConsultation Rs 29.\nHome visit: [OWNER TO CHECK]\n\n"
        "Q: Refund?\nA: [OWNER TO CHECK]\n\n"
        "=== EXAMPLE BELOW - DELETE BEFORE UPLOADING ===\nFake Academy fee Rs 85,000"
    )
    review = await _sort(env, doc, source_text=source)

    assert review["proposed_facts"] == "Pricing\nConsultation Rs 29."
    blanks = [item["text"] for item in review["left_out"] if item["note"] == ks.BLANK_NOTE]
    assert blanks == ["Home visit:", "Refund?"]


@pytest.mark.asyncio
async def test_a_kit_file_routes_by_heading_and_only_labels_the_rest(env, monkeypatch):
    calls = fake_model(monkeypatch, labels=lambda sid, text: ("JUNK", []))
    doc = add_doc(env.db)
    source = (
        "Owner notes.\n\nABOUT YOUR BUSINESS\nWe are AstroTamil.\n\nWHO YOUR CUSTOMERS ARE\nFamilies.\n\n"
        "WHAT AIRA MUST NEVER SAY OR PROMISE\n- Never promise results.\n\n"
        "PRODUCTS, SERVICES, PRICES\nConsultation Rs 29."
    )
    review = await _sort(env, doc, source_text=source)

    assert review["proposed_facts"] == "PRODUCTS, SERVICES, PRICES\nConsultation Rs 29."
    assert "We are AstroTamil." in review["proposed_description"]
    assert "Never promise results." in review["proposed_description"]
    assert [item["text"] for item in review["left_out"]] == ["Owner notes."]
    assert calls.count("label") == 1


@pytest.mark.asyncio
async def test_an_all_rules_file_adds_nothing_to_lookup(env, monkeypatch):
    calls = fake_model(monkeypatch, labels=lambda sid, text: ("RULE", []))
    doc = add_doc(env.db)
    review = await _sort(env, doc, source_text=RULES)

    assert "compile" in calls
    assert review["proposed_facts"] == ""
    assert "Always say vanakkam first." in review["proposed_description"]
    assert "always say vanakkam first." in {l.lower() for l in review["proposed_rule_lines"]}


@pytest.mark.asyncio
async def test_a_campaign_file_leaves_its_rules_out(env, monkeypatch):
    fact_line = "Consultations start from 29 rupees. Link: https://astrotamil.co.in/app/consultation/"
    # Short blocks pack into one section, which the model reports as MIXED.
    calls = fake_model(monkeypatch, labels=lambda sid, text: ("MIXED", [fact_line]))
    doc = add_doc(env.db, campaign_tag_id="camp-1")
    review = await _sort(env, doc, source_text=f"{RULES}\n\n{FACTS}", campaign_tag_id="camp-1")

    assert "compile" not in calls
    assert review["left_out_rules"] and "vanakkam" in review["left_out_rules"][0]
    assert review["proposed_facts"] == fact_line


@pytest.mark.asyncio
async def test_replacing_a_file_drops_lines_only_it_claimed(env, monkeypatch):
    env.set_description("ABOUT US\nOld rule from v1.\nShared rule.\nMy own line.")
    add_doc(env.db, id="other", rule_lines=["Shared rule."], sorted_at="x", status="indexed")
    old = add_doc(env.db, id="old", rule_lines=["Old rule from v1.", "Shared rule."], sorted_at="x", status="indexed")
    seen = {}

    async def capture(system, user, *, tenant_id, max_tokens):
        if system is ks._LABEL_SYSTEM:
            return {"sections": [{"id": "s1", "label": "RULE", "facts": []}]}
        seen["user"] = user
        return {"description": "ABOUT US\nShared rule.\nMy own line.\nNew rule from v2.", "conflicts": []}

    monkeypatch.setattr(ks, "_llm_json", capture)
    doc = add_doc(env.db)
    await _sort(env, doc, source_text="New rule from v2.", replaces_document_id=old["id"])

    compile_input = seen["user"].split("NEW RULES:")[0]
    assert "Old rule from v1." not in compile_input
    assert "Shared rule." in compile_input and "My own line." in compile_input


@pytest.mark.asyncio
async def test_a_new_sort_discards_the_older_pending_review(env, monkeypatch):
    fake_model(monkeypatch, labels=lambda sid, text: ("FACT", []))
    doc = add_doc(env.db)
    first = await _sort(env, doc, source_text=FACTS)
    second = await _sort(env, doc, source_text=FACTS)
    statuses = {r["id"]: r["status"] for r in env.db.rows("knowledge_reviews")}
    assert statuses == {first["id"]: "discarded", second["id"]: "pending"}


@pytest.mark.asyncio
async def test_disagreements_are_checked_against_the_description_and_other_files(env, monkeypatch):
    env.set_description("FACTS YOU MAY STATE\n- Consultations start from ₹29.")
    add_doc(env.db, name="Pricing.pdf", full_text="Consultations start from ₹29.", sorted_at="x", status="indexed")
    fake_model(
        monkeypatch,
        labels=lambda sid, text: ("FACT", []),
        disagreements=[
            {"where": "description", "topic": "price", "new_value": "₹49", "existing_value": "₹29",
             "existing_line": "- Consultations start from ₹29.", "proposed_line": "- Consultations start from ₹49."},
            {"where": "file", "document_name": "Pricing.pdf", "topic": "price", "new_value": "₹49", "existing_value": "₹29"},
            {"where": "file", "document_name": "Pricing.pdf", "topic": "invented", "new_value": "₹99", "existing_value": "₹29"},
        ],
    )
    doc = add_doc(env.db)
    review = await _sort(env, doc, source_text="Consultations start from ₹49.")

    kinds = [(d["where"], d["new_value"]) for d in review["fact_disagreements"]]
    assert kinds == [("description", "₹49"), ("file", "₹49")]
    assert review["fact_disagreements"][0]["client_line"] is True  # no document claims that line


# ─── validate_disagreements ───────────────────────────────────────────────────

def test_validate_drops_a_description_disagreement_whose_line_does_not_exist():
    items = [{"where": "description", "new_value": "49", "existing_value": "29",
              "existing_line": "Price is 29 (paraphrased)", "proposed_line": "Price is 49"}]
    assert ks.validate_disagreements(items, new_facts="now 49", description="Price is 29.", other_docs={}, client_line_set=set()) == []


def test_validate_drops_an_unknown_file_and_same_values():
    items = [
        {"where": "file", "document_name": "Nope.pdf", "new_value": "49", "existing_value": "29"},
        {"where": "file", "document_name": "A.pdf", "new_value": "29", "existing_value": "29"},
    ]
    assert ks.validate_disagreements(items, new_facts="29 49", description="", other_docs={"A.pdf": "29"}, client_line_set=set()) == []


def test_validate_rejects_a_proposed_line_with_an_invented_value():
    items = [{"where": "description", "new_value": "49", "existing_value": "29",
              "existing_line": "Price is 29.", "proposed_line": "Price is 59."}]
    assert ks.validate_disagreements(items, new_facts="now 49", description="Price is 29.", other_docs={}, client_line_set=set()) == []


# ─── model output parsing ─────────────────────────────────────────────────────

def test_parse_json_tolerates_code_fences_and_chatter():
    assert ks._parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert ks._parse_json('Sure! {"a": 2} hope that helps') == {"a": 2}
    with pytest.raises(ValueError):
        ks._parse_json("no json here")


@pytest.mark.asyncio
async def test_missing_model_config_becomes_a_plain_message(monkeypatch):
    from app.services import ai_reply

    async def boom(*a, **k):
        raise RuntimeError("ai_reply_model not configured for this client")

    monkeypatch.setattr(ai_reply, "_llm_chat", boom)
    with pytest.raises(ks.SortError, match="no AI model is set up"):
        await ks._llm_json("s", "u", tenant_id=T, max_tokens=10)


@pytest.mark.asyncio
async def test_two_bad_parses_raise_a_sort_error(monkeypatch):
    from app.services import ai_reply

    async def garbage(*a, **k):
        return "not json"

    monkeypatch.setattr(ai_reply, "_llm_chat", garbage)
    with pytest.raises(ks.SortError, match="couldn't read the sorting result"):
        await ks._llm_json("s", "u", tenant_id=T, max_tokens=10)


# ─── handover extraction and the deterministic safety net ─────────────────────

def test_strip_handover_lines_drops_a_phone_and_call_line():
    text = "ABOUT US\nWe are AstroTamil.\n\nHOW CUSTOMERS BUY\nBook on the app.\nTo talk to a person, call 98765 43210."
    cleaned, handover = ks.strip_handover_lines(text, "")
    assert "98765" not in cleaned and "call" not in cleaned.lower()
    assert handover == "To talk to a person, call 98765 43210."
    assert "Book on the app." in cleaned


def test_strip_handover_lines_prefers_the_models_own_handover():
    text = "Call 98765 43210 for help."
    cleaned, handover = ks.strip_handover_lines(text, "WhatsApp us for help.")
    assert cleaned == ""
    assert handover == "WhatsApp us for help."


def test_strip_handover_lines_leaves_a_phone_number_with_no_handover_word_alone():
    text = "Our office is at 98765 43210 Anna Salai."  # an address, not a handover line
    cleaned, handover = ks.strip_handover_lines(text, "")
    assert cleaned == text and handover == ""


@pytest.mark.asyncio
async def test_run_sort_stores_the_compiled_handover(env, monkeypatch):
    fake_model(monkeypatch, labels=lambda sid, text: ("RULE", []), handover="Reach us on WhatsApp for help.")
    doc = add_doc(env.db)
    review = await _sort(env, doc, source_text=RULES)
    assert review["suggested_handover"] == "Reach us on WhatsApp for help."


@pytest.mark.asyncio
async def test_run_sort_catches_a_handover_line_the_model_left_in(env, monkeypatch):
    calls = []

    async def compile_that_leaks_a_handover_line(system, user, *, tenant_id, max_tokens):
        if system is ks._LABEL_SYSTEM:
            return {"sections": [{"id": "s1", "label": "RULE", "facts": []}]}
        calls.append(system)
        return {
            "description": "ABOUT US\nWe are AstroTamil.\n\nTo talk to a person, call 98765 43210.",
            "conflicts": [],
            "handover": "",
        }

    monkeypatch.setattr(ks, "_llm_json", compile_that_leaks_a_handover_line)
    doc = add_doc(env.db)
    # The line must come from the file: a suggested contact the file doesn't contain
    # is treated as invented and never offered (verified_handover).
    review = await _sort(env, doc, source_text=RULES + "\nTo talk to a person, call 98765 43210.")
    assert "98765" not in review["proposed_description"]
    assert review["suggested_handover"] == "To talk to a person, call 98765 43210."


# ─── enforce_section_limits ────────────────────────────────────────────────────

_LONG_HOW_TO_BUY = "buy now " * 65  # 130 words, over the 60-word how_to_buy limit


@pytest.mark.asyncio
async def test_enforce_section_limits_condenses_only_the_section_over_limit(monkeypatch):
    text = f"ABOUT US\nWe are AstroTamil.\n\nHOW CUSTOMERS BUY\n{_LONG_HOW_TO_BUY.strip()}"
    seen_headings = []

    async def condense(system, user, *, tenant_id, max_tokens):
        seen_headings.append(user.splitlines()[0])
        return {"text": "Book on the app."}

    monkeypatch.setattr(ks, "_llm_json", condense)
    result = await ks.enforce_section_limits(T, text)
    assert seen_headings == ["SECTION: HOW CUSTOMERS BUY"]
    assert "Book on the app." in result
    assert "We are AstroTamil." in result  # untouched section survives as-is


@pytest.mark.asyncio
async def test_enforce_section_limits_leaves_sections_within_limit_alone(monkeypatch):
    text = "ABOUT US\nWe are AstroTamil."

    async def boom(*a, **k):
        raise AssertionError("should not call the model when nothing is over limit")

    monkeypatch.setattr(ks, "_llm_json", boom)
    assert await ks.enforce_section_limits(T, text) == text


@pytest.mark.asyncio
async def test_enforce_section_limits_keeps_the_shorter_version_when_condense_fails_to_fit(monkeypatch):
    text = f"HOW CUSTOMERS BUY\n{_LONG_HOW_TO_BUY.strip()}"

    async def condense_but_still_too_long(system, user, *, tenant_id, max_tokens):
        return {"text": _LONG_HOW_TO_BUY.strip() + " buy"}  # longer than the original

    monkeypatch.setattr(ks, "_llm_json", condense_but_still_too_long)
    result = await ks.enforce_section_limits(T, text)
    assert result == text  # the original (shorter) text wins


@pytest.mark.asyncio
async def test_enforce_section_limits_preserves_other_text_untouched(monkeypatch):
    text = "ABOUT US\nWe are AstroTamil.\n\nRANDOM SECTION\nOdd leftover text."

    async def boom(*a, **k):
        raise AssertionError("nothing is over limit here")

    monkeypatch.setattr(ks, "_llm_json", boom)
    result = await ks.enforce_section_limits(T, text)
    assert result == text


# ─── Suggested handover line must never carry an invented contact (2026-09-24) ──

def test_suggested_handover_with_invented_number_is_replaced_by_the_source_line():
    # Live eval: the model suggested 9840012345; the file says 97890 33445.
    from app.services.knowledge_sort import verified_handover
    source = ("Timings 10am to 9pm.\n"
              "If a client wants to speak to the manager, share Divya's number, 97890 33445, and let her handle it.")
    got = verified_handover("Please reach out to her directly at 9840012345.", source)
    assert "9840012345" not in got
    assert "97890 33445" in got


def test_suggested_handover_without_contact_prefers_the_source_line_with_the_number():
    from app.services.knowledge_sort import verified_handover
    source = "For staff concerns, call Mr. Ganesan on 94430 11223."
    assert "94430 11223" in verified_handover("Please contact Mr. Ganesan directly.", source)


def test_verified_model_handover_is_kept_when_the_source_has_no_phone_line():
    from app.services.knowledge_sort import verified_handover
    source = "If they need help, tell them to use the Support option in the app."
    line = "Use the Support option in the app."
    assert verified_handover(line, source) == line


def test_unverifiable_handover_and_no_source_line_gives_empty():
    from app.services.knowledge_sort import verified_handover
    assert verified_handover("Call us on 90000 00000.", "We sell sarees online.") == ""


def test_handover_sentence_found_for_share_and_give_number_phrasings():
    from app.services.knowledge_sort import verified_handover
    neet = ("If a parent wants to meet the academy director in person or has a serious complaint "
            "about a teacher, share the office number 94430 11223 and tell them to ask for Mr. Ganesan.")
    saree = ("If a customer has a serious complaint, like a wrong item received or damaged in transit, "
             "give them Meena's number directly, 98407 65432, she handles all after-sales issues personally.")
    assert "94430 11223" in verified_handover("", neet)
    assert "98407 65432" in verified_handover("", saree)
