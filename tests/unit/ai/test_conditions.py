"""Tests for the medical-condition dictionary (medicina_naturista.ai.conditions)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from medicina_naturista.ai import conditions
from medicina_naturista.ai.conditions import ConditionDictionary, parse_conditions

SAMPLE = """
# comment line
Adenom,tumora adenomatoasa,adenoma
Adenom de prostata,adenom prostatic,hiperplazie benigna de prostata,benign prostatic hyperplasia

Artrita gutoasa,guta articulara,artrita urica,gout
Artrita,artrita cronica,arthritis
Acnee rozacee,rozacee,cuperoza,rosacea
"""


class ParseTests(unittest.TestCase):
    def test_first_field_is_the_name_and_blank_and_comment_lines_are_skipped(self):
        parsed = parse_conditions(SAMPLE)

        self.assertEqual([item.name for item in parsed], ["Adenom", "Adenom de prostata", "Artrita gutoasa", "Artrita", "Acnee rozacee"])
        self.assertIn("gout", parsed[2].terms)

    def test_duplicate_terms_within_a_line_are_dropped(self):
        parsed = parse_conditions("Acalazie,acalazie,ACALAZIE ,cardiospasm")

        self.assertEqual(parsed[0].terms, ("Acalazie", "cardiospasm"))


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.dictionary = ConditionDictionary(parse_conditions(SAMPLE))

    def names(self, query):
        return [item.name for item in self.dictionary.match(query)]

    def test_exact_synonym_in_english_finds_the_condition(self):
        self.assertEqual(self.names("gout"), ["Artrita gutoasa"])

    def test_match_ignores_case_and_diacritics(self):
        self.assertEqual(self.names("CUPEROZĂ"), ["Acnee rozacee"])

    def test_longest_contained_term_wins(self):
        self.assertEqual(self.names("tratament pentru adenom de prostata"), ["Adenom de prostata"])

    def test_near_identical_spelling_beats_a_shorter_contained_term(self):
        self.assertEqual(self.names("artrita gutosa"), ["Artrita gutoasa"])

    def test_unknown_query_matches_nothing(self):
        self.assertEqual(self.names("durere de cap"), [])

    def test_empty_query_matches_nothing(self):
        self.assertEqual(self.names("  ?! "), [])


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.dictionary = ConditionDictionary(parse_conditions(SAMPLE + "Tuse,cough\n"))

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
            [("tratament pentru adenom de prostata la barbati", ["Adenom de prostata"], "tratament pentru la barbati")],
        )

    def test_a_misspelled_condition_is_the_whole_segment(self):
        self.assertEqual(self.segments("artrita gutosa"), [("artrita gutosa", ["Artrita gutoasa"], "")])

    def test_each_comma_separated_segment_is_recognised_on_its_own(self):
        resolved = self.dictionary.resolve("Artrita, tuse")

        self.assertEqual(resolved.condition_names, ("Artrita", "Tuse"))
        self.assertEqual(self.segments("durere de cap, tuse"), [
            ("durere de cap", [], "durere de cap"),
            ("tuse", ["Tuse"], ""),
        ])

    def test_condition_names_are_canonical_and_unique(self):
        resolved = self.dictionary.resolve("gout, artrita urica")

        self.assertEqual(resolved.condition_names, ("Artrita gutoasa",))

    def test_empty_segments_and_wordless_messages_resolve_to_nothing(self):
        self.assertEqual(self.dictionary.resolve("  ?! , ,").segments, ())
        self.assertEqual(self.dictionary.resolve("").condition_names, ())

    def test_message_without_a_condition_keeps_its_text(self):
        self.assertEqual(self.segments("durere de cap"), [("durere de cap", [], "durere de cap")])


class FileLoadingTests(unittest.TestCase):
    def test_missing_file_gives_an_empty_dictionary(self):
        result = conditions.load_dictionary(Path(tempfile.gettempdir()) / "definitely-missing-conditions.txt")

        self.assertEqual(result.conditions, [])
        self.assertEqual(result.resolve("gout").condition_names, ())

    def test_file_is_loaded_and_reloaded_when_it_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conditions.txt"
            path.write_text("Guta,gout\n", encoding="utf-8")
            self.assertEqual(conditions.load_dictionary(path).match("gout")[0].terms, ("Guta", "gout"))

            path.write_text("Guta,gout,podagra\n", encoding="utf-8")
            import os
            os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 5_000_000_000))

            self.assertEqual(conditions.load_dictionary(path).match("gout")[0].terms, ("Guta", "gout", "podagra"))

    def test_shipped_dictionary_parses(self):
        text = conditions.settings.conditions_file.read_text(encoding="utf-8")

        parsed = parse_conditions(text)

        self.assertGreater(len(parsed), 10)
        self.assertTrue(all(len(item.terms) >= 2 for item in parsed))


if __name__ == "__main__":
    unittest.main()
