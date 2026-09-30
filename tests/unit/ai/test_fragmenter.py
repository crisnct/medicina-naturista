from __future__ import annotations

import unittest

from medicina_naturista.ai import fragmenter
from medicina_naturista.ai.conditions import ConditionDictionary, parse_conditions
from medicina_naturista.ai.fragmenter import BusinessCategory, Fragment, fragment_document

R1, R2, D1 = BusinessCategory.R1, BusinessCategory.R2, BusinessCategory.D1

DICTIONARY = ConditionDictionary(parse_conditions(
    "Gripa,gripe,influenza,gout\n"
    "Febra,fever\n"
    "Constipatie\n"
    "Acnee,acne\n"
    "Insomnie\n"
    "Adenom\n"
    "Adenom colonic\n"
    "RA\n"
))


def split(text: str) -> list[Fragment]:
    return fragment_document(text, DICTIONARY)


def of(fragments: list[Fragment], category: BusinessCategory) -> list[Fragment]:
    return [f for f in fragments if f.business_category == category]


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


class R1Tests(unittest.TestCase):
    def test_deepest_condition_heading_alone_makes_the_fragment(self):
        text = (
            "# Vindecare prin nutritie\n"
            "## Gripa si raceala\n"
            "### Gripa - tratament naturiste\n"
            "Ceai de musetel: de doua ori pe zi."
        )

        fragments = split(text)

        self.assertEqual(fragments, [Fragment(
            "### Gripa - tratament naturiste\nCeai de musetel: de doua ori pe zi.",
            3, 4,
            "Vindecare prin nutritie > Gripa si raceala > Gripa - tratament naturiste",
            R1, ("Gripa",), (),
        )])

    def test_matches_a_synonym_and_an_inflected_form(self):
        fragments = split("# Gout\nUn text.\n# Tratamentul gripei\nAlt text.")

        self.assertEqual([(f.path, f.primary_conditions) for f in fragments],
                         [("Gout", ("Gripa",)), ("Tratamentul gripei", ("Gripa",))])
        self.assertTrue(all(f.business_category == R1 for f in fragments))

    def test_parent_and_child_condition_headings_are_separate_and_disjoint(self):
        text = "# Carte\n## Gripa\nText raceala.\n### Febra\nText caldura.\n### Plante\nText plante.\n## Altceva\nText."

        fragments = split(text)

        gripa = next(f for f in fragments if f.path == "Carte > Gripa")
        febra = next(f for f in fragments if f.path == "Carte > Gripa > Febra")
        self.assertEqual(gripa.text, "## Gripa\nText raceala.\n### Plante\nText plante.")
        self.assertEqual(febra.text, "### Febra\nText caldura.")
        self.assertEqual((febra.line_start, febra.line_end), (4, 5))
        self.assertEqual((gripa.line_start, gripa.line_end), (2, 7))
        self.assertEqual(gripa.primary_conditions, ("Gripa",))
        self.assertEqual(febra.primary_conditions, ("Febra",))
        self.assertEqual(gripa.secondary_conditions, ())

    def test_heading_left_without_text_makes_no_fragment_and_is_not_d1(self):
        fragments = split("# Carte\n## Gripa\n### Febra\nText febra.")

        self.assertEqual([f.path for f in fragments], ["Carte > Gripa > Febra"])

    def test_condition_in_the_text_of_an_r1_is_secondary_only(self):
        fragments = split("# Carte\n## Gripa\nSe însoțește de febra și de insomnie.\n## Altceva\nText.")

        gripa = next(f for f in fragments if f.business_category == R1)
        self.assertEqual(gripa.primary_conditions, ("Gripa",))
        self.assertEqual(gripa.secondary_conditions, ("Febra", "Insomnie"))
        self.assertEqual(of(fragments, R2), [])

    def test_a_condition_in_both_title_and_text_is_in_both_columns(self):
        fragments = split("## Gripa\nGripa se vindecă.")

        self.assertEqual(fragments[0].primary_conditions, ("Gripa",))
        self.assertEqual(fragments[0].secondary_conditions, ("Gripa",))

    def test_conditions_in_ancestor_headings_are_never_read(self):
        fragments = split("# Gripa\n## Plante\nCeai de mușețel.\n### Febra\nLa febra se bea ceai.")

        by_path = {f.path: f for f in fragments}
        febra = by_path["Gripa > Plante > Febra"]
        self.assertEqual(febra.primary_conditions, ("Febra",))
        self.assertNotIn("Gripa", febra.secondary_conditions)
        self.assertEqual(by_path["Gripa"].business_category, R1)

    def test_r1_has_no_size_limit(self):
        fragments = split("# Carte\n## Gripa\n" + sentences(2000))

        self.assertEqual(len(fragments), 1)
        self.assertGreater(len(fragments[0].text), 50_000)

    def test_page_markers_are_neither_path_nor_text(self):
        text = "# Carte\n### Pagina 3\n## Gripa\nText.\n### Pagina 4\nContinuare."

        gripa = next(f for f in split(text) if f.business_category == R1)

        self.assertEqual(gripa.path, "Carte > Gripa")
        self.assertNotIn("Pagina", gripa.text)
        self.assertIn("Continuare.", gripa.text)


class R2Tests(unittest.TestCase):
    def test_section_mentioning_a_condition_is_only_its_heading_and_text(self):
        text = "# Vindecare prin nutritie\n## Plante utile\n### Musetel\nCeaiul de musetel ajuta in gripa si in insomnie."

        fragments = split(text)

        self.assertEqual(fragments, [Fragment(
            "### Musetel\nCeaiul de musetel ajuta in gripa si in insomnie.", 3, 4,
            "Vindecare prin nutritie > Plante utile > Musetel", R2, (), ("Gripa", "Insomnie"),
        )])

    def test_introductions_of_ancestors_are_not_included(self):
        fragments = split("# Dictionar\nCarte cu remedii\n## Coada\nUtila in febra, amenoree.\n## Lavanda\nUtila in dureri de cap.")

        febra = of(fragments, R2)[0]
        self.assertEqual(febra.text, "## Coada\nUtila in febra, amenoree.")
        self.assertNotIn("Carte cu remedii", febra.text)

    def test_several_conditions_in_one_section_make_one_fragment(self):
        fragments = of(split("# Plante\n## Traista\nBună pentru febra, gripa și constipatie."), R2)

        self.assertEqual(len(fragments), 1)
        self.assertEqual(fragments[0].secondary_conditions, ("Febra", "Gripa", "Constipatie"))

    def test_r2_never_has_primary_conditions(self):
        fragments = of(split("# Carte\n## Plante\nMenta ajută la febra.\n## Altele\nAcnee vulgară."), R2)

        self.assertEqual(len(fragments), 2)
        self.assertTrue(all(f.primary_conditions == () for f in fragments))

    def test_text_taken_by_an_r1_is_not_reused_by_an_r2(self):
        fragments = split("# Carte\n## Gripa\nSe însoțește adesea de febra.\n## Plante\nMenta ajută la febra.")

        self.assertEqual([f.business_category for f in fragments], [R1, R2])
        self.assertNotIn("Plante", fragments[0].text)
        self.assertNotIn("însoțește", fragments[1].text)

    def test_r2_only_takes_the_own_text_up_to_the_next_heading(self):
        fragments = split("# Plante\nBune pentru febra.\n## Menta\nCeai de mentă.")

        r2 = of(split("# Plante\nBune pentru febra.\n## Menta\nCeai de mentă."), R2)
        self.assertEqual(r2[0].text, "# Plante\nBune pentru febra.")
        self.assertEqual([f.business_category for f in fragments], [R2, D1])

    def test_r2_has_no_size_limit(self):
        fragments = of(split("# Carte\n## Plante\nBună pentru febra. " + sentences(2000)), R2)

        self.assertEqual(len(fragments), 1)
        self.assertGreater(len(fragments[0].text), 50_000)


class D1Tests(unittest.TestCase):
    def test_text_without_headings_is_d1_even_when_it_mentions_a_condition(self):
        text = "Coada-calului ajută la infecții urinare.\nSe bea ceai pentru gripa."

        self.assertEqual(split(text), [Fragment(text, 1, 2, "", D1)])

    def test_text_before_the_first_heading_is_d1(self):
        fragments = split("Introducere despre febra.\n\n# Carte\nText fără nimic.")

        self.assertEqual([(f.business_category, f.path) for f in fragments], [(D1, "")])
        self.assertEqual(fragments[0].text, "Introducere despre febra.\n\n# Carte\nText fără nimic.")

    def test_d1_has_no_conditions(self):
        fragments = of(split("# Carte\nCeva.\n## Gripa\nText.\n## Lavanda\nUtila la dureri."), D1)

        self.assertTrue(fragments)
        self.assertTrue(all(f.primary_conditions == () and f.secondary_conditions == () for f in fragments))

    def test_pieces_are_about_1800_characters_with_a_bounded_overlap(self):
        text = sentences(400)

        pieces = split(text)

        self.assertGreater(len(pieces), 3)
        self.assertTrue(all(f.business_category == D1 for f in pieces))
        for piece in pieces[:-1]:
            self.assertGreaterEqual(len(piece.text), fragmenter.D1_MIN_CHARS)
            self.assertLessEqual(len(piece.text), fragmenter.D1_MAX_CHARS)
            self.assertTrue(piece.text.endswith("."))
        for previous, following in zip(pieces, pieces[1:]):
            self.assertLessEqual(_overlap(previous.text, following.text), fragmenter.D1_MAX_OVERLAP_CHARS)
        self.assertGreaterEqual(len(pieces[-1].text), fragmenter.D1_MIN_TAIL_CHARS)

    def test_pieces_overlap_and_together_cover_the_whole_text(self):
        text = sentences(400)

        pieces = split(text)

        self.assertTrue(any(_overlap(a.text, b.text) > 0 for a, b in zip(pieces, pieces[1:])))
        rebuilt = pieces[0].text
        for previous, following in zip(pieces, pieces[1:]):
            rebuilt += following.text[_overlap(previous.text, following.text):]
        self.assertEqual(rebuilt.replace(" ", "").replace("\n", ""), text.replace(" ", ""))

    def test_pieces_start_at_a_sentence_start(self):
        pieces = split(sentences(400))

        self.assertTrue(all(p.text.startswith("Propoziția") for p in pieces))

    def test_text_without_any_boundary_is_hard_cut(self):
        pieces = split("x" * 5000)

        self.assertEqual([len(p.text) for p in pieces[:-1]], [fragmenter.D1_MAX_CHARS] * (len(pieces) - 1))
        self.assertEqual(sum(len(p.text) for p in pieces), 5000)

    def test_text_without_sentence_ends_is_cut_at_a_line_break(self):
        rows = "\n".join(f"| Rând {index} | valoare |" for index in range(600))

        pieces = split(rows)

        self.assertGreater(len(pieces), 1)
        self.assertTrue(all(len(p.text) <= fragmenter.D1_MAX_CHARS for p in pieces))
        self.assertTrue(all(p.text.startswith("| Rând") and p.text.endswith("|") for p in pieces))

    def test_a_piece_never_crosses_text_taken_by_an_r1_or_r2(self):
        text = f"# Carte\n{sentences(150)}\n## Gripa\nText gripa.\n## Altele\n{sentences(150)}"

        fragments = split(text)

        gripa = of(fragments, R1)[0]
        for piece in of(fragments, D1):
            self.assertNotIn("Text gripa", piece.text)
            self.assertFalse(piece.line_start <= gripa.line_start <= piece.line_end)
        starts = [piece.line_start for piece in of(fragments, D1)]
        self.assertTrue(any(start < gripa.line_start for start in starts))
        self.assertTrue(any(start > gripa.line_end for start in starts))

    def test_a_stretch_of_only_headings_makes_no_fragment(self):
        self.assertEqual(split("# Carte\n## Capitol\n### Subcapitol"), [])

    def test_a_piece_carries_the_path_of_the_section_it_starts_in(self):
        fragments = split(f"# Carte\n## Capitol\n{sentences(300)}")

        self.assertEqual(fragments[0].path, "Carte")  # the first piece starts at "# Carte"
        self.assertEqual(fragments[-1].path, "Carte > Capitol")

    def test_page_marker_files_are_plain_text(self):
        fragments = split("### Pagina 1\n\nText.\n\n### Pagina 2\n\nMai mult text.")

        self.assertEqual(len(fragments), 1)
        self.assertEqual(fragments[0].business_category, D1)
        self.assertNotIn("Pagina", fragments[0].text)


# Length of the longest suffix of `first` that is also a prefix of `second`.
def _overlap(first: str, second: str) -> int:
    for size in range(min(len(first), len(second)), 0, -1):
        if first.endswith(second[:size]):
            return size
    return 0


class DocumentNameTests(unittest.TestCase):
    def test_document_names_are_not_an_input(self):
        import inspect

        self.assertEqual(list(inspect.signature(fragment_document).parameters), ["text", "dictionary"])


class LineRangeTests(unittest.TestCase):
    def test_line_ranges_point_at_the_fragment_text_in_the_source(self):
        book = (
            "# Vindecare prin nutritie\nCarte cu remedii naturiste\n## Gripa\nRemedii: ceai\n"
            "### Nutritie\nCeai de lamaie\n## Acnee\nGel cu armurariu"
        )
        source_lines = book.split("\n")

        for fragment in split(book):
            excerpt = "\n".join(source_lines[fragment.line_start - 1:fragment.line_end])
            for line in fragment.text.split("\n"):
                self.assertIn(line, excerpt)


if __name__ == "__main__":
    unittest.main()
