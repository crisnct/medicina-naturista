import unittest

from backend.web.main import app


class ApplicationIntegrationTests(unittest.TestCase):
    def test_application_exposes_health_and_report_routes(self):
        paths = set(app.openapi()["paths"])
        self.assertIn("/healthz", paths)
        self.assertIn("/api/reports/{tab_id}/{report_id}", paths)
