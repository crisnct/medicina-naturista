"""Smoke tests for the local web application; no live xAI requests."""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfReader

from search_medical_embeddings import _normalize_fastembed_metadata
from web_app import main
from web_app.ai import GENERATE_REPORT_SYSTEM_PROMPT_PATH, XAIClient
from web_app.config import settings
from web_app.profile import HEALTH_PROBLEM_QUESTION, HealthProfile
from web_app.reports import create_pdf, format_recommendation, report_title
from web_app.retrieval import Retriever, _meaningful_words, consultation_queries
from web_app.sessions import SessionStore


class FakeRequest:
    def __init__(self, sid: str, tab: str):
        self.session_hash = tab
        self.headers = {"cookie": f"naturist_sid={sid}"}


class FakeAI:
    generate_calls = 0
    report_profile = None

    def close(self):
        pass

    def generate(self, profile, evidence):
        type(self).generate_calls += 1
        type(self).report_profile = profile
        first = next(iter(evidence))
        return {
            "uz_intern": [{"text": "Informație adjuvantă din sursă.", "evidence_ids": [first]}],
            "nutritie": [],
            "uz_extern": [],
            "alte_recomandari": [],
            "atentionari": [],
        }


class FakeRetriever:
    def collect(self, session):
        return {
            "C1": {
                "source": "documents/plan.md:1-5",
                "text": "Informație locală relevantă.",
            }
        }


class FakeResponse:
    def __init__(self, content: str):
        self._content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "status": "completed",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": self._content}],
            }],
        }


class WebTests(unittest.TestCase):
    def test_fastembed_metadata_paths_are_portable_between_windows_and_linux(self):
        with tempfile.TemporaryDirectory() as temp:
            model_dir = Path(temp) / "models--test--model"
            model_dir.mkdir()
            metadata_file = model_dir / "files_metadata.json"
            metadata_file.write_text(
                '{"snapshots\\\\revision\\\\onnx\\\\model.onnx": {"size": 42}}',
                encoding="utf-8",
            )

            _normalize_fastembed_metadata(Path(temp))

            self.assertEqual(
                metadata_file.read_text(encoding="utf-8"),
                '{"snapshots/revision/onnx/model.onnx": {"size": 42}}',
            )

    def test_profile_asks_only_health_problem(self):
        profile = HealthProfile()
        self.assertEqual(profile.next_question(), HEALTH_PROBLEM_QUESTION)
        profile.add_transcript("assistant", HEALTH_PROBLEM_QUESTION)
        profile.add_transcript("user", "Gripă și răceală")
        profile.set_health_problem("Gripă și răceală")

        self.assertTrue(profile.report_ready)
        self.assertIsNone(profile.next_question())
        self.assertEqual(profile.as_dict()["health_problem"], "Gripă și răceală")
        self.assertEqual(set(profile.as_dict()), {"health_problem", "health_context", "transcript"})

    def test_recommendation_label_is_bold_and_underlined(self):
        formatted = format_recommendation("Tinctură de soc: 2 linguri pe zi")
        self.assertEqual(formatted, "<b><u>Tinctură de soc</u></b>: 2 linguri pe zi")
        self.assertEqual(
            format_recommendation("Suc din morcovi, ananas, ghimbir și usturoi pentru răceală."),
            "<b><u>Suc din morcovi, ananas, ghimbir și usturoi</u></b> pentru răceală.",
        )
        self.assertEqual(
            format_recommendation("Lichen piatră cu rădăcină de brusture și echinaceea pulbere în părți egale"),
            "<b><u>Lichen piatră cu rădăcină de brusture și echinaceea</u></b> pulbere în părți egale",
        )

    def test_report_title_restores_common_romanian_diacritics(self):
        self.assertEqual(
            report_title({"health_problem": "gripa si raceala"}),
            "Recomandări naturiste pentru gripă și răceală",
        )

    def test_generate_uses_one_ai_request_with_all_evidence(self):
        client = XAIClient(settings)
        calls = []
        result = {
            "uz_intern": [
                {"text": f"Recomandarea {number}", "evidence_ids": [f"E{number}"]}
                for number in range(12)
            ],
            "nutritie": [],
            "uz_extern": [],
            "alte_recomandari": [],
            "atentionari": [],
        }
        evidence = {
            f"E{number}": {"source": "documents/plan.md", "text": f"Fragmentul {number}"}
            for number in range(12)
        }

        def complete_json(system, user, max_tokens):
            calls.append((system, user, max_tokens))
            return result

        with patch.object(client, "complete_json", side_effect=complete_json):
            sections = client.generate({"health_problem": "gripă"}, evidence)
        client.close()

        self.assertEqual(len(calls), 1)
        self.assertEqual(
            calls[0][0],
            GENERATE_REPORT_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip(),
        )
        self.assertTrue(all(f"Fragmentul {number}" in calls[0][1] for number in range(12)))
        self.assertEqual(calls[0][2], 20000)
        self.assertEqual(len(sections["uz_intern"]), 12)

    def test_responses_api_sends_exactly_one_http_request(self):
        with patch.dict(os.environ, {"GROK_API_KEY_MED": "synthetic-test-key"}):
            client = XAIClient(settings)
            calls = []

            def post(url, **kwargs):
                calls.append((url, kwargs["json"]))
                return FakeResponse('{"uz_intern": []}')

            client.http.post = post
            result = client.complete_json("system prompt", "user prompt", 321)
            client.close()

        self.assertEqual(result, {"uz_intern": []})
        self.assertEqual(len(calls), 1)
        url, request = calls[0]
        self.assertTrue(url.endswith("/v1/responses"))
        self.assertEqual(request["input"][0], {"role": "system", "content": "system prompt"})
        self.assertEqual(request["text"]["format"], {"type": "json_object"})
        self.assertEqual(request["max_output_tokens"], 321)
        self.assertNotIn("messages", request)

    def test_consultation_queries_keep_entire_long_context(self):
        profile = HealthProfile(health_problem="durere articulară")
        profile.add_transcript("assistant", HEALTH_PROBLEM_QUESTION)
        profile.add_transcript("user", "Durere de trei zile")
        marker = "FINAL-CONTEXT"
        profile.add_health_context(("simptom repetat " * 100) + marker)
        queries = consultation_queries(profile)

        self.assertTrue(any(HEALTH_PROBLEM_QUESTION in query for query in queries))
        self.assertTrue(any(marker in query for query in queries))
        self.assertTrue(all(len(query) <= 900 for query in queries))

    def test_flu_query_retrieves_reflection_fragment_from_internal_dictionary(self):
        profile = HealthProfile()
        profile.set_health_problem("vreau recomandari naturiste pentru gripa")
        session = type("SyntheticSession", (), {"profile": profile})()
        evidence = Retriever(settings.index_dir, settings.documents_dir).collect(session)

        self.assertEqual(_meaningful_words(profile.health_problem), {"gripa"})
        self.assertLessEqual(len(evidence), 500)
        self.assertTrue(any(
            "Marele dict" in item["source"]
            and "13522-13575" in item["source"]
            and "nevoie de\nodihnă sau de o pauză" in item["text"]
            for item in evidence.values()
        ))
        self.assertTrue(any(
            "Plan tratament naturist" in item["source"]
            and "Tinctură fructe de soc" in item["text"]
            for item in evidence.values()
        ))

    def test_chat_automatically_generates_report_after_single_answer(self):
        sid_a = "A" * 43
        sid_b = "B" * 43
        req_a = FakeRequest(sid_a, "tab-a")
        req_b = FakeRequest(sid_b, "tab-b")
        FakeAI.generate_calls = 0
        FakeAI.report_profile = None

        with patch.object(main, "ai", FakeAI()), patch.object(main, "retriever", FakeRetriever()):
            history, link = main.on_load(req_a)
            self.assertEqual(history[-1]["content"], HEALTH_PROBLEM_QUESTION)
            self.assertEqual(link, "")
            main.on_load(req_b)

            _, history, link = main.on_message("Gripă și răceală", req_a)
            self.assertIn("a început generarea", history[-1]["content"])
            self.assertEqual(link, "")
            self.assertEqual(FakeAI.generate_calls, 0)

            history, link = main.on_auto_report(req_a)
            self.assertEqual(FakeAI.generate_calls, 1)
            self.assertEqual(FakeAI.report_profile["health_problem"], "Gripă și răceală")
            self.assertIn("Descarcă PDF", link)
            self.assertIn("Uz intern", history[-1]["content"])
            self.assertIn("[1]", history[-1]["content"])
            self.assertIn("Bibliografie", history[-1]["content"])
            self.assertIn("1 - plan.md:1-5", history[-1]["content"])
            self.assertEqual(len(main.store.get(sid_b, "tab-b").history), 2)

            session_a = main.store.get(sid_a, "tab-a")
            self.assertTrue(session_a.report_bytes.startswith(b"%PDF-"))
            content = "\n".join(
                page.extract_text() for page in PdfReader(io.BytesIO(session_a.report_bytes)).pages
            )
            self.assertIn("Recomandări naturiste", content)
            self.assertIn("Gripă și răceală", content)

            with TestClient(main.app, base_url="https://testserver") as http:
                url = f"/api/reports/tab-a/{session_a.report_id}"
                self.assertEqual(http.get(url, cookies={main.COOKIE: sid_a}).status_code, 200)
                self.assertEqual(http.get(url, cookies={main.COOKIE: sid_b}).status_code, 404)

            main.on_end(req_a)
            self.assertIsNone(main.store.get(sid_a, "tab-a"))
            self.assertIsNotNone(main.store.get(sid_b, "tab-b"))
            main.store.delete(sid_b, "tab-b")

    def test_public_report_link_uses_gradio_root_path(self):
        sid = "C" * 43
        request = FakeRequest(sid, "tab-public")
        session = main.store.get(sid, "tab-public", create=True)
        session.report_id = "report-1"
        with patch.dict(os.environ, {"GRADIO_ROOT_PATH": "/medicina"}):
            link = main._download_html(session)
        self.assertIn('/medicina/api/reports/tab-public/report-1', link)
        main.store.delete(sid, "tab-public")

    def test_pdf_diacritics_and_pagination(self):
        evidence = {
            "C1": {"source": "documents/test.md:1-3", "text": "Text suport"},
            "C2": {"source": "documents/alt-test.md:4-8", "text": "Alt text suport"},
        }
        sections = {
            "uz_intern": [{
                "text": "Recomandare cu ă â î ș ț " + "îngrijire " * 300,
                "evidence_ids": ["C1", "C2"] if number == 0 else ["C1"],
            } for number in range(5)]
        }
        profile = {"health_problem": "tuse și oboseală", "transcript": []}
        pdf = create_pdf(profile, sections, evidence)
        pages = PdfReader(io.BytesIO(pdf)).pages
        self.assertGreater(len(pages), 1)
        text = "\n".join(page.extract_text() for page in pages)
        self.assertIn("ă â î ș ț", text)
        self.assertIn("[1]", text)
        self.assertIn("[2]", text)
        self.assertIn("6. Bibliografie", text)
        self.assertIn("1 - test.md:1-3", text)
        self.assertIn("2 - alt-test.md:4-8", text)
        self.assertNotIn("documents/test.md:1-3", text)
        links = [
            annotation.get_object()
            for page in pages
            for annotation in page.get("/Annots", [])
            if annotation.get_object().get("/Subtype") == "/Link"
        ]
        self.assertGreaterEqual(len(links), 2)
        self.assertTrue(all("/Dest" in link for link in links))

    def test_session_store_has_no_attachment_state(self):
        store = SessionStore(Path(tempfile.mkdtemp()), 60, 120)
        session = store.get("synthetic-cookie", "synthetic-tab", create=True)
        self.assertFalse(hasattr(session, "documents"))
        store.delete("synthetic-cookie", "synthetic-tab")


if __name__ == "__main__":
    unittest.main()
