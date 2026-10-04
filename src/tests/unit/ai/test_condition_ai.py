"""Tests for the AI identification of a condition the dictionary does not know
(backend.ai.condition_ai): the answer's validation, the backends and their
fallback, the cache, and how an answer becomes an ordinary condition. No real
request is made: the HTTP client's post() is replaced."""
from __future__ import annotations

import json
import os
import unittest
from dataclasses import replace
from unittest.mock import MagicMock, patch

import httpx

from backend.ai import condition_ai, conditions
from backend.ai.condition_ai import AIConditionResult
from backend.ai.conditions import Condition, ConditionDictionary, parse_conditions, resolve_query
from backend.ai.search import ALL_SIGNALS, SearchSignals, effective_signals, max_score, weights
from backend.config import settings as base_settings
from backend.core.models import HealthProfile
from backend.reporting.pdf import report_title

DICTIONARY_TEXT = "Hipertiroidism,hipertiroidie,hyperthyroidism\nGripa,influenza,flu\n"


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


# A Responses API reply whose text is `value` (a JSON string, or any object dumped as JSON).
def reply(value) -> FakeResponse:
    text = value if isinstance(value, str) else json.dumps(value)
    return FakeResponse({"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]})


def segments_reply(*entries: dict) -> FakeResponse:
    return reply({"segments": list(entries)})


HYPER = {"index": 1, "name": "hipertiroidism", "synonyms": ["tiroida hiperactiva", "hyperthyroidism"]}


class ConditionAITestCase(unittest.TestCase):
    backends: tuple[str, ...] = ("local",)

    def setUp(self):
        self.dictionary = ConditionDictionary(parse_conditions(DICTIONARY_TEXT))
        test_settings = replace(base_settings, condition_ai_backends=self.backends)
        env = patch.dict(os.environ, {"HF_TOKEN": "synthetic-token"})
        for manager in (
            patch.object(condition_ai, "settings", test_settings),
            patch.object(conditions, "load_dictionary", return_value=self.dictionary),
            env,
        ):
            manager.start()
            self.addCleanup(manager.stop)
        condition_ai.clear_cache()
        condition_ai._clients.clear()
        self.addCleanup(condition_ai.clear_cache)
        self.addCleanup(condition_ai._clients.clear)

    # Replace the HTTP post of one backend's client; `behaviours` are returned (or raised) in turn.
    def fake_post(self, backend: str, *behaviours):
        client = condition_ai._client(backend)
        post = MagicMock(side_effect=list(behaviours))
        client.http.post = post
        return post

    def identify(self, message: str = "tiroida care merge prea repede") -> AIConditionResult:
        return condition_ai.identify_conditions(resolve_query(message))


class IdentificationTests(ConditionAITestCase):
    def test_a_valid_answer_becomes_a_condition_with_its_name_and_synonyms(self):
        self.fake_post("local", segments_reply({**HYPER, "name": "Hipertiroidism-ul meu", "synonyms": ["tiroida hiperactiva"]}))

        result = self.identify()

        self.assertEqual(result.reason, condition_ai.IDENTIFIED)
        self.assertEqual(result.backend, "local")
        self.assertEqual(result.conditions, (Condition("Hipertiroidism-ul meu", ("Hipertiroidism-ul meu", "tiroida hiperactiva")),))

    def test_the_answer_makes_the_segment_a_whole_condition_segment(self):
        self.fake_post("local", segments_reply({"index": 1, "name": "Cefalee", "synonyms": ["migrena", "headache"]}))
        resolved = resolve_query("durere de cap, gripa")

        result = condition_ai.identify_conditions(resolved)
        completed = condition_ai.with_ai_conditions(resolved, result.answers)

        first, second = completed.segments
        self.assertTrue(first.whole_condition)
        self.assertEqual(first.text, "durere de cap")
        self.assertEqual(first.remainder, "")
        self.assertEqual(first.conditions, (Condition("Cefalee", ("Cefalee", "migrena", "headache")),))
        self.assertEqual(second, resolved.segments[1])  # the segment the AI did not name is untouched

    def test_a_name_that_is_a_dictionary_term_takes_the_canonical_name_and_keeps_both_term_lists(self):
        resolved = resolve_query("tiroida care merge prea repede")
        answers = ({"index": 1, "name": "Hipertiroidie", "terms": ["Hipertiroidie", "tiroida hiperactiva"]},)

        condition = condition_ai.with_ai_conditions(resolved, answers).conditions[0]

        self.assertEqual(condition.name, "Hipertiroidism")
        self.assertEqual(
            condition.terms,
            ("Hipertiroidism", "hipertiroidie", "hyperthyroidism", "tiroida hiperactiva"),
        )

    def test_a_synonym_that_is_a_dictionary_term_also_maps_to_the_canonical_name(self):
        resolved = resolve_query("tiroida care merge prea repede")
        answers = ({"index": 1, "name": "Tiroida hiperactiva", "terms": ["Tiroida hiperactiva", "HYPERTHYROIDISM"]},)

        self.assertEqual(condition_ai.with_ai_conditions(resolved, answers).condition_names, ("Hipertiroidism",))

    def test_a_name_missing_from_the_dictionary_is_kept_as_it_is(self):
        self.fake_post("local", segments_reply({"index": 1, "name": "Cefalee", "synonyms": ["headache"]}))
        result = self.identify("durere de cap")

        self.assertEqual(condition_ai.with_ai_conditions(resolve_query("durere de cap"), result.answers).condition_names, ("Cefalee",))

    def test_nothing_identified_is_the_none_reason_without_a_fallback(self):
        local = self.fake_post("local", segments_reply())

        result = self.identify("ce plante sunt bune?")

        self.assertEqual((result.reason, result.answers, result.conditions), (condition_ai.NONE, (), ()))
        self.assertEqual(local.call_count, 1)

    def test_an_already_identified_segment_is_not_replaced(self):
        resolved = resolve_query("gripa")
        answers = ({"index": 1, "name": "Altceva", "terms": ["Altceva"]},)

        self.assertEqual(condition_ai.with_ai_conditions(resolved, answers), resolved)

    def test_answers_for_missing_segments_are_ignored(self):
        resolved = resolve_query("durere de cap")

        self.assertEqual(condition_ai.with_ai_conditions(resolved, ({"index": 5, "name": "X", "terms": ["X"]},)), resolved)
        self.assertEqual(condition_ai.with_ai_conditions(resolved, ()), resolved)
        self.assertEqual(condition_ai.with_ai_conditions(resolved, None), resolved)

    def test_the_request_numbers_the_segments_and_sends_the_system_prompt(self):
        post = self.fake_post("local", segments_reply())

        self.identify("durere de cap,  ameteli ")

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], base_settings.condition_ai_local_model)
        self.assertEqual(payload["max_output_tokens"], base_settings.condition_ai_max_output_tokens)
        self.assertEqual(payload["input"][1], {"role": "user", "content": "1. durere de cap\n2. ameteli"})
        self.assertIn("DOAR", payload["input"][0]["content"])
        self.assertEqual(payload["temperature"], 0.0)  # the small local model is asked without sampling noise


class FailureTests(ConditionAITestCase):
    def test_invalid_json_is_an_error_not_an_exception(self):
        self.fake_post("local", reply("nu e JSON"))

        self.assertEqual(self.identify().reason, condition_ai.ERROR)

    def test_a_reply_of_the_wrong_shape_is_an_error(self):
        self.fake_post("local", reply({"segments": "gripa"}))

        self.assertEqual(self.identify().reason, condition_ai.ERROR)

    def test_a_timeout_is_the_timeout_reason(self):
        self.fake_post("local", httpx.ReadTimeout("slow"))

        self.assertEqual(self.identify().reason, condition_ai.TIMEOUT)

    def test_a_connection_error_is_an_error(self):
        self.fake_post("local", httpx.ConnectError("refused"))

        result = self.identify()

        self.assertEqual((result.reason, result.answers), (condition_ai.ERROR, ()))

    def test_an_http_error_status_is_an_error(self):
        response = httpx.Response(500, request=httpx.Request("POST", "http://x"), text="boom")
        self.fake_post("local", httpx.HTTPStatusError("500", request=response.request, response=response))

        self.assertEqual(self.identify().reason, condition_ai.ERROR)

    def test_the_message_text_is_not_logged(self):
        self.fake_post("local", segments_reply({"index": 1, "name": "Cefalee", "synonyms": []}))

        with self.assertLogs("naturist.condition_ai", level="INFO") as captured:
            self.identify("am o durere secreta")

        output = "\n".join(captured.output)
        self.assertIn("condition_ai_completed backend=local reason=identified", output)
        self.assertIn("identified=Cefalee synonyms=0 mapped_to_dictionary=nu", output)
        self.assertNotIn("secreta", output)


class DisabledTests(ConditionAITestCase):
    backends = ()

    def test_no_backend_means_the_step_is_disabled_and_no_request_is_made(self):
        with patch.object(condition_ai, "_client", side_effect=AssertionError("no client")):
            result = self.identify()

        self.assertEqual((result.reason, result.answers), (condition_ai.DISABLED, ()))


class NoTokenTests(ConditionAITestCase):
    backends = ("huggingface",)

    def test_hugging_face_without_a_token_is_no_token(self):
        with patch.dict(os.environ, {"HF_TOKEN": ""}):
            post = self.fake_post("huggingface")
            result = self.identify()

        self.assertEqual(result.reason, condition_ai.NO_TOKEN)
        post.assert_not_called()

    def test_hugging_face_sends_the_token_and_its_own_model(self):
        post = self.fake_post("huggingface", segments_reply(HYPER))

        result = self.identify()

        self.assertEqual((result.reason, result.backend), (condition_ai.IDENTIFIED, "huggingface"))
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer synthetic-token")
        self.assertEqual(post.call_args.kwargs["json"]["model"], base_settings.condition_ai_hf_model)
        self.assertNotIn("temperature", post.call_args.kwargs["json"])
        self.assertTrue(post.call_args.args[0].startswith(base_settings.hf_api_base))


class FallbackTests(ConditionAITestCase):
    backends = ("local", "huggingface")

    def test_the_local_backend_answers_first_and_hugging_face_is_not_called(self):
        local = self.fake_post("local", segments_reply(HYPER))
        remote = self.fake_post("huggingface")

        result = self.identify()

        self.assertEqual(result.backend, "local")
        self.assertEqual((local.call_count, remote.call_count), (1, 0))

    def test_hugging_face_is_tried_when_the_local_backend_is_unavailable(self):
        self.fake_post("local", httpx.ConnectError("refused"))
        remote = self.fake_post("huggingface", segments_reply(HYPER))

        result = self.identify()

        self.assertEqual((result.reason, result.backend), (condition_ai.IDENTIFIED, "huggingface"))
        self.assertEqual(remote.call_count, 1)

    def test_hugging_face_is_tried_when_the_local_reply_is_not_valid_json(self):
        self.fake_post("local", reply("nu e JSON"))
        remote = self.fake_post("huggingface", segments_reply(HYPER))

        self.assertEqual(self.identify().backend, "huggingface")
        self.assertEqual(remote.call_count, 1)

    def test_a_valid_nothing_found_from_the_local_backend_does_not_cost_a_remote_call(self):
        self.fake_post("local", segments_reply())
        remote = self.fake_post("huggingface")

        result = self.identify("ce plante sunt bune?")

        self.assertEqual(result.reason, condition_ai.NONE)
        remote.assert_not_called()

    def test_when_every_backend_fails_the_last_failure_is_the_reason(self):
        self.fake_post("local", httpx.ReadTimeout("slow"))
        self.fake_post("huggingface", reply("nu e JSON"))

        self.assertEqual(self.identify().reason, condition_ai.ERROR)


class CacheTests(ConditionAITestCase):
    def test_the_same_message_is_answered_once(self):
        post = self.fake_post("local", segments_reply(HYPER), segments_reply())

        first, second = self.identify(), self.identify()

        self.assertEqual(first.answers, second.answers)
        self.assertEqual(post.call_count, 1)

    def test_the_key_is_the_text_of_the_segments(self):
        post = self.fake_post("local", segments_reply(HYPER), segments_reply())

        self.identify("tiroida care merge prea repede")
        self.identify("ceva cu totul diferit")

        self.assertEqual(post.call_count, 2)

    def test_an_error_is_not_cached(self):
        post = self.fake_post("local", httpx.ConnectError("refused"), segments_reply(HYPER))

        self.assertEqual(self.identify().reason, condition_ai.ERROR)
        self.assertEqual(self.identify().reason, condition_ai.IDENTIFIED)
        self.assertEqual(post.call_count, 2)


class ValidationTests(unittest.TestCase):
    def validate(self, entries, count: int = 2):
        return condition_ai._validate({"segments": entries}, count)

    def test_the_answer_is_checked_in_form_only(self):
        answers = self.validate([{"index": 2, "name": "  Boala   inexistenta ", "synonyms": ["x y"]}])

        self.assertEqual(answers, ({"index": 2, "name": "Boala inexistenta", "terms": ["Boala inexistenta", "x y"]},))

    def test_the_name_starts_with_a_capital_letter(self):
        self.assertEqual(self.validate([{"index": 1, "name": "gripa"}])[0]["name"], "Gripa")

    def test_entries_with_a_bad_index_or_name_are_dropped(self):
        entries = [
            {"index": 0, "name": "A"}, {"index": 3, "name": "B"}, {"index": "1", "name": "C"}, {"index": True, "name": "D"},
            {"index": 1, "name": ""}, {"index": 1, "name": 5}, {"index": 1, "name": "x" * 101}, "text", {"index": 1, "name": "?!"},
        ]

        self.assertEqual(self.validate(entries), ())

    def test_the_first_answer_of_a_segment_wins(self):
        answers = self.validate([{"index": 1, "name": "Prima"}, {"index": 1, "name": "A doua"}])

        self.assertEqual([answer["name"] for answer in answers], ["Prima"])

    def test_synonyms_are_cleaned_deduplicated_and_cut_to_eight(self):
        synonyms = ["Gripa", "gripă", "a", "A", "", 5, "x" * 101, *[f"sinonim {number}" for number in range(12)]]

        terms = self.validate([{"index": 1, "name": "Gripa", "synonyms": synonyms}])[0]["terms"]

        self.assertEqual(terms, ["Gripa", "a", *[f"sinonim {number}" for number in range(7)]])
        self.assertEqual(len(terms) - 1, 8)

    def test_synonyms_that_are_not_a_list_are_ignored(self):
        self.assertEqual(self.validate([{"index": 1, "name": "Gripa", "synonyms": "flu"}])[0]["terms"], ["Gripa"])
        self.assertEqual(self.validate([{"index": 1, "name": "Gripa"}])[0]["terms"], ["Gripa"])

    def test_a_reply_without_a_segment_list_is_rejected(self):
        for raw in ({}, {"segments": None}, [], "x"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                condition_ai._validate(raw, 1)


class ResolvedForTests(ConditionAITestCase):
    ANSWERS = ({"index": 1, "name": "Cefalee", "terms": ["Cefalee", "migrena"]},)

    def test_a_profile_resolves_like_the_dictionary_when_the_ai_found_nothing(self):
        profile = HealthProfile()
        profile.set_health_problem("gripa")

        self.assertEqual(condition_ai.resolved_for(profile), resolve_query("gripa"))

    def test_a_profile_and_its_dict_resolve_to_the_same_conditions(self):
        profile = HealthProfile()
        profile.set_health_problem("durere de cap")
        profile.ai_conditions = self.ANSWERS

        self.assertEqual(condition_ai.resolved_for(profile).condition_names, ("Cefalee",))
        self.assertEqual(condition_ai.resolved_for(profile.as_dict()), condition_ai.resolved_for(profile))

    def test_a_new_message_drops_the_conditions_of_the_old_one(self):
        profile = HealthProfile()
        profile.set_health_problem("durere de cap")
        profile.ai_conditions = self.ANSWERS

        profile.replace_health_problem("durere de stomac")
        self.assertEqual(profile.ai_conditions, ())

        profile.ai_conditions = self.ANSWERS
        profile.set_health_problem("durere de gat")
        self.assertEqual(profile.ai_conditions, ())
        self.assertEqual(profile.as_dict()["ai_conditions"], [])


class EffectiveSignalsTests(unittest.TestCase):
    def test_the_conditions_signal_is_dropped_when_the_message_names_no_condition(self):
        resolved = ConditionDictionary(parse_conditions(DICTIONARY_TEXT)).resolve("durere de cap")

        for code, expected in (("ABC", "BC"), ("AB", "B"), ("AC", "C"), ("A", "A"), ("BC", "BC"), ("B", "B"), ("C", "C")):
            with self.subTest(code=code):
                self.assertEqual(effective_signals(SearchSignals.from_code(code), resolved).code, expected)

    def test_the_signals_stay_when_the_message_names_a_condition(self):
        resolved = ConditionDictionary(parse_conditions(DICTIONARY_TEXT)).resolve("gripa")

        self.assertIs(effective_signals(ALL_SIGNALS, resolved), ALL_SIGNALS)

    def test_a_condition_from_the_ai_keeps_the_conditions_signal(self):
        resolved = condition_ai.with_ai_conditions(
            resolve_query("durere de cap"), ({"index": 1, "name": "Cefalee", "terms": ["Cefalee"]},)
        )
        with patch.object(conditions, "load_dictionary", return_value=ConditionDictionary([])):
            self.assertIs(effective_signals(ALL_SIGNALS, resolved), ALL_SIGNALS)

    def test_without_the_conditions_signal_the_best_fragment_can_reach_a_hundred_percent(self):
        resolved = ConditionDictionary([]).resolve("durere de cap")
        effective = effective_signals(ALL_SIGNALS, resolved)

        self.assertEqual(weights(effective), (0, 0, 1, 1))
        self.assertEqual(max_score(effective), 2)
        self.assertEqual(max_score(ALL_SIGNALS), 8)


class ReportTitleTests(unittest.TestCase):
    def setUp(self):
        dictionary = ConditionDictionary(parse_conditions(DICTIONARY_TEXT))
        manager = patch.object(conditions, "load_dictionary", return_value=dictionary)
        manager.start()
        self.addCleanup(manager.stop)

    def test_the_title_names_the_condition_the_ai_identified(self):
        profile = {
            "health_problem": "durere de cap",
            "ai_conditions": [{"index": 1, "name": "Hipertensiune arterială", "terms": ["Hipertensiune arterială"]}],
        }

        self.assertEqual(report_title(profile), "Remedii naturiste pentru hipertensiune arterială")

    def test_two_ai_conditions_are_joined_in_romanian(self):
        profile = {
            "health_problem": "a, b",
            "ai_conditions": [{"index": 1, "name": "Cefalee"}, {"index": 2, "name": "Vertij"}],
        }

        self.assertEqual(report_title(profile), "Remedii naturiste pentru cefalee și vertij")

    def test_a_condition_from_the_dictionary_comes_first(self):
        profile = {"health_problem": "gripa", "ai_conditions": [{"index": 1, "name": "Altceva"}]}

        self.assertEqual(report_title(profile), "Remedii naturiste pentru gripă")

    def test_without_any_condition_the_title_is_the_typed_text(self):
        self.assertEqual(report_title({"health_problem": "durere de cap", "ai_conditions": []}), "Remedii naturiste pentru durere de cap")
        self.assertEqual(report_title({"health_problem": "durere de cap"}), "Remedii naturiste pentru durere de cap")


if __name__ == "__main__":
    unittest.main()
