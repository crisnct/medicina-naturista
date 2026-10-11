"""Tests for the medical-condition dictionary (backend.ai.conditions)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
        parsed = parse_conditions(
            '{"name": "Acalazie", "synonyms": ["acalazie", "ACALAZIE ", "cardiospasm"]}'
        )

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
        self.dictionary = ConditionDictionary(
            parse_conditions(conditions_jsonl(SAMPLE + "Tuse,cough\n"))
        )

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


class FileLoadingTests(unittest.TestCase):
    def test_query_and_index_validation_share_one_parse_for_unchanged_bytes(self):
        from dataclasses import replace

        from backend.ai import index_state

        conditions._parsed_dictionary.cache_clear()
        self.addCleanup(conditions._parsed_dictionary.cache_clear)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conditions.jsonl"
            path.write_text(conditions_jsonl("Guta,gout\n"), encoding="utf-8")
            with (
                patch.object(
                    index_state, "settings", replace(conditions.settings, conditions_file=path)
                ),
                patch.object(
                    conditions, "parse_conditions", wraps=conditions.parse_conditions
                ) as parser,
            ):
                first = conditions.load_dictionary(path)
                fingerprint, indexed = index_state.dictionary_snapshot()
                self.assertIs(first, indexed)
                self.assertIs(first, conditions.load_dictionary(path))
                self.assertEqual(index_state.dictionary_snapshot()[0], fingerprint)
                parser.assert_called_once()

                path.write_text(conditions_jsonl("Guta,gout,podagra\n"), encoding="utf-8")
                changed_fingerprint, changed = index_state.dictionary_snapshot()
                self.assertNotEqual(changed_fingerprint, fingerprint)
                self.assertIsNot(changed, first)
                self.assertIs(changed, conditions.load_dictionary(path))
                self.assertEqual(parser.call_count, 2)

    def test_concurrent_initial_loads_parse_the_dictionary_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from time import sleep

        conditions._parsed_dictionary.cache_clear()
        self.addCleanup(conditions._parsed_dictionary.cache_clear)
        raw = conditions_jsonl("Guta,gout\n").encode("utf-8")
        barrier = Barrier(8)

        def load(_):
            barrier.wait(timeout=5)
            return conditions.dictionary_from_bytes(raw)

        def slow_parse(text):
            # Release the GIL so simultaneous cache misses would overlap if
            # the initialization lock were removed.
            sleep(0.02)
            return parse_conditions(text)

        with (
            patch.object(conditions, "parse_conditions", wraps=slow_parse) as parser,
            ThreadPoolExecutor(max_workers=8) as workers,
        ):
            snapshots = list(workers.map(load, range(8)))
            self.assertTrue(all(snapshot is snapshots[0] for snapshot in snapshots))
            parser.assert_called_once()

    def test_missing_file_gives_an_empty_dictionary(self):
        result = conditions.load_dictionary(
            Path(tempfile.gettempdir()) / "definitely-missing-conditions.jsonl"
        )

        self.assertEqual(result.conditions, [])
        self.assertEqual(result.resolve("gout").condition_names, ())

    def test_file_is_loaded_and_reloaded_when_it_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conditions.jsonl"
            path.write_text(conditions_jsonl("Guta,gout\n"), encoding="utf-8")
            self.assertEqual(
                conditions.load_dictionary(path).match("gout")[0].terms, ("Guta", "gout")
            )

            path.write_text(conditions_jsonl("Guta,gout,podagra\n"), encoding="utf-8")
            import os

            os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 5_000_000_000))

            self.assertEqual(
                conditions.load_dictionary(path).match("gout")[0].terms, ("Guta", "gout", "podagra")
            )


if __name__ == "__main__":
    unittest.main()
