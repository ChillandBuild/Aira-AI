from unittest.mock import MagicMock, patch

from app.routes import operator
from app.services.ai_reply import FALLBACK_PROMPT


def test_template_routes_exist():
    paths = {route.path for route in operator.router.routes}
    assert "/prompt-template" in paths


def test_get_default_master_prompt_returns_stored_template():
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"value": "STORED TEMPLATE"}
    ]
    with patch.object(operator, "get_supabase", return_value=db):
        assert operator.get_default_master_prompt() == "STORED TEMPLATE"


def test_get_default_master_prompt_falls_back_when_table_unreadable():
    """Client creation must never fail on a template read."""
    db = MagicMock()
    db.table.side_effect = Exception("relation does not exist")
    with patch.object(operator, "get_supabase", return_value=db):
        assert operator.get_default_master_prompt() == FALLBACK_PROMPT


def test_get_default_master_prompt_falls_back_when_row_missing():
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    with patch.object(operator, "get_supabase", return_value=db):
        assert operator.get_default_master_prompt() == FALLBACK_PROMPT
