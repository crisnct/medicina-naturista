"""Rebuild and upgrade isolated PostgreSQL databases using only packaged SQL."""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from backend.ai import herb_repository as repository
from backend.ai.condition_repository import catalog_fingerprint as condition_fingerprint
from backend.ai.condition_repository import read_conditions
from scripts import migrate_database as migration
from scripts.bootstrap_database import ensure_database
from tests.support.postgres import PostgresFixture

fixture = PostgresFixture()
INITIAL_FINGERPRINT = "e223532a183ff14d072481e097a36f4ba1a72dc3d40b56a9fbca89baf38dd67f"


def setUpModule():
    fixture.start()


def tearDownModule():
    fixture.stop()


class HerbDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.name = "herbs_test_" + uuid.uuid4().hex
        base = fixture._container.get_connection_url()
        self.url = urlunsplit(urlsplit(base)._replace(path="/" + self.name))
        self.maintenance = make_conninfo(base, dbname="postgres")
        self.addCleanup(self.drop_database)
        ensure_database(self.url)
        migration.migrate(self.url)

    def drop_database(self):
        repository.clear_herb_catalog_cache()
        with psycopg.connect(self.maintenance, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(self.name))
            )

    def test_seed_schema_counts_and_fingerprint_without_jsonl(self):
        with psycopg.connect(self.url) as connection:
            items = repository.read_herbs(connection)
            self.assertEqual(len(items), 1188)
            self.assertEqual({h.id for h in items}, set(range(1, 1189)))
            self.assertEqual(repository.catalog_fingerprint(items), INITIAL_FINGERPRINT)
            self.assertEqual(sum(not h.en for h in items), 79)
            self.assertEqual(
                connection.execute(
                    "SELECT kind, count(*) FROM herb_aliases GROUP BY kind ORDER BY kind"
                ).fetchall(),
                [("en_alt", 2205), ("latin_synonyms", 225), ("ro_regional", 704)],
            )
            for table, expected in (
                ("herbs", ["id", "family", "latin", "ro", "en"]),
                ("herb_aliases", ["id", "herb_id", "name", "kind"]),
            ):
                columns = connection.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position",
                    (table,),
                ).fetchall()
                self.assertEqual([row[0] for row in columns], expected)
                sequence = connection.execute(
                    "SELECT identity_generation, identity_start, identity_increment FROM information_schema.columns WHERE table_name=%s AND column_name='id'",
                    (table,),
                ).fetchone()
                self.assertEqual(sequence, ("ALWAYS", "1", "1"))
            catalog = repository.catalog_snapshot(connection).catalog
            self.assertEqual(
                [h.latin for h in catalog.lookup("PĂDUCEL")],
                ["crataegus laevigata", "crataegus monogyna", "crataegus pentagyna"],
            )
            self.assertEqual(catalog.by_latin("Matricaria recutita").latin, "matricaria chamomilla")
            self.assertEqual(catalog.by_id(1), items[0])
            self.assertEqual(catalog.lookup(""), [])

    def test_lowercase_constraints_and_foreign_key(self):
        with psycopg.connect(self.url) as connection:
            for column in ("family", "latin", "ro", "en"):
                with self.subTest(column=column), self.assertRaises(psycopg.errors.CheckViolation):
                    with connection.transaction():
                        connection.execute(
                            sql.SQL("UPDATE herbs SET {}='Uppercase' WHERE id=1").format(
                                sql.Identifier(column)
                            )
                        )
            with self.assertRaises(psycopg.errors.CheckViolation):
                with connection.transaction():
                    connection.execute(
                        "INSERT INTO herb_aliases(herb_id,name,kind) VALUES (1,'Uppercase','en_alt')"
                    )
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                with connection.transaction():
                    connection.execute(
                        "INSERT INTO herb_aliases(herb_id,name,kind) VALUES (99999,'alias','en_alt')"
                    )

    def test_no_aliases_cascade_and_latin_update_preserve_identity(self):
        with psycopg.connect(self.url) as connection:
            identifier = connection.execute(
                "INSERT INTO herbs(family,latin,ro) VALUES ('asteraceae','testus species','test plant') RETURNING id"
            ).fetchone()[0]
            self.assertEqual(identifier, 1189)
            self.assertEqual(
                repository.catalog_snapshot(connection).catalog.by_id(identifier).en_alt, ()
            )
            connection.execute("UPDATE herbs SET latin='testus changed' WHERE id=%s", (identifier,))
            connection.execute(
                "INSERT INTO herb_aliases(herb_id,name,kind) VALUES (%s,'test alias','ro_regional')",
                (identifier,),
            )
            self.assertEqual(
                repository.catalog_snapshot(connection).catalog.by_latin("testus changed").id,
                identifier,
            )
            connection.execute("DELETE FROM herbs WHERE id=%s", (identifier,))
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) FROM herb_aliases WHERE herb_id=%s", (identifier,)
                ).fetchone()[0],
                0,
            )

    def test_failed_validation_rolls_back_herbs_and_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "migrations"
            shutil.copytree(migration.MIGRATIONS, folder)
            (folder / "008_invalid_herb.sql").write_text(
                "INSERT INTO herbs(family,latin,ro) VALUES ('rosaceae','testus species','test plant'); INSERT INTO herb_aliases(herb_id,name,kind) SELECT id,'crataegus monogyna','latin_synonyms' FROM herbs WHERE latin='testus species';"
            )
            with (
                patch.object(migration, "MIGRATIONS", folder),
                self.assertRaises(repository.HerbCatalogUnavailable),
            ):
                migration.migrate(self.url)
        with psycopg.connect(self.url) as connection:
            self.assertEqual(
                repository.catalog_fingerprint(repository.read_herbs(connection)),
                INITIAL_FINGERPRINT,
            )
            self.assertIsNone(
                connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version='008_invalid_herb.sql'"
                ).fetchone()
            )

    def test_upgrade_preserves_conditions_owner_and_index_metadata(self):
        with psycopg.connect(self.url) as connection:
            before = read_conditions(connection)
            connection.execute("INSERT INTO owner_sessions(token_hash) VALUES (%s)", ("a" * 64,))
            connection.execute("INSERT INTO sync_metadata(key,value) VALUES ('test','unchanged')")
            connection.execute("DROP TABLE herbs_benefits, herb_aliases, herbs")
            connection.execute(
                "DELETE FROM schema_migrations WHERE version IN ('006_herbs.sql','007_seed_herbs.sql','008_herbs_benefits.sql')"
            )
        self.assertEqual(
            migration.migrate(self.url),
            ["006_herbs.sql", "007_seed_herbs.sql", "008_herbs_benefits.sql"],
        )
        with psycopg.connect(self.url) as connection:
            self.assertEqual(read_conditions(connection), before)
            self.assertEqual(
                connection.execute("SELECT token_hash FROM owner_sessions").fetchall(),
                [("a" * 64,)],
            )
            self.assertEqual(
                connection.execute("SELECT value FROM sync_metadata WHERE key='test'").fetchone()[
                    0
                ],
                "unchanged",
            )

    def test_content_changes_refresh_cache_without_affecting_condition_fingerprint(self):
        with psycopg.connect(self.url) as connection:
            before = repository.catalog_snapshot(connection)
            conditions = condition_fingerprint(read_conditions(connection))
            connection.execute("UPDATE herbs SET family='changedaceae' WHERE id=1")
            after = repository.catalog_snapshot(connection)
            self.assertIsNot(before, after)
            self.assertNotEqual(before.fingerprint, after.fingerprint)
            self.assertEqual(condition_fingerprint(read_conditions(connection)), conditions)
        self.assertEqual(migration.migrate(self.url), [])
        with psycopg.connect(self.url) as connection:
            self.assertEqual(
                repository.catalog_snapshot(connection).catalog.by_id(1).family, "changedaceae"
            )

    def test_readers_see_only_committed_catalogue(self):
        with psycopg.connect(self.url) as writer, psycopg.connect(self.url) as reader:
            before = repository.catalog_snapshot(reader)
            writer.execute("UPDATE herbs SET family='changedaceae' WHERE id=1")
            writer.execute(
                "UPDATE herb_aliases SET name='changed alias' WHERE id=(SELECT min(id) FROM herb_aliases WHERE kind='en_alt')"
            )
            self.assertEqual(repository.catalog_snapshot(reader).fingerprint, before.fingerprint)
            writer.commit()
            self.assertNotEqual(repository.catalog_snapshot(reader).fingerprint, before.fingerprint)

    def test_concurrent_initial_migrations_and_retry_do_not_repeat_seed(self):
        self.drop_database()
        ensure_database(self.url)
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: migration.migrate(self.url), range(2)))
        self.assertEqual(
            sorted(map(len, results)), [0, len(list(migration.MIGRATIONS.glob("*.sql")))]
        )
        self.assertEqual(migration.migrate(self.url), [])
        with psycopg.connect(self.url) as connection:
            self.assertEqual(
                repository.catalog_fingerprint(repository.read_herbs(connection)),
                INITIAL_FINGERPRINT,
            )
