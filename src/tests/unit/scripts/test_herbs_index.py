"""Association semantics, dense bitmaps and Windows spawn readiness."""

from dataclasses import replace
from types import MappingProxyType
from unittest import TestCase, mock

from scripts import build_hybrid_index as builder


def context():
    return builder.HerbsIndexContext(
        (7, 991),
        (17, 803),
        MappingProxyType({"Gastrita": (0,), "comun": (0, 1)}),
        (("musetel", (0, 1)),),
        "cf",
        "hf",
        "old",
        "new",
        True,
        "forced",
        0,
        100,
        True,
        True,
    )


class HerbsIndexTests(TestCase):
    def test_normalization_boundaries_aliases_and_overlaps(self):
        names = (
            ("musetel", (0, 1)),
            ("in", (2,)),
            ("sunatoare", (3,)),
            ("iarba mare", (4,)),
            ("mare de camp", (5,)),
            ("mare", (6,)),
            ("matricaria chamomilla", (0,)),
        )
        matcher = builder._make_herbs_matcher(names)
        text = "MUȘEȚEL, musetel. inflamație; in; sunătoarea; iarba-mare de câmp!"
        self.assertEqual(
            builder._match_herbs(matcher, builder._herb_text(text)), {0, 1, 2, 4, 5, 6}
        )
        self.assertEqual(builder._match_herbs(matcher, builder._herb_text("sunătoare")), {3})
        self.assertEqual(
            builder._match_herbs(matcher, builder._herb_text("Matricaria chamomilla")), {0}
        )

    def test_ascii_and_unicode_paths_agree_and_keep_short_names(self):
        for value in ("IN, IN!_in", "Iarba-mare\n de camp", "123", "", "MUSETEL"):
            self.assertEqual(
                builder._herb_text(value),
                " ".join(builder._HERBS_TOKENS.findall(builder.plain(value))),
            )
        self.assertEqual(builder._herb_text("Mușețel şi PĂDUCEL"), "musetel si paducel")

    def test_exact_conditions_shared_synonyms_and_sparse_ids(self):
        ctx = context()
        self.assertEqual(builder._herbs_condition_mask(ctx, ["Gastrita"], ["comun", "comun"]), 3)
        self.assertEqual(
            builder._herbs_condition_mask(ctx, ["gastrita", "Gastrita cronica"], []), 0
        )
        seen = [0, 0]
        self.assertEqual(
            set(builder._new_herbs_pairs(ctx, seen, [0, 1], 3)),
            {(17, 7), (17, 991), (803, 7), (803, 991)},
        )
        self.assertEqual(list(builder._new_herbs_pairs(ctx, seen, [1, 0], 3)), [])
        self.assertEqual(
            set(builder._new_herbs_pairs(ctx, None, [0, 1], 3)),
            {(17, 7), (17, 991), (803, 7), (803, 991)},
        )

    def test_fingerprint_order_independent_but_ids_and_version_matter(self):
        rows = [[991, "Gastrita", ["gastric"]], [7, "Febra", []]]
        self.assertEqual(builder._herbs_fingerprint(rows), builder._herbs_fingerprint(rows[::-1]))
        self.assertNotEqual(
            builder._herbs_fingerprint(rows), builder._herbs_fingerprint([[1, "Febra", []]])
        )
        original = builder._herbs_fingerprint(rows)
        with mock.patch.object(builder, "HERBS_INDEX_VERSION", 2):
            self.assertNotEqual(builder._herbs_fingerprint(rows), original)

    def test_bitmap_budget_conservative_and_monotonic(self):
        self.assertLess(builder._herbs_bitmap_bytes(1188, 6284), builder.HERBS_BITMAP_BUDGET_BYTES)
        self.assertGreater(
            builder._herbs_bitmap_bytes(100_000, 100_000), builder.HERBS_BITMAP_BUDGET_BYTES
        )

    def test_fast_path_never_creates_executor(self):
        with mock.patch.object(builder, "ProcessPoolExecutor") as pool:
            with builder._prepared_herbs_workers(
                replace(context(), workers_required=False)
            ) as executor:
                self.assertIsNone(executor)
            pool.assert_not_called()

    def test_spawn_matchers_ready_and_compact_results(self):
        with mock.patch.object(builder, "HERBS_INDEX_WORKERS", 2):
            with builder._prepared_herbs_workers(context()) as pool:
                offsets, positions, _, _ = pool.submit(
                    builder._scan_herbs_batch, ["Mușețel mușețel", "inflamatie"]
                ).result()
        self.assertEqual(list(offsets), [0, 2, 2])
        self.assertEqual(list(positions), [0, 1])

    def test_missing_matcher_reports_interpreter_before_starting_pool(self):
        with mock.patch.dict("sys.modules", {"ahocorasick": None}):
            with mock.patch.object(builder, "ProcessPoolExecutor") as pool:
                with self.assertRaisesRegex(RuntimeError, "HERBS_MATCHER_UNAVAILABLE") as error:
                    with builder._prepared_herbs_workers(context()):
                        self.fail("missing matcher must prevent worker startup")
                self.assertIn(builder.sys.executable, str(error.exception))
                self.assertIn("-m pip install", str(error.exception))
                pool.assert_not_called()

    def test_progress_counts_completed_and_reports_empty(self):
        output = mock.Mock()
        reporter = builder.HerbsProgress(10, progress=output, clock=iter([0, 0, 10]).__next__)
        stats = dict(chunks_completed=0, chunks_read=5, characters=0, candidate_pairs=0)
        reporter.report("scan", stats, active=1, force=True)
        self.assertIn("0.00%", output.call_args.args[0])
        self.assertIn("calculare", output.call_args.args[0])
        stats.update(chunks_completed=5, characters=500)
        reporter.report("scan", stats, active=1)
        self.assertIn("50.00%", output.call_args.args[0])
        self.assertIn("00:00:10", output.call_args.args[0])
        reporter = builder.HerbsProgress(0, progress=output)
        reporter.report(
            "scan",
            dict(chunks_completed=0, chunks_read=0, characters=0, candidate_pairs=0),
            force=True,
        )
        self.assertIn("100.00%", output.call_args.args[0])

    def test_cli_force_flag(self):
        with mock.patch("sys.argv", ["builder", "--rebuild-herbs"]):
            self.assertTrue(builder.parse_args().rebuild_herbs)
        with mock.patch("sys.argv", ["builder"]):
            self.assertFalse(builder.parse_args().rebuild_herbs)
