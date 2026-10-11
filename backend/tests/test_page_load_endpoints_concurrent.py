"""Page-load endpoints must not block each other.

Render runs one uvicorn process, and get_supabase() is the synchronous client:
every .execute() is a blocking network call. Inside an `async def` handler that
call runs on the event loop and freezes the whole server until the database
answers, so the dozen requests a page fires on load (sidebar, counts, list)
queue up one behind another. A plain `def` handler runs in FastAPI's thread
pool instead, so they run side by side. Segments and the Shared Inbox were
slow to load because of exactly this.
"""
import asyncio
import inspect
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from app.main import app
from app.routes import calls, conversations, inbound_leads, leads, segments
from app.dependencies.auth import get_current_user

DB_DELAY = 0.3  # seconds a fake database round trip takes


def _slow_db():
    """A Supabase stand-in whose every query chain ends in a blocking sleep."""
    result = MagicMock(data=[], count=0)

    def execute():
        time.sleep(DB_DELAY)
        return result

    chain = MagicMock()
    for name in ("table", "select", "eq", "neq", "is_", "or_", "in_", "gte", "lt", "lte",
                 "order", "range", "limit", "rpc", "not_", "ilike"):
        getattr(chain, name).return_value = chain
    chain.not_ = chain
    chain.execute.side_effect = execute
    return chain


class PageLoadEndpointsAreConcurrent(unittest.TestCase):
    def setUp(self):
        owner = {"tenant_id": "tenant-1", "role": "owner", "permissions": []}
        app.dependency_overrides[leads.require_leads_view] = lambda: owner
        app.dependency_overrides[conversations.require_conversations_view] = lambda: owner
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    def _time_concurrent(self, paths):
        async def run():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/health")  # first request pays one-off app warm-up; keep it out of the timing
                start = time.perf_counter()
                responses = await asyncio.gather(*(client.get(p) for p in paths))
                return time.perf_counter() - start, responses

        return asyncio.run(run())

    def test_two_lead_lists_load_side_by_side(self):
        with patch("app.routes.leads.get_supabase", side_effect=_slow_db):
            elapsed, responses = self._time_concurrent(["/api/v1/leads/?segment=A", "/api/v1/leads/?segment=B"])
        self.assertTrue(all(r.status_code == 200 for r in responses), [r.status_code for r in responses])
        # Serialized: >= 2 x DB_DELAY. Side by side: about 1 x DB_DELAY.
        self.assertLess(elapsed, DB_DELAY * 1.7, f"requests ran one after another ({elapsed:.2f}s)")

    def test_conversations_and_leads_load_side_by_side(self):
        with patch("app.routes.leads.get_supabase", side_effect=_slow_db), \
             patch("app.routes.conversations.get_supabase", side_effect=_slow_db):
            elapsed, responses = self._time_concurrent(["/api/v1/conversations", "/api/v1/leads/"])
        self.assertTrue(all(r.status_code == 200 for r in responses), [r.status_code for r in responses])
        self.assertLess(elapsed, DB_DELAY * 1.7, f"requests ran one after another ({elapsed:.2f}s)")

    def test_page_load_handlers_are_plain_functions(self):
        """Every handler these pages call on load uses the blocking client, so none may be async."""
        for handler in (leads.list_leads, conversations.list_conversations, inbound_leads.list_campaigns,
                        segments.list_templates, calls.count_call_alerts):
            self.assertFalse(inspect.iscoroutinefunction(handler), f"{handler.__module__}.{handler.__name__} is async")


if __name__ == "__main__":
    unittest.main()
