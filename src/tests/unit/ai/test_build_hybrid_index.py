from __future__ import annotations

import dataclasses
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import numpy as np
import psycopg
from psycopg.rows import namedtuple_row

from backend.ai import categories
from backend.ai import db as db_module
from backend.ai.conditions import ConditionDictionary, parse_conditions
from backend.ai.embedding_model import PROFILES, EmbeddingProfile, get_profile
from scripts import build_hybrid_index as builder
from tests.support.conditions import conditions_jsonl
from tests.support.postgres import PostgresFixture

_fixture = PostgresFixture()
QWEN = get_profile(builder.DEFAULT_MODEL)
# A second, narrower model that only exists in the tests, to exercise a model change.
OTHER = EmbeddingProfile("test/other-model", 64, "{text}", "{text}", 1400, 240)


def setUpModule():
    _fixture.start()


def tearDownModule():
    _fixture.stop()


def make_chunk(index: int, text: str = "text") -> builder.Chunk:
    return builder.Chunk(
        source_relative_path="document.md",
        source_absolute_path="C:/documents/document.md",
        source_sha256="source-hash",
        line_start=1,
        line_end=1,
        heading="Titlu",
        text=text,
        text_sha256=f"text-hash-{index}",
        char_count=len(text),
    )


class FakeClock:
    def __init__(self, *values: float) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


class FakeEmbeddingModel:
    def __init__(self, count: int, *, fail_after: int | None = None) -> None:
        self.count = count
        self.fail_after = fail_after

    def embed(self, documents, batch_size: int, parallel):
        inputs = list(documents)
        if len(inputs) != self.count:
            raise AssertionError(f"Expected {self.count} inputs, received {len(inputs)}")
        for index in range(self.count):
            if self.fail_after is not None and index == self.fail_after:
                raise RuntimeError("embedding failed")
            vector = np.zeros(QWEN.dimension, dtype=np.float32)
            vector[index % QWEN.dimension] = 1.0
            yield vector


# Return unit-normalized deterministic embeddings, standing in for the real
# ONNX model in tests that only care about the sync/DB-write behaviour.
def fake_embed(_model, chunks, _batch_size, profile):
    vectors = np.ones((len(chunks), profile.dimension), dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors


class ChunkingTests(unittest.TestCase):
    def test_normalize_text_preserves_composed_romanian_diacritics(self):
        decomposed = "s\u0326i t\u0326erapie\r\n"

        self.assertEqual(builder.normalize_text(decomposed), "și țerapie\n")


class EmbeddingProgressTests(unittest.TestCase):
    def test_reports_periodic_progress_and_completion(self):
        chunks = [make_chunk(index) for index in range(1, 4)]
        output = io.StringIO()

        with redirect_stdout(output):
            embeddings = builder.embed_chunks(
                FakeEmbeddingModel(3),
                chunks,
                batch_size=64,
                profile=QWEN,
                clock=FakeClock(0.0, 3.0, 11.0, 12.0, 15.0),
            )

        log = output.getvalue()
        self.assertIn("Embedding progress: 2/3 (66.7%)", log)
        self.assertIn("elapsed 00:00:11", log)
        self.assertIn("ETA 00:00:05", log)
        self.assertIn("Embedding completed: 3/3 (100.0%)", log)
        self.assertEqual(embeddings.shape, (3, QWEN.dimension))
        np.testing.assert_allclose(np.linalg.norm(embeddings, axis=1), np.ones(3))

    def test_short_run_still_reports_completion(self):
        output = io.StringIO()

        with redirect_stdout(output):
            builder.embed_chunks(
                FakeEmbeddingModel(1),
                [make_chunk(1)],
                batch_size=64,
                profile=QWEN,
                clock=FakeClock(0.0, 1.0, 2.0),
            )

        log = output.getvalue()
        self.assertNotIn("Embedding progress:", log)
        self.assertIn("Embedding completed: 1/1 (100.0%)", log)

    def test_oversized_chunk_is_embedded_on_windows_and_averaged(self):
        # Deterministic per-input-index unit vectors, so we can tell how many
        # documents a call actually embedded without depending on a real model.
        class WindowModel:
            def embed(self, documents, batch_size, parallel):
                for index, _ in enumerate(documents):
                    vector = np.zeros(QWEN.dimension, dtype=np.float32)
                    vector[index % QWEN.dimension] = 1.0
                    yield vector

        long_chunk = make_chunk(1, text="Propoziție. " * 300)
        self.assertGreater(len(long_chunk.text), QWEN.max_chars)
        windows = len(builder._embedding_windows(long_chunk, QWEN))
        self.assertGreater(windows, 1)
        output = io.StringIO()

        with redirect_stdout(output):
            embeddings = builder.embed_chunks(
                WindowModel(), [long_chunk], batch_size=64, profile=QWEN,
                clock=FakeClock(0.0, *([1.0] * windows), 5.0),
            )

        self.assertEqual(embeddings.shape, (1, QWEN.dimension))
        np.testing.assert_allclose(np.linalg.norm(embeddings, axis=1), [1.0], atol=1e-6)
        self.assertIn("Embedding completed: 1/1 (100.0%)", output.getvalue())

    def test_short_and_oversized_chunks_land_at_their_original_positions(self):
        class WindowModel:
            def embed(self, documents, batch_size, parallel):
                for index, _ in enumerate(documents):
                    vector = np.zeros(QWEN.dimension, dtype=np.float32)
                    vector[index % QWEN.dimension] = 1.0
                    yield vector

        chunks = [make_chunk(1, text="scurt"), make_chunk(2, text="Propoziție. " * 300), make_chunk(3, text="scurt2")]
        windows = sum(len(builder._embedding_windows(chunk, QWEN)) for chunk in chunks)

        embeddings = builder.embed_chunks(
            WindowModel(), chunks, batch_size=64, profile=QWEN, clock=FakeClock(0.0, *([1.0] * windows), 3.0),
        )

        self.assertEqual(embeddings.shape, (3, QWEN.dimension))
        for row in embeddings:
            self.assertAlmostEqual(float(np.linalg.norm(row)), 1.0, places=5)

    def test_a_long_chunk_averages_only_its_own_windows(self):
        # Window i of the whole batch gets the unit vector e_i, so a chunk's
        # embedding must be the normalized mean of exactly its own windows.
        class WindowModel:
            def embed(self, documents, batch_size, parallel):
                for index, _ in enumerate(documents):
                    vector = np.zeros(QWEN.dimension, dtype=np.float32)
                    vector[index] = 1.0
                    yield vector

        chunks = [make_chunk(1, text="scurt"), make_chunk(2, text="Propoziție. " * 300)]
        long_windows = len(builder._embedding_windows(chunks[1], QWEN))

        embeddings = builder.embed_chunks(WindowModel(), chunks, batch_size=64, profile=QWEN)

        np.testing.assert_allclose(embeddings[0][0], 1.0)
        expected = np.zeros(QWEN.dimension, dtype=np.float32)
        expected[1:1 + long_windows] = 1.0 / np.sqrt(long_windows)
        np.testing.assert_allclose(embeddings[1], expected, atol=1e-6)

    def test_embedding_failure_is_propagated_without_false_completion(self):
        output = io.StringIO()

        with self.assertRaisesRegex(RuntimeError, "embedding failed"), redirect_stdout(output):
            builder.embed_chunks(
                FakeEmbeddingModel(3, fail_after=1),
                [make_chunk(index) for index in range(1, 4)],
                batch_size=64,
                profile=QWEN,
                clock=FakeClock(0.0, 11.0),
            )

        self.assertNotIn("Embedding completed", output.getvalue())


class EmbeddingProfileTests(unittest.TestCase):
    def test_qwen_puts_an_instruction_before_the_query_and_no_prefix_before_passages(self):
        query = QWEN.query_text("ceai pentru tuse")

        self.assertTrue(query.startswith("Instruct: "))
        self.assertTrue(query.endswith("\nQuery:ceai pentru tuse"))
        self.assertEqual(QWEN.passage_text("Titlu\ntext"), "Titlu\ntext")
        self.assertEqual(QWEN.dimension, 1024)

    def test_braces_in_a_question_are_not_template_syntax(self):
        self.assertEqual(QWEN.query_text("{text} {0}").split("Query:")[1], "{text} {0}")

    def test_windows_follow_the_profile(self):
        chunk = make_chunk(1, text="Propoziție. " * 300)

        qwen_windows = builder._embedding_windows(chunk, QWEN)
        prefixed = builder._embedding_windows(chunk, dataclasses.replace(QWEN, passage_template="passage: {text}"))

        self.assertGreater(len(qwen_windows), 1)
        self.assertTrue(qwen_windows[0].startswith("document\nTitlu\n"))
        self.assertEqual(prefixed, ["passage: " + window for window in qwen_windows])

    def test_unknown_model_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "Unknown embedding model"):
            get_profile("nu/exista")


def make_source(relative_path: str, category_id: str) -> builder.SourceFile:
    return builder.SourceFile(
        relative_path=relative_path,
        absolute_path=f"C:/documents/{relative_path}",
        size_bytes=10,
        modified_utc="2026-01-01T00:00:00Z",
        sha256="hash",
        encoding="utf-8",
        line_count=1,
        char_count=10,
        category_id=category_id,
    )


class CategoryTreeTests(unittest.TestCase):
    def test_builds_recursive_tree_from_folder_structure(self):
        sources = [
            make_source("Cancer/a.md", "Cancer"),
            make_source("Cancer/b.md", "Cancer"),
            make_source("Centrul de studii/Anatomie/c.md", "Centrul de studii/Anatomie"),
            make_source("root.md", ""),
        ]

        tree = categories.build_category_tree(sources)

        self.assertEqual(tree["root_id"], "")
        nodes = tree["nodes"]
        self.assertEqual(set(nodes), {"", "Cancer", "Centrul de studii", "Centrul de studii/Anatomie"})

        # "Cancer" has documents of its own and no children.
        self.assertEqual(nodes["Cancer"]["own_documents"], 2)
        self.assertEqual(nodes["Cancer"]["total_documents"], 2)
        self.assertEqual(nodes["Cancer"]["children"], [])
        self.assertEqual(nodes["Cancer"]["parent"], "")

        # "Centrul de studii" is a purely structural ancestor: no document of
        # its own, but its subfolder's document counts toward its total.
        self.assertEqual(nodes["Centrul de studii"]["own_documents"], 0)
        self.assertEqual(nodes["Centrul de studii"]["total_documents"], 1)
        self.assertEqual(nodes["Centrul de studii"]["children"], ["Centrul de studii/Anatomie"])

        self.assertEqual(nodes["Centrul de studii/Anatomie"]["own_documents"], 1)
        self.assertEqual(nodes["Centrul de studii/Anatomie"]["label"], "Anatomie")
        self.assertEqual(nodes["Centrul de studii/Anatomie"]["parent"], "Centrul de studii")

        # The root category (files with no folder) and the whole-tree total.
        self.assertEqual(nodes[""]["own_documents"], 1)
        self.assertEqual(nodes[""]["total_documents"], 4)
        self.assertEqual(set(nodes[""]["children"]), {"Cancer", "Centrul de studii"})

    def test_root_children_are_sorted_case_insensitively(self):
        sources = [
            make_source("zebra/a.md", "zebra"),
            make_source("Alpha/b.md", "Alpha"),
            make_source("beta/c.md", "beta"),
        ]

        tree = categories.build_category_tree(sources)

        self.assertEqual(tree["nodes"][""]["children"], ["Alpha", "beta", "zebra"])

    def test_deeply_nested_folders_each_become_their_own_category(self):
        sources = [make_source("A/B/C/D/doc.md", "A/B/C/D")]

        tree = categories.build_category_tree(sources)

        self.assertEqual(set(tree["nodes"]), {"", "A", "A/B", "A/B/C", "A/B/C/D"})
        self.assertEqual(tree["nodes"]["A/B/C/D"]["total_documents"], 1)
        self.assertEqual(tree["nodes"]["A"]["total_documents"], 1)
        for ancestor in ("A", "A/B", "A/B/C"):
            self.assertEqual(tree["nodes"][ancestor]["own_documents"], 0)


class SyncTests(unittest.TestCase):
    def setUp(self):
        _fixture.reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "documents"
        self.source.mkdir()

    # Fetch every row of `documents`/`chunks`, sorted for stable assertions.
    def _rows(self, table: str, columns: str):
        with db_module.get_pool().connection() as connection:
            with connection.cursor(row_factory=namedtuple_row) as cursor:
                return cursor.execute(f"SELECT {columns} FROM {table} ORDER BY 1").fetchall()

    def _sync(self, model_name: str = builder.DEFAULT_MODEL):
        with mock.patch.object(builder, "create_embedding_model", return_value=object()), \
             mock.patch.object(builder, "embed_chunks", side_effect=fake_embed) as embed_mock, \
             redirect_stdout(io.StringIO()):
            builder.build(self.source, model_name, batch_size=64)
        return embed_mock

    # The vector width of the `chunks.embedding` column, as the catalog sees it.
    def _column_dimension(self) -> int:
        with db_module.get_pool().connection() as connection:
            return db_module._embedding_dimension(connection)

    def test_sync_writes_documents_and_chunks(self):
        (self.source / "document.md").write_text(
            "# Remedii\n\nCeai de mușețel și atenționări.", encoding="utf-8",
        )

        self._sync()

        documents = self._rows("documents", "relative_path, category_id")
        self.assertEqual(documents, [("document.md", "")])
        chunks = self._rows("chunks", "source_relative_path, category_id")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].category_id, "")

        with db_module.get_pool().connection() as connection:
            model_name = connection.execute(
                "SELECT value FROM sync_metadata WHERE key = 'model_name'"
            ).fetchone()[0]
        self.assertEqual(model_name, builder.DEFAULT_MODEL)

    def test_sync_stores_business_category_conditions_and_heading_per_fragment(self):
        (self.source / "carte.md").write_text(
            "# Carte\n## Gripa\nCeai de scortisoara.\n## Plante\nMenta ajută la febra.\n## Altele\nApă.",
            encoding="utf-8",
        )
        (self.source / "Febra.md").write_text("Repaus și lichide.", encoding="utf-8")

        with mock.patch.object(
            builder, "load_dictionary",
            return_value=ConditionDictionary(parse_conditions(conditions_jsonl("Gripa,gripe\nFebra\n"))),
        ):
            self._sync()

        rows = self._rows(
            "chunks",
            "source_relative_path, heading, business_category,"
            " primary_medical_conditions, secondary_medical_conditions",
        )
        by_key = {(row.source_relative_path, row.heading): row for row in rows}
        self.assertEqual(len(rows), 4)
        # The file name is not compared with the conditions: plain text is D1.
        febra_file = by_key[("Febra.md", "")]
        self.assertEqual(
            (febra_file.business_category, febra_file.primary_medical_conditions,
             febra_file.secondary_medical_conditions),
            ("D1", [], []),
        )
        gripa = by_key[("carte.md", "Carte > Gripa")]
        self.assertEqual((gripa.business_category, gripa.primary_medical_conditions), ("R1", ["Gripa"]))
        self.assertEqual(gripa.secondary_medical_conditions, [])
        plante = by_key[("carte.md", "Carte > Plante")]
        self.assertEqual(
            (plante.business_category, plante.primary_medical_conditions, plante.secondary_medical_conditions),
            ("R2", [], ["Febra"]),
        )
        rest = by_key[("carte.md", "Carte > Altele")]
        self.assertEqual((rest.business_category, rest.primary_medical_conditions), ("D1", []))

    def test_schema_replaces_the_conditions_column_and_is_idempotent(self):
        with db_module.get_pool().connection() as connection:
            connection.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS conditions TEXT[] NOT NULL DEFAULT '{}'")
            connection.commit()

        db_module.ensure_schema()
        db_module.ensure_schema()

        with db_module.get_pool().connection() as connection:
            columns = {
                row[0] for row in connection.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'chunks'"
                ).fetchall()
            }
        self.assertNotIn("conditions", columns)
        self.assertLessEqual(
            {"business_category", "primary_medical_conditions", "secondary_medical_conditions"}, columns
        )

    def test_business_category_only_accepts_r1_r2_d1(self):
        (self.source / "document.md").write_text("Text.", encoding="utf-8")
        self._sync()

        with db_module.get_pool().connection() as connection:
            with self.assertRaises(psycopg.errors.CheckViolation):
                connection.execute("UPDATE chunks SET business_category = 'R3'")

    def test_category_id_comes_from_containing_folder(self):
        (self.source / "Cancer").mkdir()
        (self.source / "Cancer" / "a.md").write_text("# A\n\nText despre tratament.", encoding="utf-8")

        self._sync()

        documents = self._rows("documents", "relative_path, category_id")
        self.assertEqual(documents, [("Cancer/a.md", "Cancer")])

    def test_second_sync_with_no_changes_skips_embedding_entirely(self):
        (self.source / "document.md").write_text("# Remedii\n\nText neschimbat.", encoding="utf-8")
        self._sync()

        second_call = self._sync()

        second_call.assert_not_called()

    def test_only_the_modified_file_is_reprocessed(self):
        (self.source / "a.md").write_text("# A\n\nConținut inițial pentru a.", encoding="utf-8")
        (self.source / "b.md").write_text("# B\n\nConținut neschimbat pentru b.", encoding="utf-8")
        self._sync()

        (self.source / "a.md").write_text("# A\n\nConținut modificat pentru a.", encoding="utf-8")
        embed_mock = self._sync()

        embedded_chunks = embed_mock.call_args.args[1]
        self.assertTrue(all(chunk.source_relative_path == "a.md" for chunk in embedded_chunks))
        chunks = self._rows("chunks", "source_relative_path, text")
        b_chunk = next(row for row in chunks if row.source_relative_path == "b.md")
        self.assertIn("neschimbat", b_chunk.text)
        a_chunk = next(row for row in chunks if row.source_relative_path == "a.md")
        self.assertIn("modificat", a_chunk.text)

    def test_bumping_text_repr_version_forces_a_full_resync(self):
        (self.source / "document.md").write_text("# Remedii\n\nText neschimbat.", encoding="utf-8")
        self._sync()

        # Simulate a document already synced under an older cleaning/chunking
        # representation: its own file hasn't changed, but the code's
        # TEXT_REPR_VERSION has moved on since.
        with db_module.get_pool().connection() as connection:
            connection.execute(
                "UPDATE sync_metadata SET value = %s WHERE key = 'text_repr_version'", ("0",),
            )
            connection.commit()

        embed_mock = self._sync()

        embed_mock.assert_called_once()
        embedded_chunks = embed_mock.call_args.args[1]
        self.assertTrue(any(chunk.source_relative_path == "document.md" for chunk in embedded_chunks))

        with db_module.get_pool().connection() as connection:
            stored = connection.execute(
                "SELECT value FROM sync_metadata WHERE key = 'text_repr_version'"
            ).fetchone()[0]
        self.assertEqual(stored, builder.TEXT_REPR_VERSION)

    # Register OTHER next to QWEN for one test, and put the column back to the
    # default width afterwards (the model change tests leave it at OTHER's).
    def _with_other_model(self):
        patcher = mock.patch.dict(PROFILES, {OTHER.name: OTHER})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(db_module.ensure_schema, QWEN.dimension)

    def test_changing_the_model_re_embeds_every_document_and_updates_the_metadata(self):
        self._with_other_model()
        (self.source / "a.md").write_text("# A\n\nConținut a.", encoding="utf-8")
        (self.source / "b.md").write_text("# B\n\nConținut b.", encoding="utf-8")
        self._sync(QWEN.name)

        embed_mock = self._sync(OTHER.name)

        embed_mock.assert_called_once()
        embedded = {chunk.source_relative_path for chunk in embed_mock.call_args.args[1]}
        self.assertEqual(embedded, {"a.md", "b.md"})
        self.assertIs(embed_mock.call_args.args[3], OTHER)
        with db_module.get_pool().connection() as connection:
            metadata = dict(connection.execute(
                "SELECT key, value FROM sync_metadata WHERE key IN ('model_name', 'model_dimension')"
            ).fetchall())
        self.assertEqual(metadata, {"model_name": OTHER.name, "model_dimension": str(OTHER.dimension)})

    def test_changing_the_model_recreates_the_vector_column_with_the_new_width(self):
        self._with_other_model()
        (self.source / "document.md").write_text("# Remedii\n\nText.", encoding="utf-8")
        self._sync(QWEN.name)
        self.assertEqual(self._column_dimension(), QWEN.dimension)

        self._sync(OTHER.name)

        self.assertEqual(self._column_dimension(), OTHER.dimension)
        self.assertEqual(len(self._rows("chunks", "chunk_id")), 1)
        with db_module.get_pool().connection() as connection:
            width = connection.execute("SELECT vector_dims(embedding) FROM chunks").fetchone()[0]
            nullable = connection.execute(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'chunks' AND column_name = 'embedding'"
            ).fetchone()[0]
        self.assertEqual(width, OTHER.dimension)
        self.assertEqual(nullable, "NO")

    def test_ensure_schema_without_a_dimension_never_touches_an_existing_index(self):
        (self.source / "document.md").write_text("# Remedii\n\nText.", encoding="utf-8")
        self._sync(QWEN.name)

        db_module.ensure_schema()
        db_module.ensure_schema(QWEN.dimension)

        self.assertEqual(len(self._rows("chunks", "chunk_id")), 1)

    def test_unknown_model_fails_before_touching_the_database(self):
        (self.source / "document.md").write_text("# Remedii\n\nText.", encoding="utf-8")
        self._sync(QWEN.name)

        with self.assertRaisesRegex(ValueError, "Unknown embedding model"):
            self._sync("nu/exista")

        self.assertEqual(len(self._rows("chunks", "chunk_id")), 1)

    def test_file_removed_from_source_is_deleted_from_the_index(self):
        (self.source / "a.md").write_text("# A\n\nConținut a.", encoding="utf-8")
        (self.source / "b.md").write_text("# B\n\nConținut b.", encoding="utf-8")
        self._sync()

        (self.source / "b.md").unlink()
        self._sync()

        documents = self._rows("documents", "relative_path, category_id")
        self.assertEqual(documents, [("a.md", "")])
        chunks = self._rows("chunks", "source_relative_path, text")
        self.assertTrue(all(row.source_relative_path == "a.md" for row in chunks))


if __name__ == "__main__":
    unittest.main()
