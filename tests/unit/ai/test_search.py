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
from medicina_naturista.ai.conditions import ConditionDictionary, parse_conditions
from tests.support.postgres import PostgresFixture
from scripts import build_hybrid_index as builder

_fixture = PostgresFixture()


def setUpModule():
    _fixture.start()


def tearDownModule():
    _fixture.stop()


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


# Sync a small real hybrid index into the test Postgres (same machinery as
# tests/unit/ai/test_build_hybrid_index.py) from `documents`
# (relative_path -> markdown text, one short chunk each) with a fixed
# embedding per document, so semantic ranking is fully controlled.
def _build_fixture_index(root: Path, documents: dict[str, str], vectors: dict[str, np.ndarray]) -> None:
    source = root / "documents"
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
        builder.build(source, builder.DEFAULT_MODEL, batch_size=64)


class CategoryFilteredRankTests(unittest.TestCase):
    def setUp(self):
        _fixture.reset()
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
        _build_fixture_index(self.root, self.documents, self.vectors)
        query_vector = np.zeros(dim, dtype=np.float32)
        query_vector[1] = 0.6
        query_vector[2] = 0.8
        self.create_model_patch = mock.patch.object(
            search, "cached_query_model", return_value=FakeQueryModel(query_vector)
        )
        self.create_model_patch.start()
        self.addCleanup(self.create_model_patch.stop)

    # A phrase absent from every document isolates the semantic signal (no
    # lexical match anywhere), so hybrid_score reduces to 1/(RRF_K + semantic_rank).
    def test_unfiltered_ranking_orders_by_full_index_semantic_rank(self):
        results = search.rank("propoziție absentă din orice document")

        order = [item["source_relative_path"] for item in results]
        self.assertEqual(order, ["catB/three.md", "catA/two.md", "catA/one.md"])
        two = next(item for item in results if item["source_relative_path"] == "catA/two.md")
        # These queries name no condition, so every fragment is PRIORITY 10, whose weight scales the RRF score.
        self.assertAlmostEqual(two["hybrid_score"], search.PRIORITY_WEIGHT[10] / (search.RRF_K + 2))
        self.assertAlmostEqual(two["semantic_similarity"], 0.6, places=5)

    # The critical correctness property: filtering to "catA" must rank catA's
    # own two fragments against EACH OTHER (so catA/two.md becomes rank 1 of
    # 2), not just drop catB/three.md from the full-index ranking and keep its
    # original rank-2 position (which a "filter after ranking" implementation
    # would produce, and which would then be a rank 2 that no longer exists
    # relative to anything real).
    def test_category_filter_reranks_within_the_selected_subset(self):
        results = search.rank(
            "propoziție absentă din orice document",
            category_ids=frozenset({"catA"}),
        )

        order = [item["source_relative_path"] for item in results]
        self.assertEqual(order, ["catA/two.md", "catA/one.md"])
        two = next(item for item in results if item["source_relative_path"] == "catA/two.md")
        # Rank 1 of the *filtered* subset, not its unfiltered rank of 2.
        self.assertAlmostEqual(two["hybrid_score"], search.PRIORITY_WEIGHT[10] / (search.RRF_K + 1))
        self.assertAlmostEqual(two["semantic_similarity"], 0.6, places=5)

    def test_category_filter_excludes_other_categories_entirely(self):
        results = search.rank(
            "propoziție absentă din orice document",
            category_ids=frozenset({"catA"}),
        )

        self.assertNotIn("catB/three.md", [item["source_relative_path"] for item in results])

    # A lexical match outside the filtered categories must not leave a gap in
    # the ranks assigned to matches inside it: with two matching documents
    # unfiltered (catB ranks first, being the shorter/stronger match),
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
        _fixture.reset()
        _build_fixture_index(self.root / "second", documents, vectors)

        unfiltered = search.rank("fraza cautata")
        one_unfiltered = next(item for item in unfiltered if item["source_relative_path"] == "catA/one.md")
        self.assertEqual(one_unfiltered["lexical_rank"], 2)

        filtered = search.rank("fraza cautata", category_ids=frozenset({"catA"}))
        one_filtered = next(item for item in filtered if item["source_relative_path"] == "catA/one.md")
        self.assertEqual(one_filtered["lexical_rank"], 1)
        self.assertTrue(one_filtered["found_by_lexical"])

    # None and an empty frozenset must both behave exactly like "no filter" —
    # the shared default every existing caller relies on.
    def test_no_filter_and_empty_filter_are_equivalent_to_none(self):
        baseline = search.rank("propoziție absentă din orice document")
        empty = search.rank("propoziție absentă din orice document", category_ids=frozenset())

        self.assertEqual(
            [item["source_relative_path"] for item in baseline],
            [item["source_relative_path"] for item in empty],
        )


class LexicalQueryTests(unittest.TestCase):
    def test_words_become_prefix_stems_joined_with_and(self):
        strict, loose = search.lexical_queries("durere de genunchi")

        self.assertEqual(strict, "(dure:* & genunc:*)")
        self.assertEqual(loose, "dure:* | genunc:*")

    def test_generic_and_tiny_words_are_dropped(self):
        strict, _ = search.lexical_queries("acest guta")

        self.assertEqual(strict, "(guta:*)")

    def test_short_query_keeps_its_words(self):
        strict, _ = search.lexical_queries("HPV")

        self.assertEqual(strict, "(hpv:*)")

    def test_comma_separated_segments_are_or_ed(self):
        strict, _ = search.lexical_queries("artroza genunchi, guta")

        self.assertEqual(strict, "(artro:* & genunc:*) | (guta:*)")

    def test_diacritics_and_syntax_characters_never_reach_the_tsquery(self):
        strict, loose = search.lexical_queries("gută'; DROP TABLE chunks; --")

        self.assertNotIn("'", strict + loose)
        self.assertNotIn(";", strict + loose)
        self.assertTrue(strict.startswith("(guta:*"))

    def test_expansions_are_extra_or_groups_in_strict_but_not_in_loose(self):
        strict, loose = search.lexical_queries("gout", expansions=["artrita gutoasa", "guta articulara"])

        self.assertEqual(strict, "(gout:*) | (artri:* & gutoa:*) | (guta:* & articula:*)")
        self.assertEqual(loose, "gout:*")

    def test_expansion_duplicating_the_query_is_ignored(self):
        strict, _ = search.lexical_queries("gout", expansions=["Gout"])

        self.assertEqual(strict, "(gout:*)")

    def test_text_without_words_has_no_query(self):
        self.assertEqual(search.lexical_queries("?! ,"), (None, None))


class CandidateLimitedRankTests(unittest.TestCase):
    def setUp(self):
        _fixture.reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        dim = builder.MODEL_DIMENSION
        self.documents = {
            "boli/Guta.md": "# Guta\n\nCeai de urzica si dieta pentru guta.",
            "boli/Digestie.md": "# Digestie\n\nBiscuiti, pâine, orez, mere si alte alimente obisnuite aici.",
            "boli/Somn.md": "# Somn\n\nMuzica calma, liniste si odihna pe timpul noptii aici.",
            "boli/Piele.md": "# Piele\n\nCrema cu galbenele si aloe pentru pielea uscata aici.",
        }
        self.vectors = {
            "boli/Guta.md": _one_hot(dim, 0),
            "boli/Digestie.md": _one_hot(dim, 1),
            "boli/Somn.md": _one_hot(dim, 2),
            "boli/Piele.md": _one_hot(dim, 3),
        }
        _build_fixture_index(Path(self.tmp.name), self.documents, self.vectors)
        # The query vector is closest to Digestie, then Somn, then Piele; Guta is last.
        query_vector = np.zeros(dim, dtype=np.float32)
        query_vector[1], query_vector[2], query_vector[3] = 0.8, 0.5, 0.33
        query_vector /= np.linalg.norm(query_vector)
        patch = mock.patch.object(search, "cached_query_model", return_value=FakeQueryModel(query_vector))
        patch.start()
        self.addCleanup(patch.stop)

    def _paths(self, results):
        return [item["source_relative_path"] for item in results]

    # Only the semantic top-`limit` is returned when nothing matches lexically:
    # the rest of the index is not fetched or scored at all.
    def test_semantic_candidates_are_capped_at_limit(self):
        results = search.rank("propoziție absentă din orice document", limit=2)

        self.assertEqual(self._paths(results), ["boli/Digestie.md", "boli/Somn.md"])

    # A fragment outside the semantic top-`limit` still surfaces when the
    # lexical signal finds it, and reports its own semantic similarity.
    def test_lexical_match_outside_semantic_limit_is_included(self):
        results = search.rank("guta", limit=2)

        self.assertIn("boli/Guta.md", self._paths(results))
        guta = next(item for item in results if item["source_relative_path"] == "boli/Guta.md")
        self.assertTrue(guta["found_by_lexical"])
        self.assertAlmostEqual(guta["semantic_similarity"], 0.0, places=5)

    # The index uses the 'simple' text-search config, so inflected forms only
    # match through the prefix stem: "genunchi" finds "genunchiului".
    def test_prefix_stem_matches_inflected_form(self):
        _fixture.reset()
        documents = {"boli/Genunchi.md": "# Articulatii\n\nDurerea genunchiului la urcarea scarilor si la efort."}
        vectors = {"boli/Genunchi.md": _one_hot(builder.MODEL_DIMENSION, 0)}
        _build_fixture_index(Path(self.tmp.name) / "second", documents, vectors)

        results = search.rank("genunchi")

        self.assertTrue(results[0]["found_by_lexical"])

    # Every content word is required first; the loose any-word query only
    # widens the candidates when the strict one finds fewer than
    # MIN_STRICT_LEXICAL_HITS.
    def test_loose_query_widens_when_strict_finds_too_little(self):
        results = search.rank("guta galbenele", limit=1)

        matched = [item["source_relative_path"] for item in results if item["found_by_lexical"]]
        self.assertEqual(len(matched), 1)

    # A section whose heading names the condition gets the heading signal even
    # when the body text matches nothing else.
    def test_heading_match_is_a_separate_signal(self):
        results = search.rank("Digestie", limit=1)

        digestie = next(item for item in results if item["source_relative_path"] == "boli/Digestie.md")
        self.assertTrue(digestie["found_by_heading"])
        self.assertGreater(digestie["hybrid_score"], search.PRIORITY_WEIGHT[10] / (search.RRF_K + 1))

    # A section titled with a synonym is found through the expansion even
    # though the query text itself matches nothing in it.
    def test_expansion_finds_section_named_by_a_synonym(self):
        without = search.rank("podagra", limit=1)
        with_expansion = search.rank("podagra", limit=1, expansions=["Guta"])

        self.assertFalse(any(item["source_relative_path"] == "boli/Guta.md" and item["found_by_heading"] for item in without))
        guta = next(item for item in with_expansion if item["source_relative_path"] == "boli/Guta.md")
        self.assertTrue(guta["found_by_heading"])
        self.assertTrue(guta["found_by_lexical"])

    def test_hybrid_score_never_exceeds_rrf_max_score(self):
        results = search.rank("Guta")

        self.assertLessEqual(max(item["hybrid_score"] for item in results), search.RRF_MAX_SCORE + 1e-12)


class PriorityWeightTests(unittest.TestCase):
    NAMES = ["Gripa", "influenza", "gripa sezoniera"]

    def setUp(self):
        _fixture.reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        dim = builder.MODEL_DIMENSION
        body = "Ceai calduros si repaus la pat pentru remedii naturiste."
        documents = {
            "a/Plante.md": f"# Plante\n## Ceaiuri\n{body}",  # neither heading nor text names it
            "a/Carte.md": f"# Carte\n## Ceaiuri\n{body} Util si pentru influenza.",  # synonym in text
            "a/Sezon.md": f"# Carte\n## Gripa sezoniera\n{body}",  # synonym in the heading path
        }
        # Query vector e0: semantic rank 1 is Plante, 2 is Carte, 3 is Sezon.
        vectors = {
            "a/Plante.md": _one_hot(dim, 0),
            "a/Carte.md": _one_hot(dim, 0, 0.8) + _one_hot(dim, 1, 0.6),
            "a/Sezon.md": _one_hot(dim, 0, 0.6) + _one_hot(dim, 1, 0.8),
        }
        _build_fixture_index(Path(self.tmp.name), documents, vectors)
        patch = mock.patch.object(search, "cached_query_model", return_value=FakeQueryModel(_one_hot(dim, 0)))
        patch.start()
        self.addCleanup(patch.stop)

    def test_weights_per_priority(self):
        self.assertEqual(search.PRIORITY_WEIGHT, {1: 1.0, 3: 0.7, 10: 0.2})

    def test_priority_comes_from_the_searched_condition_and_its_synonyms(self):
        # The query text itself matches nothing lexically: only the semantic signal counts.
        results = search.rank("propoziție absentă din orice document", condition_names=self.NAMES)

        self.assertEqual(
            [(item["source_relative_path"], item["priority"]) for item in results],
            [("a/Sezon.md", 1), ("a/Carte.md", 3), ("a/Plante.md", 10)],
        )
        scores = [item["hybrid_score"] for item in results]
        self.assertAlmostEqual(scores[0], 1.0 / (search.RRF_K + 3))
        self.assertAlmostEqual(scores[1], 0.7 / (search.RRF_K + 2))
        self.assertAlmostEqual(scores[2], 0.2 / (search.RRF_K + 1))

    def test_a_condition_missing_from_the_dictionary_is_searched_as_typed(self):
        # No condition names, so no synonyms: the query itself is matched against
        # each fragment's heading path (1) and text (3).
        results = search.rank("Gripa sezoniera")

        by_path = {item["source_relative_path"]: item["priority"] for item in results}
        self.assertEqual(by_path, {"a/Sezon.md": 1, "a/Carte.md": 10, "a/Plante.md": 10})

    def test_a_query_matching_nothing_gives_every_fragment_priority_10(self):
        results = search.rank("propoziție absentă din orice document")

        self.assertEqual({item["priority"] for item in results}, {10})
        self.assertAlmostEqual(results[0]["hybrid_score"], search.PRIORITY_WEIGHT[10] / (search.RRF_K + 1))

    def test_results_carry_the_indexed_conditions(self):
        results = search.rank("propoziție absentă din orice document", condition_names=self.NAMES)

        self.assertTrue(all(isinstance(item["conditions"], list) for item in results))


if __name__ == "__main__":
    unittest.main()
