"""Process-owned execution; session admission bounds the executor's pending work."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import httpx

from backend.ai.client import AIUnavailable
from backend.ai.report_validation import ReportValidationError
from backend.core.conversation import ConversationService, evidence_above, evidence_within_budget
from backend.core.errors import ApplicationError, OperationCancelled
from backend.core.models import SessionData, SessionOperation
from backend.core.sessions import SessionStore

logger = logging.getLogger("naturist.reports")


class ReportGenerationService:
    def __init__(self, store: SessionStore) -> None:
        self.store = store
        self.executor = ThreadPoolExecutor(
            max_workers=store.limits.max_concurrent_generations,
            thread_name_prefix="report-generation",
        )

    def start(
        self,
        conversation: ConversationService,
        session: SessionData,
        search_id: str,
        min_score: float,
        request_id: str,
        model_choice: str,
    ) -> dict:
        # Provider client is captured here and never reselected by the worker.
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
            return job
        try:
            search = operation.snapshot.search
            assert search is not None
            evidence = evidence_above(search.evidence, min_score)
            if not evidence:
                raise ApplicationError(
                    "NO_ELIGIBLE_FRAGMENTS", "Niciun fragment nu atinge scorul minim selectat.", 422
                )
            if not evidence_within_budget(evidence, conversation.ai.context_budget()):
                raise ApplicationError(
                    "AI_CONTEXT_LIMIT",
                    "Fragmentele depășesc limita de context a modelului ales.",
                    422,
                )
            self.executor.submit(self._run, conversation, operation, min_score)
        except Exception as exc:
            self.store.fail_generation(
                operation,
                getattr(exc, "code", "GENERATION_UNAVAILABLE"),
                "Generarea nu a putut fi pornită.",
            )
            self.store.finish_operation(operation)
            if isinstance(exc, ApplicationError):
                raise
            raise ApplicationError(
                "GENERATION_UNAVAILABLE", "Generarea nu a putut fi pornită.", 503
            ) from None
        return job

    def _run(
        self, conversation: ConversationService, operation: SessionOperation, min_score: float
    ) -> None:
        logger.info("report_job_started job_id=%s", operation.operation_id)
        try:
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
                    "context_limit": "AI_CONTEXT_LIMIT_EXCEEDED",
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
                    "AI_READ_TIMEOUT": "Furnizorul AI nu a transmis date în timpul alocat. Puteți încerca din nou.",
                    "AI_RATE_LIMITED": "Limita de utilizare a furnizorului AI a fost atinsă. Încercați mai târziu.",
                    "AI_RESPONSE_INVALID": "Răspunsul AI nu a putut fi validat. Puteți încerca din nou.",
                    "AI_CONTEXT_LIMIT_EXCEEDED": (
                        "Fragmentele selectate depășesc contextul disponibil al modelului. "
                        "Selectați mai puține fragmente sau creșteți scorul minim. "
                        "Conținutul nu a fost trunchiat."
                    ),
                    "PDF_GENERATION_FAILED": "PDF-ul nu a putut fi creat. Puteți încerca din nou.",
                    "REPORT_COMMIT_FAILED": "Raportul nu a putut fi salvat în sesiune.",
                }.get(
                    code,
                    "Furnizorul AI nu este disponibil sau raportul nu a putut fi generat. Puteți încerca din nou.",
                ),
            )
        finally:
            self.store.finish_operation(operation)
            logger.info("report_job_worker_finished job_id=%s", operation.operation_id)

    def close(self, *, wait: bool = True) -> None:
        # Submitted jobs own reservations; they must execute their finally cleanup.
        self.executor.shutdown(wait=wait, cancel_futures=False)
