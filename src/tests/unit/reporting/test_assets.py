import unittest
from io import BytesIO
from unittest.mock import patch

from pypdf import PdfReader

from backend.reporting.pdf import ORNAMENT_PNG, create_pdf


class ReportingAssetTests(unittest.TestCase):
    def test_pdf_ornament_is_packaged_with_reporting(self):
        self.assertTrue(ORNAMENT_PNG.is_file())
        self.assertEqual("assets", ORNAMENT_PNG.parent.name)

    def test_recommendation_fonts_in_every_non_nutrition_section(self):
        sections = {
            key: [
                {
                    "text": "Vitamina B6 (piridoxina) – Descriere documentată.",
                    "evidence_ids": ["C1"],
                }
            ]
            for key in ("uz_intern", "uz_extern", "alte_recomandari", "atentionari")
        }
        evidence = {"C1": {"source": "documents/test.md:1", "text": "Text suport"}}
        with patch("backend.reporting.pdf.report_title", return_value="Verificare formatare"):
            report = create_pdf({"health_problem": "", "transcript": []}, sections, evidence)
        fragments = []

        def collect(text, cm, tm, font, size):
            fragments.append((text.strip(), str((font or {}).get("/BaseFont", ""))))

        for page in PdfReader(BytesIO(report)).pages:
            page.extract_text(visitor_text=collect)

        labels = [font for text, font in fragments if text == "● Vitamina B6 (piridoxina):"]
        descriptions = [font for text, font in fragments if text == "Descriere documentată."]
        self.assertEqual(len(labels), 4)
        self.assertEqual(len(descriptions), 4)
        self.assertTrue(all("Bold" in font for font in labels))
        self.assertTrue(all("Bold" not in font for font in descriptions))
