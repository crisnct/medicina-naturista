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
from dataclasses import asdict, dataclass
from pathlib import Path

from backend.ai.search import ALL_SIGNALS
from backend.config import Settings
from backend.core.errors import ApplicationError, OperationCancelled
from backend.core.models import (
    MAX_KEPT_REPORTS,
    MAX_KEPT_SEARCHES,
    CommitChange,
    ConversationGroup,
    HealthProfile,
    OperationResult,
    SessionData,
    SessionOperation,
    SessionSnapshot,
)
from backend.core.rate_limits import RateLimiter

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
            {k: v for k, v in m.items() if k != "fragments"}
            if m.get("kind") == "fragments"
            else m
            for m in session.history
        ]
    )
    searches = {sid: asdict(search) for sid, search in session.searches.items()}
    evidence = serialized_bytes(searches)
    pdf = sum(len(report.data) for report in session.reports.values())
    metadata = serialized_bytes(
        {
            "profile": asdict(session.profile),
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
    return RetainedUsage(history, evidence, pdf, history + evidence + pdf + metadata)


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
                        "SHUTTING_DOWN", "Aplicația se închide.", 503
                    )
                # Reclaim expired entries before applying allocation limits.
                self._sweep_locked()
                if len(self._sessions) >= self.limits.max_active_sessions:
                    raise ApplicationError(
                        "GLOBAL_SESSION_LIMIT",
                        "Capacitatea aplicației este ocupată.",
                        503,
                    )
                cookie_full = (
                    sum(s.cookie_id == cookie_id for s in self._sessions.values())
                    >= self.limits.max_sessions_per_cookie
                )
                ip_full = (
                    sum(s.client_ip == client_ip for s in self._sessions.values())
                    >= self.limits.max_sessions_per_ip
                )
                if (cookie_full and self.limits.max_sessions_per_cookie == 1) or (
                    ip_full and self.limits.max_sessions_per_ip == 1
                ):
                    raise ApplicationError(
                        "SESSION_ALREADY_ACTIVE",
                        "Chatul este deja deschis într-un alt tab sau browser. "
                        "Este permisă o singură sesiune per adresă IP. "
                        "Folosiți pagina deschisă sau închideți-o și încercați din nou aici.",
                        429,
                    )
                if cookie_full or ip_full:
                    raise ApplicationError(
                        "CLIENT_SESSION_LIMIT",
                        "Limita de sesiuni active a fost atinsă.",
                        429,
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
                    raise ApplicationError(
                        "SESSION_BUDGET", "Bugetul sesiunii este insuficient."
                    )
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
        if (
            self._used_bytes + self._reserved_bytes + additional
            > self.limits.max_global_bytes
        ):
            raise ApplicationError(
                "GLOBAL_BUDGET", "Capacitatea aplicației este ocupată.", 503
            )

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
        if operation.kind in {"message", "condition", "search", "initialize"}:
            return operation.snapshot.context_revision == s.context_revision
        if operation.kind == "generate":
            search = s.searches.get(operation.search_id or "")
            return (
                search is not None
                and operation.snapshot.search is not None
                and search.identity == operation.snapshot.search.identity
            )
        if operation.kind == "email":
            return operation.snapshot.report_id in s.reports
        return True

    def begin_operation(
        self,
        session: SessionData,
        kind: str,
        *,
        search_id: str | None = None,
        expected_revision: int | None = None,
    ) -> SessionOperation:
        """Reserve lifetime/resource/capacity atomically, before external calls."""
        with self._lock, session.lock:
            if (
                not self._accepting
                or session.closed
                or self._sessions.get((session.cookie_id, session.tab_id))
                is not session
            ):
                raise ApplicationError("SESSION_CLOSED", "Sesiunea a fost închisă.")
            if self._expired(session):
                self._delete_locked((session.cookie_id, session.tab_id))
                raise ApplicationError(
                    "SESSION_EXPIRED", "Sesiunea a expirat. Reîncărcați pagina."
                )
            if (
                expected_revision is not None
                and expected_revision != session.context_revision
            ):
                raise OperationCancelled()
            search = session.searches.get(search_id or "")
            if kind == "generate" and search is None:
                raise ApplicationError(
                    "SEARCH_UNAVAILABLE",
                    "Nu există fragmente pregătite. Descrieți din nou problema de sănătate.",
                )
            active = [
                op
                for op in self._workers.values()
                if op.state == "running" and not op.cancellation.is_set()
            ]
            if kind == "generate" and any(
                op.session is session and op.kind == kind and op.search_id == search_id
                for op in active
            ):
                raise ApplicationError(
                    "GENERATION_IN_PROGRESS",
                    "Această căutare este deja în curs de generare.",
                )
            # Count workers until finally, even when cancelled; network threads may still run.
            if kind in {"search", "condition", "generate"}:
                category = "generate" if kind == "generate" else "search"
                cap = (
                    self.limits.max_concurrent_generations
                    if category == "generate"
                    else self.limits.max_concurrent_searches
                )
                count = sum(
                    ("generate" if op.kind == "generate" else "search") == category
                    for op in self._workers.values()
                    if op.kind in {"search", "condition", "generate"}
                )
                if count >= cap:
                    raise ApplicationError(
                        "OPERATION_LIMIT",
                        "Prea multe operații în curs. Încercați mai târziu.",
                        429,
                    )
            group_id = session.current_group_id
            if kind == "generate":
                group_id = next(
                    gid
                    for gid, g in session.groups.items()
                    if search_id in g.search_ids
                )
            latest = session.reports.get(session.report_id or "")
            if kind == "email" and latest:
                group_id = next(
                    gid
                    for gid, g in session.groups.items()
                    if session.report_id in g.report_ids
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
                session.report_id if kind == "email" else None,
            )
            reservation = self.limits.operation_reservation_bytes
            reservation += serialized_bytes(
                {
                    "profile": asdict(snapshot.profile),
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
                retained_usage(session).total
                + self._session_reserved(session)
                + reservation
                > self.limits.max_session_bytes
            ):
                raise ApplicationError(
                    "SESSION_BUDGET", "Bugetul sesiunii este insuficient."
                )
            self._check_global(reservation)
            op = SessionOperation(
                secrets.token_urlsafe(18),
                kind,
                session,
                snapshot,
                self.clock() + self.limits.operation_timeout_seconds,
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

    def checkpoint(self, operation: SessionOperation) -> None:
        with self._lock, operation.session.lock:
            if not self._valid(operation):
                self._cancel(operation)
                raise OperationCancelled()

    def _cancel(self, operation: SessionOperation) -> None:
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
                secrets.token_urlsafe(12)
                if change.new_context
                else operation.snapshot.group_id
            )
            proposed.groups.setdefault(group_id, ConversationGroup())
            if change.profile is not None:
                proposed.profile = copy.deepcopy(change.profile)
            if change.new_context:
                proposed.context_revision += 1
                proposed.current_group_id = group_id
            if change.selected_categories is not None:
                proposed.selected_categories = set(change.selected_categories)
            if change.search_signals is not None:
                proposed.search_signals = change.search_signals
            messages = copy.deepcopy(change.messages)
            for message in messages:
                message["groupId"] = group_id
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
                proposed.history = [
                    m for m in proposed.history if m.get("groupId") != gid
                ]
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
                        proposed.reports[proposed.report_id].data
                        if proposed.report_id
                        else None
                    )
                usage = retained_usage(proposed)
            if not fits_session():
                raise ApplicationError(
                    "SESSION_BUDGET", "Rezultatul depășește bugetul sesiunii."
                )
            global_total = (
                self._used_bytes
                - previous
                + usage.total
                + self._reserved_bytes
                - operation.reserved_bytes
            )
            if global_total > self.limits.max_global_bytes:
                raise ApplicationError(
                    "GLOBAL_BUDGET", "Capacitatea aplicației este ocupată.", 503
                )
            for name in STATE_FIELDS:
                setattr(session, name, getattr(proposed, name))
            self._used_bytes += usage.total - previous
            session.retained_bytes = usage.total
            self._reserved_bytes -= operation.reserved_bytes
            operation.reserved_bytes = 0
            operation.state = "committed"
            if change.new_context:
                for op in self._workers.values():
                    if (
                        op.session is session
                        and op is not operation
                        and op.kind in {"condition", "search"}
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

    def history(self, session: SessionData) -> list[dict]:
        with self._lock, session.lock:
            key = session.cookie_id, session.tab_id
            if session.closed or self._sessions.get(key) is not session:
                raise ApplicationError("SESSION_CLOSED", "Sesiunea a fost închisă.")
            if self._expired(session):
                self._delete_locked(key)
                raise ApplicationError("SESSION_CLOSED", "Sesiunea a fost închisă.")
            return copy.deepcopy(session.history)

    def report(self, session: SessionData, report_id: str):
        with self._lock, session.lock:
            if (
                session.closed
                or self._sessions.get((session.cookie_id, session.tab_id))
                is not session
                or self._expired(session)
            ):
                return None
            return copy.deepcopy(session.reports.get(report_id))

    def delete(self, cookie_id: str, tab_id: str) -> None:
        with self._lock:
            self._delete_locked((cookie_id, tab_id))

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
        self.creation_limiter.sweep()

    def sweep(self) -> None:
        with self._lock:
            self._sweep_locked()

    def shutdown(self) -> None:
        with self._lock:
            self._accepting = False
            for key in list(self._sessions):
                self._delete_locked(key)

    def wait_workers(self) -> None:
        with self._finished:
            self._finished.wait_for(lambda: not self._workers)

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
