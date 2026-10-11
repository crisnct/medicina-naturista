"""Herb snapshot reconstruction, content hashing and cache isolation."""

from dataclasses import replace
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import psycopg

from backend.ai import herb_repository as repository
from backend.ai.herb_validation import catalog_problems, convert_source
from backend.ai.herbs import load_herbs, parse_herbs
from backend.config import Settings, configure_settings, settings
from tests.unit.ai.test_herbs import SAMPLE, line


class RepositoryTests(TestCase):
    def setUp(self):
        repository.clear_herb_catalog_cache()
        self.addCleanup(repository.clear_herb_catalog_cache)
        self.items = convert_source(parse_herbs(SAMPLE))
        self.connection = Mock()
        self.connection.info = SimpleNamespace(
            host="localhost", port=5432, dbname="test", user="test"
        )

    def test_one_join_reconstructs_lists_and_keeps_a_species_without_aliases(self):
        rows = []
        for herb in reversed(self.items):
            aliases = [
                (name, key)
                for key in ("ro_regional", "latin_synonyms", "en_alt")
                for name in getattr(herb, key)
            ] or [(None, None)]
            rows.extend(
                (herb.id, herb.family, herb.latin, herb.ro, herb.en, name, key)
                for name, key in aliases
            )
        self.connection.execute.return_value.fetchall.return_value = rows
        self.assertEqual(repository.read_herbs(self.connection), self.items)
        self.connection.execute.assert_called_once()

    def test_invalid_and_empty_catalogues_are_controlled_failures(self):
        for rows in (
            [],
            [(1, "Rosaceae", "crataegus monogyna", "paducel", "", None, None)],
            [(1, "rosaceae", "crataegus monogyna", "paducel", "", "alias", "bad")],
        ):
            self.connection.execute.return_value.fetchall.return_value = rows
            with self.assertRaises(repository.HerbCatalogUnavailable) as caught:
                repository.read_herbs(self.connection)
            self.assertEqual(caught.exception.code, "HERB_CATALOG_UNAVAILABLE")
            self.assertEqual(caught.exception.status, 503)

    def test_fingerprint_includes_every_field_and_alias_order(self):
        original = repository.catalog_fingerprint(self.items)
        changes = dict(
            id=42,
            ro="another name",
            latin="another species",
            en="other",
            family="otheraceae",
            ro_regional=("changed",),
            latin_synonyms=("other species",),
            en_alt=("changed",),
        )
        for key, value in changes.items():
            with self.subTest(field=key):
                altered = (replace(self.items[0], **{key: value}), *self.items[1:])
                self.assertNotEqual(original, repository.catalog_fingerprint(altered))
        altered = (
            self.items[0],
            replace(self.items[1], ro_regional=tuple(reversed(self.items[1].ro_regional))),
            *self.items[2:],
        )
        self.assertNotEqual(original, repository.catalog_fingerprint(altered))

    def test_cache_reads_content_every_time_and_separates_databases(self):
        with patch.object(repository, "read_herbs", return_value=self.items) as read:
            first = repository.catalog_snapshot(self.connection)
            self.assertIs(first, repository.catalog_snapshot(self.connection))
            read.return_value = (replace(self.items[0], family="otheraceae"), *self.items[1:])
            second = repository.catalog_snapshot(self.connection)
            self.assertIsNot(first, second)
            self.connection.info.dbname = "another"
            self.assertIsNot(second, repository.catalog_snapshot(self.connection))
            for number in range(8):
                self.connection.info.dbname = str(number)
                repository.catalog_snapshot(self.connection)
            self.assertEqual(len(repository._cache), 4)
            self.assertEqual(read.call_count, 12)

    def test_settings_clear_cache(self):
        saved = replace(settings)
        self.addCleanup(configure_settings, saved)
        with patch.object(repository, "read_herbs", return_value=self.items):
            repository.catalog_snapshot(self.connection)
            configure_settings(Settings())
            self.assertFalse(repository._cache)

    def test_connection_failure_has_no_jsonl_fallback(self):
        with patch("backend.ai.db.get_pool", side_effect=psycopg.OperationalError("secret URL")):
            with self.assertRaises(repository.HerbCatalogUnavailable) as caught:
                load_herbs()
            self.assertNotIn("secret", str(caught.exception))

    def test_runtime_validation_and_source_conversion_are_distinct(self):
        self.assertEqual(catalog_problems(self.items, source=False), [])
        for identifier in (0, -1, True, "slug"):
            self.assertTrue(
                catalog_problems((replace(self.items[0], id=identifier),), source=False)
            )
        for source in (
            line(en="", en_alt=["alternative"]),
            line(latin_synonyms=["Matricaria chamomilla"]),
            line(en_alt=["wild chamomile", "Wild chamomile"]),
        ):
            with self.assertRaises(ValueError):
                convert_source(parse_herbs(source))
