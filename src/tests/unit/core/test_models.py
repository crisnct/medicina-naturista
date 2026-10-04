import tempfile
import unittest
from pathlib import Path

from backend.core.models import HealthProfile, SessionData


class CoreModelTests(unittest.TestCase):
    def test_session_owns_a_health_profile_without_web_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            session = SessionData("cookie", "tab", Path(directory))
            self.assertIsInstance(session.profile, HealthProfile)
