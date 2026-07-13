import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.catalog_retrieval import (
    contention_set,
    classify_gate,
    differing_attribute_directive,
    broad_browse_directive,
)


class ContentionSetTests(unittest.TestCase):
    def test_empty_candidates_returns_empty(self):
        self.assertEqual(contention_set([]), [])

    def test_single_candidate_is_its_own_contention_set(self):
        candidates = [{"id": "a", "similarity": 0.9}]
        self.assertEqual(contention_set(candidates), candidates)

    def test_confident_top_match_excludes_far_second(self):
        candidates = [
            {"id": "a", "similarity": 0.91},
            {"id": "b", "similarity": 0.60},
        ]
        self.assertEqual(contention_set(candidates), [candidates[0]])

    def test_close_scores_are_all_in_contention(self):
        candidates = [
            {"id": "a", "similarity": 0.83},
            {"id": "b", "similarity": 0.82},
            {"id": "c", "similarity": 0.81},
            {"id": "d", "similarity": 0.55},
        ]
        self.assertEqual(contention_set(candidates), candidates[:3])


class ClassifyGateTests(unittest.TestCase):
    def test_single_item_is_confident(self):
        self.assertEqual(classify_gate([{"id": "a", "variant_group_id": None}]), "confident")

    def test_shared_variant_group_is_same_group(self):
        contention = [
            {"id": "a", "variant_group_id": "vg-1"},
            {"id": "b", "variant_group_id": "vg-1"},
        ]
        self.assertEqual(classify_gate(contention), "same_group")

    def test_ungrouped_items_are_confident_on_top_candidate(self):
        contention = [
            {"id": "a", "variant_group_id": None},
            {"id": "b", "variant_group_id": None},
        ]
        self.assertEqual(classify_gate(contention), "confident")

    def test_different_variant_groups_are_broad_browse(self):
        contention = [
            {"id": "a", "variant_group_id": "vg-1"},
            {"id": "b", "variant_group_id": "vg-2"},
        ]
        self.assertEqual(classify_gate(contention), "broad_browse")


class DifferingAttributeDirectiveTests(unittest.TestCase):
    def test_names_differing_locations(self):
        contention = [
            {"id": "a", "name": "2BHK Apartment", "attributes": {"location": "Coimbatore"}},
            {"id": "b", "name": "2BHK Apartment", "attributes": {"location": "Chennai"}},
            {"id": "c", "name": "2BHK Apartment", "attributes": {"location": "Salem"}},
        ]
        directive = differing_attribute_directive(contention)
        self.assertIn("location: Chennai, Coimbatore, Salem", directive)
        self.assertIn("Do NOT call recommend_catalog_item", directive)

    def test_no_shared_attribute_key_still_produces_a_directive(self):
        contention = [
            {"id": "a", "name": "Chocolate Cake", "attributes": {}},
            {"id": "b", "name": "Chocolate Cake", "attributes": {}},
        ]
        directive = differing_attribute_directive(contention)
        self.assertIn("Chocolate Cake", directive)
        self.assertIn("Do NOT call recommend_catalog_item", directive)


class BroadBrowseDirectiveTests(unittest.TestCase):
    def test_lists_distinct_item_names(self):
        contention = [
            {"id": "a", "name": "Chocolate Cake"},
            {"id": "b", "name": "Red Velvet Cake"},
        ]
        directive = broad_browse_directive(contention)
        self.assertIn("Chocolate Cake", directive)
        self.assertIn("Red Velvet Cake", directive)
        self.assertIn("do NOT send any photos", directive)


class BuildEmbeddingTextTests(unittest.TestCase):
    def test_combines_name_type_description_and_attributes(self):
        from app.services.catalog_retrieval import build_catalog_item_embedding_text

        text = build_catalog_item_embedding_text(
            "2BHK Apartment", "property", "Spacious flat", {"location": "Coimbatore"}
        )
        self.assertIn("2BHK Apartment", text)
        self.assertIn("property", text)
        self.assertIn("Spacious flat", text)
        self.assertIn("location: Coimbatore", text)

    def test_skips_missing_description(self):
        from app.services.catalog_retrieval import build_catalog_item_embedding_text

        text = build_catalog_item_embedding_text("Item", "product", None, {})
        self.assertEqual(text, "Item | product")


class EmbedAndStoreCatalogItemTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.embeddings.embed_texts")
    async def test_stores_embedding_via_rpc(self, mock_embed_texts):
        from app.services.catalog_retrieval import embed_and_store_catalog_item

        mock_embed_texts.return_value = [[0.1, 0.2, 0.3]]
        db = MagicMock()

        await embed_and_store_catalog_item(
            db, "tenant-1", "item-1", "Chocolate Cake", "product", "Rich cake", {}
        )

        db.rpc.assert_called_once()
        rpc_name, rpc_args = db.rpc.call_args[0]
        self.assertEqual(rpc_name, "update_catalog_item_embedding")
        self.assertEqual(rpc_args["p_item_id"], "item-1")
        self.assertEqual(rpc_args["p_tenant_id"], "tenant-1")
        self.assertIn("0.1", rpc_args["p_embedding"])

    @patch("app.services.embeddings.embed_texts", return_value=[])
    async def test_no_vectors_returned_is_a_noop(self, mock_embed_texts):
        from app.services.catalog_retrieval import embed_and_store_catalog_item

        db = MagicMock()
        await embed_and_store_catalog_item(db, "tenant-1", "item-1", "Item", "product", None, {})
        db.rpc.assert_not_called()


class MatchCatalogItemsTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.embeddings.embed_query")
    async def test_returns_rpc_rows(self, mock_embed_query):
        from app.services.catalog_retrieval import match_catalog_items

        mock_embed_query.return_value = [0.1, 0.2]
        db = MagicMock()
        db.rpc.return_value.execute.return_value.data = [
            {"id": "item-1", "name": "2BHK Coimbatore", "similarity": 0.83}
        ]

        rows = await match_catalog_items(db, "tenant-1", "2bhk apartment photos")

        self.assertEqual(rows[0]["id"], "item-1")
        rpc_name, rpc_args = db.rpc.call_args[0]
        self.assertEqual(rpc_name, "match_catalog_items")
        self.assertEqual(rpc_args["p_tenant_id"], "tenant-1")

    @patch("app.services.embeddings.embed_query")
    async def test_no_rows_returns_empty_list(self, mock_embed_query):
        from app.services.catalog_retrieval import match_catalog_items

        mock_embed_query.return_value = [0.1, 0.2]
        db = MagicMock()
        db.rpc.return_value.execute.return_value.data = None

        rows = await match_catalog_items(db, "tenant-1", "anything")
        self.assertEqual(rows, [])


class ReindexCatalogItemsTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.catalog_retrieval.embed_and_store_catalog_item")
    @patch("app.services.catalog_retrieval.get_supabase")
    async def test_embeds_every_ready_item_without_one(self, mock_get_db, mock_embed_and_store):
        from app.services.catalog_retrieval import reindex_catalog_items

        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": "item-1", "name": "A", "item_type": "product", "description": None, "attributes": {}},
            {"id": "item-2", "name": "B", "item_type": "product", "description": None, "attributes": {}},
        ]
        mock_get_db.return_value = db
        mock_embed_and_store.return_value = None

        result = await reindex_catalog_items("tenant-1")

        self.assertEqual(result, {"items_embedded": 2, "items_total": 2})
        self.assertEqual(mock_embed_and_store.call_count, 2)

    @patch("app.services.catalog_retrieval.embed_and_store_catalog_item")
    @patch("app.services.catalog_retrieval.get_supabase")
    async def test_one_item_failing_does_not_stop_the_rest(self, mock_get_db, mock_embed_and_store):
        from app.services.catalog_retrieval import reindex_catalog_items

        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": "item-1", "name": "A", "item_type": "product", "description": None, "attributes": {}},
            {"id": "item-2", "name": "B", "item_type": "product", "description": None, "attributes": {}},
        ]
        mock_get_db.return_value = db
        mock_embed_and_store.side_effect = [Exception("boom"), None]

        result = await reindex_catalog_items("tenant-1")

        self.assertEqual(result, {"items_embedded": 1, "items_total": 2})


if __name__ == "__main__":
    unittest.main()
