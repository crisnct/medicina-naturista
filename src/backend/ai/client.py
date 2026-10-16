"""Single-request report generation through a Responses API provider (xAI, Hugging Face, Ollama)."""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx

from backend.ai.providers import ProviderConfig, provider_config
from backend.ai.report_validation import ValidatedReport, validate_report
from backend.config import Settings
from backend.config import settings as default_settings
from backend.core.contracts import AIProtocol, Evidence, ProfilePayload, ReportModel
from backend.core.operation_context import (
    ReportActivity,
    checkpoint,
    emit_report_activity,
    emit_report_output,
    emit_report_thinking,
    remaining_timeout,
)
from backend.core.report_models import REPORT_MODELS

logger = logging.getLogger("naturist.ai")

GENERATE_REPORT_SYSTEM_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "generate_report_system.md"
)


# Evidence fragments as the AI request carries them, highest score first.
def _ordered_entries(evidence: Evidence) -> list[dict[str, str]]:
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
    def __init__(self, message: str, *, reason: str = "unavailable") -> None:
        super().__init__(message)
        self.reason = reason


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
    def __init__(
        self, payload: dict[str, Any], status_code: int, headers: Any, raw_bytes: int
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = headers
        self.content = b""
        self.raw_bytes = raw_bytes

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def _response_metrics(response: dict[str, Any]) -> dict[str, int | float]:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return {}
    values = {key: usage.get(key) for key in ("input_tokens", "output_tokens")}
    details = usage.get("output_tokens_details")
    if isinstance(details, dict):
        values["reasoning_tokens"] = details.get("reasoning_tokens")
    return {
        key: value
        for key, value in values.items()
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    }


def _ollama_metrics(response: dict[str, Any]) -> dict[str, int | float]:
    result: dict[str, int | float] = {}
    for key in (
        "load_duration",
        "prompt_eval_duration",
        "eval_duration",
        "total_duration",
        "prompt_eval_count",
        "eval_count",
    ):
        value = response.get(key)
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value >= 0
        ):
            result[f"{key}_ms" if key.endswith("duration") else key] = (
                value / 1_000_000 if key.endswith("duration") else value
            )
    return result


# Fold Responses API server-sent events into the final response object.
def _collect_stream(lines: Any) -> tuple[dict[str, Any], int]:
    deltas: list[str] = []
    raw_bytes = 0
    for line in lines:
        checkpoint()
        raw_bytes += len(line) + 1
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        event = json.loads(data)
        if not isinstance(event, dict):
            raise ValueError("Invalid Responses stream event")
        kind = event.get("type")
        if kind == "response.output_text.delta" and isinstance(event.get("delta"), str):
            deltas.append(event["delta"])
            emit_report_output(event["delta"])
        elif kind == "response.reasoning_text.delta" and isinstance(event.get("delta"), str):
            emit_report_thinking(event["delta"])
        elif kind in (
            "response.created",
            "response.in_progress",
            "response.output_item.added",
            "response.output_item.done",
            "response.content_part.added",
            "response.content_part.done",
            "response.reasoning_text.done",
            "response.output_text.done",
        ):
            emit_report_activity(ReportActivity("provider_activity"))
        elif kind in ("response.completed", "response.incomplete", "response.failed"):
            final = event.get("response")
            if not isinstance(final, dict):
                raise ValueError(f"{kind} without response object")
            emit_report_activity(ReportActivity("response_finished", _response_metrics(final)))
            if kind == "response.failed":
                raise ValueError(f"response failed: {final.get('error')}")
            if kind == "response.completed" and not final.get("output") and deltas:
                # Some servers end the stream without repeating the output.
                final = {
                    **final,
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "".join(deltas)}],
                        }
                    ],
                }
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
        timeout = httpx.Timeout(
            remaining_timeout(float(self.provider.read_timeout_seconds)),
            connect=remaining_timeout(10.0),
        )
        emit_report_activity(ReportActivity("request_started"))
        if not self.provider.stream:
            response = self.http.post(url, headers=headers, json=payload, timeout=timeout)
            checkpoint()
            if getattr(response, "status_code", 200) < 400:
                final = response.json()
                if isinstance(final, dict):
                    emit_report_activity(
                        ReportActivity("response_finished", _response_metrics(final))
                    )
            return response
        with self.http.stream(
            "POST",
            url,
            headers={**headers, "Accept": "text/event-stream"},
            json=payload,
            timeout=timeout,
        ) as response:
            if response.status_code >= 400:
                response.read()
                response.raise_for_status()
            final, raw_bytes = _collect_stream(response.iter_lines())
            return _StreamedResponse(final, response.status_code, response.headers, raw_bytes)

    # Send one request to the provider's Responses API with diagnostic logging.
    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        key = self.provider.api_key()
        if not key and self.provider.api_key_required:
            logger.error(
                "ai_request_skipped reason=missing_api_key provider=%s", self.provider.name
            )
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
            request_id = (
                response.headers.get("x-request-id") or response.headers.get("request-id") or "-"
            )
            body = "<redacted>"
            logger.error(
                "ai_request_failed status=%s duration_ms=%s request_id=%s body=%s",
                response.status_code,
                round((time.perf_counter() - started) * 1000),
                request_id,
                body[:12000],
            )
            raise AIUnavailable(
                f"Serviciul AI ({self.provider.label}) a respins cererea "
                f"(HTTP {response.status_code}, request_id={request_id}).",
                reason="rate_limited" if response.status_code == 429 else "unavailable",
            ) from exc
        except httpx.RequestError as exc:
            logger.error(
                "ai_request_failed error=request duration_ms=%s message=%s",
                round((time.perf_counter() - started) * 1000),
                type(exc).__name__,
            )
            raise AIUnavailable(
                "Serviciul AI nu este disponibil momentan. Încercați din nou.",
                reason="timeout" if isinstance(exc, httpx.TimeoutException) else "unavailable",
            ) from exc
        except ValueError as exc:
            logger.error(
                "ai_request_failed error=invalid_response duration_ms=%s message=%s",
                round((time.perf_counter() - started) * 1000),
                type(exc).__name__,
            )
            raise AIUnavailable(
                "Serviciul AI nu este disponibil momentan. Încercați din nou.",
                reason="invalid_response",
            ) from exc

    # Build the Responses API request body for this provider.
    def _build_payload(self, system: str, user: str, max_tokens: int) -> dict[str, Any]:
        provider = self.provider
        payload: dict[str, Any] = {"model": provider.model}
        if provider.reasoning_effort:
            payload["reasoning"] = {"effort": provider.reasoning_effort}
        payload["input"] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if provider.json_format == "text_format":
            payload["text"] = {"format": {"type": "json_object"}}
        elif provider.json_format == "response_format":
            payload["response_format"] = {"type": "json_object"}
        if provider.response_schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "message_classification",
                    "schema": provider.response_schema,
                    "strict": True,
                }
            }
        payload["max_output_tokens"] = max_tokens
        if provider.temperature is not None:
            payload["temperature"] = provider.temperature
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
                if payload.get("status") == "failed":
                    error = payload.get("error")
                    error_message = error.get("message", "") if isinstance(error, dict) else ""
                    no_credits = (
                        self.provider.name == "huggingface"
                        and isinstance(error_message, str)
                        and error_message.lstrip().startswith("402 ")
                    )
                    reason = "credits_exhausted" if no_credits else "provider_failed"
                    logger.error(
                        "ai_response_failed stage=response provider=%s reason=%s",
                        self.provider.name,
                        reason,
                    )
                    raise AIUnavailable(
                        "Hugging Face nu mai are credite disponibile."
                        if no_credits
                        else "Furnizorul AI a raportat eșecul cererii.",
                        reason=reason,
                    )
                if payload.get("status") == "incomplete":
                    incomplete_reason = (payload.get("incomplete_details") or {}).get("reason")
                    logger.error(
                        "ai_response_incomplete provider=%s reason=%s",
                        self.provider.name,
                        incomplete_reason,
                    )
                    if incomplete_reason == "max_output_tokens":
                        raise AIUnavailable(
                            "Modelul AI a atins limita de tokeni a răspunsului înainte de finalizarea raportului.",
                            reason="output_limit",
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
            logger.error("ai_response_invalid type=%s", type(exc).__name__)
            if isinstance(output_tokens, int) and output_tokens >= max_tokens:
                logger.error(
                    "ai_response_truncated output_tokens=%s max_output_tokens=%s "
                    "hint=increase REPORT_GENERATION_MAX_OUTPUT_TOKENS",
                    output_tokens,
                    max_tokens,
                )
            raise AIUnavailable(
                "Răspunsul AI nu a putut fi validat. Încercați din nou.", reason="invalid_response"
            ) from exc

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

    # Convert evidence to AI input entries, ordered by relevance score. Every fragment
    # is sent: the context budget was already applied when the fragments were selected.
    def _evidence_entries(self, evidence: Evidence) -> list[dict[str, str]]:
        return _ordered_entries(evidence)

    # Send the full evidence context to the provider and normalize all returned report sections.
    def generate(self, profile: ProfilePayload, evidence: Evidence) -> ValidatedReport:
        if not evidence:
            logger.info("fragments_sent_to_ai count=0 reason=no_evidence")
            return validate_report({}, evidence)
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
        return validate_report(result, evidence)


class OllamaReportClient(ResponsesClient):
    """Native report transport: preserve the entire input and disable context shifting.

    Ollama 0.40.4 does not forward Responses.truncation to its native chat request.
    Keep the common report validation and use native controls for this transport.
    """

    @staticmethod
    def _check_native_error(event: dict[str, Any]) -> None:
        error = event.get("error")
        if not error:
            return
        message = error.get("message", "") if isinstance(error, dict) else str(error)
        lowered = message.lower()
        if "model" in lowered and "not found" in lowered:
            logger.warning("ai_model_not_found provider=ollama")
            raise AIUnavailable(
                "Modelul Ollama selectat nu este instalat sau nu este disponibil.",
                reason="model_not_found",
            )
        if any(
            marker in lowered
            for marker in (
                "exceeds the available context",
                "input length exceeds the context",
                "context size has been exceeded",
                "context window is full",
                "context length exceeded",
                "maximum context length",
                "context_length_exceeded",
                "context shift is disabled",
                "prompt is too long",
            )
        ):
            logger.warning("ai_context_limit_exceeded provider=ollama truncation=disabled")
            raise AIUnavailable(
                "Fragmentele selectate depășesc contextul disponibil al modelului. "
                "Selectați mai puține fragmente sau creșteți scorul minim. "
                "Conținutul nu a fost trunchiat.",
                reason="context_limit",
            )
        raise ValueError("Ollama reported a generation error")

    def _send(self, headers: dict[str, str], payload: dict[str, Any]) -> Any:
        native: dict[str, Any] = {
            "model": payload["model"],
            "messages": payload["input"],
            "stream": bool(payload.get("stream")),
            "format": "json",
            "truncate": False,
            "shift": False,
            "options": {"num_predict": payload["max_output_tokens"]},
        }
        # Gemma4 and Qwen3.5 support boolean thinking; omit it for Gemma3 and Ministral.
        effort = payload.get("reasoning", {}).get("effort")
        if effort and self.provider.model.startswith(("gemma4:", "qwen3.5:")):
            native["think"] = effort != "none"
        if "temperature" in payload:
            native["options"]["temperature"] = payload["temperature"]
        url = f"{self.provider.base_url.removesuffix('/v1')}/api/chat"
        timeout = httpx.Timeout(
            remaining_timeout(float(self.provider.read_timeout_seconds)),
            connect=remaining_timeout(10.0),
        )
        parts: list[str] = []
        raw_bytes = 0
        final = None
        emit_report_activity(ReportActivity("request_started"))
        with self.http.stream(
            "POST", url, headers=headers, json=native, timeout=timeout
        ) as response:
            if response.status_code >= 400:
                response.read()
                try:
                    error = response.json()
                except ValueError:
                    error = {}
                if isinstance(error, dict):
                    # Inspect only known context errors; keep normal HTTP error handling otherwise.
                    try:
                        self._check_native_error(error)
                    except ValueError:
                        pass
                response.raise_for_status()
            for line in response.iter_lines():
                checkpoint()
                raw_bytes += len(line.encode("utf-8")) + 1
                if not line:
                    continue
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("Invalid Ollama stream event")
                self._check_native_error(event)
                if "message" not in event and not event.get("done"):
                    raise ValueError("Ollama event without message or completion")
                message = event.get("message") or {}
                if not isinstance(message, dict):
                    raise ValueError("Invalid Ollama message")
                emit_report_activity(ReportActivity("provider_activity"))
                thinking = message.get("thinking")
                if isinstance(thinking, str):
                    emit_report_thinking(thinking)
                content = message.get("content")
                if isinstance(content, str):
                    parts.append(content)
                    emit_report_output(content)
                if event.get("done"):
                    final = event
                    emit_report_activity(
                        ReportActivity("response_finished", _ollama_metrics(event))
                    )
                    break
            if final is None:
                raise ValueError("Ollama stream ended before completion")
            if (
                final.get("done_reason") == "length"
                and final.get("eval_count", 0) < payload["max_output_tokens"]
            ):
                self._check_native_error({"error": "context window is full"})
            result = {
                "status": "incomplete" if final.get("done_reason") == "length" else "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "".join(parts)}],
                    }
                ],
                "usage": {
                    "input_tokens": final.get("prompt_eval_count"),
                    "output_tokens": final.get("eval_count"),
                },
                "incomplete_details": {"reason": "max_output_tokens"},
            }
            return _StreamedResponse(result, response.status_code, response.headers, raw_bytes)


class XAIClient(ResponsesClient):
    # Explicit xAI constructor, independent of the selected default report model.
    def __init__(self, settings: Settings) -> None:
        super().__init__(provider_config(replace(settings, ai_provider="xai")), settings)


# Build a generic client using the already resolved provider settings.
def create_ai_client(settings: Settings) -> ResponsesClient:
    if settings.ai_provider == "xai":
        return XAIClient(settings)
    return ResponsesClient(provider_config(settings), settings)


def create_report_clients(settings: Settings) -> dict[ReportModel, AIProtocol]:
    """Independent clients for UI choices; never mutate process-wide settings."""
    clients: dict[ReportModel, AIProtocol] = {}
    try:
        for choice in settings.report_generation_models:
            spec = REPORT_MODELS[choice]
            selected = replace(
                settings,
                report_generation_models=(choice,),
                ai_provider=spec.provider,
                ollama_model=spec.model if spec.provider == "ollama" else settings.ollama_model,
                deepseek_model=spec.model
                if spec.provider == "deepseek"
                else settings.deepseek_model,
                hf_model=spec.model if spec.provider == "huggingface" else settings.hf_model,
                xai_model=spec.model if spec.provider == "xai" else settings.xai_model,
            )
            clients[choice] = (
                OllamaReportClient(provider_config(selected), selected)
                if spec.provider == "ollama"
                else create_ai_client(selected)
            )
        return clients
    except Exception:
        for client in clients.values():
            client.close()
        raise
