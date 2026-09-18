import pytest

from app.services import knowledge_sort as ks
from app.services import knowledge_versions as kv
from knowledge_sort_helpers import T, add_doc, env, fake_model  # noqa: F401  (env is a fixture)

BASE = "ABOUT US\nWe are AstroTamil.\n\nWHAT YOU MUST NEVER DO\n- Never predict."


def _review(env, doc, *, proposed, facts="Price 29.", conflicts=None, disagreements=None, **extra):
    base = kv.current_description_version(env.db, T)
    return env.db.add("knowledge_reviews", **{
        "tenant_id": T, "document_id": doc["id"], "base_version_id": base["id"],
        "proposed_description": proposed, "proposed_facts": facts,
        "conflicts": conflicts or [], "fact_disagreements": disagreements or [], **extra,
    })


def _choices(env, review, **kw):
    payload = ks.build_review_payload(env.db, T, review["document_id"])
    accepted = kw.pop("accept", [h["id"] for h in payload["hunks"]])
    return ks.ApplyChoices(base_version_id=payload["base_version_id"], accepted_hunk_ids=accepted, **kw)


def test_payload_flags_hunks_touching_client_lines(env):
    env.set_description(BASE)
    doc = add_doc(env.db)
    _review(env, doc, proposed=BASE.replace("- Never predict.", "- Never predict dates."))
    payload = ks.build_review_payload(env.db, T, doc["id"])
    assert payload["stale"] is False
    assert [h["touches_client_lines"] for h in payload["hunks"]] == [True]
    assert payload["word_count"] == len(payload["proposed_description"].split())


def test_apply_commits_description_facts_and_versions(env):
    env.set_description(BASE)
    doc = add_doc(env.db)
    env.db.add("knowledge_chunks", tenant_id=T, document_id=doc["id"], content="old raw rulebook chunk")
    review = _review(env, doc, proposed=BASE + "\n- Never promise security.")

    result = ks.apply_review(env.db, T, doc["id"], _choices(env, review), user_id="u1", is_owner=True)

    assert result["description_changed"] is True
    assert env.description().endswith("- Never promise security.")
    reasons = [v["reason"] for v in kv.list_versions(env.db, T, "description")]
    assert reasons == ["upload", "baseline"]
    assert [v["content"] for v in kv.list_versions(env.db, T, "facts", doc["id"])] == ["Price 29."]
    saved = env.db.rows("knowledge_documents")[0]
    assert saved["status"] == "indexed" and saved["full_text"] == "Price 29." and saved["sorted_at"]
    assert saved["rule_lines"] == ["- Never promise security."]
    assert env.db.rows("knowledge_chunks") == []
    assert env.db.rows("knowledge_reviews")[0]["status"] == "applied"


def test_unticked_hunks_are_not_applied(env):
    env.set_description(BASE)
    doc = add_doc(env.db)
    review = _review(env, doc, proposed=BASE + "\n- Never promise security.")
    ks.apply_review(env.db, T, doc["id"], _choices(env, review, accept=[]), user_id=None, is_owner=True)
    assert env.description() == BASE


def test_a_changed_description_since_the_review_is_refused(env):
    env.set_description(BASE)
    doc = add_doc(env.db)
    review = _review(env, doc, proposed=BASE + "\nNew.")
    choices = _choices(env, review)
    kv.save_description(env.db, T, BASE + "\nEdited meanwhile.", "edit", None)
    with pytest.raises(ks.StaleError):
        ks.apply_review(env.db, T, doc["id"], choices, user_id=None, is_owner=True)
    assert ks.build_review_payload(env.db, T, doc["id"])["stale"] is True


def test_an_empty_result_is_refused(env):
    doc = add_doc(env.db)
    review = _review(env, doc, proposed="")  # FAQ-only first upload
    with pytest.raises(ks.EmptyDescriptionError):
        ks.apply_review(env.db, T, doc["id"], _choices(env, review), user_id=None, is_owner=True)


def test_a_manager_cannot_change_the_description_but_can_apply_facts(env):
    env.set_description(BASE)
    doc = add_doc(env.db)
    review = _review(env, doc, proposed=BASE + "\nNew rule.")
    with pytest.raises(ks.OwnerRequiredError):
        ks.apply_review(env.db, T, doc["id"], _choices(env, review), user_id=None, is_owner=False)

    faq = add_doc(env.db, name="faq.txt")
    faq_review = _review(env, faq, proposed=BASE)
    result = ks.apply_review(env.db, T, faq["id"], _choices(env, faq_review), user_id=None, is_owner=False)
    assert result["description_changed"] is False


def test_a_conflict_choice_lands_under_its_heading(env):
    env.set_description(BASE)
    doc = add_doc(env.db)
    conflict = {"id": "c1", "topic": "greeting", "heading": "ABOUT US", "option_a": "Say hi.", "option_b": "Say vanakkam.",
                "source_a": "current Description", "source_b": "this file"}
    review = _review(env, doc, proposed=BASE, conflicts=[conflict])
    ks.apply_review(env.db, T, doc["id"], _choices(env, review, conflict_choices={"c1": "b"}), user_id=None, is_owner=True)
    assert env.description().split("\n")[:3] == ["ABOUT US", "We are AstroTamil.", "Say vanakkam."]
    assert "Say vanakkam." in env.db.rows("knowledge_documents")[0]["rule_lines"]


def test_an_accepted_price_update_swaps_its_line(env):
    env.set_description("FACTS\n- Consultations start from 29.")
    doc = add_doc(env.db)
    update = {"id": "d1", "where": "description", "existing_line": "- Consultations start from 29.",
              "proposed_line": "- Consultations start from 49.", "new_value": "49", "existing_value": "29"}
    review = _review(env, doc, proposed="FACTS\n- Consultations start from 29.", disagreements=[update])
    ks.apply_review(env.db, T, doc["id"], _choices(env, review, accepted_update_ids=["d1"]), user_id=None, is_owner=True)
    assert env.description() == "FACTS\n- Consultations start from 49."


def test_a_price_update_is_skipped_when_its_line_was_changed_by_a_hunk(env):
    env.set_description("FACTS\n- Consultations start from 29.")
    doc = add_doc(env.db)
    update = {"id": "d1", "where": "description", "existing_line": "- Consultations start from 29.",
              "proposed_line": "- Consultations start from 49.", "new_value": "49", "existing_value": "29"}
    review = _review(env, doc, proposed="FACTS\n- Consultations vary.", disagreements=[update])
    ks.apply_review(env.db, T, doc["id"], _choices(env, review, accepted_update_ids=["d1"]), user_id=None, is_owner=True)
    assert env.description() == "FACTS\n- Consultations vary."


def test_replace_deletes_the_old_file_and_inherits_its_surviving_lines(env):
    env.set_description(BASE)
    old = add_doc(env.db, name="v1.docx", status="indexed", sorted_at="x", rule_lines=["- Never predict."])
    new = add_doc(env.db, name="v2.docx")
    review = _review(env, new, proposed=BASE + "\n- Never guarantee.", replaces_document_id=old["id"])
    ks.apply_review(env.db, T, new["id"], _choices(env, review), user_id=None, is_owner=True)

    docs = env.db.rows("knowledge_documents")
    assert [d["name"] for d in docs] == ["v2.docx"]
    assert set(docs[0]["rule_lines"]) == {"- Never guarantee.", "- Never predict."}


def test_discard_deletes_a_new_upload_but_keeps_a_live_file(env):
    new = add_doc(env.db, status="review_pending")
    _review(env, new, proposed="")
    ks.discard_review(env.db, T, new["id"])
    assert env.db.rows("knowledge_documents") == []

    live = add_doc(env.db, status="indexed", sort_state="review")
    _review(env, live, proposed="")
    ks.discard_review(env.db, T, live["id"])
    assert env.db.rows("knowledge_documents")[0]["sort_state"] is None


@pytest.mark.asyncio
async def test_sort_failure_on_a_new_upload_marks_it_failed(env, monkeypatch):
    monkeypatch.setattr(ks, "get_supabase", lambda: env.db)

    async def no_model(*a, **k):
        raise ks.SortError(ks.NO_MODEL_MESSAGE)

    monkeypatch.setattr(ks, "_llm_json", no_model)
    doc = add_doc(env.db, status="processing", source_text="Some rules.")
    await ks.sort_document(tenant_id=T, document_id=doc["id"], user_id=None)
    saved = env.db.rows("knowledge_documents")[0]
    assert (saved["status"], saved["sort_state"], saved["error_message"]) == ("failed", "failed", ks.NO_MODEL_MESSAGE)


@pytest.mark.asyncio
async def test_sort_failure_on_a_live_file_keeps_it_live(env, monkeypatch):
    monkeypatch.setattr(ks, "get_supabase", lambda: env.db)

    async def boom(*a, **k):
        raise ValueError("unexpected")

    monkeypatch.setattr(ks, "_llm_json", boom)
    doc = add_doc(env.db, status="indexed", source_text="Some rules.")
    await ks.sort_document(tenant_id=T, document_id=doc["id"], user_id=None)
    saved = env.db.rows("knowledge_documents")[0]
    assert (saved["status"], saved["sort_state"]) == ("indexed", "failed")
    assert saved["error_message"] == ks.SortError.message


@pytest.mark.asyncio
async def test_a_successful_sort_leaves_the_upload_waiting_for_review(env, monkeypatch):
    monkeypatch.setattr(ks, "get_supabase", lambda: env.db)
    fake_model(monkeypatch, labels=lambda sid, text: ("FACT", []))
    doc = add_doc(env.db, status="processing", source_text="Price 29.")
    await ks.sort_document(tenant_id=T, document_id=doc["id"], user_id=None)
    saved = env.db.rows("knowledge_documents")[0]
    assert (saved["status"], saved["sort_state"]) == ("review_pending", "review")
    assert env.db.rows("knowledge_reviews")[0]["origin"] == "upload"


def test_prepare_resort_copies_a_legacy_files_text_and_keeps_it_live(env):
    doc = add_doc(env.db, status="indexed", full_text="Raw legacy text.")
    ks.prepare_resort(env.db, T, doc["id"])
    saved = env.db.rows("knowledge_documents")[0]
    assert (saved["status"], saved["sort_state"], saved["source_text"]) == ("indexed", "sorting", "Raw legacy text.")
    with pytest.raises(ks.SortError, match="already being sorted"):
        ks.prepare_resort(env.db, T, doc["id"])


def test_prepare_resort_refuses_a_file_with_no_text(env):
    doc = add_doc(env.db, status="failed")
    with pytest.raises(ks.SortError, match="no text to sort"):
        ks.prepare_resort(env.db, T, doc["id"])
