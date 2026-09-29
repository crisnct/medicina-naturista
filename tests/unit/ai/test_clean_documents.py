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

    def test_preserves_original_encoding_on_rewrite(self):
        # cp1250 supports the legacy cedilla diacritics (ş/ţ) but not the
        # modern comma-below forms (ș/ț) used elsewhere in the corpus. The
        # trailing "!" keeps the byte count odd, so the utf-16 fallback
        # (tried before cp1250) fails to decode instead of spuriously
        # succeeding on an unrelated even-length byte pairing — the same
        # encoding-detection order build_hybrid_index.read_markdown() uses.
        path = self.source / "a.md"
        path.write_bytes("Coadă-şoricel [aici](https://x.ro) ajută mult!\n".encode("cp1250"))

        with redirect_stdout(io.StringIO()):
            clean_documents.clean_documents(self.source, dry_run=False)

        raw = path.read_bytes()
        self.assertEqual(raw.decode("cp1250"), "Coadă-şoricel aici ajută mult!\n")

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
