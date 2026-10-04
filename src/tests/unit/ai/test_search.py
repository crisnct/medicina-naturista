"""Tests for the combined fragment score (backend.ai.search): the
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

from backend.ai import conditions, search
from backend.ai import db as db_module
from backend.ai.conditions import ConditionDictionary, parse_conditions
from backend.ai.embedding_model import PROFILES, EmbeddingProfile, get_profile
from tests.support.postgres import PostgresFixture
from scripts import build_hybrid_index as builder

_fixture = PostgresFixture()
DIM = get_profile(builder.DEFAULT_MODEL).dimension

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
        self.queries: list[str] = []

    def query_embed(self, texts):
        self.queries.extend(texts)
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

    def fake_embed(_model, chunks, _batch_size, _profile):
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


def _queries(text: str) -> list[str]:
    return search.lexical_queries(_dictionary().resolve(text))


def _signals(code: str) -> search.SearchSignals:
    return search.SearchSignals.from_code(code)


COMBINATIONS = ("ABC", "AB", "AC", "BC", "A", "B", "C")


class SearchSignalsTests(unittest.TestCase):
    def test_every_signal_is_on_by_default(self):
        self.assertEqual(search.ALL_SIGNALS, search.SearchSignals(True, True, True))
        self.assertEqual(search.ALL_SIGNALS.code, "ABC")

    def test_at_least_one_signal_must_be_on(self):
        with self.assertRaises(ValueError):
            search.SearchSignals(False, False, False)

    def test_code_and_from_code_round_trip(self):
        for code in COMBINATIONS:
            self.assertEqual(_signals(code).code, code)
        self.assertEqual(_signals("ca"), search.SearchSignals(True, False, True))  # any order, any case

    def test_from_code_rejects_empty_and_unknown_codes(self):
        for code in ("", "  ", "D", "ABD"):
            with self.subTest(code=code), self.assertRaises(ValueError):
                search.SearchSignals.from_code(code)


class LexicalQueriesTests(unittest.TestCase):
    def test_an_expression_is_one_phrase_of_prefix_stems_in_the_order_written(self):
        self.assertEqual(_queries("durere de genunchi"), ["(dure:* <-> de <-> genunc:*)"])

    def test_generic_and_short_words_are_kept(self):
        self.assertEqual(_queries("ce sa iau pentru durere"), ["(ce <-> sa <-> iau:* <-> pent:* <-> dure:*)"])
        self.assertEqual(_queries("acest guta"), ["(acest:* <-> guta:*)"])

    def test_words_under_three_letters_match_exactly_and_the_rest_by_prefix(self):
        query = _queries("la de cu pat")[0]

        self.assertEqual(query, "(la <-> de <-> cu <-> pat:*)")

    def test_short_query_keeps_its_words(self):
        self.assertEqual(_queries("HPV"), ["(hpv:*)"])

    def test_each_comma_separated_expression_is_its_own_query(self):
        self.assertEqual(_queries("artroza genunchi, guta"), ["(artro:* <-> genunc:*)", "(guta:*)"])

    def test_an_expression_that_is_a_condition_is_an_or_of_the_phrases_of_all_its_names(self):
        # A multi-word synonym ("zorbit disease") is a phrase itself.
        self.assertEqual(
            _queries("zorbita"),
            ["((zorbi:*) | (zorbito:*) | (zorb:* <-> disea:*))"],
        )

    def test_a_near_identical_spelling_of_a_condition_is_still_the_whole_condition(self):
        self.assertEqual(_queries("vertiggo"), ["((verti:*) | (ametea:*))"])

    def test_a_condition_inside_a_longer_expression_is_searched_as_written(self):
        # No synonyms and no condition looked up inside the expression: just the phrase.
        self.assertEqual(
            _queries("tratament pentru zorbita la copii"),
            ["(tratame:* <-> pent:* <-> zorbi:* <-> la <-> copii:*)"],
        )
        self.assertEqual(_queries("vertigo la copii"), ["(verti:* <-> la <-> copii:*)"])

    def test_the_expressions_of_a_message_are_resolved_separately(self):
        self.assertEqual(
            _queries("durere de genunchi la efort, vertigo"),
            ["(dure:* <-> de <-> genunc:* <-> la <-> efort:*)", "((verti:*) | (ametea:*))"],
        )

    def test_identical_expressions_count_once(self):
        self.assertEqual(len(_queries("zorbita, Zorbita")), 1)
        self.assertEqual(len(_queries("durere de cap, DURERE  de   cap, ameteala")), 2)
        # Different expressions of the same condition stay different expressions.
        self.assertEqual(len(_queries("zorbita, zorbitoza")), 2)

    def test_at_most_32_words_of_an_expression_are_used(self):
        query = _queries(" ".join(f"cuvant{index}" for index in range(40)))[0]

        self.assertEqual(query.count("<->"), 31)

    def test_text_cannot_inject_tsquery_syntax(self):
        for text in ("gută'; DROP TABLE chunks; --", "a & b | !c <-> d:*", "(((", "zorbita) | (x"):
            for query in _queries(text):
                with self.subTest(text=text):
                    self.assertRegex(query, r"^[a-z0-9:*()| <>-]+$")
                    self.assertNotIn("'", query)
                    self.assertNotIn("!", query)
                    self.assertNotIn("&", query)

    def test_text_without_words_has_no_query(self):
        self.assertEqual(_queries("?! ,"), [])
        self.assertEqual(_queries(""), [])


class WeightTests(unittest.TestCase):
    # (weights, ceiling) of every combination of signals.
    EXPECTED = {
        "ABC": ((4, 2, 1, 1), 8),
        "AB": ((3, 2, 1, 0), 6),
        "AC": ((3, 2, 0, 1), 6),
        "BC": ((0, 0, 1, 1), 2),
        "A": ((2, 1, 0, 0), 3),
        "B": ((0, 0, 1, 0), 1),
        "C": ((0, 0, 0, 1), 1),
    }

    def test_every_combination_has_its_weights_and_ceiling(self):
        self.assertEqual(set(self.EXPECTED), set(COMBINATIONS))
        for code, (weights, ceiling) in self.EXPECTED.items():
            with self.subTest(code=code):
                self.assertEqual(search.weights(_signals(code)), weights)
                self.assertEqual(search.max_score(_signals(code)), ceiling)

    def test_a_signal_that_is_off_has_no_weight(self):
        for code in COMBINATIONS:
            signals = _signals(code)
            w_primary, w_secondary, w_lexical, w_semantic = search.weights(signals)
            with self.subTest(code=code):
                self.assertEqual(bool(w_primary or w_secondary), signals.conditions)
                self.assertEqual(bool(w_lexical), signals.lexical)
                self.assertEqual(bool(w_semantic), signals.semantic)

    # With the lexical and semantic signals on, the condition in the title is
    # worth all the lower signals at their best and the one in the text is worth
    # lexical plus semantic; with one of them off, the title still weighs as much
    # as the text plus what remains; with conditions alone, title beats text.
    def test_weights_keep_the_priority_order_wherever_it_exists(self):
        p, s, l, v = search.weights(search.ALL_SIGNALS)
        self.assertEqual(p, s + l + v)
        self.assertEqual(s, l + v)
        for code in ("AB", "AC"):
            p, s, l, v = search.weights(_signals(code))
            self.assertEqual(p, s + l + v, code)
        p, s, _, _ = search.weights(_signals("A"))
        self.assertGreater(p, s)

    def test_lexical_and_semantic_weigh_the_same(self):
        _, _, l, v = search.weights(_signals("BC"))
        self.assertEqual(l, v)


class RankTestCase(unittest.TestCase):
    documents: dict[str, str] = {}
    vectors: dict[str, np.ndarray] = {}

    def setUp(self):
        _fixture.reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        _build_fixture_index(Path(self.tmp.name), self.documents, self.vectors)
        # Every query is embedded as e0; a document's vector decides its cosine.
        self.query_model = FakeQueryModel(_one_hot(DIM, 0))
        for target, value in (
            (search, mock.patch.object(search, "cached_query_model", return_value=self.query_model)),
            (conditions, mock.patch.object(conditions, "load_dictionary", return_value=_dictionary())),
        ):
            value.start()
            self.addCleanup(value.stop)

    def by_path(self, results) -> dict[str, dict]:
        return {item["source_relative_path"]: item for item in results}


class QueryProfileTests(RankTestCase):
    documents = {"catA/a.md": "# Plante\n\nCeai de musetel."}
    vectors = {"catA/a.md": _one_hot(DIM, 0)}

    def test_the_query_is_written_the_way_the_indexed_model_expects(self):
        search.rank("ceai de musetel")

        profile = get_profile(builder.DEFAULT_MODEL)
        self.assertEqual(self.query_model.queries, [profile.query_text("ceai de musetel")])
        self.assertTrue(self.query_model.queries[0].startswith("Instruct: "))

    def test_the_profile_comes_from_the_index_not_from_the_default_model(self):
        other = EmbeddingProfile("test/other-model", DIM, "q: {text}", "{text}", 1400, 240)
        with db_module.get_pool().connection() as connection:
            connection.execute("UPDATE sync_metadata SET value = %s WHERE key = 'model_name'", (other.name,))
            connection.commit()

        with mock.patch.dict(PROFILES, {other.name: other}):
            search.rank("ceai de musetel")

        self.assertEqual(self.query_model.queries, ["q: ceai de musetel"])

    def test_an_index_whose_dimension_disagrees_with_its_model_is_rejected(self):
        with db_module.get_pool().connection() as connection:
            connection.execute("UPDATE sync_metadata SET value = '64' WHERE key = 'model_dimension'")
            connection.commit()

        with self.assertRaisesRegex(RuntimeError, "does not match model"):
            search.rank("ceai de musetel")


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
        self.assertGreaterEqual(first["score"], search.weights(search.ALL_SIGNALS)[0])

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

    def test_score_is_the_weighted_sum_of_the_chosen_signals_in_every_combination(self):
        for code in COMBINATIONS:
            signals = _signals(code)
            w_primary, w_secondary, w_lexical, w_semantic = search.weights(signals)
            results = search.rank("zorbita", signals=signals)
            self.assertTrue(results, code)
            for item in results:
                expected = (
                    w_primary * bool(item["condition_in_title"])
                    + w_secondary * bool(item["condition_in_text"])
                    + w_lexical * (item["lexical_score"] or 0.0)
                    + w_semantic * (item["semantic_score"] or 0.0)
                )
                with self.subTest(code=code, path=item["source_relative_path"]):
                    self.assertAlmostEqual(item["score"], expected, places=5)
                    self.assertGreater(item["score"], 0)
                    self.assertLessEqual(item["score"], search.max_score(signals) + 1e-9)
            scores = [item["score"] for item in results]
            self.assertEqual(scores, sorted(scores, reverse=True), code)

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

    def test_results_carry_the_signals_they_were_scored_with(self):
        for code in COMBINATIONS:
            for item in search.rank("zorbita", signals=_signals(code)):
                self.assertEqual(item["signals"], _signals(code), code)

    def test_the_fields_of_a_signal_that_is_off_are_none(self):
        lexical = search.rank("zorbita", signals=_signals("B"))
        semantic = search.rank("zorbita", signals=_signals("C"))
        conditions = search.rank("zorbita", signals=_signals("A"))

        self.assertTrue(lexical and semantic and conditions)
        for item in lexical:
            self.assertIsNone(item["condition_in_title"])
            self.assertIsNone(item["condition_in_text"])
            self.assertIsNone(item["semantic_score"])
            self.assertIsNone(item["semantic_similarity"])
            self.assertIsNotNone(item["lexical_score"])
            self.assertTrue(item["found_by_lexical"])
        for item in semantic:
            self.assertIsNone(item["condition_in_title"])
            self.assertIsNone(item["condition_in_text"])
            self.assertIsNone(item["lexical_score"])
            self.assertFalse(item["found_by_lexical"])
            self.assertIsNotNone(item["semantic_score"])
            self.assertIsNotNone(item["semantic_similarity"])
        for item in conditions:
            self.assertIsNone(item["lexical_score"])
            self.assertFalse(item["found_by_lexical"])
            self.assertIsNone(item["semantic_score"])
            self.assertIsNone(item["semantic_similarity"])
            self.assertIsInstance(item["condition_in_title"], bool)
            self.assertIsInstance(item["condition_in_text"], bool)

    def test_a_signal_that_is_off_is_not_computed(self):
        # The question is embedded only for the semantic signal.
        for code in ("A", "B", "AB"):
            with self.subTest(code=code), mock.patch.object(
                search, "cached_query_model", side_effect=AssertionError("the model must not be loaded")
            ):
                self.assertTrue(search.rank("zorbita", signals=_signals(code)))
        self.assertEqual(self.query_model.queries, [])

        search.rank("zorbita", signals=_signals("C"))

        self.assertEqual(len(self.query_model.queries), 1)

    def test_without_the_semantic_signal_an_unsynced_index_is_not_an_error(self):
        with db_module.get_pool().connection() as connection:
            connection.execute("DELETE FROM sync_metadata")
            connection.commit()

        self.assertTrue(search.rank("zorbita", signals=_signals("AB")))
        with self.assertRaisesRegex(RuntimeError, "not been synced"):
            search.rank("zorbita", signals=_signals("C"))

    def test_only_the_semantic_signal_keeps_the_fragments_above_the_median_in_cosine_order(self):
        results = search.rank("zorbita", signals=_signals("C"))

        self.assertEqual(_paths(results), ["catB/prefix.md", "catB/neutru.md"])
        for item in results:
            self.assertAlmostEqual(item["score"], item["semantic_score"])
        self.assertAlmostEqual(results[0]["score"], 1.0)
        self.assertAlmostEqual(results[1]["score"], 0.9)

    def test_only_the_lexical_signal_gives_every_found_fragment_the_same_score(self):
        results = search.rank("zorbita", signals=_signals("B"))

        # One expression: L is 0 or 1, so the order inside the tie is chunk_id.
        self.assertEqual({item["score"] for item in results}, {1.0})
        ids = [item["chunk_id"] for item in results]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(
            set(_paths(results)),
            {"catA/titlu.md", "catA/text.md", "catB/sinonim.md", "catB/prefix.md"},
        )

    def test_conditions_and_lexical_without_the_semantic_signal_ignore_the_cosine(self):
        results = self.by_path(search.rank("zorbita", signals=_signals("AB")))

        # 3*P1 + 2*P2 + L; the cosine plays no part, so the semantic-only fragment is not there at all.
        self.assertNotIn("catB/neutru.md", results)
        self.assertAlmostEqual(results["catA/titlu.md"]["score"], 3 + 1)
        self.assertAlmostEqual(results["catA/text.md"]["score"], 2 + 1)
        self.assertAlmostEqual(results["catB/prefix.md"]["score"], 1)

    def test_conditions_and_semantic_without_the_lexical_signal_ignore_the_words(self):
        results = self.by_path(search.rank("zorbita", signals=_signals("AC")))

        # 3*P1 + 2*P2 + V: "prefix" is only a lexical match, so it keeps just its cosine.
        self.assertAlmostEqual(results["catA/titlu.md"]["score"], 3)
        self.assertAlmostEqual(results["catA/text.md"]["score"], 2)
        self.assertAlmostEqual(results["catB/prefix.md"]["score"], 1)
        self.assertAlmostEqual(results["catB/neutru.md"]["score"], 0.9)

    def test_lexical_and_semantic_without_the_conditions_signal_know_no_conditions(self):
        results = self.by_path(search.rank("zorbita", signals=_signals("BC")))

        # L + V: the title and text fragments are only lexical matches.
        self.assertAlmostEqual(results["catA/titlu.md"]["score"], 1)
        self.assertAlmostEqual(results["catB/prefix.md"]["score"], 2)  # lexical and the best cosine
        self.assertAlmostEqual(results["catB/neutru.md"]["score"], 0.9)

    def test_a_message_that_gives_the_chosen_signals_nothing_to_look_for_finds_nothing(self):
        # Conditions only, and no condition in the message.
        self.assertEqual(search.rank("zorbicul", signals=_signals("A")), [])


class ConditionsOnlyTests(RankTestCase):
    documents = {
        "a/ambele.md": "# Zorbita\n\nZorbita se trateaza cu odihna.",
        "a/titlu.md": "# Zorbita\n\nRepaus si ceai calduros la pat.",
        "a/text.md": "# Plante\n\nCeaiul de musetel ajuta in zorbita usoara.",
        "a/nimic.md": "# Diverse\n\nZorbicul este altceva.",
    }
    vectors = {path: _one_hot(DIM, index + 3) for index, path in enumerate(documents)}

    def test_the_score_has_three_values_title_and_text_then_title_then_text(self):
        results = self.by_path(search.rank("zorbita", signals=_signals("A")))

        self.assertEqual(
            {path: item["score"] for path, item in results.items()},
            {"a/ambele.md": 3.0, "a/titlu.md": 2.0, "a/text.md": 1.0},
        )

    def test_fragments_without_the_condition_are_not_returned(self):
        self.assertNotIn("a/nimic.md", _paths(search.rank("zorbita", signals=_signals("A"))))

    def test_ties_are_ordered_by_chunk_id_only(self):
        # No hidden tiebreak by a signal that is off.
        for code in ("A", "B"):
            results = search.rank("zorbita", signals=_signals(code))
            keys = [(-item["score"], item["chunk_id"]) for item in results]
            self.assertEqual(keys, sorted(keys), code)

    def test_a_message_without_a_recognised_condition_finds_nothing(self):
        with mock.patch.object(search, "cached_query_model", side_effect=AssertionError("no model")):
            self.assertEqual(search.rank("durere de cap", signals=_signals("A")), [])


class ExpressionTests(RankTestCase):
    documents = {
        "e/toate.md": "# Diverse\n\nDurerea genunchiului la efort si la urcat scarile.",
        "e/doar-durere.md": "# Diverse\n\nDurere de cap, nu de altceva.",
        "e/ameteala.md": "# Diverse\n\nAmeteala apare dimineata.",
        "e/genunchi-si-ameteala.md": "# Diverse\n\nGenunchi umflat si ameteala.",
        "e/trei.md": "# Diverse\n\nDurere de cap, ameteala si genunchi umflat.",
        "e/copii.md": "# Diverse\n\nZorbita la copii se trateaza cu odihna.",
        "e/fara-copii.md": "# Diverse\n\nZorbitoza la adulti se trateaza cu odihna.",
        "e/sinonim-copii.md": "# Diverse\n\nAmeteala la copii apare rar.",
        "e/vertigo-copii.md": "# Diverse\n\nVertigo la copii se vindeca.",
        "e/sinonime.md": "# Diverse\n\nZorbita, zorbitoza si zorbit disease, toate odata.",
    }
    vectors = {path: _one_hot(DIM, index + 3) for index, path in enumerate(documents)}

    def lexical(self, query: str) -> dict[str, dict]:
        return self.by_path(search.rank(query, signals=_signals("B")))

    def test_an_expression_is_found_only_as_the_exact_phrase_in_the_order_written(self):
        # "durere genunchi efort": the words are there, but not next to each other.
        self.assertEqual(self.lexical("durere genunchi efort"), {})
        self.assertEqual(self.lexical("cap de durere"), {})
        self.assertEqual(set(self.lexical("durere de cap")), {"e/doar-durere.md", "e/trei.md"})

    def test_generic_and_short_words_are_part_of_the_phrase(self):
        self.assertEqual(set(self.lexical("durerea genunchiului la efort")), {"e/toate.md"})
        # "durere de genunchi" is in no fragment, so the extra word costs the match.
        self.assertEqual(self.lexical("durere de genunchi"), {})

    def test_words_match_through_their_inflections(self):
        # "durere genunchiul" finds "Durerea genunchiului" through the prefix stems.
        self.assertIn("e/toate.md", self.lexical("durere genunchiul"))

    def test_l_is_the_fraction_of_expressions_found_in_the_fragment(self):
        results = self.lexical("durere de cap, ameteala, genunchi")

        # An expression counts once however many of its words or names appear.
        self.assertAlmostEqual(results["e/genunchi-si-ameteala.md"]["lexical_score"], 2 / 3)
        self.assertAlmostEqual(results["e/trei.md"]["lexical_score"], 1.0)
        for path in ("e/doar-durere.md", "e/ameteala.md", "e/toate.md"):
            self.assertAlmostEqual(results[path]["lexical_score"], 1 / 3, msg=path)
        # With L alone as the score, the best come first and ties follow chunk_id.
        ranked = _paths(search.rank("durere de cap, ameteala, genunchi", signals=_signals("B")))
        self.assertEqual(ranked[:2], ["e/trei.md", "e/genunchi-si-ameteala.md"])

    def test_a_condition_counts_once_even_when_several_of_its_names_are_in_the_fragment(self):
        self.assertAlmostEqual(self.lexical("zorbita")["e/sinonime.md"]["lexical_score"], 1.0)
        self.assertAlmostEqual(self.lexical("zorbita, vertigo")["e/sinonime.md"]["lexical_score"], 0.5)

    def test_an_expression_that_is_a_condition_is_found_under_its_synonyms(self):
        # "vertigo" is an exact term, "vertiggo" a near-identical spelling: both find "ameteala".
        self.assertIn("e/ameteala.md", self.lexical("vertigo"))
        self.assertIn("e/ameteala.md", self.lexical("vertiggo"))

    def test_a_condition_inside_an_expression_is_searched_literally_without_synonyms(self):
        results = self.by_path(search.rank("vertigo la copii", signals=_signals("AB")))

        # The literal phrase is in one fragment only; the synonym "ameteala" does
        # not stand in for the word "vertigo" inside an expression ...
        self.assertTrue(results["e/vertigo-copii.md"]["found_by_lexical"])
        sinonim = results["e/sinonim-copii.md"]
        self.assertFalse(sinonim["found_by_lexical"])
        self.assertIsNone(sinonim["lexical_score"])
        # ... but the conditions signal still recognises the condition there.
        self.assertTrue(sinonim["condition_in_text"])

    def test_a_synonym_of_the_condition_does_not_replace_the_other_words_either(self):
        results = self.by_path(search.rank("zorbita la copii"))

        self.assertTrue(results["e/copii.md"]["found_by_lexical"])
        # It names the condition (P2) but not the phrase, so no lexical score.
        fara = results["e/fara-copii.md"]
        self.assertTrue(fara["condition_in_text"])
        self.assertFalse(fara["found_by_lexical"])
        self.assertIsNone(fara["lexical_score"])
        self.assertGreater(results["e/copii.md"]["score"], fara["score"])

    def test_identical_expressions_are_counted_once(self):
        results = self.lexical("durere de cap, DURERE de cap")

        self.assertAlmostEqual(results["e/doar-durere.md"]["lexical_score"], 1.0)

    def test_expressions_are_or_ed_and_the_condition_of_any_expression_counts(self):
        results = self.by_path(search.rank("durere de genunchi la efort, vertigo"))

        # Contains the second expression's condition (via a synonym) but none of the first's words.
        ameteala = results["e/ameteala.md"]
        self.assertTrue(ameteala["found_by_lexical"])
        self.assertTrue(ameteala["condition_in_text"])
        self.assertAlmostEqual(ameteala["lexical_score"], 0.5)

    def test_equal_similarities_give_a_semantic_score_of_zero(self):
        # Every document has cosine 0, so none is "above the median": V = 0, not NULL or 1.
        doar = self.by_path(search.rank("durere de cap"))["e/doar-durere.md"]

        self.assertEqual(doar["semantic_score"], 0.0)
        self.assertAlmostEqual(doar["score"], doar["lexical_score"])

    def test_wordless_messages_search_nothing(self):
        self.assertEqual(search.rank(""), [])
        self.assertEqual(search.rank("  ?! , "), [])
        for code in COMBINATIONS:
            self.assertEqual(search.rank("?!", signals=_signals(code)), [])


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

    def test_the_length_of_a_fragment_does_not_change_l(self):
        results = self.by_path(search.rank("fraza cautata"))

        # Both contain the one expression: L = 1 for the short and the long fragment alike.
        self.assertAlmostEqual(results["l/scurt.md"]["lexical_score"], 1.0)
        self.assertAlmostEqual(results["l/lung.md"]["lexical_score"], 1.0)

    def test_a_lexical_match_beats_a_strong_semantic_only_one_and_both_signals_beat_either(self):
        results = self.by_path(search.rank("fraza cautata"))

        scurt, lung, semantic = results["l/scurt.md"], results["l/lung.md"], results["l/semantic.md"]
        self.assertAlmostEqual(scurt["semantic_score"], 0.0)
        self.assertLess(semantic["semantic_score"], 1.0)
        self.assertGreater(scurt["score"], semantic["score"])
        self.assertGreater(lung["score"], scurt["score"])
        # A fragment with neither signal has no score at all.
        self.assertNotIn("l/zero.md", results)

    def test_without_the_semantic_signal_the_lexical_matches_tie(self):
        results = search.rank("fraza cautata", signals=_signals("B"))

        self.assertEqual(set(_paths(results)), {"l/scurt.md", "l/lung.md"})
        self.assertEqual({item["score"] for item in results}, {1.0})
        ids = [item["chunk_id"] for item in results]
        self.assertEqual(ids, sorted(ids))  # the tie is broken by chunk_id alone


class MultipleExpressionRankTests(RankTestCase):
    documents = {
        "m/gripa-guta.md": "# Diverse\n\nGripa si guta in acelasi loc.",
        "m/gripa.md": "# Diverse\n\nNumai gripa aici.",
        "m/raceala.md": "# Diverse\n\nNumai raceala aici.",
        "m/nimic.md": "# Diverse\n\nNimic de interes.",
    }
    vectors = {path: _one_hot(DIM, index + 3) for index, path in enumerate(documents)}

    def test_two_of_three_expressions_make_l_two_thirds_even_if_none_has_all_three(self):
        results = self.by_path(search.rank("gripa, raceala, guta", signals=_signals("B")))

        self.assertAlmostEqual(results["m/gripa-guta.md"]["lexical_score"], 2 / 3)
        self.assertAlmostEqual(results["m/gripa.md"]["lexical_score"], 1 / 3)
        self.assertAlmostEqual(results["m/raceala.md"]["lexical_score"], 1 / 3)
        # L is not relative to the best fragment of the search: nothing reaches 1.
        self.assertLess(max(item["lexical_score"] for item in results.values()), 1.0)
        self.assertNotIn("m/nimic.md", results)


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

    def test_the_lexical_matches_are_restricted_to_the_selected_categories_too(self):
        everything = _paths(search.rank("nimic special", signals=_signals("B")))
        filtered = _paths(search.rank("nimic special", category_ids=frozenset({"catA"}), signals=_signals("B")))

        self.assertIn("catB/three.md", everything)
        self.assertEqual(set(filtered), {"catA/one.md", "catA/two.md"})

    def test_the_conditions_signal_alone_respects_the_selection(self):
        filtered = search.rank("zorbita", category_ids=frozenset({"catA"}), signals=_signals("A"))

        self.assertEqual(filtered, [])
        self.assertEqual(_paths(search.rank("zorbita", signals=_signals("A"))), ["catB/zorbita.md"])

    def test_condition_fragments_outside_the_selection_are_excluded(self):
        results = search.rank("zorbita", category_ids=frozenset({"catA"}))

        self.assertNotIn("catB/zorbita.md", _paths(results))

    def test_no_filter_and_empty_filter_are_equivalent(self):
        baseline = search.rank("zorbita")
        empty = search.rank("zorbita", category_ids=frozenset())

        self.assertEqual(_paths(baseline), _paths(empty))


if __name__ == "__main__":
    unittest.main()
