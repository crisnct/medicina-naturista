"""Sequential whole-fragment report batches through the selected AI provider."""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextvars import copy_context
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx

from backend.ai.effort import ollama_think, responses_effort
from backend.ai.providers import ProviderConfig, provider_config
from backend.ai.report_validation import (
    ReportValidationError,
    ValidatedReport,
    report_response_schema,
    validate_report,
)
from backend.config import Settings
from backend.config import settings as default_settings
from backend.core.contracts import (
    AIProtocol,
    Evidence,
    EvidenceTokenBudget,
    ProfilePayload,
    ReportModel,
)
from backend.core.errors import OperationCancelled
from backend.core.language import current_language, language_scope, read_prompt, validate_language
from backend.core.operation_context import (
    ReportActivity,
    checkpoint,
    current_report_effort,
    emit_report_activity,
    emit_report_batch,
    emit_report_output,
    emit_report_thinking,
    remaining_timeout,
    report_batch_context,
    report_effort_scope,
)
from backend.core.report_batches import combine_reports, partition_evidence
from backend.core.report_models import REPORT_MODELS, ReportEffort
from backend.core.texts import tr

logger = logging.getLogger("naturist.ai")

GENERATE_REPORT_SYSTEM_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "generate_report_system.md"
)

# Byte fallback is deliberately conservative; reserve extra space for chat framing.
REPORT_TOKEN_FRAMING_RESERVE = 256


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


# Protocol reasons are application-owned labels, never provider text.
class _AIResponseError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# Recognize technical failures without retaining Ollama's free-form error message.
def _ollama_error_reason(error: Any) -> str:
    message = error.get("message") if isinstance(error, dict) else error
    lowered = message.lower() if isinstance(message, str) else ""
    if "prediction aborted, token repeat limit reached" in lowered:
        return "repetition_limit"
    if "model" in lowered and "not found" in lowered:
        return "model_not_found"
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
        return "context_limit"
    if any(
        marker in lowered
        for marker in ("out of memory", "not enough memory", "cannot allocate memory")
    ):
        return "memory_exhausted"
    if "cuda error" in lowered:
        return "gpu_error"
    if any(marker in lowered for marker in ("failed to load model", "error loading model")):
        return "model_load_failed"
    return "provider_error"


# Keep JSON diagnostics useful without exposing any generated text or source content.
def json_error_details(error: BaseException | None) -> dict[str, int | str]:
    if not isinstance(error, json.JSONDecodeError):
        return {}
    kinds = {
        "Expecting value": "missing_value",
        "Expecting ',' delimiter": "missing_delimiter",
        "Expecting ':' delimiter": "missing_colon",
        "Expecting property name enclosed in double quotes": "invalid_property_name",
        "Unterminated string starting at": "unterminated_string",
        "Invalid control character at": "control_character",
        "Invalid \\escape": "invalid_escape",
        "Invalid \\uXXXX escape": "invalid_unicode_escape",
        "Extra data": "extra_data",
    }
    return {
        "json_error_kind": kinds.get(error.msg, "invalid_json"),
        "json_error_position": error.pos,
        "json_error_line": error.lineno,
        "json_error_column": error.colno,
        "json_document_chars": len(error.doc),
    }


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
        "prompt_eval_cached_count",
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
        self.english_generate_system_prompt = read_prompt(GENERATE_REPORT_SYSTEM_PROMPT_PATH, "en")
        self.batch_max_tokens = settings.report_generation_batch_max_tokens[
            settings.report_generation_model
        ]
        self.batch_workers = settings.report_batch_workers

    def _report_prompt(self) -> str:
        return (
            self.english_generate_system_prompt
            if current_language() == "en"
            else self.generate_system_prompt
        )

    # Whether the active provider can be called (its key is present when one is required).
    def is_configured(self) -> bool:
        return not self.provider.api_key_required or bool(self.provider.api_key())

    # Keep token budgets explicit at the retrieval boundary.
    def context_budget(self) -> int | EvidenceTokenBudget:
        if self.provider.max_content_tokens is not None:
            return EvidenceTokenBudget(self.provider.max_content_tokens)
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
                tr(
                    "errors.ai_key_missing",
                    variable=self.provider.api_key_env,
                )
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
            reason = "http_error"
            if self.provider.name == "ollama":
                try:
                    error = response.json()
                except ValueError:
                    error = None
                reason = _ollama_error_reason(
                    error.get("error") if isinstance(error, dict) else None
                )
            logger.error(
                "ai_request_failed provider=%s model=%s stage=http status=%s "
                "reason=%s duration_ms=%s request_id=%s body=%s",
                self.provider.name,
                self.provider.model,
                response.status_code,
                reason,
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
                "ai_request_failed provider=%s model=%s stage=transport error=%s "
                "duration_ms=%s type=%s",
                self.provider.name,
                self.provider.model,
                "timeout" if isinstance(exc, httpx.TimeoutException) else "connection",
                round((time.perf_counter() - started) * 1000),
                type(exc).__name__,
            )
            raise AIUnavailable(
                tr("errors.ai_unavailable"),
                reason="timeout" if isinstance(exc, httpx.TimeoutException) else "unavailable",
            ) from exc
        except (ValueError, TypeError, KeyError) as exc:
            logger.error(
                "ai_request_failed provider=%s model=%s stage=protocol error=%s "
                "duration_ms=%s type=%s details=%s",
                self.provider.name,
                self.provider.model,
                exc.reason if isinstance(exc, _AIResponseError) else "invalid_response",
                round((time.perf_counter() - started) * 1000),
                type(exc).__name__,
                json_error_details(exc),
            )
            raise AIUnavailable(
                tr("errors.ai_unavailable"),
                reason="invalid_response",
            ) from exc
        except AIUnavailable as exc:
            logger.error(
                "ai_request_failed provider=%s model=%s stage=provider reason=%s duration_ms=%s",
                self.provider.name,
                self.provider.model,
                exc.reason,
                round((time.perf_counter() - started) * 1000),
            )
            raise
        except OperationCancelled:
            logger.info(
                "ai_request_cancelled provider=%s model=%s duration_ms=%s",
                self.provider.name,
                self.provider.model,
                round((time.perf_counter() - started) * 1000),
            )
            raise
        except Exception as exc:
            # Record unexpected failures without serializing sensitive exception arguments.
            logger.error(
                "ai_request_failed provider=%s model=%s stage=request "
                "error=unexpected type=%s duration_ms=%s",
                self.provider.name,
                self.provider.model,
                type(exc).__name__,
                round((time.perf_counter() - started) * 1000),
            )
            raise

    # Build the Responses API request body for this provider.
    def _build_payload(
        self, system: str, user: str, max_tokens: int, *, schema: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        provider = self.provider
        payload: dict[str, Any] = {"model": provider.model}
        effort = current_report_effort()
        if provider.effort_control == "responses_effort" and effort is not None:
            payload["reasoning"] = {"effort": responses_effort(effort)}
        elif provider.reasoning_effort:
            payload["reasoning"] = {"effort": provider.reasoning_effort}
        payload["input"] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if provider.json_format == "text_format":
            payload["text"] = {"format": {"type": "json_object"}}
        elif provider.json_format == "response_format":
            payload["response_format"] = {"type": "json_object"}
        schema = provider.response_schema if schema is None else schema
        if schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "structured_response",
                    "schema": schema,
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

    def _parse_content(self, content: str) -> Any:
        return _parse_json_object(content)

    # Request a JSON response from the provider and validate its top-level structure.
    def complete_json(self, system: str, user: str, max_tokens: int) -> dict[str, Any]:
        return self._complete_json(system, user, max_tokens)

    # Report schemas stay request-local and do not change classifier client configuration.
    def _complete_json(
        self, system: str, user: str, max_tokens: int, *, schema: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        response = self._post(self._build_payload(system, user, max_tokens, schema=schema))
        output_tokens = None
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise _AIResponseError("invalid_response_object")
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
            if content and not isinstance(response, _StreamedResponse):
                emit_report_output(content)
            raw_usage = payload.get("usage")
            usage = _response_metrics({"usage": raw_usage})
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
                        "ai_response_failed stage=response provider=%s model=%s reason=%s",
                        self.provider.name,
                        self.provider.model,
                        reason,
                    )
                    raise AIUnavailable(
                        "Hugging Face nu mai are credite disponibile."
                        if no_credits
                        else tr("errors.ai_request_failed"),
                        reason=reason,
                    )
                if payload.get("status") == "incomplete":
                    incomplete_reason = (payload.get("incomplete_details") or {}).get("reason")
                    logger.error(
                        "ai_response_incomplete provider=%s model=%s reason=%s",
                        self.provider.name,
                        self.provider.model,
                        incomplete_reason
                        if incomplete_reason == "max_output_tokens"
                        else "unknown",
                    )
                    if incomplete_reason == "max_output_tokens":
                        raise AIUnavailable(
                            tr("errors.ai_output_limit"),
                            reason="output_limit",
                        )
                raise _AIResponseError("not_completed")
            if not content:
                raise _AIResponseError("empty_content")
            result = self._parse_content(content)
            if not isinstance(result, dict):
                raise _AIResponseError("invalid_json_object")
            logger.info(
                "ai_response_parsed content_chars=%s top_level_keys=%s",
                len(content),
                len(result),
            )
            return result
        except (KeyError, ValueError, TypeError) as exc:
            logger.error(
                "ai_response_invalid provider=%s model=%s stage=json reason=%s type=%s details=%s",
                self.provider.name,
                self.provider.model,
                exc.reason if isinstance(exc, _AIResponseError) else "invalid_response",
                type(exc).__name__,
                json_error_details(exc),
            )
            if isinstance(output_tokens, int) and output_tokens >= max_tokens:
                logger.error(
                    "ai_response_truncated provider=%s model=%s output_tokens=%s max_output_tokens=%s "
                    "hint=increase REPORT_GENERATION_MAX_OUTPUT_TOKENS",
                    self.provider.name,
                    self.provider.model,
                    output_tokens,
                    max_tokens,
                )
            raise AIUnavailable(
                tr("errors.ai_response_invalid"), reason="invalid_response"
            ) from exc
        except (AIUnavailable, OperationCancelled):
            raise
        except Exception as exc:
            logger.error(
                "ai_response_invalid provider=%s model=%s stage=json error=unexpected type=%s",
                self.provider.name,
                self.provider.model,
                type(exc).__name__,
            )
            raise

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
            "%s count=%s total_chars=%s content_tokens_upper_bound=%s counting=utf8_bytes "
            "documents_count=%s min_chars=%s max_chars=%s text_logging=%s",
            event,
            len(entries),
            total_chars,
            len(json.dumps(entries, ensure_ascii=False).encode("utf-8")),
            len(unique_source_files),
            min(lengths, default=0),
            max(lengths, default=0),
            self.settings.log_fragment_text,
        )

    # Convert evidence to AI input entries, ordered by relevance score. Every fragment
    # is sent: the context budget was already applied when the fragments were selected.
    def _evidence_entries(self, evidence: Evidence) -> list[dict[str, str]]:
        return _ordered_entries(evidence)

    def _report_user_message(self, profile: ProfilePayload, evidence: Evidence) -> str:
        if current_language() == "en":
            return (
                "Health problem for natural recommendations:\n"
                + json.dumps(profile, ensure_ascii=False)
                + "\nAll approved local excerpts:\n"
                + json.dumps(self._evidence_entries(evidence), ensure_ascii=False)
            )
        return f"""
            Problema pentru care se solicită recomandări naturiste:
            {json.dumps(profile, ensure_ascii=False)}

            Toate fragmentele locale admise:
            {json.dumps(self._evidence_entries(evidence), ensure_ascii=False)}
        """.strip()

    # Use the same payload as generation, including the schema's batch-local citation IDs.
    def _report_input_tokens(self, profile: ProfilePayload, evidence: Evidence) -> int:
        checkpoint()
        payload = self._build_payload(
            self._report_prompt(),
            self._report_user_message(profile, evidence),
            self.provider.max_output_tokens,
            schema=report_response_schema(evidence) if self.provider.name == "ollama" else None,
        )
        return (
            len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            + REPORT_TOKEN_FRAMING_RESERVE
        )

    def _report_input_limit(self) -> int:
        limit = self.batch_max_tokens
        if self.provider.context_tokens is not None:
            limit = min(limit, self.provider.context_tokens - self.provider.max_output_tokens)
        return limit

    # The single FIFO report owner drains all batch workers before releasing its capacity.
    def generate(
        self, profile: ProfilePayload, evidence: Evidence, effort: ReportEffort | None = None
    ) -> ValidatedReport:
        language = validate_language(profile.get("language", current_language()))
        if any(item.get("language", language) != language for item in evidence.values()):
            raise AIUnavailable(
                tr("errors.search_evidence_missing", language=language), reason="invalid_response"
            )
        with language_scope(language), report_effort_scope(effort):
            return self._generate(profile, evidence)

    def _generate(self, profile: ProfilePayload, evidence: Evidence) -> ValidatedReport:
        if not evidence:
            logger.info("fragments_sent_to_ai count=0 reason=no_evidence")
            return validate_report({}, evidence)
        logger.info(
            "fragments_collected_for_ai count=%s total_chars=%s",
            len(evidence),
            sum(len(value.get("text", "")) for value in evidence.values()),
        )
        input_limit = self._report_input_limit()
        if input_limit <= 0:
            raise AIUnavailable(tr("errors.ai_context_limit"), reason="context_limit")
        batches = partition_evidence(
            evidence, input_limit, lambda batch: self._report_input_tokens(profile, batch)
        )
        emit_report_batch(0, len(batches))
        reports: dict[int, ValidatedReport] = {}
        stopped = threading.Event()
        failure_lock = threading.Lock()
        failures: list[BaseException] = []

        def record_failure(exc: BaseException) -> None:
            with failure_lock:
                if not failures:
                    failures.append(exc)
                stopped.set()

        def generate_batch(index: int, batch: Evidence) -> ValidatedReport:
            with report_batch_context(index, stopped.is_set):
                try:
                    result = self._run_report_batch(profile, batch, index, len(batches))
                    checkpoint()
                    emit_report_batch(index, len(batches), result)
                    logger.info(
                        "report_batch_completed provider=%s batch=%s total=%s",
                        self.provider.name,
                        index,
                        len(batches),
                    )
                    return result
                except Exception as exc:
                    record_failure(exc)
                    try:
                        emit_report_activity(
                            ReportActivity(
                                "batch_cancelled"
                                if isinstance(exc, OperationCancelled)
                                else "batch_failed"
                            )
                        )
                    except OperationCancelled:
                        # Explicit user cancellation may already have invalidated the session operation.
                        pass
                    log_failure = (
                        logger.info if isinstance(exc, OperationCancelled) else logger.error
                    )
                    log_failure(
                        "report_batch_failed provider=%s model=%s batch=%s total=%s type=%s",
                        self.provider.name,
                        self.provider.model,
                        index,
                        len(batches),
                        type(exc).__name__,
                    )
                    raise

        executor = ThreadPoolExecutor(
            max_workers=self.batch_workers, thread_name_prefix="report-batch"
        )
        pending: dict[Future[ValidatedReport], int] = {}
        next_index = 1
        try:
            while next_index <= len(batches) or pending:
                checkpoint()
                while (
                    not stopped.is_set()
                    and next_index <= len(batches)
                    and len(pending) < self.batch_workers
                ):
                    context = copy_context()
                    future = executor.submit(
                        context.run, generate_batch, next_index, batches[next_index - 1]
                    )
                    pending[future] = next_index
                    next_index += 1
                if not pending:
                    break
                completed, _ = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                # Observe every completed future before admitting replacement work.
                for future in completed:
                    reports[pending.pop(future)] = future.result()
        except BaseException as exc:
            # Preserve the initiating failure even if a sibling notices cooperative cancellation first.
            record_failure(exc)
        finally:
            if failures:
                stopped.set()
                for future in pending:
                    future.cancel()
            executor.shutdown(wait=True, cancel_futures=True)
        if failures:
            raise failures[0]
        checkpoint()
        combined = combine_reports([reports[index] for index in range(1, len(batches) + 1)])
        return validate_report(combined.section_payload(), evidence, strict=True)

    def _run_report_batch(
        self, profile: ProfilePayload, batch: Evidence, index: int, total: int
    ) -> ValidatedReport:
        checkpoint()
        logger.info(
            "report_batch_started provider=%s model=%s parallel_limit=%s batch=%s total=%s "
            "fragments=%s chars=%s input_tokens_upper_bound=%s input_limit=%s counting=utf8_bytes",
            self.provider.name,
            self.provider.model,
            self.batch_workers,
            index,
            total,
            len(batch),
            sum(len(item["text"]) for item in batch.values()),
            self._report_input_tokens(profile, batch),
            self._report_input_limit(),
        )
        try:
            result = self._generate_batch(profile, batch)
        except ReportValidationError as exc:
            logger.error(
                "ai_report_validation_failed provider=%s model=%s batch=%s total=%s "
                "reason=%s issues=%s details=%s",
                self.provider.name,
                self.provider.model,
                index,
                total,
                "REPORT_EMPTY" if str(exc) == "REPORT_EMPTY" else "REPORT_INVALID",
                dict(Counter(warning.code for warning in exc.warnings)),
                [warning.model_dump(exclude_none=True) for warning in exc.warnings[:20]],
            )
            raise
        checkpoint()
        return result

    # Every request uses the original prompt and validates citations against only its own batch.
    def _generate_batch(self, profile: ProfilePayload, evidence: Evidence) -> ValidatedReport:
        input_tokens = self._report_input_tokens(profile, evidence)
        input_limit = self._report_input_limit()
        if input_tokens > input_limit:
            if len(evidence) != 1:
                raise AIUnavailable(tr("errors.ai_context_limit"), reason="context_limit")
            logger.info(
                "report_batch_token_limit_bypassed provider=%s model=%s fragments=1 "
                "input_tokens_upper_bound=%s input_limit=%s counting=utf8_bytes",
                self.provider.name,
                self.provider.model,
                input_tokens,
                input_limit,
            )
        entries = self._evidence_entries(evidence)
        self._log_fragment_inventory(entries, "fragments_sent_to_ai")
        user = self._report_user_message(profile, evidence)
        logger.info(
            "ai_request_payload_prepared provider=%s chars=%s input_tokens_upper_bound=%s "
            "evidence_entries=%s counting=utf8_bytes",
            self.provider.name,
            len(user),
            input_tokens,
            len(entries),
        )
        if self.provider.name == "ollama":
            result = self._complete_json(
                self._report_prompt(),
                user,
                self.provider.max_output_tokens,
                schema=report_response_schema(evidence),
            )
        else:
            result = self.complete_json(
                self._report_prompt(), user, self.provider.max_output_tokens
            )
        return validate_report(result, evidence, allow_empty=True, strict=True)


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
        reason = _ollama_error_reason(error)
        if reason == "model_not_found":
            logger.warning("ai_model_not_found provider=ollama")
            raise AIUnavailable(
                "Modelul Ollama selectat nu este instalat sau nu este disponibil.",
                reason="model_not_found",
            )
        if reason == "context_limit":
            logger.warning("ai_context_limit_exceeded provider=ollama truncation=disabled")
            raise AIUnavailable(
                tr("errors.ai_context_limit"),
                reason="context_limit",
            )
        if reason == "repetition_limit":
            logger.warning("ai_repetition_limit_exceeded provider=ollama")
            raise AIUnavailable(tr("errors.ai_repetition_limit"), reason="repetition_limit")
        raise _AIResponseError(reason)

    def _send(self, headers: dict[str, str], payload: dict[str, Any]) -> Any:
        native: dict[str, Any] = {
            "model": payload["model"],
            "messages": payload["input"],
            "stream": bool(payload.get("stream")),
            "format": payload.get("text", {}).get("format", {}).get("schema")
            or self.provider.response_schema
            or "json",
            "truncate": False,
            "shift": False,
            "options": {"num_predict": payload["max_output_tokens"]},
        }
        if self.provider.context_tokens is not None:
            native["options"]["num_ctx"] = self.provider.context_tokens
        effort = current_report_effort()
        if self.provider.effort_control == "ollama_think" and effort is not None:
            native["think"] = ollama_think(effort)
        elif self.provider.thinking is not None:
            native["think"] = self.provider.thinking
        if self.provider.keep_alive_seconds is not None:
            native["keep_alive"] = self.provider.keep_alive_seconds
        if "temperature" in payload:
            native["options"]["temperature"] = payload["temperature"]
        if self.provider.repeat_penalty is not None:
            native["options"]["repeat_penalty"] = self.provider.repeat_penalty
        if self.provider.repeat_last_n is not None:
            native["options"]["repeat_last_n"] = self.provider.repeat_last_n
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
                    raise _AIResponseError("invalid_event")
                self._check_native_error(event)
                if "done" in event and type(event["done"]) is not bool:
                    raise _AIResponseError("invalid_done_flag")
                if "message" not in event and not event.get("done"):
                    raise _AIResponseError("missing_message")
                message = event.get("message", {})
                if not isinstance(message, dict):
                    raise _AIResponseError("invalid_message")
                emit_report_activity(ReportActivity("provider_activity"))
                thinking = message.get("thinking")
                if thinking is not None and not isinstance(thinking, str):
                    raise _AIResponseError("invalid_thinking")
                if isinstance(thinking, str):
                    emit_report_thinking(thinking)
                content = message.get("content")
                if content is not None and not isinstance(content, str):
                    raise _AIResponseError("invalid_content")
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
                raise _AIResponseError("missing_completion")
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
    if settings.ai_provider == "ollama":
        return OllamaReportClient(provider_config(settings), settings)
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
