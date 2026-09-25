import unittest

from medicina_naturista.web.main import app


class ApplicationIntegrationTests(unittest.TestCase):
    def test_application_exposes_health_and_report_routes(self):
        paths = {route.path for route in app.routes}
        self.assertIn("/healthz", paths)
        self.assertIn("/api/reports/{tab_id}/{report_id}", paths)
