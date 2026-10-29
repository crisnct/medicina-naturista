"""Minimal medical context collected before report generation."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from backend.ai.search import ALL_SIGNALS, SearchSignals
from backend.core.contracts import Evidence, IdentifiedCondition, ProfilePayload, TranscriptEntry
from backend.core.herb_categories import HerbCategory, TopClarification
from backend.core.texts import tr


def health_problem_question() -> str:
    return tr("conversation.health_problem_question")


@dataclass
class HealthProfile:
    health_problem: str = ""
    health_context: list[str] = field(default_factory=list)
    transcript: list[TranscriptEntry] = field(default_factory=list)
    asked_field: str | None = None
    # Conditions the AI identified for health_problem when the dictionary knew
    # none (ai/condition_ai.py): {"index", "name", "terms"} per message segment.
    # Cleared with every new message, so it never outlives the text it came from.
    ai_conditions: tuple[IdentifiedCondition, ...] = ()

    # Store a normalized conversation entry when its role and content are allowed.
    def add_transcript(self, role: str, content: str) -> None:
        clean = " ".join((content or "").split())[:4000]
        if role in {"assistant", "user"} and clean:
            self.transcript.append({"role": role, "content": clean})

    # Add a unique normalized user detail to the profile context.
    def add_health_context(self, message: str) -> None:
        clean = " ".join((message or "").split())[:4000]
        if clean and clean.casefold() not in {value.casefold() for value in self.health_context}:
            self.health_context.append(clean)

    # Set the primary health problem and add it to the searchable context.
    def set_health_problem(self, message: str) -> None:
        clean = " ".join((message or "").split())[:4000]
        if clean:
            self.health_problem = clean
            self.ai_conditions = ()
            self.add_health_context(clean)
            self.asked_field = None

    # Start a distinct report context and discard medical details from the
    # previously generated report while leaving the visual chat history intact.
    def replace_health_problem(self, message: str) -> None:
        clean = " ".join((message or "").split())[:4000]
        if not clean:
            return
        self.health_problem = clean
        self.ai_conditions = ()
        self.health_context = [clean]
        self.transcript = [{"role": "user", "content": clean}]
        self.asked_field = None

    @property
    # Indicate whether the profile contains enough information to generate a report.
    def report_ready(self) -> bool:
        return bool(self.health_problem)

    # Return the next required profile question, if the health problem is missing.
    def next_question(self) -> str | None:
        if not self.health_problem:
            self.asked_field = "health_problem"
            return health_problem_question()
        self.asked_field = None
        return None

    # Serialize the profile into the structure consumed by retrieval and AI generation.
    def as_dict(self) -> ProfilePayload:
        return {
            "health_problem": self.health_problem,
            "health_context": list(self.health_context),
            "transcript": [
                TranscriptEntry(role=entry["role"], content=entry["content"])
                for entry in self.transcript
            ],
            "ai_conditions": [
                IdentifiedCondition(
                    index=entry["index"], name=entry["name"], terms=list(entry["terms"])
                )
                for entry in self.ai_conditions
            ],
        }


MAX_KEPT_SEARCHES = 12
MAX_KEPT_REPORTS = 12


@dataclass
class PendingSearch:
    """Retained evidence for reviewing and generating reports for one health problem."""

    profile: ProfilePayload
    evidence: Evidence
    # The signals the search was scored with (the patient may change them for
    # the next search, but these fragments keep the scores of this one).
    signals: SearchSignals = ALL_SIGNALS
    identity: str = field(default_factory=lambda: secrets.token_urlsafe(18))
    index_generation: str | None = None
    intent: str = "remedii"


@dataclass
class MessageRouting:
    """Bounded state for one message revision and an optional clarification."""

    message: str = ""
    intent: str = ""
    classified: bool = False
    start_search: bool = False
    identify_condition: bool = False
    clarification: str = ""
    herb_choices: tuple[str, ...] = ()
    top_herb_choices: tuple[str, ...] = ()
    top_count: int | None = None
    top_category: HerbCategory | None = None
    top_clarification: TopClarification | None = None
    top_condition: str | None = None
    top_condition_choices: tuple[str, ...] = ()
    top_condition_required: bool = False
    report_id: str | None = None
    email_attempted: bool = False


@dataclass
class StoredReport:
    """A generated PDF kept so its download link stays valid while the chat continues."""

    data: bytes
    filename: str
    health_problem: str


@dataclass
class AIStreamRate:
    """Provider-independent character estimate measured at chunk receipt."""

    characters_received: int = 0
    first_chunk_characters: int = 0
    first_chunk_at: float | None = None
    last_chunk_at: float | None = None

    def record(self, text: str, now: float) -> None:
        if not text:
            return
        if self.first_chunk_at is None:
            self.first_chunk_at = now
            self.first_chunk_characters = len(text)
        self.characters_received += len(text)
        self.last_chunk_at = now

    def tokens_per_second(self) -> float | None:
        if self.first_chunk_at is None or self.last_chunk_at is None:
            return None
        elapsed = self.last_chunk_at - self.first_chunk_at
        if elapsed < 1:
            return None
        # Exclude the initial chunk: its production interval is unknown.
        return round((self.characters_received - self.first_chunk_characters) / 4 / elapsed, 1)


@dataclass
class AIActivity:
    request_started_at: float
    phase: Literal["waiting", "processing", "thinking", "answering"] = "waiting"
    first_event_at: float | None = None
    first_thinking_at: float | None = None
    first_answer_at: float | None = None
    last_activity_at: float | None = None
    thinking_characters_received: int = 0

    def as_dict(self, now: float) -> dict[str, Any]:
        def elapsed(at: float | None) -> int | None:
            return None if at is None else max(0, round((at - self.request_started_at) * 1000))

        return {
            "phase": self.phase,
            "lastActivityAgeMs": None
            if self.last_activity_at is None
            else max(0, round((now - self.last_activity_at) * 1000)),
            "firstEventElapsedMs": elapsed(self.first_event_at),
            "firstThinkingElapsedMs": elapsed(self.first_thinking_at),
            "firstAnswerElapsedMs": elapsed(self.first_answer_at),
            "thinkingCharactersReceived": self.thinking_characters_received,
        }


@dataclass
class ReportBatchPreview:
    """One batch owns its diagnostic chunks, activity and validated snapshot."""

    index: int
    started: bool = False
    completed: bool = False
    report_preview: str | None = None
    failed: bool = False
    cancelled: bool = False
    stream_parts: list[str] = field(default_factory=list, repr=False)
    thinking_parts: list[str] = field(default_factory=list, repr=False)
    ai_activity: AIActivity | None = None

    # Raw chunks are charged once by the job; activity owns a fixed metadata slot.
    def metadata(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "started": self.started,
            "completed": self.completed,
            "failed": self.failed,
            "cancelled": self.cancelled,
            "report_preview": self.report_preview,
        }

    def as_dict(self, job: ReportGeneration, now: float) -> dict[str, Any]:
        state = "validated" if self.completed else "pending"
        if self.started and not self.completed:
            if self.failed:
                state = "failed"
            elif self.cancelled:
                state = "timed_out" if job.state == "timed_out" else "cancelled"
            else:
                state = (
                    job.state if job.state in {"failed", "cancelled", "timed_out"} else "running"
                )
        return {
            "index": self.index,
            "state": state,
            "reportPreview": self.report_preview,
            "streamPreview": "".join(self.stream_parts) or None,
            "thinkingPreview": ("".join(self.thinking_parts) or None)
            if job.state != "succeeded"
            else None,
            "aiActivity": self.ai_activity.as_dict(now) if self.ai_activity else None,
        }


@dataclass
class ReportGeneration:
    """Bounded, session-owned job metadata; never stores credentials or PDF copies."""

    job_id: str
    search_id: str
    request_id: str
    min_score: int
    model_choice: str
    provider: str
    model: str
    created_at: float
    deadline_at: float
    state: str = "accepted"
    stage: str = "queued"
    started_at: float | None = None
    finished_at: float | None = None
    progress_logged_at: float = 0
    report_id: str | None = None
    partial: bool = False
    validation_warnings: list[dict[str, Any]] = field(default_factory=list)
    error_code: str | None = None
    message: str | None = None

    stream_parts: list[str] = field(default_factory=list, repr=False)
    stream_bytes: int = 0
    thinking_parts: list[str] = field(default_factory=list, repr=False)
    thinking_bytes: int = 0
    stream_rate: AIStreamRate = field(default_factory=AIStreamRate)
    thinking_rate: AIStreamRate = field(default_factory=AIStreamRate)
    ai_activity: AIActivity | None = None
    report_preview: str | None = None
    report_preview_bytes: int = 0
    preview_version: int = 0
    batches_completed: int = 0
    batches_total: int = 0
    batch_previews: list[ReportBatchPreview] = field(default_factory=list, repr=False)
    batch_previews_bytes: int = 0

    @property
    def stream_preview(self) -> str | None:
        if self.batch_previews:
            return (
                "\n\n".join(
                    f"--- Lot {batch.index}/{self.batches_total} ---\n{''.join(batch.stream_parts)}"
                    for batch in self.batch_previews
                    if batch.stream_parts
                )
                or None
            )
        return "".join(self.stream_parts) or None

    @property
    def thinking_preview(self) -> str | None:
        if self.state == "succeeded":
            return None
        if self.batch_previews:
            return (
                "\n\n".join(
                    f"--- Lot {batch.index}/{self.batches_total} ---\n{''.join(batch.thinking_parts)}"
                    for batch in self.batch_previews
                    if batch.thinking_parts
                )
                or None
            )
        return "".join(self.thinking_parts) or None

    def as_dict(self, now: float | None = None) -> dict[str, Any]:
        return {
            "jobId": self.job_id,
            "searchId": self.search_id,
            "state": self.state,
            "stage": self.stage,
            "provider": self.provider,
            "model": self.model,
            "modelChoice": self.model_choice,
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "deadlineAt": self.deadline_at,
            "reportId": self.report_id,
            "partial": self.partial,
            "validationWarnings": self.validation_warnings,
            "errorCode": self.error_code,
            "message": self.message,
            "pollAfterMs": 3000,
            "reportPreview": self.report_preview,
            "previewVersion": self.preview_version,
            "batchesCompleted": self.batches_completed,
            "batchesTotal": self.batches_total,
            "batchPreviews": [
                batch.as_dict(self, time.monotonic() if now is None else now)
                for batch in self.batch_previews
            ],
            "streamPreview": self.stream_preview,
            "streamTokensPerSecond": self.stream_rate.tokens_per_second(),
            "thinkingTokensPerSecond": self.thinking_rate.tokens_per_second(),
            "thinkingPreview": self.thinking_preview,
            "aiActivity": self.ai_activity.as_dict(time.monotonic() if now is None else now)
            if self.ai_activity
            else None,
        }


@dataclass
class SessionData:
    """Ephemeral state isolated to one browser tab."""

    cookie_id: str
    tab_id: str
    directory: Path
    client_ip: str = "unknown"
    lifetime_id: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    active_page_id: str | None = None
    detached_until: float | None = None
    generations: dict[str, ReportGeneration] = field(default_factory=dict)
    generation_receipts: dict[str, str] = field(default_factory=dict)
    closed: bool = False
    context_revision: int = 0
    retained_bytes: int = 0
    current_group_id: str = "greeting"
    groups: dict[str, "ConversationGroup"] = field(default_factory=dict)
    created_at: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)
    profile: HealthProfile = field(default_factory=HealthProfile)
    # Each entry is a small JSON-serializable dict distinguished by "kind"
    # ("text", "fragments", "generate" or "download") — see web/handlers.py's
    # message builders. Never HTML: the frontend renders each kind itself.
    history: list[dict[str, Any]] = field(default_factory=list)
    report_bytes: bytes | None = None
    report_id: str | None = None
    # Evidence found by the retrieval-only stage, shown to the patient before
    # they choose to send it to the AI. Reused (not recomputed) by report
    # generation and retained afterwards for reviewing or generating another report.
    # One entry per search shown in the chat, keyed by the id carried by its
    # "Generează raportul" section, so several searches remain available at the same time.
    searches: dict[str, PendingSearch] = field(default_factory=dict)
    # Every generated PDF, keyed by report id; report_bytes/report_id above
    # always point at the latest one (used when the patient asks for it by email).
    reports: dict[str, StoredReport] = field(default_factory=dict)
    # Source-folder categories (see backend.ai.categories) the patient
    # chose in the "Filtrează sursele" panel before the last search. Empty means
    # zero sources; the frontend explicitly seeds its initial selection.
    selected_categories: set[str] = field(default_factory=set)
    # Signals of the score the patient chose ("Ce tip de căutare doriți să
    # efectuez?") before the last search; every signal is on by default.
    search_signals: SearchSignals = ALL_SIGNALS
    routing: MessageRouting = field(default_factory=MessageRouting)
    message_receipts: dict[str, tuple[int, str]] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)

    def touch(self) -> None:
        """Refresh the session's last-activity timestamp."""
        self.last_seen = time.monotonic()

    def clear_report(self) -> None:
        """Discard every generated report and download identifier."""
        self.report_bytes = None
        self.report_id = None
        self.reports.clear()

    def add_search(self, search_id: str, search: PendingSearch) -> None:
        """Remember a search's fragments, dropping the oldest beyond the cap."""
        self.searches[search_id] = search
        while len(self.searches) > MAX_KEPT_SEARCHES:
            self.searches.pop(next(iter(self.searches)))

    def add_report(self, report_id: str, report: StoredReport) -> None:
        """Store a generated PDF and make it the latest one."""
        self.reports[report_id] = report
        self.report_id = report_id
        self.report_bytes = report.data
        while len(self.reports) > MAX_KEPT_REPORTS:
            self.reports.pop(next(iter(self.reports)))


@dataclass
class ConversationGroup:
    search_ids: list[str] = field(default_factory=list)
    report_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SessionSnapshot:
    """Independent worker input. Nested data is copied while holding both locks."""

    lifetime_id: str
    context_revision: int
    group_id: str
    tab_id: str
    profile: HealthProfile
    selected_categories: set[str]
    search_signals: SearchSignals
    search: PendingSearch | None = None
    report: StoredReport | None = None
    report_id: str | None = None
    routing: MessageRouting = field(default_factory=MessageRouting)
    message_receipts: dict[str, tuple[int, str]] = field(default_factory=dict)


@dataclass
class SessionOperation:
    operation_id: str
    kind: str
    session: SessionData
    snapshot: SessionSnapshot
    deadline: float
    cancellation: threading.Event = field(default_factory=threading.Event)
    state: str = "running"
    reserved_bytes: int = 0
    search_id: str | None = None


@dataclass
class CommitChange:
    """A proposed update; nothing is changed until all budgets pass."""

    messages: list[dict[str, Any]] = field(default_factory=list)
    profile: HealthProfile | None = None
    new_context: bool = False
    selected_categories: set[str] | None = None
    search_signals: SearchSignals | None = None
    search: tuple[str, PendingSearch] | None = None
    report: tuple[str, StoredReport] | None = None
    replace_search_id: str | None = None
    routing: MessageRouting | None = None
    message_receipt: tuple[str, str] | None = None
    partial: bool = False
    validation_warnings: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class OperationResult:
    messages: list[dict[str, Any]] = field(default_factory=list)
    evicted_search_ids: list[str] = field(default_factory=list)
    evicted_report_ids: list[str] = field(default_factory=list)
    evicted_group_ids: list[str] = field(default_factory=list)
    cancelled: bool = False
    partial: bool = False
    validation_warnings: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "messages": self.messages,
            "evictedSearchIds": self.evicted_search_ids,
            "evictedReportIds": self.evicted_report_ids,
            "evictedGroupIds": self.evicted_group_ids,
            "cancelled": self.cancelled,
            "partial": self.partial,
            "validationWarnings": self.validation_warnings,
        }
