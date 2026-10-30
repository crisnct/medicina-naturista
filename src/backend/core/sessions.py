"""Atomic tab lifetimes, operation commits and bounded ephemeral retention.

Every API acquires registry -> session. Callers must never acquire the registry
while holding a session lock. External I/O is forbidden inside these APIs.
"""

from __future__ import annotations

import copy
import json
import logging
import secrets
import shutil
import stat
import struct
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from backend.ai.search import ALL_SIGNALS
from backend.config import Settings
from backend.core.contracts import HerbEvidenceReference, HerbSafetyReference
from backend.core.errors import ApplicationError, OperationCancelled
from backend.core.language import Language, current_language
from backend.core.models import (
    MAX_KEPT_REPORTS,
    MAX_KEPT_SEARCHES,
    AIActivity,
    CommitChange,
    ConversationGroup,
    HealthProfile,
    MessageRouting,
    OperationResult,
    ReportBatchPreview,
    ReportGeneration,
    SessionData,
    SessionOperation,
    SessionSnapshot,
)
from backend.core.operation_context import ReportActivity
from backend.core.rate_limits import RateLimiter
from backend.core.texts import tr

logger = logging.getLogger("naturist.sessions")
MARKER = ".naturist-session"
STATE_FIELDS = (
    "profile",
    "history",
    "searches",
    "reports",
    "selected_categories",
    "search_signals",
    "report_id",
    "report_bytes",
    "current_group_id",
    "groups",
    "context_revision",
    "routing",
    "message_receipts",
    "generations",
    "generation_receipts",
)


def serialized_bytes(value) -> int:
    """Single deterministic UTF-8 representation; MiB/KiB are powers of 1024."""
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


@dataclass(frozen=True)
class RetainedUsage:
    history: int
    evidence: int
    pdf: int
    total: int


def retained_usage(session: SessionData) -> RetainedUsage:
    # Fragment text is a view of the search evidence: count that resource once.
    # report_bytes aliases the latest StoredReport.data and is never added again.
    history = serialized_bytes(
        [
            {k: v for k, v in m.items() if k != "fragments"} if m.get("kind") == "fragments" else m
            for m in session.history
        ]
    )
    searches = {sid: asdict(search) for sid, search in session.searches.items()}
    evidence = serialized_bytes(searches)
    pdf = sum(len(report.data) for report in session.reports.values())
    metadata = serialized_bytes(
        {
            "profile": asdict(session.profile),
            "routing": asdict(session.routing),
            "message_receipts": session.message_receipts,
            # Fixed metadata slots cover bounded terminal errors/warnings as they grow.
            "generation_slots": len(session.generations),
            "generation_receipts": session.generation_receipts,
            "categories": sorted(session.selected_categories),
            "signals": asdict(session.search_signals),
            "groups": {gid: asdict(group) for gid, group in session.groups.items()},
            "reports": {
                rid: {"filename": r.filename, "health_problem": r.health_problem}
                for rid, r in session.reports.items()
            },
            "report_id": session.report_id,
            "lifetime_id": session.lifetime_id,
            "context_revision": session.context_revision,
            "current_group_id": session.current_group_id,
            "tab_id": session.tab_id,
            "cookie_id": session.cookie_id,
            "client_ip": session.client_ip,
            "closed": session.closed,
            "created_at": struct.pack("!d", session.created_at).hex(),
            "last_seen": struct.pack("!d", session.last_seen).hex(),
        }
    )
    return RetainedUsage(
        history,
        evidence,
        pdf,
        history
        + evidence
        + pdf
        + metadata
        + 8192 * len(session.generations)
        + sum(
            job.stream_bytes
            + job.thinking_bytes
            + job.report_preview_bytes
            + job.batch_previews_bytes
            for job in session.generations.values()
        ),
    )


class SessionStore:
    def __init__(
        self,
        temp_root: Path,
        idle_seconds: int,
        max_seconds: int,
        limits: Settings | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limits = limits or Settings()
        self.clock = clock
        self.temp_root = temp_root.resolve()
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.idle_seconds = idle_seconds
        self.max_seconds = max_seconds
        self._sessions: dict[tuple[str, str], SessionData] = {}
        self._workers: dict[str, SessionOperation] = {}
        self._lock = threading.RLock()
        self._finished = threading.Condition(self._lock)
        self._used_bytes = 0
        self._reserved_bytes = 0
        self._accepting = True
        self.creation_limiter = RateLimiter(clock)
        # Only app-owned direct children are eligible; never traverse junctions.
        for child in self.temp_root.iterdir():
            if self._owned_directory(child):
                shutil.rmtree(child)

    def _owned_directory(self, path: Path) -> bool:
        return (
            path.is_dir()
            and not path.is_symlink()
            and not (
                getattr(path.lstat(), "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            )
            and (
                path.resolve().parent == self.temp_root
                and (path / MARKER).is_file()
                and not (path / MARKER).is_symlink()
            )
        )

    def _expired(self, session: SessionData) -> bool:
        now = self.clock()
        return (
            now - session.last_seen >= self.idle_seconds
            or now - session.created_at >= self.max_seconds
            or (session.detached_until is not None and now >= session.detached_until)
        )

    def get(
        self,
        cookie_id: str,
        tab_id: str,
        create: bool = False,
        *,
        client_ip: str = "unknown",
    ) -> SessionData | None:
        if not cookie_id or not tab_id:
            return None
        key = cookie_id, tab_id
        with self._lock:
            session = self._sessions.get(key)
            if session and self._expired(session):
                self._delete_locked(key)
                session = None
            if session is None and create:
                if not self._accepting:
                    raise ApplicationError(
                        "SHUTTING_DOWN", tr("errors.application_shutting_down"), 503
                    )
                # Reclaim expired entries before applying allocation limits.
                self._sweep_locked()
                if len(self._sessions) >= self.limits.max_active_sessions:
                    raise ApplicationError(
                        "GLOBAL_SESSION_LIMIT",
                        tr("errors.application_capacity"),
                        503,
                    )
                self.creation_limiter.check(
                    (f"ip:{client_ip}", self.limits.new_sessions_per_ip_minute),
                    (f"cookie:{cookie_id}", self.limits.new_sessions_per_cookie_minute),
                )
                directory = self.temp_root / ("session-" + secrets.token_hex(20))
                session = SessionData(
                    cookie_id,
                    tab_id,
                    directory,
                    client_ip=client_ip,
                    created_at=self.clock(),
                    last_seen=self.clock(),
                )
                usage = retained_usage(session)
                if usage.total > self.limits.max_session_bytes:
                    raise ApplicationError("SESSION_BUDGET", tr("errors.session_budget_exceeded"))
                self._check_global(usage.total)
                directory.mkdir(mode=0o700)
                try:
                    (directory / MARKER).touch(mode=0o600)
                except OSError:
                    shutil.rmtree(directory)
                    raise
                self._sessions[key] = session
                session.retained_bytes = usage.total
                self._used_bytes += usage.total
            if session:
                with session.lock:
                    session.last_seen = self.clock()
            return session

    def _check_global(self, additional: int) -> None:
        if self._used_bytes + self._reserved_bytes + additional > self.limits.max_global_bytes:
            raise ApplicationError("GLOBAL_BUDGET", tr("errors.application_capacity"), 503)

    def _valid(self, operation: SessionOperation) -> bool:
        if self._workers.get(operation.operation_id) is not operation:
            return False
        s = operation.session
        if self._sessions.get((s.cookie_id, s.tab_id)) is not s or s.closed:
            return False
        if self._expired(s):
            self._delete_locked((s.cookie_id, s.tab_id))
            return False
        if (
            operation.cancellation.is_set()
            or operation.state != "running"
            or operation.snapshot.lifetime_id != s.lifetime_id
            or self.clock() >= operation.deadline
        ):
            return False
        if operation.kind in {"message", "classify", "condition", "search", "initialize"}:
            return operation.snapshot.context_revision == s.context_revision
        if operation.kind == "generate":
            search = s.searches.get(operation.search_id or "")
            return (
                search is not None
                and operation.snapshot.search is not None
                and search.identity == operation.snapshot.search.identity
            )
        if operation.kind == "email":
            return operation.snapshot.context_revision == s.context_revision and (
                operation.snapshot.report is None or operation.snapshot.report_id in s.reports
            )
        return True

    def begin_operation(
        self,
        session: SessionData,
        kind: str,
        *,
        search_id: str | None = None,
        expected_revision: int | None = None,
        report_id: str | None = None,
        queue_generation: bool = False,
    ) -> SessionOperation:
        """Reserve lifetime/resource/capacity atomically, before external calls."""
        with self._lock, session.lock:
            if (
                not self._accepting
                or session.closed
                or self._sessions.get((session.cookie_id, session.tab_id)) is not session
            ):
                raise ApplicationError("SESSION_CLOSED", tr("errors.session_closed"))
            if self._expired(session):
                self._delete_locked((session.cookie_id, session.tab_id))
                raise ApplicationError("SESSION_EXPIRED", tr("errors.session_expired"))
            if expected_revision is not None and expected_revision != session.context_revision:
                raise OperationCancelled()
            search = session.searches.get(search_id or "")
            if kind == "generate" and search is None:
                raise ApplicationError(
                    "SEARCH_UNAVAILABLE",
                    tr("errors.search_evidence_missing"),
                )
            if kind == "generate" and search is not None and search.intent != "remedii":
                raise ApplicationError(
                    "REPORT_NOT_ALLOWED",
                    tr("errors.report_intent_required"),
                    409,
                )
            active = [
                op
                for op in self._workers.values()
                if op.state == "running" and not op.cancellation.is_set()
            ]
            if kind == "classify" and any(
                op.session is session and op.kind == kind for op in active
            ):
                raise ApplicationError(
                    "CLASSIFICATION_IN_PROGRESS", tr("errors.classification_in_progress"), 409
                )
            if kind == "generate" and any(
                op.session is session and op.kind == kind and op.search_id == search_id
                for op in active
            ):
                raise ApplicationError(
                    "GENERATION_IN_PROGRESS",
                    tr("errors.search_already_generating"),
                )
            # Count workers until finally, even when cancelled; network threads may still run.
            if kind in {"classify", "search", "condition", "generate", "email", "herb_evidence"}:
                category = "generate" if kind == "generate" else "search"
                cap = (
                    self.limits.max_concurrent_generations
                    if category == "generate"
                    else self.limits.max_concurrent_searches
                )
                if category == "generate" and queue_generation:
                    cap += self.limits.max_queued_generations
                count = sum(
                    ("generate" if op.kind == "generate" else "search") == category
                    for op in self._workers.values()
                    if op.kind
                    in {"classify", "search", "condition", "generate", "email", "herb_evidence"}
                )
                if count >= cap:
                    if category == "generate":
                        raise ApplicationError(
                            "GENERATION_QUEUE_FULL" if queue_generation else "GENERATION_CAPACITY",
                            tr("errors.generation_queue_full")
                            if queue_generation
                            else tr("errors.generation_capacity"),
                            429,
                            retry_after=5,
                        )
                    raise ApplicationError(
                        "OPERATION_LIMIT",
                        tr("errors.operation_capacity"),
                        429,
                    )
            group_id = session.current_group_id
            if kind == "generate":
                group_id = next(
                    gid for gid, g in session.groups.items() if search_id in g.search_ids
                )
            selected_report_id = report_id if report_id is not None else session.report_id
            latest = session.reports.get(selected_report_id or "")
            if kind == "email" and latest:
                group_id = next(
                    gid for gid, g in session.groups.items() if selected_report_id in g.report_ids
                )
            snapshot = SessionSnapshot(
                session.lifetime_id,
                session.context_revision,
                group_id,
                session.tab_id,
                copy.deepcopy(session.profile),
                set(session.selected_categories),
                session.search_signals,
                copy.deepcopy(search) if kind == "generate" else None,
                copy.deepcopy(latest) if kind == "email" else None,
                selected_report_id,
                copy.deepcopy(session.routing),
                copy.deepcopy(session.message_receipts),
                language=(
                    search.language
                    if kind == "generate" and search
                    else latest.language
                    if kind == "email" and latest
                    else current_language()
                ),
            )
            snapshot.profile.language = snapshot.language
            reservation = self.limits.operation_reservation_bytes
            reservation += serialized_bytes(
                {
                    "profile": asdict(snapshot.profile),
                    "routing": asdict(snapshot.routing),
                    "message_receipts": snapshot.message_receipts,
                    "selected_categories": sorted(snapshot.selected_categories),
                    "search_signals": asdict(snapshot.search_signals),
                    "lifetime_id": snapshot.lifetime_id,
                    "context_revision": snapshot.context_revision,
                    "group_id": snapshot.group_id,
                    "tab_id": snapshot.tab_id,
                    "report_id": snapshot.report_id,
                }
            )
            if snapshot.search:
                reservation += serialized_bytes(asdict(snapshot.search))
            if snapshot.report:
                reservation += len(snapshot.report.data)
                reservation += serialized_bytes(
                    {
                        "filename": snapshot.report.filename,
                        "health_problem": snapshot.report.health_problem,
                    }
                )
            if (
                retained_usage(session).total + self._session_reserved(session) + reservation
                > self.limits.max_session_bytes
            ):
                raise ApplicationError("SESSION_BUDGET", tr("errors.session_budget_exceeded"))
            self._check_global(reservation)
            op = SessionOperation(
                secrets.token_urlsafe(18),
                kind,
                session,
                snapshot,
                min(
                    self.clock()
                    + (
                        self.max_seconds
                        if queue_generation
                        else self.limits.report_generation_timeout_seconds
                        if kind == "generate"
                        else self.limits.operation_timeout_seconds
                    ),
                    session.created_at + self.max_seconds,
                ),
                reserved_bytes=reservation,
                search_id=search_id,
            )
            self._workers[op.operation_id] = op
            self._reserved_bytes += reservation
            return op

    def _session_reserved(
        self, session: SessionData, excluding: SessionOperation | None = None
    ) -> int:
        return sum(
            op.reserved_bytes
            for op in self._workers.values()
            if op.session is session and op is not excluding
        )

    def admit_generation(
        self,
        session: SessionData,
        search_id: str,
        request_id: str,
        min_score: int,
        model_choice: str,
        provider: str,
        model: str,
    ) -> tuple[dict[str, Any], SessionOperation | None]:
        """Reserve exactly once, including retries whose first HTTP reply was lost."""
        with self._lock, session.lock:
            existing_id = session.generation_receipts.get(request_id)
            existing = session.generations.get(existing_id or "")
            if existing:
                if (existing.search_id, existing.min_score, existing.model_choice) != (
                    search_id,
                    min_score,
                    model_choice,
                ):
                    raise ApplicationError(
                        "IDEMPOTENCY_CONFLICT",
                        tr("errors.request_options_conflict"),
                        409,
                    )
                return copy.deepcopy(existing.as_dict(self.clock())), None
            for job in session.generations.values():
                if job.search_id == search_id and job.job_id in self._workers:
                    if (job.min_score, job.model_choice) != (min_score, model_choice):
                        raise ApplicationError(
                            "GENERATION_IN_PROGRESS",
                            tr("errors.search_already_generating"),
                            409,
                        )
                    if len(session.generation_receipts) >= 64:
                        raise ApplicationError(
                            "GENERATION_HISTORY_LIMIT",
                            tr("errors.session_attempt_limit"),
                            429,
                        )
                    previous = session.retained_bytes
                    session.generation_receipts[request_id] = job.job_id
                    usage = retained_usage(session)
                    try:
                        self._check_global(usage.total - previous)
                        if (
                            usage.total + self._session_reserved(session)
                            > self.limits.max_session_bytes
                        ):
                            raise ApplicationError(
                                "SESSION_BUDGET", tr("errors.session_budget_exceeded"), 409
                            )
                    except Exception:
                        del session.generation_receipts[request_id]
                        raise
                    self._used_bytes += usage.total - previous
                    session.retained_bytes = usage.total
                    return copy.deepcopy(job.as_dict(self.clock())), None
            if len(session.generations) >= 32:
                raise ApplicationError(
                    "GENERATION_HISTORY_LIMIT",
                    tr("errors.session_generation_limit"),
                    429,
                )
            operation = self.begin_operation(
                session, "generate", search_id=search_id, queue_generation=True
            )
            previous = session.retained_bytes
            job = ReportGeneration(
                operation.operation_id,
                search_id,
                request_id,
                min_score,
                model_choice,
                provider[:128],
                model[:128],
                time.time(),
                time.time() + max(0, operation.deadline - self.clock()),
                language=operation.snapshot.language,
            )
            session.generations[job.job_id] = job
            session.generation_receipts[request_id] = job.job_id
            try:
                usage = retained_usage(session)
                if usage.total + self._session_reserved(session) > self.limits.max_session_bytes:
                    raise ApplicationError(
                        "SESSION_BUDGET", tr("errors.session_budget_exceeded"), 409
                    )
                self._check_global(usage.total - previous)
                self._used_bytes += usage.total - previous
                session.retained_bytes = usage.total
            except Exception:
                del session.generations[job.job_id]
                del session.generation_receipts[request_id]
                self.finish_operation(operation)
                raise
            logger.info(
                "report_job_accepted job_id=%s provider=%s model=%s", job.job_id, provider, model
            )
            return copy.deepcopy(job.as_dict(self.clock())), operation

    def generation(
        self, session: SessionData, job_id: str, *, cancel: bool = False
    ) -> dict[str, Any]:
        with self._lock, session.lock:
            self._sweep_locked()
            job = session.generations.get(job_id)
            if (
                session.closed
                or self._sessions.get((session.cookie_id, session.tab_id)) is not session
                or not job
            ):
                raise ApplicationError(
                    "GENERATION_NOT_FOUND", tr("common.generation_unavailable"), 404
                )
            operation = self._workers.get(job_id)
            if cancel and operation and job.state in {"accepted", "running"}:
                self._cancel(operation)
            result = copy.deepcopy(job.as_dict(self.clock()))
            result["workerActive"] = operation is not None
            if job.report_id and job.report_id not in session.reports:
                result["reportId"] = None
                result["message"] = tr("errors.report_unavailable")
            return result

    def generation_stage(self, operation: SessionOperation, stage: str) -> None:
        with self._lock, operation.session.lock:
            self.checkpoint(operation)
            job = operation.session.generations.get(operation.operation_id)
            if job:
                if job.state == "accepted":
                    operation.deadline = min(
                        self.clock() + self.limits.report_generation_timeout_seconds,
                        operation.session.created_at + self.max_seconds,
                    )
                    job.deadline_at = time.time() + max(0, operation.deadline - self.clock())
                job.state = "running"
                job.stage = stage
                job.started_at = job.started_at or time.time()
                logger.info("report_job_stage_changed job_id=%s stage=%s", job.job_id, stage)

    def generation_activity(
        self, operation: SessionOperation, event: ReportActivity, *, batch_index: int | None = None
    ) -> None:
        with self._lock, operation.session.lock:
            self.checkpoint(operation)
            job = operation.session.generations.get(operation.operation_id)
            if not job or job.state != "running" or job.stage != "generating":
                return
            batch = self._report_batch(job, batch_index)
            now = self.clock()
            if batch is not None and event.kind in {"batch_failed", "batch_cancelled"}:
                previews = list(job.batch_previews)
                previews[batch.index - 1] = replace(
                    batch,
                    started=True,
                    failed=event.kind == "batch_failed",
                    cancelled=event.kind == "batch_cancelled",
                )
                self._store_batch_previews(operation.session, job, previews)
                return
            if event.kind == "request_started":
                job.ai_activity = AIActivity(now)
                if batch is not None:
                    previews = list(job.batch_previews)
                    previews[batch.index - 1] = replace(
                        batch,
                        started=True,
                        ai_activity=job.ai_activity,
                    )
                    self._store_batch_previews(operation.session, job, previews)
                return
            activity = batch.ai_activity if batch is not None else job.ai_activity
            if activity is None:
                return
            job.ai_activity = activity
            previous_phase = activity.phase
            if activity.first_event_at is None:
                activity.first_event_at = now
            activity.last_activity_at = now
            if event.kind == "answering":
                activity.phase = "answering"
                if activity.first_answer_at is None:
                    activity.first_answer_at = now
            elif event.kind == "thinking":
                if activity.first_thinking_at is None:
                    activity.first_thinking_at = now
                if activity.phase != "answering":
                    activity.phase = "thinking"
            elif activity.phase == "waiting":
                activity.phase = "processing"
            if previous_phase != activity.phase:
                logger.info(
                    "report_ai_phase_changed job_id=%s batch=%s phase=%s",
                    job.job_id,
                    batch_index,
                    activity.phase,
                )
            if event.kind == "response_finished":
                logger.info(
                    "report_ai_timing job_id=%s batch=%s first_event_ms=%s first_thinking_ms=%s "
                    "first_answer_ms=%s duration_ms=%s metrics=%s",
                    job.job_id,
                    batch_index,
                    activity.as_dict(now)["firstEventElapsedMs"],
                    activity.as_dict(now)["firstThinkingElapsedMs"],
                    activity.as_dict(now)["firstAnswerElapsedMs"],
                    max(0, round((now - activity.request_started_at) * 1000)),
                    json.dumps(event.metrics or {}, sort_keys=True),
                )

    def generation_output(
        self,
        operation: SessionOperation,
        text: str,
        *,
        thinking: bool = False,
        measure: bool = True,
        batch_index: int | None = None,
    ) -> None:
        if not text:
            return
        with self._lock, operation.session.lock:
            self.checkpoint(operation)
            session = operation.session
            job = session.generations.get(operation.operation_id)
            if job and job.state == "running" and job.stage == "generating":
                batch = self._report_batch(job, batch_index)
                # JSON string bytes are additive after removing the enclosing quotes.
                added_bytes = serialized_bytes(text) - 2
                if (
                    session.retained_bytes + self._session_reserved(session) + added_bytes
                    > self.limits.max_session_bytes
                ):
                    raise ApplicationError(
                        "SESSION_BUDGET", tr("errors.ai_text_budget_exceeded"), 409
                    )
                self._check_global(added_bytes)
                if thinking:
                    (batch.thinking_parts if batch is not None else job.thinking_parts).append(text)
                    job.thinking_bytes += added_bytes
                    if measure:
                        job.thinking_rate.record(text, self.clock())
                    activity = batch.ai_activity if batch is not None else job.ai_activity
                    if measure and activity:
                        activity.thinking_characters_received += len(text)
                else:
                    (batch.stream_parts if batch is not None else job.stream_parts).append(text)
                    job.stream_bytes += added_bytes
                    if measure:
                        job.stream_rate.record(text, self.clock())
                session.retained_bytes += added_bytes
                self._used_bytes += added_bytes

    @staticmethod
    def _report_batch(job: ReportGeneration, index: int | None) -> ReportBatchPreview | None:
        if index is None:
            return None
        if not 1 <= index <= len(job.batch_previews):
            raise ValueError("Report batch is not in the admitted plan")
        return job.batch_previews[index - 1]

    # Callers own registry -> session locks; reserve 2 KiB per batch for mutable activity metadata.
    def _store_batch_previews(
        self, session: SessionData, job: ReportGeneration, previews: list[ReportBatchPreview]
    ) -> None:
        size = (
            (serialized_bytes([batch.metadata() for batch in previews]) + 2048 * len(previews))
            if previews
            else 0
        )
        added_bytes = size - job.batch_previews_bytes
        if (
            session.retained_bytes + self._session_reserved(session) + added_bytes
            > self.limits.max_session_bytes
        ):
            raise ApplicationError("SESSION_BUDGET", tr("errors.preview_budget_exceeded"), 409)
        self._check_global(max(0, added_bytes))
        job.batch_previews = previews
        job.batch_previews_bytes = size
        session.retained_bytes += added_bytes
        self._used_bytes += added_bytes

    # Each validated snapshot belongs to its own batch; the final report is combined elsewhere.
    def generation_batch(
        self, operation: SessionOperation, completed: int, total: int, preview: str | None
    ) -> None:
        with self._lock, operation.session.lock:
            self.checkpoint(operation)
            session = operation.session
            job = session.generations.get(operation.operation_id)
            if job is None or job.state != "running" or job.stage != "generating":
                return
            if not 0 <= completed <= total:
                raise ValueError("Invalid report batch progress")
            if completed == 0 and job.batches_total or job.batches_total not in {0, total}:
                raise ValueError("Report batch plan cannot change during generation")
            previews = list(job.batch_previews) or [
                ReportBatchPreview(index=index) for index in range(1, total + 1)
            ]
            if completed:
                if preview is None:
                    raise ValueError("Missing validated report batch snapshot")
                previews[completed - 1] = replace(
                    previews[completed - 1],
                    started=True,
                    completed=True,
                    report_preview=preview,
                )
            self._store_batch_previews(session, job, previews)
            # Legacy consumers receive the latest batch; its string is already charged above.
            session.retained_bytes -= job.report_preview_bytes
            self._used_bytes -= job.report_preview_bytes
            job.report_preview = preview
            job.report_preview_bytes = 0
            job.batches_completed = sum(batch.completed for batch in previews)
            job.batches_total = total
            job.preview_version += 1

    def fail_generation(self, operation: SessionOperation, code: str, message: str) -> None:
        with self._lock, operation.session.lock:
            job = operation.session.generations.get(operation.operation_id)
            if job and job.state in {"accepted", "running"}:
                if not self._valid(operation):
                    self._cancel(operation)
                    return
                job.state, job.error_code, job.message = "failed", code[:64], message[:300]
                job.finished_at = time.time()
                logger.warning(
                    "report_job_failed job_id=%s code=%s stage=%s", job.job_id, code, job.stage
                )

    def checkpoint(self, operation: SessionOperation) -> None:
        with self._lock, operation.session.lock:
            if not self._valid(operation):
                self._cancel(operation)
                raise OperationCancelled()

    def _cancel(self, operation: SessionOperation) -> None:
        job = operation.session.generations.get(operation.operation_id)
        if job and job.state in {"accepted", "running"}:
            timed_out = self.clock() >= operation.deadline
            job.state = "timed_out" if timed_out else "cancelled"
            job.error_code = "GENERATION_TIMED_OUT" if timed_out else "GENERATION_CANCELLED"
            job.message = (
                tr("errors.generation_timeout") if timed_out else tr("errors.generation_cancelled")
            )
            job.finished_at = time.time()
            logger.info("report_job_%s job_id=%s", job.state, job.job_id)
        operation.cancellation.set()
        if self._workers.get(operation.operation_id) is operation:
            self._reserved_bytes -= operation.reserved_bytes
        operation.reserved_bytes = 0
        operation.state = "cancelled"

    def finish_operation(self, operation: SessionOperation) -> None:
        """Release exactly once. Invoke in a worker's finally block, never at HTTP timeout."""
        with self._finished:
            if self._workers.get(operation.operation_id) is not operation:
                return
            self._reserved_bytes -= operation.reserved_bytes
            operation.reserved_bytes = 0
            self._workers.pop(operation.operation_id, None)
            job = operation.session.generations.get(operation.operation_id)
            if job:
                session = operation.session
                # Retain failed/interrupted previews for inspection within the session budget.
                interrupted = job.state in {"failed", "cancelled", "timed_out"}
                released_bytes = 0
                if job.state != "succeeded" and not interrupted:
                    released_bytes += job.stream_bytes
                    job.stream_parts.clear()
                    for batch in job.batch_previews:
                        batch.stream_parts.clear()
                    job.stream_bytes = 0
                if not interrupted:
                    released_bytes += job.thinking_bytes
                    job.thinking_parts.clear()
                    for batch in job.batch_previews:
                        batch.thinking_parts.clear()
                    job.thinking_bytes = 0
                if self._sessions.get((session.cookie_id, session.tab_id)) is session:
                    session.retained_bytes -= released_bytes
                    self._used_bytes -= released_bytes
            if operation.state == "running":
                operation.state = "finished"
            self._finished.notify_all()

    def commit_operation(
        self, operation: SessionOperation, change: CommitChange
    ) -> OperationResult:
        """Publish messages/resources/accounting in one transaction, or change nothing."""
        session = operation.session
        with self._lock, session.lock:
            if not self._valid(operation):
                self._cancel(operation)
                return OperationResult(cancelled=True)
            if operation.kind == "initialize" and session.history:
                operation.state = "committed"
                return OperationResult()
            # Copy only retained state; never deepcopy a lock or an active worker.
            proposed = copy.copy(session)
            for name in STATE_FIELDS:
                setattr(proposed, name, copy.deepcopy(getattr(session, name)))
            group_id = (
                secrets.token_urlsafe(12) if change.new_context else operation.snapshot.group_id
            )
            proposed.groups.setdefault(group_id, ConversationGroup())
            if change.profile is not None:
                proposed.profile = copy.deepcopy(change.profile)
            if change.routing is not None:
                proposed.routing = copy.deepcopy(change.routing)
            if change.new_context:
                proposed.context_revision += 1
                proposed.current_group_id = group_id
            if change.message_receipt:
                request_id, fingerprint = change.message_receipt
                proposed.message_receipts[request_id] = (proposed.context_revision, fingerprint)
                while len(proposed.message_receipts) > 32:
                    del proposed.message_receipts[next(iter(proposed.message_receipts))]
            if change.selected_categories is not None:
                proposed.selected_categories = set(change.selected_categories)
            if change.search_signals is not None:
                proposed.search_signals = change.search_signals
            messages = copy.deepcopy(change.messages)
            for message in messages:
                message["groupId"] = group_id
                message["language"] = operation.snapshot.language
            if change.replace_search_id:
                index = next(
                    (
                        i
                        for i, m in enumerate(proposed.history)
                        if m.get("kind") == "generate"
                        and m.get("searchId") == change.replace_search_id
                    ),
                    None,
                )
                if index is not None:
                    proposed.history[index : index + 1] = messages
                else:
                    proposed.history.extend(messages)
                proposed.searches.pop(change.replace_search_id, None)
                # Fragments are a view of the evidence; discard them when the search is consumed.
                proposed.history = [
                    m
                    for m in proposed.history
                    if not (
                        m.get("kind") == "fragments"
                        and m.get("searchId") == change.replace_search_id
                    )
                ]
            else:
                proposed.history.extend(messages)
            if change.search:
                sid, search = change.search
                proposed.searches[sid] = copy.deepcopy(search)
                proposed.groups[group_id].search_ids.append(sid)
            if change.report:
                job = proposed.generations.get(operation.operation_id)
                if job:
                    job.state = "succeeded"
                    job.stage = "publishing"
                    job.finished_at = time.time()
                    job.report_id = change.report[0]
                    job.partial = change.partial
                    job.validation_warnings = change.validation_warnings
                if operation.kind == "generate" and operation.search_id:
                    # A successful retry clears only the hidden generation error,
                    # while preserving the search, fragments and report controls.
                    proposed.history = [
                        message
                        for message in proposed.history
                        if message.get("generationSearchId") != operation.search_id
                    ]
                rid, report = change.report
                proposed.reports[rid] = copy.deepcopy(report)
                proposed.report_id, proposed.report_bytes = rid, report.data
                proposed.groups[group_id].report_ids.append(rid)
            pinned = {group_id}
            for op in self._workers.values():
                if (
                    op is not operation
                    and op.session is session
                    and op.state == "running"
                    and not op.cancellation.is_set()
                ):
                    pinned.add(op.snapshot.group_id)
            evicted_groups, evicted_searches, evicted_reports = [], [], []
            other_reserved = self._session_reserved(session, operation)
            usage = retained_usage(proposed)
            previous = session.retained_bytes

            def fits_session():
                return (
                    usage.history <= self.limits.max_history_bytes
                    and usage.evidence <= self.limits.max_evidence_bytes
                    and usage.pdf <= self.limits.max_pdf_bytes
                    and usage.total + other_reserved <= self.limits.max_session_bytes
                    and len(proposed.searches) <= MAX_KEPT_SEARCHES
                    and len(proposed.reports) <= MAX_KEPT_REPORTS
                )

            def fits_global():
                return (
                    self._used_bytes
                    - previous
                    + usage.total
                    + self._reserved_bytes
                    - operation.reserved_bytes
                    <= self.limits.max_global_bytes
                )

            def fits():
                return fits_session() and fits_global()

            for gid, group in list(proposed.groups.items()):
                if fits():
                    break
                if gid in pinned:
                    continue
                proposed.history = [m for m in proposed.history if m.get("groupId") != gid]
                for sid in group.search_ids:
                    proposed.searches.pop(sid, None)
                for rid in group.report_ids:
                    proposed.reports.pop(rid, None)
                del proposed.groups[gid]
                evicted_groups.append(gid)
                evicted_searches.extend(group.search_ids)
                evicted_reports.extend(group.report_ids)
                if proposed.report_id not in proposed.reports:
                    proposed.report_id = next(reversed(proposed.reports), None)
                    proposed.report_bytes = (
                        proposed.reports[proposed.report_id].data if proposed.report_id else None
                    )
                usage = retained_usage(proposed)
            if not fits_session():
                raise ApplicationError("SESSION_BUDGET", tr("errors.result_budget_exceeded"))
            global_total = (
                self._used_bytes
                - previous
                + usage.total
                + self._reserved_bytes
                - operation.reserved_bytes
            )
            if global_total > self.limits.max_global_bytes:
                raise ApplicationError("GLOBAL_BUDGET", tr("errors.application_capacity"), 503)
            for name in STATE_FIELDS:
                setattr(session, name, getattr(proposed, name))
            self._used_bytes += usage.total - previous
            session.retained_bytes = usage.total
            self._reserved_bytes -= operation.reserved_bytes
            operation.reserved_bytes = 0
            operation.state = "committed"
            if change.report and operation.operation_id in session.generations:
                logger.info("report_job_succeeded job_id=%s", operation.operation_id)
            if change.new_context:
                for op in self._workers.values():
                    if (
                        op.session is session
                        and op is not operation
                        and op.kind in {"classify", "condition", "search", "email"}
                    ):
                        self._cancel(op)
            if change.replace_search_id:
                evicted_searches.append(change.replace_search_id)
            return OperationResult(
                copy.deepcopy(messages),
                evicted_searches,
                evicted_reports,
                evicted_groups,
            )

    def set_language(self, session: SessionData, language: Language) -> None:
        with self._lock, session.lock:
            if session.language == language:
                return
            if any(op.session is session for op in self._workers.values()):
                raise ApplicationError(
                    "OPERATION_IN_PROGRESS", tr("errors.operation_capacity"), 409
                )
            session.language = language
            session.profile.language = language

    def history(self, session: SessionData) -> list[dict]:
        return self.conversation_view(session)["history"]

    # Read only the small catalog reference, never duplicate retained evidence or chat text.
    def herb_evidence_reference(self, session: SessionData, group_id: str) -> HerbEvidenceReference:
        with self._lock, session.lock:
            if (
                session.closed
                or self._sessions.get((session.cookie_id, session.tab_id)) is not session
                or self._expired(session)
            ):
                raise ApplicationError("SESSION_CLOSED", tr("errors.session_closed"))
            for message in session.history:
                if message.get("groupId") != group_id or message.get("kind") != "herb_conditions":
                    continue
                if not message.get("herbId") or not message.get("positiveRunId"):
                    break
                reference: HerbEvidenceReference = {
                    "herbId": message["herbId"],
                    "positiveRunId": message["positiveRunId"],
                    "language": message.get("language", "ro"),
                    "conditionIds": [condition["id"] for condition in message["conditions"]],
                }
                if message.get("cautionRunId"):
                    reference["cautionRunId"] = message["cautionRunId"]
                    reference["contraindicationConditionIds"] = [
                        condition["id"] for condition in message.get("contraindications", [])
                    ]
                return reference
            raise ApplicationError(
                "HERB_EVIDENCE_UNAVAILABLE", tr("errors.herb_evidence_unavailable"), 404
            )

    def herb_safety_reference(self, session: SessionData, group_id: str) -> HerbSafetyReference:
        with self._lock, session.lock:
            if (
                session.closed
                or self._sessions.get((session.cookie_id, session.tab_id)) is not session
                or self._expired(session)
            ):
                raise ApplicationError("SESSION_CLOSED", tr("errors.session_closed"))
            for message in session.history:
                if message.get("groupId") != group_id or message.get("kind") != "herb_conditions":
                    continue
                if message.get("warningsStatus") == "stale":
                    raise ApplicationError("HERB_SAFETY_STALE", tr("errors.herb_safety_stale"), 409)
                if message.get("herbId") and message.get("safetyRunId"):
                    return {
                        "herbId": message["herbId"],
                        "safetyRunId": message["safetyRunId"],
                        "language": message.get("language", "ro"),
                    }
                raise ApplicationError(
                    "HERB_SAFETY_NOT_READY", tr("errors.herb_safety_not_ready"), 503
                )
            raise ApplicationError(
                "HERB_SAFETY_UNAVAILABLE", tr("errors.herb_safety_unavailable"), 404
            )

    def conversation_view(
        self, session: SessionData, *, page_id: str | None = None
    ) -> dict[str, Any]:
        """Read messages and the email-eligible report from the same session state."""
        with self._lock, session.lock:
            key = session.cookie_id, session.tab_id
            if session.closed or self._sessions.get(key) is not session:
                raise ApplicationError("SESSION_CLOSED", tr("errors.session_closed"))
            if self._expired(session):
                self._delete_locked(key)
                raise ApplicationError("SESSION_CLOSED", tr("errors.session_closed"))
            if page_id is not None:
                session.active_page_id = page_id
                session.detached_until = None
            return {
                "history": copy.deepcopy(session.history),
                "latestReportId": session.report_id,
                "generations": [
                    {
                        **copy.deepcopy(job.as_dict(self.clock())),
                        "workerActive": job.job_id in self._workers,
                    }
                    for job in session.generations.values()
                ],
            }

    def report(self, session: SessionData, report_id: str):
        with self._lock, session.lock:
            if (
                session.closed
                or self._sessions.get((session.cookie_id, session.tab_id)) is not session
                or self._expired(session)
            ):
                return None
            return copy.deepcopy(session.reports.get(report_id))

    def delete(self, cookie_id: str, tab_id: str) -> None:
        with self._lock:
            self._delete_locked((cookie_id, tab_id))

    def close_page(self, cookie_id: str, tab_id: str, page_id: str | None) -> None:
        """Ignore an old document's delayed unload after its replacement has connected."""
        with self._lock:
            key = cookie_id, tab_id
            session = self._sessions.get(key)
            if session is None:
                return
            with session.lock:
                if session.active_page_id == page_id:
                    if session.generations:
                        session.detached_until = (
                            self.clock() + self.limits.session_reconnect_grace_seconds
                        )
                    else:
                        self._delete_locked(key)

    def _delete_locked(self, key: tuple[str, str]) -> None:
        session = self._sessions.get(key)
        if session is None:
            return
        with session.lock:
            self._used_bytes -= session.retained_bytes
            session.retained_bytes = 0
            session.closed = True
            for op in self._workers.values():
                if op.session is session:
                    self._cancel(op)
            self._sessions.pop(key)
            session.profile = HealthProfile()
            session.routing = MessageRouting()
            session.message_receipts.clear()
            session.generations.clear()
            session.generation_receipts.clear()
            session.detached_until = None
            session.history.clear()
            session.searches.clear()
            session.clear_report()
            session.selected_categories.clear()
            session.search_signals = ALL_SIGNALS
            session.groups.clear()
            if self._owned_directory(session.directory):
                shutil.rmtree(session.directory)
            logger.info(
                "session_closed active_sessions=%s retained_bytes=%s",
                len(self._sessions),
                self._used_bytes,
            )

    def _sweep_locked(self) -> None:
        for key, session in list(self._sessions.items()):
            if self._expired(session):
                self._delete_locked(key)
        for op in self._workers.values():
            if self.clock() >= op.deadline:
                self._cancel(op)
            else:
                job = op.session.generations.get(op.operation_id)
                if (
                    job
                    and job.state in {"accepted", "running"}
                    and self.clock() - job.progress_logged_at >= 30
                ):
                    job.progress_logged_at = self.clock()
                    logger.info(
                        "report_job_progress job_id=%s stage=%s remaining_seconds=%.0f",
                        job.job_id,
                        job.stage,
                        op.deadline - self.clock(),
                    )
        self.creation_limiter.sweep()

    def sweep(self) -> None:
        with self._lock:
            self._sweep_locked()

    def shutdown(self) -> None:
        with self._lock:
            self._accepting = False
            for key in list(self._sessions):
                self._delete_locked(key)

    def wait_workers(self, timeout: float | None = None) -> bool:
        with self._finished:
            return self._finished.wait_for(lambda: not self._workers, timeout=timeout)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def metrics(self) -> dict[str, int]:
        with self._lock:
            return {
                "active_sessions": len(self._sessions),
                "retained_bytes": self._used_bytes,
                "reserved_bytes": self._reserved_bytes,
                "active_workers": len(self._workers),
            }
