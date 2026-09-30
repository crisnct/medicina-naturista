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
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle

from medicina_naturista.ai.categories import CategoryNode, CategoryTree
from medicina_naturista.ai.embedding_model import _normalize_fastembed_metadata
from medicina_naturista.ai.search import MAX_SCORE
from medicina_naturista.web import handlers, main
from medicina_naturista.reporting import pdf as reports_module
from medicina_naturista.ai.client import GENERATE_REPORT_SYSTEM_PROMPT_PATH, XAIClient
from medicina_naturista.config import settings
from medicina_naturista.core.models import HEALTH_PROBLEM_QUESTION, HealthProfile
from medicina_naturista.reporting.pdf import SECTION_PRESENTATION, create_pdf, format_recommendation, report_title
from medicina_naturista.ai import conditions as conditions_module
from medicina_naturista.ai.conditions import ConditionDictionary, parse_conditions
from medicina_naturista.ai.retrieval import Retriever, _meaningful_words, consultation_query
from medicina_naturista.core.sessions import SessionStore


# Build the request headers a real browser tab would send: the session
# cookie plus the client-generated X-Tab-Id header (see TAB_ID_RE in
# web/main.py — the replacement for Gradio's own request.session_hash).
def _headers(sid: str, tab: str, owner: bool = False) -> dict:
    cookie = f"{main.COOKIE}={sid}"
    if owner:
        cookie += f"; {main.OWNER_COOKIE}={main._owner_token()}"
    return {"Cookie": cookie, "X-Tab-Id": tab}


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
                "score": 0.0167,
                "relevance_percent": 51.0,
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


def _by_kind(messages: list[dict], kind: str) -> dict:
    return next(message for message in messages if message["kind"] == kind)


# Drive the two-phase send flow the same way the frontend does: POST
# /api/messages (fast echo + notice/rejection), then POST /api/search when
# the first call says a search should follow. Returns the combined messages
# from both calls, matching what the old single combined endpoint returned.
def _send(client: TestClient, sid: str, tab: str, message: str, categories: list[str] | None = None) -> list[dict]:
    response = client.post(
        "/api/messages", json={"message": message, "categories": categories or []}, headers=_headers(sid, tab)
    )
    body = response.json()
    messages = list(body["messages"])
    if body["startSearch"]:
        messages += client.post("/api/search", headers=_headers(sid, tab)).json()["messages"]
    return messages


class WebTests(unittest.TestCase):
    def setUp(self):
        owner_key = patch.dict(os.environ, {"OWNER_KEY": "synthetic-owner-key"})
        owner_key.start()
        self.addCleanup(owner_key.stop)
        # Module-level rate limiting state (see web/main.py's rate_events)
        # would otherwise accumulate across tests sharing one TestClient IP.
        main.rate_events.clear()
        self.client = TestClient(main.app, base_url="https://testserver")
        self.addCleanup(self.client.close)

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

    # Verify a later problem fully replaces the active retrieval/report context.
    def test_profile_replaces_previous_health_problem_context(self):
        profile = HealthProfile()
        profile.set_health_problem("Gripă și răceală")
        profile.add_transcript("user", "Gripă și răceală")
        profile.add_health_context("Simptome de trei zile")

        profile.replace_health_problem("Migrenă")

        self.assertEqual(profile.health_problem, "Migrenă")
        self.assertEqual(profile.health_context, ["Migrenă"])
        self.assertEqual(profile.transcript, [{"role": "user", "content": "Migrenă"}])

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
            "Remedii naturiste pentru gripă și răceală",
        )
        self.assertEqual(
            report_title({"health_problem": "răceală, gripă"}),
            "Remedii naturiste pentru răceală",
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

    # Verify each section is ordered by the best relevance_percent among an item's fragments.
    def test_report_orders_every_section_by_max_relevance_percent(self):
        evidence = {
            "C1": {"source": "documents/a.md:1-2", "text": "A", "relevance_percent": 35.0},
            "C2": {"source": "documents/b.md:1-2", "text": "B", "relevance_percent": 90.0},
            "C3": {"source": "documents/c.md:1-2", "text": "C", "relevance_percent": 30.0},
        }
        sections = {
            "uz_intern": [
                {"text": "Multe surse slabe", "evidence_ids": ["C1", "C3"]},
                {"text": "O sursa puternica", "evidence_ids": ["C2"]},
            ],
            "nutritie": [
                {"text": "Slab", "evidence_ids": ["C1"]},
                {"text": "Puternic", "evidence_ids": ["C1", "C2"]},
            ],
        }

        report = handlers._recommendation_text(sections, evidence)

        self.assertLess(report.index("O sursa puternica"), report.index("Multe surse slabe"))
        self.assertLess(report.index("Puternic"), report.index("Slab"))

    # Verify ties on max relevance fall back to source count, then original order; unsourced last.
    def test_relevance_ties_use_source_count_then_original_order(self):
        evidence = {
            "C1": {"source": "documents/a.md:1-2", "text": "A", "relevance_percent": 80.0},
            "C2": {"source": "documents/b.md:1-2", "text": "B", "relevance_percent": 40.0},
        }
        sections = {
            "uz_intern": [
                {"text": "fara sursa", "evidence_ids": []},
                {"text": "id necunoscut", "evidence_ids": ["UNKNOWN"]},
                {"text": "o sursa", "evidence_ids": ["C1"]},
                {"text": "doua surse", "evidence_ids": ["C1", "C2"]},
                {"text": "repetat", "evidence_ids": ["C1"]},
            ],
        }

        ordered = reports_module.sort_sections_by_relevance(sections, evidence)

        self.assertEqual(
            [item["text"] for item in ordered["uz_intern"]],
            ["doua surse", "o sursa", "repetat", "fara sursa", "id necunoscut"],
        )

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

        report = handlers._recommendation_text(sections, {})

        labels = [
            "**• Rețete culinare:**",
            "**• Alimente recomandate:**",
            "**• Alimente nerecomandate:**",
            "**• Alimente total interzise:**",
            "**• Alte recomandări:**",
        ]
        self.assertEqual(labels, sorted(labels, key=report.index))
        self.assertLess(report.index("    - Salată de hrean"), report.index("    - Supă ușoară cu țelină"))
        self.assertLess(report.index("    - Supă ușoară cu țelină"), report.index("    - Ceai de ghimbir"))
        self.assertNotIn("• Rețete culinare:\n    - Rețete culinare", report)

    # The AI request applies no context budget of its own: the budget was applied
    # by rank() when the fragments were selected (see ai/search.py), so the
    # patient sees exactly the fragments the request carries. It sends every
    # fragment it is given, best score first.
    def test_ai_request_sends_every_fragment_it_is_given_best_score_first(self):
        evidence = {
            "E2": {"source": "documents/plan-b.md:20-30", "text": "B" * 300, "score": 0.0100},
            "E1": {"source": "documents/plan-a.md:1-10", "text": "A" * 300, "score": 0.0500},
        }

        client = XAIClient(settings)
        self.assertEqual([entry["id"] for entry in client._evidence_entries(evidence)], ["E1", "E2"])
        client.close()

    # Verify a fragment with no serialized-length budget problem is returned
    # unmodified and in relevance-score order (highest first), independent of
    # the evidence dict's own insertion order.
    def test_evidence_entries_orders_by_score(self):
        client = XAIClient(settings)
        evidence = {
            "E_low": {"source": "documents/plan-a.md:1-5", "text": "scor mic", "score": 0.0100},
            "E_high": {"source": "documents/plan-b.md:1-5", "text": "scor mare", "score": 0.0500},
        }

        entries = client._evidence_entries(evidence)
        client.close()

        self.assertEqual([entry["id"] for entry in entries], ["E_high", "E_low"])

    # Verify the Responses API payload and ensure only one HTTP request is sent.
    def test_responses_api_sends_exactly_one_http_request(self):
        with patch.dict(os.environ, {"X_API_KEY": "synthetic-test-key"}):
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

    # Verify conversation history (transcript, health_context) is excluded from
    # search queries — only the health problem itself should drive retrieval.
    def test_consultation_query_ignores_conversation_history(self):
        profile = HealthProfile(health_problem="durere articulară")
        profile.add_transcript("assistant", HEALTH_PROBLEM_QUESTION)
        profile.add_transcript("user", "Durere de trei zile")
        marker = "FINAL-CONTEXT"
        profile.add_health_context(("simptom repetat " * 100) + marker)
        query = consultation_query(profile)

        self.assertEqual(query, "durere articulară")
        self.assertNotIn(HEALTH_PROBLEM_QUESTION, query)
        self.assertNotIn(marker, query)

    # --- Category selection -------------------------------------------------

    # Verify GET /api/session creates a session and asks the health-problem question.
    def test_get_session_creates_welcome_and_question(self):
        sid, tab = "A" * 43, "tab-session01"
        response = self.client.get("/api/session", headers=_headers(sid, tab))
        self.assertEqual(response.status_code, 200)
        history = response.json()["history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(
            history[0],
            {"role": "assistant", "kind": "text", "content": f"{main.WELCOME}\n\n{HEALTH_PROBLEM_QUESTION}"},
        )
        main.store.delete(sid, tab)

    # Verify a request with a missing or malformed X-Tab-Id header is rejected,
    # rather than silently falling back to some other identity.
    def test_missing_or_malformed_tab_id_is_rejected(self):
        sid = "A" * 43
        response = self.client.get("/api/session", headers={"Cookie": f"{main.COOKIE}={sid}"})
        self.assertEqual(response.status_code, 400)
        response = self.client.get("/api/session", headers={"Cookie": f"{main.COOKIE}={sid}", "X-Tab-Id": "x"})
        self.assertEqual(response.status_code, 400)

    # Verify the "Caut rapid în cele N documente" notice reflects the
    # documents covered by the selected categories, not the whole corpus —
    # summed from own_documents (never total_documents, which would
    # double-count a folder together with its own subfolders).
    def test_report_started_message_counts_only_selected_categories(self):
        class RetrieverWithCategories:
            category_tree = CategoryTree(
                root_id="",
                nodes={
                    "": CategoryNode(id="", label="(fără categorie)", parent=None, children=("Cancer", "Centrul"), own_documents=0, total_documents=15),
                    "Cancer": CategoryNode(id="Cancer", label="Cancer", parent="", children=(), own_documents=4, total_documents=4),
                    "Centrul": CategoryNode(id="Centrul", label="Centrul", parent="", children=("Centrul/Anatomie",), own_documents=0, total_documents=11),
                    "Centrul/Anatomie": CategoryNode(id="Centrul/Anatomie", label="Anatomie", parent="Centrul", children=(), own_documents=11, total_documents=11),
                },
            )
            document_count = 15

            def collect(self, session):
                return {}

        sid, tab = "H" * 43, "tab-doccount1"
        with patch.object(main, "retriever", RetrieverWithCategories()):
            self.client.get("/api/session", headers=_headers(sid, tab))
            messages = _send(self.client, sid, tab, "Gripă", ["Cancer"])
            notice = next(m for m in messages if "Caut rapid" in m.get("content", ""))
            self.assertIn("Caut rapid în cele 4 documente", notice["content"])

            messages = _send(self.client, sid, tab, "Migrenă", ["Cancer", "Centrul/Anatomie"])
            notice = next(m for m in messages if "Caut rapid" in m.get("content", ""))
            self.assertIn("Caut rapid în cele 15 documente", notice["content"])

            # An id the tree doesn't know (stale selection) contributes nothing.
            messages = _send(self.client, sid, tab, "Alergie", ["necunoscuta"])
            notice = next(m for m in messages if "Caut rapid" in m.get("content", ""))
            self.assertIn("Caut rapid în cele 0 documente", notice["content"])
        main.store.delete(sid, tab)

    # A health problem recognised in the condition dictionary gets a chat
    # notice naming the condition and listing ALL its synonyms (Romanian and
    # English); an unrecognised one gets no notice at all.
    def test_condition_identified_message_lists_every_synonym(self):
        dictionary = ConditionDictionary(parse_conditions(
            "Artrita gutoasa,guta articulara,artrita urica,gout\nAcnee rozacee,rozacee,cuperoza,rosacea\n"
        ))
        with patch.object(conditions_module, "load_dictionary", return_value=dictionary):
            message = main._condition_identified_message("gout")
            self.assertEqual(message["role"], "assistant")
            self.assertEqual(
                message["content"],
                "✅ Am identificat afecțiunea: **Artrita gutoasa**. "
                "O caut și după denumirile: guta articulara, artrita urica, gout.",
            )
            self.assertIsNone(main._condition_identified_message("durere de cap"))

    def test_condition_identified_message_names_both_conditions_when_two_match(self):
        dictionary = ConditionDictionary(parse_conditions("Artrita,arthritis\nArtroza,osteoarthritis\n"))
        with patch.object(conditions_module, "load_dictionary", return_value=dictionary):
            content = main._condition_identified_message("artrita, artroza")["content"]

        self.assertIn("**Artrita**", content)
        self.assertIn("**Artroza**", content)
        self.assertEqual(content.count("\n"), 1)

    def test_condition_without_synonyms_only_names_the_condition(self):
        dictionary = ConditionDictionary(parse_conditions("Acalazie\n"))
        with patch.object(conditions_module, "load_dictionary", return_value=dictionary):
            content = main._condition_identified_message("acalazie")["content"]

        self.assertEqual(content, "✅ Am identificat afecțiunea: **Acalazie**.")

    def test_identified_condition_notice_precedes_the_searching_notice(self):
        class Empty:
            category_tree = None
            document_count = 3

            def collect(self, session):
                return {}

        dictionary = ConditionDictionary(parse_conditions("Artrita gutoasa,guta articulara,gout\n"))
        sid, tab = "J" * 43, "tab-condition1"
        with patch.object(main, "retriever", Empty()), patch.object(conditions_module, "load_dictionary", return_value=dictionary):
            self.client.get("/api/session", headers=_headers(sid, tab))
            messages = self.client.post(
                "/api/messages", json={"message": "gout", "categories": []}, headers=_headers(sid, tab)
            ).json()["messages"]
            contents = [m.get("content", "") for m in messages]
            searching = next(i for i, c in enumerate(contents) if "Caut rapid" in c)
            self.assertIn("**Artrita gutoasa**", contents[searching - 1])
            self.assertIn("guta articulara, gout", contents[searching - 1])

            messages = self.client.post(
                "/api/messages", json={"message": "durere de cap", "categories": []}, headers=_headers(sid, tab)
            ).json()["messages"]
            self.assertFalse(any("Am identificat" in m.get("content", "") for m in messages))
        main.store.delete(sid, tab)

    # An index with no category tree falls back to the whole-corpus count,
    # exactly like before category filtering existed — regardless of what
    # (if anything) is in the selection.
    def test_report_started_message_falls_back_to_total_without_a_category_tree(self):
        class RetrieverWithoutCategories:
            category_tree = None
            document_count = 42

        with patch.object(main, "retriever", RetrieverWithoutCategories()):
            self.assertEqual(main._document_count_for_categories(set()), 42)
            self.assertEqual(main._document_count_for_categories({"anything"}), 42)

    # Verify searching with nothing selected is refused with an explanatory
    # message, and never reaches Retriever.collect() — only when the loaded
    # index actually has a category tree to select from.
    def test_messages_rejects_empty_category_selection_when_tree_exists(self):
        sid, tab = "F" * 43, "tab-nocateg01"

        class RetrieverWithCategories:
            category_tree = CategoryTree(
                root_id="",
                nodes={
                    "": CategoryNode(id="", label="(fără categorie)", parent=None, children=("Cancer",), own_documents=0, total_documents=1),
                    "Cancer": CategoryNode(id="Cancer", label="Cancer", parent="", children=(), own_documents=1, total_documents=1),
                },
            )
            document_count = 1

            def collect(self, session):
                raise AssertionError("collect() must not run with nothing selected")

        with patch.object(main, "retriever", RetrieverWithCategories()):
            self.client.get("/api/session", headers=_headers(sid, tab))
            messages = _send(self.client, sid, tab, "Gripă", [])
        self.assertEqual(messages[-1]["content"], main.NO_CATEGORY_SELECTED_MESSAGE)
        main.store.delete(sid, tab)

    # An index with no category tree at all never enforces a selection —
    # collect() runs exactly as it always has.
    def test_messages_allows_empty_selection_without_a_category_tree(self):
        sid, tab = "G" * 43, "tab-notree001"
        with patch.object(main, "retriever", FakeRetriever()):
            self.client.get("/api/session", headers=_headers(sid, tab))
            messages = _send(self.client, sid, tab, "Gripă", [])
        self.assertNotEqual(messages[-1].get("content"), main.NO_CATEGORY_SELECTED_MESSAGE)
        main.store.delete(sid, tab)

    # --- Fragment message building (pure function, no HTTP round trip needed) --

    # Verify every fragment carries the same relevance measure (its raw
    # "score" field, written by Retriever.collect() from rank()'s score); the message sorts by that raw score, descending — no separate
    # section or ordering rule for any subset of fragments. Each fragment
    # also carries a matchLabel derived from found_by_lexical.
    def test_fragments_message_sorts_by_relevance_score(self):
        evidence = {
            "C1": {
                "source": "documents/doc-a.md:1-5",
                "text": "Scor mic",
                "score": MAX_SCORE * 0.1,
                "relevance_percent": 10.0,
                "found_by_lexical": True,
            },
            "C2": {
                "source": "documents/doc-z.md:10-15",
                "text": "Scor mediu z",
                "score": MAX_SCORE * 0.5,
                "relevance_percent": 50.0,
                "found_by_lexical": False,
            },
            "C3": {
                "source": "documents/doc-a.md:20-25",
                "text": "Scor mare",
                "score": MAX_SCORE,
                "relevance_percent": 100.0,
                "found_by_lexical": True,
                "condition_in_title": True,
            },
            "C4": {
                "source": "documents/doc-b.md:1-5",
                "text": "Scor mediu b",
                "score": MAX_SCORE * 0.5,  # tied with C2
                "relevance_percent": 50.0,
                "found_by_lexical": True,
            },
        }

        message = handlers._fragments_message("search-1", evidence)

        self.assertEqual(message["fragmentsCount"], 4)
        self.assertEqual(message["documentsCount"], 3)
        texts_in_order = [fragment["text"] for fragment in message["fragments"]]
        self.assertEqual(texts_in_order, ["Scor mare", "Scor mediu z", "Scor mediu b", "Scor mic"])
        self.assertEqual(message["fragments"][0]["relevancePercent"], 100.0)
        self.assertEqual(message["fragments"][0]["matchLabel"], "Găsire Lexicală")
        self.assertEqual(message["fragments"][0]["conditionMatch"], "title")
        self.assertEqual(message["fragments"][1]["matchLabel"], "")
        self.assertIsNone(message["fragments"][1]["conditionMatch"])

    # A fragment missing found_by_lexical (older cached evidence, or a caller
    # that doesn't set it) must still render — just with an empty matchLabel.
    def test_fragments_message_omits_match_label_when_absent(self):
        evidence = {
            "C1": {
                "source": "documents/doc-a.md:1-5",
                "text": "Fragment fără found_by_lexical",
                "score": MAX_SCORE,
                "relevance_percent": 100.0,
            },
        }

        message = handlers._fragments_message("search-1", evidence)

        self.assertEqual(message["fragments"][0]["matchLabel"], "")
        self.assertEqual(message["fragments"][0]["relevancePercent"], 100.0)

    # Verify the message carries the backend-computed relevance_percent as is,
    # and null for a fragment that carries none.
    def test_fragments_message_shows_backend_relevance_percent(self):
        evidence = {
            "C1": {"source": "documents/doc-a.md:1-5", "text": "Cu procent", "score": 0.02, "relevance_percent": 61.6},
            "C2": {"source": "documents/doc-b.md:1-5", "text": "Fără procent", "score": 0.01},
        }

        message = handlers._fragments_message("search-1", evidence)

        self.assertEqual(message["fragments"][0]["relevancePercent"], 61.6)
        self.assertIsNone(message["fragments"][1]["relevancePercent"])

    # --- Full chat flow, owner gating and multi-report downloads -----------

    # Verify one submitted health answer triggers retrieval, is gated behind
    # the owner cookie for generation, and produces a downloadable, tab-scoped PDF.
    def test_full_chat_flow_generates_report_and_gates_generation_by_owner(self):
        sid_a, tab_a = "A" * 43, "tab-flow-a001"
        sid_b, tab_b = "B" * 43, "tab-flow-b001"
        FakeAI.generate_calls = 0
        FakeAI.report_profile = None

        with patch.object(main, "send_report", return_value="email_sent") as send_report_mock, patch.object(
            main, "ai", FakeAI()
        ), patch.object(main, "retriever", FakeRetriever()):
            session_a = self.client.get("/api/session", headers=_headers(sid_a, tab_a)).json()
            self.assertTrue(session_a["history"][-1]["content"].endswith(HEALTH_PROBLEM_QUESTION))
            self.client.get("/api/session", headers=_headers(sid_b, tab_b))

            messages = _send(self.client, sid_a, tab_a, "Gripă și răceală", [])
            self.assertTrue(any("Caut rapid în cele" in m.get("content", "") for m in messages))
            self.assertEqual(FakeAI.generate_calls, 0, "retrieval must not call the AI")

            fragments = _by_kind(messages, "fragments")
            generate = _by_kind(messages, "generate")
            self.assertEqual(fragments["fragmentsCount"], 1)
            self.assertEqual(fragments["documentsCount"], 1)
            self.assertIn("Informație locală relevantă.", fragments["fragments"][0]["text"])
            self.assertFalse(generate["busy"])
            search_id = generate["searchId"]
            session = main.store.get(sid_a, tab_a)
            self.assertEqual(
                session.searches[search_id].evidence,
                {
                    "C1": {
                        "source": "documents/plan.md:1-5",
                        "text": "Informație locală relevantă.",
                        "score": 0.0167,
                        "relevance_percent": 51.0,
                    }
                },
            )

            # A non-owner visitor is refused, and the button stays clickable.
            resp = self.client.post(f"/api/searches/{search_id}/generate", headers=_headers(sid_a, tab_a))
            body = resp.json()
            self.assertEqual(body["ownerNotice"], main.OWNER_ONLY_MESSAGE)
            self.assertEqual(body["messages"], [])
            self.assertEqual(FakeAI.generate_calls, 0)

            # The owner successfully generates the report.
            resp = self.client.post(f"/api/searches/{search_id}/generate", headers=_headers(sid_a, tab_a, owner=True))
            body = resp.json()
            self.assertIsNone(body["ownerNotice"])
            self.assertEqual(FakeAI.generate_calls, 1)
            self.assertEqual(main.store.get(sid_a, tab_a).searches, {})
            send_report_mock.assert_not_called()
            recommendation = _by_kind(body["messages"], "text")
            download = _by_kind(body["messages"], "download")
            self.assertIn("Uz intern", recommendation["content"])
            self.assertIn("[1]", recommendation["content"])
            self.assertIn("Bibliografie", recommendation["content"])
            self.assertIn("1 - plan.md:1-5", recommendation["content"])
            self.assertTrue(download["url"].startswith(f"/api/reports/{tab_a}/"))

            # The report downloads for tab A's cookie only.
            pdf_response = self.client.get(download["url"], headers={"Cookie": f"{main.COOKIE}={sid_a}"})
            self.assertEqual(pdf_response.status_code, 200)
            self.assertTrue(pdf_response.content.startswith(b"%PDF-"))
            other_tab_response = self.client.get(download["url"], headers={"Cookie": f"{main.COOKIE}={sid_b}"})
            self.assertEqual(other_tab_response.status_code, 404)

            # Emailing the finished report.
            reply = _send(self.client, sid_a, tab_a, "prieten@example.com", [])[-1]
            self.assertIn("prieten@example.com", reply["content"])
            send_report_mock.assert_called_once()
            self.assertEqual(send_report_mock.call_args.args[0], "Gripă și răceală")
            self.assertTrue(send_report_mock.call_args.args[1].startswith(b"%PDF-"))
            self.assertTrue(send_report_mock.call_args.args[2].endswith(".pdf"))
            self.assertEqual(send_report_mock.call_args.args[3], "prieten@example.com")
            self.assertEqual(FakeAI.report_profile["health_problem"], "Gripă și răceală")

            content = "\n".join(
                page.extract_text() for page in PdfReader(io.BytesIO(pdf_response.content)).pages
            )
            self.assertIn("Remedii naturiste", content)
            self.assertIn("Gripă și răceală", " ".join(content.split()))

            end_resp = self.client.post("/api/session/end", headers=_headers(sid_a, tab_a))
            self.assertIn("Sesiunea a fost închisă", end_resp.json()["messages"][0]["content"])
            self.assertIsNone(main.store.get(sid_a, tab_a))
            self.assertIsNotNone(main.store.get(sid_b, tab_b))
            main.store.delete(sid_b, tab_b)

    # Verify each search keeps its own "generate" section and PDF, and that
    # several finished reports stay independently downloadable in one session.
    def test_each_search_keeps_its_own_generate_section_and_report(self):
        sid, tab = "C" * 43, "tab-multi-001"
        FakeAI.generate_calls = 0
        FakeAI.report_profile = None

        with patch.object(main, "send_report", return_value="email_sent"), patch.object(
            main, "ai", FakeAI()
        ), patch.object(main, "retriever", FakeRetriever()):
            self.client.get("/api/session", headers=_headers(sid, tab))
            first_messages = _send(self.client, sid, tab, "Gripă și răceală", [])
            first_search_id = _by_kind(first_messages, "generate")["searchId"]

            second_messages = _send(self.client, sid, tab, "Migrenă", [])
            second_search_id = _by_kind(second_messages, "generate")["searchId"]
            self.assertNotEqual(first_search_id, second_search_id)

            session = main.store.get(sid, tab)
            self.assertEqual(session.profile.health_problem, "Migrenă")
            self.assertEqual(session.searches[first_search_id].profile["health_problem"], "Gripă și răceală")

            # Generating the FIRST search uses its own problem, even though the chat moved on.
            first_result = self.client.post(
                f"/api/searches/{first_search_id}/generate", headers=_headers(sid, tab, owner=True)
            ).json()
            self.assertEqual(FakeAI.report_profile["health_problem"], "Gripă și răceală")
            first_report_id = _by_kind(first_result["messages"], "download")["reportId"]

            second_result = self.client.post(
                f"/api/searches/{second_search_id}/generate", headers=_headers(sid, tab, owner=True)
            ).json()
            self.assertEqual(FakeAI.generate_calls, 2)
            self.assertEqual(FakeAI.report_profile["health_problem"], "Migrenă")
            second_report_id = _by_kind(second_result["messages"], "download")["reportId"]
            self.assertNotEqual(first_report_id, second_report_id)

            # Both PDFs stay downloadable, each for its own problem.
            self.assertEqual(len(session.reports), 2)
            first_text = " ".join(
                page.extract_text() for page in PdfReader(io.BytesIO(session.reports[first_report_id].data)).pages
            )
            self.assertIn("Gripă și răceală", " ".join(first_text.split()))
            self.assertNotIn("Migrenă", " ".join(first_text.split()))

        main.store.delete(sid, tab)

    # Verify a Google API failure keeps the report available and tells the user in chat.
    def test_email_failure_keeps_report_available(self):
        sid, tab = "D" * 43, "tab-emailfail1"

        with patch.object(main, "ai", FakeAI()), patch.object(main, "retriever", FakeRetriever()), patch.object(
            main, "send_report", side_effect=OSError("SMTP unavailable")
        ):
            self.client.get("/api/session", headers=_headers(sid, tab))
            messages = _send(self.client, sid, tab, "Gripă și răceală", [])
            search_id = _by_kind(messages, "generate")["searchId"]
            self.client.post(f"/api/searches/{search_id}/generate", headers=_headers(sid, tab, owner=True))
            with self.assertLogs("naturist.web", level="ERROR") as captured:
                reply_messages = _send(self.client, sid, tab, "prieten@example.com", [])

        session = main.store.get(sid, tab)
        self.assertTrue(session.report_bytes.startswith(b"%PDF-"))
        self.assertIn("Nu am putut trimite", reply_messages[-1]["content"])
        self.assertIn("stage=email", "\n".join(captured.output))
        main.store.delete(sid, tab)

    # Verify the download URL honours a reverse-proxy sub-path when configured.
    def test_public_report_link_uses_configured_root_path(self):
        sid, tab = "C" * 43, "tab-public0001"
        session = main.store.get(sid, tab, create=True)
        session.report_id = "report-1"
        with patch.dict(os.environ, {"PUBLIC_ROOT_PATH": "/medicina"}):
            message = handlers._download_message(session)
        self.assertEqual(message["url"], f"/medicina/api/reports/{tab}/report-1")
        self.assertEqual(message["kind"], "download")
        main.store.delete(sid, tab)

    # --- Category tree endpoint ----------------------------------------------

    def test_get_categories_serializes_tree_and_default_selection(self):
        tree = CategoryTree(
            root_id="",
            nodes={
                "": CategoryNode(id="", label="(fără categorie)", parent=None, children=("Cancer",), own_documents=0, total_documents=2),
                "Cancer": CategoryNode(id="Cancer", label="Cancer", parent="", children=(), own_documents=2, total_documents=2),
            },
        )

        class RetrieverWithCategories:
            category_tree = tree

        with patch.object(main, "retriever", RetrieverWithCategories()):
            response = self.client.get("/api/categories")
        body = response.json()
        self.assertEqual(body["defaultSelection"], ["Cancer"])
        self.assertEqual(body["tree"]["id"], "")
        self.assertEqual(body["tree"]["children"][0]["id"], "Cancer")
        self.assertTrue(body["tree"]["children"][0]["isReal"])

    def test_get_categories_returns_null_tree_without_synced_documents(self):
        class RetrieverWithoutCategories:
            category_tree = None

        with patch.object(main, "retriever", RetrieverWithoutCategories()):
            response = self.client.get("/api/categories")
        self.assertEqual(response.json(), {"tree": None, "defaultSelection": []})

    # Verify retrieval against the real, locally configured index/database: the
    # sections titled with the condition come first (P1), the treatment plan is
    # among the evidence, and the evidence fits the context budget.
    def test_flu_query_ranks_titled_sections_first_from_the_real_index(self):
        profile = HealthProfile()
        profile.set_health_problem("vreau recomandari naturiste pentru gripa")
        session = type("SyntheticSession", (), {"profile": profile})()
        retriever = Retriever(settings.documents_dir)
        evidence = retriever.collect(session)

        self.assertEqual(_meaningful_words(profile.health_problem), {"gripa"})
        titled = [item["condition_in_title"] for item in evidence.values()]
        self.assertTrue(any(titled))
        self.assertEqual(titled, sorted(titled, reverse=True))
        self.assertTrue(any(
            "Plan tratament naturist" in item["source"]
            and "Tinctură fructe de soc" in item["text"]
            for item in evidence.values()
        ))
        self.assertLessEqual(sum(len(item["text"]) for item in evidence.values()), settings.max_context_chars)

    # Build synthetic rank() output for one query, as rank() returns every fragment.
    @staticmethod
    def _ranked(chunk_id, path, start, end, fraction, lexical=False, text="fără cuvinte comune"):
        return {
            "chunk_id": chunk_id,
            "score": MAX_SCORE * fraction,
            "found_by_lexical": lexical,
            "condition_in_title": False,
            "condition_in_text": False,
            "source_relative_path": path,
            "line_start": start,
            "line_end": end,
            "heading": "",
            "text": text,
        }

    # Verify every candidate rank() returns becomes evidence — there is no
    # relevance_percent floor any more (removed so a large selected category
    # can no longer make a smaller one's fragments disappear from collect()
    # itself; the only remaining cut is the MAX_CONTEXT_CHARS budget that rank()
    # applies in SQL, tested in test_search.py).
    def test_collect_keeps_every_candidate_regardless_of_relevance_percent(self):
        profile = HealthProfile()
        profile.set_health_problem("gripa")
        session = type("SyntheticSession", (), {"profile": profile})()
        retriever = Retriever(settings.documents_dir)
        # Purely about whether a low score still survives into evidence.
        ranked = [
            self._ranked(1, "a.md", 1, 5, 0.50),
            self._ranked(2, "b.md", 1, 5, 0.05),  # would have failed the old default 10% threshold
            self._ranked(3, "c.md", 1, 5, 0.90, lexical=True),
            self._ranked(4, "d.md", 1, 5, 0.001, lexical=True),  # near-zero score, still kept
        ]

        with patch("medicina_naturista.ai.retrieval.rank", return_value=ranked):
            evidence = retriever.collect(session)

        self.assertEqual(set(evidence), {"C1", "C2", "C3", "C4"})
        self.assertAlmostEqual(evidence["C1"]["relevance_percent"], 50.0)
        self.assertAlmostEqual(evidence["C2"]["relevance_percent"], 5.0)
        self.assertAlmostEqual(evidence["C3"]["relevance_percent"], 90.0)
        self.assertAlmostEqual(evidence["C4"]["relevance_percent"], 0.1)
        self.assertFalse(evidence["C1"]["found_by_lexical"])
        self.assertTrue(evidence["C3"]["found_by_lexical"])

    # Verify session.selected_categories reaches rank() as category_ids,
    # restricted to ids the loaded category tree actually knows about.
    def test_collect_passes_known_selected_categories_to_rank(self):
        profile = HealthProfile()
        profile.set_health_problem("gripa")
        session = type("SyntheticSession", (), {"profile": profile, "selected_categories": {"Cancer", "necunoscuta"}})()
        retriever = Retriever(settings.documents_dir)
        retriever._known_category_ids = frozenset({"Cancer", "Sex"})
        captured_kwargs = []

        def fake_rank(_query, **kwargs):
            captured_kwargs.append(kwargs.get("category_ids"))
            return []

        with patch("medicina_naturista.ai.retrieval.rank", side_effect=fake_rank):
            retriever.collect(session)

        self.assertTrue(captured_kwargs, "rank() must be called at least once")
        # The unknown id is dropped; only the known one is forwarded.
        self.assertTrue(all(value == frozenset({"Cancer"}) for value in captured_kwargs))

    # An empty selection, or a selection with nothing the tree recognizes,
    # must mean "no filter" (None) — the same as never opening the panel.
    def test_collect_passes_none_when_no_known_category_is_selected(self):
        profile = HealthProfile()
        profile.set_health_problem("gripa")
        session = type("SyntheticSession", (), {"profile": profile, "selected_categories": {"necunoscuta"}})()
        retriever = Retriever(settings.documents_dir)
        retriever._known_category_ids = frozenset({"Cancer", "Sex"})
        captured_kwargs = []

        def fake_rank(_query, **kwargs):
            captured_kwargs.append(kwargs.get("category_ids"))
            return []

        with patch("medicina_naturista.ai.retrieval.rank", side_effect=fake_rank):
            retriever.collect(session)

        self.assertTrue(captured_kwargs, "rank() must be called at least once")
        self.assertTrue(all(value is None for value in captured_kwargs))

    # A caller/test double without a selected_categories attribute at all
    # (like the SyntheticSession objects used throughout this file) must not
    # crash collect() — it is treated the same as an empty selection.
    def test_collect_tolerates_missing_selected_categories_attribute(self):
        profile = HealthProfile()
        profile.set_health_problem("gripa")
        session = type("SyntheticSession", (), {"profile": profile})()
        retriever = Retriever(settings.documents_dir)
        retriever._known_category_ids = frozenset({"Cancer"})

        with patch("medicina_naturista.ai.retrieval.rank", return_value=[]):
            evidence = retriever.collect(session)  # must not raise

        self.assertEqual(evidence, {})

    # Verify long evidence sent to the AI retains its semantic section heading.
    def test_retrieval_context_prefixes_heading_for_long_chunks(self):
        retriever = object.__new__(Retriever)
        retriever.documents_dir = settings.documents_dir
        result = {
            "source_relative_path": "missing.md",
            "line_start": 1,
            "line_end": 1,
            "heading": "Gripă > Uz intern",
            "text": "Conținut medical. " * 50,
        }

        context = retriever._context(result)

        self.assertTrue(context.startswith("Secțiune: Gripă > Uz intern\n\n"))
        self.assertIn(result["text"], context)

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
        reader = PdfReader(io.BytesIO(pdf))
        pages = reader.pages
        self.assertGreater(len(pages), 1)
        text = "\n".join(page.extract_text() for page in pages)
        self.assertIn("ă â î ș ț", text)
        self.assertIn("de la dr. Cuișor", text)
        self.assertIn("Surse 1-2", text)
        self.assertNotIn("Cuprins", text)
        self.assertIn("Bibliografie", text)
        self.assertIn("1 - test.md:1-3", text)
        self.assertIn("2 - alt-test.md:4-8", text)
        self.assertNotIn("documents/test.md:1-3", text)
        self.assertNotIn("\x00", text)
        self.assertGreaterEqual(len(reader.outline), 6)
        links = [
            annotation.get_object()
            for page in pages
            for annotation in page.get("/Annots", [])
            if annotation.get_object().get("/Subtype") == "/Link"
        ]
        self.assertGreaterEqual(len(links), 2)
        self.assertTrue(all("/Dest" in link for link in links))

    # Verify the PDF uses clean numbered headers and outlined white section cards.
    def test_pdf_section_headers_use_colored_bands_without_symbols(self):
        for presentation in SECTION_PRESENTATION.values():
            self.assertNotIn("symbol", presentation)

        _, bold = reports_module._register_fonts()
        heading = reports_module._section_heading(
            "uz_intern",
            ParagraphStyle(
                "TestSectionHeading",
                fontName=bold,
                fontSize=15,
                leading=20,
                textColor=colors.white,
            ),
        )
        self.assertIn("1. Uz intern", heading.text)
        self.assertNotIn("●", heading.text)

        source = Path(reports_module.__file__).read_text(encoding="utf-8")
        self.assertIn("class CoverPanel", source)
        self.assertIn("visible_height=56 * mm", source)
        self.assertIn("self.canv.setFillColor(colors.white)", source)
        self.assertIn("self.canv.setFillColor(self.border)", source)
        self.assertIn("ORNAMENT_PNG", source)
        self.assertIn("ornament_width = width", source)
        self.assertIn("ornament_height = ornament_width * ORNAMENT_SIZE[1] / ORNAMENT_SIZE[0]", source)
        self.assertNotIn("canvas.roundRect(18 * mm, 15.5 * mm", source)
        self.assertIn('Paragraph("de la dr. Cuișor", styles["NaturalCoverByline"])', source)
        self.assertIn("self.padding = 7", source)
        self.assertIn("story.append(Spacer(1, 6 * mm))", source)
        self.assertIn("Spacer(1, 2.5 * mm)", source)
        self.assertIn("self.bookmark and len(first_content) <= 2", source)
        self.assertIn('bookmark="section-bibliografie"', source)
        self.assertIn('"#52636D",', source)

    # Verify sessions do not retain unsupported attachment state.
    def test_session_store_has_no_attachment_state(self):
        store = SessionStore(Path(tempfile.mkdtemp()), 60, 120)
        session = store.get("synthetic-cookie", "synthetic-tab", create=True)
        self.assertFalse(hasattr(session, "documents"))
        store.delete("synthetic-cookie", "synthetic-tab")


if __name__ == "__main__":
    unittest.main()
