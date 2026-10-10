"""Explicit opt-in smoke test against an operator-provided local corpus/index."""

import os
import unittest

from backend.ai.query_terms import plain
from backend.ai.retrieval import Retriever, _meaningful_words
from backend.config import Settings, configure_settings
from backend.core.models import HealthProfile


@unittest.skipUnless(
    os.getenv("RUN_LOCAL_CORPUS_TESTS") == "1",
    "requires explicit local corpus/index opt-in",
)
class LocalCorpusTests(unittest.TestCase):
    def setUp(self):
        configure_settings(Settings.from_env(dotenv=True))

    def test_flu_query_ranks_titled_sections_first_from_the_real_index(self):
        profile = HealthProfile()
        profile.set_health_problem("vreau recomandari naturiste pentru gripa")
        session = type("SyntheticSession", (), {"profile": profile})()
        retriever = Retriever(Settings.from_env(dotenv=True).documents_dir)
        evidence = retriever.collect(session, 1_000_000)

        self.assertEqual(_meaningful_words(profile.health_problem), {"gripa"})
        titled = [item["condition_in_title"] for item in evidence.values()]
        self.assertTrue(any(titled))
        self.assertEqual(titled, sorted(titled, reverse=True))
        self.assertTrue(
            any(
                "Plan tratament naturist" in item["source"]
                and "tinctura fructe de soc" in plain(item["text"])
                for item in evidence.values()
            )
        )
        self.assertLessEqual(
            sum(len(item["text"]) for item in evidence.values()), 1_000_000
        )
