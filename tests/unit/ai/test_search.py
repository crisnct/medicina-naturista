"""Tests for the combined fragment score (medicina_naturista.ai.search): the
lexical query, the P1 > P2 > P3 > P4 priorities of rank(), the context budget
and the category filter."""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import numpy as np

from medicina_naturista.ai import conditions, search
from medicina_naturista.ai.conditions import ConditionDictionary, parse_conditions
from tests.support.postgres import PostgresFixture
from scripts import build_hybrid_index as builder

_fixture = PostgresFixture()
DIM = builder.MODEL_DIMENSION

# Made-up conditions, so the tests do not depend on the shipped dictionary.
DICTIONARY_TEXT = "Zorbita,zorbitoza,zorbit disease\nVertigo,ameteala\n"


def setUpModule():
    _fixture.start()


def tearDownModule():
    _fixture.stop()


def _dictionary() -> ConditionDictionary:
    return ConditionDictionary(parse_conditions(DICTIONARY_TEXT))


# A fake FastEmbed model whose query_embed always returns the same fixed
# vector, so rank()'s semantic signal is fully deterministic in tests.
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


# A unit vector whose cosine similarity to e0 (the query vector of these tests) is `cosine`.
def _vector_with_cosine(dimension: int, cosine: float, orthogonal_axis: int = 1) -> np.ndarray:
    vector = _one_hot(dimension, 0, cosine)
    vector[orthogonal_axis] = float(np.sqrt(1.0 - cosine * cosine))
    return vector


# Sync a small real hybrid index into the test Postgres (same machinery as
# tests/unit/ai/test_build_hybrid_index.py) from `documents`
# (relative_path -> markdown text) with a fixed embedding per document, so the
# semantic signal is controlled and the conditions come from DICTIONARY_TEXT.
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
        mock.patch.object(builder, "load_dictionary", return_value=_dictionary()),
        redirect_stdout(io.StringIO()),
    ):
        builder.build(source, builder.DEFAULT_MODEL, batch_size=64)


def _paths(results) -> list[str]:
    return [item["source_relative_path"] for item in results]


def _lexical(text: str) -> str | None:
    return search.lexical_query(_dictionary().resolve(text))


class LexicalQueryTests(unittest.TestCase):
    def test_words_become_prefix_stems_joined_with_and(self):
        self.assertEqual(_lexical("durere de genunchi"), "(dure:* & genunc:*)")

    def test_generic_and_tiny_words_are_dropped(self):
        self.assertEqual(_lexical("acest guta"), "(guta:*)")

    def test_short_query_keeps_its_words(self):
        self.assertEqual(_lexical("HPV"), "(hpv:*)")

    def test_comma_separated_expressions_are_or_ed_and_their_words_and_ed(self):
        self.assertEqual(_lexical("artroza genunchi, guta"), "(artro:* & genunc:*) | (guta:*)")

    def test_diacritics_and_syntax_characters_never_reach_the_tsquery(self):
        query = _lexical("gută'; DROP TABLE chunks; --")

        self.assertNotIn("'", query)
        self.assertNotIn(";", query)
        self.assertTrue(query.startswith("(guta:*"))

    def test_text_without_words_has_no_query(self):
        self.assertIsNone(_lexical("?! ,"))

    def test_a_condition_is_replaced_by_an_or_of_its_names(self):
        self.assertEqual(
            _lexical("zorbita"),
            "(((zorbi:*) | (zorbito:*) | (zorb:* & disea:*)))",
        )

    def test_synonyms_never_let_a_fragment_skip_the_other_words(self):
        # "tratament" and "copii" stay AND-ed with the whole group of names,
        # instead of the names being OR-ed with the segment as separate groups.
        self.assertEqual(
            _lexical("tratament pentru zorbita la copii"),
            "(tratame:* & copii:* & ((zorbi:*) | (zorbito:*) | (zorb:* & disea:*)))",
        )

    def test_the_conditions_of_each_expression_are_resolved_separately(self):
        query = _lexical("durere de genunchi la efort, vertigo")

        self.assertEqual(query, "(dure:* & genunc:* & efort:*) | (((verti:*) | (ametea:*)))")


class WeightTests(unittest.TestCase):
    # The priorities are strict where it matters: a fragment with the condition
    # in its title beats any combination of the lower signals, and the
    # condition in the text beats lexical + semantic together.
    def test_weights_keep_the_priority_order(self):
        self.assertGreater(
            search.WEIGHT_PRIMARY,
            search.WEIGHT_SECONDARY + search.WEIGHT_LEXICAL + search.WEIGHT_SEMANTIC,
        )
        self.assertGreater(search.WEIGHT_SECONDARY, search.WEIGHT_LEXICAL + search.WEIGHT_SEMANTIC)
        self.assertGreater(search.WEIGHT_LEXICAL, search.WEIGHT_SEMANTIC)

    def test_max_score_is_the_sum_of_the_weights(self):
        self.assertEqual(search.MAX_SCORE, 15)


class RankTestCase(unittest.TestCase):
    documents: dict[str, str] = {}
    vectors: dict[str, np.ndarray] = {}

    def setUp(self):
        _fixture.reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        _build_fixture_index(Path(self.tmp.name), self.documents, self.vectors)
        # Every query is embedded as e0; a document's vector decides its cosine.
        for target, value in (
            (search, mock.patch.object(search, "cached_query_model", return_value=FakeQueryModel(_one_hot(builder.MODEL_DIMENSION, 0)))),
            (conditions, mock.patch.object(conditions, "load_dictionary", return_value=_dictionary())),
        ):
            value.start()
            self.addCleanup(value.stop)

    def by_path(self, results) -> dict[str, dict]:
        return {item["source_relative_path"]: item for item in results}


class PriorityRankTests(RankTestCase):
    documents = {
        # R1: the condition is in the title; its text never names it.
        "catA/titlu.md": "# Zorbita\n\nRepaus si ceai calduros la pat.",
        # R2: the condition is in the text only.
        "catA/text.md": "# Plante\n\nCeaiul de musetel ajuta in zorbita usoara.",
        # R2 through a synonym of the condition.
        "catB/sinonim.md": "# Alte\n\nZorbitoza se trateaza cu odihna.",
        # Lexical hit on the prefix only ("zorbicul" is not the condition).
        "catB/prefix.md": "# Diverse\n\nZorbicul este altceva.",
        # Nothing about the condition, but the semantically closest fragment.
        "catB/neutru.md": "# Diverse\n\nMuzica calma si liniste pe timpul noptii.",
        "catB/altul.md": "# Diverse\n\nCeva complet diferit despre gradinarit.",
    }
    vectors = {
        "catA/titlu.md": _one_hot(DIM, 5),  # cosine 0
        "catA/text.md": _one_hot(DIM, 6),  # cosine 0
        "catB/sinonim.md": _one_hot(DIM, 7),  # cosine 0
        "catB/prefix.md": _one_hot(DIM, 0),  # cosine 1
        "catB/neutru.md": _vector_with_cosine(DIM, 0.9),
        "catB/altul.md": _one_hot(DIM, 8),  # cosine 0
    }

    def test_condition_in_title_ranks_first_whatever_the_other_signals_say(self):
        results = search.rank("zorbita")

        self.assertEqual(results[0]["source_relative_path"], "catA/titlu.md")
        first = results[0]
        self.assertTrue(first["condition_in_title"])
        self.assertFalse(first["condition_in_text"])
        self.assertAlmostEqual(first["semantic_score"], 0.0)
        self.assertGreaterEqual(first["score"], search.WEIGHT_PRIMARY)

    def test_condition_in_text_beats_lexical_plus_semantic(self):
        results = self.by_path(search.rank("zorbita"))

        text, sinonim, prefix = results["catA/text.md"], results["catB/sinonim.md"], results["catB/prefix.md"]
        self.assertTrue(text["condition_in_text"])
        self.assertTrue(sinonim["condition_in_text"])  # a synonym in the text counts as the condition
        # The prefix-only fragment has the best possible cosine and a lexical hit,
        # yet stays below the fragments that name the condition.
        self.assertFalse(prefix["condition_in_text"])
        self.assertTrue(prefix["found_by_lexical"])
        self.assertAlmostEqual(prefix["semantic_score"], 1.0)
        self.assertGreater(text["score"], prefix["score"])
        self.assertGreater(sinonim["score"], prefix["score"])

    def test_order_is_title_then_text_then_the_rest(self):
        order = _paths(search.rank("zorbita"))

        self.assertEqual(order[0], "catA/titlu.md")
        self.assertLess(order.index("catA/text.md"), order.index("catB/prefix.md"))
        self.assertLess(order.index("catB/sinonim.md"), order.index("catB/prefix.md"))
        self.assertLess(order.index("catB/prefix.md"), order.index("catB/neutru.md"))

    def test_score_is_the_weighted_sum_and_results_are_sorted_by_it(self):
        results = search.rank("zorbita")

        for item in results:
            expected = (
                search.WEIGHT_PRIMARY * item["condition_in_title"]
                + search.WEIGHT_SECONDARY * item["condition_in_text"]
                + search.WEIGHT_LEXICAL * (item["lexical_score"] or 0.0)
                + search.WEIGHT_SEMANTIC * item["semantic_score"]
            )
            self.assertAlmostEqual(item["score"], expected, places=5)
            self.assertLessEqual(item["score"], search.MAX_SCORE)
        scores = [item["score"] for item in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_message_without_a_condition_is_ordered_by_lexical_then_semantic_score(self):
        results = search.rank("zorbicul")

        self.assertFalse(any(item["condition_in_title"] or item["condition_in_text"] for item in results))
        self.assertEqual(results[0]["source_relative_path"], "catB/prefix.md")
        self.assertEqual(_paths(results)[1], "catB/neutru.md")  # semantic only, below the median otherwise

    def test_fragments_below_the_median_similarity_without_any_other_signal_are_left_out(self):
        paths = _paths(search.rank("zorbicul"))

        self.assertNotIn("catB/altul.md", paths)

    def test_results_carry_the_indexed_category_and_conditions(self):
        results = self.by_path(search.rank("zorbita"))

        titlu = results["catA/titlu.md"]
        self.assertEqual(titlu["business_category"], "R1")
        self.assertEqual(titlu["primary_medical_conditions"], ["Zorbita"])
        self.assertEqual(results["catA/text.md"]["secondary_medical_conditions"], ["Zorbita"])


class ExpressionTests(RankTestCase):
    documents = {
        "e/toate.md": "# Diverse\n\nDurerea genunchiului la efort si la urcat scarile.",
        "e/doar-durere.md": "# Diverse\n\nDurere de cap, nu de altceva.",
        "e/ameteala.md": "# Diverse\n\nAmeteala apare dimineata.",
        "e/genunchi-si-ameteala.md": "# Diverse\n\nGenunchi umflat si ameteala.",
        "e/copii.md": "# Diverse\n\nZorbita la copii se trateaza cu odihna.",
        "e/fara-copii.md": "# Diverse\n\nZorbitoza la adulti se trateaza cu odihna.",
    }
    vectors = {path: _one_hot(DIM, index + 3) for index, path in enumerate(documents)}

    def test_a_fragment_missing_words_of_the_expression_has_no_lexical_score(self):
        results = self.by_path(search.rank("durere genunchi efort"))

        self.assertTrue(results["e/toate.md"]["found_by_lexical"])
        self.assertNotIn("e/doar-durere.md", results)

    def test_expressions_are_or_ed_and_the_condition_of_any_expression_counts(self):
        results = self.by_path(search.rank("durere de genunchi la efort, vertigo"))

        # Contains the second expression's condition (via a synonym) but none of the first's words.
        ameteala = results["e/ameteala.md"]
        self.assertTrue(ameteala["found_by_lexical"])
        self.assertTrue(ameteala["condition_in_text"])
        self.assertTrue(results["e/toate.md"]["found_by_lexical"])
        # "genunchi" alone satisfies neither expression's words; it only has the condition.
        mixed = results["e/genunchi-si-ameteala.md"]
        self.assertTrue(mixed["found_by_lexical"])

    def test_a_synonym_of_the_condition_still_needs_the_other_words(self):
        results = self.by_path(search.rank("zorbita copii"))

        self.assertTrue(results["e/copii.md"]["found_by_lexical"])
        # It names the condition (P2) but lacks "copii", so no lexical score.
        fara = results["e/fara-copii.md"]
        self.assertTrue(fara["condition_in_text"])
        self.assertFalse(fara["found_by_lexical"])
        self.assertIsNone(fara["lexical_score"])
        self.assertGreater(results["e/copii.md"]["score"], fara["score"])

    def test_equal_similarities_give_a_semantic_score_of_zero(self):
        # Every document has cosine 0, so none is "above the median": V = 0, not NULL or 1.
        toate = self.by_path(search.rank("durere genunchi efort"))["e/toate.md"]

        self.assertEqual(toate["semantic_score"], 0.0)
        self.assertAlmostEqual(toate["score"], search.WEIGHT_LEXICAL * toate["lexical_score"])

    def test_wordless_messages_search_nothing(self):
        self.assertEqual(search.rank(""), [])
        self.assertEqual(search.rank("  ?! , "), [])


class LexicalAgainstSemanticTests(RankTestCase):
    padding = " ".join(["cuvinte", "de", "umplutura", "fara", "legatura"] * 30)
    documents = {
        "l/scurt.md": "# Diverse\n\nfraza cautata",
        "l/lung.md": f"# Diverse\n\nText cu fraza cautata aici. {padding}",
        "l/semantic.md": "# Diverse\n\nAlt text fara nimic comun aici.",
        "l/zero.md": "# Diverse\n\nAltceva fara nimic comun aici.",
    }
    vectors = {
        "l/scurt.md": _one_hot(DIM, 4),  # cosine 0
        "l/lung.md": _one_hot(DIM, 0),  # cosine 1
        "l/semantic.md": _vector_with_cosine(DIM, 0.95),
        "l/zero.md": _one_hot(DIM, 5),
    }

    def test_lexical_counts_double_so_a_strong_lexical_match_beats_a_perfect_semantic_only_one(self):
        results = self.by_path(search.rank("fraza cautata"))

        scurt, semantic = results["l/scurt.md"], results["l/semantic.md"]
        self.assertAlmostEqual(scurt["lexical_score"], 1.0)
        self.assertGreater(scurt["score"], semantic["score"])

    def test_a_weak_lexical_match_can_lose_to_a_strong_semantic_one(self):
        results = self.by_path(search.rank("fraza cautata"))

        lung, semantic = results["l/lung.md"], results["l/semantic.md"]
        self.assertLess(lung["lexical_score"], 0.5)
        self.assertAlmostEqual(lung["semantic_score"], 1.0)
        # Soft P3 vs P4: the long fragment's weak lexical match plus a perfect cosine
        # still ranks by the formula, and a fragment with neither has no score at all.
        self.assertGreater(lung["score"], semantic["score"])
        self.assertNotIn("l/zero.md", results)

    def test_lexical_score_is_relative_to_the_best_match_of_the_search(self):
        results = search.rank("fraza cautata")

        best = max(item["lexical_score"] or 0.0 for item in results)
        self.assertAlmostEqual(best, 1.0)


class BudgetTests(RankTestCase):
    documents = {
        f"b/doc{index}.md": f"# Zorbita\n\n{'Text medical despre zorbita. ' * (index + 2)}" for index in range(4)
    }
    vectors = {path: _one_hot(DIM, index + 3) for index, path in enumerate(documents)}

    @staticmethod
    def _evidence_chars(item) -> int:
        heading = str(item["heading"]).strip()
        overhead = len(search.EVIDENCE_HEADING_PREFIX) + len(search.EVIDENCE_HEADING_SEPARATOR)
        return len(item["text"]) + (len(heading) + overhead if heading else 0)

    def test_everything_is_returned_when_the_budget_is_large(self):
        self.assertEqual(len(search.rank("zorbita")), 4)

    def test_whole_fragments_are_cut_from_the_tail_until_the_rest_fits(self):
        everything = search.rank("zorbita")
        sizes = [self._evidence_chars(item) for item in everything]
        budget = sizes[0] + sizes[1] + sizes[2] - 1  # the third no longer fits

        kept = search.rank("zorbita", max_chars=budget)

        self.assertEqual([item["chunk_id"] for item in kept], [item["chunk_id"] for item in everything[:2]])
        self.assertLessEqual(sum(self._evidence_chars(item) for item in kept), budget)
        # Exactly the budget: the third one now fits.
        exact = search.rank("zorbita", max_chars=sizes[0] + sizes[1] + sizes[2])
        self.assertEqual(len(exact), 3)

    def test_a_fragment_that_does_not_fit_is_dropped_whole_never_truncated(self):
        everything = search.rank("zorbita")

        kept = search.rank("zorbita", max_chars=self._evidence_chars(everything[0]) - 1)

        self.assertEqual(kept, [])

    def test_a_fragment_too_big_for_the_budget_also_cuts_the_smaller_ones_after_it(self):
        everything = search.rank("zorbita")
        first_size = self._evidence_chars(everything[0])

        # Room for the first only: no later (lower-scored) fragment slips in ahead of the cut.
        kept = search.rank("zorbita", max_chars=first_size + 1)

        self.assertEqual([item["chunk_id"] for item in kept], [everything[0]["chunk_id"]])


class TieBreakTests(RankTestCase):
    documents = {f"t/doc{index}.md": "# Zorbita\n\nAcelasi text despre zorbita." for index in range(4)}
    vectors = {path: _one_hot(DIM, 3) for path in documents}

    def test_equal_scores_are_ordered_by_chunk_id(self):
        results = search.rank("zorbita")

        self.assertEqual(len({item["score"] for item in results}), 1)
        ids = [item["chunk_id"] for item in results]
        self.assertEqual(ids, sorted(ids))


class NoCandidateLimitTests(RankTestCase):
    COUNT = 260
    documents = {f"n/doc{index:03d}.md": f"# Diverse\n\nText numarul {index} despre fraza cautata." for index in range(COUNT)}
    documents["n/zorbita.md"] = "# Zorbita\n\nRepaus."
    vectors = {path: _one_hot(DIM, 3 + index % 40) for index, path in enumerate(documents)}

    def test_every_matching_fragment_is_scored_and_returned(self):
        results = search.rank("fraza cautata")

        # More than the old 100/200-per-signal caps, none dropped before scoring.
        self.assertEqual(sum(item["found_by_lexical"] for item in results), self.COUNT)

    def test_the_condition_fragment_is_first_however_many_others_match(self):
        results = search.rank("zorbita")

        self.assertEqual(results[0]["source_relative_path"], "n/zorbita.md")


class CategoryFilterTests(RankTestCase):
    documents = {
        "catA/one.md": "# Diverse\n\nText fara nimic special aici.",
        "catA/two.md": "# Diverse\n\nAlt text fara nimic special aici.",
        "catB/three.md": "# Diverse\n\nInca un text fara nimic special aici.",
        "catB/zorbita.md": "# Zorbita\n\nRepaus si odihna.",
    }
    vectors = {
        "catA/one.md": _one_hot(DIM, 5),
        "catA/two.md": _vector_with_cosine(DIM, 0.3),
        "catB/three.md": _vector_with_cosine(DIM, 0.9),
        "catB/zorbita.md": _one_hot(DIM, 6),
    }

    def test_only_the_selected_categories_are_searched(self):
        results = search.rank("propozitie absenta din orice document", category_ids=frozenset({"catA"}))

        self.assertTrue(results)
        self.assertTrue(all(path.startswith("catA/") for path in _paths(results)))

    def test_semantic_score_is_relative_to_the_selected_subset(self):
        everything = self.by_path(search.rank("propozitie absenta din orice document"))
        filtered = self.by_path(
            search.rank("propozitie absenta din orice document", category_ids=frozenset({"catA"}))
        )

        # catA/two.md is far from the best fragment of the whole index, but the best of catA.
        self.assertLess(everything["catA/two.md"]["semantic_score"], 1.0)
        self.assertAlmostEqual(filtered["catA/two.md"]["semantic_score"], 1.0)

    def test_condition_fragments_outside_the_selection_are_excluded(self):
        results = search.rank("zorbita", category_ids=frozenset({"catA"}))

        self.assertNotIn("catB/zorbita.md", _paths(results))

    def test_no_filter_and_empty_filter_are_equivalent(self):
        baseline = search.rank("zorbita")
        empty = search.rank("zorbita", category_ids=frozenset())

        self.assertEqual(_paths(baseline), _paths(empty))


if __name__ == "__main__":
    unittest.main()
