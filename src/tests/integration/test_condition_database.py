"""Reconstruct disposable databases from SQL, never from the removed JSONL."""

from __future__ import annotations

import io
import shutil
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext, redirect_stdout
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit, urlunsplit

import numpy as np
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from backend.ai import db, index_state
from backend.ai.condition_repository import (
    catalog_fingerprint,
    catalog_snapshot,
    clear_catalog_cache,
    read_conditions,
)
from backend.ai.conditions import make_condition
from backend.config import Settings
from scripts import build_hybrid_index as builder
from scripts import migrate_database as migration
from scripts.bootstrap_database import ensure_database
from scripts.condition_sql import additions_sql
from tests.support.conditions import replace_catalog
from tests.support.postgres import PostgresFixture

fixture = PostgresFixture()
INITIAL_FINGERPRINT = "64dfdeccfb04dd9d71ecc763bafda0f5d291df8299895781a945d17b5513a858"


def setUpModule():
    fixture.start()


def tearDownModule():
    fixture.stop()


class ConditionDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.name = "conditions_test_" + uuid.uuid4().hex
        base_url = fixture._container.get_connection_url()
        parts = urlsplit(base_url)
        self.url = urlunsplit(parts._replace(path="/" + self.name))
        self.maintenance = make_conninfo(base_url, dbname="postgres")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "documents"
        self.source.mkdir()
        self.expected_conditions = 6284
        (self.source / "a.md").write_text("# Gripa\nRemedii și repaus.", encoding="utf-8")
        self.config = replace(
            Settings(), database_url=self.url, model_cache_dir=Path(self.tmp.name) / "models"
        )
        db.close_pool()
        self.addCleanup(self.drop_database)

    def drop_database(self):
        db.close_pool()
        clear_catalog_cache()
        with psycopg.connect(self.maintenance, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (self.name,),
            )
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(self.name))
            )

    def assert_two_table_schema(self, connection):
        columns = connection.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name IN "
            "('medical_conditions', 'medical_condition_synonyms', "
            "'medical_condition_terms', 'medical_condition_catalog') "
            "ORDER BY table_name, ordinal_position"
        ).fetchall()
        self.assertEqual(
            columns,
            [
                ("medical_condition_synonyms", "id"),
                ("medical_condition_synonyms", "medical_condition_id"),
                ("medical_condition_synonyms", "synonym"),
                ("medical_conditions", "id"),
                ("medical_conditions", "name"),
            ],
        )

    def sync(self, fail=False):
        def embeddings(_model, chunks, _batch, profile, **_kwargs):
            with psycopg.connect(self.url) as connection:
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM medical_conditions").fetchone()[0],
                    self.expected_conditions,
                )
            if fail:
                raise RuntimeError("injected embedding failure")
            vectors = np.ones((len(chunks), profile.dimension), dtype=np.float32)
            return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

        with (
            patch.object(db, "settings", self.config),
            patch.object(builder, "settings", self.config),
            patch.object(
                builder,
                "GPUUsageMonitor",
                return_value=nullcontext(SimpleNamespace(percent=lambda: "N/A")),
            ),
            patch.object(builder, "create_embedding_model", return_value=object()),
            patch.object(builder, "embed_chunks", side_effect=embeddings) as embed,
            redirect_stdout(io.StringIO()),
        ):
            builder.build(self.source, builder.DEFAULT_MODEL)
            return embed

    def test_reindex_creates_missing_database_and_seeds_before_fragmentation(self):
        original = builder.fragment_document

        def fragment(*args, **kwargs):
            with psycopg.connect(self.url) as connection:
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM medical_conditions").fetchone()[0],
                    6284,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT count(*) FROM medical_condition_synonyms"
                    ).fetchone()[0],
                    39356,
                )
                self.assert_two_table_schema(connection)
            return original(*args, **kwargs)

        with patch.object(builder, "fragment_document", side_effect=fragment):
            self.sync()
        with psycopg.connect(self.url) as connection:
            items = read_conditions(connection)
            self.assertEqual(catalog_fingerprint(items), INITIAL_FINGERPRINT)
            self.assertEqual(connection.execute("SELECT count(*) FROM documents").fetchone()[0], 1)
            rows = connection.execute(
                "SELECT business_category, primary_medical_conditions FROM chunks"
            ).fetchall()
            self.assertEqual(rows, [("R1", ["Gripa"])])
        with patch.object(db, "settings", self.config):
            with index_state.index_reader():
                pass
        self.sync().assert_not_called()
        # Recreate again after an actual DROP of this isolated database.
        self.drop_database()
        self.sync()
        with psycopg.connect(self.url) as connection:
            self.assertEqual(
                connection.execute("SELECT count(*) FROM medical_conditions").fetchone()[0], 6284
            )
            self.assertEqual(connection.execute("SELECT count(*) FROM chunks").fetchone()[0], 1)

    def test_new_sql_migration_is_applied_without_replacing_existing_conditions(self):
        ensure_database(self.url)
        migration.migrate(self.url)
        with psycopg.connect(self.url) as connection:
            before = read_conditions(connection)
        folder = Path(self.tmp.name) / "migrations"
        shutil.copytree(migration.MIGRATIONS, folder)
        additions = [
            make_condition("ABCES", ["should not replace"]),
            make_condition("Boala testului", ["Măr's syndrome", "test disease"]),
        ]
        (folder / "006_test_additions.sql").write_text(additions_sql(additions), encoding="utf-8")
        self.expected_conditions = 6285
        with patch.object(migration, "MIGRATIONS", folder):
            self.sync()
            self.assertEqual(migration.migrate(self.url), [])
        with psycopg.connect(self.url) as connection:
            after = read_conditions(connection)
            self.assertEqual(after[:-1], before)
            self.assertEqual(after[-1], additions[-1])
            self.assertNotEqual(catalog_fingerprint(after), catalog_fingerprint(before))

    def test_initial_seed_preserves_a_condition_already_in_the_database(self):
        ensure_database(self.url)
        with psycopg.connect(self.url) as connection:
            for filename in ("001_hybrid_index.sql", "003_medical_conditions.sql"):
                connection.execute((migration.MIGRATIONS / filename).read_text(encoding="utf-8"))
            condition_id = connection.execute(
                "INSERT INTO medical_conditions(name, normalized_name, sort_order) "
                "VALUES ('Abces', 'abces', 0) RETURNING condition_id"
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO medical_condition_terms VALUES (%s,0,'Abces','abces'), "
                "(%s,1,'existing-only','existing only')",
                (condition_id, condition_id),
            )
            connection.execute(
                "CREATE TABLE schema_migrations(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES ('001_hybrid_index.sql'), ('003_medical_conditions.sql')"
            )
        migration.migrate(self.url)
        with psycopg.connect(self.url) as connection:
            items = read_conditions(connection)
            self.assertEqual(len(items), 6284)
            self.assertEqual(items[0], make_condition("Abces", ["existing-only"]))

    def test_failed_sql_rolls_back_data_and_ledger(self):
        ensure_database(self.url)
        migration.migrate(self.url)
        folder = Path(self.tmp.name) / "migrations"
        shutil.copytree(migration.MIGRATIONS, folder)
        (folder / "006_broken.sql").write_text(
            additions_sql([make_condition("Test rollback")]) + "SELECT 1 / 0;", encoding="utf-8"
        )
        with psycopg.connect(self.url) as connection:
            before = read_conditions(connection)
        with patch.object(migration, "MIGRATIONS", folder):
            with self.assertRaises(psycopg.errors.DivisionByZero):
                migration.migrate(self.url)
        with psycopg.connect(self.url) as connection:
            self.assertEqual(read_conditions(connection), before)
            self.assertEqual(
                connection.execute("SELECT count(*) FROM medical_conditions").fetchone()[0], 6284
            )
            self.assertIsNone(
                connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version='006_broken.sql'"
                ).fetchone()
            )

    def test_embedding_failure_retains_complete_catalog_and_retry_succeeds(self):
        with self.assertRaisesRegex(RuntimeError, "embedding failure"):
            self.sync(fail=True)
        with psycopg.connect(self.url) as connection:
            self.assertEqual(
                connection.execute("SELECT count(*) FROM medical_conditions").fetchone()[0], 6284
            )
            self.assertEqual(connection.execute("SELECT count(*) FROM chunks").fetchone()[0], 0)
        self.sync()

    def test_concurrent_bootstrap_and_migrations_are_idempotent(self):
        with ThreadPoolExecutor(max_workers=2) as workers:
            created = list(workers.map(lambda _: ensure_database(self.url), range(2)))
            applied = list(workers.map(lambda _: migration.migrate(self.url), range(2)))
        self.assertEqual(sum(created), 1)
        self.assertEqual(sorted(len(versions) for versions in applied), [0, 5])
        with psycopg.connect(self.url) as connection:
            self.assertEqual(
                connection.execute("SELECT count(*) FROM medical_conditions").fetchone()[0], 6284
            )

    def test_synonym_changes_invalidate_cache_without_a_metadata_table(self):
        ensure_database(self.url)
        migration.migrate(self.url)
        with psycopg.connect(self.url) as connection:
            first = catalog_snapshot(connection)
            connection.execute(
                "UPDATE medical_condition_synonyms SET synonym='changed synonym' WHERE id=1"
            )
            second = catalog_snapshot(connection)
            self.assertIsNot(first, second)
            self.assertNotEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(migration.migrate(self.url), [])

    def test_upgrade_removes_legacy_tables_and_preserves_diseases_and_synonyms(self):
        ensure_database(self.url)
        legacy = sorted(migration.MIGRATIONS.glob("00[1-4]_*.sql"))
        with psycopg.connect(self.url) as connection:
            connection.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY)")
            for path in legacy:
                connection.execute(path.read_text(encoding="utf-8"))
                connection.execute("INSERT INTO schema_migrations VALUES (%s)", (path.name,))
            original_ids = connection.execute(
                "SELECT condition_id, name FROM medical_conditions ORDER BY condition_id"
            ).fetchall()
        self.assertEqual(migration.migrate(self.url), ["005_simplify_medical_conditions.sql"])
        with psycopg.connect(self.url) as connection:
            self.assert_two_table_schema(connection)
            self.assertEqual(
                connection.execute(
                    "SELECT id, name FROM medical_conditions ORDER BY id"
                ).fetchall(),
                original_ids,
            )
            self.assertEqual(catalog_fingerprint(read_conditions(connection)), INITIAL_FINGERPRINT)
            self.assertEqual(
                connection.execute("SELECT count(*) FROM medical_condition_synonyms").fetchone()[0],
                39356,
            )

    def test_disease_without_synonyms_and_cascade_deletion(self):
        ensure_database(self.url)
        migration.migrate(self.url)
        with psycopg.connect(self.url) as connection:
            replace_catalog(
                connection,
                [make_condition("Single disease"), make_condition("Other disease", ["alias"])],
            )
            self.assertEqual(
                read_conditions(connection),
                (make_condition("Single disease"), make_condition("Other disease", ["alias"])),
            )
            connection.execute("DELETE FROM medical_conditions WHERE name='Other disease'")
            self.assertEqual(
                connection.execute("SELECT count(*) FROM medical_condition_synonyms").fetchone()[0],
                0,
            )
