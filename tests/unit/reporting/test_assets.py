import unittest

from medicina_naturista.reporting.pdf import ORNAMENT_PNG


class ReportingAssetTests(unittest.TestCase):
    def test_pdf_ornament_is_packaged_with_reporting(self):
        self.assertTrue(ORNAMENT_PNG.is_file())
        self.assertEqual("assets", ORNAMENT_PNG.parent.name)
