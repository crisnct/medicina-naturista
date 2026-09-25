from pathlib import Path
import unittest

from medicina_naturista.ai.client import GENERATE_REPORT_SYSTEM_PROMPT_PATH
from medicina_naturista.ai.retrieval import GENERIC_QUERY_WORDS_PATH


class AIResourceTests(unittest.TestCase):
    def test_packaged_ai_resources_exist(self):
        self.assertTrue(GENERATE_REPORT_SYSTEM_PROMPT_PATH.is_file())
        self.assertTrue(GENERIC_QUERY_WORDS_PATH.is_file())
        self.assertEqual("resources", GENERIC_QUERY_WORDS_PATH.parent.name)
        self.assertEqual(Path("prompts"), GENERATE_REPORT_SYSTEM_PROMPT_PATH.parent.relative_to(
            GENERATE_REPORT_SYSTEM_PROMPT_PATH.parents[1]
        ))
