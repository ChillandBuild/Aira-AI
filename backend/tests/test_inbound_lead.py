"""Tests for create_inbound_lead(), the single-enquiry lead intake path used
by the marketplace webhooks (IndiaMART, JustDial). Covers the three things
that matter for a webhook that can be called more than once for the same
enquiry: dedupe on (tenant_id, phone), reviving a soft-deleted lead instead
of duplicating it, and phone normalisation. maybe_assign_lead and
sync_follow_up_jobs are patched to no-ops -- their own behaviour is exercised
by their own tests; this file is about create_inbound_lead's own orchestration.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.fake_supabase import FakeSupabase
from app.services.inbound_lead import create_inbound_lead

TENANT_ID = "11111111-1111-1111-1111-111111111111"


class TestCreateInboundLead(unittest.TestCase):
    def setUp(self):
        self.db = FakeSupabase()
        self.patches = [
            patch("app.services.assignment.maybe_assign_lead", return_value=None),
            patch("app.services.inbound_lead.sync_follow_up_jobs", return_value=[]),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_new_phone_creates_one_lead_with_source_and_event(self):
        lead_id = create_inbound_lead(TENANT_ID, "9876543210", "indiamart", db=self.db)

        leads = self.db.rows("leads")
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["id"], lead_id)
        self.assertEqual(leads[0]["phone"], "+919876543210")
        self.assertEqual(leads[0]["source"], "indiamart")
        self.assertEqual(leads[0]["tenant_id"], TENANT_ID)

        events = self.db.rows("lead_stage_events")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "created")
        self.assertEqual(events[0]["metadata"]["source"], "indiamart")

    def test_same_phone_twice_creates_one_lead_not_two(self):
        first_id = create_inbound_lead(TENANT_ID, "9876543210", "indiamart", db=self.db)
        second_id = create_inbound_lead(TENANT_ID, "9876543210", "justdial", db=self.db)

        self.assertEqual(first_id, second_id)
        self.assertEqual(len(self.db.rows("leads")), 1)
        # Second call found the lead and returned early -- source is NOT
        # overwritten to the second provider.
        self.assertEqual(self.db.rows("leads")[0]["source"], "indiamart")

    def test_soft_deleted_lead_is_revived_not_duplicated(self):
        lead_id = create_inbound_lead(TENANT_ID, "9876543210", "indiamart", db=self.db)
        self.db.table("leads").update({"deleted_at": "2026-01-01T00:00:00"}).eq("id", lead_id).execute()

        revived_id = create_inbound_lead(TENANT_ID, "9876543210", "justdial", db=self.db)

        self.assertEqual(revived_id, lead_id)
        self.assertEqual(len(self.db.rows("leads")), 1)
        self.assertIsNone(self.db.rows("leads")[0]["deleted_at"])

    def test_ten_digit_number_starting_nine_gets_91_prefixed(self):
        create_inbound_lead(TENANT_ID, "9876543210", "indiamart", db=self.db)
        self.assertEqual(self.db.rows("leads")[0]["phone"], "+919876543210")

    def test_unusable_phone_returns_none_and_creates_nothing(self):
        lead_id = create_inbound_lead(TENANT_ID, "123", "indiamart", db=self.db)
        self.assertIsNone(lead_id)
        self.assertEqual(len(self.db.rows("leads")), 0)

    def test_different_tenants_same_phone_get_separate_leads(self):
        other_tenant = "22222222-2222-2222-2222-222222222222"
        id_a = create_inbound_lead(TENANT_ID, "9876543210", "indiamart", db=self.db)
        id_b = create_inbound_lead(other_tenant, "9876543210", "indiamart", db=self.db)

        self.assertNotEqual(id_a, id_b)
        self.assertEqual(len(self.db.rows("leads")), 2)


if __name__ == "__main__":
    unittest.main()
