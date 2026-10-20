"""Offline source validation and SQL publication safety."""

import hashlib
import sys
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from scripts.convert_herbs_to_sql import main, read_source, seed_sql
from tests.unit.ai.test_herbs import SAMPLE, line


class ConversionTests(TestCase):
    def test_deterministic_lowercase_sql_uses_returned_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.jsonl"
            source.write_text(SAMPLE)
            raw, herbs = read_source(source)
            digest = hashlib.sha256(raw).hexdigest()
            result = seed_sql(herbs, digest)
            self.assertEqual(result, seed_sql(herbs, digest))
            self.assertIn("RETURNING id", result)
            self.assertIn("herbs (category, family, latin, ro, en)", result)
            self.assertIn("'plante medicinale'", result)
            self.assertIn("SELECT plant.id", result)
            self.assertIn("'matricaria chamomilla'", result)
            self.assertNotIn("ON CONFLICT", result)

    def test_sql_literal_escaping(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.jsonl"
            source.write_text(line(en="Gardener's plant", en_alt=[r"plant\name"]))
            raw, herbs = read_source(source)
            result = seed_sql(herbs, hashlib.sha256(raw).hexdigest())
            self.assertIn("gardener''s plant", result)
            self.assertIn(r"plant\\name", result)

    def test_check_writes_nothing_and_publication_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source.jsonl", Path(directory) / "seed.sql"
            source.write_text(SAMPLE)
            args = ["convert", "--source", str(source), "--output", str(output)]
            with patch.object(sys, "argv", [*args, "--check"]):
                main()
            self.assertFalse(output.exists())
            with patch.object(sys, "argv", args):
                main()
                first = output.read_bytes()
                with self.assertRaises(SystemExit):
                    main()
            self.assertEqual(first, output.read_bytes())

    def test_invalid_or_empty_source_never_publishes(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source.jsonl", Path(directory) / "seed.sql"
            for content in ("", "bad json", line(id="bad_id"), SAMPLE + line()):
                source.write_text(content)
                with patch.object(
                    sys, "argv", ["convert", "--source", str(source), "--output", str(output)]
                ):
                    with self.assertRaises(SystemExit):
                        main()
                self.assertFalse(output.exists())
