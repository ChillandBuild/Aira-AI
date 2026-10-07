"""Lead page 'Send details on WhatsApp': free message inside 24h, approved template otherwise."""
import inspect
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.services import call_details_share as share
from tests.fake_supabase import FakeSupabase

UTC = timezone.utc
NOW = datetime(2026, 9, 27, 8, 30, tzinfo=UTC)  # Sunday 14:00 IST
PACKAGES = [
    {"key": "basic", "name": "Basic reading", "amount_paise": 4900, "description": "20 minute call", "active": True},
    {"key": "premium", "name": "Premium", "amount_paise": 0, "active": True, "options": [
        {"key": "k", "name": "Kundli", "amount_paise": 9900, "active": True},
        {"key": "m", "name": "Marriage match", "amount_paise": 14900, "active": True},
    ]},
    {"key": "old", "name": "Old plan", "amount_paise": 100, "active": False},
]
SETTINGS = {"meta_phone_number_id": "pn-1", "meta_access_token": "tok", "meta_waba_id": "waba-1"}
SHARE_BODY = "Hi {{1}}, thanks for calling {{2}}. Details: {{3}}"


class _Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = FakeSupabase()
        self.db.add("leads", id="lead-1", tenant_id="t1", name="Priya Raman", phone="+919800000001", opted_out=False,
                    last_inbound_at=(NOW - timedelta(hours=2)).isoformat())
        self.db.add("tenants", id="t1", name="Astro Tamil")
        self.db.add("call_logs", tenant_id="t1", lead_id="lead-1", outcome="interested_booked",
                    next_action_at="2026-10-02T05:30:00+00:00", created_at="2026-09-27T08:00:00+00:00")
        self.db.add("message_templates", id="tpl-1", tenant_id="t1", name="call_details_share", language="en",
                    body_text=SHARE_BODY, status="APPROVED", meta_waba_id="waba-1", header_media_type=None)
        self.db.add("message_templates", id="tpl-2", tenant_id="t1", name="promo", language="en", body_text="Hi {{1}} {{2}}",
                    status="APPROVED", meta_waba_id="waba-1", header_media_type=None)
        self.db.add("message_templates", id="tpl-3", tenant_id="t1", name="pending_one", language="en", body_text="x",
                    status="PENDING", meta_waba_id="waba-1", header_media_type=None)
        self.db.add("message_templates", id="tpl-4", tenant_id="t1", name="old_waba", language="en", body_text="x",
                    status="APPROVED", meta_waba_id="waba-0", header_media_type=None)
        self.db.add("message_templates", id="tpl-5", tenant_id="t1", name="with_image", language="en", body_text="x",
                    status="APPROVED", meta_waba_id="waba-1", header_media_type="IMAGE")
        self.settings = dict(SETTINGS)
        self.send_text = AsyncMock(return_value="wamid.1")
        self.send_template = AsyncMock(return_value={"messages": [{"id": "wamid.2"}]})
        for target, value in (
            ("get_setting", lambda key, tenant_id=None: self.settings.get(key)),
            ("get_intake_config", lambda tenant_id, db=None: {"packages": PACKAGES}),
            ("send_whatsapp", self.send_text),
            ("send_template_message", self.send_template),
            ("get_last_send_error", lambda: "(#131047) Re-engagement message"),
        ):
            patcher = patch.object(share, target, side_effect=value) if callable(value) and not isinstance(value, AsyncMock) else patch.object(share, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def lead(self):
        return self.db.rows("leads")[0]


class TextTests(unittest.TestCase):
    def test_services_text_nests_options_and_skips_inactive(self):
        self.assertEqual(share.services_text(PACKAGES),
                         "• Basic reading — ₹49\n  20 minute call\n• Premium\n  • Kundli — ₹99\n  • Marriage match — ₹149")

    def test_one_line_for_templates(self):
        self.assertEqual(share.services_one_line(PACKAGES), "Basic reading ₹49; Premium (Kundli ₹99; Marriage match ₹149)")

    def test_render_template_leaves_unfilled_blanks(self):
        self.assertEqual(share.render_template("Hi {{1}}, {{2}}", ["Priya"]), "Hi Priya, {{2}}")


class ContextTests(_Base):
    async def test_free_message_inside_the_window(self):
        ctx = share.share_context(self.db, "t1", "lead-1", now=NOW)
        self.assertTrue(ctx["available"])
        self.assertTrue(ctx["window_open"])
        self.assertEqual(ctx["free_text"], (
            "Hi Priya, thank you for your time on the call today.\n\n"
            "Here are the details from Astro Tamil:\n\n"
            "• Basic reading — ₹49\n  20 minute call\n• Premium\n  • Kundli — ₹99\n  • Marriage match — ₹149\n\n"
            "Next step on Friday at 11 AM."
        ))

    async def test_only_approved_text_templates_on_the_current_number(self):
        ctx = share.share_context(self.db, "t1", "lead-1", now=NOW)
        self.assertEqual([t["name"] for t in ctx["templates"]], ["call_details_share", "promo"])
        self.assertEqual(ctx["templates"][0]["variables"], [
            {"key": "1", "role": "customer_name", "value": "Priya Raman"},
            {"key": "2", "role": "business_name", "value": "Astro Tamil"},
            {"key": "3", "role": "details", "value": "Basic reading ₹49; Premium (Kundli ₹99; Marriage match ₹149)"},
        ])
        self.assertEqual(ctx["templates"][1]["variables"], [
            {"key": "1", "role": None, "value": ""}, {"key": "2", "role": None, "value": ""},
        ])

    async def test_window_closed_after_24_hours(self):
        self.lead()["last_inbound_at"] = (NOW - timedelta(hours=25)).isoformat()
        self.assertFalse(share.share_context(self.db, "t1", "lead-1", now=NOW)["window_open"])

    async def test_hidden_without_whatsapp_or_for_opted_out_leads(self):
        self.settings.pop("meta_access_token")
        self.assertEqual(share.share_context(self.db, "t1", "lead-1", now=NOW), {"available": False})
        self.settings["meta_access_token"] = "tok"
        self.lead()["opted_out"] = True
        self.assertEqual(share.share_context(self.db, "t1", "lead-1", now=NOW), {"available": False})

    async def test_unknown_lead(self):
        self.assertIsNone(share.share_context(self.db, "t1", "nope", now=NOW))

    async def test_soft_deleted_lead_is_treated_as_not_found(self):
        self.lead()["deleted_at"] = NOW.isoformat()
        self.assertIsNone(share.share_context(self.db, "t1", "lead-1", now=NOW))

    async def test_independent_reads_run_at_the_same_time(self):
        # Each read is a Render -> Supabase round trip; one after another they made the
        # card appear ~1 s after the lead opened. Four 0.2 s reads must overlap.
        def slow(original):
            def run(*args, **kwargs):
                time.sleep(0.2)
                return original(*args, **kwargs)
            return run

        patches = [patch.object(share, name, side_effect=slow(getattr(share, name)))
                   for name in ("get_intake_config", "_business_name", "_next_step", "_approved_templates")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        started = time.monotonic()
        ctx = share.share_context(self.db, "t1", "lead-1", now=NOW)
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual([t["name"] for t in ctx["templates"]], ["call_details_share", "promo"])
        self.assertIn("Astro Tamil", ctx["free_text"])

    def test_route_does_not_block_the_event_loop(self):
        # share_context does blocking database reads; a plain `def` route runs in
        # FastAPI's thread pool instead of stalling every other request meanwhile.
        from app.routes.lead_details_share import get_send_details
        self.assertFalse(inspect.iscoroutinefunction(get_send_details))


class SendTests(_Base):
    async def test_free_text_goes_out_and_lands_in_conversations(self):
        row = await share.send_details(self.db, "t1", "lead-1", text=" Hello ", template_id=None, variables=[], now=NOW)
        self.send_text.assert_awaited_once_with("+919800000001", "Hello", tenant_id="t1")
        self.assertEqual((row["content"], row["meta_message_id"], row["direction"], row["channel"], row["is_ai_generated"]),
                         ("Hello", "wamid.1", "outbound", "whatsapp", False))

    async def test_free_text_outside_the_window_is_refused(self):
        self.lead()["last_inbound_at"] = (NOW - timedelta(days=2)).isoformat()
        with self.assertRaises(share.ShareError) as err:
            await share.send_details(self.db, "t1", "lead-1", text="Hello", template_id=None, variables=[], now=NOW)
        self.assertIn("send a template instead", str(err.exception))
        self.send_text.assert_not_awaited()

    async def test_template_variables_are_flattened_to_one_line(self):
        row = await share.send_details(self.db, "t1", "lead-1", text=None, template_id="tpl-1",
                                       variables=["Priya", "Astro Tamil", "Basic ₹49\n  Premium ₹99"], now=NOW)
        components = self.send_template.await_args.kwargs["components"]
        self.assertEqual([p["text"] for p in components[0]["parameters"]], ["Priya", "Astro Tamil", "Basic ₹49 Premium ₹99"])
        self.assertEqual(self.send_template.await_args.args, ("+919800000001", "call_details_share", "en"))
        self.assertEqual(row["content"], "Hi Priya, thanks for calling Astro Tamil. Details: Basic ₹49 Premium ₹99")
        self.assertEqual(row["meta_message_id"], "wamid.2")

    async def test_every_blank_must_be_filled(self):
        with self.assertRaises(share.ShareError) as err:
            await share.send_details(self.db, "t1", "lead-1", text=None, template_id="tpl-2", variables=["Priya", "  "], now=NOW)
        self.assertEqual(str(err.exception), "Fill every blank in the template.")

    async def test_unapproved_template_is_refused(self):
        with self.assertRaises(share.ShareError):
            await share.send_details(self.db, "t1", "lead-1", text=None, template_id="tpl-3", variables=[], now=NOW)

    async def test_meta_errors_are_reported(self):
        self.send_template.side_effect = HTTPException(status_code=400, detail="(#132000) param count mismatch")
        with self.assertRaises(share.ShareError) as err:
            await share.send_details(self.db, "t1", "lead-1", text=None, template_id="tpl-2", variables=["a", "b"], now=NOW)
        self.assertIn("WhatsApp didn't send it", str(err.exception))

    async def test_failed_free_text_reports_metas_reason(self):
        self.send_text.return_value = None
        with self.assertRaises(share.ShareError) as err:
            await share.send_details(self.db, "t1", "lead-1", text="Hello", template_id=None, variables=[], now=NOW)
        self.assertIn("131047", str(err.exception))
        self.assertEqual(self.db.rows("messages"), [])


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1"}
        self.as_perms(["telecalling.dialer"])

    def tearDown(self):
        app.dependency_overrides.clear()

    def as_perms(self, perms):
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t1", "role": "caller", "user_id": "u1", "caller_id": "c1", "permissions": perms,
        }

    def test_telecallers_without_dialer_or_reply_are_refused(self):
        self.as_perms(["leads.view"])
        self.assertEqual(self.client.get("/api/v1/leads/11111111-2222-3333-4444-555555555555/send-details").status_code, 403)

    def test_get_returns_the_context(self):
        with patch("app.routes.lead_details_share.get_supabase"), \
             patch("app.routes.lead_details_share.share_context", return_value={"available": False}):
            res = self.client.get("/api/v1/leads/11111111-2222-3333-4444-555555555555/send-details")
        self.assertEqual(res.json(), {"available": False})

    def test_post_needs_exactly_one_of_text_or_template(self):
        res = self.client.post("/api/v1/leads/11111111-2222-3333-4444-555555555555/send-details",
                               json={"text": "hi", "template_id": "tpl-1"})
        self.assertEqual(res.status_code, 400)

    def test_share_errors_are_400s(self):
        with patch("app.routes.lead_details_share.get_supabase"), \
             patch("app.routes.lead_details_share.send_details", AsyncMock(side_effect=share.ShareError("Fill every blank in the template."))):
            res = self.client.post("/api/v1/leads/11111111-2222-3333-4444-555555555555/send-details",
                                   json={"template_id": "tpl-1", "variables": [""]})
        self.assertEqual((res.status_code, res.json()["detail"]), (400, "Fill every blank in the template."))


if __name__ == "__main__":
    unittest.main()
