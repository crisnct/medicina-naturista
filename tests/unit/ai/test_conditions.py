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


class ExpansionTests(unittest.TestCase):
    def setUp(self):
        self.dictionary = ConditionDictionary(parse_conditions(SAMPLE))

    def test_expansion_lists_the_other_names_but_not_the_query_itself(self):
        expansions = self.dictionary.expansions("gout")

        self.assertEqual(expansions, ["Artrita gutoasa", "guta articulara", "artrita urica"])

    def test_no_expansion_without_a_match(self):
        self.assertEqual(self.dictionary.expansions("durere de cap"), [])


class FileLoadingTests(unittest.TestCase):
    def test_missing_file_gives_an_empty_dictionary(self):
        result = conditions.load_dictionary(Path(tempfile.gettempdir()) / "definitely-missing-conditions.txt")

        self.assertEqual(result.conditions, [])
        self.assertEqual(result.expansions("gout"), [])

    def test_file_is_loaded_and_reloaded_when_it_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conditions.txt"
            path.write_text("Guta,gout\n", encoding="utf-8")
            self.assertEqual(conditions.load_dictionary(path).expansions("gout"), ["Guta"])

            path.write_text("Guta,gout,podagra\n", encoding="utf-8")
            import os
            os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 5_000_000_000))

            self.assertEqual(conditions.load_dictionary(path).expansions("gout"), ["Guta", "podagra"])

    def test_shipped_dictionary_parses(self):
        text = conditions.settings.conditions_file.read_text(encoding="utf-8")

        parsed = parse_conditions(text)

        self.assertGreater(len(parsed), 10)
        self.assertTrue(all(len(item.terms) >= 2 for item in parsed))


if __name__ == "__main__":
    unittest.main()
