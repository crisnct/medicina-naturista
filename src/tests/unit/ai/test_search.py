"""Tests for the combined fragment score (backend.ai.search): the
lexical query, the P1 > P2 > P3 > P4 priorities of rank(), the context budget
and the category filter."""

from __future__ import annotations

import unittest
import unittest.mock

from backend.ai import search
from backend.ai.conditions import ConditionDictionary
from backend.ai.embedding_model import get_profile
from scripts import build_hybrid_index as builder
from tests.support.conditions import conditions_from_rows

DIM = get_profile(builder.DEFAULT_MODEL).dimension

# Made-up conditions, so the tests do not depend on the shipped dictionary.
DICTIONARY_TEXT = "Zorbita,zorbitoza,zorbit disease\nVertigo,ameteala\n"


def _dictionary() -> ConditionDictionary:
    return ConditionDictionary(conditions_from_rows(DICTIONARY_TEXT))


def _lexical(text: str) -> tuple[str, dict[str, object]] | None:
    return search.lexical_query(_dictionary().resolve(text))


def _sql(text: str) -> str:
    return _lexical(text)[0]


def _words(text: str) -> list[object]:
    return list(_lexical(text)[1].values())


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


class LexicalQueryTests(unittest.TestCase):
    def test_an_expression_is_searched_as_terms_and_as_a_phrase_in_text_and_heading(self):
        sql = _sql("durere de genunchi")

        # terms and phrase, in the text and in the heading: the words are bound four times
        self.assertEqual(_words("durere de genunchi"), ["durere", "genunchi"] * 4)
        for field in ("text_ro", "heading_ro"):
            self.assertIn(f"paradedb.match('{field}', %(lexical_", sql)
            self.assertIn(f"paradedb.phrase('{field}', ARRAY[", sql)
        self.assertIn("minimum_should_match => 2", sql)  # 75% of 2 words, rounded up

    def test_generic_words_are_left_out(self):
        self.assertEqual(_words("ce sa iau pentru durere"), ["durere", "durere"])
        self.assertIn("minimum_should_match => 1", _sql("ce sa iau pentru durere"))
        self.assertEqual(
            _words("Spune-mi tot ce știi despre Ovidiu Bojor")[:2], ["Ovidiu", "Bojor"]
        )

    def test_an_expression_of_only_generic_words_keeps_them(self):
        self.assertEqual(_words("ce este")[:2], ["ce", "este"])
        self.assertIn("minimum_should_match => 2", _sql("ce este"))

    def test_a_single_word_has_no_phrase(self):
        self.assertEqual(_words("HPV"), ["HPV", "HPV"])  # text and heading
        self.assertNotIn("paradedb.phrase", _sql("HPV"))
        self.assertIn("minimum_should_match => 1", _sql("HPV"))

    def test_each_comma_separated_expression_is_its_own_query(self):
        sql = _sql("artroza genunchi, guta")

        self.assertEqual(sql.count("minimum_should_match"), 4)  # 2 expressions x (text, heading)
        self.assertEqual(_words("artroza genunchi, guta")[:2], ["artroza", "genunchi"])
        self.assertIn("guta", _words("artroza genunchi, guta"))

    def test_an_expression_that_is_a_condition_is_every_phrase_of_its_names(self):
        # A multi-word synonym ("zorbit disease") is a phrase itself; no terms clause.
        sql = _sql("zorbita")

        self.assertEqual(_words("zorbita"), ["Zorbita", "zorbitoza", "zorbit", "disease"] * 2)
        self.assertNotIn("minimum_should_match", sql)
        self.assertIn(
            "paradedb.phrase('text_ro', ARRAY[%(lexical_2)s::text, %(lexical_3)s::text], 0)", sql
        )

    def test_a_near_identical_spelling_of_a_condition_is_still_the_whole_condition(self):
        self.assertEqual(_words("vertiggo"), ["Vertigo", "ameteala"] * 2)
        self.assertNotIn("minimum_should_match", _sql("vertiggo"))

    def test_a_condition_inside_a_longer_expression_is_searched_as_written(self):
        # No synonyms and no condition looked up inside the expression.
        words = _words("tratament pentru zorbita la copii")

        self.assertEqual(words, ["zorbita", "copii"] * 4)
        self.assertNotIn("zorbitoza", words)

    def test_the_expressions_of_a_message_are_resolved_separately(self):
        words = _words("durere de genunchi la efort, vertigo")

        self.assertEqual(words[:3], ["durere", "genunchi", "efort"])
        self.assertEqual(words[-4:], ["Vertigo", "ameteala"] * 2)

    def test_identical_expressions_count_once(self):
        self.assertEqual(len(_words("zorbita, Zorbita")), 8)
        self.assertEqual(len(_words("durere de cap, DURERE  de   cap, ameteala")), 12)
        # Different expressions of the same condition stay different expressions.
        self.assertEqual(len(_words("zorbita, zorbitoza")), 16)

    def test_at_most_32_words_of_an_expression_are_used(self):
        self.assertEqual(len(_words(" ".join(f"cuvant{index}" for index in range(40)))), 32 * 4)

    def test_text_travels_only_as_bound_parameters(self):
        for text in ("guta'; DROP TABLE chunks; --", "a & b | !c <-> d:*", "(((", "zorbita) | (x"):
            with self.subTest(text=text):
                query = _lexical(text)
                if query is None:  # no word at all
                    continue
                sql, parameters = query
                self.assertNotIn("DROP", sql)
                self.assertNotIn("chunks", sql)
                self.assertNotIn("!", sql)
                self.assertTrue(all(isinstance(value, str) for value in parameters.values()))
                self.assertEqual(sql.count("%(lexical_"), len(parameters))

    def test_text_without_words_has_no_query(self):
        self.assertIsNone(_lexical("?! ,"))
        self.assertIsNone(_lexical(""))


class ScoreFormulaTests(unittest.TestCase):
    # The ceiling of every combination of signals under the default formula
    # 4*P1 + 2*P2 + (K+1)/(K+L) + (K+1)/(K+V): a signal that is off has infinite ranks.
    EXPECTED = {"ABC": 8, "AB": 7, "AC": 7, "BC": 2, "A": 6, "B": 1, "C": 1}

    def test_every_combination_has_its_ceiling(self):
        self.assertEqual(set(self.EXPECTED), set(COMBINATIONS))
        for code, ceiling in self.EXPECTED.items():
            with self.subTest(code=code):
                self.assertEqual(search.max_score(_signals(code)), ceiling)

    def test_the_formula_comes_from_the_settings(self):
        from dataclasses import replace

        changed = replace(search.settings, search_score_formula="P1+P2+3*(K+1)/(K+L)+(K+1)/(K+V)")
        with unittest.mock.patch.object(search, "settings", changed):
            self.assertEqual(search.max_score(search.ALL_SIGNALS), 6)
            self.assertEqual(search.max_score(_signals("B")), 3)
            self.assertIn("3.0::double precision", search.score_sql())

    def test_the_formula_is_one_sql_expression_over_the_ranked_columns(self):
        sql = search.score_sql()

        for column in ("p1", "p2", "lexical", "semantic"):
            self.assertIn(f"({column}::double precision)", sql)
        self.assertNotIn("P1", sql)
