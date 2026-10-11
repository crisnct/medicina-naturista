"""Database and SQL catalog preparation must finish before fragmentation."""

import tempfile
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from scripts import build_hybrid_index as builder


class IndexPreparationTests(TestCase):
    def test_preparation_precedes_writer_and_fragmentation(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(
                    builder, "ensure_database", side_effect=lambda *_: calls.append("bootstrap")
                ),
                patch.object(
                    builder, "migrate", side_effect=lambda *_args, **_kwargs: calls.append("sql")
                ),
                patch.object(
                    builder,
                    "index_writer",
                    side_effect=lambda **_kwargs: (
                        calls.append("lock")
                        or nullcontext(SimpleNamespace(execute=lambda *_args: None))
                    ),
                ),
                patch.object(
                    builder,
                    "GPUUsageMonitor",
                    return_value=nullcontext(SimpleNamespace(percent=lambda: "N/A")),
                ),
                patch.object(
                    builder,
                    "_build",
                    side_effect=lambda *_args, **_kwargs: calls.append("fragmentation"),
                ),
            ):
                builder.build(Path(directory), builder.DEFAULT_MODEL)
        self.assertEqual(calls, ["bootstrap", "sql", "lock", "fragmentation"])

    def test_failed_seed_never_starts_fragmentation(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(builder, "ensure_database"),
                patch.object(builder, "migrate", side_effect=RuntimeError("SQL failed")),
                patch.object(builder, "_build") as fragment,
                self.assertRaisesRegex(RuntimeError, "SQL failed"),
            ):
                builder.build(Path(directory), builder.DEFAULT_MODEL)
            fragment.assert_not_called()

    def test_invalid_model_is_rejected_before_touching_the_database(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(builder, "ensure_database") as bootstrap:
                with self.assertRaisesRegex(ValueError, "Unknown embedding model"):
                    builder.build(Path(directory), "invalid/model")
                bootstrap.assert_not_called()
