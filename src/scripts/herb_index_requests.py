"""Stream one indexing request per batch and emit aggregate telemetry without source content."""

from __future__ import annotations

import json
import math
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from contextvars import copy_context
from dataclasses import replace
from typing import Any, Literal

from backend.ai.client import AIUnavailable, OllamaReportClient, ResponsesClient, json_error_details
from backend.ai.herb_association_classification import make_client as association_client
from backend.ai.herb_association_classification import response_schema
from backend.ai.herb_product_safety import product_response_schema
from backend.config import Settings
from backend.core.errors import OperationCancelled
from backend.core.operation_context import (
    OperationBudget,
    ReportActivity,
    checkpoint,
    operation_budget,
    remaining_timeout,
)

BatchKind = Literal["associations", "combined", "warnings_only", "product_safety"]
METRIC_KEYS = (
    "load_duration_ms",
    "prompt_eval_duration_ms",
    "eval_duration_ms",
    "total_duration_ms",
    "prompt_eval_count",
    "prompt_eval_cached_count",
    "eval_count",
)
FAILURE_REASONS = frozenset(
    {
        "timeout",
        "unavailable",
        "rate_limited",
        "invalid_response",
        "output_limit",
        "context_limit",
        "model_not_found",
        "provider_failed",
    }
)
_OUTPUT_LOCK = threading.Lock()


# Heartbeats and batch events share stdout; each JSON record must remain a complete line.
def emit_index_event(value: dict[str, Any]) -> None:
    line = json.dumps(value)
    with _OUTPUT_LOCK:
        print(line, flush=True)


# Compound statements can support several warnings, so a focus is not a one-message quota.
def warning_item_limit(statement_count: int, kind_count: int, source_words: int) -> int:
    return max(kind_count * statement_count, source_words)


# Native grammars may ignore uniqueItems, so every generated list also needs a source-derived bound.
def index_response_schema(payload: dict[str, Any]) -> dict[str, Any]:
    if "product" in payload:
        return product_response_schema(payload["product"]["id"])
    schema = response_schema(payload)
    if "safety_targets" not in payload:
        return schema
    warnings = schema["properties"]["warnings"]["properties"]
    for target in payload["safety_targets"]:
        items = warnings[target["id"]]["properties"]["items"]
        if items.get("maxItems") == 0:
            continue
        # A raw regex character class can admit unescaped JSON quotes and backslashes.
        # minLength/maxLength retain bounded strings through the native JSON character rule.
        items["items"]["properties"]["summary"].pop("pattern", None)
        unit = payload["units"][target["unit"]]
        count = len(target["warning_statement_ids"])
        kinds = len(items["items"]["properties"]["kind"]["enum"])
        items["maxItems"] = warning_item_limit(count, kinds, target["warning_source_words"])
        # Each explicit interaction partner needs at least one word in the source.
        items["items"]["properties"]["partners"]["maxItems"] = len(unit["text"].split())
    return schema


# This transport policy leaves validated decisions and their semantic cache identities unchanged.
class IndexClient(OllamaReportClient):
    _product_request = False

    def complete_json(self, system: str, user: str, max_tokens: int) -> dict[str, Any]:
        payload = json.loads(user)
        self._product_request = "product" in payload
        self.provider = replace(self.provider, response_schema=index_response_schema(payload))
        return super().complete_json(system, user, max_tokens)

    def _parse_content(self, content: str) -> Any:
        if not self._product_request:
            return super()._parse_content(content)

        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            value: dict[str, Any] = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("HERB_PRODUCT_SAFETY_DUPLICATE_KEY")
                value[key] = item
            return value

        def reject_constant(_value: str) -> Any:
            raise ValueError("HERB_PRODUCT_SAFETY_NONFINITE_JSON")

        return json.loads(content, object_pairs_hook=unique_object, parse_constant=reject_constant)


# Retain the original local-only settings and proxy restrictions while transferring HTTP ownership.
def make_client(settings: Settings) -> ResponsesClient:
    with ExitStack() as cleanup:
        template = association_client(settings)
        cleanup.callback(template.close)
        client = IndexClient(
            replace(
                template.provider,
                stream=True,
                keep_alive_seconds=settings.herb_association_ai_keep_alive_seconds,
            ),
            template.settings,
        )
        client.http.close()
        client.http = template.http
        cleanup.pop_all()
    return client


class BatchTelemetry:
    def __init__(self, metadata: dict[str, Any], clock: Callable[[], float]) -> None:
        self.metadata = metadata
        self.clock = clock
        self.started = clock()
        self.first_chunk_ms: float | None = None
        self.first_output_ms: float | None = None
        self.last_activity_ms: float | None = None
        self.stream_events = 0
        self.output_chars = 0
        self.thinking_chars = 0
        self.metrics: dict[str, int | float | None] = dict.fromkeys(METRIC_KEYS)

    def activity(self, event: ReportActivity) -> None:
        elapsed = round(max(0.0, self.clock() - self.started) * 1000, 3)
        if event.kind == "provider_activity":
            self.stream_events += 1
            self.last_activity_ms = elapsed
            if self.first_chunk_ms is None:
                self.first_chunk_ms = elapsed
        elif event.kind == "answering" and self.first_output_ms is None:
            self.first_output_ms = elapsed
        elif event.kind == "response_finished":
            for key, value in (event.metrics or {}).items():
                if (
                    key in METRIC_KEYS
                    and isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(value)
                    and value >= 0
                ):
                    self.metrics[key] = value

    def output(self, text: str) -> None:
        self.output_chars += len(text)

    def thinking(self, text: str) -> None:
        self.thinking_chars += len(text)

    def emit(self, completed: bool, error: BaseException | None = None) -> None:
        duration = max(0.0, self.clock() - self.started) * 1000
        tokens, generation = self.metrics["eval_count"], self.metrics["eval_duration_ms"]
        rate = (
            tokens * 1000 / generation
            if tokens is not None and generation is not None and generation > 0
            else None
        )
        rate = round(rate, 3) if rate is not None and math.isfinite(rate) else None
        reason = getattr(error, "reason", None)
        if isinstance(error, OperationCancelled):
            reason = "cancelled"
        elif not isinstance(reason, str) or reason not in FAILURE_REASONS:
            reason = None
        emit_index_event(
            {
                **self.metadata,
                "event": "completed" if completed else "failed",
                "duration_ms": round(duration, 3),
                "first_chunk_ms": self.first_chunk_ms,
                "first_output_ms": self.first_output_ms,
                "last_activity_ms": self.last_activity_ms,
                "stream_events": self.stream_events,
                "output_chars": self.output_chars,
                "thinking_chars": self.thinking_chars,
                **self.metrics,
                "output_tokens_per_second": rate,
                "error_type": type(error).__name__ if error is not None else None,
                "error_reason": reason,
                **json_error_details(error.__cause__ if error is not None else None),
            }
        )


# Parent cancellation and deadlines stay active while a streamed batch owns its request budget.
@contextmanager
def index_batch(
    settings: Settings,
    *,
    run_id: str,
    kind: BatchKind,
    batch: int,
    batches: int,
    system: str,
    user: str,
    max_tokens: int,
    clock: Callable[[], float] = time.monotonic,
) -> Iterator[BatchTelemetry]:
    parent = copy_context()
    timeout = remaining_timeout(float(settings.herb_association_ai_timeout_seconds))
    payload = json.loads(user)
    units = payload.get("units", {})
    warning_limits = (
        index_response_schema(payload)["properties"]["warnings"]["properties"]
        if "safety_targets" in payload
        else {}
    )
    metadata = {
        "stage": "herb_ai_batch",
        "run_id": run_id,
        "kind": kind,
        "batch": batch,
        "batches": batches,
        "model": settings.herb_association_ai_model,
        "context_tokens": settings.herb_association_ai_context_tokens,
        "max_output_tokens": max_tokens,
        "timeout_seconds": settings.herb_association_ai_timeout_seconds,
        "effective_timeout_seconds": round(timeout, 3),
        "stream": True,
        "think": False,
        "keep_alive_seconds": settings.herb_association_ai_keep_alive_seconds,
        "fragments": len(units),
        "source_chars": sum(len(unit["text"]) for unit in units.values()),
        "user_payload_chars": len(user),
        "system_prompt_chars": len(system),
        "association_targets": len(payload.get("candidates", [])),
        "safety_targets": 1 if "product" in payload else len(payload.get("safety_targets", [])),
        "herb_id": payload["product"]["id"] if "product" in payload else None,
        "safety_source": "model_knowledge" if "product" in payload else None,
        "warning_items_max_total": sum(
            value["properties"]["items"]["maxItems"] for value in warning_limits.values()
        ),
    }
    telemetry = BatchTelemetry(metadata, clock)
    completed = False
    emit_index_event({**metadata, "event": "started"})
    try:
        with operation_budget(
            OperationBudget(
                telemetry.started + timeout,
                clock,
                lambda: parent.run(checkpoint),
                report_output=telemetry.output,
                report_thinking=telemetry.thinking,
                report_activity=telemetry.activity,
            )
        ):
            yield telemetry
        completed = True
    except OperationCancelled:
        parent.run(checkpoint)
        raise AIUnavailable(
            "Cererea de indexare AI a depășit limita de timp.", reason="timeout"
        ) from None
    finally:
        telemetry.emit(completed, None if completed else sys.exc_info()[1])
