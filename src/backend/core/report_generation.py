"""Process-owned execution; session admission bounds the executor's pending work."""

from __future__ import annotations

import logging
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import httpx

from backend.ai.client import AIUnavailable
from backend.ai.report_validation import ReportValidationError
from backend.core.conversation import ConversationService, evidence_above
from backend.core.errors import ApplicationError, OperationCancelled
from backend.core.language import language_scope
from backend.core.models import SessionData, SessionOperation
from backend.core.report_batches import REPORT_GENERATION_WORKERS
from backend.core.report_metrics import validate_min_score
from backend.core.sessions import SessionStore
from backend.core.texts import tr

logger = logging.getLogger("naturist.reports")


class ReportGenerationService:
    def __init__(self, store: SessionStore) -> None:
        self.store = store
        self.executor = ThreadPoolExecutor(
            max_workers=REPORT_GENERATION_WORKERS,
            thread_name_prefix="report-generation",
        )
        self._lock = threading.RLock()
        self._pending: deque[tuple[ConversationService, SessionOperation, int]] = deque()
        self._draining = False
        self._closed = False

    def start(
        self,
        conversation: ConversationService,
        session: SessionData,
        search_id: str,
        min_score: int,
        request_id: str,
        model_choice: str,
    ) -> dict:
        validate_min_score(min_score)
        with self._lock:
            if self._closed:
                raise ApplicationError("SHUTTING_DOWN", tr("errors.application_shutting_down"), 503)
            self._prune_cancelled()
            # Capture the provider and evidence at admission, before joining the FIFO.
            provider = getattr(conversation.ai, "provider", None)
            job, operation = self.store.admit_generation(
                session,
                search_id,
                request_id,
                min_score,
                model_choice,
                getattr(provider, "name", "configured"),
                getattr(provider, "model", model_choice),
            )
            if operation is None:
                return self.generation(session, job["jobId"])
            try:
                search = operation.snapshot.search
                assert search is not None
                evidence = evidence_above(search.evidence, min_score)
                if not evidence:
                    raise ApplicationError(
                        "NO_ELIGIBLE_FRAGMENTS",
                        tr("interface.generate_no_eligible_fragments"),
                        422,
                    )
                self._pending.append((conversation, operation, min_score))
                if not self._draining:
                    self.executor.submit(self._drain)
                    self._draining = True
            except Exception as exc:
                self._pending = deque(item for item in self._pending if item[1] is not operation)
                self.store.fail_generation(
                    operation,
                    getattr(exc, "code", "GENERATION_UNAVAILABLE"),
                    tr("errors.generation_start_failed"),
                )
                self.store.finish_operation(operation)
                if isinstance(exc, ApplicationError):
                    raise
                raise ApplicationError(
                    "GENERATION_UNAVAILABLE", tr("errors.generation_start_failed"), 503
                ) from None
            return self.generation(session, job["jobId"])

    def _prune_cancelled(self) -> None:
        pending: deque[tuple[ConversationService, SessionOperation, int]] = deque()
        for item in self._pending:
            try:
                self.store.checkpoint(item[1])
            except OperationCancelled:
                # No AI call exists for a queued job, so its slot can be released now.
                self.store.finish_operation(item[1])
            else:
                pending.append(item)
        self._pending = pending

    def generation(self, session: SessionData, job_id: str, *, cancel: bool = False) -> dict:
        with self._lock:
            self.store.generation(session, job_id, cancel=cancel)
            self._prune_cancelled()
            result = self.store.generation(session, job_id)
            result["queuePosition"] = next(
                (
                    index
                    for index, item in enumerate(self._pending, 1)
                    if item[1].operation_id == job_id
                ),
                None,
            )
            return result

    def _drain(self) -> None:
        while True:
            with self._lock:
                self._prune_cancelled()
                if not self._pending:
                    self._draining = False
                    return
                conversation, operation, min_score = self._pending.popleft()
            # Run synchronously: the next item cannot start until this worker's finally.
            with language_scope(operation.snapshot.language):
                self._run(conversation, operation, min_score)

    def _run(
        self, conversation: ConversationService, operation: SessionOperation, min_score: int
    ) -> None:
        logger.info("report_job_started job_id=%s", operation.operation_id)
        try:
            self.store.generation_stage(operation, "preparing")
            result = conversation.generate(
                operation.session,
                operation.search_id or "",
                min_score,
                admitted=operation,
            )
            if not result.cancelled:
                logger.info("report_job_finished job_id=%s", operation.operation_id)
        except OperationCancelled:
            pass
        except Exception as exc:
            code = getattr(exc, "code", "REPORT_GENERATION_FAILED")
            if isinstance(exc, AIUnavailable):
                code = {
                    "timeout": "AI_READ_TIMEOUT",
                    "rate_limited": "AI_RATE_LIMITED",
                    "invalid_response": "AI_RESPONSE_INVALID",
                    "output_limit": "AI_OUTPUT_LIMIT_EXCEEDED",
                    "context_limit": "AI_CONTEXT_LIMIT_EXCEEDED",
                    "repetition_limit": "AI_REPETITION_LIMIT_EXCEEDED",
                    "model_not_found": "AI_MODEL_NOT_FOUND",
                }.get(exc.reason, "AI_PROVIDER_UNAVAILABLE")
            elif isinstance(exc, httpx.TimeoutException):
                code = "AI_READ_TIMEOUT"
            elif isinstance(exc, ReportValidationError):
                code = "AI_RESPONSE_INVALID"
            # Stage identifies PDF/commit failures without exposing exception content.
            try:
                status = self.store.generation(operation.session, operation.operation_id)
            except ApplicationError:
                status = {}
            if status.get("stage") == "rendering_pdf":
                code = "PDF_GENERATION_FAILED"
            elif status.get("stage") == "publishing":
                code = "REPORT_COMMIT_FAILED"
            self.store.fail_generation(
                operation,
                code,
                exc.message
                if isinstance(exc, ApplicationError)
                else {
                    "AI_READ_TIMEOUT": tr("errors.ai_read_timeout"),
                    "AI_RATE_LIMITED": tr("errors.ai_rate_limited"),
                    "AI_RESPONSE_INVALID": tr("errors.ai_response_invalid_retry"),
                    "AI_OUTPUT_LIMIT_EXCEEDED": (tr("errors.ai_output_limit_guidance")),
                    "AI_MODEL_NOT_FOUND": (tr("errors.ollama_model_unavailable")),
                    "AI_CONTEXT_LIMIT_EXCEEDED": (tr("errors.ai_context_limit")),
                    "AI_REPETITION_LIMIT_EXCEEDED": tr("errors.ai_repetition_limit"),
                    "PDF_GENERATION_FAILED": tr("errors.pdf_failed"),
                    "REPORT_COMMIT_FAILED": tr("errors.report_commit_failed"),
                }.get(
                    code,
                    tr("errors.ai_generation_failed"),
                ),
            )
        finally:
            self.store.finish_operation(operation)
            logger.info("report_job_worker_finished job_id=%s", operation.operation_id)

    def close(self, *, wait: bool = True) -> None:
        with self._lock:
            self._closed = True
            for _, operation, _ in self._pending:
                operation.cancellation.set()
            self._prune_cancelled()
        self.executor.shutdown(wait=wait, cancel_futures=False)
