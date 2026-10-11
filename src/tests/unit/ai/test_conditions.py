"""Tests for the medical-condition dictionary (backend.ai.conditions)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.ai import conditions
from backend.ai.conditions import ConditionDictionary, make_condition
from tests.support.conditions import conditions_from_rows

SAMPLE = """
Adenom,tumora adenomatoasa,adenoma
Adenom de prostata,adenom prostatic,hiperplazie benigna de prostata,benign prostatic hyperplasia
Artrita gutoasa,guta articulara,artrita urica,gout
Artrita,artrita cronica,arthritis
Acnee rozacee,rozacee,cuperoza,rosacea
"""


class ConstructionTests(unittest.TestCase):
    def test_name_is_first_and_duplicate_normalized_terms_are_dropped(self):
        item = make_condition(" Acalazie ", ["acalazie", "ACALAZIE ", "cardiospasm", " "])
        self.assertEqual(item.name, "Acalazie")
        self.assertEqual(item.terms, ("Acalazie", "cardiospasm"))

    def test_invalid_structured_values_are_rejected(self):
        for name, synonyms in [(" ", []), (3, []), ("Tuse", "cough"), ("Tuse", ["cough", 3])]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                make_condition(name, synonyms)


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.dictionary = ConditionDictionary(conditions_from_rows(SAMPLE))

    def names(self, query):
        return [item.name for item in self.dictionary.match(query)]

    def test_exact_synonym_in_english_finds_the_condition(self):
        self.assertEqual(self.names("gout"), ["Artrita gutoasa"])

    def test_match_ignores_case_and_diacritics(self):
        self.assertEqual(self.names("CUPEROZĂ"), ["Acnee rozacee"])

    def test_longest_contained_term_wins(self):
        self.assertEqual(self.names("tratament pentru adenom de prostata"), ["Adenom de prostata"])

    def test_independent_mentions_survive_even_when_one_name_is_shorter(self):
        dictionary = ConditionDictionary(
            conditions_from_rows("Gripa,influenza\nRaceala,common cold\n")
        )
        for query, expected in [
            ("cauta remedii naturiste pentru gripa si raceala", ("Gripa", "Raceala")),
            ("raceala si gripa", ("Raceala", "Gripa")),
            ("GRIPĂ și RĂCEALĂ", ("Gripa", "Raceala")),
            ("remedii pentru influenza sau common cold", ("Gripa", "Raceala")),
            ("gripa / raceala", ("Gripa", "Raceala")),
            ("gripa, raceala", ("Gripa", "Raceala")),
        ]:
            with self.subTest(query=query):
                self.assertEqual(dictionary.resolve(query).condition_names, expected)

    def test_nested_term_only_suppresses_the_overlapping_occurrence(self):
        self.assertEqual(
            self.names("tratament pentru adenom de prostata si adenom"),
            ["Adenom de prostata", "Adenom"],
        )
        self.assertEqual(
            self.names("tratament pentru adenom si adenom de prostata"),
            ["Adenom", "Adenom de prostata"],
        )

    def test_distinct_short_name_survives_beside_a_longer_compound_name(self):
        self.assertEqual(
            self.names("tratament pentru adenom de prostata si artrita"),
            ["Adenom de prostata", "Artrita"],
        )

    def test_repeated_mentions_are_unique_and_the_two_condition_limit_is_preserved(self):
        self.assertEqual(
            self.names("gout si artrita urica si adenom si rozacee"), ["Artrita gutoasa", "Adenom"]
        )

    def test_near_identical_spelling_beats_a_shorter_contained_term(self):
        self.assertEqual(self.names("artrita gutosa"), ["Artrita gutoasa"])

    def test_unknown_query_matches_nothing(self):
        self.assertEqual(self.names("durere de cap"), [])

    def test_empty_query_matches_nothing(self):
        self.assertEqual(self.names("  ?! "), [])


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.dictionary = ConditionDictionary(conditions_from_rows(SAMPLE + "Tuse,cough\n"))

    def segments(self, query):
        return [
            (segment.text, [item.name for item in segment.conditions], segment.remainder)
            for segment in self.dictionary.resolve(query).segments
        ]

    def test_a_segment_that_is_the_condition_has_nothing_left_over(self):
        self.assertEqual(self.segments("gout"), [("gout", ["Artrita gutoasa"], "")])

    def test_words_around_the_condition_name_are_the_remainder(self):
        self.assertEqual(
            self.segments("tratament pentru adenom de prostata la barbati"),
            [
                (
                    "tratament pentru adenom de prostata la barbati",
                    ["Adenom de prostata"],
                    "tratament pentru la barbati",
                )
            ],
        )

    def test_separate_conditions_are_removed_from_the_remainder(self):
        dictionary = ConditionDictionary(conditions_from_rows("Gripa\nRaceala\n"))
        segment = dictionary.resolve("cauta remedii naturiste pentru gripa si raceala").segments[0]
        self.assertEqual([item.name for item in segment.conditions], ["Gripa", "Raceala"])
        self.assertEqual(segment.remainder, "cauta remedii naturiste pentru si")
        self.assertFalse(segment.whole_condition)

    def test_a_misspelled_condition_is_the_whole_segment(self):
        self.assertEqual(
            self.segments("artrita gutosa"), [("artrita gutosa", ["Artrita gutoasa"], "")]
        )

    def test_each_comma_separated_segment_is_recognised_on_its_own(self):
        resolved = self.dictionary.resolve("Artrita, tuse")

        self.assertEqual(resolved.condition_names, ("Artrita", "Tuse"))
        self.assertEqual(
            self.segments("durere de cap, tuse"),
            [
                ("durere de cap", [], "durere de cap"),
                ("tuse", ["Tuse"], ""),
            ],
        )

    def test_condition_names_are_canonical_and_unique(self):
        resolved = self.dictionary.resolve("gout, artrita urica")

        self.assertEqual(resolved.condition_names, ("Artrita gutoasa",))

    def test_empty_segments_and_wordless_messages_resolve_to_nothing(self):
        self.assertEqual(self.dictionary.resolve("  ?! , ,").segments, ())
        self.assertEqual(self.dictionary.resolve("").condition_names, ())

    def test_message_without_a_condition_keeps_its_text(self):
        self.assertEqual(self.segments("durere de cap"), [("durere de cap", [], "durere de cap")])

    def whole(self, query):
        return [segment.whole_condition for segment in self.dictionary.resolve(query).segments]

    def test_an_expression_that_is_exactly_a_term_is_a_whole_condition(self):
        self.assertEqual(self.whole("gout"), [True])
        self.assertEqual(self.whole("Artrită gutoasă"), [True])

    def test_a_near_identical_spelling_of_a_whole_term_is_a_whole_condition(self):
        self.assertEqual(self.whole("artrita gutosa"), [True])

    def test_a_condition_inside_a_longer_expression_is_not_a_whole_condition(self):
        self.assertEqual(self.whole("tratament pentru adenom de prostata la barbati"), [False])
        self.assertEqual(self.whole("tuse la copii"), [False])

    def test_a_loose_spelling_match_is_not_a_whole_condition(self):
        # Close enough for P1/P2 (the 0.84 fallback) but not a typo of a whole term (0.9).
        segment = self.dictionary.resolve("cuperzaa").segments[0]  # ratio 0.875 to "cuperoza"

        self.assertEqual([item.name for item in segment.conditions], ["Acnee rozacee"])
        self.assertFalse(segment.whole_condition)

    def test_an_expression_without_a_condition_is_not_a_whole_condition(self):
        self.assertEqual(self.whole("durere de cap"), [False])

    def test_each_comma_separated_expression_is_judged_on_its_own(self):
        self.assertEqual(
            self.whole("gout, tuse la copii, durere de cap, tuse"), [True, False, False, True]
        )


class DatabaseLoadingTests(unittest.TestCase):
    def test_active_operation_reuses_its_dictionary_without_another_connection(self):
        from backend.ai import index_state

        dictionary = ConditionDictionary(conditions_from_rows("Guta,gout\n"))
        with patch.object(
            index_state, "dictionary_snapshot", side_effect=AssertionError("DB lookup")
        ):
            token = index_state._dictionary.set(dictionary)
            try:
                self.assertIs(conditions.load_dictionary(), dictionary)
            finally:
                index_state._dictionary.reset(token)

    def test_loading_outside_an_operation_uses_the_database_snapshot(self):
        dictionary = ConditionDictionary(conditions_from_rows("Guta,gout\n"))
        with patch("backend.ai.index_state.dictionary_snapshot", return_value=("hash", dictionary)):
            self.assertIs(conditions.load_dictionary(), dictionary)


if __name__ == "__main__":
    unittest.main()
