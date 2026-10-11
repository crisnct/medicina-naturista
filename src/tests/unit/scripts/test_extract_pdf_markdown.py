from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reportlab.pdfgen import canvas

try:
    from scripts import extract_pdf_markdown as extractor
except ModuleNotFoundError as exc:
    if exc.name not in {"pdfplumber", "pdfminer", "numpy"}:
        raise
    extractor = None


@unittest.skipIf(extractor is None, "Install the optional PDF dependencies: pip install -e .[pdf]")
class ExtractMarkdownTests(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(__file__).resolve().parents[4] / "tmp" / "pdfs"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def make_pdf(self, angle=0, columns=1):
        path = self.root / "source.pdf"
        pdf = canvas.Canvas(str(path), pagesize=(700, 900))
        pdf.translate(350, 450)
        pdf.rotate(-angle)
        pdf.translate(-350, -450)
        pdf.setFont("Helvetica-Bold", 22)
        pdf.drawString(100, 740, "Chapter 1 Introduction")
        for column in range(columns):
            x = 100 + column * 270
            pdf.setFont("Helvetica-Bold", 15)
            pdf.drawString(x, 700, f"1.{column+1} Details")
            pdf.setFont("Helvetica", 11)
            for row in range(12):
                pdf.drawString(x, 670-row*17, f"Column {column+1} row {row+1} has readable text.")
        pdf.showPage()
        pdf.save()
        return path

    def test_rotated_text_preserves_rows_at_one_to_thirty_degrees(self):
        for angle in (0, 1, -1, 15, -15, 30, -30):
            with self.subTest(angle=angle):
                source = self.make_pdf(angle)
                output = self.root / "output.md"
                report = self.root / "report.json"
                pages, _ = extractor.extract_markdown(source, output, report_path=report)
                text = output.read_text(encoding="utf-8")
                self.assertEqual(pages, 1)
                self.assertIn("## Chapter 1 Introduction", text)
                self.assertIn("### 1.1 Details", text)
                for row in range(1, 13):
                    self.assertIn(f"Column 1 row {row} has readable text.", text)
                self.assertIn("<!-- Pagina PDF 1 -->", text)
                self.assertNotIn("Phyllis", text)

    def test_two_columns_are_read_separately_after_deskew(self):
        source = self.make_pdf(15, 2)
        output = self.root / "output.md"
        extractor.extract_markdown(source, output)
        text = output.read_text(encoding="utf-8")
        self.assertLess(text.index("Column 1 row 12"), text.index("Column 2 row 1"))
        self.assertIn("Chapter 1 Introduction", text)

    def test_invalid_range_preserves_existing_output(self):
        source = self.make_pdf()
        output = self.root / "output.md"
        output.write_text("existing", encoding="utf-8")
        with self.assertRaises(ValueError):
            extractor.extract_markdown(source, output, extractor.Options(end_page=2))
        self.assertEqual(output.read_text(encoding="utf-8"), "existing")

    def test_source_cannot_be_overwritten(self):
        source = self.make_pdf()
        before = source.read_bytes()
        with self.assertRaises(ValueError):
            extractor.extract_markdown(source, source)
        self.assertEqual(source.read_bytes(), before)

    def test_repeated_interior_subheadings_survive_margin_filter(self):
        profile = extractor.Profile()
        lines = [extractor.Line("BOOK HEADER 12", 20, 200, 40, 50, 10, 0),
                 extractor.Line("Plant species name", 20, 180, 90, 103, 13, 1),
                 extractor.Line("Composition", 20, 100, 120, 130, 10, 0),
                 extractor.Line("This paragraph describes the detailed composition of this species and its properties.", 20, 300, 140, 150, 10, 0)]
        for _ in range(10):
            profile.observe(lines)
        text, _ = extractor._render_page(lines, profile)
        self.assertNotIn("BOOK HEADER", text)
        self.assertIn("#### Composition", text)

    def test_ocr_failure_preserves_output(self):
        source = self.make_pdf()
        output = self.root / "output.md"
        output.write_text("existing", encoding="utf-8")
        with patch.object(extractor, "_ocr_glyphs", side_effect=RuntimeError("OCR failed")):
            with self.assertRaises(RuntimeError):
                extractor.extract_markdown(source, output, extractor.Options(ocr="always"))
        self.assertEqual(output.read_text(encoding="utf-8"), "existing")

    def test_skewed_ocr_characters_with_horizontal_matrices(self):
        # OCR can position every character individually while leaving each glyph
        # matrix unrotated. This reproduces the difficult Compendiu text layer.
        from types import SimpleNamespace
        import math
        chars = []
        angle = math.radians(25)
        for row in range(8):
            for index, letter in enumerate(f"Readable OCR row {row+1}"):
                x = 80 + index * 7
                y = 100 + row * 16 + math.tan(angle) * x
                chars.append({"text": letter, "matrix": (1,0,0,1,x,900-y),
                              "x0": x, "x1": x+6, "width": 6, "adv": 6,
                              "size": 10, "fontname": "OCR"})
        page = SimpleNamespace(height=900, chars=chars)
        page.dedupe_chars = lambda **kwargs: page
        glyphs, found = extractor._text_glyphs(page, extractor.Options())
        self.assertAlmostEqual(found, 25, delta=.6)
        lines = extractor._group_glyphs(glyphs)
        self.assertEqual([line.text for line in lines], [f"Readable OCR row {r+1}" for r in range(8)])

    def test_scan_deskew_from_one_to_thirty_degrees(self):
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new("RGB", (1400, 1800), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=30)
        for row in range(15):
            draw.text((200, 200 + row * 70), f"Readable scanned text on row {row+1}.", font=font, fill="black")
        for angle in (-30, -15, -1, 1, 15, 30):
            with self.subTest(angle=angle):
                rotated = image.rotate(-angle, expand=True, fillcolor="white")
                _, found = extractor._deskew_image(rotated, 30)
                self.assertAlmostEqual(found, angle, delta=.7)

    def test_wide_spaces_do_not_reorder_heading_fragments(self):
        lines = [extractor.Line("Panax ginseng (sin. Panax", 30, 240, 50, 61, 11, 0),
                 extractor.Line("pseudoginseng, Panax", 275, 395, 49.5, 60.5, 11, 0),
                 extractor.Line("schinseng), Fam. Araliaceae", 30, 220, 63, 74, 11, 0),
                 extractor.Line("The main paragraph describes this plant and provides detailed information about its properties.", 30, 395, 80, 90, 10, 0)]
        ordered = extractor._reading_order(lines, [])
        self.assertEqual(ordered[0].text, "Panax ginseng (sin. Panax pseudoginseng, Panax")
        text, _ = extractor._render_page(ordered, extractor.Profile())
        self.assertIn("### Panax ginseng (sin. Panax pseudoginseng, Panax schinseng), Fam. Araliaceae", text)


if __name__ == "__main__":
    unittest.main()
