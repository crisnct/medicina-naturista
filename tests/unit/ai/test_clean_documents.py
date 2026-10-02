from __future__ import annotations

import io
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout
from pathlib import Path

from scripts import clean_documents
from scripts.clean_documents import (
    DigitInvariantError,
    Removed,
    check_digit_invariant,
    compact_document,
    fold_diacritics,
    strip_colophon_lines,
    strip_furniture_sections,
    strip_page_number_lines,
    strip_repeated_lines,
)


class CleanDocumentsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "documents"
        self.source.mkdir()

    def clean(self, **kwargs):
        with redirect_stdout(io.StringIO()):
            return clean_documents.clean_documents(self.source, dry_run=kwargs.pop("dry_run", False), **kwargs)

    def write(self, name: str, text: str, encoding: str = "utf-8") -> Path:
        path = self.source / name
        path.write_bytes(text.encode(encoding))
        return path

    def test_rewrites_a_file_containing_a_markdown_link(self):
        path = self.write("a.md", "Planta [sunătoare](https://example.com) ajută la ficat.\n")

        changed = self.clean()

        self.assertEqual(changed, 1)
        self.assertEqual(path.read_text(encoding="utf-8"), "Planta sunătoare ajută la ficat.\n")

    def test_leaves_an_already_compact_file_untouched(self):
        path = self.write("a.md", "Text simplu, fara linkuri sau trimiteri.\n")
        original_mtime = path.stat().st_mtime_ns

        changed = self.clean()

        self.assertEqual(changed, 0)
        self.assertEqual(path.stat().st_mtime_ns, original_mtime)

    def test_dry_run_reports_but_does_not_write(self):
        path = self.write("a.md", "Vezi și Altă afecțiune, Partea a doua.\nText rămas.\n")
        original = path.read_text(encoding="utf-8")

        output = io.StringIO()
        with redirect_stdout(output):
            changed = clean_documents.clean_documents(self.source, dry_run=True)

        self.assertEqual(changed, 1)
        self.assertEqual(path.read_text(encoding="utf-8"), original)
        self.assertIn("Would clean: a.md", output.getvalue())
        self.assertIn("Would rewrite 1/1 files", output.getvalue())

    def test_preserves_original_encoding_when_still_representable(self):
        path = self.write("a.md", "Coadă [aici](https://x.ro) ajută mult!\n", encoding="cp1250")

        self.clean()

        self.assertEqual(path.read_bytes().decode("cp1250"), "Coadă aici ajută mult!\n")

    def test_falls_back_to_utf8_when_comma_below_is_not_encodable(self):
        # The path where the fallback still matters: with folding off the cleaned
        # text keeps the comma-below s, which cp1250 cannot represent.
        path = self.write(
            "a.md", "Coad\u0103-\u015foricel ajut\u0103 mult!!\n", encoding="cp1250",
        )

        self.clean(fold_diacritics_to_ascii=False)

        self.assertEqual(path.read_bytes().decode("utf-8"), "Coadă-\u0219oricel ajută mult!!\n")

    def test_strips_extraction_metadata_title_and_scaffold(self):
        text = (
            '---\nsource_path: "C:\\\\x.pdf"\nsource_format: gdoc_pointer\nstatus: "ok"\n---\n\n'
            "# x.pdf\n\n## Pagini\n\n### Pagina 1\n\nContinut.\n"
        )
        self.assertEqual(
            clean_documents.strip_extraction_metadata(text),
            "### Pagina 1\n\nContinut.\n",
        )

    def test_strips_ocr_fence_and_trailing_note(self):
        text = (
            '---\nsource_path: "x"\n---\n\n# a.jpg\n\n## Text OCR extras\n\n```text\nun text\n```\n\n'
            "## Not\u0103\n\nTextul este rezultatul OCR local \u0219i poate con\u021bine erori.\n"
        )
        self.assertEqual(clean_documents.strip_extraction_metadata(text), "un text\n")

    def test_keeps_a_first_heading_that_is_not_the_file_name(self):
        text = '---\nsource_path: "x"\n---\n\n# Titlu real\n\nCorp.\n'
        self.assertEqual(
            clean_documents.strip_extraction_metadata(text, "carte.pdf"),
            "# Titlu real\n\nCorp.\n",
        )
        self.assertEqual(
            clean_documents.strip_extraction_metadata('---\nsource_path: "x"\n---\n\n# carte\n\nCorp.\n', "carte.docx"),
            "Corp.\n",
        )

    def test_strips_page_markers_and_the_doubled_blank_line(self):
        text = "Prima.\n\n### Pagina 8\n\nA doua.\n### Pagina 9\nA treia.\n\n## Pagina 10\n"
        self.assertEqual(
            clean_documents.strip_page_markers(text),
            "Prima.\n\nA doua.\nA treia.\n",
        )

    def test_keeps_headings_that_merely_mention_pagina(self):
        text = "### Pagina de start\n\nText.\n"
        self.assertEqual(clean_documents.strip_page_markers(text), text)

    def test_keeps_unrelated_frontmatter(self):
        text = "---\ntitle: x\n---\n\nCorp.\n"
        self.assertEqual(clean_documents.strip_extraction_metadata(text), text)

    def test_never_changes_line_count(self):
        path = self.write(
            "a.md",
            "Prima linie [etichetă](http://x.ro) rămâne.\n"
            "Vezi și Altă afecțiune, Partea a doua.\n"
            "Ultima linie.\n",
        )

        self.clean()

        cleaned = path.read_text(encoding="utf-8")
        self.assertEqual(cleaned.count("\n"), 3)


class FurnitureSectionTests(unittest.TestCase):
    def test_drops_a_contents_section_and_keeps_what_follows(self):
        text = (
            "# Carte\n\n"
            "## Cuprins\n\n"
            "Capitolul 1 ............ 5\n"
            "Capitolul 2 ............ 12\n"
            "Capitolul 3 ............ 27\n"
            "Capitolul 4 ............ 41\n"
            "Capitolul 5 ............ 58\n\n"
            "## Capitolul 1\n\nText medical important.\n"
        )

        stripped, removed = strip_furniture_sections(text)

        self.assertNotIn("Cuprins", stripped)
        self.assertNotIn("Capitolul 5", stripped)
        self.assertIn("## Capitolul 1\n\nText medical important.", stripped)
        self.assertEqual([item.rule for item in removed], ["furniture:toc"])

    def test_keeps_a_dictionary_entry_titled_index(self):
        # In "Marele dictionar al bolilor" a heading "## INDEX" introduces the
        # dictionary entry for the word, not the book's back-matter index.
        text = (
            "# Dictionar\n\n"
            "## INDEX\n\n"
            "580. INDEX Vezi: DEGETE - INDEX\n"
            "Stomacul este locul in care corpul meu fizic asimilizeaza mancarea.\n"
            "Daca fac o indigestie, corpul meu imi cere sa mananc mai incet.\n\n"
            "## Alte afectiuni\n\nText.\n"
        )

        stripped, removed = strip_furniture_sections(text)

        self.assertIn("## INDEX", stripped)
        self.assertIn("Stomacul este locul", stripped)
        self.assertEqual(removed, [])

    def test_keeps_a_mixed_heading_that_promises_more_than_references(self):
        text = (
            "# Cristale\n\n"
            "## REFERINȚE ȘI ANEXE\n\n"
            "Ametistul este o piatra pretioasa de culoare violet ....... 12\n"
            "Diamantul, regele pietrelor, se gaseste in mai multe culori ....... 34\n"
            "Rubinul este o piatra rosie folosita pentru vitalitate ....... 56\n"
        )

        stripped, removed = strip_furniture_sections(text)

        self.assertIn("Ametistul", stripped)
        self.assertEqual(removed, [])

    def test_drops_a_bibliography_at_the_end_of_a_document(self):
        filler = "Text medical care ocupa spatiul dinaintea bibliografiei. " * 20
        text = (
            "# Carte\n\n"
            "## Capitolul 1\n\n"
            f"{filler}\n\n"
            "## Bibliografie\n\n"
            "Autor A, Titlu, 1999 ....... 12\n"
            "Autor B, Titlu, 2001 ....... 34\n"
            "Autor C, Titlu, 2005 ....... 56\n"
            "Autor D, Titlu, 2008 ....... 78\n"
        )

        stripped, removed = strip_furniture_sections(text)

        self.assertNotIn("Bibliografie", stripped)
        self.assertIn("Text medical care ocupa", stripped)
        self.assertEqual([item.rule for item in removed], ["furniture:bibliography"])


class RepeatedLineTests(unittest.TestCase):
    def test_drops_the_document_title_repeated_on_every_page(self):
        title = "Vindecare prin nutritie - Phyllis A. Balch"
        text = "\n".join([title, "Text 1.", title, "Text 2.", title, "Text 3.", title, "Text 4.", title])

        stripped, removed = strip_repeated_lines(text, titles=("vindecare prin nutritie phyllis a balch",))

        self.assertEqual(stripped.split("\n").count(title), 1)
        self.assertEqual(len(removed), 4)
        self.assertTrue(all(item.rule == "running_header" for item in removed))

    def test_keeps_a_template_subheading_repeated_for_every_entry(self):
        # The regression this rule exists for: every plant's safety section in
        # "Herbal Antibiotics" is headed by the same subheading, which is content.
        line = "Side Effects and Contraindications"
        text = "\n".join([line, "None."] * 8)

        stripped, removed = strip_repeated_lines(text, titles=("herbal antibiotics",))

        self.assertEqual(stripped, text)
        self.assertEqual(removed, [])

    def test_keeps_a_table_header_repeated_on_every_page(self):
        line = "SUPLIMENT DOZA RECOMANDATA OBSERVATII"
        text = "\n".join([line, "Vitamina C 500 mg"] * 6)

        stripped, removed = strip_repeated_lines(text, titles=("vindecare prin nutritie",))

        self.assertEqual(stripped, text)
        self.assertEqual(removed, [])

    def test_never_drops_a_repeated_heading(self):
        text = "\n".join(["# Carte", "Text."] * 5)

        stripped, removed = strip_repeated_lines(text, titles=("carte",))

        self.assertEqual(stripped, text)
        self.assertEqual(removed, [])

    def test_leaves_a_title_repeated_only_four_times_alone(self):
        title = "Vindecare prin nutritie - Phyllis A. Balch"
        text = "\n".join([title, "Text 1.", title, "Text 2.", title, "Text 3.", title])

        stripped, removed = strip_repeated_lines(text, titles=("vindecare prin nutritie phyllis a balch",))

        self.assertEqual(stripped, text)
        self.assertEqual(removed, [])

    def test_never_drops_a_repeated_title_that_carries_a_dosage(self):
        title = "Carte 500 mg"
        text = "\n".join([title, "Text.", title, "Text.", title, "Text.", title, "Text.", title])

        stripped, removed = strip_repeated_lines(text, titles=("carte 500 mg",))

        self.assertEqual(stripped, text)
        self.assertEqual(removed, [])


class PageNumberLineTests(unittest.TestCase):
    def test_removes_lines_holding_only_a_page_number(self):
        lines = ["Text.", "12", "pagina 7", "- 41 -", "iv", "Text 2."]

        kept, removed = strip_page_number_lines(lines)

        self.assertEqual(kept, ["Text.", "Text 2."])
        self.assertEqual(len(removed), 4)

    def test_removes_the_english_page_label_extractors_leave_behind(self):
        lines = ["Text.", "Page 104", "Page 104 of 350", "Page: 12", "PAGE 7", "Text 2."]

        kept, removed = strip_page_number_lines(lines)

        self.assertEqual(kept, ["Text.", "Text 2."])
        self.assertEqual(len(removed), 4)

    def test_removes_roman_page_numbers_but_not_words_spelled_with_them(self):
        lines = ["Text.", "Page iv", "page viii.", "xii", "civil", "Mix", "Text 2."]

        kept, removed = strip_page_number_lines(lines)

        self.assertEqual(kept, ["Text.", "civil", "Mix", "Text 2."])
        self.assertEqual(len(removed), 3)

    def test_keeps_a_sentence_that_merely_mentions_a_page(self):
        lines = ["Page 104 describes the dosage of echinacea.", "See page 12 for details."]

        kept, removed = strip_page_number_lines(lines)

        self.assertEqual(kept, lines)
        self.assertEqual(removed, [])


class ColophonTests(unittest.TestCase):
    def test_drops_credit_lines_in_the_front_matter(self):
        lines = ["Editura Litera", "Text medical.", "Traducere din limba engleză: Aurelia Ulici"]

        kept, removed = strip_colophon_lines(lines)

        self.assertEqual(kept, ["Text medical."])
        self.assertEqual(len(removed), 2)

    def test_keeps_a_publisher_mention_in_the_body_of_the_document(self):
        lines = ["Text."] * 300 + ["Rețeta apare la editura din București, ediția a doua."]

        kept, removed = strip_colophon_lines(lines)

        self.assertIn("Rețeta apare la editura din București, ediția a doua.", kept)
        self.assertEqual(removed, [])

    def test_keeps_a_content_line_that_merely_contains_a_credit_word(self):
        # Reported from the corpus: the word "distribuiti" (the carbohydrates are
        # distributed over the day) must not read as a distribution credit.
        lines = [
            "-mentinerea unei diete sanatoase in care carbohidratii sa fie distribuiti pe parcursul zilei\\",
            "1\\. Banu C. (coordonator), Aditivi și ingrediente, Editura Tehnică, 2002.",
            'articol publicat la: 25 Aprilie 2002 in Evenimentul Zilei\\',
        ]

        kept, removed = strip_colophon_lines(lines)

        self.assertEqual(kept, lines)
        self.assertEqual(removed, [])

    def test_drops_an_unambiguous_credit_line_anywhere(self):
        lines = ["Text."] * 300 + ["Toate drepturile rezervate."]

        kept, removed = strip_colophon_lines(lines)

        self.assertEqual(kept, ["Text."] * 300)
        self.assertEqual([item.rule for item in removed], ["colophon"])


class DiacriticsTests(unittest.TestCase):
    def test_folds_romanian_diacritics_and_legacy_cedillas(self):
        self.assertEqual(
            fold_diacritics("Coadă, șoricel, ţuică, mână, România, Ştefan"),
            "Coada, soricel, tuica, mana, Romania, Stefan",
        )

    def test_does_not_fold_diacritics_by_default(self):
        text = "Coadă și mână, țuică.\n"

        cleaned, _ = compact_document(text)

        self.assertEqual(cleaned, text)

    def test_folds_diacritics_when_asked(self):
        cleaned, _ = compact_document("Coadă și mână, țuică.\n", fold_diacritics_to_ascii=True)

        self.assertEqual(cleaned, "Coada si mana, tuica.\n")

    def test_folding_runs_before_repeated_lines_are_counted(self):
        # The two spellings become identical only after folding: three copies of
        # each reach the five-occurrence threshold only if folding runs first.
        text = "\n".join(
            ["Coada si măna ajută ficatul"] * 3 + ["Coada și mana ajuta ficatul"] * 3 + ["Text."]
        )

        cleaned, removed = compact_document(text, stem="Coada si mana ajuta ficatul", fold_diacritics_to_ascii=True)

        self.assertEqual(cleaned.count("Coada"), 1)
        self.assertEqual(len([item for item in removed if item.rule == "running_header"]), 5)


class ContactDetailTests(unittest.TestCase):
    def test_removes_an_email_address(self):
        text, removed = compact_document("Scrieți la adresa cabinet@exemplu.ro pentru programări.\n")

        self.assertEqual(text, "Scrieți la adresa pentru programări.\n")
        self.assertEqual([item.text for item in removed if item.rule == "email"], ["cabinet@exemplu.ro"])

    def test_removes_a_labelled_phone_number_and_its_label(self):
        text, removed = compact_document("Programări: tel. 021/637.30.22 sau 0745 123 456.\n")

        self.assertEqual(text, "Programări: sau.\n")
        self.assertEqual(
            sorted(item.rule for item in removed if item.rule.startswith("phone")),
            ["phone_label", "phone_number", "phone_number"],
        )

    def test_removes_a_line_that_held_nothing_but_contact_data(self):
        text, removed = compact_document("Text medical.\ntel. 021 319 6390; 031 425 1619; 0752 548 372\n")

        self.assertEqual(text, "Text medical.\n")
        self.assertTrue(all(item.rule.startswith("phone") or item.rule == "empty_contact_line" for item in removed))

    def test_removes_an_unlabelled_national_and_toll_free_number(self):
        text, _ = compact_document("Comenzi la 0722371863 ori 1-800-793-9396 oricând.\n")

        self.assertNotIn("0722371863", text)
        self.assertNotIn("1-800-793-9396", text)

    def test_removes_the_ocr_stand_in_for_a_leading_zero(self):
        text, _ = compact_document("Cabinet medical Tel o21 242 14 46, București.\n")

        self.assertNotIn("242 14 46", text)
        self.assertIn("Cabinet medical", text)

    def test_never_removes_a_dose_quantity_date_or_isbn(self):
        untouched = [
            "Se administrează 500 mg de trei ori pe zi.",
            "Doza este 500-1 000 mg zilnic, timp de 10 zile.",
            "Între 150.000-300.000 de lei, conform statisticilor.",
            "Perioada Neolitică (10.000-4.000 AD) a lăsat urme.",
            "Volumul are ISBN 978-606-686-622-4, fără telefon de contact.",
        ]

        for line in untouched:
            with self.subTest(line=line):
                text, _ = compact_document(line + "\n")
                self.assertEqual(text, line + "\n")

        # On a contact line the phone goes and the ISBN stays.
        text, removed = compact_document("Volumul are ISBN 978-606-686-622-4; comenzi la tel. 021 319 6390.\n")
        self.assertIn("978-606-686-622-4", text)
        self.assertNotIn("319 6390", text)
        self.assertEqual([item.text for item in removed if item.rule == "phone_number"], ["021 319 6390"])

    def test_keeps_a_contact_word_that_is_not_glued_to_the_number(self):
        # "suna" is an ordinary verb here, and "Contact" opens the sentence: only
        # the label introducing the removed number may disappear.
        text, _ = compact_document("Scrie la adresa sau suna la tel. 021 319 6390.\n")
        self.assertIn("Scrie la adresa sau suna la", text)
        self.assertNotIn("319 6390", text)

        text, _ = compact_document("Contact Diane Krieger Spivak at 477-6019 or dspivak\\@post-trib.com\n")
        self.assertIn("Contact Diane Krieger Spivak at", text)
        self.assertNotIn("477-6019", text)
        self.assertNotIn("post-trib.com", text)

    def test_keeps_a_word_that_merely_contains_tel(self):
        line = "Eritrocitele mature sunt anucleate, iar Suplimentele se iau la 0745 123 456.\n"

        text, _ = compact_document(line)

        self.assertIn("Eritrocitele", text)
        self.assertIn("Suplimentele", text)


class DigitInvariantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "documents"
        self.source.mkdir()

    def source_file(self, name: str, text: str) -> Path:
        path = self.source / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_accounts_for_numbers_removed_with_a_whitelisted_span(self):
        removals = [Removed("furniture:toc", "Capitolul 1 ....... 5")]

        self.assertEqual(check_digit_invariant("Capitolul 1 5", "Capitolul 1", removals), [])

    def test_reports_a_number_that_no_span_accounts_for(self):
        self.assertEqual(check_digit_invariant("Doză 500 mg", "Doză mg", []), ["500"])

    def test_reports_only_the_uncovered_occurrence(self):
        removals = [Removed("running_header", "Capitolul 2")]

        self.assertEqual(check_digit_invariant("Capitolul 2. Doza 2 mg", "Capitolul. Doza mg", removals), ["2"])

    def test_a_file_that_would_lose_a_number_is_not_written(self):
        path = self.source_file("a.md", "Doza este 500 mg pe zi.\n")

        with mock.patch.object(
            clean_documents, "compact_document", return_value=("Doza este mg pe zi.\n", [])
        ):
            with redirect_stdout(io.StringIO()):
                with self.assertRaises(DigitInvariantError):
                    clean_documents.clean_documents(self.source, dry_run=False)

        self.assertEqual(path.read_text(encoding="utf-8"), "Doza este 500 mg pe zi.\n")


class CompactionPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "documents"
        self.source.mkdir()

    def clean(self):
        with redirect_stdout(io.StringIO()):
            return clean_documents.clean_documents(self.source, dry_run=False)

    def write(self, name: str, text: str) -> Path:
        path = self.source / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_second_run_changes_nothing(self):
        path = self.write(
            "a.md",
            "Coada și măna ajută ficatul.\n"
            "Vezi și Altă afecțiune, Partea a doua.\n"
            "Programări: tel. 021 319 6390.\n"
            "Ultimul rând.\n",
        )

        self.assertEqual(self.clean(), 1)
        first = path.read_text(encoding="utf-8")
        original_mtime = path.stat().st_mtime_ns

        self.assertEqual(self.clean(), 0)
        self.assertEqual(path.read_text(encoding="utf-8"), first)
        self.assertEqual(path.stat().st_mtime_ns, original_mtime)

    def test_keeps_every_heading(self):
        headings = ["# Carte", "## Capitolul 1", "### Subcapitol", "## Capitolul 2"]
        text = "\n\n".join([headings[0], headings[1], headings[2], "Text unu.", headings[3], "Text doi."]) + "\n"
        path = self.write("a.md", text)

        self.clean()

        cleaned = path.read_text(encoding="utf-8")
        for heading in headings:
            self.assertIn(heading, cleaned)

    def test_prints_the_compaction_summary_without_any_flag(self):
        self.write("a.md", "# Carte\n\nCoada și măna ajută ficatul.\nVezi și Altă afecțiune.\n")

        output = io.StringIO()
        with redirect_stdout(output):
            clean_documents.clean_documents(self.source, dry_run=True)

        text = output.getvalue()
        self.assertIn("Would rewrite 1/1 files", text)
        self.assertIn("Characters ", text)
        self.assertIn("that would change", text)
        self.assertIn("Removed by rule:", text)
        self.assertIn("digit-invariant violations: 0", text)

    def test_dry_run_of_a_furniture_section_reports_and_keeps_the_file(self):
        text = (
            "# Carte\n\n## Cuprins\n\n"
            "Capitolul 1 ............ 5\n"
            "Capitolul 2 ............ 12\n"
            "Capitolul 3 ............ 27\n"
            "Capitolul 4 ............ 41\n\n"
            "## Capitolul 1\n\nDoza este 500 mg pe zi; text medical.\n"
        )
        path = self.write("a.md", text)

        with redirect_stdout(io.StringIO()):
            changed = clean_documents.clean_documents(self.source, dry_run=True)

        self.assertEqual(changed, 1)
        self.assertEqual(path.read_text(encoding="utf-8"), text)

        self.clean()

        cleaned = path.read_text(encoding="utf-8")
        self.assertNotIn("Cuprins", cleaned)
        self.assertIn("500 mg", cleaned)


if __name__ == "__main__":
    unittest.main()
