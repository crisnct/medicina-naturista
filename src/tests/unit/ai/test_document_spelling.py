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
        self.english_dictionary = self.root / "english-hunspell"
        self.english_dictionary.mkdir()
        (self.english_dictionary / "en_GB.dic").write_text(
            "6\ntreatment\nmedication\nfrom\nwith\nthe\nand\n", encoding="utf-8"
        )
        (self.english_dictionary / "en_GB.aff").write_text("SET UTF-8\n", encoding="utf-8")
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
            mock.patch.object(clean_documents, "ENGLISH_HUNSPELL_DIR", self.english_dictionary),
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

    def test_english_directory_uses_english_dictionary_and_unscoped_files_keep_detection(self):
        english = self.write(
            "english.md",
            "The mediicament is for the patient and the treatment. [here](https://x.ro)\n",
        )
        mixed = self.write("mixed.md", "the si mediicament\n")
        misplaced = self.write(
            "ro/nested/english.md",
            "The treatment is for the patient and it is taken with medication from the "
            "bottle on the table. The mediicament and medica tion are here.\n",
        )
        uncertain = self.write("ro/short.md", "the si mediicament\n")
        self.write("en/frequencies.md", "the treatment and medication\n" * 110)
        target = self.write(
            "en/nested/target.md",
            "### Pagina 9\n"
            "treatm ent with mediication fromtreatment and cind, 500 mg.\n"
            "si cu pentru mediicament\n",
        )
        before = (misplaced.read_bytes(), misplaced.stat().st_mtime_ns)
        self.clean(dry_run=True)
        self.assertEqual((misplaced.read_bytes(), misplaced.stat().st_mtime_ns), before)
        self.clean()
        self.assertTrue(misplaced.exists())
        self.assertIn("mediicament and medication", misplaced.read_text(encoding="utf-8"))
        self.assertIn("medicament", uncertain.read_text(encoding="utf-8"))
        self.assertEqual(
            clean_documents._spelling_language(
                misplaced, self.source / "ro" / "nested", misplaced.read_text(encoding="utf-8")
            ),
            "en",
        )
        self.assertIn("The mediicament is", english.read_text(encoding="utf-8"))
        self.assertNotIn("https://", english.read_text(encoding="utf-8"))
        self.assertEqual(mixed.read_text(encoding="utf-8"), "the si mediicament\n")
        self.assertEqual(
            target.read_text(encoding="utf-8"),
            "treatment with medication from treatment and cind, 500 mg.\n"
            "si cu pentru mediicament\n",
        )
        self.assertEqual({row["rule"] for row in self.rows()}, {"join", "split", "typo"})
        self.assertEqual(
            {row["file"] for row in self.rows()},
            {"en/nested/target.md", "ro/nested/english.md", "ro/short.md"},
        )
        self.assertEqual(
            clean_documents._spelling_language(
                misplaced,
                self.source,
                "Acesta este un document cu tratament pentru care se ia medicament. " * 5
                + "The patient is here and this is the treatment from the bottle.",
            ),
            "ro",
        )
        shared = {"the", "and", "of", "with", "for", "botanical"}
        romanian = shared | {"planta", "medicament", "tratament", "frunza", "floare"}
        british = shared | {"patient", "bottle", "remedy", "treatment", "flower"}
        dictionaries = {
            language: clean_documents._SpellingDictionary(words, words, {})
            for language, words in (("ro", romanian), ("en", british))
        }
        agreement = "the and of with for patient bottle remedy treatment flower " * 3
        conflict = "the and of with for planta medicament tratament frunza floare " * 3
        self.assertEqual(clean_documents.detect_language(agreement, dictionaries), "en")
        self.assertEqual(clean_documents.detect_language(conflict, dictionaries), "mix")
        self.assertEqual(
            clean_documents._spelling_language(misplaced, self.source, conflict, dictionaries),
            "ro",
        )
        self.assertEqual(
            clean_documents.detect_language("patient bottle remedy treatment flower", dictionaries),
            "en",
        )
        self.assertEqual(clean_documents.detect_language("botanical " * 20, dictionaries), "mix")
        unchanged = (target.read_bytes(), target.stat().st_mtime_ns)
        self.assertEqual(self.clean(), 0)
        self.assertEqual(unchanged, (target.read_bytes(), target.stat().st_mtime_ns))

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
        (self.dictionary / "ro_RO.dic").write_text("2\nplanta/SABN\nCristian\n", encoding="utf-8")
        (self.dictionary / "ro_RO.aff").write_text(
            "SET UTF-8\nSFX S Y 1\nSFX S a e a\n"
            "PFX A Y 1\nPFX A 0 re .\nPFX B Y 1\nPFX B p un p\n"
            "PFX N N 1\nPFX N 0 non .\n",
            encoding="utf-8",
        )
        dictionary, common = clean_documents.build_dictionary(self.dictionary)
        self.assertTrue({"planta", "plante", "cristian"}.issubset(dictionary))
        self.assertNotIn("cristian", common)
        self.assertTrue({"replanta", "replante", "unlanta", "unlante", "nonplanta"} <= dictionary)
        self.assertFalse({"unreplanta", "reunlanta", "nonplante"} & dictionary)

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
