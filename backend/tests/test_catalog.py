import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_id, get_tenant_and_role


class CatalogItemsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_id] = lambda: "tenant-1"
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.catalog.get_supabase")
    def test_list_items_returns_data(self, mock_get_db):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
            {"id": "item-1", "name": "Chocolate Cake", "item_type": "product", "status": "ready"}
        ]
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/catalog/items")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["data"][0]["name"], "Chocolate Cake")

    @patch("app.routes.catalog.get_supabase")
    def test_create_item_defaults_to_draft_status(self, mock_get_db):
        db = MagicMock()
        db.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "item-1", "name": "New Item", "item_type": "product", "status": "draft"}
        ]
        mock_get_db.return_value = db

        res = self.client.post("/api/v1/catalog/items", json={"name": "New Item", "item_type": "product"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "draft")
        insert_call = db.table.return_value.insert.call_args[0][0]
        self.assertEqual(insert_call["tenant_id"], "tenant-1")
        self.assertEqual(insert_call["status"], "draft")

    @patch("app.routes.catalog.get_supabase")
    def test_update_item_rejects_invalid_status(self, mock_get_db):
        db = MagicMock()
        mock_get_db.return_value = db

        res = self.client.patch("/api/v1/catalog/items/11111111-1111-1111-1111-111111111111", json={"status": "archived"})
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.catalog.get_supabase")
    def test_update_item_not_found_for_wrong_tenant_returns_404(self, mock_get_db):
        db = MagicMock()
        db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        mock_get_db.return_value = db

        res = self.client.patch("/api/v1/catalog/items/11111111-1111-1111-1111-111111111111", json={"name": "Renamed"})
        self.assertEqual(res.status_code, 404)

    @patch("app.routes.catalog.get_supabase")
    def test_delete_item_not_found_returns_404(self, mock_get_db):
        db = MagicMock()
        db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        mock_get_db.return_value = db

        res = self.client.delete("/api/v1/catalog/items/11111111-1111-1111-1111-111111111111")
        self.assertEqual(res.status_code, 404)

    @patch("app.routes.catalog.get_supabase")
    def test_delete_item_success(self, mock_get_db):
        db = MagicMock()
        db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "item-1"}]
        mock_get_db.return_value = db

        res = self.client.delete("/api/v1/catalog/items/11111111-1111-1111-1111-111111111111")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])


class CatalogMediaTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_id] = lambda: "tenant-1"
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.catalog.get_supabase")
    def test_upload_media_returns_404_when_item_not_found(self, mock_get_db):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        mock_get_db.return_value = db

        res = self.client.post(
            "/api/v1/catalog/items/11111111-1111-1111-1111-111111111111/media",
            files={"file": ("photo.jpg", b"fake-bytes", "image/jpeg")},
        )
        self.assertEqual(res.status_code, 404)

    @patch("app.routes.catalog.get_supabase")
    def test_upload_media_success_returns_url(self, mock_get_db):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "catalog_items":
                tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"id": "item-1"}]
            elif name == "catalog_media":
                tbl.insert.return_value.execute.return_value.data = [
                    {"id": "media-1", "catalog_item_id": "item-1", "storage_path": "tenant-1/item-1/x_photo.jpg", "label": "photo.jpg"}
                ]
            return tbl

        db.table.side_effect = table
        db.storage.from_.return_value.get_public_url.return_value = "https://storage.example/photo.jpg"
        mock_get_db.return_value = db

        res = self.client.post(
            "/api/v1/catalog/items/11111111-1111-1111-1111-111111111111/media",
            files={"file": ("photo.jpg", b"fake-bytes", "image/jpeg")},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["url"], "https://storage.example/photo.jpg")
        db.storage.from_.return_value.upload.assert_called_once()

    @patch("app.routes.catalog.get_supabase")
    def test_list_media_joins_item_names(self, mock_get_db):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "catalog_media":
                tbl.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
                    {"id": "media-1", "catalog_item_id": "item-1", "storage_path": "path/a.jpg", "label": "a.jpg"}
                ]
            elif name == "catalog_items":
                tbl.select.return_value.in_.return_value.execute.return_value.data = [{"id": "item-1", "name": "Chocolate Cake"}]
            return tbl

        db.table.side_effect = table
        db.storage.from_.return_value.get_public_url.return_value = "https://storage.example/a.jpg"
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/catalog/media")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["data"][0]["item_name"], "Chocolate Cake")


class CatalogAiRulesTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_id] = lambda: "tenant-1"
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.catalog.get_supabase")
    def test_get_ai_rules_returns_defaults_when_no_row_exists(self, mock_get_db):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/catalog/ai-rules")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"can_recommend": True, "can_send_images": True, "max_images_per_reply": 3})

    @patch("app.routes.catalog.get_supabase")
    def test_patch_ai_rules_merges_partial_update(self, mock_get_db):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"value": json.dumps({"can_recommend": True, "can_send_images": True, "max_images_per_reply": 3})}
        ]
        mock_get_db.return_value = db

        res = self.client.patch("/api/v1/catalog/ai-rules", json={"can_send_images": False})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"can_recommend": True, "can_send_images": False, "max_images_per_reply": 3})

        upsert_call = db.table.return_value.upsert.call_args[0][0]
        self.assertEqual(json.loads(upsert_call["value"])["can_send_images"], False)


class CatalogAiReplyIntegrationTests(unittest.TestCase):
    """Tests for _build_catalog_context and _load_catalog_ai_rules in ai_reply.py."""

    def test_build_catalog_context_returns_empty_when_can_recommend_is_false(self):
        from app.services.ai_reply import _build_catalog_context
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"value": json.dumps({"can_recommend": False})}
        ]

        text, tools, items_by_id = _build_catalog_context(db, "tenant-1")
        self.assertEqual(text, "")
        self.assertEqual(tools, [])
        self.assertEqual(items_by_id, {})

    def test_build_catalog_context_returns_empty_when_no_items(self):
        from app.services.ai_reply import _build_catalog_context
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "app_settings":
                tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
            elif name == "catalog_items":
                tbl.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = []
            return tbl

        db.table.side_effect = table

        text, tools, items_by_id = _build_catalog_context(db, "tenant-1")
        self.assertEqual(text, "")
        self.assertEqual(tools, [])
        self.assertEqual(items_by_id, {})

    def test_build_catalog_context_builds_text_and_tools_for_ready_items(self):
        from app.services.ai_reply import _build_catalog_context
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "app_settings":
                tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
            elif name == "catalog_items":
                tbl.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = [
                    {"id": "item-1", "name": "Chocolate Cake", "item_type": "product", "description": "Rich dark chocolate cake"}
                ]
            return tbl

        db.table.side_effect = table

        text, tools, items_by_id = _build_catalog_context(db, "tenant-1")
        self.assertIn("Chocolate Cake", text)
        self.assertIn("item-1", text)
        self.assertIn("Rich dark chocolate cake", text)
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["function"]["name"], "recommend_catalog_item")
        self.assertEqual(items_by_id["item-1"]["name"], "Chocolate Cake")

    def test_load_catalog_ai_rules_merges_with_defaults(self):
        from app.services.ai_reply import _load_catalog_ai_rules
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"value": json.dumps({"can_recommend": False})}
        ]

        rules = _load_catalog_ai_rules(db, "tenant-1")
        self.assertFalse(rules["can_recommend"])
        self.assertTrue(rules["can_send_images"])  # from defaults
        self.assertEqual(rules["max_images_per_reply"], 3)  # from defaults

    def test_generate_reply_static_import_scopes(self):
        import inspect
        from app.services import ai_reply

        source = inspect.getsource(ai_reply.generate_reply)
        assert "_build_catalog_context" in source
        assert "sarvam_chat_completion_with_tools" in source
        assert "catalog_images_to_send" in source


if __name__ == "__main__":
    unittest.main()
