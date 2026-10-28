"""One local-model request per uncached catalog product; no corpus or association inference."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from contextvars import copy_context
from dataclasses import replace
from typing import Any
from uuid import uuid4

import psycopg

from backend.ai.client import AIUnavailable, ResponsesClient
from backend.ai.herb_association_classification import model_digest
from backend.ai.herb_association_rules import content_hash
from backend.ai.herb_product_safety import (
    product_prompt,
    product_semantic,
    serialize_product,
    validate_product_response,
)
from backend.ai.herb_product_safety_repository import ProductSafetyRepository
from backend.config import Settings
from backend.core.errors import ApplicationError, OperationCancelled
from backend.core.operation_context import OperationBudget, checkpoint, operation_budget
from scripts.herb_index_requests import emit_index_event, index_batch, make_client
from scripts.herb_safety_index import batch_progress, format_duration, workflow_progress


class ProductSafetyCoordinator:
    def __init__(
        self,
        settings: Settings,
        repository: ProductSafetyRepository,
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
        self.counters = counters if counters is not None else {}
        self.herbs = repository.read_products()
        self.semantic = product_semantic(settings)
        self.results = repository.cached(self.herbs, self.semantic, digest)
        self.state = repository.create_run(
            run_id,
            self.herbs,
            self.semantic,
            digest,
            resume,
            require_existing=require_existing,
        )
        self.started: float | None = None
        self.finished: float | None = None
        self.counters.update(
            safety_run_id=run_id,
            safety_source="model_knowledge",
            safety_targets=len(self.herbs),
            safety_products_total=len(self.herbs),
            safety_products_completed=0,
            safety_cache_hits=len(self.results),
            product_safety_ai_requests=0,
            warnings_only_ai_requests=0,
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

    def prepare(
        self,
        *,
        client_factory: Callable[[Settings], ResponsesClient] = make_client,
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
            return self._prepare(client_factory, digest_verifier)

    def _prepare(
        self,
        client_factory: Callable[[Settings], ResponsesClient],
        digest_verifier: Callable[[Settings], str],
    ) -> dict[str, Any]:
        self.counters["progress_stage"] = "product_safety_cache"
        pending = [herb for herb in self.herbs if herb.id not in self.results]
        self.counters["safety_batches"] = len(pending)
        if len(pending) > self.settings.herb_safety_ai_max_requests:
            raise ValueError("HERB_PRODUCT_SAFETY_REQUEST_LIMIT")
        if self.state != "ready":
            for herb in self.herbs:
                checkpoint()
                if herb.id in self.results:
                    self.repository.save_result(
                        self.run_id,
                        herb,
                        self.results[herb.id],
                        self.semantic,
                        self.digest,
                    )
                    self.counters["safety_products_completed"] += 1
            request_settings = replace(
                self.settings,
                herb_association_ai_context_tokens=self.settings.herb_safety_ai_context_tokens,
            )
            prompt = product_prompt()
            if content_hash(prompt) != self.semantic["prompt"]:
                raise ValueError("HERB_PRODUCT_SAFETY_CONFIGURATION_CHANGED")
            self.started = self.clock()
            self.counters["progress_stage"] = "product_safety"
            client = client_factory(request_settings) if pending else None
            try:
                for number, herb in enumerate(pending, 1):
                    checkpoint()
                    if product_semantic(self.settings) != self.semantic:
                        raise ValueError("HERB_PRODUCT_SAFETY_CONFIGURATION_CHANGED")
                    assert client is not None
                    self.repository.admit_request(
                        self.run_id, self.settings.herb_safety_ai_max_requests
                    )
                    self.counters["product_safety_ai_requests"] += 1
                    self.counters["warnings_only_ai_requests"] += 1
                    user = serialize_product(herb)
                    with index_batch(
                        request_settings,
                        run_id=self.run_id,
                        kind="product_safety",
                        batch=number,
                        batches=len(pending),
                        system=prompt,
                        user=user,
                        max_tokens=self.settings.herb_safety_ai_max_output_tokens,
                        clock=self.clock,
                    ):
                        raw = client.complete_json(
                            prompt, user, self.settings.herb_safety_ai_max_output_tokens
                        )
                        checkpoint()
                        result = validate_product_response(raw, herb.id)
                        # Do not cache a response under weights replaced during its request.
                        if digest_verifier(self.settings) != self.digest:
                            raise ValueError("HERB_PRODUCT_SAFETY_MODEL_CHANGED")
                        result = self.repository.save_result(
                            self.run_id, herb, result, self.semantic, self.digest
                        )
                        self.results[herb.id] = result
                    self.counters["safety_batches_completed"] += 1
                    self.counters["safety_products_completed"] += 1
            finally:
                if client is not None:
                    client.http.close()
            self.finished = self.clock()
            self.counters["progress_stage"] = "safety_finalization"
            if pending and digest_verifier(self.settings) != self.digest:
                raise ValueError("HERB_PRODUCT_SAFETY_MODEL_CHANGED")
            if product_semantic(self.settings) != self.semantic:
                raise ValueError("HERB_PRODUCT_SAFETY_CONFIGURATION_CHANGED")
            self.repository.finish(self.run_id, self.herbs, self.semantic)
        self.counters.update(
            safety_products_completed=len(self.herbs),
            safety_complete=sum(result.status == "complete" for result in self.results.values()),
            safety_partial=sum(result.status != "complete" for result in self.results.values()),
            safety_warnings=sum(len(result.messages) for result in self.results.values()),
            progress_stage="ready",
        )
        self.state = "ready"
        return self.counters


def run_product_safety_index(
    settings: Settings,
    *,
    analyze: bool = False,
    publish: str | None = None,
    resume: str | None = None,
) -> dict[str, Any]:
    repository = ProductSafetyRepository()
    started = time.monotonic()
    counters: dict[str, Any] = {
        "stage": "herb_product_safety",
        "progress_stage": "product_safety_inventory",
    }
    coordinator: ProductSafetyCoordinator | None = None
    stopped = threading.Event()

    def progress() -> None:
        elapsed = time.monotonic() - started
        counters["elapsed(hh:mm:ss)"] = format_duration(elapsed)
        counters["ai_requests_sent_total"] = counters.get("product_safety_ai_requests", 0)
        emit_index_event(
            {
                **counters,
                **workflow_progress(
                    counters,
                    elapsed,
                    coordinator.progress_metrics() if coordinator else None,
                ),
            }
        )

    def heartbeat() -> None:
        while not stopped.wait(60):
            progress()

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        with operation_budget(
            OperationBudget(
                started + settings.herb_safety_build_timeout_seconds,
                time.monotonic,
                lambda: None,
            )
        ):
            if publish:
                repository.publish(publish, settings, digest=model_digest(settings))
                counters.update(run_id=publish, status="published", progress_stage="publication")
                return counters
            if analyze:
                herbs = repository.read_products()
                semantic = product_semantic(settings)
                digest = repository.analysis_digest(semantic)
                cached = repository.cached(herbs, semantic, digest) if digest else {}
                counters.update(
                    status="analyzed",
                    safety_products_total=len(herbs),
                    safety_cache_hits=len(cached),
                    estimated_warning_requests=len(herbs) - len(cached),
                    model_digest_verified=False,
                )
                return counters
            coordinator = ProductSafetyCoordinator(
                settings,
                repository,
                resume or str(uuid4()),
                model_digest(settings),
                resume=bool(resume),
                require_existing=bool(resume),
                counters=counters,
            )
            coordinator.prepare()
            counters.update(run_id=coordinator.run_id, status="ready")
            return counters
    except (
        AIUnavailable,
        ApplicationError,
        ValueError,
        psycopg.Error,
        OSError,
        OperationCancelled,
    ) as error:
        counters.update(status="failed", error=type(error).__name__)
        raise
    finally:
        stopped.set()
        thread.join(timeout=1)
        progress()
