"""Tests for the configurable AI provider (AI_PROVIDER): selection, payloads, parsing, budget.

No real requests are made: client.http.post is replaced, as in test_web.py.
"""
from __future__ import annotations

import json
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

import httpx

from medicina_naturista.ai.client import AIUnavailable, ResponsesClient, XAIClient, create_ai_client
from medicina_naturista.ai.providers import provider_config
from medicina_naturista import config as config_module
from medicina_naturista.config import Settings, settings as base_settings


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def completed(text: str, *, reasoning_first: bool = False) -> FakeResponse:
    output = [{"type": "message", "content": [{"type": "output_text", "text": text}]}]
    if reasoning_first:
        output.insert(0, {"type": "reasoning", "summary": [{"type": "summary_text", "text": "gândesc"}]})
    return FakeResponse({"status": "completed", "output": output})


# Every provider-related field is pinned, so the tests never depend on the local .env.
PINNED = dict(
    xai_model="grok-4.3",
    xai_reasoning_effort="medium",
    xai_api_base="https://api.x.ai/v1",
    hf_model="deepseek-ai/DeepSeek-V4-Flash:deepinfra",
    hf_api_base="https://router.huggingface.co/v1",
    hf_reasoning_effort="",
    hf_max_context_chars=120_000,
    ollama_model="deepseek-v4.1-flash:cloud",
    ollama_api_base="http://localhost:11434/v1",
    ollama_reasoning_effort="",
    ollama_max_context_chars=None,
    ai_stream=False,
    ai_max_output_tokens=20000,
    ai_read_timeout_seconds=300,
    max_context_chars=1_000_000,
)


def settings_for(provider: str, **overrides) -> Settings:
    return replace(base_settings, **{**PINNED, "ai_provider": provider, **overrides})


def capture_post(client: ResponsesClient, response: FakeResponse) -> list[dict]:
    calls: list[dict] = []

    def post(url, **kwargs):
        calls.append({"url": url, "headers": kwargs["headers"], "json": kwargs["json"]})
        return response

    client.http.post = post
    return calls


class ProviderSelectionTest(unittest.TestCase):
    def test_unknown_provider_fails_fast(self):
        with self.assertRaises(ValueError):
            settings_for("openai")

    def test_default_provider_is_xai(self):
        with patch.dict(os.environ):
            os.environ.pop("AI_PROVIDER", None)
            self.assertEqual(config_module._ai_provider(), "xai")

    def test_create_ai_client_per_provider(self):
        xai = create_ai_client(settings_for("xai"))
        hf = create_ai_client(settings_for("huggingface"))
        ollama = create_ai_client(settings_for("ollama"))
        try:
            self.assertIsInstance(xai, XAIClient)
            self.assertEqual(xai.provider.base_url, "https://api.x.ai/v1")
            self.assertEqual(hf.provider.name, "huggingface")
            self.assertNotIsInstance(hf, XAIClient)
            self.assertEqual(hf.provider.model, "deepseek-ai/DeepSeek-V4-Flash:deepinfra")
            self.assertEqual(hf.provider.base_url, "https://router.huggingface.co/v1")
            self.assertEqual(ollama.provider.name, "ollama")
            self.assertEqual(ollama.provider.model, "deepseek-v4.1-flash:cloud")
        finally:
            for client in (xai, hf, ollama):
                client.close()

    def test_xai_client_ignores_ai_provider_setting(self):
        client = XAIClient(settings_for("huggingface"))
        client.close()
        self.assertEqual(client.provider.name, "xai")

    def test_ollama_needs_a_key_only_for_remote_bases(self):
        self.assertFalse(provider_config(settings_for("ollama")).api_key_required)
        self.assertFalse(
            provider_config(
                settings_for("ollama", ollama_api_base="http://host.docker.internal:11434/v1")
            ).api_key_required
        )
        self.assertTrue(
            provider_config(settings_for("ollama", ollama_api_base="https://ollama.com/v1")).api_key_required
        )


class PayloadTest(unittest.TestCase):
    def test_xai_payload_is_unchanged(self):
        with patch.dict(os.environ, {"X_API_KEY": "synthetic-xai-key"}):
            client = XAIClient(settings_for("xai", xai_model="grok-4.3", xai_reasoning_effort="medium"))
            calls = capture_post(client, completed('{"ok": true}'))
            result = client.complete_json("sistem", "utilizator", 321)
            client.close()
        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls[0]["url"], "https://api.x.ai/v1/responses")
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer synthetic-xai-key")
        self.assertEqual(
            calls[0]["json"],
            {
                "model": "grok-4.3",
                "reasoning": {"effort": "medium"},
                "input": [
                    {"role": "system", "content": "sistem"},
                    {"role": "user", "content": "utilizator"},
                ],
                "text": {"format": {"type": "json_object"}},
                "max_output_tokens": 321,
                "store": False,
            },
        )

    def test_huggingface_request(self):
        with patch.dict(os.environ, {"HF_TOKEN": "synthetic-hf-token"}):
            client = create_ai_client(settings_for("huggingface", hf_reasoning_effort=""))
            calls = capture_post(client, completed('{"ok": true}'))
            client.complete_json("sistem", "utilizator", 500)
            client.close()
        self.assertEqual(calls[0]["url"], "https://router.huggingface.co/v1/responses")
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer synthetic-hf-token")
        payload = calls[0]["json"]
        self.assertEqual(payload["model"], "deepseek-ai/DeepSeek-V4-Flash:deepinfra")
        self.assertEqual(payload["max_output_tokens"], 500)
        for absent in ("reasoning", "store", "text", "response_format"):
            self.assertNotIn(absent, payload)

    def test_huggingface_sends_reasoning_only_when_configured(self):
        with patch.dict(os.environ, {"HF_TOKEN": "synthetic-hf-token"}):
            client = create_ai_client(settings_for("huggingface", hf_reasoning_effort="low"))
            calls = capture_post(client, completed('{"ok": true}'))
            client.complete_json("s", "u", 10)
            client.close()
        self.assertEqual(calls[0]["json"]["reasoning"], {"effort": "low"})

    def test_local_ollama_sends_no_authorization_and_no_store(self):
        with patch.dict(os.environ, {"OLLAMA_API_KEY": ""}):
            client = create_ai_client(settings_for("ollama"))
            calls = capture_post(client, completed('{"ok": true}'))
            client.complete_json("s", "u", 10)
            client.close()
        self.assertEqual(calls[0]["url"], "http://localhost:11434/v1/responses")
        self.assertNotIn("Authorization", calls[0]["headers"])
        self.assertNotIn("store", calls[0]["json"])


class MissingKeyTest(unittest.TestCase):
    def assert_missing(self, provider: str, variable: str, **overrides):
        with patch.dict(os.environ, {variable: ""}):
            client = create_ai_client(settings_for(provider, **overrides))
            try:
                self.assertFalse(client.is_configured())
                with self.assertRaises(AIUnavailable) as caught:
                    client.complete_json("s", "u", 10)
                self.assertIn(variable, str(caught.exception))
            finally:
                client.close()

    def test_xai(self):
        self.assert_missing("xai", "X_API_KEY")

    def test_huggingface(self):
        self.assert_missing("huggingface", "HF_TOKEN")

    def test_remote_ollama(self):
        self.assert_missing("ollama", "OLLAMA_API_KEY", ollama_api_base="https://ollama.com/v1")

    def test_local_ollama_without_key_is_configured(self):
        with patch.dict(os.environ, {"OLLAMA_API_KEY": ""}):
            client = create_ai_client(settings_for("ollama"))
            client.close()
        self.assertTrue(client.is_configured())


class ParsingTest(unittest.TestCase):
    def complete(self, response: FakeResponse) -> dict:
        with patch.dict(os.environ, {"HF_TOKEN": "synthetic-hf-token"}):
            client = create_ai_client(settings_for("huggingface"))
            capture_post(client, response)
            try:
                return client.complete_json("s", "u", 10)
            finally:
                client.close()

    def test_json_inside_markdown_fences(self):
        self.assertEqual(self.complete(completed('```json\n{"a": 1}\n```')), {"a": 1})

    def test_json_preceded_by_text(self):
        self.assertEqual(self.complete(completed('Iată răspunsul: {"a": {"b": 2}} Sper că ajută.')), {"a": {"b": 2}})

    def test_reasoning_item_before_message_is_ignored(self):
        self.assertEqual(self.complete(completed('{"a": 1}', reasoning_first=True)), {"a": 1})

    def test_text_without_object_is_rejected(self):
        with self.assertRaises(AIUnavailable):
            self.complete(completed("nu e JSON"))

    def test_incomplete_response_is_rejected_and_logged_with_reason(self):
        response = FakeResponse({
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [{"type": "reasoning"}],
        })
        with self.assertLogs("naturist.ai", level="ERROR") as logs:
            with self.assertRaises(AIUnavailable):
                self.complete(response)
        self.assertTrue(any("max_output_tokens" in line for line in logs.output))


class FakeStream:
    def __init__(self, lines, status_code=200):
        self._lines = lines
        self.status_code = status_code
        self.headers = {}
        self.text = "boom"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b""

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://x")
            raise httpx.HTTPStatusError("e", request=request, response=httpx.Response(self.status_code, request=request, text="boom"))

    def iter_lines(self):
        return iter(self._lines)


def sse(event_type, **fields):
    return "data: " + json.dumps({"type": event_type, **fields})


class StreamingTest(unittest.TestCase):
    def run_stream(self, lines, status_code=200):
        sent = []
        with patch.dict(os.environ, {"HF_TOKEN": "synthetic-hf-token"}):
            client = create_ai_client(settings_for("huggingface", ai_stream=True))

            def stream(method, url, **kwargs):
                sent.append((method, url, kwargs))
                return FakeStream(lines, status_code)

            client.http.stream = stream
            try:
                return client.complete_json("s", "u", 10), sent
            finally:
                client.close()

    def test_stream_request_and_completed_event(self):
        final = {"status": "completed", "output": [
            {"type": "message", "content": [{"type": "output_text", "text": '{"a": 1}'}]}]}
        result, sent = self.run_stream([
            "event: response.output_text.delta",
            sse("response.output_text.delta", delta='{"a"'),
            "",
            sse("response.completed", response=final),
        ])
        self.assertEqual(result, {"a": 1})
        method, url, kwargs = sent[0]
        self.assertEqual((method, url), ("POST", "https://router.huggingface.co/v1/responses"))
        self.assertIs(kwargs["json"]["stream"], True)
        self.assertEqual(kwargs["headers"]["Accept"], "text/event-stream")

    def test_deltas_are_used_when_completed_has_no_output(self):
        result, _ = self.run_stream([
            sse("response.output_text.delta", delta='{"a":'),
            sse("response.output_text.delta", delta=' 2}'),
            sse("response.completed", response={"status": "completed", "output": []}),
            "data: [DONE]",
        ])
        self.assertEqual(result, {"a": 2})

    def test_incomplete_event_is_rejected(self):
        with self.assertRaises(AIUnavailable):
            self.run_stream([sse("response.incomplete", response={
                "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}, "output": []})])

    def test_stream_cut_before_completion_is_rejected(self):
        with self.assertRaises(AIUnavailable):
            self.run_stream([sse("response.output_text.delta", delta="{")])

    def test_error_event_is_rejected(self):
        with self.assertRaises(AIUnavailable):
            self.run_stream([sse("error", message="overloaded")])

    def test_http_error_status_is_reported(self):
        with self.assertRaises(AIUnavailable) as caught:
            self.run_stream([], status_code=504)
        self.assertIn("HTTP 504", str(caught.exception))

    def test_xai_payload_has_no_stream_field_by_default(self):
        client = XAIClient(settings_for("xai"))
        client.close()
        self.assertNotIn("stream", client._build_payload("s", "u", 1))


class ContextBudgetTest(unittest.TestCase):
    def budget(self, provider: str, **overrides) -> int:
        client = create_ai_client(settings_for(provider, **overrides))
        client.close()
        return client.context_budget()

    def test_xai_uses_the_global_limit(self):
        self.assertEqual(self.budget("xai", max_context_chars=900_000), 900_000)

    def test_huggingface_is_capped_by_its_own_limit(self):
        self.assertEqual(self.budget("huggingface", max_context_chars=1_000_000, hf_max_context_chars=120_000), 120_000)

    def test_global_limit_wins_when_lower(self):
        self.assertEqual(self.budget("huggingface", max_context_chars=50_000, hf_max_context_chars=120_000), 50_000)

    def test_ollama_without_own_limit_uses_the_global_one(self):
        self.assertEqual(self.budget("ollama", max_context_chars=800_000, ollama_max_context_chars=None), 800_000)


class HTTPErrorTest(unittest.TestCase):
    def test_error_message_names_the_provider(self):
        with patch.dict(os.environ, {"HF_TOKEN": "synthetic-hf-token"}):
            client = create_ai_client(settings_for("huggingface"))

            def post(url, **kwargs):
                request = httpx.Request("POST", url)
                raise httpx.HTTPStatusError(
                    "boom", request=request, response=httpx.Response(400, request=request, text="bad")
                )

            client.http.post = post
            try:
                with self.assertRaises(AIUnavailable) as caught:
                    client.complete_json("s", "u", 10)
            finally:
                client.close()
        self.assertIn("Hugging Face", str(caught.exception))
        self.assertIn("HTTP 400", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
