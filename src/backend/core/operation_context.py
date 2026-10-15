"""Propagate a worker's deadline to synchronous I/O without changing public ports.

Capacity stays owned by SessionStore until the worker actually exits. This
context only bounds I/O and rejects late results; it cannot kill Python threads.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

from backend.core.errors import OperationCancelled

ReportActivityKind = Literal[
    "request_started", "provider_activity", "thinking", "answering", "response_finished"
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

    def remaining(self) -> float:
        self.checkpoint()
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise OperationCancelled()
        return remaining


_budget: ContextVar[OperationBudget | None] = ContextVar("operation_budget", default=None)


@contextmanager
def operation_budget(value: OperationBudget) -> Iterator[None]:
    token = _budget.set(value)
    try:
        value.remaining()
        yield
        value.remaining()
    finally:
        _budget.reset(token)


def remaining_timeout(timeout: float) -> float:
    value = _budget.get()
    return min(timeout, value.remaining()) if value else timeout


def checkpoint() -> None:
    value = _budget.get()
    if value:
        value.remaining()


def emit_report_output(text: str) -> None:
    """Publish answer deltas independently of thinking text."""
    if not text:
        return
    emit_report_activity(ReportActivity("answering"))
    value = _budget.get()
    if value and value.report_output:
        value.report_output(text)


def emit_report_thinking(text: str) -> None:
    if not text:
        return
    emit_report_activity(ReportActivity("thinking"))
    value = _budget.get()
    if value and value.report_thinking:
        value.report_thinking(text)


def emit_report_activity(event: ReportActivity) -> None:
    value = _budget.get()
    if value and value.report_activity:
        value.report_activity(event)
