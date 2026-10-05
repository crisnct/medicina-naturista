"""Tests for the medicinal-plant catalogue (backend.ai.herbs)."""
from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from backend.ai import herbs
from backend.ai.conditions import _normalize
from backend.ai.herbs import FIELDS, Herb, HerbCatalog, parse_herbs


def line(**overrides) -> str:
    record = {
        "id": "matricaria-chamomilla", "ro": "Musetel", "ro_regional": ["romanita", "matricea"],
        "latin": "Matricaria chamomilla", "latin_synonyms": ["Matricaria recutita", "Chamomilla recutita"],
        "en": "German chamomile", "en_alt": ["wild chamomile"], "family": "Asteraceae",
    }
    record.update(overrides)
    return json.dumps(record)


MONOGYNA = line(id="crataegus-monogyna", ro="Paducel", ro_regional=["gherghinar"], latin="Crataegus monogyna",
                latin_synonyms=[], en="Common hawthorn", en_alt=["single-seeded hawthorn"], family="Rosaceae")
LAEVIGATA = line(id="crataegus-laevigata", ro="Paducel", ro_regional=["gherghinar"], latin="Crataegus laevigata",
                 latin_synonyms=["Crataegus oxyacantha"], en="Midland hawthorn", en_alt=[], family="Rosaceae")
BIRCH_POLYPORE = line(id="fomitopsis-betulina", ro="Iasca de mesteacan", ro_regional=[], latin="Fomitopsis betulina",
                      latin_synonyms=["Piptoporus betulinus"], en="", en_alt=[], family="Fomitopsidaceae")
# A valid catalogue, sorted by ro then latin, as the shipped file must be.
SAMPLE = "\n".join([BIRCH_POLYPORE, line(), LAEVIGATA, MONOGYNA]) + "\n"

SLUG = re.compile(r"[a-z]+(-[a-z]+)+")
# Genus, optional hybrid sign, epithet (may hold a hyphen: "uva-ursi"),
# optional subspecies or variety; no author.
LATIN = re.compile(r"[A-Z][a-z]+ (x )?[a-z]+(-[a-z]+)?( (subsp|var)\. [a-z]+(-[a-z]+)?)?")


# The content rules of the shipped catalogue (beyond the schema parse_herbs()
# enforces): every broken rule as one message, [] when the text is valid.
def content_problems(text: str) -> list[str]:
    problems: list[str] = []
    lines = [item for item in text.splitlines() if item.strip()]
    parsed = parse_herbs(text)
    for number, (raw, herb) in enumerate(zip(lines, parsed), 1):
        where = f"line {number} ({herb.latin})"
        if list(json.loads(raw)) != list(FIELDS):
            problems.append(f"{where}: keys out of order")
        strings = (herb.id, herb.ro, herb.latin, herb.en, herb.family,
                   *herb.ro_regional, *herb.latin_synonyms, *herb.en_alt)
        if not all(value.isascii() for value in strings):
            problems.append(f"{where}: non-ASCII text")
        if any("," in value for value in strings):
            problems.append(f"{where}: a name holds a comma")
        if any(value != " ".join(value.split()) for value in strings):
            problems.append(f"{where}: stray spaces")
        if not SLUG.fullmatch(herb.id):
            problems.append(f"{where}: id is not a slug")
        if not herb.ro[:1].isupper():
            problems.append(f"{where}: ro does not start with a capital")
        for latin in (herb.latin, *herb.latin_synonyms):
            if not LATIN.fullmatch(latin):
                problems.append(f"{where}: {latin!r} is not a Latin species name without author")
        if not herb.family.endswith("aceae"):
            problems.append(f"{where}: family does not end in -aceae")
        if _normalize(herb.ro) in {_normalize(name) for name in herb.ro_regional}:
            problems.append(f"{where}: ro repeated in ro_regional")
        if herb.en and _normalize(herb.en) in {_normalize(name) for name in herb.en_alt}:
            problems.append(f"{where}: en repeated in en_alt")
        if not herb.en and herb.en_alt:
            problems.append(f"{where}: en_alt without en")
        for field in ("ro_regional", "latin_synonyms", "en_alt"):
            keys = [_normalize(name) for name in getattr(herb, field)]
            if len(keys) != len(set(keys)):
                problems.append(f"{where}: duplicates in {field}")
    order = [(_normalize(herb.ro), _normalize(herb.latin)) for herb in parsed]
    if order != sorted(order):
        problems.append("lines are not sorted by ro, then latin")
    ids = [herb.id for herb in parsed]
    problems += [f"id {item!r} repeated" for item in sorted({i for i in ids if ids.count(i) > 1})]
    owners: dict[str, str] = {}  # normalized Latin name or synonym -> latin of its species
    for herb in parsed:
        for latin in (herb.latin, *herb.latin_synonyms):
            key = _normalize(latin)
            if key in owners and owners[key] != herb.latin:
                problems.append(f"{latin!r} belongs to both {owners[key]!r} and {herb.latin!r}")
            owners.setdefault(key, herb.latin)
    return problems


class ParseTests(unittest.TestCase):
    def test_a_line_becomes_a_herb_with_tuples_for_the_lists(self):
        (herb,) = parse_herbs(line())

        self.assertEqual(herb, Herb(
            id="matricaria-chamomilla", ro="Musetel", ro_regional=("romanita", "matricea"),
            latin="Matricaria chamomilla", latin_synonyms=("Matricaria recutita", "Chamomilla recutita"),
            en="German chamomile", en_alt=("wild chamomile",), family="Asteraceae",
        ))

    def test_blank_lines_are_skipped_and_an_empty_english_name_is_accepted(self):
        parsed = parse_herbs(line() + "\n\n" + BIRCH_POLYPORE + "\n")

        self.assertEqual([herb.id for herb in parsed], ["matricaria-chamomilla", "fomitopsis-betulina"])
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

        self.assertEqual(herb.names, ("Iasca de mesteacan", "Fomitopsis betulina", "Piptoporus betulinus"))


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = HerbCatalog(parse_herbs(SAMPLE))

    def test_by_id(self):
        self.assertEqual(self.catalog.by_id("crataegus-laevigata").latin, "Crataegus laevigata")
        self.assertIsNone(self.catalog.by_id("crataegus"))

    def test_by_latin_finds_the_accepted_name_and_the_synonyms(self):
        self.assertEqual(self.catalog.by_latin("matricaria chamomilla").id, "matricaria-chamomilla")
        self.assertEqual(self.catalog.by_latin("Chamomilla recutita").id, "matricaria-chamomilla")
        self.assertEqual(self.catalog.by_latin("Piptoporus betulinus").id, "fomitopsis-betulina")
        self.assertIsNone(self.catalog.by_latin("Crataegus"))

    def test_lookup_ignores_case_and_diacritics(self):
        self.assertEqual([herb.id for herb in self.catalog.lookup("MUȘEȚEL")], ["matricaria-chamomilla"])
        self.assertEqual([herb.id for herb in self.catalog.lookup("romaniță")], ["matricaria-chamomilla"])
        self.assertEqual([herb.id for herb in self.catalog.lookup("german chamomile")], ["matricaria-chamomilla"])

    def test_a_shared_romanian_name_returns_every_species(self):
        self.assertEqual([herb.id for herb in self.catalog.lookup("Paducel")], ["crataegus-laevigata", "crataegus-monogyna"])
        self.assertEqual(len(self.catalog.lookup("gherghinar")), 2)

    def test_an_empty_name_matches_nothing(self):
        # the birch polypore has no English name: "" is not a name
        self.assertEqual(self.catalog.lookup(""), [])
        self.assertEqual(self.catalog.lookup("  "), [])

    def test_an_unknown_name_matches_nothing(self):
        self.assertEqual(self.catalog.lookup("mentă"), [])


class FileLoadingTests(unittest.TestCase):
    def test_missing_file_gives_an_empty_catalog(self):
        catalog = herbs.load_herbs(Path(tempfile.gettempdir()) / "definitely-missing-herbs.jsonl")

        self.assertEqual(catalog.herbs, [])
        self.assertEqual(catalog.lookup("musetel"), [])

    def test_file_is_loaded_and_reloaded_when_it_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "herbs.jsonl"
            path.write_text(line() + "\n", encoding="utf-8")
            self.assertEqual(len(herbs.load_herbs(path).herbs), 1)

            path.write_text(SAMPLE, encoding="utf-8")
            os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 5_000_000_000))

            self.assertEqual(len(herbs.load_herbs(path).herbs), 4)


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
            "duplicates in latin_synonyms": line(latin_synonyms=["Matricaria recutita", "matricaria recutita"]),
        }
        for expected, broken in cases.items():
            with self.subTest(rule=expected):
                problems = content_problems(broken + "\n")
                self.assertTrue(any(expected in problem for problem in problems), problems)

    def test_catalogue_wide_rules_are_reported(self):
        unsorted = content_problems(MONOGYNA + "\n" + LAEVIGATA + "\n")
        repeated_id = content_problems(LAEVIGATA + "\n" + MONOGYNA.replace("crataegus-monogyna", "crataegus-laevigata") + "\n")
        shared_synonym = content_problems(
            LAEVIGATA + "\n" + MONOGYNA.replace('"latin_synonyms": []', '"latin_synonyms": ["Crataegus oxyacantha"]') + "\n"
        )

        self.assertIn("lines are not sorted by ro, then latin", unsorted)
        self.assertIn("id 'crataegus-laevigata' repeated", repeated_id)
        self.assertTrue(any("belongs to both" in problem for problem in shared_synonym), shared_synonym)

    def test_a_hybrid_and_a_hyphenated_epithet_are_latin_names(self):
        for latin in ("Mentha x piperita", "Arctostaphylos uva-ursi", "Achillea millefolium subsp. collina"):
            with self.subTest(latin=latin):
                self.assertTrue(LATIN.fullmatch(latin))


@unittest.skipUnless(herbs.settings.herbs_file.exists(), "data/herbs.jsonl is created in stage E4 of the plan")
class ShippedCatalogueTests(unittest.TestCase):
    def test_shipped_catalogue_follows_every_rule(self):
        text = herbs.settings.herbs_file.read_text(encoding="utf-8")

        self.assertEqual(content_problems(text), [])


if __name__ == "__main__":
    unittest.main()
