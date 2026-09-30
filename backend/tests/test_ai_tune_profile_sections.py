"""The profile routes follow business_profile.SECTIONS, so the two new sections
(hours_contact, handover) are listed, accepted and saved through the one owner-only
PUT /api/v1/ai-tune/profile the frontend uses (blueprint 9B)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.tenant import get_tenant_id
from app.routes import ai_tune

HANDOVER_HEADING = "WHAT AIRA SAYS WHEN IT BRINGS IN YOUR TEAM"
HOURS_HEADING = "BUSINESS HOURS AND CONTACT"


@pytest.fixture
def env(monkeypatch):
    saved: list[str] = []
    state = {"description": ""}
    monkeypatch.setattr(ai_tune, "get_setting", lambda key, fallback=None, tenant_id=None: state["description"])
    monkeypatch.setattr(ai_tune, "get_supabase", lambda: object())

    def fake_save(db, tenant_id, text, reason, user_id):
        saved.append(text)
        state["description"] = text

    monkeypatch.setattr(ai_tune, "save_description", fake_save)
    monkeypatch.setattr(ai_tune, "queue_rubric_for_description", lambda tenant_id, text: True)

    async def fake_check(tenant_id):
        return None

    monkeypatch.setattr("app.services.consistency.run_check_safely", fake_check)
    app = FastAPI()
    app.include_router(ai_tune.router, prefix="/api/v1/ai-tune")
    app.dependency_overrides[get_tenant_id] = lambda: "t1"
    app.dependency_overrides[ai_tune.require_owner] = lambda: {"tenant_id": "t1", "user_id": "u1"}
    return type("Env", (), {"client": TestClient(app), "saved": saved, "state": state})


def test_profile_lists_all_eight_sections_with_the_new_limits(env):
    body = env.client.get("/api/v1/ai-tune/profile").json()
    assert [s["key"] for s in body["sections"]] == [
        "about", "how_to_buy", "who", "voice", "job", "never", "hours_contact", "handover"]
    limits = {s["key"]: s["word_limit"] for s in body["sections"]}
    assert limits["hours_contact"] == 60 and limits["handover"] == 50
    assert sum(limits.values()) <= body["hard_limit"] == 700


def test_profile_shows_the_handover_text_already_in_the_description(env):
    env.state["description"] = f"ABOUT US\nWe sell sarees.\n\n{HANDOVER_HEADING}\nTeam replies here."
    sections = {s["key"]: s for s in env.client.get("/api/v1/ai-tune/profile").json()["sections"]}
    assert sections["handover"]["text"] == "Team replies here." and sections["handover"]["words"] == 3


def test_put_saves_the_new_sections_under_their_headings(env):
    res = env.client.put("/api/v1/ai-tune/profile", json={"sections": {
        "about": "We sell sarees.", "hours_contact": "Open 10am to 6pm.", "handover": "Team replies here."}})
    assert res.status_code == 200, res.text
    assert env.saved == [
        f"ABOUT US\nWe sell sarees.\n\n{HOURS_HEADING}\nOpen 10am to 6pm.\n\n{HANDOVER_HEADING}\nTeam replies here."]
    assert {s["key"]: s["text"] for s in res.json()["sections"]}["handover"] == "Team replies here."


def test_put_with_only_the_six_old_keys_keeps_hours_contact_and_handover(env):
    env.state["description"] = (
        f"ABOUT US\nOld about.\n\n{HOURS_HEADING}\nOpen 10am to 6pm.\n\n{HANDOVER_HEADING}\nTeam replies here.")
    res = env.client.put("/api/v1/ai-tune/profile", json={"sections": {"about": "New about."}})
    assert res.status_code == 200, res.text
    assert env.saved[-1] == (
        f"ABOUT US\nNew about.\n\n{HOURS_HEADING}\nOpen 10am to 6pm.\n\n{HANDOVER_HEADING}\nTeam replies here.")


def test_put_with_an_empty_string_clears_that_section(env):
    env.state["description"] = f"ABOUT US\nWe sell sarees.\n\n{HANDOVER_HEADING}\nTeam replies here."
    res = env.client.put("/api/v1/ai-tune/profile", json={"sections": {"handover": ""}})
    assert res.status_code == 200
    assert env.saved[-1] == "ABOUT US\nWe sell sarees."  # no 8th heading, so no legacy fallback either


def test_put_rejects_when_the_merged_total_passes_700_words(env):
    env.state["description"] = f"{HANDOVER_HEADING}\n" + "word " * 100
    res = env.client.put("/api/v1/ai-tune/profile", json={"sections": {"about": "word " * 601}})
    assert res.status_code == 422 and "700" in res.json()["detail"]
    assert env.saved == []


def test_put_rejects_an_unknown_section_key(env):
    res = env.client.put("/api/v1/ai-tune/profile", json={"sections": {"handover_line": "x"}})
    assert res.status_code == 422 and env.saved == []


def test_put_rejects_a_profile_over_700_words_including_the_new_sections(env):
    res = env.client.put("/api/v1/ai-tune/profile", json={"sections": {
        "about": "word " * 400, "hours_contact": "word " * 200, "handover": "word " * 101}})
    assert res.status_code == 422 and "700" in res.json()["detail"]
    assert env.saved == []
