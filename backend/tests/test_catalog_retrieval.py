import sys
import unittest
from pathlib import Path

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

    def test_ungrouped_items_are_broad_browse(self):
        contention = [
            {"id": "a", "variant_group_id": None},
            {"id": "b", "variant_group_id": None},
        ]
        self.assertEqual(classify_gate(contention), "broad_browse")

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


if __name__ == "__main__":
    unittest.main()
