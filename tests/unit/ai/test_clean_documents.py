from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts import clean_documents


class CleanDocumentsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "documents"
        self.source.mkdir()

    def test_rewrites_a_file_containing_a_markdown_link(self):
        path = self.source / "a.md"
        path.write_text("Planta [sunătoare](https://example.com) ajută la ficat.\n", encoding="utf-8")

        with redirect_stdout(io.StringIO()):
            changed = clean_documents.clean_documents(self.source, dry_run=False)

        self.assertEqual(changed, 1)
        self.assertEqual(path.read_text(encoding="utf-8"), "Planta sunătoare ajută la ficat.\n")

    def test_leaves_an_already_clean_file_untouched(self):
        path = self.source / "a.md"
        original = "Text simplu, fără linkuri sau trimiteri.\n"
        path.write_text(original, encoding="utf-8")
        original_mtime = path.stat().st_mtime_ns

        with redirect_stdout(io.StringIO()):
            changed = clean_documents.clean_documents(self.source, dry_run=False)

        self.assertEqual(changed, 0)
        self.assertEqual(path.stat().st_mtime_ns, original_mtime)

    def test_dry_run_reports_but_does_not_write(self):
        path = self.source / "a.md"
        original = "Vezi și Altă afecțiune, Partea a doua.\nText rămas.\n"
        path.write_text(original, encoding="utf-8")

        output = io.StringIO()
        with redirect_stdout(output):
            changed = clean_documents.clean_documents(self.source, dry_run=True)

        self.assertEqual(changed, 1)
        self.assertEqual(path.read_text(encoding="utf-8"), original)
        self.assertIn("Would clean: a.md", output.getvalue())
        self.assertIn("Would rewrite 1/1 files", output.getvalue())

    def test_preserves_original_encoding_when_still_representable(self):
        path = self.source / "a.md"
        path.write_bytes("Coad\u0103 [aici](https://x.ro) ajut\u0103 mult!\n".encode("cp1250"))

        with redirect_stdout(io.StringIO()):
            clean_documents.clean_documents(self.source, dry_run=False)

        self.assertEqual(path.read_bytes().decode("cp1250"), "Coad\u0103 aici ajut\u0103 mult!\n")

    def test_falls_back_to_utf8_when_comma_below_is_not_encodable(self):
        path = self.source / "a.md"
        # Odd byte count, so the utf-16 fallback cannot spuriously decode it.
        path.write_bytes("Coad\u0103-\u015foricel ajut\u0103 mult!!\n".encode("cp1250"))

        with redirect_stdout(io.StringIO()):
            clean_documents.clean_documents(self.source, dry_run=False)

        self.assertEqual(path.read_bytes().decode("utf-8"), "Coad\u0103-\u0219oricel ajut\u0103 mult!!\n")

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
        path = self.source / "a.md"
        text = (
            "Prima linie [etichetă](http://x.ro) rămâne.\n"
            "Vezi și Altă afecțiune, Partea a doua.\n"
            "Ultima linie.\n"
        )
        path.write_text(text, encoding="utf-8")

        with redirect_stdout(io.StringIO()):
            clean_documents.clean_documents(self.source, dry_run=False)

        cleaned = path.read_text(encoding="utf-8")
        self.assertEqual(cleaned.count("\n"), text.count("\n"))


if __name__ == "__main__":
    unittest.main()
