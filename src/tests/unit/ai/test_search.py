"""Tests for the combined fragment score (backend.ai.search): the
lexical query, the P1 > P2 > P3 > P4 priorities of rank(), the context budget
and the category filter."""

from __future__ import annotations

import unittest

from backend.ai import search
from backend.ai.conditions import ConditionDictionary, parse_conditions
from backend.ai.embedding_model import get_profile
from scripts import build_hybrid_index as builder
from tests.support.conditions import conditions_jsonl

DIM = get_profile(builder.DEFAULT_MODEL).dimension

# Made-up conditions, so the tests do not depend on the shipped dictionary.
DICTIONARY_TEXT = "Zorbita,zorbitoza,zorbit disease\nVertigo,ameteala\n"


def _dictionary() -> ConditionDictionary:
    return ConditionDictionary(parse_conditions(conditions_jsonl(DICTIONARY_TEXT)))


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
        self.assertEqual(
            _signals("ca"), search.SearchSignals(True, False, True)
        )  # any order, any case

    def test_from_code_rejects_empty_and_unknown_codes(self):
        for code in ("", "  ", "D", "ABD"):
            with self.subTest(code=code), self.assertRaises(ValueError):
                search.SearchSignals.from_code(code)


class LexicalQueriesTests(unittest.TestCase):
    def test_an_expression_is_one_phrase_of_prefix_stems_in_the_order_written(self):
        self.assertEqual(_queries("durere de genunchi"), ["(dure:* <-> de <-> genunc:*)"])

    def test_generic_and_short_words_are_kept(self):
        self.assertEqual(
            _queries("ce sa iau pentru durere"), ["(ce <-> sa <-> iau:* <-> pent:* <-> dure:*)"]
        )
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
