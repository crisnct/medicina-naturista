"""Single-request report generation through a Responses API provider (xAI, Hugging Face, Ollama)."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx

from medicina_naturista.ai.providers import ProviderConfig, provider_config
from medicina_naturista.config import Settings, settings as default_settings

logger = logging.getLogger("naturist.ai")
SECTIONS = ("uz_intern", "nutritie", "uz_extern", "alte_recomandari", "atentionari")
GENERATE_REPORT_SYSTEM_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "generate_report_system.md"
)
# Evidence fragments as the AI request carries them, highest score first.
def _ordered_entries(evidence: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    ordered_tokens = sorted(
        evidence.keys(),
        key=lambda token: evidence[token].get("score", float("-inf")),
        reverse=True,
    )
    return [
        {"id": token, "source": evidence[token]["source"], "text": evidence[token]["text"]}
        for token in ordered_tokens
    ]


class AIUnavailable(RuntimeError):
    pass


# Parse the model's JSON object, tolerating Markdown fences and text around it.
def _parse_json_object(content: str) -> Any:
    try:
        return json.loads(content)
    except ValueError:
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end <= start:
            raise
        return json.loads(content[start : end + 1])


# The final response of a streamed request, shaped like the parts of
# httpx.Response that _post() and complete_json() read.
class _StreamedResponse:
    def __init__(self, payload: dict[str, Any], status_code: int, headers: Any, raw_bytes: int) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = headers
        self.content = b""
        self.raw_bytes = raw_bytes

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


# Fold Responses API server-sent events into the final response object.
def _collect_stream(lines: Any) -> tuple[dict[str, Any], int]:
    deltas: list[str] = []
    raw_bytes = 0
    for line in lines:
        raw_bytes += len(line) + 1
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        event = json.loads(data)
        kind = event.get("type")
        if kind == "response.output_text.delta" and isinstance(event.get("delta"), str):
            deltas.append(event["delta"])
        elif kind in ("response.completed", "response.incomplete", "response.failed"):
            final = event.get("response")
            if not isinstance(final, dict):
                raise ValueError(f"{kind} without response object")
            if kind == "response.failed":
                raise ValueError(f"response failed: {final.get('error')}")
            if kind == "response.completed" and not final.get("output") and deltas:
                # Some servers end the stream without repeating the output.
                final = {**final, "output": [{
                    "type": "message",
                    "content": [{"type": "output_text", "text": "".join(deltas)}],
                }]}
            return final, raw_bytes
        elif kind == "error":
            raise ValueError(f"stream error: {event.get('message') or event.get('error')}")
    raise ValueError("stream ended before the response completed")


class ResponsesClient:
    # Initialize the HTTP client and load the report-generation system prompt.
    def __init__(self, provider: ProviderConfig, settings: Settings = default_settings) -> None:
        self.provider = provider
        self.settings = settings
        # The read timeout is generous: a request can carry close to
        # the provider's context budget (1M chars, ~250K tokens), which can take minutes.
        self.http = httpx.Client(
            timeout=httpx.Timeout(float(provider.read_timeout_seconds), connect=10.0)
        )
        self.generate_system_prompt = GENERATE_REPORT_SYSTEM_PROMPT_PATH.read_text(
            encoding="utf-8"
        ).strip()

    # Whether the active provider can be called (its key is present when one is required).
    def is_configured(self) -> bool:
        return not self.provider.api_key_required or bool(self.provider.api_key())

    # Evidence budget in characters: the active provider's own context limit.
    def context_budget(self) -> int:
        return self.provider.max_context_chars

    # Close the underlying HTTP connection pool.
    def close(self) -> None:
        self.http.close()

    # POST the request; with streaming, read the event stream up to the final response.
    # The read timeout then applies between events, not to the whole generation,
    # so a proxy's idle cut-off (e.g. 60 s) is not reached while tokens flow.
    def _send(self, headers: dict[str, str], payload: dict[str, Any]) -> Any:
        url = f"{self.provider.base_url}/responses"
        if not self.provider.stream:
            return self.http.post(url, headers=headers, json=payload)
        with self.http.stream("POST", url, headers={**headers, "Accept": "text/event-stream"}, json=payload) as response:
            if response.status_code >= 400:
                response.read()
                response.raise_for_status()
            final, raw_bytes = _collect_stream(response.iter_lines())
            return _StreamedResponse(final, response.status_code, response.headers, raw_bytes)

    # Send one request to the provider's Responses API with diagnostic logging.
    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        key = self.provider.api_key()
        if not key and self.provider.api_key_required:
            logger.error("ai_request_skipped reason=missing_api_key provider=%s", self.provider.name)
            raise AIUnavailable(
                f"Lipsește {self.provider.api_key_env}. Configurați variabila în .env înainte de utilizare."
            )
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        started = time.perf_counter()
        logger.info(
            "ai_request_started provider=%s model=%s reasoning_effort=%s max_output_tokens=%s",
            self.provider.name,
            payload.get("model"),
            payload.get("reasoning", {}).get("effort"),
            payload.get("max_output_tokens"),
        )
        try:
            response = self._send(headers, payload)
            response.raise_for_status()
            logger.info(
                "ai_request_completed status=%s duration_ms=%s response_bytes=%s request_id=%s",
                getattr(response, "status_code", "-"),
                round((time.perf_counter() - started) * 1000),
                getattr(response, "raw_bytes", None) or len(getattr(response, "content", b"")),
                getattr(response, "headers", {}).get("x-request-id")
                or getattr(response, "headers", {}).get("request-id")
                or "-",
            )
            return response
        except httpx.HTTPStatusError as exc:
            response = exc.response
            request_id = response.headers.get("x-request-id") or response.headers.get("request-id") or "-"
            body = response.text.strip() or "<empty response body>"
            logger.error(
                "ai_request_failed status=%s duration_ms=%s request_id=%s body=%s",
                response.status_code,
                round((time.perf_counter() - started) * 1000),
                request_id,
                body[:12000],
            )
            raise AIUnavailable(
                f"Serviciul AI ({self.provider.label}) a respins cererea "
                f"(HTTP {response.status_code}, request_id={request_id})."
            ) from exc
        except httpx.RequestError as exc:
            logger.error(
                "ai_request_failed error=request duration_ms=%s message=%s",
                round((time.perf_counter() - started) * 1000),
                str(exc),
            )
            raise AIUnavailable("Serviciul AI nu este disponibil momentan. Încercați din nou.") from exc
        except ValueError as exc:
            logger.error(
                "ai_request_failed error=invalid_response duration_ms=%s message=%s",
                round((time.perf_counter() - started) * 1000),
                str(exc),
            )
            raise AIUnavailable("Serviciul AI nu este disponibil momentan. Încercați din nou.") from exc

    # Build the Responses API request body for this provider.
    def _build_payload(self, system: str, user: str, max_tokens: int) -> dict[str, Any]:
        provider = self.provider
        payload: dict[str, Any] = {"model": provider.model}
        if provider.reasoning_effort:
            payload["reasoning"] = {"effort": provider.reasoning_effort}
        payload["input"] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        if provider.json_format == "text_format":
            payload["text"] = {"format": {"type": "json_object"}}
        elif provider.json_format == "response_format":
            payload["response_format"] = {"type": "json_object"}
        payload["max_output_tokens"] = max_tokens
        if provider.send_store:
            payload["store"] = False
        if provider.stream:
            payload["stream"] = True
        return payload

    # Request a JSON response from the provider and validate its top-level structure.
    def complete_json(self, system: str, user: str, max_tokens: int) -> dict[str, Any]:
        response = self._post(self._build_payload(system, user, max_tokens))
        output_tokens = None
        try:
            payload = response.json()
            usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
            output_tokens = usage.get("output_tokens")
            logger.info(
                "ai_response_usage provider=%s input_tokens=%s output_tokens=%s max_output_tokens=%s",
                self.provider.name,
                usage.get("input_tokens"),
                output_tokens,
                max_tokens,
            )
            if payload.get("status") != "completed":
                if payload.get("status") == "incomplete":
                    logger.error(
                        "ai_response_incomplete provider=%s reason=%s",
                        self.provider.name,
                        (payload.get("incomplete_details") or {}).get("reason"),
                    )
                raise ValueError("response not completed")
            parts = [
                block["text"]
                for item in payload.get("output", [])
                if isinstance(item, dict) and item.get("type") == "message"
                for block in item.get("content", [])
                if isinstance(block, dict)
                and block.get("type") == "output_text"
                and isinstance(block.get("text"), str)
            ]
            content = "".join(parts)
            if self.settings.log_ai_response_text:
                logger.info(
                    "ai_response_text chars=%s text=%s",
                    len(content),
                    content,
                )
            if not content:
                raise ValueError("empty content")
            result = _parse_json_object(content)
            if not isinstance(result, dict):
                raise ValueError("not an object")
            logger.info(
                "ai_response_parsed content_chars=%s top_level_keys=%s",
                len(content),
                len(result),
            )
            return result
        except (KeyError, ValueError, TypeError) as exc:
            logger.error("ai_response_invalid message=%s", str(exc))
            if isinstance(output_tokens, int) and output_tokens >= max_tokens:
                logger.error(
                    "ai_response_truncated output_tokens=%s max_output_tokens=%s "
                    "hint=increase AI_MAX_OUTPUT_TOKENS",
                    output_tokens,
                    max_tokens,
                )
            raise AIUnavailable("Răspunsul AI nu a putut fi validat. Încercați din nou.") from exc

    # Log fragment counts, documents, metadata, and optionally fragment text at a pipeline stage.
    def _log_fragment_inventory(
        self,
        entries: list[dict[str, str]],
        event: str,
        original_lengths: dict[str, int] | None = None,
    ) -> None:
        """Log the exact evidence inventory at one context-building stage.

        Fragment text logging is intentionally configurable because the evidence
        can contain sensitive medical details. Source and line metadata remain
        available even when text logging is disabled.
        """
        lengths = [len(entry["text"]) for entry in entries]
        total_chars = sum(lengths)
        unique_source_files = {entry["source"].split(":", 1)[0] for entry in entries}
        logger.info(
            "%s count=%s total_chars=%s approx_tokens=%s "
            "documents_count=%s min_chars=%s max_chars=%s text_logging=%s",
            event,
            len(entries),
            total_chars,
            total_chars // 4,
            len(unique_source_files),
            min(lengths, default=0),
            max(lengths, default=0),
            self.settings.log_fragment_text,
        )
        for document in sorted(unique_source_files):
            logger.info("%s_document source=%s", event, document)
        for position, entry in enumerate(entries, start=1):
            text = entry["text"]
            logged_text = (
                text[: self.settings.log_fragment_text_max_chars]
                if self.settings.log_fragment_text
                else "<disabled>"
            )
            logger.info(
                "%s_fragment %s",
                event,
                json.dumps(
                    {
                        "position": position,
                        "id": entry["id"],
                        "source": entry["source"],
                        "text_chars": len(text),
                        "text_logged_chars": len(logged_text) if self.settings.log_fragment_text else 0,
                        "text_truncated_in_log": bool(
                            self.settings.log_fragment_text and len(logged_text) < len(text)
                        ),
                        "original_text_chars": (
                            original_lengths.get(entry["id"], len(text))
                            if original_lengths is not None
                            else len(text)
                        ),
                        "compaction_removed_chars": (
                            max(0, original_lengths.get(entry["id"], len(text)) - len(text))
                            if original_lengths is not None
                            else 0
                        ),
                        "text": logged_text,
                    },
                    ensure_ascii=False,
                ),
            )

    # Convert evidence to AI input entries, ordered by relevance score. Every fragment
    # is sent: the context budget was already applied when the fragments were selected.
    def _evidence_entries(self, evidence: dict[str, dict[str, str]]) -> list[dict[str, str]]:
        return _ordered_entries(evidence)

    # Normalize the structured nutrition object into the internal recommendation-item format.
    def _normalize_nutrition_section(self, value: Any) -> list[dict[str, Any]]:
        fields = (
            ("retete", "[RETETA]"),
            ("recomandate", "[RECOMANDAT]"),
            ("nerecomandate", "[NERECOMANDAT]"),
            ("interzise", "[INTERZIS]"),
            ("alte", "[ALTE]"),
        )
        normalized: list[dict[str, Any]] = []
        if not isinstance(value, dict):
            return normalized
        for field, prefix in fields:
            raw_values = value.get(field)
            if isinstance(raw_values, list):
                values = raw_values
            elif raw_values is None:
                values = []
            else:
                values = [raw_values]
            for raw_value in values:
                evidence_ids: list[str] = []
                if isinstance(raw_value, dict):
                    claim = raw_value.get("text")
                    raw_ids = raw_value.get("evidence_ids", [])
                    if isinstance(raw_ids, list):
                        evidence_ids = [token for token in raw_ids if isinstance(token, str)]
                elif isinstance(raw_value, str):
                    claim = raw_value
                else:
                    continue
                if not isinstance(claim, str):
                    continue
                claim = self._normalize_claim(claim)
                if not claim or claim.strip(" -•\n\t") == "":
                    continue
                normalized.append({
                    "text": f"{prefix}: {claim}",
                    "evidence_ids": evidence_ids,
                })
        return normalized

    # Preserve meaningful line breaks while normalizing text returned by the AI.
    @staticmethod
    def _normalize_claim(claim: str) -> str:
        return "\n".join(
            line.strip()
            for line in claim.replace("\r\n", "\n").split("\n")
            if line.strip()
        )

    # Send the full evidence context to the provider and normalize all returned report sections.
    def generate(
        self, profile: dict[str, Any], evidence: dict[str, dict[str, str]]
    ) -> dict[str, list[dict[str, Any]]]:
        if not evidence:
            logger.info("fragments_sent_to_ai count=0 reason=no_evidence")
            return {name: [] for name in SECTIONS}
        logger.info(
            "fragments_collected_for_ai count=%s total_chars=%s",
            len(evidence),
            sum(len(value.get("text", "")) for value in evidence.values()),
        )
        entries = self._evidence_entries(evidence)
        self._log_fragment_inventory(entries, "fragments_sent_to_ai")
        user = f"""
            Problema pentru care se solicită recomandări naturiste:
            {json.dumps(profile, ensure_ascii=False)}

            Toate fragmentele locale admise:
            {json.dumps(entries, ensure_ascii=False)}
        """.strip()
        logger.info(
            "ai_request_payload_prepared provider=%s chars=%s approx_tokens=%s evidence_entries=%s",
            self.provider.name,
            len(user),
            len(user) // 4,
            len(entries),
        )
        result = self.complete_json(
            self.generate_system_prompt, user, self.provider.max_output_tokens
        )
        sections: dict[str, list[dict[str, Any]]] = {name: [] for name in SECTIONS}
        for section in SECTIONS:
            items = result.get(section, [])
            if section == "nutritie" and isinstance(items, dict):
                sections[section] = self._normalize_nutrition_section(items)
                continue
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                claim = item.get("text")
                if not isinstance(claim, str):
                    continue
                ids = item.get("evidence_ids", [])
                if not isinstance(ids, list):
                    ids = []
                claim = self._normalize_claim(claim)
                evidence_ids = [token for token in ids if isinstance(token, str)]
                if claim:
                    sections[section].append({"text": claim, "evidence_ids": evidence_ids})
        logger.info(
            "ai_report_sections_completed total_items=%s %s",
            sum(len(items) for items in sections.values()),
            " ".join(f"{name}={len(sections[name])}" for name in SECTIONS),
        )
        return sections


class XAIClient(ResponsesClient):
    # The xAI provider, regardless of AI_PROVIDER: same constructor and payload as before.
    def __init__(self, settings: Settings) -> None:
        super().__init__(provider_config(replace(settings, ai_provider="xai")), settings)


# Build the client for the provider selected by AI_PROVIDER.
def create_ai_client(settings: Settings) -> ResponsesClient:
    if settings.ai_provider == "xai":
        return XAIClient(settings)
    return ResponsesClient(provider_config(settings), settings)
