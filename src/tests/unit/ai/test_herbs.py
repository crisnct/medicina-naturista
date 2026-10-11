"""Tests for the medicinal-plant catalogue (backend.ai.herbs)."""

from __future__ import annotations

import json
import unittest

from backend.ai.herb_validation import LATIN, content_problems, convert_source
from backend.ai.herbs import HerbCatalog, SourceHerb, parse_herbs


def line(**overrides) -> str:
    record = {
        "id": "matricaria-chamomilla",
        "ro": "Musetel",
        "ro_regional": ["romanita", "matricea"],
        "latin": "Matricaria chamomilla",
        "latin_synonyms": ["Matricaria recutita", "Chamomilla recutita"],
        "en": "German chamomile",
        "en_alt": ["wild chamomile"],
        "family": "Asteraceae",
    }
    record.update(overrides)
    return json.dumps(record)


MONOGYNA = line(
    id="crataegus-monogyna",
    ro="Paducel",
    ro_regional=["gherghinar"],
    latin="Crataegus monogyna",
    latin_synonyms=[],
    en="Common hawthorn",
    en_alt=["single-seeded hawthorn"],
    family="Rosaceae",
)
LAEVIGATA = line(
    id="crataegus-laevigata",
    ro="Paducel",
    ro_regional=["gherghinar"],
    latin="Crataegus laevigata",
    latin_synonyms=["Crataegus oxyacantha"],
    en="Midland hawthorn",
    en_alt=[],
    family="Rosaceae",
)
BIRCH_POLYPORE = line(
    id="fomitopsis-betulina",
    ro="Iasca de mesteacan",
    ro_regional=[],
    latin="Fomitopsis betulina",
    latin_synonyms=["Piptoporus betulinus"],
    en="",
    en_alt=[],
    family="Fomitopsidaceae",
)
# A valid catalogue, sorted by ro then latin, as the shipped file must be.
SAMPLE = "\n".join([BIRCH_POLYPORE, line(), LAEVIGATA, MONOGYNA]) + "\n"


class ParseTests(unittest.TestCase):
    def test_a_line_becomes_a_herb_with_tuples_for_the_lists(self):
        (herb,) = parse_herbs(line())

        self.assertEqual(
            herb,
            SourceHerb(
                id="matricaria-chamomilla",
                ro="Musetel",
                ro_regional=("romanita", "matricea"),
                latin="Matricaria chamomilla",
                latin_synonyms=("Matricaria recutita", "Chamomilla recutita"),
                en="German chamomile",
                en_alt=("wild chamomile",),
                family="Asteraceae",
            ),
        )

    def test_blank_lines_are_skipped_and_an_empty_english_name_is_accepted(self):
        parsed = parse_herbs(line() + "\n\n" + BIRCH_POLYPORE + "\n")

        self.assertEqual(
            [herb.id for herb in parsed], ["matricaria-chamomilla", "fomitopsis-betulina"]
        )
        self.assertEqual(parsed[1].en, "")

    def test_an_invalid_line_raises_with_its_number(self):
        record = json.loads(line())
        missing = {key: value for key, value in record.items() if key != "family"}
        for broken in (
            line()[:-1],  # truncated JSON
            json.dumps(list(record.values())),
            json.dumps(missing),
            json.dumps({**record, "parts_used": ["flori"]}),
            line(ro=""),
            line(latin=" "),
            line(family=None),
            line(en=None),
            line(ro_regional="romanita"),
            line(en_alt=["wild chamomile", 3]),
            line(latin_synonyms=[""]),
        ):
            with self.subTest(line=broken), self.assertRaisesRegex(ValueError, "line 2"):
                parse_herbs(line() + "\n" + broken)

    def test_names_lists_every_non_empty_name(self):
        (herb,) = parse_herbs(BIRCH_POLYPORE)

        self.assertEqual(
            herb.names, ("Iasca de mesteacan", "Fomitopsis betulina", "Piptoporus betulinus")
        )


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = HerbCatalog(list(convert_source(parse_herbs(SAMPLE))))

    def test_by_id(self):
        self.assertEqual(self.catalog.by_id(3).latin, "crataegus laevigata")
        self.assertIsNone(self.catalog.by_id("crataegus"))

    def test_by_latin_finds_the_accepted_name_and_the_synonyms(self):
        self.assertEqual(self.catalog.by_latin("matricaria chamomilla").id, 2)
        self.assertEqual(self.catalog.by_latin("Chamomilla recutita").id, 2)
        self.assertEqual(self.catalog.by_latin("Piptoporus betulinus").id, 1)
        self.assertIsNone(self.catalog.by_latin("Crataegus"))

    def test_lookup_ignores_case_and_diacritics(self):
        self.assertEqual([herb.id for herb in self.catalog.lookup("MUȘEȚEL")], [2])
        self.assertEqual([herb.id for herb in self.catalog.lookup("romaniță")], [2])
        self.assertEqual([herb.id for herb in self.catalog.lookup("german chamomile")], [2])

    def test_a_shared_romanian_name_returns_every_species(self):
        self.assertEqual(
            [herb.id for herb in self.catalog.lookup("Paducel")],
            [3, 4],
        )
        self.assertEqual(len(self.catalog.lookup("gherghinar")), 2)

    def test_an_empty_name_matches_nothing(self):
        # the birch polypore has no English name: "" is not a name
        self.assertEqual(self.catalog.lookup(""), [])
        self.assertEqual(self.catalog.lookup("  "), [])

    def test_an_unknown_name_matches_nothing(self):
        self.assertEqual(self.catalog.lookup("mentă"), [])


class ContentRulesTests(unittest.TestCase):
    def test_a_valid_catalogue_has_no_problems(self):
        self.assertEqual(content_problems(SAMPLE), [])

    def test_each_broken_rule_is_reported(self):
        cases = {
            "keys out of order": json.dumps({"ro": "Musetel", **json.loads(line())}),
            "non-ASCII": line(ro="Mușețel"),
            "comma": line(ro_regional=["romanita, matricea"]),
            "stray spaces": line(en="German  chamomile"),
            "not a slug": line(id="Matricaria_chamomilla"),
            "capital": line(ro="musetel"),
            "without author": line(latin="Matricaria chamomilla L."),
            "-aceae": line(family="Compositae"),
            "ro repeated": line(ro_regional=["musetel"]),
            "en repeated": line(en_alt=["German chamomile"]),
            "en_alt without en": line(en=""),
            "duplicates in latin_synonyms": line(
                latin_synonyms=["Matricaria recutita", "matricaria recutita"]
            ),
        }
        for expected, broken in cases.items():
            with self.subTest(rule=expected):
                problems = content_problems(broken + "\n")
                self.assertTrue(any(expected in problem for problem in problems), problems)

    def test_catalogue_wide_rules_are_reported(self):
        unsorted = content_problems(MONOGYNA + "\n" + LAEVIGATA + "\n")
        repeated_id = content_problems(
            LAEVIGATA + "\n" + MONOGYNA.replace("crataegus-monogyna", "crataegus-laevigata") + "\n"
        )
        shared_synonym = content_problems(
            LAEVIGATA
            + "\n"
            + MONOGYNA.replace('"latin_synonyms": []', '"latin_synonyms": ["Crataegus oxyacantha"]')
            + "\n"
        )

        self.assertIn("lines are not sorted by ro, then latin", unsorted)
        self.assertIn("id 'crataegus-laevigata' repeated", repeated_id)
        self.assertTrue(
            any("belongs to both" in problem for problem in shared_synonym), shared_synonym
        )

    def test_a_hybrid_and_a_hyphenated_epithet_are_latin_names(self):
        for latin in (
            "Mentha x piperita",
            "Arctostaphylos uva-ursi",
            "Achillea millefolium subsp. collina",
        ):
            with self.subTest(latin=latin):
                self.assertTrue(LATIN.fullmatch(latin))


# Species in medicina-naturista-documente/data/herbs.jsonl when it was delivered; the catalogue may grow, never
# shrink by accident.
DELIVERED_SPECIES = 1188


class ShippedCatalogueTests(unittest.TestCase):
    pass


if __name__ == "__main__":
    unittest.main()
