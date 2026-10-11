"""Conversations 'Share product': photo + name + price to a WhatsApp lead, inside the 24h window."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.routes import leads as leads_route
from app.services import share_product as sp
from tests.fake_supabase import FakeSupabase

NOW = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)


class ShareProductTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        db = self.db = FakeSupabase()
        db.add("leads", id="l1", tenant_id="t1", phone="+919800000001", source="whatsapp", opted_out=False,
               deleted_at=None, last_inbound_at=(NOW - timedelta(hours=2)).isoformat())
        db.add("catalog_items", id="p1", tenant_id="t1", name="Marriage match", price_paise=14900,
               price_note="per couple", description="Detailed porutham report")
        db.add("catalog_items", id="p2", tenant_id="t1", name="Basic reading", price_paise=4950, description=None)
        db.add("catalog_items", id="px", tenant_id="t2", name="Other business", price_paise=100)
        db.add("catalog_media", catalog_item_id="p1", tenant_id="t1", storage_path="t1/p1.jpg", sort_order=0)
        db.storage.from_.return_value.get_public_url.return_value = "https://cdn.example/t1/p1.jpg"
        self.media = AsyncMock(return_value={"messages": [{"id": "wamid.img"}]})
        self.text = AsyncMock(return_value="wamid.txt")
        for target, value in (("send_media_message", self.media), ("send_whatsapp", self.text)):
            p = patch.object(sp, target, value)
            p.start()
            self.addCleanup(p.stop)

    async def test_photo_goes_out_with_name_and_price(self):
        row = await sp.share_product(self.db, "t1", "l1", "p1", now=NOW)
        kwargs = self.media.await_args.kwargs
        self.assertEqual((kwargs["to_number"], kwargs["media_link"], kwargs["wa_type"]),
                         ("+919800000001", "https://cdn.example/t1/p1.jpg", "image"))
        self.assertEqual(kwargs["caption"], "Marriage match\n₹149 (per couple)\n\nDetailed porutham report")
        self.assertEqual((row["content"], row["meta_message_id"], row["media_type"], row["is_ai_generated"]),
                         (kwargs["caption"], "wamid.img", "image", False))

    async def test_item_without_photo_goes_as_text(self):
        await sp.share_product(self.db, "t1", "l1", "p2", now=NOW)
        self.text.assert_awaited_once_with("+919800000001", "Basic reading\n₹49.50", tenant_id="t1")
        self.media.assert_not_awaited()

    async def test_outside_the_window_is_refused(self):
        self.db.rows("leads")[0]["last_inbound_at"] = (NOW - timedelta(days=2)).isoformat()
        with self.assertRaises(sp.ShareProductError) as err:
            await sp.share_product(self.db, "t1", "l1", "p1", now=NOW)
        self.assertIn("template", str(err.exception))
        self.media.assert_not_awaited()

    async def test_instagram_leads_and_other_businesses_products_are_refused(self):
        self.db.rows("leads")[0]["source"] = "instagram"
        with self.assertRaises(sp.ShareProductError):
            await sp.share_product(self.db, "t1", "l1", "p1", now=NOW)
        self.db.rows("leads")[0]["source"] = "whatsapp"
        with self.assertRaises(sp.ShareProductError):
            await sp.share_product(self.db, "t1", "l1", "px", now=NOW)
        self.media.assert_not_awaited()


class ShareProductRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1"}

    def tearDown(self):
        app.dependency_overrides.clear()

    def as_perms(self, perms):
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t1", "role": "caller", "user_id": "u1", "permissions": perms,
        }

    def test_needs_reply_permission(self):
        self.as_perms(["conversations.view"])
        res = self.client.post("/api/v1/leads/11111111-2222-3333-4444-555555555555/share-product", json={"item_id": "p1"})
        self.assertEqual(res.status_code, 403)

    def test_errors_come_back_as_400(self):
        self.as_perms(["conversations.reply"])
        with patch.object(leads_route, "get_supabase", return_value=MagicMock()), \
             patch.object(leads_route, "share_product", AsyncMock(side_effect=sp.ShareProductError("Product not found."))):
            res = self.client.post("/api/v1/leads/11111111-2222-3333-4444-555555555555/share-product", json={"item_id": "p1"})
        self.assertEqual((res.status_code, res.json()["detail"]), (400, "Product not found."))


if __name__ == "__main__":
    unittest.main()
