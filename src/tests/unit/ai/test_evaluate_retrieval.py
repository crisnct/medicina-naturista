"""Tests for the pure metric/label logic of scripts/evaluate_retrieval.py (no database)."""
from __future__ import annotations

import math
import unittest

from scripts import evaluate_retrieval as ev


class RelevanceRuleTests(unittest.TestCase):
    INDEX = {
        1: (ev.plain("Afectiuni/Guta/Recomandari.md"), ev.plain("Alimente")),
        2: (ev.plain("Books/Balch.md"), ev.plain("GUTĂ")),
        3: (ev.plain("Books/Balch.md"), ev.plain("Ulcer")),
    }

    def test_path_or_heading_rule_matches_without_diacritics_or_case(self):
        case = {"query": "guta", "paths": ["guta"], "headings": ["guta"]}

        self.assertEqual(ev.relevant_ids(case, self.INDEX), {1, 2})

    def test_case_without_rules_has_no_relevant_chunks(self):
        self.assertEqual(ev.relevant_ids({"query": "x"}, self.INDEX), set())


class MetricTests(unittest.TestCase):
    def test_ndcg_is_one_for_ideal_ordering_and_lower_otherwise(self):
        relevant = {1, 2}

        self.assertAlmostEqual(ev.ndcg_at([1, 2, 9], relevant, 10), 1.0)
        worse = ev.ndcg_at([9, 1, 2], relevant, 10)
        self.assertAlmostEqual(worse, (1 / math.log2(3) + 1 / math.log2(4)) / (1 + 1 / math.log2(3)))

    def test_ndcg_is_zero_without_relevant_chunks(self):
        self.assertEqual(ev.ndcg_at([1, 2], set(), 10), 0.0)

    def test_summary_reports_means_and_latency_percentiles(self):
        rows = [
            {"precision_at_10": 1.0, "reciprocal_rank": 1.0, "ndcg_at_10": 1.0, "recall_at_50": 0.5, "latency_ms": 100.0},
            {"precision_at_10": 0.0, "reciprocal_rank": 0.5, "ndcg_at_10": 0.0, "recall_at_50": None, "latency_ms": 300.0},
        ]

        summary = ev.summarize(rows)

        self.assertEqual(summary["queries"], 2)
        self.assertAlmostEqual(summary["precision_at_10"], 0.5)
        self.assertAlmostEqual(summary["recall_at_50"], 0.5)
        self.assertAlmostEqual(summary["latency_p50_ms"], 200.0)
        self.assertAlmostEqual(summary["latency_p95_ms"], 300.0)

    def test_priority_violations_are_reported_only_when_the_conditions_signal_is_on(self):
        rows = [{
            "precision_at_10": 1.0, "reciprocal_rank": 1.0, "ndcg_at_10": 1.0,
            "recall_at_50": 1.0, "latency_ms": 100.0, "priority_order_violations": 2,
        }]

        with_conditions = ev.summarize(rows, ev.SearchSignals.from_code("AC"))
        without_conditions = ev.summarize(rows, ev.SearchSignals.from_code("BC"))

        self.assertEqual(with_conditions["priority_order_violations"], 2)
        self.assertEqual(with_conditions["signals"], "AC")
        self.assertNotIn("priority_order_violations", without_conditions)
        self.assertEqual(without_conditions["signals"], "BC")

    def test_summary_defaults_to_every_signal(self):
        rows = [{"precision_at_10": 0.0, "reciprocal_rank": 0.0, "ndcg_at_10": 0.0, "recall_at_50": None, "latency_ms": 1.0}]

        summary = ev.summarize(rows)

        self.assertEqual(summary["signals"], "ABC")
        self.assertEqual(summary["priority_order_violations"], 0)

    def test_shipped_cases_are_well_formed(self):
        cases = ev.load_cases(ev.CASES_PATH)

        self.assertGreaterEqual(len(cases), 30)
        for case in cases:
            self.assertTrue(case["query"].strip())
            self.assertTrue(case.get("paths") or case.get("headings"), case["query"])


if __name__ == "__main__":
    unittest.main()
