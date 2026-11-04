"""Propagate a worker's deadline to synchronous I/O without changing public ports.

Capacity stays owned by SessionStore until the worker actually exits. This
context only bounds I/O and rejects late results; it cannot kill Python threads.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from backend.core.contracts import ReportBatchCallback
from backend.core.errors import OperationCancelled
from backend.core.language import Language, current_language, language_scope
from backend.core.report_metrics import ReportBatchUsage
from backend.core.report_models import ReportEffort

if TYPE_CHECKING:
    from backend.ai.report_validation import ValidatedReport

ReportActivityKind = Literal[
    "request_started",
    "provider_activity",
    "thinking",
    "answering",
    "response_finished",
    "batch_failed",
    "batch_cancelled",
]


@dataclass(frozen=True)
class ReportActivity:
    kind: ReportActivityKind
    metrics: dict[str, int | float] | None = None


@dataclass(frozen=True)
class OperationBudget:
    deadline: float
    clock: Callable[[], float]
    checkpoint: Callable[[], None]
    report_output: Callable[[str], None] | None = None
    report_thinking: Callable[[str], None] | None = None
    report_activity: Callable[[ReportActivity], None] | None = None
    report_batch: ReportBatchCallback | None = None
    language: Language | None = None

    def remaining(self) -> float:
        self.checkpoint()
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise OperationCancelled()
        return remaining


_budget: ContextVar[OperationBudget | None] = ContextVar("operation_budget", default=None)
_batch_index: ContextVar[int | None] = ContextVar("report_batch_index", default=None)
_batch_stopped: ContextVar[Callable[[], bool] | None] = ContextVar(
    "report_batch_stopped", default=None
)


class ReportUsage:
    """The tokens of every request of a report; batches report from several threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._max_output_tokens = 0
        self._batches: list[ReportBatchUsage] = []

    def add(self, output_tokens: int, reasoning_tokens: int | None, truncated: bool) -> None:
        reasoning = None if reasoning_tokens is None else min(reasoning_tokens, output_tokens)
        with self._lock:
            self._max_output_tokens = max(self._max_output_tokens, output_tokens)
            self._batches.append(
                ReportBatchUsage(reasoning, output_tokens - (reasoning or 0), truncated)
            )

    @property
    def max_output_tokens(self) -> int | None:
        return self._max_output_tokens or None

    @property
    def batches(self) -> tuple[ReportBatchUsage, ...]:
        with self._lock:
            return tuple(self._batches)


_report_usage: ContextVar[ReportUsage | None] = ContextVar("report_usage", default=None)


@contextmanager
def report_usage_scope(usage: ReportUsage) -> Iterator[None]:
    token = _report_usage.set(usage)
    try:
        yield
    finally:
        _report_usage.reset(token)


# Requests outside a report (classifiers, condition lookup) have no scope and record nothing.
def record_report_output_tokens(
    output_tokens: int, reasoning_tokens: int | None = None, truncated: bool = False
) -> None:
    usage = _report_usage.get()
    if usage is not None:
        usage.add(output_tokens, reasoning_tokens, truncated)


_report_effort: ContextVar[ReportEffort | None] = ContextVar("report_effort", default=None)
_report_batch_max_tokens: ContextVar[int | None] = ContextVar(
    "report_batch_max_tokens", default=None
)
_report_batch_workers: ContextVar[int | None] = ContextVar("report_batch_workers", default=None)
_report_max_output_tokens: ContextVar[int | None] = ContextVar(
    "report_max_output_tokens", default=None
)
_report_thinking_override: ContextVar[int | None] = ContextVar(
    "report_thinking_override", default=None
)


def report_batch_index() -> int | None:
    return _batch_index.get()


# The effort belongs to one report request; the shared AI client never stores it.
def current_report_effort() -> ReportEffort | None:
    return _report_effort.get()


@contextmanager
def report_effort_scope(effort: ReportEffort | None) -> Iterator[None]:
    token = _report_effort.set(effort)
    try:
        yield
    finally:
        _report_effort.reset(token)


# The thinking budget learned from earlier batches of this model and effort; None keeps the
# model's configured budget ("thinking" in REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL).
_report_thinking_tokens: ContextVar[int | None] = ContextVar("report_thinking_tokens", default=None)


def current_report_thinking_tokens() -> int | None:
    return _report_thinking_tokens.get()


@contextmanager
def report_thinking_scope(tokens: int | None) -> Iterator[None]:
    token = _report_thinking_tokens.set(tokens)
    try:
        yield
    finally:
        _report_thinking_tokens.reset(token)


# The admin's per-report overrides; None keeps the value configured for the model.
def current_report_batch_max_tokens() -> int | None:
    return _report_batch_max_tokens.get()


def current_report_batch_workers() -> int | None:
    return _report_batch_workers.get()


def current_report_max_output_tokens() -> int | None:
    return _report_max_output_tokens.get()


# The thinking budget typed in the report panel; it wins over the learned and configured ones.
def current_report_thinking_override() -> int | None:
    return _report_thinking_override.get()


@contextmanager
def report_batch_scope(
    max_tokens: int | None,
    workers: int | None,
    max_output_tokens: int | None,
    thinking_tokens: int | None = None,
) -> Iterator[None]:
    tokens = (
        _report_batch_max_tokens.set(max_tokens),
        _report_batch_workers.set(workers),
        _report_max_output_tokens.set(max_output_tokens),
        _report_thinking_override.set(thinking_tokens),
    )
    try:
        yield
    finally:
        _report_thinking_override.reset(tokens[3])
        _report_max_output_tokens.reset(tokens[2])
        _report_batch_workers.reset(tokens[1])
        _report_batch_max_tokens.reset(tokens[0])


# Each submitted worker owns a fresh context; sibling failure cannot escape its request budget.
@contextmanager
def report_batch_context(index: int, stopped: Callable[[], bool]) -> Iterator[None]:
    index_token = _batch_index.set(index)
    stop_token = _batch_stopped.set(stopped)
    try:
        checkpoint()
        yield
    finally:
        _batch_stopped.reset(stop_token)
        _batch_index.reset(index_token)


@contextmanager
def operation_budget(value: OperationBudget) -> Iterator[None]:
    token = _budget.set(value)
    try:
        with language_scope(value.language or current_language()):
            value.remaining()
            yield
            value.remaining()
    finally:
        _budget.reset(token)


def remaining_timeout(timeout: float) -> float:
    checkpoint()
    value = _budget.get()
    return min(timeout, value.remaining()) if value else timeout


def checkpoint() -> None:
    stopped = _batch_stopped.get()
    if stopped and stopped():
        raise OperationCancelled()
    value = _budget.get()
    if value:
        value.remaining()


def emit_report_output(text: str) -> None:
    """Publish answer deltas independently of thinking text."""
    if not text:
        return
    checkpoint()
    emit_report_activity(ReportActivity("answering"))
    value = _budget.get()
    if value and value.report_output:
        value.report_output(text)


def emit_report_thinking(text: str) -> None:
    if not text:
        return
    checkpoint()
    emit_report_activity(ReportActivity("thinking"))
    value = _budget.get()
    if value and value.report_thinking:
        value.report_thinking(text)


def emit_report_activity(event: ReportActivity) -> None:
    value = _budget.get()
    if value and value.report_activity:
        value.report_activity(event)


# Publish only the current validated batch; final combination remains with the report client.
def emit_report_batch(completed: int, total: int, report: ValidatedReport | None = None) -> None:
    checkpoint()
    value = _budget.get()
    if value and value.report_batch:
        value.report_batch(completed, total, report)
