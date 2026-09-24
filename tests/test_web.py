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
import web_app.ai as ai_module
from web_app.ai import GENERATE_REPORT_SYSTEM_PROMPT_PATH, XAIClient
from web_app.config import settings
from web_app.profile import HEALTH_PROBLEM_QUESTION, HealthProfile
from web_app.reports import create_pdf, format_recommendation, report_title
from web_app.retrieval import Retriever, _meaningful_words, consultation_queries
from web_app.sessions import SessionStore


class FakeRequest:
    # Create the minimal request object required by the Gradio callbacks.
    def __init__(self, sid: str, tab: str):
        self.session_hash = tab
        self.headers = {"cookie": f"naturist_sid={sid}"}


class FakeAI:
    generate_calls = 0
    report_profile = None

    # Provide the client cleanup interface without opening network resources.
    def close(self):
        pass

    # Return one deterministic evidence-backed recommendation for UI tests.
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
    # Return a small deterministic evidence inventory for report tests.
    def collect(self, session):
        return {
            "C1": {
                "source": "documents/plan.md:1-5",
                "text": "Informație locală relevantă.",
            }
        }


class FakeResponse:
    # Store the synthetic API response body used by the HTTP client tests.
    def __init__(self, content: str):
        self._content = content

    # Emulate a successful HTTP response status check.
    def raise_for_status(self):
        return None

    # Return the synthetic response in the xAI Responses API shape.
    def json(self):
        return {
            "status": "completed",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": self._content}],
            }],
        }


class WebTests(unittest.TestCase):
    # Verify that cached model metadata paths are normalized across operating systems.
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

    # Verify that profile questioning stops after the health problem is supplied.
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

    # Verify that report recommendation labels use bold emphasis without underlining.
    def test_recommendation_label_is_bold_and_underlined(self):
        formatted = format_recommendation("Tinctură de soc: 2 linguri pe zi")
        self.assertEqual(formatted, "<b>Tinctură de soc</b>: 2 linguri pe zi")
        self.assertEqual(
            format_recommendation("Suc din morcovi, ananas, ghimbir și usturoi pentru răceală."),
            "<b>Suc din morcovi, ananas, ghimbir și usturoi</b> pentru răceală.",
        )
        self.assertEqual(
            format_recommendation("Lichen piatră cu rădăcină de brusture și echinaceea pulbere în părți egale"),
            "<b>Lichen piatră cu rădăcină de brusture și echinaceea</b> pulbere în părți egale",
        )

    # Verify that common Romanian diacritics are restored in report titles.
    def test_report_title_restores_common_romanian_diacritics(self):
        self.assertEqual(
            report_title({"health_problem": "gripa si raceala"}),
            "Recomandări naturiste pentru gripă și răceală",
        )

    # Verify that report generation sends all evidence in one AI request.
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

        # Capture the synthetic request and return the prepared AI result.
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

    # Verify that AI items remain visible even without valid local evidence IDs.
    def test_generate_preserves_items_without_valid_evidence_ids(self):
        client = XAIClient(settings)
        result = {
            "uz_intern": [],
            "nutritie": [
                {"text": "Rețetă culinară fără sursă locală", "evidence_ids": []},
                {"text": "Recomandare fără câmp evidence_ids"},
                {"text": "Recomandare cu ID necunoscut", "evidence_ids": ["UNKNOWN"]},
            ],
            "uz_extern": [],
            "alte_recomandari": [],
            "atentionari": [],
        }

        with patch.object(client, "complete_json", return_value=result):
            sections = client.generate({"health_problem": "gripă"}, {"E1": {"source": "plan.md", "text": "sursă"}})
        client.close()

        self.assertEqual(
            sections["nutritie"],
            [
                {"text": "Rețetă culinară fără sursă locală", "evidence_ids": []},
                {"text": "Recomandare fără câmp evidence_ids", "evidence_ids": []},
                {"text": "Recomandare cu ID necunoscut", "evidence_ids": ["UNKNOWN"]},
            ],
        )

    # Verify the structured nutrition object is normalized into the internal item format.
    def test_generate_normalizes_structured_nutrition_object(self):
        client = XAIClient(settings)
        result = {
            "uz_intern": [],
            "nutritie": {
                "retete": ["Supă ușoară", "Ceai de ghimbir"],
                "recomandate": "hrean, țelină",
                "nerecomandate": "zahăr",
                "interzise": "",
                "alte": "Alimentație ușoară la febră",
            },
            "uz_extern": [],
            "alte_recomandari": [],
            "atentionari": [],
        }

        with patch.object(client, "complete_json", return_value=result):
            sections = client.generate(
                {"health_problem": "gripă"},
                {"E1": {"source": "plan.md", "text": "fragment"}},
            )
        client.close()

        self.assertEqual(
            sections["nutritie"],
            [
                {"text": "[RETETA]: Supă ușoară", "evidence_ids": []},
                {"text": "[RETETA]: Ceai de ghimbir", "evidence_ids": []},
                {"text": "[RECOMANDAT]: hrean, țelină", "evidence_ids": []},
                {"text": "[NERECOMANDAT]: zahăr", "evidence_ids": []},
                {"text": "[ALTE]: Alimentație ușoară la febră", "evidence_ids": []},
            ],
        )

    # Verify source-count ordering independently for every report section.
    def test_report_orders_every_section_by_descending_source_count(self):
        evidence = {
            "C1": {"source": "documents/a.md:1-2", "text": "A"},
            "C2": {"source": "documents/b.md:1-2", "text": "B"},
            "C3": {"source": "documents/c.md:1-2", "text": "C"},
        }
        sections = {
            "uz_intern": [
                {"text": "Puține surse", "evidence_ids": ["C1"]},
                {"text": "Multe surse", "evidence_ids": ["C1", "C2", "C3"]},
            ],
            "nutritie": [
                {"text": "Mediu", "evidence_ids": ["C1", "C2"]},
                {"text": "Mult", "evidence_ids": ["C1", "C2", "C3"]},
            ],
        }

        report = main._recommendation_text(sections, evidence)

        self.assertLess(report.index("Multe surse"), report.index("Puține surse"))
        self.assertLess(report.index("Mult"), report.index("Mediu"))
        self.assertIn("[1] [2] [3]", report)

    # Verify nutrition subsections keep their fixed order and recipes are rendered one per line.
    def test_nutrition_subsections_are_ordered_and_recipes_are_split(self):
        sections = {
            "uz_intern": [],
            "nutritie": [
                {"text": "Alimente nerecomandate: zahăr", "evidence_ids": []},
                {
                    "text": "Rețete culinare: - Salată de hrean - Supă ușoară cu țelină - Ceai de ghimbir",
                    "evidence_ids": [],
                },
                {"text": "Alimente recomandate: hrean, țelină", "evidence_ids": []},
                {"text": "Alimente interzise: -", "evidence_ids": []},
                {"text": "Alte recomandări nutriționale: alimentație ușoară", "evidence_ids": []},
            ],
            "uz_extern": [],
            "alte_recomandari": [],
            "atentionari": [],
        }

        report = main._recommendation_text(sections, {})

        labels = [
            "• Rețete culinare",
            "• Alimente recomandate",
            "• Alimente nerecomandate",
            "• Alimente total interzise",
            "• Alte recomandări",
        ]
        self.assertEqual(labels, sorted(labels, key=report.index))
        self.assertLess(report.index("    - Salată de hrean"), report.index("    - Supă ușoară cu țelină"))
        self.assertLess(report.index("    - Supă ușoară cu țelină"), report.index("    - Ceai de ghimbir"))
        self.assertNotIn("• Rețete culinare:\n    - Rețete culinare", report)

        combined_sections = {
            "uz_intern": [],
            "nutritie": [{
                "text": (
                    "Rețete culinare: Alimente recomandate: hrean, țelină. "
                    "Alimente nerecomandate: zahăr. Alimente interzise:"
                ),
                "evidence_ids": [],
            }],
            "uz_extern": [],
            "alte_recomandari": [],
            "atentionari": [],
        }
        combined_report = main._recommendation_text(combined_sections, {})

        self.assertIn("• Alimente recomandate: hrean, țelină.", combined_report)
        self.assertIn("• Alimente nerecomandate: zahăr.", combined_report)
        self.assertIn("• Alimente total interzise: -", combined_report)
        self.assertNotIn("  • Alimente recomandate:", combined_report)

        prefixed_sections = {
            "uz_intern": [],
            "nutritie": [{
                "text": (
                    "**[ALTE]**: probiotic. [RECOMANDAT]: hrean, țelină. "
                    "**[RETETA]**: supă ușoară. **[RETETA]**: ceai de ghimbir. "
                    "[NERECOMANDAT]: zahăr. [INTERZIS]: -"
                ),
                "evidence_ids": [],
            }],
            "uz_extern": [],
            "alte_recomandari": [],
            "atentionari": [],
        }
        prefixed_report = main._recommendation_text(prefixed_sections, {})

        self.assertLess(prefixed_report.index("• Rețete culinare"), prefixed_report.index("• Alimente recomandate"))
        self.assertIn("    - supă ușoară.", prefixed_report)
        self.assertIn("    - ceai de ghimbir.", prefixed_report)
        self.assertIn("• Alimente nerecomandate: zahăr.", prefixed_report)
        self.assertIn("• Alte recomandări: probiotic.", prefixed_report)

    # Verify that compaction logs both original and shortened fragment metadata.
    def test_compaction_logs_fragments_before_and_after_with_removed_chars(self):
        client = XAIClient(settings)
        evidence = {
            "E1": {"source": "documents/plan-a.md:1-10", "text": "A" * 700},
            "E2": {"source": "documents/plan-b.md:20-30", "text": "B" * 700},
        }

        with patch.object(ai_module, "MAX_CONTEXT_CHARS", 500), self.assertLogs(
            "naturist.ai", level="INFO"
        ) as captured:
            entries = client._evidence_entries(evidence)
        client.close()

        output = "\n".join(captured.output)
        self.assertEqual(len(entries), 2)
        self.assertIn("fragments_before_compaction count=2", output)
        self.assertIn("fragments_sent_to_ai count=2", output)
        self.assertIn('documents_count=2', output)
        self.assertIn("source=documents/plan-a.md", output)
        self.assertIn("source=documents/plan-b.md", output)
        self.assertIn('"original_text_chars": 700', output)
        self.assertIn('"compaction_removed_chars":', output)
        self.assertLess(sum(len(entry["text"]) for entry in entries), 1400)

    # Verify the Responses API payload and ensure only one HTTP request is sent.
    def test_responses_api_sends_exactly_one_http_request(self):
        with patch.dict(os.environ, {"GROK_API_KEY_MED": "synthetic-test-key"}):
            client = XAIClient(settings)
            calls = []

            # Capture the outgoing request and return a valid synthetic response.
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

    # Verify long consultation context is split without losing its final marker.
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

    # Verify retrieval preserves both reflection and treatment-plan flu fragments.
    def test_flu_query_retrieves_reflection_fragment_from_internal_dictionary(self):
        profile = HealthProfile()
        profile.set_health_problem("vreau recomandari naturiste pentru gripa")
        session = type("SyntheticSession", (), {"profile": profile})()
        evidence = Retriever(settings.index_dir, settings.documents_dir).collect(session)

        self.assertEqual(_meaningful_words(profile.health_problem), {"gripa"})
        self.assertLessEqual(len(evidence), 2000)
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

    # Verify that one submitted health answer triggers report generation and download.
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

    # Verify generated download links include the configured public Gradio prefix.
    def test_public_report_link_uses_gradio_root_path(self):
        sid = "C" * 43
        request = FakeRequest(sid, "tab-public")
        session = main.store.get(sid, "tab-public", create=True)
        session.report_id = "report-1"
        with patch.dict(os.environ, {"GRADIO_ROOT_PATH": "/medicina"}):
            link = main._download_html(session)
        self.assertIn('/medicina/api/reports/tab-public/report-1', link)
        main.store.delete(sid, "tab-public")

    # Verify PDF pagination, Romanian characters, citations, and bibliography links.
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

    # Verify sessions do not retain unsupported attachment state.
    def test_session_store_has_no_attachment_state(self):
        store = SessionStore(Path(tempfile.mkdtemp()), 60, 120)
        session = store.get("synthetic-cookie", "synthetic-tab", create=True)
        self.assertFalse(hasattr(session, "documents"))
        store.delete("synthetic-cookie", "synthetic-tab")


if __name__ == "__main__":
    unittest.main()
