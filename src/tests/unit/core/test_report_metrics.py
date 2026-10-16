"""Publication measurements use real session commits and a controlled clock."""

from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.ai.client import AIUnavailable
from backend.ai.conditions import ConditionDictionary, make_condition
from backend.config import Settings
from backend.core.conversation import ConversationService
from backend.core.errors import ApplicationError
from backend.core.models import CommitChange, HealthProfile, PendingSearch
from backend.core.report_generation import ReportGenerationService
from backend.core.report_metrics import ReportMetrics
from backend.core.sessions import SessionStore


@pytest.fixture
def generation(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.ai.conditions.load_dictionary",
        lambda: ConditionDictionary([make_condition("Gripă")]),
    )
    now = [100.0]
    config = Settings()
    store = SessionStore(tmp_path, 3600, 14400, config, clock=lambda: now[0])
    session = store.get("synthetic-cookie", "metrics-tab", create=True)
    profile = {
        "health_problem": "Gripă",
        "health_context": [],
        "transcript": [],
        "ai_conditions": [],
    }
    evidence = {
        "C1": {"text": "Șase 🌿", "source": "test.md:1-2", "relevance_percent": 80},
        "C2": {"text": "excluded", "source": "test.md:3-4", "relevance_percent": 20},
        "C3": {"text": "over budget", "source": "test.md:5-6", "relevance_percent": 70},
    }
    operation = store.begin_operation(session, "message")
    store.commit_operation(
        operation, CommitChange(profile=HealthProfile(health_problem="Gripă"), new_context=True)
    )
    store.finish_operation(operation)
    operation = store.begin_operation(session, "search")
    store.commit_operation(
        operation, CommitChange(search=("search", PendingSearch(profile, evidence)))
    )
    store.finish_operation(operation)
    sections = {
        "uz_intern": [{"text": "Recomandare", "evidence_ids": ["C1"]}],
        "nutritie": [],
        "uz_extern": [],
        "alte_recomandari": [],
        "atentionari": [],
    }

    def ai_generate(*args):
        now[0] += 1
        return sections

    def render(*args):
        now[0] += 2
        return b"synthetic PDF"

    ai = Mock()
    ai.context_budget.return_value = len(evidence["C1"]["text"])
    ai.generate.side_effect = ai_generate
    writer = Mock(return_value=7)
    service = ConversationService(
        config,
        store,
        Mock(),
        ai,
        Mock(),
        Mock(),
        Mock(side_effect=render),
        report_model="gemma4:12b",
        report_model_choice="ollama-gemma4:12b",
        report_ai_effort="medium",
        record_report_metrics=writer,
    )
    try:
        yield SimpleNamespace(
            service=service,
            store=store,
            session=session,
            now=now,
            writer=writer,
            sections=sections,
        )
    finally:
        store.shutdown()


def test_success_counts_sent_unicode_evidence_and_times_through_commit(generation, monkeypatch):
    h = generation
    original_commit = h.store.commit_operation

    def commit(*args):
        h.now[0] += 0.25
        return original_commit(*args)

    def persist(metrics):
        assert h.session.report_bytes == b"synthetic PDF"
        h.now[0] += 20  # Persistence itself must not increase the stored duration.
        return 7

    monkeypatch.setattr(h.store, "commit_operation", commit)
    h.writer.side_effect = persist
    h.session.profile.health_problem = "Changed after the search"
    result = h.service.generate(h.session, "search", 50)
    assert not result.cancelled
    h.writer.assert_called_once_with(
        ReportMetrics("Gripă", 50, len("Șase 🌿"), "ollama-gemma4:12b", "medium", 3250)
    )
    assert list(h.service.ai.generate.call_args.args[1]) == ["C1"]


def test_admitted_queue_time_is_excluded_and_unknown_effort_stays_none(generation):
    h = generation
    _, operation = h.store.admit_generation(
        h.session, "search", "request", 50, "ollama-gemma4:12b", "ollama", "gemma4:12b"
    )
    h.now[0] += 120
    h.service.report_ai_effort = None
    try:
        assert not h.service.generate(h.session, "search", 50, admitted=operation).cancelled
        metrics = h.writer.call_args.args[0]
        assert metrics.duration == 3000 and metrics.ai_effort is None
    finally:
        h.store.finish_operation(operation)


@pytest.mark.parametrize("stage", ["ai", "pdf", "cancel", "timeout", "commit", "rejected_commit"])
def test_unpublished_reports_never_write_metrics(generation, monkeypatch, stage):
    h = generation
    if stage == "ai":
        h.service.ai.generate.side_effect = AIUnavailable("synthetic failure")
    elif stage == "pdf":
        h.service.pdf.side_effect = RuntimeError("synthetic failure")
    elif stage == "cancel":
        h.service.pdf.side_effect = lambda *args: h.store.delete("synthetic-cookie", "metrics-tab")
    elif stage == "timeout":

        def delayed_response(*args):
            h.now[0] += h.service.settings.operation_timeout_seconds + 1
            return h.sections

        h.service.ai.generate.side_effect = delayed_response
    elif stage == "rejected_commit":
        original_commit = h.store.commit_operation

        def reject(operation, change):
            h.store.delete("synthetic-cookie", "metrics-tab")
            return original_commit(operation, change)

        monkeypatch.setattr(h.store, "commit_operation", reject)
    else:
        monkeypatch.setattr(
            h.store, "commit_operation", Mock(side_effect=ApplicationError("TEST", "test", 409))
        )
    if stage == "commit":
        with pytest.raises(ApplicationError):
            h.service.generate(h.session, "search", 50)
    else:
        h.service.generate(h.session, "search", 50)
    h.writer.assert_not_called()
    assert not h.session.reports


def test_empty_selection_does_not_write_metrics(generation):
    h = generation
    h.service.generate(h.session, "search", 100)
    h.writer.assert_not_called()
    h.service.ai.generate.assert_not_called()


def test_partial_report_is_measured_and_db_failure_preserves_success(generation, caplog):
    h = generation
    h.sections["uz_intern"].append({"text": "Invalid", "evidence_ids": ["missing"]})
    h.writer.side_effect = RuntimeError("PRIVATE DATA MUST NOT APPEAR IN LOGS")
    result = h.service.generate(h.session, "search", 50)
    assert result.partial and not result.cancelled
    assert h.session.report_bytes == b"synthetic PDF"
    h.writer.assert_called_once()
    assert "report_metrics_persistence_failed job_id=" in caplog.text
    assert "PRIVATE DATA" not in caplog.text
    h.service.ai.generate.assert_called_once()


@pytest.mark.parametrize("score", [50.5, 50.0, True, "50", -1, 101])
def test_invalid_scores_fail_before_ai_or_queue_admission(generation, score):
    h = generation
    with pytest.raises(ApplicationError, match="Scorul minim"):
        h.service.generate(h.session, "search", score)
    queue = ReportGenerationService(h.store)
    try:
        with pytest.raises(ApplicationError, match="Scorul minim"):
            queue.start(h.service, h.session, "search", score, "request", "ollama-gemma4:12b")
    finally:
        queue.close()
    h.writer.assert_not_called()
    h.service.ai.generate.assert_not_called()
    assert not h.session.generations


@pytest.mark.parametrize(
    "field,value",
    [
        ("characters", -1),
        ("duration", -1),
        ("duration", 1 << 63),
        ("characters", 1.5),
        ("medical_condition", " "),
        ("ai_model", ""),
        ("ai_effort", " "),
    ],
)
def test_metrics_reject_invalid_values(field, value):
    metrics = ReportMetrics("Gripa", 50, 53924, "grok-4.3", None, 40000)
    with pytest.raises(ValueError):
        replace(metrics, **{field: value})


def test_metrics_are_immutable():
    metrics = ReportMetrics("Gripa", 50, 53924, "grok-4.3", None, 40000)
    with pytest.raises(FrozenInstanceError):
        metrics.duration = 1
