from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import numpy as np

from scripts import build_hybrid_index as builder


def make_chunk(chunk_id: int, text: str = "text") -> builder.Chunk:
    return builder.Chunk(
        chunk_id=chunk_id,
        embedding_row=chunk_id - 1,
        source_relative_path="document.md",
        source_absolute_path="C:/documents/document.md",
        source_sha256="source-hash",
        line_start=1,
        line_end=1,
        heading="Titlu",
        text=text,
        text_sha256=f"text-hash-{chunk_id}",
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
            vector = np.zeros(builder.MODEL_DIMENSION, dtype=np.float32)
            vector[index % builder.MODEL_DIMENSION] = 1.0
            yield vector


class ChunkingTests(unittest.TestCase):
    def test_normalize_text_preserves_composed_romanian_diacritics(self):
        decomposed = "s\u0326i t\u0326erapie\r\n"

        self.assertEqual(builder.normalize_text(decomposed), "și țerapie\n")

    def test_chunks_never_cross_markdown_heading_boundaries(self):
        text = (
            "# Document\n\nIntroducere scurtă.\n\n"
            "## Secțiunea A\n\nTratamentul A și atenționările sale.\n\n"
            "## Secțiunea B\n\nTratamentul B și contraindicațiile sale."
        )

        chunks = builder.chunk_document(text)

        self.assertEqual(len(chunks), 3)
        self.assertEqual(
            [heading for _, _, _, heading in chunks],
            ["Document", "Document > Secțiunea A", "Document > Secțiunea B"],
        )
        self.assertTrue(all(not chunk_text.startswith("#") for chunk_text, *_ in chunks))
        self.assertFalse(any("Tratamentul A" in item[0] and "Tratamentul B" in item[0] for item in chunks))

    def test_page_headings_keep_one_sentence_of_soft_overlap(self):
        previous_context = "Contextul anterior rămâne pe prima pagină."
        bridge_sentence = "Această propoziție continuă ideea medicală."
        text = (
            "# Document\n\n## Pagini\n\n### Pagina 1\n\n"
            f"{previous_context} {bridge_sentence}\n\n"
            "### Pagina 2\n\nTratamentul continuă pe pagina următoare."
        )

        chunks = builder.chunk_document(text)

        self.assertEqual(len(chunks), 2)
        self.assertIn(previous_context, chunks[0][0])
        self.assertEqual(
            chunks[1][0],
            f"{bridge_sentence}\n\nTratamentul continuă pe pagina următoare.",
        )
        self.assertEqual([item[3] for item in chunks], ["Document > Pagini", "Document > Pagini"])
        self.assertNotIn("Pagina 1", chunks[0][3])
        self.assertNotIn("Pagina 2", chunks[1][3])

    def test_chunks_respect_hard_limit_without_overlap_only_duplicates(self):
        paragraphs = [f"Paragraful {index}: " + (chr(65 + index) * 125) for index in range(18)]
        text = "# Secțiune\n\n" + "\n\n".join(paragraphs)

        chunks = builder.chunk_document(text)
        chunk_texts = [item[0] for item in chunks]

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(value) <= builder.MAX_CHARS for value in chunk_texts))
        self.assertTrue(all(left != right for left, right in zip(chunk_texts, chunk_texts[1:])))
        self.assertTrue(all(paragraph in "\n\n".join(chunk_texts) for paragraph in paragraphs))

    def test_oversized_content_prefers_readable_boundaries(self):
        sentences = [f"Propoziția {index} conține informații medicale relevante." for index in range(80)]
        text = "# Tratament\n\n" + " ".join(sentences)

        chunks = builder.chunk_document(text)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(item[0]) <= builder.MAX_CHARS for item in chunks))
        self.assertTrue(all(item[0].endswith(".") for item in chunks))
        self.assertEqual(chunks[0][1:], (3, 3, "Tratament"))

    def test_lists_and_tables_remain_intact_when_they_fit(self):
        list_block = "- Ceai de mușețel\n- Tinctură de gălbenele\n- Repaus"
        table_block = "| Plantă | Utilizare |\n|---|---|\n| Mușețel | Infuzie |"
        text = f"# Recomandări\n\n{list_block}\n\n{table_block}"

        chunks = builder.chunk_document(text)

        self.assertEqual(len(chunks), 1)
        self.assertIn(list_block, chunks[0][0])
        self.assertIn(table_block, chunks[0][0])
        self.assertEqual(chunks[0][1:3], (3, 9))

    def test_oversized_list_splits_only_between_complete_items(self):
        items = [f"- Recomandarea {index}: " + ("detaliu " * 20).strip() for index in range(20)]
        text = "# Recomandări\n\n" + "\n".join(items)

        chunks = builder.chunk_document(text)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(item[0]) <= builder.MAX_CHARS for item in chunks))
        emitted_lines = [line for item in chunks for line in item[0].splitlines()]
        self.assertEqual(emitted_lines, items)

    def test_chunk_line_ranges_cover_their_source_content(self):
        text = "# Document\n\nPrima informație.\n\n## Capitol\n\nA doua informație."
        source_lines = text.splitlines()

        for chunk_text, line_start, line_end, _ in builder.chunk_document(text):
            source_excerpt = "\n".join(source_lines[line_start - 1:line_end])
            for paragraph in chunk_text.split("\n\n"):
                self.assertIn(paragraph, source_excerpt)

    def test_splitting_a_blank_line_free_block_gives_each_piece_its_own_range(self):
        # A table-like block with no blank lines between rows (e.g. a spreadsheet
        # converted to Markdown) is one huge block to markdown_blocks(). Every
        # piece split out of it must get its own line range, not the whole
        # block's range, or reading a piece's "context" back from disk pulls in
        # the entire table.
        rows = [f"| Rând {index} | Valoare {index} |" for index in range(400)]
        text = "# Tabel\n\n" + "\n".join(rows)
        source_lines = text.splitlines()

        chunks = builder.chunk_document(text)

        self.assertGreater(len(chunks), 1)
        ranges = [(line_start, line_end) for _, line_start, line_end, _ in chunks]
        self.assertGreater(len(set(ranges)), 1)
        for chunk_text, line_start, line_end, _ in chunks:
            self.assertLessEqual(line_end - line_start, len(chunk_text.splitlines()) + 1)
            source_excerpt = "\n".join(source_lines[line_start - 1:line_end])
            for row_line in chunk_text.splitlines():
                self.assertIn(row_line, source_excerpt)


class EmbeddingProgressTests(unittest.TestCase):
    def test_reports_periodic_progress_and_completion(self):
        chunks = [make_chunk(index) for index in range(1, 4)]
        output = io.StringIO()

        with redirect_stdout(output):
            embeddings = builder.embed_chunks(
                FakeEmbeddingModel(3),
                chunks,
                batch_size=64,
                clock=FakeClock(0.0, 3.0, 11.0, 12.0, 15.0),
            )

        log = output.getvalue()
        self.assertIn("Embedding progress: 2/3 (66.7%)", log)
        self.assertIn("elapsed 00:00:11", log)
        self.assertIn("ETA 00:00:05", log)
        self.assertIn("Embedding completed: 3/3 (100.0%)", log)
        self.assertEqual(embeddings.shape, (3, builder.MODEL_DIMENSION))
        np.testing.assert_allclose(np.linalg.norm(embeddings, axis=1), np.ones(3))

    def test_short_run_still_reports_completion(self):
        output = io.StringIO()

        with redirect_stdout(output):
            builder.embed_chunks(
                FakeEmbeddingModel(1),
                [make_chunk(1)],
                batch_size=64,
                clock=FakeClock(0.0, 1.0, 2.0),
            )

        log = output.getvalue()
        self.assertNotIn("Embedding progress:", log)
        self.assertIn("Embedding completed: 1/1 (100.0%)", log)

    def test_embedding_failure_is_propagated_without_false_completion(self):
        output = io.StringIO()

        with self.assertRaisesRegex(RuntimeError, "embedding failed"), redirect_stdout(output):
            builder.embed_chunks(
                FakeEmbeddingModel(3, fail_after=1),
                [make_chunk(index) for index in range(1, 4)],
                batch_size=64,
                clock=FakeClock(0.0, 11.0),
            )

        self.assertNotIn("Embedding completed", output.getvalue())


class BuildArtifactTests(unittest.TestCase):
    def test_build_writes_complete_index_to_hybrid_index_with_fragments_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "documents"
            output = root / "data"
            source.mkdir()
            (source / "document.md").write_text(
                "# Remedii\n\nCeai de mușețel și atenționări.",
                encoding="utf-8",
            )

            def fake_embed(_model, chunks, _batch_size):
                vectors = np.ones((len(chunks), builder.MODEL_DIMENSION), dtype=np.float32)
                vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
                return vectors

            with (
                mock.patch.object(builder, "create_embedding_model", return_value=object()),
                mock.patch.object(builder, "embed_chunks", side_effect=fake_embed),
                redirect_stdout(io.StringIO()),
            ):
                builder.build(source, output, builder.DEFAULT_MODEL, batch_size=64)

            index_dir = output / "hybrid_index"
            self.assertTrue(index_dir.is_dir())
            self.assertTrue((index_dir / "fragments.jsonl").is_file())
            self.assertFalse((index_dir / "chunks.jsonl").exists())
            self.assertEqual(
                {path.name for path in index_dir.iterdir()},
                {
                    "SHA256SUMS.txt",
                    "embeddings.npy",
                    "fragments.jsonl",
                    "index.sqlite3",
                    "manifest.json",
                    "source_manifest.jsonl",
                },
            )
            manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["index"]["fragments"], "fragments.jsonl")
            checksums = (index_dir / "SHA256SUMS.txt").read_text(encoding="ascii")
            self.assertIn("  fragments.jsonl\n", checksums)
            self.assertNotIn("chunks.jsonl", checksums)


if __name__ == "__main__":
    unittest.main()
