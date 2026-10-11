"""Hand-calculated quality metrics and incompatible baseline rejection."""

import copy
import math
import unittest
from pathlib import Path

from backend.ai.content_evaluation import (
    ContentCase,
    FragmentKey,
    Judgement,
    compare,
    evaluate,
    load_suite,
    metrics,
)


class ContentEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b, self.c, self.unknown = [
            FragmentKey.from_text("synthetic.md", text) for text in ("a", "b", "c", "unknown")
        ]
        self.case = ContentCase(
            id="one",
            query="synthetic",
            category="synthetic",
            kind="warning",
            judgements=[
                Judgement(fragment=self.a, grade=3),
                Judgement(fragment=self.b, grade=1, warning_ids=["W1"]),
                Judgement(fragment=self.c, grade=0),
            ],
            expected_warnings=["W1"],
        )

    def test_graded_metrics_separate_false_positives_from_unjudged(self):
        row = metrics(self.case, [self.c, self.b, self.unknown, self.a])
        self.assertEqual(row["recall_at_50"], 1)
        self.assertAlmostEqual(
            row["ndcg_at_10"], (1 / math.log2(3) + 7 / math.log2(5)) / (7 + 1 / math.log2(3))
        )
        self.assertEqual(row["false_positives_at_10"], 1)
        self.assertEqual(row["unjudged_at_10"], 1)
        self.assertEqual(row["warning_coverage_at_50"], 1)

    def test_missing_warning_and_relevant_fragment_reduce_coverage(self):
        row = metrics(self.case, [self.a])
        self.assertEqual(row["recall_at_50"], 0.5)
        self.assertEqual(row["warning_coverage_at_50"], 0)
        with self.assertRaisesRegex(ValueError, "unique"):
            metrics(self.case, [self.a, self.a])

    def test_content_identity_survives_db_id_changes_and_rejects_edited_corpus(self):
        suite = load_suite(Path(__file__).resolve().parents[2] / "eval" / "content_cases.json")
        corpus = list(
            {j.fragment.identity: j.fragment for c in suite.cases for j in c.judgements}.values()
        )
        rankings = {c.id: [j.fragment for j in c.judgements] for c in suite.cases}
        metadata = dict(
            model_name="synthetic",
            passage_profile="plain",
            text_repr_version=1,
            dictionary_fingerprint="fixed",
            signals="ABC",
            evaluation_mode="replay",
        )
        baseline = evaluate(suite, rankings, corpus, {**metadata, "index_generation": "old"})
        rebuilt = evaluate(suite, rankings, corpus, {**metadata, "index_generation": "new"})
        self.assertEqual(compare(baseline, rebuilt), [])
        changed = copy.deepcopy(rebuilt)
        changed["cases"][0]["recall_at_50"] = 0
        self.assertIn(suite.cases[0].id + ":recall_at_50", compare(baseline, changed))
        changed["metadata"]["corpus_hash"] = "edited"
        with self.assertRaisesRegex(ValueError, "corpus_hash"):
            compare(baseline, changed)
        with self.assertRaisesRegex(ValueError, "no longer resolve"):
            evaluate(suite, rankings, corpus[1:], metadata)
