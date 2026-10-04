"""Tests for backend.ai.categories (loading the category tree)."""
from __future__ import annotations

import unittest

from backend.ai import db as db_module
from backend.ai.categories import load_category_tree
from tests.support.postgres import PostgresFixture

_fixture = PostgresFixture()


def setUpModule():
    _fixture.start()


def tearDownModule():
    _fixture.stop()


# Insert a minimal `documents` row with just the columns load_category_tree()
# reads. category_id is a GENERATED column (derived from relative_path, see
# db.py's SCHEMA_SQL) — it is never inserted explicitly.
def _insert_document(relative_path: str) -> None:
    with db_module.get_pool().connection() as connection:
        connection.execute(
            """
            INSERT INTO documents (relative_path, absolute_path, size_bytes, modified_utc,
                                    sha256, encoding, line_count, char_count)
            VALUES (%s, %s, 1, now(), 'hash', 'utf-8', 1, 1)
            """,
            (relative_path, f"C:/documents/{relative_path}"),
        )
        connection.commit()


class LoadCategoryTreeTests(unittest.TestCase):
    def setUp(self):
        _fixture.reset()

    # No document has been synced yet — callers must treat that as "no
    # filtering available", not as an error.
    def test_returns_none_when_no_documents_are_synced(self):
        self.assertIsNone(load_category_tree())

    def test_loads_nodes_and_known_ids_exclude_structural_branches(self):
        _insert_document("Cancer/a.md")
        _insert_document("Cancer/b.md")
        _insert_document("Centrul/Anatomie/c.md")

        tree = load_category_tree()

        self.assertIsNotNone(tree)
        self.assertEqual(tree.root_id, "")
        self.assertEqual(set(tree.nodes), {"", "Cancer", "Centrul", "Centrul/Anatomie"})
        self.assertEqual(tree.nodes["Cancer"].total_documents, 2)
        self.assertEqual(tree.nodes["Centrul/Anatomie"].parent, "Centrul")
        # "Centrul" holds no document directly — never a valid retrieval filter.
        self.assertEqual(tree.known_ids(), frozenset({"Cancer", "Centrul/Anatomie"}))


if __name__ == "__main__":
    unittest.main()
