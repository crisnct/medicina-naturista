from __future__ import annotations

import unittest

from medicina_naturista.ai import fragmenter
from medicina_naturista.ai.conditions import ConditionDictionary, parse_conditions
from medicina_naturista.ai.fragmenter import Fragment, fragment_document

DICTIONARY = ConditionDictionary(parse_conditions(
    "Gripa,gripe,influenza\n"
    "Febra,fever\n"
    "Constipatie\n"
    "Acnee,acne\n"
    "Adenom\n"
    "Adenom colonic\n"
    "RA\n"
))


def split(text: str, path: str = "carte.md") -> list[Fragment]:
    return fragment_document(text, path, DICTIONARY)


def sentences(count: int) -> str:
    return " ".join(f"Propoziția numărul {index} descrie un remediu." for index in range(count))


class ConditionDetectionTests(unittest.TestCase):
    def test_finds_whole_words_ignoring_case_and_diacritics(self):
        self.assertEqual([c.name for c in DICTIONARY.find("Ceai pentru GRIPĂ și febră")], ["Gripa", "Febra"])
        self.assertEqual([c.name for c in DICTIONARY.find("Utila in febra, amenoree")], ["Febra"])

    def test_folds_romanian_endings(self):
        self.assertEqual([c.name for c in DICTIONARY.find("tratamentul gripei")], ["Gripa"])
        self.assertEqual([c.name for c in DICTIONARY.find("cauzele febrei")], ["Febra"])

    def test_does_not_match_inside_other_words(self):
        self.assertEqual(DICTIONARY.find("constipatiecronica gripalizat"), [])

    def test_longest_term_wins_at_a_position(self):
        self.assertEqual([c.name for c in DICTIONARY.find("Adenom colonic")], ["Adenom colonic"])
        self.assertEqual([c.name for c in DICTIONARY.find("Adenom cerebral")], ["Adenom"])

    def test_there_is_no_minimum_term_length(self):
        self.assertEqual([c.name for c in DICTIONARY.find("RA este o boală")], ["RA"])

    def test_three_letter_acronyms_are_found(self):
        dictionary = ConditionDictionary(parse_conditions("Hpv,human papillomavirus\n"))

        self.assertEqual([c.name for c in dictionary.find("Natural remedies for HPV")], ["Hpv"])


class NameCriterionTests(unittest.TestCase):
    def test_file_name_with_a_condition_makes_one_fragment_of_priority_1(self):
        text = "# Titlu\n\nUn text.\n\n## Altceva\n\nAlt text."

        fragments = split(text, "Boli/Gripa.md")

        self.assertEqual(len(fragments), 1)
        self.assertEqual(fragments[0].priority, 1)
        self.assertEqual(fragments[0].conditions, ("Gripa",))
        self.assertEqual(fragments[0].path, "Gripa")
        self.assertIn("Alt text.", fragments[0].text)
        self.assertEqual((fragments[0].line_start, fragments[0].line_end), (1, 7))

    def test_folder_name_with_a_condition_counts_too(self):
        fragments = split("Doar text simplu despre remedii.", "Afectiuni/Constipatie/Nota.md")

        self.assertEqual([(f.priority, f.conditions) for f in fragments], [(1, ("Constipatie",))])

    def test_document_title_drops_the_original_extension(self):
        fragments = split("Text.", "Afectiuni/Constipatie/Constipatie rebela.rtf.md")

        self.assertEqual(fragments[0].path, "Constipatie rebela")

    def test_huge_named_document_is_split_but_keeps_its_metadata(self):
        fragments = split(sentences(1500), "Gripa.md")

        self.assertGreater(len(fragments), 1)
        self.assertTrue(all(len(f.text) <= fragmenter.MAX_FRAGMENT_CHARS for f in fragments))
        self.assertTrue(all((f.priority, f.conditions) == (1, ("Gripa",)) for f in fragments))


class PlainTextTests(unittest.TestCase):
    def test_short_text_is_one_fragment_of_priority_5(self):
        text = "Coada-calului ajută la infecții urinare.\nSe bea ceai."

        fragments = split(text)

        self.assertEqual(fragments, [Fragment(text, 1, 2, "", 5, ())])

    def test_long_text_is_cut_after_the_sentence_that_crosses_3000(self):
        fragments = split(sentences(200))

        self.assertGreater(len(fragments), 1)
        self.assertTrue(all(f.priority == 5 and f.conditions == () for f in fragments))
        for fragment in fragments[:-1]:
            self.assertGreaterEqual(len(fragment.text), fragmenter.PLAIN_CHUNK_CHARS)
            self.assertLess(len(fragment.text), fragmenter.PLAIN_CHUNK_CHARS + 100)
            self.assertTrue(fragment.text.endswith("."))
        self.assertEqual(" ".join(f.text for f in fragments), sentences(200))

    def test_text_without_sentence_ends_is_cut_at_a_line_break(self):
        rows = "\n".join(f"| Rând {index} | valoare |" for index in range(600))

        fragments = split(rows)

        self.assertGreater(len(fragments), 1)
        self.assertTrue(all(len(f.text) <= fragmenter.PLAIN_HARD_CAP_CHARS for f in fragments))
        self.assertEqual("\n".join(f.text for f in fragments), rows)

    def test_file_with_only_page_markers_as_headings_is_plain_text(self):
        fragments = split("### Pagina 1\n\nText.\n\n### Pagina 2\n\nMai mult text.")

        self.assertEqual(len(fragments), 1)
        self.assertEqual(fragments[0].priority, 5)
        self.assertNotIn("Pagina", fragments[0].text)


BOOK = (
    "# Vindecare prin nutritie\n"
    "Carte cu remedii naturiste\n"
    "## Gripa\n"
    "Remedii naturiste: ceai de scortisoara\n"
    "### Nutritie\n"
    "Ceai de lamaie\n"
    "## Acnee\n"
    "Remedii naturiste: gel cu armurariu"
)


class HeadingCriterionTests(unittest.TestCase):
    def test_condition_heading_takes_its_whole_subtree_with_its_path(self):
        fragments = split(BOOK)

        gripa = next(f for f in fragments if f.conditions == ("Gripa",))
        self.assertEqual(gripa.priority, 1)
        self.assertEqual(gripa.path, "Vindecare prin nutritie > Gripa")
        self.assertEqual(
            gripa.text,
            "## Gripa\nRemedii naturiste: ceai de scortisoara\n### Nutritie\nCeai de lamaie",
        )
        self.assertEqual((gripa.line_start, gripa.line_end), (3, 6))

        acnee = next(f for f in fragments if f.conditions == ("Acnee",))
        self.assertEqual((acnee.priority, acnee.path), (1, "Vindecare prin nutritie > Acnee"))
        self.assertEqual((acnee.line_start, acnee.line_end), (7, 8))

    def test_the_rest_of_the_document_is_priority_5_with_headings(self):
        fragments = split(BOOK)

        rest = [f for f in fragments if f.priority == 5]
        self.assertEqual(len(rest), 1)
        self.assertEqual(rest[0].text, "# Vindecare prin nutritie\nCarte cu remedii naturiste")
        self.assertEqual(rest[0].conditions, ())

    def test_nested_condition_heading_is_folded_into_the_outer_fragment(self):
        text = "# Carte\n## Gripa\nText.\n### Febra\nMai mult text.\n## Altceva\nText."

        fragments = split(text)

        conditions = [f for f in fragments if f.priority == 1]
        self.assertEqual(len(conditions), 1)
        self.assertEqual(conditions[0].conditions, ("Gripa", "Febra"))
        self.assertIn("### Febra", conditions[0].text)

    def test_page_marker_headings_are_neither_path_nor_text(self):
        text = "# Carte\n### Pagina 3\n## Gripa\nText.\n### Pagina 4\nContinuare."

        gripa = next(f for f in split(text) if f.priority == 1)

        self.assertEqual(gripa.path, "Carte > Gripa")
        self.assertNotIn("Pagina", gripa.text)
        self.assertIn("Continuare.", gripa.text)


DICTIONARY_BOOK = (
    "# Dictionarul plantelor de leac\n"
    "Carte cu remedii naturiste\n"
    "## Coada soricelului\n"
    "Utila in febra, amenoree, dispnee, migrene.\n"
    "## Lavanda\n"
    "Utila in dureri de cap."
)


class MentionCriterionTests(unittest.TestCase):
    def test_section_mentioning_a_condition_gets_ancestor_headings_but_no_intro(self):
        fragments = split(DICTIONARY_BOOK)

        febra = next(f for f in fragments if f.priority == 3)
        self.assertEqual(
            febra.text,
            "# Dictionarul plantelor de leac\n## Coada soricelului\nUtila in febra, amenoree, dispnee, migrene.",
        )
        self.assertNotIn("Carte cu remedii", febra.text)
        self.assertEqual(febra.conditions, ("Febra",))
        self.assertEqual(febra.path, "Dictionarul plantelor de leac > Coada soricelului")
        self.assertEqual((febra.line_start, febra.line_end), (3, 4))

    def test_sections_without_a_condition_are_priority_5(self):
        fragments = split(DICTIONARY_BOOK)

        lavanda = next(f for f in fragments if "Lavanda" in f.text)
        self.assertEqual((lavanda.priority, lavanda.conditions), (5, ()))
        self.assertEqual(
            lavanda.text,
            "# Dictionarul plantelor de leac\n## Lavanda\nUtila in dureri de cap.",
        )

    def test_several_conditions_in_one_section_make_one_fragment(self):
        text = "# Plante\n## Traista\nBună pentru febra, gripa și constipatie."

        fragments = [f for f in split(text) if f.priority == 3]

        self.assertEqual(len(fragments), 1)
        self.assertEqual(fragments[0].conditions, ("Febra", "Gripa", "Constipatie"))

    def test_text_taken_by_a_heading_fragment_is_not_reused(self):
        text = "# Carte\n## Gripa\nSe însoțește adesea de febra.\n## Plante\nMenta ajută la febra."

        fragments = split(text)

        self.assertEqual([f.priority for f in fragments], [1, 3])
        self.assertNotIn("Plante", fragments[0].text)
        self.assertNotIn("însoțește", fragments[1].text)

    def test_text_before_the_first_heading_is_a_section_without_title(self):
        fragments = split("Introducere despre febra.\n\n# Carte\nText fără nimic.")

        self.assertEqual((fragments[0].priority, fragments[0].path), (3, ""))
        self.assertEqual(fragments[0].text, "Introducere despre febra.")

    def test_large_section_is_split_and_keeps_its_headings_and_metadata(self):
        text = "# Carte\n## Plante\nBună pentru febra. " + sentences(1500)

        fragments = split(text)

        self.assertGreater(len(fragments), 1)
        for fragment in fragments:
            self.assertLessEqual(len(fragment.text), fragmenter.MAX_FRAGMENT_CHARS)
            self.assertTrue(fragment.text.startswith("# Carte\n## Plante\n"))
            self.assertEqual((fragment.priority, fragment.conditions), (3, ("Febra",)))


class LineRangeTests(unittest.TestCase):
    def test_line_ranges_point_at_the_fragment_text_in_the_source(self):
        source_lines = BOOK.split("\n")

        for fragment in split(BOOK):
            excerpt = "\n".join(source_lines[fragment.line_start - 1:fragment.line_end])
            for line in fragment.text.split("\n"):
                if not line.startswith("#") or line in excerpt:
                    self.assertIn(line, excerpt)


if __name__ == "__main__":
    unittest.main()
