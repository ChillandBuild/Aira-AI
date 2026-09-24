"""Route-level checks for Knowledge Auto-Sort: auth context wiring, status codes and
string error details. The service logic itself is covered by test_knowledge_sort*."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.tenant import get_tenant_and_role, get_tenant_id
from app.routes import knowledge
from app.services import knowledge_sort as ks
from app.services import knowledge_versions as kv
from knowledge_sort_helpers import T, add_doc, env  # noqa: F401  (env is a fixture)


def _client(env, monkeypatch, role="owner", permissions=None):
    monkeypatch.setattr(knowledge, "get_supabase", lambda: env.db)
    monkeypatch.setattr(ks, "get_supabase", lambda: env.db)
    app = FastAPI()
    app.include_router(knowledge.router, prefix="/api/v1/knowledge")
    ctx = {"tenant_id": T, "role": role, "user_id": "u1", "permissions": permissions or []}
    app.dependency_overrides[get_tenant_and_role] = lambda: ctx
    app.dependency_overrides[get_tenant_id] = lambda: T
    return TestClient(app)


def test_every_auto_sort_path_is_registered():
    paths = {(tuple(sorted(r.methods)), r.path) for r in knowledge.router.routes}
    for method, path in [
        ("GET", "/documents/{doc_id}/review"),
        ("POST", "/documents/{doc_id}/review/apply"),
        ("POST", "/documents/{doc_id}/review/discard"),
        ("POST", "/documents/{doc_id}/resort"),
        ("PUT", "/documents/{doc_id}/facts"),
        ("GET", "/documents/{doc_id}/delete-preview"),
        ("DELETE", "/documents/{doc_id}"),
        ("GET", "/versions"),
        ("POST", "/versions/{version_id}/restore"),
    ]:
        assert ((method,), path) in paths, f"{method} {path} missing"


@pytest.mark.parametrize(
    "error, status",
    [(ks.StaleError(), 409), (ks.EmptyDescriptionError(), 422), (ks.OwnerRequiredError(), 403),
     (ks.NotFoundError(), 404), (ks.SortError(), 400), (ks.ProfileTooLongError("This would make your profile 900 words; the limit is 700."), 422)],
)
def test_errors_map_to_status_with_a_plain_string_detail(error, status):
    http = knowledge._http(error)
    assert http.status_code == status
    assert isinstance(http.detail, str) and http.detail


def test_list_marks_documents_with_a_pending_review(env, monkeypatch):
    client = _client(env, monkeypatch)
    waiting = add_doc(env.db, name="waiting.docx", status="review_pending")
    add_doc(env.db, name="live.docx", status="indexed")
    env.db.add("knowledge_reviews", tenant_id=T, document_id=waiting["id"], status="pending")

    data = client.get("/api/v1/knowledge/documents").json()["data"]
    assert {d["name"]: d["has_pending_review"] for d in data} == {"waiting.docx": True, "live.docx": False}


def test_list_reports_search_status_without_an_n_plus_one(env, monkeypatch):
    """indexed + chunks -> searchable; indexed + no chunks + a key -> not_indexed;
    indexed + no chunks + no key -> no_jina_key; not indexed -> not searchable, no issue."""
    client = _client(env, monkeypatch)
    monkeypatch.setattr(knowledge, "get_setting", lambda key, tenant_id=None: "a-jina-key")
    chunked = add_doc(env.db, name="chunked.docx", status="indexed")
    env.db.add("knowledge_chunks", tenant_id=T, document_id=chunked["id"], content="c")
    add_doc(env.db, name="stuck.docx", status="indexed")
    add_doc(env.db, name="processing.docx", status="processing")

    data = client.get("/api/v1/knowledge/documents").json()["data"]
    by_name = {d["name"]: (d["searchable"], d["search_issue"]) for d in data}
    assert by_name == {
        "chunked.docx": (True, None),
        "stuck.docx": (False, "not_indexed"),
        "processing.docx": (False, None),
    }


def test_list_flags_no_jina_key_when_the_tenant_has_none_configured(env, monkeypatch):
    client = _client(env, monkeypatch)
    monkeypatch.setattr(knowledge, "get_setting", lambda key, tenant_id=None: None)
    add_doc(env.db, name="stuck.docx", status="indexed")

    data = client.get("/api/v1/knowledge/documents").json()["data"]
    assert data[0]["search_issue"] == "no_jina_key"


def test_upload_rejects_a_replace_target_that_is_not_a_uuid(env, monkeypatch):
    client = _client(env, monkeypatch)
    res = client.post(
        "/api/v1/knowledge/upload-document",
        files={"file": ("a.txt", b"hello", "text/plain")},
        data={"replaces_document_id": "not-a-uuid"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "The file you chose to replace wasn't found."
    assert env.db.rows("knowledge_documents") == []


def test_description_history_includes_the_current_text(env, monkeypatch):
    env.set_description("We are AstroTamil.")
    client = _client(env, monkeypatch)
    data = client.get("/api/v1/knowledge/versions", params={"kind": "description"}).json()["data"]
    assert [(v["reason"], v["content"]) for v in data] == [("baseline", "We are AstroTamil.")]


def test_facts_history_needs_a_document(env, monkeypatch):
    client = _client(env, monkeypatch)
    assert client.get("/api/v1/knowledge/versions", params={"kind": "facts"}).status_code == 400


def test_a_manager_applying_a_description_change_gets_a_403_string(env, monkeypatch):
    env.set_description("ABOUT US\nWe are AstroTamil.")
    doc = add_doc(env.db, status="review_pending")
    base = kv.current_description_version(env.db, T)
    env.db.add("knowledge_reviews", tenant_id=T, document_id=doc["id"], base_version_id=base["id"],
               proposed_description="ABOUT US\nWe are AstroTamil.\nNew rule.", proposed_facts="")
    client = _client(env, monkeypatch, role="member", permissions=["knowledge.manage"])

    review = client.get(f"/api/v1/knowledge/documents/{doc['id']}/review").json()
    res = client.post(
        f"/api/v1/knowledge/documents/{doc['id']}/review/apply",
        json={"base_version_id": review["base_version_id"], "accepted_hunk_ids": [h["id"] for h in review["hunks"]]},
    )
    assert res.status_code == 403
    assert "owner" in res.json()["detail"]


def test_an_owner_apply_succeeds_and_schedules_indexing(env, monkeypatch):
    env.set_description("ABOUT US\nWe are AstroTamil.")
    doc = add_doc(env.db, status="review_pending")
    base = kv.current_description_version(env.db, T)
    env.db.add("knowledge_reviews", tenant_id=T, document_id=doc["id"], base_version_id=base["id"],
               proposed_description="ABOUT US\nWe are AstroTamil.\nNew rule.", proposed_facts="Price 29.")
    indexed = []

    async def fake_index(*args):
        indexed.append(args)

    monkeypatch.setattr(ks, "index_facts", fake_index)
    monkeypatch.setattr(knowledge, "_queue_rubric", lambda tenant_id, result: False)
    client = _client(env, monkeypatch)

    review = client.get(f"/api/v1/knowledge/documents/{doc['id']}/review").json()
    res = client.post(
        f"/api/v1/knowledge/documents/{doc['id']}/review/apply",
        json={"base_version_id": review["base_version_id"], "accepted_hunk_ids": [h["id"] for h in review["hunks"]]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["description_changed"] is True
    assert indexed == [(T, doc["id"], "Price 29.", None)]
    assert env.description().endswith("New rule.")


def test_apply_rejects_an_unknown_conflict_choice(env, monkeypatch):
    client = _client(env, monkeypatch)
    res = client.post(
        "/api/v1/knowledge/documents/00000000-0000-0000-0000-000000000001/review/apply",
        json={"base_version_id": "x", "conflict_choices": {"c1": "maybe"}},
    )
    assert res.status_code == 422


def test_delete_without_a_body_still_works(env, monkeypatch):
    doc = add_doc(env.db, status="indexed", id="00000000-0000-0000-0000-0000000000aa")
    monkeypatch.setattr(knowledge, "_queue_rubric", lambda tenant_id, result: False)
    client = _client(env, monkeypatch)
    res = client.delete(f"/api/v1/knowledge/documents/{doc['id']}")
    assert res.status_code == 200, res.text
    assert env.db.rows("knowledge_documents") == []


def test_readiness_reads_description_handover_and_live_facts_for_a_manager(env, monkeypatch):
    client = _client(env, monkeypatch, role="manager", permissions=["knowledge.view"])
    settings = {
        "business_description": "ABOUT US\nA dental clinic.\n\nHOW CUSTOMERS BUY\nBook a checkup.",
        "handover_line": "Call 90000 12345.",
    }
    monkeypatch.setattr(knowledge, "get_setting", lambda key, tenant_id=None: settings.get(key))
    add_doc(env.db, name="prices.docx", status="indexed", full_text="Cleaning Rs 800")
    add_doc(env.db, name="waiting.docx", status="review_pending", full_text="Q: Refund?\nA: No refunds.")

    items = {i["key"]: i["ok"] for i in client.get("/api/v1/knowledge/readiness").json()["data"]}
    assert items == {
        "about": True, "how_to_buy": True, "prices": True, "handover": True,
        "who": False, "never": False, "questions": False, "voice": False,
    }
