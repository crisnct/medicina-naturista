"""Tests for category-filtered hybrid ranking (medicina_naturista.ai.search.rank)."""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import numpy as np

from medicina_naturista.ai import search
from scripts import build_hybrid_index as builder


# A fake FastEmbed model whose query_embed always returns the same fixed
# vector, so rank()'s semantic ranking is fully deterministic in tests.
class FakeQueryModel:
    def __init__(self, vector: np.ndarray) -> None:
        self.vector = vector

    def query_embed(self, texts):
        for _ in texts:
            yield self.vector


def _one_hot(dimension: int, index: int, value: float = 1.0) -> np.ndarray:
    vector = np.zeros(dimension, dtype=np.float32)
    vector[index] = value
    return vector


# Build a small real hybrid index (same machinery as
# tests/unit/ai/test_build_hybrid_index.py's BuildArtifactTests) from
# `documents` (relative_path -> markdown text, one short chunk each) with a
# fixed embedding per document, so semantic ranking is fully controlled.
def _build_fixture_index(root: Path, documents: dict[str, str], vectors: dict[str, np.ndarray]) -> Path:
    source = root / "documents"
    output = root / "data"
    source.mkdir(parents=True)
    for relative_path, text in documents.items():
        path = source / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def fake_embed(_model, chunks, _batch_size):
        return np.asarray([vectors[chunk.source_relative_path] for chunk in chunks], dtype=np.float32)

    with (
        mock.patch.object(builder, "create_embedding_model", return_value=object()),
        mock.patch.object(builder, "embed_chunks", side_effect=fake_embed),
        redirect_stdout(io.StringIO()),
    ):
        builder.build(source, output, builder.DEFAULT_MODEL, batch_size=64)
    return output / "hybrid_index"


class CategoryFilteredRankTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        dim = builder.MODEL_DIMENSION
        # catB/three.md is the closest semantic match, catA/two.md second,
        # catA/one.md unrelated — chosen so query_vector (0, 0.6, 0.8) is
        # already unit length, giving exact cosine similarities.
        self.vectors = {
            "catA/one.md": _one_hot(dim, 0),
            "catA/two.md": _one_hot(dim, 1),
            "catB/three.md": _one_hot(dim, 2),
        }
        self.documents = {
            "catA/one.md": "# Doc\n\nText fără cuvântul căutat, doar umplutură nesemnificativă aici.",
            "catA/two.md": "# Doc\n\nAlt text fără cuvântul căutat, tot umplutură nesemnificativă aici.",
            "catB/three.md": "# Doc\n\nÎncă un text fără cuvântul căutat, umplutură nesemnificativă aici.",
        }
        self.index_dir = _build_fixture_index(self.root, self.documents, self.vectors)
        query_vector = np.zeros(dim, dtype=np.float32)
        query_vector[1] = 0.6
        query_vector[2] = 0.8
        self.create_model_patch = mock.patch.object(search, "create_model", return_value=FakeQueryModel(query_vector))
        self.create_model_patch.start()
        self.addCleanup(self.create_model_patch.stop)

    # A phrase absent from every document isolates the semantic signal (no
    # lexical match anywhere), so hybrid_score reduces to 1/(RRF_K + semantic_rank).
    def test_unfiltered_ranking_orders_by_full_index_semantic_rank(self):
        results = search.rank(self.index_dir, "propoziție absentă din orice document")

        order = [item["source_relative_path"] for item in results]
        self.assertEqual(order, ["catB/three.md", "catA/two.md", "catA/one.md"])
        two = next(item for item in results if item["source_relative_path"] == "catA/two.md")
        self.assertAlmostEqual(two["hybrid_score"], 1.0 / (search.RRF_K + 2))
        self.assertAlmostEqual(two["semantic_similarity"], 0.6, places=5)

    # The critical correctness property: filtering to "catA" must rank catA's
    # own two fragments against EACH OTHER (so catA/two.md becomes rank 1 of
    # 2), not just drop catB/three.md from the full-index ranking and keep its
    # original rank-2 position (which a "filter after ranking" implementation
    # would produce, and which would then be a rank 2 that no longer exists
    # relative to anything real).
    def test_category_filter_reranks_within_the_selected_subset(self):
        results = search.rank(
            self.index_dir,
            "propoziție absentă din orice document",
            category_ids=frozenset({"catA"}),
        )

        order = [item["source_relative_path"] for item in results]
        self.assertEqual(order, ["catA/two.md", "catA/one.md"])
        two = next(item for item in results if item["source_relative_path"] == "catA/two.md")
        # Rank 1 of the *filtered* subset, not its unfiltered rank of 2.
        self.assertAlmostEqual(two["hybrid_score"], 1.0 / (search.RRF_K + 1))
        self.assertAlmostEqual(two["semantic_similarity"], 0.6, places=5)

    def test_category_filter_excludes_other_categories_entirely(self):
        results = search.rank(
            self.index_dir,
            "propoziție absentă din orice document",
            category_ids=frozenset({"catA"}),
        )

        self.assertNotIn("catB/three.md", [item["source_relative_path"] for item in results])

    # A lexical match outside the filtered categories must not leave a gap in
    # the ranks assigned to matches inside it: with two matching documents
    # unfiltered (catB ranks first, being the shorter/stronger bm25 match),
    # filtering down to catA alone must renumber its match to lexical_rank 1.
    def test_lexical_rank_has_no_gap_after_filtering(self):
        padding = " ".join(["cuvinte", "de", "umplutură", "fără", "legătură"] * 12)
        documents = {
            "catA/one.md": f"# Doc\n\nText cu fraza cautata aici. {padding}",
            "catB/short.md": "# Doc\n\nfraza cautata",
            "catC/unrelated.md": "# Doc\n\nText complet diferit, fără nimic relevant.",
        }
        vectors = {
            "catA/one.md": _one_hot(builder.MODEL_DIMENSION, 0),
            "catB/short.md": _one_hot(builder.MODEL_DIMENSION, 1),
            "catC/unrelated.md": _one_hot(builder.MODEL_DIMENSION, 2),
        }
        index_dir = _build_fixture_index(self.root / "second", documents, vectors)

        unfiltered = search.rank(index_dir, "fraza cautata")
        one_unfiltered = next(item for item in unfiltered if item["source_relative_path"] == "catA/one.md")
        self.assertEqual(one_unfiltered["lexical_rank"], 2)

        filtered = search.rank(index_dir, "fraza cautata", category_ids=frozenset({"catA"}))
        one_filtered = next(item for item in filtered if item["source_relative_path"] == "catA/one.md")
        self.assertEqual(one_filtered["lexical_rank"], 1)
        self.assertTrue(one_filtered["found_by_lexical"])

    # None and an empty frozenset must both behave exactly like "no filter" —
    # the shared default every existing caller relies on.
    def test_no_filter_and_empty_filter_are_equivalent_to_none(self):
        baseline = search.rank(self.index_dir, "propoziție absentă din orice document")
        empty = search.rank(self.index_dir, "propoziție absentă din orice document", category_ids=frozenset())

        self.assertEqual(
            [item["source_relative_path"] for item in baseline],
            [item["source_relative_path"] for item in empty],
        )


if __name__ == "__main__":
    unittest.main()
