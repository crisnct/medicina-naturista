"""Container smoke tests for the local web application; no live xAI requests."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from docx import Document
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from web_app import main
from web_app.ai import AIUnavailable, XAIClient
from web_app.config import settings
from web_app.documents import DocumentError, ingest
from web_app.profile import HealthProfile
from web_app.reports import create_pdf
from web_app.sessions import SessionStore


class FakeRequest:
    def __init__(self, sid: str, tab: str):
        self.session_hash = tab
        self.headers = {"cookie": f"naturist_sid={sid}"}


class FakeAI:
    def close(self):
        pass

    def extract_profile(self, message, asked_field):
        if "57" in message:
            return {"age": 57, "sex": "masculin", "weight_kg": 93,
                    "height_cm": 178, "health_conditions": ["hipertensiune"],
                    "symptoms": ["durere de cap"]}
        return {}

    def extract_document_facts(self, name, text):
        return {"summary": "simptome declarate", "symptoms": ["tuse"]}

    def generate(self, profile, evidence):
        first = next(iter(evidence))
        return {"uz_intern": [{"text": "Informație adjuvantă de verificat în sursă.", "evidence_ids": [first]}],
                "nutritie": [], "uz_extern": [], "alte_recomandari": [], "atentionari": []}

    def verify(self, sections, evidence):
        return sections


class FakeResponse:
    def __init__(self, zdr: bool, content: str = "{}"):
        self.headers = {"x-zero-data-retention": "true"} if zdr else {}
        self._content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class WebTests(unittest.TestCase):
    def test_profile_missing_then_unknown(self):
        profile = HealthProfile()
        profile.merge(FakeAI().extract_profile("57", None))
        self.assertIn("hipertensiune", profile.health_conditions)
        self.assertEqual(profile.age, 57)
        self.assertIsNone(profile.next_question())
        other = HealthProfile(health_conditions=["tuse"])
        self.assertIn("vârstă", other.next_question())
        self.assertTrue(other.mark_unknown_answer("nu știu"))
        self.assertIn("age", other.unknown)
        self.assertNotIn("vârstă", other.next_question())

    def test_zdr_gate_never_sends_sensitive_data_without_confirmation(self):
        with patch.dict(os.environ, {"GROK_API_KEY_MED": "synthetic-test-key"}):
            client = XAIClient(settings)
            calls = []
            def post(url, **kwargs):
                calls.append(kwargs["json"])
                return FakeResponse(False)
            client.http.post = post
            with self.assertRaises(AIUnavailable):
                client.complete_json("system", "SENSITIVE PATIENT DATA")
            self.assertEqual(len(calls), 1)
            self.assertNotIn("SENSITIVE", json.dumps(calls))
            client.close()

    def test_document_extraction_and_rejection(self):
        sid = SessionStore(Path(tempfile.mkdtemp()), 60, 120)
        session = sid.get("synthetic-cookie", "synthetic-tab", create=True)
        with tempfile.TemporaryDirectory() as cache:
            root = Path(cache)
            docx_path = root / "sample.docx"
            word = Document()
            word.add_paragraph("Informații: tuse și somn neliniștit.")
            word.save(docx_path)
            item = ingest(docx_path, session, settings, root, lambda texts: np.ones((len(texts), 384), dtype=np.float32))
            self.assertIn("tuse", item.chunks[0]["text"])
            self.assertFalse(docx_path.exists())
            pdf_path = root / "sample.pdf"
            pdf = canvas.Canvas(str(pdf_path))
            pdf.drawString(50, 780, "Synthetic medical note with cough and headache.")
            pdf.save()
            item_pdf = ingest(pdf_path, session, settings, root, lambda texts: np.ones((len(texts), 384), dtype=np.float32))
            self.assertTrue(item_pdf.chunks)
            img_path = root / "sample.png"
            image = Image.new("RGB", (1600, 360), "white")
            ImageDraw.Draw(image).text((40, 80), "DURERE DE CAP", fill="black", font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 90))
            image.save(img_path)
            item_image = ingest(img_path, session, settings, root, lambda texts: np.ones((len(texts), 384), dtype=np.float32))
            self.assertTrue(item_image.chunks)
            scan_path = root / "scan.pdf"
            scanned = canvas.Canvas(str(scan_path))
            scanned.drawImage(ImageReader(image), 30, 650, width=550, height=125)
            scanned.save()
            item_scan = ingest(scan_path, session, settings, root, lambda texts: np.ones((len(texts), 384), dtype=np.float32))
            self.assertTrue(item_scan.chunks)
            bad = root / "bad.pdf"
            bad.write_bytes(b"not a pdf")
            with self.assertRaises(DocumentError):
                ingest(bad, session, settings, root, lambda texts: None)
            self.assertFalse(bad.exists())
        sid.delete("synthetic-cookie", "synthetic-tab")

    def test_chat_retrieval_report_download_and_isolation(self):
        sid_a = "A" * 43
        sid_b = "B" * 43
        req_a = FakeRequest(sid_a, "tab-a")
        req_b = FakeRequest(sid_b, "tab-b")
        with patch.object(main, "ai", FakeAI()):
            history, *_ = main.on_load(req_a)
            self.assertIn("Bună", history[0]["content"])
            main.on_load(req_b)
            _, history_a, profile, _ = main.on_message(
                "Am 57 de ani, bărbat, 93 kg, 1,78 m. Am hipertensiune și durere de cap.", req_a
            )
            self.assertIn("57", profile)
            self.assertEqual(history_a[-1]["role"], "assistant")
            self.assertEqual(len(main.store.get(sid_b, "tab-b").history), 1)
            history_a, link = main.on_report(req_a)
            self.assertIn("Descarcă PDF", link)
            self.assertIn("Uz intern", history_a[-1]["content"])
            self.assertIn("documents/", history_a[-1]["content"])
            session_a = main.store.get(sid_a, "tab-a")
            self.assertTrue(session_a.report_bytes.startswith(b"%PDF-"))
            reader = PdfReader(io.BytesIO(session_a.report_bytes))
            content = "\n".join(page.extract_text() for page in reader.pages)
            self.assertIn("Nutriție", content)
            self.assertIn("Atenționări", content)
            with TestClient(main.app, base_url="https://testserver") as http:
                url = f"/api/reports/tab-a/{session_a.report_id}"
                ok = http.get(url, cookies={main.COOKIE: sid_a})
                self.assertEqual(ok.status_code, 200)
                self.assertEqual(ok.headers["content-type"], "application/pdf")
                other = http.get(url, cookies={main.COOKIE: sid_b})
                self.assertEqual(other.status_code, 404)
                cache = http.get("/gradio_api/file=/tmp/gradio-cache/fake.pdf")
                self.assertEqual(cache.status_code, 403)
            main.on_end(req_a)
            self.assertIsNone(main.store.get(sid_a, "tab-a"))
            self.assertIsNotNone(main.store.get(sid_b, "tab-b"))
        main.store.delete(sid_b, "tab-b")

    def test_pdf_diacritics_and_pagination(self):
        evidence = {"C1": {"source": "documents/test.md:1-3", "text": "Text suport"}}
        sections = {"uz_intern": [{"text": "Recomandare cu ă â î ș ț " + "îngrijire " * 300,
                                  "evidence_ids": ["C1"]} for _ in range(5)]}
        profile = {"health_conditions": ["tuse"], "symptoms": ["oboseală"], "age": None,
                   "sex": None, "weight_kg": None, "height_cm": None}
        pdf = create_pdf(profile, sections, evidence)
        pages = PdfReader(io.BytesIO(pdf)).pages
        self.assertGreater(len(pages), 1)
        text = "\n".join(page.extract_text() for page in pages)
        self.assertIn("ă â î ș ț", text)
        self.assertIn("documents/test.md:1-3", text)


if __name__ == "__main__":
    unittest.main()
