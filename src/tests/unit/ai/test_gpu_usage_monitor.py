from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import numpy as np

from backend.ai.embedding_model import EmbeddingProfile
from scripts.build_hybrid_index import Chunk, GPUUsageMonitor, embed_chunks


class GPUUsageMonitorTests(unittest.TestCase):
    def test_reads_gpu_util_instead_of_fan_or_vram(self):
        monitor = GPUUsageMonitor()
        monitor._consume("| 0 NVIDIA RTX 3500 Ada WDDM | 00000000:01:00.0 Off | 0 |")
        monitor._consume("| 37% 70C P3 54W / 55W | 3111MiB / 11514MiB | 100% Default |")
        self.assertEqual(monitor.percent(), "100%")
        monitor._consume("| N/A 70C P3 54W / 55W | 3111MiB / 11514MiB | 0% Default |")
        self.assertEqual(monitor.percent(), "0%")

    def test_other_gpu_and_process_table_do_not_overwrite_gpu_zero(self):
        monitor = GPUUsageMonitor()
        monitor._consume("| 0 NVIDIA RTX WDDM | 00000000:01:00.0 Off | 0 |")
        monitor._consume("| N/A 70C P3 54W / 55W | 3111MiB / 11514MiB | 62% Default |")
        monitor._consume("| 1 NVIDIA RTX WDDM | 00000000:02:00.0 Off | 0 |")
        monitor._consume("| N/A 70C P3 54W / 55W | 3111MiB / 11514MiB | 99% Default |")
        monitor._consume("| 0 N/A N/A 5884 C+G python.exe N/A |")
        self.assertEqual(monitor.percent(), "62%")

    def test_stale_reading_is_unavailable(self):
        monitor = GPUUsageMonitor()
        monitor._consume("| 0 NVIDIA RTX WDDM | 00000000:01:00.0 Off | 0 |")
        monitor._consume("| N/A 70C P3 54W / 55W | 3111MiB / 11514MiB | 62% Default |")
        with patch(
            "scripts.build_hybrid_index.time.monotonic",
            return_value=monitor._updated + 4,
        ):
            self.assertEqual(monitor.percent(), "N/A")

    def test_missing_command_does_not_abort(self):
        with patch(
            "scripts.build_hybrid_index.subprocess.Popen", side_effect=FileNotFoundError
        ):
            with GPUUsageMonitor() as monitor:
                monitor._thread.join(timeout=2)
                self.assertEqual(monitor.percent(), "N/A")
            self.assertFalse(monitor._thread.is_alive())

    def test_thread_starts_exact_command_and_stops_process_on_error(self):
        with patch("scripts.build_hybrid_index.subprocess.Popen") as popen:
            process = popen.return_value
            process.stdout = io.StringIO("")
            process.poll.return_value = None
            with self.assertRaisesRegex(RuntimeError, "embedding failed"):
                with GPUUsageMonitor() as monitor:
                    monitor._thread.join(timeout=2)
                    raise RuntimeError("embedding failed")
            self.assertEqual(popen.call_args.args[0], ["nvidia-smi", "--loop=1"])
            process.terminate.assert_called_once()
            process.wait.assert_called_once_with(timeout=2)
            self.assertFalse(monitor._thread.is_alive())

    def test_progress_contains_sampled_gpu_usage(self):
        profile = EmbeddingProfile("test", 2, "{text}", "{text}", 1400, 240)
        chunk = Chunk("doc.md", "doc.md", "sha", 1, 1, "title", "text", "sha", 4)
        model = unittest.mock.Mock()
        model.embed.return_value = iter([np.array([1.0, 0.0]), np.array([0.0, 1.0])])
        clock = iter([0.0, 11.0, 12.0, 13.0])
        output = io.StringIO()
        with redirect_stdout(output):
            embed_chunks(
                model,
                [chunk, chunk],
                8,
                profile,
                clock=lambda: next(clock),
                gpu_usage=lambda: "100%",
            )
        self.assertIn("ETA 00:00:11 | GPU usage: 100%", output.getvalue())
