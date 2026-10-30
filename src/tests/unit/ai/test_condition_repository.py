"""Catalog cache isolation, semantic hashing and structured failure handling."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from backend.ai import condition_repository as repository
from backend.ai.conditions import make_condition


class CatalogTests(TestCase):
    def setUp(self):
        repository.clear_catalog_cache()
        self.addCleanup(repository.clear_catalog_cache)
        self.items = (make_condition("Gută", ["gout", "podagra"]),)
        self.fingerprint = repository.catalog_fingerprint(self.items)
        self.connection = Mock()
        self.connection.info = SimpleNamespace(
            host="localhost", port=5432, dbname="test", user="test"
        )

    def test_concurrent_cache_misses_build_one_snapshot(self):
        barrier = Barrier(8)

        def load(_):
            barrier.wait(timeout=5)
            return repository.catalog_snapshot(self.connection)

        with (
            patch.object(repository, "read_conditions", return_value=self.items),
            patch.object(
                repository, "ConditionDictionary", wraps=repository.ConditionDictionary
            ) as dictionary,
        ):
            with ThreadPoolExecutor(max_workers=8) as workers:
                snapshots = list(workers.map(load, range(8)))
            dictionary.assert_called_once()
            self.assertTrue(all(item is snapshots[0] for item in snapshots))

    def test_data_and_database_changes_never_reuse_an_old_snapshot(self):
        with patch.object(repository, "read_conditions", return_value=self.items) as read:
            first = repository.catalog_snapshot(self.connection)
            read.return_value = (make_condition("Gută", ["gout", "podagra", "new synonym"]),)
            second = repository.catalog_snapshot(self.connection)
            self.connection.info.dbname = "another-test"
            third = repository.catalog_snapshot(self.connection)
        self.assertIsNot(first, second)
        self.assertIsNot(second, third)

    def test_empty_database_is_unavailable(self):
        self.connection.execute.return_value.fetchall.return_value = []
        with self.assertRaises(repository.CatalogUnavailable):
            repository.catalog_snapshot(self.connection)

    def test_reading_two_tables_adds_the_canonical_name_in_python(self):
        self.connection.execute.return_value.fetchall.return_value = [
            (7, "Gută", "Gout", "gout"),
            (7, "Gută", "Gout", "podagra"),
            (12, "Gripa", "Flu", None),
        ]
        self.assertEqual(
            repository.read_conditions(self.connection),
            (
                replace(make_condition("Gută", ["gout", "podagra"]), english="Gout"),
                replace(make_condition("Gripa"), english="Flu"),
            ),
        )

    def test_fingerprint_includes_term_order_but_excludes_database_ids(self):
        changed = (make_condition("Gută", ["podagra", "gout"]),)
        self.assertNotEqual(self.fingerprint, repository.catalog_fingerprint(changed))
        self.assertEqual(self.fingerprint, repository.catalog_fingerprint(tuple(self.items)))
