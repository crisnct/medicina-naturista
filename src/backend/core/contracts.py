"""Shared data and port contracts; independent of HTTP and the UI."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Literal, NotRequired, Protocol, TypedDict

from backend.core.herb_categories import HerbCategory
from backend.core.report_models import ReportModel as ReportModel

if TYPE_CHECKING:
    from backend.ai.categories import CategoryTree
    from backend.ai.condition_ai import AIConditionResult
    from backend.ai.conditions import ResolvedQuery
    from backend.ai.message_classification import MessageClassification
    from backend.ai.report_validation import ValidatedReport
    from backend.core.models import SessionSnapshot
    from backend.core.report_metrics import ReportDurationEstimate, ReportMetrics


class TranscriptEntry(TypedDict):
    role: str
    content: str


class IdentifiedCondition(TypedDict):
    index: int
    name: str
    terms: list[str]


class ProfilePayload(TypedDict):
    health_problem: str
    health_context: list[str]
    transcript: list[TranscriptEntry]
    ai_conditions: list[IdentifiedCondition]


class EvidenceItem(TypedDict):
    source: str
    text: str
    score: NotRequired[float]
    relevance_percent: NotRequired[float | None]
    lexical_score: NotRequired[float | None]
    semantic_score: NotRequired[float | None]
    semantic_similarity: NotRequired[float | None]
    condition_in_title: NotRequired[bool | None]
    condition_in_text: NotRequired[bool | None]
    business_category: NotRequired[str | None]
    primary_medical_conditions: NotRequired[list[str]]
    secondary_medical_conditions: NotRequired[list[str]]
    found_by_lexical: NotRequired[bool]


Evidence = dict[str, EvidenceItem]


class AIProtocol(Protocol):
    def context_budget(self) -> int | None: ...
    def generate(self, profile: ProfilePayload, evidence: Evidence) -> ValidatedReport: ...
    def is_configured(self) -> bool: ...
    def close(self) -> None: ...


class RetrievalProtocol(Protocol):
    @property
    def document_count(self) -> int: ...
    @property
    def category_tree(self) -> CategoryTree | None: ...
    def collect(self, session: SessionSnapshot, max_chars: int | None = None) -> Evidence: ...


class EmailProtocol(Protocol):
    def __call__(self, problem: str, pdf_bytes: bytes, filename: str, to_address: str) -> str: ...


IdentifyCondition = Callable[["ResolvedQuery"], "AIConditionResult"]
RenderPDF = Callable[[ProfilePayload, "ValidatedReport", Evidence, float], bytes]
ClassifyMessage = Callable[[str, dict[str, object]], "MessageClassification"]
RecordReportMetrics = Callable[["ReportMetrics"], int]
EstimateReportDuration = Callable[[ReportModel, int], "ReportDurationEstimate"]
ReportBatchCallback = Callable[[int, int, "ValidatedReport | None"], None]


class HerbCondition(TypedDict):
    id: int
    name: str


class HerbLookupResult(TypedDict):
    status: Literal["found", "not_found", "ambiguous"]
    choices: NotRequired[list[str]]
    herbName: NotRequired[str]
    species: NotRequired[list[str]]
    entriesCount: NotRequired[int]
    conditions: NotRequired[list[HerbCondition]]
    herbId: NotRequired[int]
    positiveRunId: NotRequired[str]
    fragmentsCount: NotRequired[int]
    documentsCount: NotRequired[int]


LookupHerb = Callable[[str], HerbLookupResult]


class HerbEvidenceReference(TypedDict):
    herbId: int
    positiveRunId: str
    conditionIds: list[int]


# Offsets are half-open Unicode code-point positions in the unchanged source field.
class HerbHighlight(TypedDict):
    start: int
    end: int
    kind: Literal["herb", "condition"]


class HerbEvidenceFragment(TypedDict):
    chunkId: int
    document: str
    lineStart: int
    lineEnd: int
    heading: str
    text: str
    conditions: list[HerbCondition]
    headingHighlights: list[HerbHighlight]
    textHighlights: list[HerbHighlight]


class HerbEvidencePage(TypedDict):
    herbId: int
    positiveRunId: str
    fragmentsCount: int
    documentsCount: int
    fragments: list[HerbEvidenceFragment]
    nextOffset: int | None


class LookupHerbEvidence(Protocol):
    def __call__(
        self, herb_id: int, run_id: str, *, condition_id: int | None = None, offset: int = 0
    ) -> HerbEvidencePage: ...


class RankedHerb(TypedDict):
    ro: str
    latin: str
    ro_regional: list[str]
    ranking: int


ListTopHerbs = Callable[[int, HerbCategory | None], list[RankedHerb]]


class ConditionTopResult(TypedDict):
    status: Literal["found", "not_found", "ambiguous"]
    choices: NotRequired[list[str]]
    condition: NotRequired[HerbCondition]
    positiveRunId: NotRequired[str]
    herbs: NotRequired[list[RankedHerb]]


ListTopHerbsForCondition = Callable[[int, HerbCategory | None, str], ConditionTopResult]
