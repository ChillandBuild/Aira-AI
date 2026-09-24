"""Shared fixtures for the knowledge auto-sort service tests: an in-memory database,
in-memory settings, and a scripted stand-in for the model that dispatches on which
prompt it was called with."""
import re
from types import SimpleNamespace

import pytest

from app.services import knowledge_sort as ks
from app.services import knowledge_versions as kv
from fake_supabase import FakeSupabase

T = "tenant-1"


@pytest.fixture
def env(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(kv, "get_setting", lambda key, fallback=None, tenant_id=None: store.get((tenant_id, key), fallback))
    monkeypatch.setattr(kv, "save_setting", lambda key, value, tenant_id=None: store.__setitem__((tenant_id, key), value))
    monkeypatch.setattr(kv, "invalidate_cache", lambda key=None: None)
    db = FakeSupabase()

    def set_description(text: str):
        store[(T, "business_description")] = text

    def description() -> str:
        return store.get((T, "business_description"), "")

    return SimpleNamespace(db=db, store=store, set_description=set_description, description=description)


def section_ids(user_text: str) -> list[str]:
    return re.findall(r"<<(s\d+)>>", user_text)


def fake_model(monkeypatch, *, labels, compiled=None, disagreements=None, handover=""):
    """labels: callable(section_id, section_text) -> (label, facts) for each section.
    compiled: dict returned for the compile prompt (default: current + rules joined,
    plus `handover` if given -- unused when `compiled` is passed explicitly).
    Returns the list of prompts called, for asserting which steps ran."""
    calls: list[str] = []

    async def _fake(system, user, *, tenant_id, max_tokens):
        if system is ks._LABEL_SYSTEM:
            calls.append("label")
            out = []
            for sid, text in re.findall(r"<<(s\d+)>>\n(.*?)(?=\n\n<<s\d+>>|\Z)", user, flags=re.S):
                label, facts = labels(sid, text)
                if label is not None:
                    out.append({"id": sid, "label": label, "facts": facts, "note": ""})
            return {"sections": out}
        if system is ks._COMPILE_SYSTEM:
            calls.append("compile")
            if compiled is not None:
                return compiled
            current = user.split("CURRENT DESCRIPTION:\n", 1)[1].split("\n\nNEW RULES:", 1)[0]
            current = "" if current == "(empty)" else current
            rules = user.split("NEW RULES:\n", 1)[1]
            return {"description": (current + "\n" + rules).strip(), "conflicts": [], "handover": handover}
        if system is ks._DISAGREE_SYSTEM:
            calls.append("disagree")
            return {"disagreements": disagreements or []}
        if system is ks._CONDENSE_SYSTEM:
            calls.append("condense")
            return {"text": user.split("TEXT:\n", 1)[1]}
        raise AssertionError("unexpected prompt")

    monkeypatch.setattr(ks, "_llm_json", _fake)
    return calls


def add_doc(db, **row) -> dict:
    return db.add("knowledge_documents", **{"tenant_id": T, "name": "doc.txt", **row})
