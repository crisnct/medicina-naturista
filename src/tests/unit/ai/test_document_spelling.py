from __future__ import annotations

import csv
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from scripts import clean_documents


class DocumentSpellingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "documents"
        self.source.mkdir()
        self.dictionary = self.root / "hunspell"
        self.dictionary.mkdir()
        words = [
            "pentru",
            "acest",
            "tratament",
            "medicament",
            "sunătoare",
            "cand",
            "si",
            "cu",
            "din",
            "la",
            "e",
            "tumorală",
            "pieptul",
            "pieptule",
            "primul",
            "primule",
            "imunitatii",
        ]
        (self.dictionary / "ro_RO.dic").write_text(
            str(len(words)) + "\n" + "\n".join(words) + "\n", encoding="utf-8"
        )
        (self.dictionary / "ro_RO.aff").write_text("SET UTF-8\n", encoding="utf-8")
        self.report = self.root / "corrections.tsv"
        self.write("corpus.md", "pentru acest tratament cu medicament si sunătoare.\n" * 110)

    def write(self, name, text, encoding="utf-8"):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode(encoding))
        return path

    def clean(self, **kwargs):
        with (
            redirect_stdout(io.StringIO()),
            mock.patch.object(clean_documents, "HUNSPELL_DIR", self.dictionary),
        ):
            return clean_documents.clean_documents(
                self.source,
                dry_run=kwargs.pop("dry_run", False),
                spelling_report=self.report,
                **kwargs,
            )

    def rows(self):
        with self.report.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))

    def test_cleans_and_applies_all_four_spelling_rules_with_a_report(self):
        path = self.write(
            "nested/target.md",
            "### Pagina 9\nSe ia pen tru [tratam ent](https://x.ro) si mediicament "
            "dintratament cind este nevoie de 500 mg si 10 picaturi.\n"
            "Tumora la san; pieptul e sensibil, primul e bun.\n",
        )
        self.clean()
        self.assertEqual(
            path.read_text(encoding="utf-8"),
            "Se ia pentru tratament si medicament din tratament cand este nevoie de 500 mg si 10 picaturi.\n"
            "Tumora la san; pieptul e sensibil, primul e bun.\n",
        )
        rows = self.rows()
        self.assertEqual({row["rule"] for row in rows}, {"join", "split", "typo", "orthography"})
        self.assertTrue(
            all(row["file"] == "nested/target.md" and row["line"] == "1" for row in rows)
        )

    def test_dry_run_matches_apply_report_without_changing_bytes_or_timestamps(self):
        path = self.write("target.md", "Se ia pen tru tratament si mediicament de 500 mg.\r\n")
        originals = {
            item: (item.read_bytes(), item.stat().st_mtime_ns) for item in self.source.rglob("*.md")
        }
        predicted = self.clean(dry_run=True)
        preview = self.rows()
        self.assertTrue(preview)
        for item, (raw, mtime) in originals.items():
            self.assertEqual(item.read_bytes(), raw)
            self.assertEqual(item.stat().st_mtime_ns, mtime)
        self.assertEqual(self.clean(), predicted)
        self.assertEqual(self.rows(), preview)
        self.assertIn("medicament", path.read_text(encoding="utf-8"))
        applied = {
            item: (item.read_bytes(), item.stat().st_mtime_ns) for item in self.source.rglob("*.md")
        }
        self.assertEqual(self.clean(dry_run=True), 0)
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.clean(), 0)
        self.assertEqual(
            applied,
            {item: (item.read_bytes(), item.stat().st_mtime_ns) for item in applied},
        )

    def test_keeps_diacritics_and_uses_dictionary_spelling_for_corrections(self):
        path = self.write("target.md", "Se ia sunaatoare cu sunătoare si tratament de 500 mg.\n")
        self.clean(fold_diacritics_to_ascii=False)
        self.assertEqual(
            path.read_text(encoding="utf-8"),
            "Se ia sunătoare cu sunătoare si tratament de 500 mg.\n",
        )
        self.assertEqual(self.rows()[0]["after"], "sunătoare")

    def test_preserves_source_encoding(self):
        path = self.write(
            "target.md", "Se ia sunaatoare cu sunătoare si tratament.\n", encoding="cp1250"
        )
        self.clean(fold_diacritics_to_ascii=False)
        self.assertEqual(
            path.read_bytes().decode("cp1250"), "Se ia sunătoare cu sunătoare si tratament.\n"
        )

    def test_utf16_sources_are_decoded_before_counting_and_correction(self):
        path = self.write(
            "target.md", "Se ia mediicament cu tratament de 500 mg.\n", encoding="utf-16"
        )
        self.clean()
        self.assertEqual(
            path.read_bytes().decode("utf-16"), "Se ia medicament cu tratament de 500 mg.\n"
        )

    def test_english_and_mixed_documents_only_receive_existing_cleanup(self):
        english = self.write(
            "english.md",
            "The mediicament is for the patient and the treatment. [here](https://x.ro)\n",
        )
        mixed = self.write("mixed.md", "the si mediicament\n")
        self.clean()
        self.assertIn("The mediicament is", english.read_text(encoding="utf-8"))
        self.assertNotIn("https://", english.read_text(encoding="utf-8"))
        self.assertEqual(mixed.read_text(encoding="utf-8"), "the si mediicament\n")
        self.assertEqual(self.rows(), [])

    def test_preserves_names_dose_tokens_and_hyphenated_compounds(self):
        text = "Se ia Mediicament cu 500mediicament si mediicament-test si tratament.\n"
        path = self.write("target.md", text)
        self.clean()
        self.assertEqual(path.read_text(encoding="utf-8"), text)
        self.assertEqual(self.rows(), [])

    def test_frequent_unknown_words_are_not_replaced(self):
        text = "Se ia mediicament cu tratament.\n" * 4
        path = self.write("target.md", text)
        self.clean()
        self.assertEqual(path.read_text(encoding="utf-8"), text)

        # A join raises the candidate frequency from 99 to 100; the dependent
        # typo must be resolved in this invocation, not in the next invocation.
        self.write("threshold.md", "si imunitatii\n" * 99)
        cascade = self.write("cascade.md", "si imu nitatii\nsi imnitatii\n")
        self.clean()
        self.assertEqual(cascade.read_text(encoding="utf-8"), "si imunitatii\nsi imunitatii\n")
        self.assertEqual(path.read_text(encoding="utf-8"), text)
        self.assertEqual({row["pass"] for row in self.rows()}, {"1", "2"})
        original = (cascade.read_bytes(), cascade.stat().st_mtime_ns)
        self.assertEqual(self.clean(), 0)
        self.assertEqual(original, (cascade.read_bytes(), cascade.stat().st_mtime_ns))

    def test_missing_dictionary_fails_before_any_source_writes(self):
        path = self.write("target.md", "Se ia [tratament](https://x.ro) cu medicament.\n")
        raw = path.read_bytes()
        (self.dictionary / "ro_RO.aff").unlink()
        with self.assertRaises(FileNotFoundError):
            self.clean()
        self.assertEqual(path.read_bytes(), raw)
        self.assertFalse(self.report.exists())

    def test_report_cannot_overwrite_a_source_or_dictionary(self):
        path = self.write("target.md", "Se ia mediicament cu tratament.\n")
        for report in (path, self.dictionary / "ro_RO.dic", self.source / "new.md"):
            self.report = report
            raw = report.read_bytes() if report.exists() else None
            with self.assertRaises(ValueError):
                self.clean()
            self.assertEqual(report.read_bytes() if report.exists() else None, raw)

    def test_digit_invariant_still_blocks_a_faulty_spelling_rule(self):
        path = self.write("target.md", "Se ia tratament de 500 mg.\n")
        raw = path.read_bytes()

        def faulty_fix(_fixer, line):
            if "500" in line:
                return line.replace("500", ""), [("typo", "500", "")]
            return line, []

        with mock.patch.object(clean_documents.Fixer, "fix_line", faulty_fix):
            with self.assertRaises(clean_documents.DigitInvariantError):
                self.clean()
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(self.rows(), [])

    def test_cleaner_cli_uses_bundled_dictionary_from_another_working_directory(self):
        path = self.write("target.md", "Se ia mediicament cu tratament.\n")
        raw = path.read_bytes()
        result = subprocess.run(
            [
                sys.executable,
                clean_documents.__file__,
                "--source",
                str(self.source),
                "--spelling-report",
                str(self.report),
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            cwd=self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Spelling corrections: 1", result.stdout)
        self.assertEqual(self.rows()[0]["after"], "medicament")
        self.assertEqual(path.read_bytes(), raw)

    def test_hunspell_affixes_and_proper_names(self):
        (self.dictionary / "ro_RO.dic").write_text("2\nplanta/S\nCristian\n", encoding="utf-8")
        (self.dictionary / "ro_RO.aff").write_text(
            "SET UTF-8\nSFX S Y 1\nSFX S a e a\n", encoding="utf-8"
        )
        dictionary, common = clean_documents.build_dictionary(self.dictionary)
        self.assertTrue({"planta", "plante", "cristian"}.issubset(dictionary))
        self.assertNotIn("cristian", common)

    def test_ambiguous_typos_are_left_unchanged(self):
        words = {"medicament", "meducament"}
        fixer = clean_documents.Fixer(
            words,
            words,
            clean_documents.collections.Counter({"medicament": 110, "meducament": 110}),
            clean_documents.collections.Counter(),
        )
        self.assertEqual(fixer.fix_line("medacament"), ("medacament", []))


class SpellingCommandLineTests(unittest.TestCase):
    def test_accepts_report_path_without_a_dictionary_flag(self):
        with mock.patch.object(
            sys, "argv", ["clean_documents.py", "--spelling-report", "report.tsv"]
        ):
            args = clean_documents.parse_args()
        self.assertFalse(hasattr(args, "hunspell_dir"))
        self.assertEqual(args.spelling_report, Path("report.tsv"))

    def test_removed_dictionary_flag_is_rejected(self):
        with mock.patch.object(sys, "argv", ["clean_documents.py", "--hunspell-dir", "dictionary"]):
            with mock.patch.object(sys, "stderr", io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    clean_documents.parse_args()
        self.assertEqual(raised.exception.code, 2)
