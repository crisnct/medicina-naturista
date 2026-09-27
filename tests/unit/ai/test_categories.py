"""Tests for medicina_naturista.ai.categories (loading the category tree)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from medicina_naturista.ai.categories import load_category_tree


class LoadCategoryTreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.index_dir = Path(self.tmp.name)

    # An index built before category support existed has no categories.json —
    # callers must treat that as "no filtering available", not as an error.
    def test_returns_none_when_categories_file_is_missing(self):
        self.assertIsNone(load_category_tree(self.index_dir))

    def test_loads_nodes_and_known_ids_exclude_structural_branches(self):
        payload = {
            "version": 1,
            "root_id": "",
            "nodes": {
                "": {"id": "", "label": "(fără categorie)", "parent": None, "children": ["Cancer", "Centrul"], "own_documents": 0, "total_documents": 3},
                "Cancer": {"id": "Cancer", "label": "Cancer", "parent": "", "children": [], "own_documents": 2, "total_documents": 2},
                "Centrul": {"id": "Centrul", "label": "Centrul", "parent": "", "children": ["Centrul/Anatomie"], "own_documents": 0, "total_documents": 1},
                "Centrul/Anatomie": {"id": "Centrul/Anatomie", "label": "Anatomie", "parent": "Centrul", "children": [], "own_documents": 1, "total_documents": 1},
            },
        }
        (self.index_dir / "categories.json").write_text(json.dumps(payload), encoding="utf-8")

        tree = load_category_tree(self.index_dir)

        self.assertIsNotNone(tree)
        self.assertEqual(tree.root_id, "")
        self.assertEqual(set(tree.nodes), {"", "Cancer", "Centrul", "Centrul/Anatomie"})
        self.assertEqual(tree.nodes["Cancer"].total_documents, 2)
        self.assertEqual(tree.nodes["Centrul/Anatomie"].parent, "Centrul")
        # "Centrul" holds no document directly — never a valid retrieval filter.
        self.assertEqual(tree.known_ids(), frozenset({"Cancer", "Centrul/Anatomie"}))


if __name__ == "__main__":
    unittest.main()
