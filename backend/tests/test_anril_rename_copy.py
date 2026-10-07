"""Aira -> Anril rename: customer-visible backend text says Anril.

Behavioural where the code is easy to drive; for the error details that sit deep in
big route handlers, the string literals of the module are scanned instead (comments and
docstrings are ignored, so only text that can reach a customer is checked)."""
import ast
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

APP = Path(__file__).resolve().parents[1] / "app"


def _literals(relative: str) -> list[str]:
    tree = ast.parse((APP / relative).read_text())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant):
                docstrings.add(id(first.value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]


@pytest.mark.parametrize("module,old,new", [
    ("routes/app_settings.py", "already connected to another Aira workspace", "already connected to another Anril workspace"),
    ("routes/app_settings.py", "grant the Page to Aira", "grant the Page to Anril"),
    ("routes/templates.py", "contact Aira support", "contact Anril support"),
    ("routes/subscriptions.py", "set up by your Aira contact", "set up by your Anril contact"),
])
def test_customer_error_details_say_anril(module, old, new):
    texts = _literals(module)
    assert not any(old in t for t in texts), old
    assert any(new in t for t in texts), new


def test_operator_temp_password_uses_the_anril_prefix():
    from app.routes import operator
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        MagicMock(data={"user_id": "u-1"})
    )
    with patch.object(operator, "get_supabase", return_value=db), patch.object(operator, "record_audit_event"):
        import asyncio
        asyncio.run(operator.reset_password("t-1", _admin={"user_id": "admin-1"}))
    password = db.auth.admin.update_user_by_id.call_args.args[1]["password"]
    assert password.startswith("Anril@") and len(password) > len("Anril@") + 8


def test_the_escalation_link_points_at_the_anril_dashboard():
    from app.services import whatsapp_notify
    texts = _literals("services/whatsapp_notify.py") + _literals("services/template_fields.py")
    assert not any("aira.ai" in t for t in texts)
    assert sum("https://www.bloommatrix.in/anril/dashboard/conversations?lead_id=" in t for t in texts) == 1


def test_the_service_names_say_anril():
    texts = _literals("main.py")
    assert "Anril AI" in texts and "anril-ai" in texts
    assert "Aira AI" not in texts and "aira-ai" not in texts
    assert "Anril AI backend starting up..." in texts and "Anril AI backend shutting down." in texts


# Old names that must keep working for values customers or partners already hold.
_LEGACY_OK = ("X-Aira-", "Aira Business Kit", "|Aira) Business Kit", "Aira told the customer it is checking")


def test_no_string_literal_in_the_backend_says_aira():
    import re
    word = re.compile(r"\bAira\b")
    hits = []
    for path in sorted(APP.rglob("*.py")):
        relative = str(path.relative_to(APP))
        for text in _literals(relative):
            if word.search(text) and not any(ok in text for ok in _LEGACY_OK):
                hits.append(f"{relative}: {text[:70]}")
    assert hits == []


def test_handovers_saved_with_the_old_aira_wording_still_classify():
    from app.services.brain import handovers
    from app.services.deal_turn import TEAM_CLAIM_REASON
    assert "Anril" in TEAM_CLAIM_REASON
    assert handovers.classify_reason(TEAM_CLAIM_REASON) == handovers.KIND_KNOWLEDGE_GAP
    assert handovers.classify_reason("Aira told the customer it is checking with the team") == handovers.KIND_KNOWLEDGE_GAP
