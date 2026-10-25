"""Atomic derived associations on an isolated PostgreSQL fixture."""

from __future__ import annotations

import io
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest import TestCase, mock

import numpy as np
import psycopg

from backend.ai import db
from backend.ai.herb_conditions import lookup_herb_conditions
from backend.ai.index_state import IndexUnavailable
from scripts import build_hybrid_index as builder
from scripts.migrate_database import migrate
from tests.support.conditions import conditions_from_rows, replace_catalog
from tests.support.postgres import PostgresFixture

fixture = PostgresFixture()


def setUpModule():
    fixture.start()
    fixture.snapshot_herbs()


def tearDownModule():
    try:
        fixture.restore_herbs()
    finally:
        fixture.stop()


@contextmanager
def threads(context):
    builder._HERBS_AUTOMATON = builder._make_herbs_matcher(context.names)
    with ThreadPoolExecutor(max_workers=2) as pool:
        yield pool


class HerbsIndexDatabaseTests(TestCase):
    def setUp(self):
        fixture.reset()
        with db.get_pool().connection() as conn:
            conn.execute("TRUNCATE herbs RESTART IDENTITY CASCADE")
            conn.execute(
                "INSERT INTO herbs(id,category,family,latin,ro,en) OVERRIDING SYSTEM VALUE VALUES "
                "(17,'plante medicinale','asteraceae','matricaria chamomilla','musetel','chamomile'), "
                "(803,'plante medicinale','asteraceae','anthemis nobilis','musetel','')"
            )
            replace_catalog(conn, conditions_from_rows("Gastrita,stomac,comun\nFebra,comun\n"))
            conn.execute(
                "INSERT INTO documents(relative_path,absolute_path,size_bytes,modified_utc,sha256,encoding,line_count,char_count) "
                "VALUES ('a.md','a.md',1,now(),'hash','utf-8',1,1)"
            )

    def add_chunk(self, conn, text, primary=(), secondary=(), heading=""):
        conn.execute(
            "INSERT INTO chunks(source_relative_path,source_absolute_path,source_sha256,line_start,line_end,heading,text,text_sha256,char_count,embedding,text_search,primary_medical_conditions,secondary_medical_conditions) "
            "VALUES ('a.md','a.md','hash',1,1,%s,%s,'hash',%s,%s,''::tsvector,%s,%s)",
            (
                heading,
                text,
                len(text),
                np.ones(db.DEFAULT_DIMENSION, dtype=np.float32),
                list(primary),
                list(secondary),
            ),
        )

    def prepare(self, conn, **kwargs):
        return builder._prepare_herbs_index(
            conn,
            chunks_changed=False,
            previous_generation="old",
            next_generation="new",
            force_rebuild=True,
            **kwargs,
        )

    def rebuild(self, conn, ctx=None):
        ctx = ctx or self.prepare(conn)
        with threads(ctx) as pool:
            with conn.transaction():
                stats = builder._rebuild_herbs_benefits(
                    conn, context=ctx, executor=pool, progress=lambda *_a, **_k: None
                )
        conn.commit()
        return stats

    def pairs(self, conn):
        return conn.execute(
            "SELECT id,herb_id,medical_condition_id FROM herbs_benefits ORDER BY 2,3"
        ).fetchall()

    def test_real_builder_metadata_is_accepted_by_plant_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "a.md").write_text("# Gastrita\nMușețel și seminte de in.", encoding="utf-8")

            def embed(_model, chunks, _batch, profile, **_kwargs):
                return np.full(
                    (len(chunks), profile.dimension),
                    1 / np.sqrt(profile.dimension),
                    dtype=np.float32,
                )

            with (
                mock.patch.object(builder, "_prepared_herbs_workers", side_effect=threads),
                mock.patch.object(builder, "create_embedding_model"),
                mock.patch.object(builder, "embed_chunks", side_effect=embed),
                redirect_stdout(io.StringIO()),
                builder.index_writer() as connection,
            ):
                builder._build(
                    source, builder.DEFAULT_MODEL, 8, gpu_usage=lambda: "N/A", connection=connection
                )

        from uuid import uuid4

        from backend.ai.herb_association_classification import (
            group_fragment_works,
            relation_id,
            semantic_config,
        )
        from backend.ai.herb_association_rules import Decision
        from backend.ai.herb_positive_repository import PositiveRepository
        from backend.config import Settings
        from backend.core.errors import ApplicationError

        repository = PositiveRepository()
        config = Settings()
        with self.assertRaises(ApplicationError) as unpublished:
            lookup_herb_conditions("matricaria chamomilla")
        self.assertEqual(unpublished.exception.code, "POSITIVE_RANKING_NOT_READY")
        data = repository.read_snapshot()
        gastrita_id = next(i for i, name in data.conditions.items() if name == "Gastrita")
        self.assertEqual(data.condition_synonyms[gastrita_id], ("stomac", "comun"))
        groups = group_fragment_works(data.works, data.conditions)
        data = replace(data, works=tuple(work for group in groups for work in group.evidence))
        run_id = str(uuid4())
        repository.create_run(run_id, data, semantic_config(config), "c" * 64, False)
        repository.finish(
            run_id,
            data,
            {
                relation_id(work): Decision("positive", "rule", "synthetic_fixture")
                for work in data.works
            },
            {},
            {},
        )
        repository.publish(run_id, config, digest="c" * 64)
        result = lookup_herb_conditions("matricaria chamomilla")
        self.assertEqual(result["status"], "found")
        self.assertEqual([row["name"] for row in result["conditions"]], ["Gastrita"])
        self.assertEqual(result["entriesCount"], 1)

        with db.get_pool().connection() as connection:
            documents = connection.execute(
                "SELECT *,xmin::text FROM documents ORDER BY relative_path"
            ).fetchall()
            chunks = connection.execute(
                "SELECT row_to_json(c)::text,xmin::text FROM chunks c ORDER BY chunk_id"
            ).fetchall()
            metadata = dict(connection.execute("SELECT key,value FROM sync_metadata").fetchall())
            pairs = self.pairs(connection)
            rankings = connection.execute("SELECT id,ranking FROM herbs ORDER BY id").fetchall()
            matching = builder._herbs_catalogs(connection)[-1]
            connection.execute("UPDATE herbs SET category='fructe' WHERE id=17")
            self.assertEqual(builder._herbs_catalogs(connection)[-1], matching)
            connection.execute("SELECT setval('herbs_id_seq',(SELECT max(id) FROM herbs),true)")
            seed = connection.execute(
                "INSERT INTO herbs(category,ro,en) VALUES('seminte','seminte de in','flax seeds') RETURNING id"
            ).fetchone()[0]

        @contextmanager
        def changed_catalog(context):
            with threads(context) as pool:
                with db.get_pool().connection() as connection:
                    connection.execute("UPDATE herbs SET category='legume' WHERE id=17")
                yield pool

        with mock.patch.object(builder, "_prepared_herbs_workers", side_effect=changed_catalog):
            with self.assertRaisesRegex(RuntimeError, "HERBS_CATALOG_CHANGED_DURING_BUILD"):
                builder.rebuild_herbs_only()
        with db.get_pool().connection() as connection:
            connection.execute("UPDATE herbs SET category='fructe' WHERE id=17")

        with (
            mock.patch.object(builder, "_prepared_herbs_workers", side_effect=threads),
            mock.patch.object(builder.os, "walk", side_effect=AssertionError("no corpus scan")),
            mock.patch.object(
                builder, "fragment_document", side_effect=AssertionError("no fragmentation")
            ),
            mock.patch.object(
                builder, "create_embedding_model", side_effect=AssertionError("no model")
            ),
            mock.patch.object(builder, "embed_chunks", side_effect=AssertionError("no embeddings")),
            redirect_stdout(io.StringIO()),
        ):

            def fail(stage):
                if stage == "commit":
                    raise RuntimeError("injected commit failure")

            with (
                mock.patch.object(builder, "_build_stage", side_effect=fail),
                self.assertRaises(RuntimeError),
            ):
                builder.rebuild_herbs_only()
            with db.get_pool().connection() as connection:
                self.assertEqual(self.pairs(connection), pairs)
                self.assertEqual(
                    dict(connection.execute("SELECT key,value FROM sync_metadata").fetchall()),
                    metadata,
                )
                self.assertEqual(
                    connection.execute("SELECT ranking FROM herbs WHERE id=%s", (seed,)).fetchone(),
                    (0,),
                )
            builder.rebuild_herbs_only()
        with db.get_pool().connection() as connection:
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
            self.assertEqual([row for row in self.pairs(connection) if row[1] != seed], pairs)
            self.assertEqual(
                connection.execute(
                    "SELECT id,ranking FROM herbs WHERE id<>%s ORDER BY id", (seed,)
                ).fetchall(),
                rankings,
            )
            self.assertEqual(
                connection.execute("SELECT ranking FROM herbs WHERE id=%s", (seed,)).fetchone(),
                (1,),
            )
            after = dict(connection.execute("SELECT key,value FROM sync_metadata").fetchall())
            self.assertEqual(
                {k: v for k, v in metadata.items() if not k.startswith("herbs_benefits_")},
                {k: v for k, v in after.items() if not k.startswith("herbs_benefits_")},
            )
            self.assertEqual(
                after["herbs_benefits_chunks_generation"], metadata["index_generation"]
            )

        with db.get_pool().connection() as connection:
            connection.execute(
                "INSERT INTO herb_aliases(herb_id,name,kind) VALUES (17,'alias nou','ro_regional')"
            )
        with self.assertRaises(ApplicationError) as error:
            lookup_herb_conditions("matricaria chamomilla")
        self.assertEqual(error.exception.code, "POSITIVE_RANKING_STALE")
        with self.assertRaisesRegex(RuntimeError, "HERBS_ONLY_EXISTING_CATALOG_CHANGED"):
            builder.rebuild_herbs_only()

    def test_schema_idempotence_unique_foreign_keys_and_cascade(self):
        self.assertEqual(migrate(db.settings.database_url), [])
        with self.assertRaises(IndexUnavailable):
            builder.rebuild_herbs_only()

        with db.get_pool().connection() as conn:
            columns = conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='herbs_benefits' ORDER BY ordinal_position"
            ).fetchall()
            self.assertEqual(columns, [("id",), ("herb_id",), ("medical_condition_id",)])
            indexes = conn.execute(
                "SELECT indexname FROM pg_indexes WHERE tablename='herbs_benefits'"
            ).fetchall()
            self.assertEqual(len(indexes), 4)
            conn.execute("INSERT INTO herbs_benefits(herb_id,medical_condition_id) VALUES (17,1)")
            with self.assertRaises(psycopg.errors.UniqueViolation), conn.transaction():
                conn.execute(
                    "INSERT INTO herbs_benefits(herb_id,medical_condition_id) VALUES (17,1)"
                )
            with self.assertRaises(psycopg.errors.ForeignKeyViolation), conn.transaction():
                conn.execute(
                    "INSERT INTO herbs_benefits(herb_id,medical_condition_id) VALUES (99999,1)"
                )
            conn.execute("DELETE FROM herbs WHERE id=17")
            self.assertEqual(self.pairs(conn), [])

    def test_single_scan_equals_sql_reference_and_preserves_pair_ids(self):
        with db.get_pool().connection() as conn:
            self.add_chunk(
                conn, "MUȘEȚEL, matricaria-chamomilla musetel", ["comun"], ["Gastrita", "comun"]
            )
            self.add_chunk(conn, "musetel", ["Gastrita"], ["stomac"])
            self.add_chunk(conn, "musetel gastrita", ["Gastrita cronica"])
            self.add_chunk(conn, "inflamatie", [], [], heading="musetel")
            ctx = self.prepare(conn)
            reference = set()
            matcher = builder._make_herbs_matcher(ctx.names)
            for position, condition_id in enumerate(ctx.condition_ids):
                terms = [
                    term
                    for term, owners in ctx.condition_positions_by_term.items()
                    if position in owners
                ]
                for (text,) in conn.execute(
                    "SELECT text FROM chunks WHERE primary_medical_conditions && %s::text[]",
                    (terms,),
                ):
                    for herb_position in builder._match_herbs(matcher, builder._herb_text(text)):
                        reference.add((ctx.herb_ids[herb_position], condition_id))
            stats = self.rebuild(conn, ctx)
            before = self.pairs(conn)
            self.assertEqual({(h, c) for _, h, c in before}, reference)
            self.assertEqual(reference, {(17, 1), (17, 2), (803, 1), (803, 2)})
            self.assertEqual(stats["staged_pairs"], 4)
            self.assertGreater(stats["candidate_pairs"], 4)
            again = self.rebuild(conn)
            self.assertEqual(self.pairs(conn), before)
            self.assertEqual((again["inserted"], again["deleted"]), (0, 0))
            fallback = self.rebuild(conn, self.prepare(conn, bitmap_budget_bytes=0))
            self.assertEqual(self.pairs(conn), before)
            self.assertEqual(fallback["row_count"], 4)

    def test_secondary_conditions_are_excluded_and_stale_ranking_is_replaced(self):
        with db.get_pool().connection() as conn:
            self.add_chunk(conn, "musetel", ["Gastrita"], ["Febra"])
            self.add_chunk(conn, "musetel", [], ["Febra"])
            conn.execute(
                "INSERT INTO herbs_benefits(herb_id,medical_condition_id) VALUES (17,2),(803,2)"
            )
            conn.execute("UPDATE herbs SET ranking=99")
            stats = self.rebuild(conn)
            self.assertEqual({(h, c) for _, h, c in self.pairs(conn)}, {(17, 1), (803, 1)})
            self.assertEqual(stats["chunks_read"], 1)
            self.assertEqual(stats["deleted"], 2)
            self.assertEqual(
                conn.execute("SELECT id,ranking FROM herbs ORDER BY id").fetchall(),
                [(17, 1), (803, 1)],
            )
            # PDF scores count live associations, independently of cached ranking
            # and the number of aliases belonging to a species.
            conn.execute("UPDATE herbs SET ranking=99")
            conn.execute("INSERT INTO herbs_benefits(herb_id,medical_condition_id) VALUES (803,2)")
            conn.execute(
                "INSERT INTO herb_aliases(herb_id,name,kind) VALUES "
                "(17,'romanita','ro_regional'), (17,'matricaria recutita','latin_synonyms')"
            )
            conn.commit()
            from backend.ai.herb_repository import (
                load_herb_benefit_scores,
                read_herb_benefit_counts,
            )

            self.assertEqual(read_herb_benefit_counts(conn, [17, 803]), {17: 1, 803: 2})
            self.assertEqual(
                load_herb_benefit_scores(
                    ["Romaniță", "Matricaria recutita", "mușețel", "Vitamina B6"]
                ),
                {"Romaniță": 1, "Matricaria recutita": 1, "mușețel": 2, "Vitamina B6": 0},
            )

    def test_last_primary_evidence_removed_with_secondary_conditions_remaining(self):
        with db.get_pool().connection() as conn:
            self.add_chunk(conn, "musetel", ["Gastrita"], ["Febra"])
            self.rebuild(conn)
            conn.execute("UPDATE chunks SET primary_medical_conditions=ARRAY[]::text[]")
            ctx = self.prepare(conn)
            self.assertFalse(ctx.workers_required)
            with conn.transaction():
                stats = builder._rebuild_herbs_benefits(
                    conn, context=ctx, executor=None, progress=lambda *_a, **_k: None
                )
            self.assertEqual(
                (stats["chunks_read"], stats["row_count"], stats["deleted"]), (0, 0, 2)
            )
            self.assertEqual(conn.execute("SELECT ranking FROM herbs").fetchall(), [(0,), (0,)])

    def test_last_evidence_removed_and_empty_result(self):
        with db.get_pool().connection() as conn:
            self.add_chunk(conn, "musetel", ["Gastrita"])
            self.rebuild(conn)
            conn.execute("DELETE FROM chunks")
            stats = self.rebuild(conn)
            self.assertEqual((stats["row_count"], stats["deleted"]), (0, 2))

    def test_rollback_after_deletion_restores_chunks_pairs_and_metadata(self):
        with db.get_pool().connection() as conn:
            self.add_chunk(conn, "musetel", ["Gastrita"])
            self.rebuild(conn)
            conn.commit()
            before = self.pairs(conn)
            before_ranking = conn.execute("SELECT id,ranking FROM herbs ORDER BY id").fetchall()
            conn.commit()
            ctx = self.prepare(conn)
            conn.commit()
            with threads(ctx) as pool:
                with self.assertRaisesRegex(RuntimeError, "publication failed"):
                    with conn.transaction():
                        conn.execute("DELETE FROM chunks")
                        builder._rebuild_herbs_benefits(
                            conn, context=ctx, executor=pool, progress=lambda *_a, **_k: None
                        )
                        conn.execute("INSERT INTO sync_metadata VALUES ('index_generation','bad')")
                        raise RuntimeError("publication failed")
            self.assertEqual(self.pairs(conn), before)
            self.assertEqual(
                conn.execute("SELECT id,ranking FROM herbs ORDER BY id").fetchall(), before_ranking
            )
            self.assertEqual(conn.execute("SELECT count(*) FROM chunks").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT * FROM sync_metadata").fetchall(), [])

    def test_fast_path_invalidations_and_family_has_no_effect(self):
        with db.get_pool().connection() as conn:
            self.add_chunk(conn, "musetel", ["Gastrita"])
            ctx = self.prepare(conn)
            stats = self.rebuild(conn, ctx)
            conn.execute("INSERT INTO sync_metadata VALUES ('index_generation','new')")
            for key, value in builder._herbs_metadata(ctx, stats["row_count"]).items():
                conn.execute("INSERT INTO sync_metadata VALUES (%s,%s)", (key, value))

            def prepare(**kwargs):
                return builder._prepare_herbs_index(
                    conn,
                    chunks_changed=False,
                    previous_generation="new",
                    next_generation="next",
                    force_rebuild=False,
                    **kwargs,
                )

            self.assertFalse(prepare().rebuild_required)
            with conn.transaction(force_rollback=True):
                conn.execute(
                    "UPDATE sync_metadata SET value='divergent' WHERE key='herbs_benefits_chunks_generation'"
                )
                self.assertTrue(prepare().rebuild_required)
            with conn.transaction(force_rollback=True):
                conn.execute("DELETE FROM herbs_benefits WHERE herb_id=17")
                self.assertTrue(prepare().rebuild_required)
            with conn.transaction(force_rollback=True):
                conn.execute("DELETE FROM sync_metadata WHERE key='herbs_benefits_index_version'")
                self.assertTrue(prepare().rebuild_required)
            with conn.transaction(force_rollback=True):
                conn.execute(
                    "INSERT INTO medical_condition_synonyms(medical_condition_id,synonym) VALUES (1,'nou sinonim')"
                )
                self.assertTrue(prepare().rebuild_required)
            conn.execute("UPDATE herbs SET family='rosaceae' WHERE id=17")
            self.assertFalse(prepare().rebuild_required)
            with mock.patch.object(builder, "HERBS_INDEX_VERSION", 1):
                self.assertTrue(prepare().rebuild_required)
            conn.execute(
                "INSERT INTO herb_aliases(herb_id,name,kind) VALUES (17,'noua planta','ro_regional')"
            )
            self.assertTrue(prepare().rebuild_required)

    def test_copy_dedup_publication_and_worker_failure_rollback(self):
        with db.get_pool().connection() as conn:
            self.add_chunk(conn, "musetel", ["Gastrita"])
            self.rebuild(conn)
            before = self.pairs(conn)
            conn.commit()
            ctx = self.prepare(conn)
            conn.commit()

            class FaultConnection:
                def __init__(self, stage):
                    self.stage = stage

                def execute(self, query, *args):
                    if self.stage == "dedup" and query.startswith("CREATE UNIQUE INDEX"):
                        raise RuntimeError("injected failure")
                    result = conn.execute(query, *args)
                    if self.stage == "publication" and query.startswith(
                        "DELETE FROM herbs_benefits"
                    ):
                        raise RuntimeError("injected failure")
                    return result

                def cursor(self, *args, **kwargs):
                    if self.stage == "copy" and not kwargs.get("name"):
                        raise RuntimeError("injected failure")
                    return conn.cursor(*args, **kwargs)

            for stage in ("copy", "dedup", "publication", "worker"):
                with self.subTest(stage=stage), threads(ctx) as pool:
                    if stage == "worker":
                        from concurrent.futures import Future

                        failed = Future()
                        failed.set_exception(RuntimeError("injected failure"))
                        pool.submit = mock.Mock(return_value=failed)
                    with self.assertRaisesRegex(RuntimeError, "injected failure"):
                        with conn.transaction():
                            conn.execute(
                                "UPDATE chunks SET primary_medical_conditions=ARRAY['Febra']"
                            )
                            builder._rebuild_herbs_benefits(
                                FaultConnection(stage),
                                context=ctx,
                                executor=pool,
                                progress=lambda *_a, **_k: None,
                            )
                    self.assertEqual(self.pairs(conn), before)
                    self.assertEqual(
                        conn.execute("SELECT primary_medical_conditions FROM chunks").fetchone()[0],
                        ["Gastrita"],
                    )
                    conn.commit()

    def test_empty_catalog_fails_before_publishing(self):
        from backend.ai.herb_repository import HerbCatalogUnavailable

        with db.get_pool().connection() as conn:
            self.add_chunk(conn, "musetel", ["Gastrita"])
            self.rebuild(conn)
            with conn.transaction(force_rollback=True):
                conn.execute("DELETE FROM herbs")
                with self.assertRaises(HerbCatalogUnavailable):
                    self.prepare(conn)

    def test_worker_startup_failure_precedes_document_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "a.md").write_text("# Gastrita\nMusetel.", encoding="utf-8")

            def embed(_model, chunks, _batch, profile, **kwargs):
                return np.full(
                    (len(chunks), profile.dimension),
                    1 / np.sqrt(profile.dimension),
                    dtype=np.float32,
                )

            with builder.index_writer() as conn:
                with (
                    mock.patch.object(builder, "create_embedding_model"),
                    mock.patch.object(builder, "embed_chunks", side_effect=embed),
                    mock.patch.object(
                        builder,
                        "_prepared_herbs_workers",
                        side_effect=RuntimeError("startup failed"),
                    ),
                    mock.patch.object(builder, "_write_document") as write,
                ):
                    with self.assertRaisesRegex(RuntimeError, "startup failed"):
                        builder._build(
                            source,
                            builder.DEFAULT_MODEL,
                            8,
                            gpu_usage=lambda: "N/A",
                            connection=conn,
                        )
                write.assert_not_called()
                self.assertEqual(
                    conn.execute("SELECT count(*) FROM sync_metadata").fetchone()[0], 0
                )

    def test_full_builder_fast_path_forcing_and_alias_change_skip_embeddings(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "a.md").write_text("# Gastrita\nMusetel. noua planta.", encoding="utf-8")

            def embed(_model, chunks, _batch, profile, **kwargs):
                return np.full(
                    (len(chunks), profile.dimension),
                    1 / np.sqrt(profile.dimension),
                    dtype=np.float32,
                )

            with (
                mock.patch.object(builder, "_prepared_herbs_workers", side_effect=threads),
                mock.patch.object(builder, "create_embedding_model"),
                mock.patch.object(builder, "embed_chunks", side_effect=embed) as embedding,
                redirect_stdout(io.StringIO()),
            ):
                with builder.index_writer() as conn:
                    builder._build(
                        source, builder.DEFAULT_MODEL, 8, gpu_usage=lambda: "N/A", connection=conn
                    )
                    before = self.pairs(conn)
                    embedding.reset_mock()
                    with mock.patch.object(
                        builder, "_rebuild_herbs_benefits", wraps=builder._rebuild_herbs_benefits
                    ) as rebuild:
                        builder._build(
                            source,
                            builder.DEFAULT_MODEL,
                            8,
                            gpu_usage=lambda: "N/A",
                            connection=conn,
                        )
                        rebuild.assert_not_called()
                        builder._build(
                            source,
                            builder.DEFAULT_MODEL,
                            8,
                            gpu_usage=lambda: "N/A",
                            connection=conn,
                            rebuild_herbs=True,
                        )
                        self.assertEqual(rebuild.call_count, 1)
                    embedding.assert_not_called()
                    self.assertEqual(self.pairs(conn), before)
                    metadata = dict(conn.execute("SELECT key,value FROM sync_metadata").fetchall())
                    self.assertEqual(
                        metadata["index_generation"], metadata["herbs_benefits_chunks_generation"]
                    )
                    conn.execute(
                        "INSERT INTO herb_aliases(herb_id,name,kind) VALUES (803,'noua planta','ro_regional')"
                    )
                    with mock.patch.object(
                        builder, "_rebuild_herbs_benefits", wraps=builder._rebuild_herbs_benefits
                    ) as rebuild:
                        builder._build(
                            source,
                            builder.DEFAULT_MODEL,
                            8,
                            gpu_usage=lambda: "N/A",
                            connection=conn,
                        )
                        rebuild.assert_called_once()
                    embedding.assert_not_called()
