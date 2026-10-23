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
INITIAL_FINGERPRINT = "4564ac7032a9e31dfb640626ef0fb41ebc8d934a677a6e6c64653e166f77d853"


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
            self.assertEqual(len(items), 1586)
            self.assertEqual({h.id for h in items}, set(range(1, 1587)))
            self.assertEqual(repository.catalog_fingerprint(items), INITIAL_FINGERPRINT)
            self.assertEqual(sum(not h.en for h in items), 79)
            self.assertEqual(
                connection.execute(
                    "SELECT kind, count(*) FROM herb_aliases GROUP BY kind ORDER BY kind"
                ).fetchall(),
                [("en_alt", 2205), ("latin_synonyms", 226), ("ro_regional", 705)],
            )
            for table, expected in (
                ("herbs", ["id", "category", "family", "latin", "ro", "en", "ranking"]),
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
            self.assertEqual(catalog.by_latin("linum usitatissimum").ro, "seminte de in")
            self.assertEqual(catalog.by_latin("linum usitatissimum").id, 514)
            self.assertEqual(sum(h.ro == "seminte de in" for h in items), 2)
            self.assertEqual(catalog.lookup(""), [])
            self.assertEqual(sum(h.category == "uleiuri" for h in items), 23)
            self.assertEqual(sum(h.category == "suplimente" for h in items), 61)
            self.assertNotIn("fibre, probiotice, prebiotice", {h.category for h in items})
            for identifier in (1191, 1192, 1195, 1198):
                self.assertEqual(catalog.by_id(identifier).category, "suplimente")
            for identifier in (*range(1293, 1314), 1585, 1586):
                self.assertEqual(catalog.by_id(identifier).category, "uleiuri")

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
                "INSERT INTO herbs(category,family,latin,ro) VALUES ('plante medicinale','asteraceae','testus species','test plant') RETURNING id"
            ).fetchone()[0]
            self.assertEqual(identifier, 1587)
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
                "INSERT INTO herbs(category,family,latin,ro) VALUES ('plante medicinale','rosaceae','testus species','test plant'); INSERT INTO herb_aliases(herb_id,name,kind) SELECT id,'crataegus monogyna','latin_synonyms' FROM herbs WHERE latin='testus species';"
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
        from backend.ai import herb_validation
        from backend.ai.herb_index_catalog import read_index_catalogs
        from backend.core.herb_categories import HERB_CATEGORIES, PRODUCT_CATEGORIES

        with psycopg.connect(self.url) as connection:
            before = read_conditions(connection)
            connection.execute("INSERT INTO owner_sessions(token_hash) VALUES (%s)", ("a" * 64,))
            connection.execute("INSERT INTO sync_metadata(key,value) VALUES ('test','unchanged')")
            connection.execute(
                "DROP TABLE herb_positive_evidence,herb_positive_pairs,herb_positive_rankings,herb_positive_cache,herb_positive_runs,herbs_benefits,herb_aliases,herbs"
            )
            versions = [
                "006_herbs.sql",
                "007_seed_herbs.sql",
                "008_herbs_benefits.sql",
                "010_herbs_ranking.sql",
                "014_allow_supplements_in_herbs.sql",
                "015_seed_supplements.sql",
                "016_separate_herb_category.sql",
            ]
            connection.execute(
                "DELETE FROM schema_migrations WHERE version IN (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    "017_food_categories_in_herbs.sql",
                    "018_reclassify_oils_medicines_and_beta_carotene.sql",
                    "019_reclassify_additional_oils.sql",
                    "020_reclassify_remaining_requested_oils.sql",
                    "021_reclassify_probiotic_products.sql",
                    "022_add_sunflower_and_pumpkin_oils.sql",
                    "023_positive_herb_rankings.sql",
                    "024_merge_fibre_probiotics_into_supplements.sql",
                    "025_rename_linum_usitatissimum_ro.sql",
                ),
            )
            for name in versions:
                connection.execute((migration.MIGRATIONS / name).read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO herbs_benefits(herb_id,medical_condition_id) "
                "SELECT 1,min(id) FROM medical_conditions"
            )
            connection.execute("UPDATE herbs SET ranking=37 WHERE id=1")
            connection.execute(
                "INSERT INTO documents(relative_path,absolute_path,size_bytes,modified_utc,sha256,encoding,line_count,char_count) VALUES('keep.md','keep.md',4,now(),'sha','utf-8',1,4)"
            )
            connection.execute(
                "INSERT INTO chunks(source_relative_path,source_absolute_path,source_sha256,line_start,line_end,heading,text,text_sha256,char_count,embedding,text_search) VALUES('keep.md','keep.md','sha',1,1,'keep','keep','sha',4,%s,''::tsvector)",
                ("[" + ",".join(["0"] * 1024) + "]",),
            )
            documents = connection.execute(
                "SELECT *,xmin::text FROM documents ORDER BY relative_path"
            ).fetchall()
            chunks = connection.execute(
                "SELECT row_to_json(c)::text,xmin::text FROM chunks c ORDER BY chunk_id"
            ).fetchall()
            original = connection.execute("SELECT * FROM herbs ORDER BY id").fetchall()
            aliases = connection.execute(
                "SELECT *,xmin::text FROM herb_aliases ORDER BY id"
            ).fetchall()
            benefits = connection.execute(
                "SELECT *,xmin::text FROM herbs_benefits ORDER BY id"
            ).fetchall()
            oids = connection.execute(
                "SELECT 'herb_aliases'::regclass::oid, 'herbs_benefits'::regclass::oid, 'herbs'::regclass::oid"
            ).fetchone()
            # Model the previous reader only while taking the pre-upgrade matching snapshot.
            with (
                patch.object(
                    herb_validation,
                    "HERB_CATEGORIES",
                    (*HERB_CATEGORIES, "fibre, probiotice, prebiotice"),
                ),
                patch.object(
                    herb_validation,
                    "PRODUCT_CATEGORIES",
                    PRODUCT_CATEGORIES | {"fibre, probiotice, prebiotice"},
                ),
            ):
                matching = read_index_catalogs(connection)[-1]
        # Force a failure after DDL, so the old OID, data and ledger must survive rollback.
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for path in migration.MIGRATIONS.glob("*.sql"):
                shutil.copy(path, folder / path.name)
            (folder / "026_injected_failure.sql").write_text("SELECT 1/0;", encoding="utf-8")
            with patch.object(migration, "MIGRATIONS", folder):
                with self.assertRaises(psycopg.errors.DivisionByZero):
                    migration.migrate(self.url)
        with psycopg.connect(self.url) as connection:
            self.assertEqual(
                connection.execute("SELECT * FROM herbs ORDER BY id").fetchall(), original
            )
            self.assertIsNone(
                connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version='017_food_categories_in_herbs.sql'"
                ).fetchone()
            )
        self.assertEqual(
            migration.migrate(self.url),
            [
                "017_food_categories_in_herbs.sql",
                "018_reclassify_oils_medicines_and_beta_carotene.sql",
                "019_reclassify_additional_oils.sql",
                "020_reclassify_remaining_requested_oils.sql",
                "021_reclassify_probiotic_products.sql",
                "022_add_sunflower_and_pumpkin_oils.sql",
                "023_positive_herb_rankings.sql",
                "024_merge_fibre_probiotics_into_supplements.sql",
                "025_rename_linum_usitatissimum_ro.sql",
            ],
        )
        with psycopg.connect(self.url) as connection:
            existing = connection.execute(
                "SELECT * FROM herbs WHERE id<=1579 ORDER BY id"
            ).fetchall()
            expected = [
                (
                    row[0],
                    row[2],
                    row[3],
                    "seminte de in" if row[3] == "linum usitatissimum" else row[4],
                    row[5],
                    row[6],
                )
                for row in original
            ]
            self.assertEqual([(r[0], *r[2:]) for r in existing], expected)
            self.assertEqual(sum(a[1] != b[1] for a, b in zip(existing, original)), 191)
            self.assertEqual(
                connection.execute("SELECT category FROM herbs WHERE id=778").fetchone(),
                ("fructe",),
            )
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) FROM herbs WHERE category='seminte' AND family IS NULL AND latin IS NULL"
                ).fetchone(),
                (4,),
            )
            self.assertEqual(
                connection.execute(
                    "SELECT category,family FROM herbs WHERE latin='chenopodium quinoa'"
                ).fetchone(),
                ("cereale", "amaranthaceae"),
            )
            self.assertEqual(
                connection.execute("SELECT *,xmin::text FROM herb_aliases ORDER BY id").fetchall(),
                aliases,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT *,xmin::text FROM herbs_benefits ORDER BY id"
                ).fetchall(),
                benefits,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT 'herb_aliases'::regclass::oid, 'herbs_benefits'::regclass::oid, 'herbs'::regclass::oid"
                ).fetchone(),
                oids,
            )
            self.assertNotEqual(read_index_catalogs(connection)[-1], matching)
            self.assertEqual(
                connection.execute(
                    "SELECT *,xmin::text FROM documents ORDER BY relative_path"
                ).fetchall(),
                documents,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT row_to_json(c)::text,xmin::text FROM chunks c ORDER BY chunk_id"
                ).fetchall(),
                chunks,
            )

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
