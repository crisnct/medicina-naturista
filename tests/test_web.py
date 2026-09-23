"""Container smoke tests for the local web application; no live xAI requests."""
from __future__ import annotations

import io
import json
import os
import shutil
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
from web_app.retrieval import consultation_queries
from web_app.sessions import SessionStore


class FakeRequest:
    def __init__(self, sid: str, tab: str):
        self.session_hash = tab
        self.headers = {"cookie": f"naturist_sid={sid}"}


class FakeAI:
    follow_up_calls = 0
    follow_up_profile = None
    report_profile = None

    def close(self):
        pass

    def extract_profile(self, message, asked_field):
        if asked_field == "age":
            return {"age": 57}
        if asked_field == "weight_kg":
            return {"weight_kg": 93}
        if asked_field == "height_cm":
            return {"height_cm": 178}
        if asked_field == "health_problem":
            return {"health_conditions": ["hipertensiune"], "symptoms": ["durere de cap"]}
        return {}

    def generate_follow_up_questions(self, profile):
        type(self).follow_up_calls += 1
        type(self).follow_up_profile = profile
        return ["De când au apărut simptomele?", "Ce medicamente luați în prezent?"]

    def extract_document_facts(self, name, text):
        return {"summary": "simptome declarate", "symptoms": ["tuse"]}

    def generate(self, profile, evidence):
        type(self).report_profile = profile
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
        self.assertIn("numiți", profile.next_question())
        profile.set_full_name("Popescu Ion")
        self.assertIn("vârstă", profile.next_question())
        profile.merge(FakeAI().extract_profile("57", "age"), scalar_field="age")
        self.assertEqual(profile.age, 57)
        self.assertIn("greutatea", profile.next_question())
        self.assertTrue(profile.mark_unknown_answer("nu știu"))
        self.assertIn("weight_kg", profile.unknown)
        self.assertIn("înălțimea", profile.next_question())
        profile.merge({"height_cm": 178}, scalar_field="height_cm")
        self.assertIn("problemă", profile.next_question())
        profile.set_health_problem("Durere persistentă de cap")
        profile.set_follow_up_questions(["De când?"])
        self.assertEqual(profile.next_question(), "De când?")
        profile.record_follow_up_answer("De două săptămâni")
        self.assertTrue(profile.report_ready)

        prefilled = HealthProfile(full_name="Popescu Ion")
        prefilled.merge({"age": 40, "weight_kg": 80, "height_cm": 180})
        self.assertIn("vârstă", prefilled.next_question())

    def test_failed_follow_up_generation_allows_report(self):
        profile = HealthProfile(full_name="Popescu Ion", health_problem="durere de cap")
        profile.completed_fields.update({"age", "weight_kg", "height_cm"})
        profile.fail_follow_up()
        self.assertEqual(profile.follow_up_status, "failed")
        self.assertTrue(profile.report_ready)

    def test_follow_up_questions_are_cleaned_deduplicated_and_limited(self):
        client = XAIClient(settings)
        values = ["  Întrebarea unu?  ", "întrebarea unu?", "", 7]
        values.extend(f"Întrebarea {number}?" for number in range(2, 15))
        with patch.object(client, "complete_json", return_value={"questions": values}):
            questions = client.generate_follow_up_questions({"health_problem": "test"})
        client.close()
        self.assertEqual(len(questions), 10)
        self.assertEqual(questions[0], "Întrebarea unu?")
        self.assertEqual(len({question.casefold() for question in questions}), 10)

    def test_consultation_queries_include_full_long_transcript(self):
        profile = HealthProfile(full_name="Popescu Ion", health_problem="durere articulară")
        profile.health_conditions = ["gută"]
        profile.add_transcript("assistant", "De când aveți durerea?")
        profile.add_transcript("user", "De trei zile")
        marker = "FINAL-CONTEXT"
        profile.add_health_context(("simptom repetat " * 100) + marker)
        queries = consultation_queries(profile)
        self.assertTrue(any("De când aveți durerea?" in query and "De trei zile" in query for query in queries))
        self.assertTrue(any(marker in query for query in queries))
        self.assertTrue(all(len(query) <= 900 for query in queries))

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
            windows_font = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts" / "arial.ttf"
            linux_font = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
            font_path = windows_font if windows_font.is_file() else linux_font
            font = ImageFont.truetype(str(font_path), 90)
            ImageDraw.Draw(image).text((40, 80), "DURERE DE CAP", fill="black", font=font)
            image.save(img_path)
            if shutil.which("tesseract"):
                item_image = ingest(
                    img_path, session, settings, root,
                    lambda texts: np.ones((len(texts), 384), dtype=np.float32),
                )
                self.assertTrue(item_image.chunks)
            if shutil.which("tesseract") and shutil.which("pdftoppm"):
                scan_path = root / "scan.pdf"
                scanned = canvas.Canvas(str(scan_path))
                scanned.drawImage(ImageReader(image), 30, 650, width=550, height=125)
                scanned.save()
                item_scan = ingest(
                    scan_path, session, settings, root,
                    lambda texts: np.ones((len(texts), 384), dtype=np.float32),
                )
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
        FakeAI.follow_up_calls = 0
        FakeAI.follow_up_profile = None
        FakeAI.report_profile = None
        with patch.object(main, "ai", FakeAI()):
            history, *_ = main.on_load(req_a)
            self.assertIn("Bună", history[0]["content"])
            self.assertIn("numiți", history[-1]["content"])
            main.on_load(req_b)
            main.on_message("Popescu Ion", req_a)
            main.on_message("57", req_a)
            main.on_message("93", req_a)
            main.on_message("178", req_a)
            _, history_a, profile, _ = main.on_message("Am hipertensiune și durere de cap.", req_a)
            self.assertIn("57", profile)
            self.assertIn("De când", history_a[-1]["content"])
            self.assertEqual(FakeAI.follow_up_profile["full_name"], "Popescu Ion")
            self.assertEqual(FakeAI.follow_up_profile["age"], 57)
            self.assertEqual(FakeAI.follow_up_profile["weight_kg"], 93)
            self.assertEqual(FakeAI.follow_up_profile["height_cm"], 178)
            self.assertIn("hipertensiune", FakeAI.follow_up_profile["health_problem"])
            blocked_history, blocked_link = main.on_report(req_a)
            self.assertEqual(blocked_link, "")
            self.assertIn("2 întrebări", blocked_history[-1]["content"])
            main.on_message("De trei zile", req_a)
            _, history_a, profile, _ = main.on_message("Iau tratamentul prescris", req_a)
            self.assertIn("2/2", profile)
            self.assertEqual(FakeAI.follow_up_calls, 1)
            self.assertEqual(history_a[-1]["role"], "assistant")
            self.assertEqual(len(main.store.get(sid_b, "tab-b").history), 2)
            history_a, link = main.on_report(req_a)
            report_dialogue = " ".join(entry["content"] for entry in FakeAI.report_profile["transcript"])
            self.assertIn("De când au apărut simptomele?", report_dialogue)
            self.assertIn("De trei zile", report_dialogue)
            self.assertIn("Descarcă PDF", link)
            self.assertIn("Uz intern", history_a[-1]["content"])
            self.assertIn("documents/", history_a[-1]["content"])
            session_a = main.store.get(sid_a, "tab-a")
            self.assertTrue(session_a.report_bytes.startswith(b"%PDF-"))
            reader = PdfReader(io.BytesIO(session_a.report_bytes))
            content = "\n".join(page.extract_text() for page in reader.pages)
            self.assertIn("Recomandări naturiste pentru Popescu Ion", content)
            self.assertIn("De când au apărut simptomele?", content)
            self.assertIn("De trei zile", content)
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
        profile = {"full_name": "Popescu Ion", "health_conditions": ["tuse"], "symptoms": ["oboseală"],
                   "age": None, "sex": None, "weight_kg": None, "height_cm": None,
                   "health_problem": "tuse și oboseală", "transcript": []}
        pdf = create_pdf(profile, sections, evidence)
        pages = PdfReader(io.BytesIO(pdf)).pages
        self.assertGreater(len(pages), 1)
        text = "\n".join(page.extract_text() for page in pages)
        self.assertIn("ă â î ș ț", text)
        self.assertIn("documents/test.md:1-3", text)


if __name__ == "__main__":
    unittest.main()
