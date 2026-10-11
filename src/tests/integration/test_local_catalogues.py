"""Opt-in structural checks against the operator's local catalogues."""

import json
import os
import unittest

from backend.ai import conditions, herbs
from backend.ai.conditions import parse_conditions
from backend.config import Settings, configure_settings
from tests.unit.ai.test_herbs import DELIVERED_SPECIES, content_problems


@unittest.skipUnless(
    os.getenv("RUN_LOCAL_CORPUS_TESTS") == "1", "requires explicit local catalogue opt-in"
)
class LocalCatalogueTests(unittest.TestCase):
    def setUp(self):
        configure_settings(Settings.from_env(dotenv=True))

    def test_shipped_dictionary_is_pure_ascii(self):
        text = conditions.settings.conditions_file.read_text(encoding="utf-8")

        # Canonical names are written verbatim into chunks.primary/secondary_medical_conditions,
        # and an extraction artefact such as a soft hyphen splits a term into two
        # words ("pio\xadtorax" -> "pio torax") that the scanned text never
        # contains, so the term silently stops matching. The terms are checked,
        # not the lines, so a JSON escape ("­") cannot hide one.
        offenders = [
            term for item in parse_conditions(text) for term in item.terms if not term.isascii()
        ]
        self.assertEqual(offenders, [])

    def test_shipped_dictionary_has_no_shared_terms(self):
        text = conditions.settings.conditions_file.read_text(encoding="utf-8")

        parsed = parse_conditions(text)
        self.assertGreater(len(parsed), 10)

        # every term belongs to exactly one condition, so a search never resolves
        # to two diseases at once
        owners: dict[str, str] = {}
        for item in parsed:
            for term in item.terms:
                key = conditions._normalize(term)
                self.assertNotIn(
                    key, owners, f"{term!r} is claimed by {item.name!r} and {owners.get(key)!r}"
                )
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

    def test_shipped_catalogue_follows_every_rule(self):
        text = herbs.settings.herbs_file.read_text(encoding="utf-8")

        self.assertEqual(content_problems(text), [])

    def test_shipped_catalogue_is_complete(self):
        catalog = herbs.load_herbs()

        self.assertGreaterEqual(len(catalog.herbs), DELIVERED_SPECIES)
        # a shared Romanian name finds every species that carries it
        found = [herb.id for herb in catalog.lookup("paducel")]
        self.assertIn("crataegus-monogyna", found)
        self.assertIn("crataegus-laevigata", found)
