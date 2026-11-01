"""Bilingual product safety in batches: ministral and deepseek, one merge, a run per language."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from contextvars import copy_context
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.ai.client import AIUnavailable
from backend.ai.herb_association_rules import content_hash
from backend.ai.herb_product_safety import (
    BILINGUAL_VERSION,
    BilingualResult,
    Stage,
    bilingual_prompt,
    dedup_cache_key,
    dedup_prompt,
    dedup_semantic,
    product_identity,
    project_language,
    run_semantic,
    serialize_batch,
    serialize_dedup_batch,
    stage_cache_key,
    stage_semantic,
    validate_batch_response,
    validate_dedup_response,
)
from backend.ai.herb_product_safety_dedup import (
    ExactMerge,
    MergeOutcome,
    exact_merge,
    finish_merge,
)
from backend.ai.herb_product_safety_repository import ProductSafetyRepository
from backend.ai.herbs import Herb
from backend.config import (
    SAFETY_MIN_MESSAGES,
    SafetyScope,
    Settings,
    normalize_latin,
    parse_safety_scope,
)
from backend.core.language import LANGUAGES, language_scope
from backend.core.operation_context import OperationBudget, checkpoint, operation_budget
from backend.core.report_models import REPORT_MODELS
from scripts.herb_index_requests import (
    DeepSeekSafetyClient,
    index_batch,
    make_client,
    make_deepseek_client,
    model_digest,
)
from scripts.herb_safety_index import batch_progress

DEDUP_REPORT = Path("aiWork") / "herb_safety_dedup_pairs.json"
# Tokens are estimated from UTF-8 bytes, as everywhere else in the codebase.
BYTES_PER_TOKEN = 3
INPUT_RESERVE_TOKENS = 512
# The grouping answer is a few index lists, so its cap stays small beside a small context.
DEDUP_OUTPUT_TOKENS = 4096
# The external model wins between sources: it was the correct one in the first real comparison.
PRIORITY: tuple[Stage, ...] = ("deepseek", "ministral")
# A request to the external model lasts minutes and fails now and then on the network; the
# failures below are retried, the others (output or context limit, credits) would repeat.
REQUEST_ATTEMPTS = 3
DEEPSEEK_RETRY_SECONDS = 30
LOCAL_RETRY_SECONDS = 5
# A local request normally lasts seconds, so a stalled server is detected long before the
# global cap: a worst-case product (12000 tokens) still fits at the slowest measured rate.
LOCAL_TIMEOUT_BASE_SECONDS = 300
LOCAL_TIMEOUT_PER_PRODUCT_SECONDS = 60
RETRYABLE_REASONS = frozenset(
    {"timeout", "unavailable", "rate_limited", "provider_failed", "invalid_response"}
)


# Resolve the products to rebuild; a Latin name must match exactly one catalog row.
def resolve_scope(herbs: tuple[Herb, ...], scope: SafetyScope) -> tuple[Herb, ...]:
    if scope.mode == "all":
        return herbs
    if scope.mode == "first":
        return herbs[: scope.count]
    if scope.mode != "latin":
        raise ValueError("HERB_PRODUCT_SAFETY_EXTENSION_DISABLED")
    chosen: list[Herb] = []
    for name in scope.latins:
        matches = [herb for herb in herbs if normalize_latin(herb.latin) == name]
        if not matches:
            raise ValueError(f"HERB_PRODUCT_SAFETY_SCOPE_NOT_FOUND: {name}")
        if len(matches) > 1:
            raise ValueError(f"HERB_PRODUCT_SAFETY_SCOPE_AMBIGUOUS: {name}")
        chosen.append(matches[0])
    return tuple(sorted(chosen, key=lambda herb: herb.id))


def batches_of(herbs: list[Herb], size: int) -> list[list[Herb]]:
    return [herbs[start : start + size] for start in range(0, len(herbs), size)]


# The batch must fit the stage's context beside its output allowance, before any request.
def check_input_fits(
    prompt: str, users: list[str], context_tokens: int, output_tokens: int
) -> None:
    allowed = context_tokens - output_tokens - INPUT_RESERVE_TOKENS
    for user in users:
        size = len(prompt.encode()) + len(user.encode())
        if -(-size // BYTES_PER_TOKEN) > allowed:
            raise ValueError("HERB_PRODUCT_SAFETY_BATCH_INPUT_TOO_LARGE")


class ExtensionCoordinator:
    def __init__(
        self,
        settings: Settings,
        repository: ProductSafetyRepository,
        *,
        counters: dict[str, Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.clock = clock
        self.counters = counters if counters is not None else {}
        self.scope = parse_safety_scope(settings.herb_safety_extension_products)
        if self.scope.mode == "off":
            raise ValueError("HERB_PRODUCT_SAFETY_EXTENSION_DISABLED")
        self.herbs = repository.read_products()
        self.targets = resolve_scope(self.herbs, self.scope)
        target_ids = {herb.id for herb in self.targets}
        self.outside = [herb for herb in self.herbs if herb.id not in target_ids]
        # An empty generation model leaves DeepSeek as the only generating stage.
        self.local = bool(settings.herb_safety_generation_model)
        self.stages: tuple[Stage, ...] = ("ministral", "deepseek") if self.local else ("deepseek",)
        self.generation_settings = replace(
            settings, herb_association_ai_model=settings.herb_safety_generation_model
        )
        self.semantics = {stage: stage_semantic(settings, stage) for stage in self.stages}
        self.dedup_semantics = dedup_semantic(settings)
        # The grouping model is a different local model, so it has its own digest and client.
        self.dedup_settings = replace(
            settings, herb_association_ai_model=settings.herb_safety_dedup_model
        )
        self.sizes = {
            "ministral": settings.herb_safety_ministral_batch_size,
            "deepseek": settings.herb_safety_deepseek_batch_size,
        }
        self.started: float | None = None
        self.finished: float | None = None
        self.counters.update(
            safety_source="model_knowledge_bilingual",
            safety_scope=self.scope.mode,
            safety_targets=len(self.targets),
            safety_products_total=len(self.herbs),
            safety_products_completed=0,
            safety_cache_hits=0,
            product_safety_ai_requests=0,
            safety_batches_completed=0,
            safety_context_tokens=settings.herb_safety_ai_context_tokens,
        )

    def progress_metrics(self) -> dict[str, Any] | None:
        if self.started is None:
            return None
        elapsed = (self.finished if self.finished is not None else self.clock()) - self.started
        return batch_progress(
            self.counters["safety_batches_completed"],
            self.counters.get("safety_batches"),
            elapsed,
        )

    def _pending(
        self, stage: Stage, digest: str | None
    ) -> tuple[dict[int, BilingualResult], list[Herb]]:
        cached = self.repository.cached_stage(self.targets, stage, self.semantics[stage], digest)
        return cached, [herb for herb in self.targets if herb.id not in cached]

    # The deterministic merge of the products whose every active stage already has an answer.
    def _exact(
        self, answers: dict[Stage, dict[int, BilingualResult]], herbs: Sequence[Herb]
    ) -> dict[int, ExactMerge]:
        return {
            herb.id: exact_merge(
                [answers[stage][herb.id] for stage in PRIORITY if stage in self.stages]
            )
            for herb in herbs
            if all(herb.id in answers[stage] for stage in self.stages)
        }

    # The cache key of a product's grouping covers the exact messages the model must group.
    def _dedup_keys(self, exact: dict[int, ExactMerge], digest: str) -> dict[int, str]:
        return {
            herb_id: dedup_cache_key(
                herb_id,
                [item.message.identity for item in merged.candidates],
                self.dedup_semantics,
                digest,
            )
            for herb_id, merged in exact.items()
            if len(merged.candidates) > 1
        }

    def _merge(
        self, exact: dict[int, ExactMerge], groups: dict[int, list[list[int]]]
    ) -> dict[int, MergeOutcome]:
        return {
            herb_id: finish_merge(merged, groups.get(herb_id, []))
            for herb_id, merged in exact.items()
            if len(merged.candidates) < 2 or herb_id in groups
        }

    def _report(self, outcomes: dict[int, MergeOutcome]) -> None:
        by_id = {herb.id: herb for herb in self.targets}
        entries = [
            {
                "herb_id": herb_id,
                "latin": by_id[herb_id].latin,
                "removed": [pair.payload() for pair in outcome.removed],
            }
            for herb_id, outcome in outcomes.items()
            if outcome.removed
        ]
        DEDUP_REPORT.parent.mkdir(parents=True, exist_ok=True)
        DEDUP_REPORT.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
        removed = [pair for outcome in outcomes.values() for pair in outcome.removed]
        by_type: dict[str, int] = {}
        for pair in removed:
            by_type[pair.removed.message_type] = by_type.get(pair.removed.message_type, 0) + 1
        self.counters.update(
            dedup_removed=len(removed),
            dedup_removed_by_type=by_type,
            dedup_report=str(DEDUP_REPORT),
            safety_products_merged=len(outcomes),
            safety_products_under_minimum=sum(
                len(outcome.messages) < SAFETY_MIN_MESSAGES for outcome in outcomes.values()
            ),
        )

    # Inventory only: no request is sent and the model digest is not verified.
    def analyze(self) -> dict[str, Any]:
        answers: dict[Stage, dict[int, BilingualResult]] = {}
        total = 0
        for stage in self.stages:
            digest = (
                self.repository.stage_digest(stage, self.semantics[stage])
                if stage == "ministral"
                else None
            )
            cached, pending = (
                self._pending(stage, digest)
                if stage != "ministral" or digest
                else ({}, self.targets)
            )
            answers[stage] = cached
            batches = len(batches_of(list(pending), self.sizes[stage]))
            total += batches
            self.counters.update({f"{stage}_cache_hits": len(cached), f"{stage}_batches": batches})
        exact = self._exact(answers, self.targets)
        digest = self.repository.stage_digest("dedup", self.dedup_semantics)
        keys = self._dedup_keys(exact, digest) if digest else {}
        groups = self.repository.cached_dedup({key: herb_id for herb_id, key in keys.items()})
        pending_dedup = [
            herb_id
            for herb_id, merged in exact.items()
            if len(merged.candidates) > 1 and herb_id not in groups
        ]
        dedup_batches = -(-len(pending_dedup) // self.sizes["ministral"])
        total += dedup_batches
        self.counters.update(dedup_cache_hits=len(groups), dedup_batches=dedup_batches)
        self._report(self._merge(exact, groups))
        self.counters.update(
            status="analyzed",
            safety_scope_products=len(self.targets),
            safety_outside_scope=len(self.outside),
            estimated_warning_requests=total,
            model_digest_verified=False,
        )
        return self.counters

    def prepare(
        self,
        *,
        client_factory: Callable[[Settings], Any] = make_client,
        deepseek_factory: Callable[[Settings], DeepSeekSafetyClient] = make_deepseek_client,
        digest_verifier: Callable[[Settings], str] = model_digest,
    ) -> dict[str, Any]:
        parent = copy_context()
        with operation_budget(
            OperationBudget(
                self.clock() + self.settings.herb_safety_build_timeout_seconds,
                self.clock,
                lambda: parent.run(checkpoint),
            )
        ):
            return self._prepare(client_factory, deepseek_factory, digest_verifier)

    # Products are processed in chunks (one DeepSeek batch each): generation, merge, grouping and
    # the write into both language runs finish for a chunk before the next one starts, so a failure
    # keeps every earlier chunk in the database and the next run continues from there.
    def _prepare(
        self,
        client_factory: Callable[[Settings], Any],
        deepseek_factory: Callable[[Settings], DeepSeekSafetyClient],
        digest_verifier: Callable[[Settings], str],
    ) -> dict[str, Any]:
        settings = self.settings
        if not self.repository.extension_schema_available():
            raise ValueError("HERB_PRODUCT_SAFETY_EXTENSION_SCHEMA_MISSING")
        if "deepseek" in self.stages and not settings.deepseek_api_key():
            raise ValueError("HERB_PRODUCT_SAFETY_DEEPSEEK_KEY_MISSING")
        if self.outside:
            for language in LANGUAGES:
                with language_scope(language):
                    if not self.repository.has_active():
                        raise ValueError("HERB_PRODUCT_SAFETY_NO_ACTIVE_RUN")
        self.counters["progress_stage"] = "product_safety_cache"
        dedup_digest = digest_verifier(self.dedup_settings)
        digest = digest_verifier(self.generation_settings) if self.local else dedup_digest
        digests: dict[Stage, str | None] = {"ministral": digest, "deepseek": None}
        prompt = bilingual_prompt()
        answers: dict[Stage, dict[int, BilingualResult]] = {}
        for stage in self.stages:
            if content_hash(prompt) != self.semantics[stage]["prompt"]:
                raise ValueError("HERB_PRODUCT_SAFETY_CONFIGURATION_CHANGED")
            answers[stage], _ = self._pending(stage, digests[stage])
        self.counters["safety_cache_hits"] = sum(len(found) for found in answers.values())
        chunks = batches_of(list(self.targets), self.sizes["deepseek"])
        plan = [
            {
                stage: batches_of(
                    [herb for herb in chunk if herb.id not in answers[stage]], self.sizes[stage]
                )
                for stage in self.stages
            }
            for chunk in chunks
        ]
        total = sum(len(batches) for step in plan for batches in step.values())
        if total > settings.herb_safety_ai_max_requests:
            raise ValueError("HERB_PRODUCT_SAFETY_REQUEST_LIMIT")
        contexts = {
            "ministral": (
                settings.herb_safety_ai_context_tokens,
                settings.herb_safety_ai_max_output_tokens,
            ),
            "deepseek": (
                REPORT_MODELS["deepseek-flash"].context_window,
                settings.herb_safety_deepseek_max_output_tokens,
            ),
        }
        for stage in self.stages:
            check_input_fits(
                prompt,
                [serialize_batch(batch) for step in plan for batch in step[stage]],
                *contexts[stage],
            )
        self.counters["safety_batches"] = total
        # Both runs exist before the first request, so their rows grow as products are prepared.
        runs = {language: self._open_run(language, digest) for language in LANGUAGES}
        self.counters.update(
            run_ids={language: run for language, (run, _) in runs.items()},
            run_id_ro=runs["ro"][0],
            run_id_en=runs["en"][0],
        )
        self.started = self.clock()
        self.counters["progress_stage"] = "product_safety"
        session = str(uuid4())
        outcomes: dict[int, MergeOutcome] = {}
        missing: set[int] = set()
        for chunk, step in zip(chunks, plan, strict=True):
            for stage in self.stages:
                if step[stage]:
                    self._run_stage(
                        stage,
                        step[stage],
                        answers[stage],
                        digests[stage],
                        prompt,
                        session,
                        client_factory,
                        deepseek_factory,
                        digest_verifier,
                    )
            ready = [herb for herb in chunk if all(herb.id in answers[s] for s in self.stages)]
            missing.update(herb.id for herb in chunk if herb not in ready)
            exact = self._exact(answers, ready)
            keys = self._dedup_keys(exact, dedup_digest)
            groups = self.repository.cached_dedup({key: herb_id for herb_id, key in keys.items()})
            self.counters["dedup_cache_hits"] = self.counters.get("dedup_cache_hits", 0) + len(
                groups
            )
            missing.update(
                self._run_dedup(
                    [herb for herb in ready if herb.id in keys and herb.id not in groups],
                    exact,
                    keys,
                    groups,
                    session,
                    client_factory,
                    digest_verifier,
                    dedup_digest,
                )
            )
            merged = self._merge(exact, groups)
            outcomes.update(merged)
            stage_keys = {
                herb.id: [
                    stage_cache_key(herb, self.semantics[stage], digests[stage])
                    for stage in self.stages
                ]
                + ([keys[herb.id]] if herb.id in keys else [])
                for herb in ready
            }
            self._write_products(
                [herb for herb in ready if herb.id in merged], merged, stage_keys, runs, digest
            )
            self.counters["safety_products_completed"] = len(outcomes)
        self.finished = self.clock()
        self.counters["progress_stage"] = "safety_finalization"
        if missing:
            self.counters["safety_missing_products"] = len(missing)
            raise ValueError("HERB_PRODUCT_SAFETY_PRODUCTS_MISSING")
        if total and self.local and digest_verifier(self.generation_settings) != digest:
            raise ValueError("HERB_PRODUCT_SAFETY_MODEL_CHANGED")
        for stage in self.stages:
            if stage_semantic(settings, stage) != self.semantics[stage]:
                raise ValueError("HERB_PRODUCT_SAFETY_CONFIGURATION_CHANGED")
        if dedup_semantic(settings) != self.dedup_semantics:
            raise ValueError("HERB_PRODUCT_SAFETY_CONFIGURATION_CHANGED")
        self._report(outcomes)
        for language, (run_id, semantic) in runs.items():
            with language_scope(language):
                self.repository.finish(run_id, self.herbs, semantic)
        self.counters.update(
            safety_products_completed=len(self.herbs),
            safety_complete=sum(o.status == "complete" for o in outcomes.values()),
            safety_partial=sum(o.status != "complete" for o in outcomes.values()),
            safety_warnings=sum(len(o.messages) for o in outcomes.values()),
            progress_stage="ready",
        )
        return self.counters

    # Run one request again after a transient failure; the pause grows with each attempt.
    def _attempts(self, request: Callable[[], int], wait_seconds: int) -> int:
        for attempt in range(1, REQUEST_ATTEMPTS + 1):
            try:
                return request()
            except AIUnavailable as exc:
                if attempt == REQUEST_ATTEMPTS or exc.reason not in RETRYABLE_REASONS:
                    raise
                self.counters["ai_request_retries"] = self.counters.get("ai_request_retries", 0) + 1
                time.sleep(wait_seconds * attempt)
                checkpoint()
        raise AssertionError("unreachable")

    def _run_stage(
        self,
        stage: Stage,
        batches: list[list[Herb]],
        answers: dict[int, BilingualResult],
        digest: str | None,
        prompt: str,
        session: str,
        client_factory: Callable[[Settings], Any],
        deepseek_factory: Callable[[Settings], DeepSeekSafetyClient],
        digest_verifier: Callable[[Settings], str],
    ) -> None:
        settings = self.settings
        local = stage == "ministral"
        request_settings = replace(
            self.generation_settings,
            herb_association_ai_context_tokens=settings.herb_safety_ai_context_tokens,
        )
        output = (
            settings.herb_safety_ai_max_output_tokens
            if local
            else settings.herb_safety_deepseek_max_output_tokens
        )
        client = client_factory(request_settings) if local else deepseek_factory(settings)
        try:
            for number, batch in enumerate(batches, 1):
                checkpoint()
                self.counters["product_safety_ai_requests"] += 1
                self.counters[f"{stage}_requests"] = self.counters.get(f"{stage}_requests", 0) + 1
                ids = [herb.id for herb in batch]
                user = serialize_batch(batch)
                batch_settings = request_settings
                if local:
                    # A stalled local server must not hold a one-product request for the whole cap.
                    timeout = LOCAL_TIMEOUT_BASE_SECONDS + LOCAL_TIMEOUT_PER_PRODUCT_SECONDS * len(
                        batch
                    )
                    batch_settings = replace(
                        request_settings,
                        herb_association_ai_timeout_seconds=min(
                            timeout, request_settings.herb_association_ai_timeout_seconds
                        ),
                    )

                def request() -> int:
                    with index_batch(
                        batch_settings,
                        run_id=session,
                        kind="product_safety",
                        batch=number,
                        batches=len(batches),
                        system=prompt,
                        user=user,
                        max_tokens=output,
                        clock=self.clock,
                        model=None if local else settings.deepseek_model,
                        context_tokens=None
                        if local
                        else REPORT_MODELS["deepseek-flash"].context_window,
                    ):
                        if local:
                            raw = client.complete_json(prompt, user, output)
                        else:
                            raw = client.complete_batch(prompt, user, output)
                        checkpoint()
                        valid, invalid = validate_batch_response(raw, ids)
                        # Do not cache a response under weights replaced during its request.
                        if local and digest_verifier(self.generation_settings) != digest:
                            raise ValueError("HERB_PRODUCT_SAFETY_MODEL_CHANGED")
                        saved = self.repository.save_stage(
                            stage,
                            [(herb, valid[herb.id]) for herb in batch if herb.id in valid],
                            self.semantics[stage],
                            digest,
                        )
                        answers.update(saved)
                    return len(invalid)

                rejected = self._attempts(
                    request, DEEPSEEK_RETRY_SECONDS if not local else LOCAL_RETRY_SECONDS
                )
                self.counters["safety_rejected_products"] = (
                    self.counters.get("safety_rejected_products", 0) + rejected
                )
                self.counters["safety_batches_completed"] += 1
        finally:
            client.http.close()

    # Local gemma groups equivalent messages; returns the products left without a valid grouping.
    def _run_dedup(
        self,
        pending: list[Herb],
        exact: dict[int, ExactMerge],
        keys: dict[int, str],
        groups: dict[int, list[list[int]]],
        session: str,
        client_factory: Callable[[Settings], Any],
        digest_verifier: Callable[[Settings], str],
        digest: str,
    ) -> list[int]:
        if not pending:
            return []
        settings = self.settings
        prompt = dedup_prompt()
        batches = batches_of(pending, self.sizes["ministral"])
        output = DEDUP_OUTPUT_TOKENS
        users = [
            serialize_dedup_batch(
                [(herb.id, [item.message for item in exact[herb.id].candidates]) for herb in batch]
            )
            for batch in batches
        ]
        check_input_fits(prompt, users, settings.herb_safety_ai_context_tokens, output)
        requests = self.counters["product_safety_ai_requests"] + len(batches)
        if requests > settings.herb_safety_ai_max_requests:
            raise ValueError("HERB_PRODUCT_SAFETY_REQUEST_LIMIT")
        self.counters["safety_batches"] += len(batches)
        self.counters["progress_stage"] = "product_safety"
        request_settings = replace(
            self.dedup_settings,
            herb_association_ai_context_tokens=settings.herb_safety_ai_context_tokens,
        )
        client = client_factory(request_settings)
        try:
            for number, (batch, user) in enumerate(zip(batches, users, strict=True), 1):
                checkpoint()
                self.counters["product_safety_ai_requests"] += 1
                self.counters["dedup_requests"] = self.counters.get("dedup_requests", 0) + 1
                sizes = {herb.id: len(exact[herb.id].candidates) for herb in batch}

                def request() -> int:
                    with index_batch(
                        replace(
                            request_settings,
                            herb_association_ai_timeout_seconds=min(
                                LOCAL_TIMEOUT_BASE_SECONDS
                                + LOCAL_TIMEOUT_PER_PRODUCT_SECONDS * len(batch),
                                request_settings.herb_association_ai_timeout_seconds,
                            ),
                        ),
                        run_id=session,
                        kind="product_safety",
                        batch=number,
                        batches=len(batches),
                        system=prompt,
                        user=user,
                        max_tokens=output,
                        clock=self.clock,
                    ):
                        raw = client.complete_json(prompt, user, output)
                        checkpoint()
                        valid, invalid = validate_dedup_response(raw, sizes)
                        # Do not cache a grouping under weights replaced during its request.
                        if digest_verifier(self.dedup_settings) != digest:
                            raise ValueError("HERB_PRODUCT_SAFETY_MODEL_CHANGED")
                        self.repository.save_dedup(
                            [
                                (herb_id, keys[herb_id], sizes[herb_id], found)
                                for herb_id, found in valid.items()
                            ],
                            self.dedup_semantics,
                            digest,
                        )
                        groups.update(valid)
                    return len(invalid)

                rejected = self._attempts(request, LOCAL_RETRY_SECONDS)
                self.counters["dedup_rejected_products"] = (
                    self.counters.get("dedup_rejected_products", 0) + rejected
                )
                self.counters["safety_batches_completed"] += 1
        finally:
            client.http.close()
        return [herb.id for herb in pending if herb.id not in groups]

    # An unfinished run of the same inputs is continued; otherwise a new one is started.
    def _open_run(self, language: Any, digest: str) -> tuple[str, dict[str, Any]]:
        with language_scope(language):
            semantic = run_semantic(self.settings, language, self.stages)
            existing = self.repository.resumable_run(semantic, digest, self.herbs)
            run_id = existing or str(uuid4())
            self.repository.create_run(run_id, self.herbs, semantic, digest, existing is not None)
            self.repository.copy_active(run_id, [herb.id for herb in self.outside])
        self.counters[f"resumed_{language}"] = existing is not None
        return run_id, semantic

    def _write_products(
        self,
        herbs: list[Herb],
        outcomes: dict[int, MergeOutcome],
        stage_keys: dict[int, list[str]],
        runs: dict[Any, tuple[str, dict[str, Any]]],
        digest: str,
    ) -> None:
        for language, (run_id, semantic) in runs.items():
            with language_scope(language):
                for herb in herbs:
                    checkpoint()
                    outcome = outcomes[herb.id]
                    key = content_hash(
                        [
                            product_identity(herb),
                            "merged",
                            BILINGUAL_VERSION,
                            language,
                            stage_keys[herb.id],
                        ]
                    )
                    self.repository.save_result(
                        run_id,
                        herb,
                        project_language(herb.id, outcome.status, outcome.messages, language),
                        semantic,
                        digest,
                        key=key,
                    )
