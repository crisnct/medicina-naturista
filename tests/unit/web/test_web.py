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

from medicina_naturista.ai.search import RRF_MAX_SCORE, _normalize_fastembed_metadata
from medicina_naturista.web import handlers, main
from medicina_naturista.reporting import pdf as reports_module
import medicina_naturista.ai.client as ai_module
from medicina_naturista.ai.client import GENERATE_REPORT_SYSTEM_PROMPT_PATH, XAIClient
from medicina_naturista.config import settings
from medicina_naturista.core.models import HEALTH_PROBLEM_QUESTION, HealthProfile
from medicina_naturista.reporting.pdf import SECTION_PRESENTATION, create_pdf, format_recommendation, report_title
from medicina_naturista.ai.retrieval import Retriever, _meaningful_words, consultation_queries
from medicina_naturista.core.sessions import SessionStore


class FakeRequest:
    # Create the minimal request object required by the Gradio callbacks.
    def __init__(self, sid: str, tab: str):
        self.session_hash = tab
        # Test requests come from the owner, the only visitor allowed to generate reports.
        self.headers = {"cookie": f"naturist_sid={sid}; {main.OWNER_COOKIE}={main._owner_token()}"}


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


class WebTests(unittest.TestCase):
    def setUp(self):
        owner_key = patch.dict(os.environ, {"OWNER_KEY": "synthetic-owner-key"})
        owner_key.start()
        self.addCleanup(owner_key.stop)

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

        report = main._recommendation_text(sections, evidence)

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

        report = main._recommendation_text(sections, {})

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

        self.assertIn("**• Alimente recomandate:** hrean, țelină.", combined_report)
        self.assertIn("**• Alimente nerecomandate:** zahăr.", combined_report)
        self.assertIn("**• Alimente total interzise:** -", combined_report)
        self.assertNotIn("  **• Alimente recomandate:**", combined_report)

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

        self.assertLess(
            prefixed_report.index("**• Rețete culinare:**"),
            prefixed_report.index("**• Alimente recomandate:**"),
        )
        self.assertIn("    - supă ușoară.", prefixed_report)
        self.assertIn("    - ceai de ghimbir.", prefixed_report)
        self.assertIn("**• Alimente nerecomandate:** zahăr.", prefixed_report)
        self.assertIn("**• Alte recomandări:** probiotic.", prefixed_report)
        self.assertTrue(main.chatbot.render_markdown)

    # Verify the fragments shown to the patient are exactly those the AI request
    # will carry: fit_evidence_to_context keeps the highest-scored prefix that fits
    # MAX_CONTEXT_CHARS. The budget is applied only there, never in the AI request.
    def test_fit_evidence_to_context_matches_what_is_sent_to_ai(self):
        evidence = {
            "E2": {"source": "documents/plan-b.md:20-30", "text": "B" * 300, "score": 0.0100},
            "E1": {"source": "documents/plan-a.md:1-10", "text": "A" * 300, "score": 0.0500},
        }

        with patch.object(ai_module, "MAX_CONTEXT_CHARS", 500), self.assertLogs(
            "naturist.ai", level="WARNING"
        ) as captured:
            fitted = ai_module.fit_evidence_to_context(evidence)
        self.assertEqual(list(fitted), ["E1"])
        self.assertIn("entries=2->1", "\n".join(captured.output))

        # The AI request applies no budget of its own: it sends every fragment it
        # is given, even with a tiny MAX_CONTEXT_CHARS.
        client = XAIClient(settings)
        with patch.object(ai_module, "MAX_CONTEXT_CHARS", 10):
            self.assertEqual([entry["id"] for entry in client._evidence_entries(fitted)], ["E1"])
            self.assertEqual([entry["id"] for entry in client._evidence_entries(evidence)], ["E1", "E2"])
        client.close()

        # Within budget: the very same evidence object comes back untouched.
        self.assertIs(ai_module.fit_evidence_to_context(evidence), evidence)

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

    # Verify conversation history (transcript, health_context) is excluded from
    # search queries — only the health problem itself should drive retrieval.
    def test_consultation_queries_ignore_conversation_history(self):
        profile = HealthProfile(health_problem="durere articulară")
        profile.add_transcript("assistant", HEALTH_PROBLEM_QUESTION)
        profile.add_transcript("user", "Durere de trei zile")
        marker = "FINAL-CONTEXT"
        profile.add_health_context(("simptom repetat " * 100) + marker)
        queries = consultation_queries(profile)

        self.assertEqual(queries, ["durere articulară"])
        self.assertFalse(any(HEALTH_PROBLEM_QUESTION in query for query in queries))
        self.assertFalse(any(marker in query for query in queries))

    # Verify retrieval preserves both reflection and treatment-plan flu fragments.
    def test_flu_query_retrieves_reflection_fragment_from_internal_dictionary(self):
        profile = HealthProfile()
        profile.set_health_problem("vreau recomandari naturiste pentru gripa")
        session = type("SyntheticSession", (), {"profile": profile})()
        retriever = Retriever(settings.index_dir, settings.documents_dir)
        evidence = retriever.collect(session)

        self.assertEqual(_meaningful_words(profile.health_problem), {"gripa"})
        # Whitespace-normalized: when the raw chunk text is short (< 600 chars,
        # true here), retrieval.py's _context() re-expands it from the source
        # file's own lines (±5/4 lines of surrounding context). That source
        # file carries incidental trailing spaces before some line breaks, so
        # the rebuilt text's line-wrapping doesn't exactly match the chunk's
        # originally stored text. A literal "\n"-exact match is therefore
        # fragile against that formatting artifact — normalize like the
        # source_excerpt comparison below already does.
        reflection = next(
            item for item in evidence.values()
            if "Marele dict" in item["source"]
            and "nevoie de odihnă sau de o pauză" in " ".join(item["text"].split())
        )
        relative_path, line_range = reflection["source"].removeprefix("documents/").rsplit(":", 1)
        line_start, line_end = (int(value) for value in line_range.split("-", 1))
        source_lines = (settings.documents_dir / relative_path).read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
        source_excerpt = "\n".join(source_lines[line_start - 1:line_end])
        self.assertIn("nevoie de odihnă sau de o pauză", " ".join(source_excerpt.split()))
        self.assertTrue(any(
            "Plan tratament naturist" in item["source"]
            and "Tinctură fructe de soc" in item["text"]
            for item in evidence.values()
        ))

    # Build synthetic rank() output for one query, as rank() returns every fragment.
    @staticmethod
    def _ranked(chunk_id, path, start, end, fraction, lexical=False, text="fără cuvinte comune"):
        return {
            "chunk_id": chunk_id,
            "hybrid_score": RRF_MAX_SCORE * fraction,
            "found_by_lexical": lexical,
            "source_relative_path": path,
            "line_start": start,
            "line_end": end,
            "heading": "",
            "text": text,
        }

    # Verify only fragments at or above MIN_RELEVANCE_PERCENT (of RRF_MAX_SCORE)
    # are kept, with no word-overlap or lexical exemption, before neighbours merge.
    def test_collect_keeps_only_fragments_above_relevance_threshold(self):
        profile = HealthProfile()
        profile.set_health_problem("gripa")
        session = type("SyntheticSession", (), {"profile": profile})()
        retriever = Retriever(settings.index_dir, settings.documents_dir)
        retriever.min_relevance_percent = 10
        ranked = [
            self._ranked(1, "a.md", 1, 10, 0.50),                 # kept, shares no word with the query
            self._ranked(2, "a.md", 12, 20, 0.05),                # below threshold, neighbour of 1
            self._ranked(3, "b.md", 1, 5, 0.90, lexical=True),   # kept
            self._ranked(4, "c.md", 1, 5, 0.09, lexical=True),    # lexical match, still below threshold
        ]

        with patch("medicina_naturista.ai.retrieval.rank", return_value=ranked):
            evidence = retriever.collect(session)

        self.assertEqual(set(evidence), {"C1", "C3"})
        # The weak neighbour is not pulled into the group.
        self.assertEqual(evidence["C1"]["source"], "documents/a.md:1-10")
        self.assertAlmostEqual(evidence["C1"]["relevance_percent"], 50.0)
        self.assertAlmostEqual(evidence["C3"]["relevance_percent"], 90.0)
        self.assertFalse(evidence["C1"]["found_by_lexical"])
        self.assertTrue(evidence["C3"]["found_by_lexical"])

    # Verify a fragment exactly at the threshold is kept and one just below is not.
    def test_collect_threshold_is_inclusive(self):
        profile = HealthProfile()
        profile.set_health_problem("gripa")
        session = type("SyntheticSession", (), {"profile": profile})()
        retriever = Retriever(settings.index_dir, settings.documents_dir)
        retriever.min_relevance_percent = 50
        ranked = [
            self._ranked(1, "a.md", 1, 5, 0.5),
            self._ranked(2, "b.md", 1, 5, 0.4999),
        ]

        with patch("medicina_naturista.ai.retrieval.rank", return_value=ranked):
            evidence = retriever.collect(session)

        self.assertEqual(set(evidence), {"C1"})

    # Verify neighbouring fragments of one file (overlapping or at most 5 lines
    # apart) are grouped, while distant fragments and other files stay separate.
    def test_merge_adjacent_groups_neighbours_within_line_gap(self):
        def chunk(path, start, end):
            return {"source_relative_path": path, "line_start": start, "line_end": end, "text": "t"}

        chunks = {
            1: chunk("a.md", 1, 10),
            2: chunk("a.md", 8, 20),    # overlaps 1
            3: chunk("a.md", 25, 30),   # 5 lines after 2 -> still merged
            4: chunk("a.md", 36, 40),   # 6 lines after 3 -> new group
            5: chunk("b.md", 1, 10),    # other file -> own group
        }

        same_percent = {chunk_id: 50.0 for chunk_id in chunks}
        groups = Retriever._merge_adjacent(chunks, same_percent, 9)
        by_members = {tuple(group["members"]): group for group in groups}

        self.assertEqual(set(by_members), {(1, 2, 3), (4,), (5,)})
        merged = by_members[(1, 2, 3)]
        self.assertEqual((merged["path"], merged["start"], merged["end"]), ("a.md", 1, 30))

    # Verify a group only grows while the spread of its relevance percentages
    # (highest - lowest, candidate included) stays strictly below the limit:
    # compared against the whole group, so no drift is possible.
    def test_merge_adjacent_limits_percent_spread_within_group(self):
        def chunk(start):
            return {"source_relative_path": "a.md", "line_start": start, "line_end": start + 4, "text": "t"}

        chunks = {1: chunk(1), 2: chunk(6), 3: chunk(11), 4: chunk(16)}

        # Consecutive gaps are 5, 7 and 8 (all < 9) but 50 -> 30 spans 20 points.
        drift = {1: 50.0, 2: 45.0, 3: 38.0, 4: 30.0}
        groups = Retriever._merge_adjacent(chunks, drift, 9)
        self.assertEqual([group["members"] for group in groups], [[1, 2], [3, 4]])

        # A spread of exactly 9 is not "below 9"; 8.9 is.
        self.assertEqual(
            [group["members"] for group in Retriever._merge_adjacent(chunks, {1: 50.0, 2: 41.0, 3: 41.0, 4: 41.0}, 9)],
            [[1], [2, 3, 4]],
        )
        self.assertEqual(
            [group["members"] for group in Retriever._merge_adjacent(chunks, {1: 50.0, 2: 41.1, 3: 41.1, 4: 41.1}, 9)],
            [[1, 2, 3, 4]],
        )

        # The line-gap rule still applies on top of the percent rule.
        far = {1: chunk(1), 2: chunk(40)}
        groups = Retriever._merge_adjacent(far, {1: 50.0, 2: 50.0}, 9)
        self.assertEqual([group["members"] for group in groups], [[1], [2]])

        # A limit of 0 disables merging altogether.
        groups = Retriever._merge_adjacent(chunks, {1: 50.0, 2: 50.0, 3: 50.0, 4: 50.0}, 0)
        self.assertEqual([group["members"] for group in groups], [[1], [2], [3], [4]])

    # Verify a merged group reads its whole united line range from the source
    # file, and falls back to the members' texts when the file is missing.
    def test_group_context_reads_united_range_or_falls_back_to_member_texts(self):
        retriever = Retriever(settings.index_dir, settings.documents_dir)
        chunks = {
            1: {"text": "primul"},
            2: {"text": "al doilea"},
        }
        with tempfile.TemporaryDirectory() as directory:
            retriever.documents_dir = Path(directory).resolve()
            (retriever.documents_dir / "doc.md").write_text(
                "\n".join(f"linia {number}" for number in range(1, 11)), encoding="utf-8"
            )
            group = {"path": "doc.md", "start": 3, "end": 6, "members": [1, 2]}

            text = retriever._group_context(group, chunks, "Titlu")
            self.assertEqual(text, "Sec\u021biune: Titlu\n\nlinia 3\nlinia 4\nlinia 5\nlinia 6")

            missing = {"path": "lipsa.md", "start": 1, "end": 2, "members": [1, 2]}
            self.assertEqual(retriever._group_context(missing, chunks, ""), "primul\n\nal doilea")

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

    # Verify every fragment carries the same relevance measure (its raw
    # "score" field, written by Retriever.collect() as hybrid_score from
    # rank()); the panel interpolates that raw value onto a 0-100 integer
    # percentage for display ("Scor relevanță: NN%") while sorting the flat
    # list by the raw score itself, descending — no separate section or
    # ordering rule for any subset of fragments. Each fragment also carries
    # a found_by_lexical boolean (from ai/search.py), shown as a Romanian
    # label right after the percentage when true.
    def test_fragments_panel_sorts_by_relevance_score(self):
        evidence = {
            "C1": {
                "source": "documents/doc-a.md:1-5",
                "text": "Scor mic",
                "score": RRF_MAX_SCORE * 0.1,
                "relevance_percent": 10.0,
                "found_by_lexical": True,
            },
            "C2": {
                "source": "documents/doc-z.md:10-15",
                "text": "Scor mediu z",
                "score": RRF_MAX_SCORE * 0.5,
                "relevance_percent": 50.0,
                "found_by_lexical": False,
            },
            "C3": {
                "source": "documents/doc-a.md:20-25",
                "text": "Scor mare",
                "score": RRF_MAX_SCORE,
                "relevance_percent": 100.0,
                "found_by_lexical": True,
            },
            "C4": {
                "source": "documents/doc-b.md:1-5",
                "text": "Scor mediu b",
                "score": RRF_MAX_SCORE * 0.5,  # tied with C2
                "relevance_percent": 50.0,
                "found_by_lexical": True,
            },
        }

        fragments_html = main._fragments_panel_html(evidence)

        # Flat list, no per-document grouping and no separate section for
        # any subset of fragments.
        self.assertIn("fragments-panel-banner", fragments_html)
        self.assertNotIn('class="fragments-panel-doc"', fragments_html)

        position_high_score = fragments_html.index("Scor mare")
        position_mid_z = fragments_html.index("Scor mediu z")
        position_mid_b = fragments_html.index("Scor mediu b")
        position_low_score = fragments_html.index("Scor mic")
        self.assertLess(position_high_score, position_mid_z, "higher relevance score must render first")
        # Equal scores keep their original (stable-sort) relative order.
        self.assertLess(position_mid_z, position_mid_b, "equal scores must preserve original order")
        self.assertLess(position_mid_b, position_low_score, "lower relevance score must render last")

        # Score/relevance, match-type label and source document render
        # together, one per fragment, as
        # "Scor relevanță: NN%, Găsire ..., document.md".
        self.assertIn("Scor relevanță: 100%, Găsire Lexicală, doc-a.md", fragments_html)
        self.assertIn("Scor relevanță: 50%, doc-z.md", fragments_html)
        self.assertIn("Scor relevanță: 50%, Găsire Lexicală, doc-b.md", fragments_html)
        self.assertIn("Scor relevanță: 10%, Găsire Lexicală, doc-a.md", fragments_html)

        self.assertIn("Total: 4 fragmente din 3 documente.", fragments_html)

    # A fragment missing found_by_lexical (older cached
    # evidence, or a caller that doesn't set them) must still render — just
    # without the middle segment — rather than crashing or printing a blank
    # label.
    def test_fragments_panel_omits_match_type_label_when_absent(self):
        evidence = {
            "C1": {
                "source": "documents/doc-a.md:1-5",
                "text": "Fragment fără found_by_lexical",
                "score": RRF_MAX_SCORE,
                "relevance_percent": 100.0,
            },
        }

        fragments_html = main._fragments_panel_html(evidence)

        self.assertIn("Scor relevanță: 100%, doc-a.md", fragments_html)
        self.assertNotIn("Găsire", fragments_html)

    # Verify the panel shows the backend-computed relevance_percent as is (rounded
    # for display) and omits the percentage for a fragment that carries none.
    def test_fragments_panel_shows_backend_relevance_percent(self):
        evidence = {
            "C1": {"source": "documents/doc-a.md:1-5", "text": "Cu procent", "score": 0.02, "relevance_percent": 61.6},
            "C2": {"source": "documents/doc-b.md:1-5", "text": "Fără procent", "score": 0.01},
        }

        fragments_html = main._fragments_panel_html(evidence)

        self.assertIn("Scor relevanță: 62%, doc-a.md", fragments_html)
        self.assertEqual(fragments_html.count("Scor relevanță"), 1)

    # Verify that one submitted health answer triggers report generation and download.
    def test_chat_automatically_generates_report_after_single_answer(self):
        sid_a = "A" * 43
        sid_b = "B" * 43
        req_a = FakeRequest(sid_a, "tab-a")
        req_b = FakeRequest(sid_b, "tab-b")
        FakeAI.generate_calls = 0
        FakeAI.report_profile = None

        with patch.object(main, "send_report", return_value="email_sent") as send_report_mock, patch.object(
            main, "ai", FakeAI()
        ), patch.object(main, "retriever", FakeRetriever()):
            history = main.on_load(req_a)
            self.assertEqual(history[-1]["content"], HEALTH_PROBLEM_QUESTION)
            main.on_load(req_b)

            _, history, generate_update = main.on_message("Gripă și răceală", req_a)
            self.assertIn("Caut rapid în cele", history[-1]["content"])
            self.assertEqual(generate_update, main.gr.update(visible=False))
            self.assertEqual(FakeAI.generate_calls, 0)

            history, row_update, button_update = main.on_find_fragments(req_a)
            self.assertEqual(FakeAI.generate_calls, 0, "retrieval must not call the AI")
            # The fragments panel is the newest chat message, right after the search notice.
            self.assertIn("Caut rapid în cele", history[-2]["content"])
            fragments_html = history[-1]["content"]
            self.assertNotIn("Fragmentele relevante", fragments_html)
            self.assertIn("Am găsit", fragments_html)
            self.assertIn("1 fragmente", fragments_html)
            self.assertIn("Informație locală relevantă.", fragments_html)
            self.assertIn("plan.md", fragments_html)
            self.assertIn("Scor relevanță", fragments_html)
            self.assertIn("Total: 1 fragmente din 1 documente.", fragments_html)
            self.assertEqual(row_update, main.gr.update(visible=True))
            self.assertEqual(button_update, main.generate_button_ready_update())
            self.assertEqual(
                main.store.get(sid_a, "tab-a").pending_evidence,
                {
                    "C1": {
                        "source": "documents/plan.md:1-5",
                        "text": "Informație locală relevantă.",
                        "score": 0.0167,
                        "relevance_percent": 51.0,
                    }
                },
            )

            history, row_update, button_update, _ = main.on_generate_report(req_a)
            self.assertEqual(FakeAI.generate_calls, 1)
            self.assertEqual(row_update, main.gr.update(visible=False))
            self.assertIsNone(main.store.get(sid_a, "tab-a").pending_evidence)
            send_report_mock.assert_not_called()
            # Chronological order: report, download panel, then the email offer.
            self.assertIn("Uz intern", history[-3]["content"])
            self.assertIn("Descarcă PDF", history[-2]["content"])
            self.assertEqual(history[-1]["content"], main.EMAIL_OFFER)
            _, history, _ = main.on_message("prieten@example.com", req_a)
            self.assertEqual(main.on_find_fragments(req_a)[0], history)
            send_report_mock.assert_called_once()
            self.assertEqual(send_report_mock.call_args.args[0], "Gripă și răceală")
            self.assertTrue(send_report_mock.call_args.args[1].startswith(b"%PDF-"))
            self.assertTrue(send_report_mock.call_args.args[2].endswith(".pdf"))
            self.assertEqual(send_report_mock.call_args.args[3], "prieten@example.com")
            self.assertIn("prieten@example.com", history[-1]["content"])
            self.assertIsNotNone(main.store.get(sid_a, "tab-a").report_bytes)
            self.assertEqual(FakeAI.report_profile["health_problem"], "Gripă și răceală")
            report_text = next(m["content"] for m in history if "Uz intern" in m["content"])
            self.assertIn("[1]", report_text)
            self.assertIn("Bibliografie", report_text)
            self.assertIn("1 - plan.md:1-5", report_text)
            self.assertNotIn("Folosiți butonul Descarcă PDF", report_text)
            self.assertEqual(len(main.store.get(sid_b, "tab-b").history), 2)

            session_a = main.store.get(sid_a, "tab-a")
            self.assertTrue(session_a.report_bytes.startswith(b"%PDF-"))
            content = "\n".join(
                page.extract_text() for page in PdfReader(io.BytesIO(session_a.report_bytes)).pages
            )
            self.assertIn("Remedii naturiste", content)
            self.assertIn("Gripă și răceală", " ".join(content.split()))

            with TestClient(main.app, base_url="https://testserver") as http:
                url = f"/api/reports/tab-a/{session_a.report_id}"
                self.assertEqual(http.get(url, cookies={main.COOKIE: sid_a}).status_code, 200)
                self.assertEqual(http.get(url, cookies={main.COOKIE: sid_b}).status_code, 404)

            main.on_end(req_a)
            self.assertIsNone(main.store.get(sid_a, "tab-a"))
            self.assertIsNotNone(main.store.get(sid_b, "tab-b"))
            main.store.delete(sid_b, "tab-b")

    # Verify a second submission in the same session generates only for the latest problem.
    def test_second_health_problem_replaces_first_report_context(self):
        sid = "C" * 43
        request = FakeRequest(sid, "tab-latest-problem")
        FakeAI.generate_calls = 0
        FakeAI.report_profile = None

        with patch.object(main, "send_report", return_value="email_sent") as send_report_mock, patch.object(
            main, "ai", FakeAI()
        ), patch.object(main, "retriever", FakeRetriever()):
            main.on_load(request)
            main.on_message("Gripă și răceală", request)
            main.on_find_fragments(request)
            main.on_generate_report(request)
            first_report_id = main.store.get(sid, "tab-latest-problem").report_id

            _, history, generate_update = main.on_message("Migrenă", request)
            session = main.store.get(sid, "tab-latest-problem")
            self.assertFalse(any("report-ready-panel" in m["content"] for m in history))
            self.assertEqual(generate_update, main.gr.update(visible=False))
            self.assertIsNone(session.report_id)
            self.assertIsNone(session.report_bytes)
            self.assertIsNone(session.pending_evidence)
            self.assertEqual(session.profile.health_problem, "Migrenă")
            self.assertEqual(session.profile.health_context, ["Migrenă"])
            self.assertEqual(session.profile.transcript, [{"role": "user", "content": "Migrenă"}])

            main.on_find_fragments(request)
            history, _, _, _ = main.on_generate_report(request)
            session = main.store.get(sid, "tab-latest-problem")
            self.assertEqual(FakeAI.generate_calls, 2)
            self.assertEqual(FakeAI.report_profile["health_problem"], "Migrenă")
            self.assertEqual(FakeAI.report_profile["health_context"], ["Migrenă"])
            self.assertNotEqual(session.report_id, first_report_id)
            self.assertIn("Descarcă PDF", history[-2]["content"])
            send_report_mock.assert_not_called()
            pdf_text = " ".join(
                page.extract_text() for page in PdfReader(io.BytesIO(session.report_bytes)).pages
            )
            self.assertIn("Migrenă", " ".join(pdf_text.split()))
            self.assertNotIn("Gripă și răceală", " ".join(pdf_text.split()))

        main.store.delete(sid, "tab-latest-problem")

    # Verify Google API failure keeps the report available and tells the user in chat.
    def test_email_failure_keeps_report_available(self):
        sid = "D" * 43
        request = FakeRequest(sid, "tab-email-failure")

        with patch.object(main, "ai", FakeAI()), patch.object(main, "retriever", FakeRetriever()), patch.object(
            main, "send_report", side_effect=OSError("SMTP unavailable")
        ):
            main.on_load(request)
            main.on_message("Gripă și răceală", request)
            main.on_find_fragments(request)
            main.on_generate_report(request)
            with self.assertLogs("naturist.web", level="ERROR") as captured:
                _, history, _ = main.on_message("prieten@example.com", request)

        session = main.store.get(sid, "tab-email-failure")
        self.assertTrue(session.report_bytes.startswith(b"%PDF-"))
        self.assertIn("Nu am putut trimite", history[-1]["content"])
        self.assertIn("stage=email", "\n".join(captured.output))
        main.store.delete(sid, "tab-email-failure")

    # Verify generated download links include the configured public Gradio prefix.
    def test_public_report_link_uses_gradio_root_path(self):
        sid = "C" * 43
        request = FakeRequest(sid, "tab-public")
        session = main.store.get(sid, "tab-public", create=True)
        session.report_id = "report-1"
        with patch.dict(os.environ, {"GRADIO_ROOT_PATH": "/medicina"}):
            link = main._download_html(session)
        self.assertIn('/medicina/api/reports/tab-public/report-1', link)
        self.assertIn('class="report-ready-panel"', link)
        self.assertIn('aria-hidden="true">✅</span>', link)
        self.assertIn("<strong>Raportul complet este gata</strong>", link)
        self.assertIn("📄</span> Descarcă PDF", link)
        self.assertIn('aria-label="Descarcă raportul complet în format PDF"', link)
        main.store.delete(sid, "tab-public")

    # Verify the redesigned chat keeps its responsive, accessible visual contract.
    def test_chat_layout_uses_warm_responsive_design(self):
        self.assertIn("width: min(100%, 680px) !important", main.APP_CSS)
        self.assertIn("zoom: 66%", main.APP_CSS)
        self.assertIn("--chat-content-width: 100%", main.APP_CSS)
        self.assertIn("width: var(--chat-content-width) !important", main.APP_CSS)
        self.assertIn("--chat-content-width: 100%", main.APP_CSS)
        self.assertIn("--nature-bg: #fff9f2", main.APP_CSS)
        self.assertIn("--nature-primary: #2f7d6d", main.APP_CSS)
        self.assertIn("font-family: Arial", main.APP_CSS)
        self.assertIn("assistant left, user right", main.APP_CSS)
        self.assertIn("#medical-chatbot .message:has(.report-ready-panel)", main.APP_CSS)
        self.assertIn("@media (max-width: 640px)", main.APP_CSS)
        self.assertIn("@media (prefers-reduced-motion: reduce)", main.APP_CSS)
        self.assertIn("#medical-chatbot .wrapper", main.APP_CSS)
        self.assertIn("height: auto !important", main.APP_CSS)
        self.assertEqual(main.chatbot.buttons, ["copy"])
        self.assertEqual(main.message.lines, 1)
        self.assertEqual(main.message.max_lines, 1)
        self.assertIn("#health-message", main.APP_CSS)
        self.assertIn("height: 38px !important", main.APP_CSS)
        self.assertIn("min-width: 96px !important", main.APP_CSS)
        self.assertIn("#health-message input", main.COMPOSER_STATE_JS)
        self.assertNotIn("event.ctrlKey || event.metaKey", main.COMPOSER_STATE_JS)
        self.assertIn("#medical-chatbot .message-row.user-row > .flex-wrap", main.APP_CSS)
        self.assertIn("background: transparent !important", main.APP_CSS)
        self.assertIn("#medical-chatbot [data-testid=\"user\"] *", main.APP_CSS)
        self.assertIn("#medical-chatbot .message-row:hover + .message-buttons", main.APP_CSS)
        self.assertIn("padding: 14px 18px !important", main.APP_CSS)
        self.assertIn("text-align: left", main.APP_CSS)
        self.assertIn(
            ".hero-title-block {\n    width: 100%;\n    max-width: none;\n    margin: 0;\n}",
            main.APP_CSS,
        )
        self.assertIn('#health-message input[data-testid="textbox"]', main.APP_CSS)
        self.assertIn("font: 22px/1.15 Arial, sans-serif !important", main.APP_CSS)
        self.assertIn("height: 38px !important", main.APP_CSS)
        self.assertIn("#medical-chatbot .bubble-wrap > .message-wrap:first-child", main.APP_CSS)
        self.assertIn("Remedii Naturiste", main.HERO_HTML)
        self.assertIn(
            'background: #f4f9f7 url("data:image/svg+xml;base64,',
            main.APP_CSS,
        )
        self.assertNotIn("__HERO_ORNAMENT_DATA_URI__", main.APP_CSS)
        self.assertNotIn("#hero-panel::before", main.APP_CSS)
        self.assertNotIn("#hero-panel::after", main.APP_CSS)
        self.assertTrue(main.ORNAMENT_SVG.is_file())
        self.assertIn('<p class="hero-byline">de la Dr. Cuișor</p>', main.HERO_HTML)
        self.assertIn(".hero-byline", main.APP_CSS)
        self.assertNotIn("text-align: right", main.APP_CSS)
        self.assertIn("message.submit", Path(main.__file__).read_text(encoding="utf-8"))
        self.assertNotIn('elem_id="end-session"', Path(main.__file__).read_text(encoding="utf-8"))
        self.assertNotIn("Închide sesiunea", Path(main.__file__).read_text(encoding="utf-8"))

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
