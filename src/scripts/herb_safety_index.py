"""Legacy corpus helpers and shared progress; public safety commands use product knowledge."""

from __future__ import annotations

import json
import math
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any
from uuid import uuid4

from backend.ai.client import ResponsesClient
from backend.ai.herb_association_classification import (
    Work,
    classification_prompt,
    group_fragment_works,
    model_digest,
)
from backend.ai.herb_association_rules import classify_rule
from backend.ai.herb_positive_repository import PositiveRepository, Snapshot
from backend.ai.herb_safety_extraction import (
    WARNING_KINDS,
    SafetyTarget,
    citation_index,
    eligible_warning_statements,
    local_warning_items,
    warning_source_word_count,
)
from backend.ai.herb_safety_repository import SafetyRepository, SafetySnapshot
from backend.ai.herb_safety_validation import (
    SafetyResult,
    safety_prompt,
    safety_semantic,
    validate_items,
    validate_reference_warnings,
)
from backend.config import Settings
from backend.core.operation_context import OperationBudget, checkpoint, operation_budget
from scripts.herb_index_requests import (
    emit_index_event,
    index_batch,
    index_response_schema,
    make_client,
    warning_item_limit,
)


# Durations keep total hours rather than wrapping at a day boundary.
def format_duration(seconds: float) -> str:
    hours, remainder = divmod(max(0, int(seconds)), 3600)
    minutes, seconds_part = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d}"


# Attempts and cache hits do not supply a measured processing rate for pending batches.
def batch_progress(completed: int, total: int | None, elapsed: float) -> dict[str, Any]:
    rate = completed / elapsed if elapsed > 0 else 0.0
    eta = None
    if total is not None:
        remaining = max(0, total - completed)
        if remaining == 0:
            eta = "00:00:00"
        elif rate > 0:
            eta = format_duration(max(1, math.ceil(remaining / rate)))
    return {"rate_batches_second": rate, "ETA(hh:mm:ss)": eta}


# Completed AI batches do not estimate inventory, projections, or publication still pending.
def workflow_progress(
    counters: dict[str, Any], elapsed: float, warning_metrics: dict[str, Any] | None = None
) -> dict[str, Any]:
    stage = counters.get("progress_stage", "analysis")
    metrics = batch_progress(0, None, elapsed)
    if stage == "associations":
        metrics = batch_progress(counters["completed"], counters.get("batches"), elapsed)
    elif stage in {"warnings_only", "product_safety"} and warning_metrics is not None:
        metrics = dict(warning_metrics)
    if counters.get("status") in {"ready", "published"}:
        metrics = dict(warning_metrics or metrics)
        metrics["ETA(hh:mm:ss)"] = "00:00:00"
    elif counters.get("status") == "failed" or metrics["ETA(hh:mm:ss)"] == "00:00:00":
        metrics["ETA(hh:mm:ss)"] = None
    return {**metrics, "progress_stage": stage}


def local_target_ids(data: SafetySnapshot, positive: Snapshot) -> set[str]:
    if data.manifest != {
        key: value for key, value in positive.manifest.items() if key != "version"
    }:
        raise ValueError("HERB_SAFETY_INPUT_CHANGED")
    pairs = {
        (group.work[0].passage.chunk_id, group.work[1].herb_id)
        for group in group_fragment_works(positive.works, positive.conditions)
        if all(classify_rule(*original) is not None for original in group.originals)
    }
    return {
        target.identity for target in data.targets if (target.chunk_id, target.herb_id) in pairs
    }


def bind_targets(
    payload: dict[str, Any], targets: list[SafetyTarget], unit_ids: dict[int, str]
) -> None:
    statements: dict[str, list[str]] = {}
    for target in targets:
        unit = payload["units"][unit_ids[target.chunk_id]]
        if unit["text"] != target.text:
            raise ValueError("HERB_SAFETY_INPUT_CHANGED")
        if "citation_passages" not in unit:
            unit["citation_passages"] = {}
        if target.certain and not unit["citation_passages"]:
            unit["citation_passages"] = citation_index(target)
        statements[target.identity] = list(eligible_warning_statements(target))
    payload["safety_targets"] = [
        {
            "id": f"s{position}",
            "unit": unit_ids[target.chunk_id],
            "herb_id": target.herb_id,
            "herb": target.name,
            "mentions": target.mentions,
            "heading_owned": target.heading_owned,
            "certain": target.certain,
            "warning_statement_ids": statements[target.identity],
            "warning_source_words": warning_source_word_count(target),
        }
        for position, target in enumerate(targets)
    ]


def safety_payload(targets: list[SafetyTarget]) -> dict[str, Any]:
    units: dict[str, Any] = {}
    unit_ids: dict[int, str] = {}
    for target in targets:
        unit_id = unit_ids.setdefault(target.chunk_id, f"u{len(unit_ids)}")
        units[unit_id] = {"text": target.text, "headings": [target.heading]}
    payload = {"units": units}
    bind_targets(payload, targets, unit_ids)
    return payload


def payload_fits(payload: dict[str, Any], prompt: str, settings: Settings) -> bool:
    # Include the strict schema and system instructions, as the original packer does.
    envelope = {
        "model": settings.herb_association_ai_model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "format": index_response_schema(payload),
        "options": {
            "num_ctx": settings.herb_association_ai_context_tokens
            if "candidates" in payload
            else settings.herb_safety_ai_context_tokens,
            "num_predict": settings.herb_safety_ai_max_output_tokens,
        },
        "truncate": False,
        "shift": False,
    }
    return (
        len(json.dumps(envelope, ensure_ascii=False))
        <= settings.herb_association_ai_max_input_chars
    )


def pack_safety_batches(
    targets: list[SafetyTarget], settings: Settings
) -> list[list[SafetyTarget]]:
    prompt = safety_prompt()
    batches: list[list[SafetyTarget]] = []
    batch: list[SafetyTarget] = []
    for target in targets:
        candidate = [*batch, target]
        if batch and (
            len(candidate) > settings.herb_association_ai_max_pairs
            or len({t.chunk_id for t in candidate}) > settings.herb_association_ai_max_units
            or not payload_fits(safety_payload(candidate), prompt, settings)
        ):
            batches.append(batch)
            batch = []
        batch.append(target)
        if not payload_fits(safety_payload(batch), prompt, settings):
            raise ValueError("HERB_SAFETY_UNIT_TOO_LARGE")
    if batch:
        batches.append(batch)
    return batches


# AI selects source IDs; only locally copied, scoped source text can become stored evidence.
def _validated_warning_results(
    raw: Any, targets: list[SafetyTarget]
) -> tuple[dict[str, SafetyResult], dict[str, int]]:
    return validate_reference_warnings(raw, targets)


class SafetyCoordinator:
    def __init__(
        self,
        settings: Settings,
        repository: SafetyRepository,
        run_id: str,
        digest: str,
        *,
        resume: bool = False,
        counters: dict[str, Any] | None = None,
        require_existing: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.run_id = run_id
        self.digest = digest
        self.clock = clock
        self._warnings_started_at: float | None = None
        self._warnings_finished_at: float | None = None
        self.counters = counters if counters is not None else {}
        self.counters["progress_stage"] = "safety_inventory"
        self.semantic = safety_semantic(settings)
        self.data = repository.read_snapshot()
        cached = repository.cached(self.data, self.semantic, digest)
        self.keys = {
            target.identity: target.cache_key(self.semantic, digest) for target in self.data.targets
        }
        self.by_cache: dict[str, list[str]] = {}
        self.by_chunk: dict[int, list[SafetyTarget]] = {}
        for target in self.data.targets:
            self.by_chunk.setdefault(target.chunk_id, []).append(target)
            self.by_cache.setdefault(self.keys[target.identity], []).append(target.identity)
        self.results: dict[str, SafetyResult] = {}
        for identity, result in cached.items():
            for sibling in self.by_cache[self.keys[identity]]:
                self.results[sibling] = result
        self.state = repository.create_run(
            run_id, self.data, self.semantic, digest, resume, require_existing=require_existing
        )
        self.counters.update(
            safety_run_id=run_id,
            warnings_only_ai_requests=0,
            safety_batches_completed=0,
            safety_cache_hits=len(self.results),
            safety_targets=len(self.data.targets),
            safety_context_tokens=settings.herb_safety_ai_context_tokens,
        )
        self.blocked: set[str] = set()

    def progress_metrics(self) -> dict[str, Any] | None:
        if self._warnings_started_at is None:
            return None
        end = self._warnings_finished_at
        elapsed = (self.clock() if end is None else end) - self._warnings_started_at
        return {
            "progress_stage": "warnings_only",
            **batch_progress(
                self.counters["safety_batches_completed"], self.counters["safety_batches"], elapsed
            ),
        }

    def enrich(self, serialized: str, batch: list[Work]) -> tuple[str, list[SafetyTarget]]:
        payload = json.loads(serialized)
        unit_ids: dict[int, str] = {}
        for unit, _ in batch:
            unit_ids.setdefault(unit.passage.chunk_id, f"u{len(unit_ids)}")
        targets = [
            target
            for chunk_id, unit_id in unit_ids.items()
            for target in self.by_chunk.get(chunk_id, [])
            if target.identity not in self.results
            and target.text == payload["units"][unit_id]["text"]
        ]
        if not targets:
            return serialized, []
        bind_targets(payload, targets, unit_ids)
        if not payload_fits(payload, classification_prompt(include_warnings=True), self.settings):
            self.counters["safety_combined_over_budget"] = (
                self.counters.get("safety_combined_over_budget", 0) + 1
            )
            return serialized, []
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")), targets

    def record(self, raw: Any, targets: list[SafetyTarget], *, combined: bool = False) -> None:
        try:
            results, diagnostics = _validated_warning_results(raw, targets)
        except ValueError:
            if not combined:
                raise
            # Association labels remain valid; malformed warnings do not erase them.
            self.blocked.update(target.identity for target in targets)
            self.counters["safety_invalid_combined"] = (
                self.counters.get("safety_invalid_combined", 0) + 1
            )
            return
        # Forced closure after repeated entries cannot establish that every warning was covered.
        for position, target in enumerate(targets):
            result = results[target.identity]
            if result.status != "complete":
                continue
            items = raw[f"s{position}"]["items"]
            limit = warning_item_limit(
                len(eligible_warning_statements(target)),
                len(WARNING_KINDS),
                warning_source_word_count(target),
            )
            groups = {json.dumps(item, sort_keys=True) for item in items}
            word_count = len(target.text.split())
            repeated_items = limit > 0 and len(items) >= limit and len(groups) < len(items)
            repeated_partners = word_count > 0 and any(
                len(item["partners"]) >= word_count
                and len(set(item["partners"])) < len(item["partners"])
                for item in items
            )
            if repeated_items or repeated_partners:
                results[target.identity] = replace(result, status="unclear")
                name = "safety_unclear_after_transport_limit"
                diagnostics[name] = diagnostics.get(name, 0) + 1
        self.repository.save_cache(targets, results, self.semantic, self.digest)
        for name, count in diagnostics.items():
            self.counters[name] = self.counters.get(name, 0) + count
        for target in targets:
            for identity in self.by_cache[self.keys[target.identity]]:
                self.results[identity] = results[target.identity]
                self.blocked.discard(identity)

    def prepare(
        self,
        mandatory: set[str],
        *,
        client_factory: Callable[[Settings], ResponsesClient] = make_client,
        digest_verifier: Callable[[Settings], str] = model_digest,
    ) -> dict[str, Any]:
        self.counters["progress_stage"] = "safety_preparation"
        if self.state == "ready":
            if self._warnings_started_at is None:
                self.counters["safety_batches"] = 0
                self._warnings_started_at = self._warnings_finished_at = self.clock()
            self.counters["progress_stage"] = "ready"
            return self.counters
        if self.blocked & mandatory:
            raise ValueError("HERB_SAFETY_INCOMPLETE_RESPONSE")
        pending: dict[str, SafetyTarget] = {}
        for target in self.data.targets:
            if target.identity in mandatory and target.identity not in self.results:
                pending.setdefault(self.keys[target.identity], target)
        prompt = safety_prompt()
        batches = pack_safety_batches(list(pending.values()), self.settings)
        self.counters["safety_batches"] = len(batches)
        if len(batches) > self.settings.herb_safety_ai_max_requests:
            raise ValueError("HERB_SAFETY_REQUEST_LIMIT")
        self.counters["safety_batches_completed"] = 0
        self._warnings_started_at = self.clock()
        self._warnings_finished_at = None
        self.counters["progress_stage"] = "warnings_only"
        # Safety capacity is independent of the semantic keys of association decisions.
        request_settings = replace(
            self.settings,
            herb_association_ai_context_tokens=self.settings.herb_safety_ai_context_tokens,
        )
        client = client_factory(request_settings) if batches else None
        try:
            for number, batch in enumerate(batches, 1):
                checkpoint()
                assert client is not None
                self.repository.admit_request(
                    self.run_id, self.settings.herb_safety_ai_max_requests
                )
                self.counters["warnings_only_ai_requests"] += 1
                user = json.dumps(safety_payload(batch), ensure_ascii=False, separators=(",", ":"))
                with index_batch(
                    request_settings,
                    run_id=self.run_id,
                    kind="warnings_only",
                    batch=number,
                    batches=len(batches),
                    system=prompt,
                    user=user,
                    max_tokens=self.settings.herb_safety_ai_max_output_tokens,
                    clock=self.clock,
                ):
                    raw = client.complete_json(
                        prompt, user, self.settings.herb_safety_ai_max_output_tokens
                    )
                    checkpoint()
                    if not isinstance(raw, dict) or set(raw) != {"warnings"}:
                        raise ValueError("HERB_SAFETY_INVALID_RESPONSE")
                    self.record(raw["warnings"], batch)
                self.counters["safety_batches_completed"] += 1
            self._warnings_finished_at = self.clock()
            self.counters["progress_stage"] = "safety_finalization"
        finally:
            if client is not None:
                client.http.close()
        if batches and digest_verifier(self.settings) != self.digest:
            raise ValueError("HERB_SAFETY_MODEL_CHANGED")
        for target in self.data.targets:
            if target.identity not in self.results:
                items = validate_items(target, local_warning_items(target))
                self.results[target.identity] = SafetyResult(
                    "local" if items else "uncovered", items
                )
        if safety_semantic(self.settings) != self.semantic:
            raise ValueError("HERB_SAFETY_CONFIGURATION_CHANGED")
        self.counters.update(
            safety_complete=sum(result.status == "complete" for result in self.results.values()),
            safety_partial=sum(result.status != "complete" for result in self.results.values()),
            safety_warnings=sum(len(result.items) for result in self.results.values()),
        )
        self.repository.finish(
            self.run_id,
            self.data,
            self.results,
            mandatory,
            self.semantic,
            self.digest,
            self.counters,
        )
        self.state = "ready"
        self.counters["progress_stage"] = "ready"
        return self.counters


def run_safety_index(
    settings: Settings,
    *,
    analyze: bool = False,
    publish: str | None = None,
    resume: str | None = None,
) -> dict[str, Any]:
    from scripts.herb_product_safety_index import run_product_safety_index

    return run_product_safety_index(settings, analyze=analyze, publish=publish, resume=resume)


# Historical corpus workflow is retained for old evidence tooling, never selected by the CLI.
def _run_legacy_safety_index(
    settings: Settings,
    *,
    analyze: bool = False,
    publish: str | None = None,
    resume: str | None = None,
) -> dict[str, Any]:
    repository = SafetyRepository()
    started = time.monotonic()
    counters: dict[str, Any] = {
        "stage": "herb_safety",
        "warnings_only_ai_requests": 0,
        "progress_stage": "safety_inventory",
    }
    coordinator: SafetyCoordinator | None = None
    stopped = threading.Event()

    def progress() -> None:
        elapsed = time.monotonic() - started
        counters["elapsed_seconds"] = round(elapsed, 3)
        counters["elapsed(hh:mm:ss)"] = format_duration(elapsed)
        counters["ai_requests_sent_total"] = counters["warnings_only_ai_requests"]
        warning_metrics = coordinator.progress_metrics() if coordinator is not None else None
        metrics = workflow_progress(counters, elapsed, warning_metrics)
        emit_index_event({**counters, **metrics})

    def heartbeat() -> None:
        while not stopped.wait(60):
            progress()

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        with operation_budget(
            OperationBudget(
                started + settings.herb_safety_build_timeout_seconds, time.monotonic, lambda: None
            )
        ):
            if publish:
                counters["progress_stage"] = "publication"
                repository.publish(publish, settings)
                counters.update(run_id=publish, status="published")
                return counters
            data = repository.read_snapshot()
            positive = PositiveRepository(repository.pool).read_snapshot()
            mandatory = local_target_ids(data, positive)
            semantic = safety_semantic(settings)
            cached_digest = repository.analysis_digest(semantic)
            if analyze:
                cached = repository.cached(data, semantic, cached_digest) if cached_digest else {}
                pending = {
                    target.cache_key(semantic, cached_digest or "unverified"): target
                    for target in data.targets
                    if target.identity in mandatory and target.identity not in cached
                }
                eligible = [
                    target
                    for target in pending.values()
                    if payload_fits(safety_payload([target]), safety_prompt(), settings)
                ]
                counters.update(
                    status="analyzed",
                    targets=len(data.targets),
                    local_targets=len(mandatory),
                    safety_cache_hits=len(cached),
                    estimated_warning_requests=len(pack_safety_batches(eligible, settings)),
                    over_budget_targets=len(pending) - len(eligible),
                    model_digest_verified=False,
                )
                return counters
            digest = model_digest(settings) if mandatory else cached_digest or "0" * 64
            coordinator = SafetyCoordinator(
                settings,
                repository,
                resume or str(uuid4()),
                digest,
                resume=bool(resume),
                counters=counters,
                require_existing=bool(resume),
            )
            if coordinator.data.manifest != data.manifest:
                raise ValueError("HERB_SAFETY_INPUT_CHANGED")
            coordinator.prepare(mandatory)
            counters.update(run_id=coordinator.run_id, status="ready")
            return counters
    except Exception:
        counters["status"] = "failed"
        raise
    finally:
        stopped.set()
        thread.join(timeout=1)
        progress()
