"""Tests for the medical-condition dictionary (backend.ai.conditions)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.ai import conditions
from backend.ai.conditions import ConditionDictionary, parse_conditions
from tests.support.conditions import conditions_jsonl

SAMPLE = """
Adenom,tumora adenomatoasa,adenoma
Adenom de prostata,adenom prostatic,hiperplazie benigna de prostata,benign prostatic hyperplasia
Artrita gutoasa,guta articulara,artrita urica,gout
Artrita,artrita cronica,arthritis
Acnee rozacee,rozacee,cuperoza,rosacea
"""


class ParseTests(unittest.TestCase):
    def test_name_comes_first_then_the_synonyms_and_blank_lines_are_skipped(self):
        parsed = parse_conditions(
            '{"name": "Guta", "synonyms": ["artrita gutoasa", "gout"]}\n'
            "\n"
            '{"name": "Acalazie", "synonyms": []}\n'
        )

        self.assertEqual([item.name for item in parsed], ["Guta", "Acalazie"])
        self.assertEqual(parsed[0].terms, ("Guta", "artrita gutoasa", "gout"))
        self.assertEqual(parsed[1].terms, ("Acalazie",))

    def test_duplicate_terms_within_a_line_are_dropped(self):
        parsed = parse_conditions('{"name": "Acalazie", "synonyms": ["acalazie", "ACALAZIE ", "cardiospasm"]}')

        self.assertEqual(parsed[0].terms, ("Acalazie", "cardiospasm"))

    def test_an_invalid_line_raises_with_its_number(self):
        valid = '{"name": "Guta", "synonyms": ["gout"]}\n'
        for broken in (
            '{"name": "Tuse", "synonyms": ["cough"]',  # truncated JSON
            '["Tuse", "cough"]',
            '{"synonyms": ["cough"]}',
            '{"name": " ", "synonyms": []}',
            '{"name": "Tuse"}',
            '{"name": "Tuse", "synonyms": "cough"}',
            '{"name": "Tuse", "synonyms": ["cough", 3]}',
        ):
            with self.subTest(line=broken), self.assertRaisesRegex(ValueError, "line 2"):
                parse_conditions(valid + broken)


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.dictionary = ConditionDictionary(parse_conditions(conditions_jsonl(SAMPLE)))

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
        self.dictionary = ConditionDictionary(parse_conditions(conditions_jsonl(SAMPLE + "Tuse,cough\n")))

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
        self.assertEqual(self.whole("gout, tuse la copii, durere de cap, tuse"), [True, False, False, True])


class FileLoadingTests(unittest.TestCase):
    def test_missing_file_gives_an_empty_dictionary(self):
        result = conditions.load_dictionary(Path(tempfile.gettempdir()) / "definitely-missing-conditions.jsonl")

        self.assertEqual(result.conditions, [])
        self.assertEqual(result.resolve("gout").condition_names, ())

    def test_file_is_loaded_and_reloaded_when_it_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conditions.jsonl"
            path.write_text(conditions_jsonl("Guta,gout\n"), encoding="utf-8")
            self.assertEqual(conditions.load_dictionary(path).match("gout")[0].terms, ("Guta", "gout"))

            path.write_text(conditions_jsonl("Guta,gout,podagra\n"), encoding="utf-8")
            import os
            os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 5_000_000_000))

            self.assertEqual(conditions.load_dictionary(path).match("gout")[0].terms, ("Guta", "gout", "podagra"))

    def test_shipped_dictionary_parses(self):
        text = conditions.settings.conditions_file.read_text(encoding="utf-8")

        parsed = parse_conditions(text)

        self.assertGreater(len(parsed), 10)
        self.assertTrue(all(len(item.terms) >= 2 for item in parsed))

    def test_shipped_dictionary_is_pure_ascii(self):
        text = conditions.settings.conditions_file.read_text(encoding="utf-8")

        # Canonical names are written verbatim into chunks.primary/secondary_medical_conditions,
        # and an extraction artefact such as a soft hyphen splits a term into two
        # words ("pio\xadtorax" -> "pio torax") that the scanned text never
        # contains, so the term silently stops matching. The terms are checked,
        # not the lines, so a JSON escape ("­") cannot hide one.
        offenders = [term for item in parse_conditions(text) for term in item.terms if not term.isascii()]
        self.assertEqual(offenders, [])

    def test_shipped_dictionary_has_no_duplicate_conditions(self):
        text = conditions.settings.conditions_file.read_text(encoding="utf-8")

        parsed = parse_conditions(text)

        # one line per disease: the canonical name may not repeat
        names = [conditions._normalize(item.name) for item in parsed]
        self.assertEqual(len(names), len(set(names)))

    def test_shipped_dictionary_has_no_shared_terms(self):
        text = conditions.settings.conditions_file.read_text(encoding="utf-8")

        parsed = parse_conditions(text)

        # every term belongs to exactly one condition, so a search never resolves
        # to two diseases at once
        owners: dict[str, str] = {}
        for item in parsed:
            for term in item.terms:
                key = conditions._normalize(term)
                self.assertNotIn(key, owners,
                                 f"{term!r} is claimed by {item.name!r} and {owners.get(key)!r}")
                owners[key] = item.name

    def test_shipped_dictionary_lines_are_complete(self):
        text = conditions.settings.conditions_file.read_text(encoding="utf-8")

        for number, line in enumerate(text.splitlines(), 1):
            with self.subTest(line=number):
                record = json.loads(line)
                self.assertEqual(list(record), ["name", "synonyms"])
                terms = [record["name"], *record["synonyms"]]
                # canonical name + 3 Romanian + 3 English synonyms
                self.assertGreaterEqual(len(record["synonyms"]), 6)
                for term in terms:
                    # no blank term, no stray spaces
                    self.assertEqual(term, " ".join(term.split()))
                    self.assertTrue(term)
                    # a message is split at commas, so a term with a comma could never match
                    self.assertNotIn(",", term)
                # written without duplicates: parsing drops none of the terms
                self.assertEqual(len(parse_conditions(line)[0].terms), len(terms))


if __name__ == "__main__":
    unittest.main()
