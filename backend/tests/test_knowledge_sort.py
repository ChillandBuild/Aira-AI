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
    sections = [
        Section("s1", "fact text 29"),
        Section("s2", "rule text"),
        Section("s3", "Approved reply: charges start from 29 rupees."),
        Section("s4", "I agree, I'd replace this section"),
        Section("s5", "unlabelled"),
    ]
    labels = {
        "s1": ks.Label("FACT", [], ""),
        "s2": ks.Label("RULE", [], ""),
        "s3": ks.Label("MIXED", ["charges start from 29 rupees", "charges start from 49 rupees"], ""),
        "s4": ks.Label("JUNK", [], "pasted AI chat"),
    }
    b = ks.bucket_sections(sections, labels)
    assert b.facts == ["fact text 29", "charges start from 29 rupees"]
    assert b.rules == ["rule text", "Approved reply: charges start from 29 rupees."]
    assert b.unverified == ["charges start from 49 rupees"]
    assert [x["note"] for x in b.left_out] == ["pasted AI chat", "Aira couldn't tell what this part is, so it was left out."]


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
