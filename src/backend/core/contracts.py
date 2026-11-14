"""Shared data and port contracts; independent of HTTP and the UI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, NotRequired, Protocol, TypedDict

from backend.core.herb_categories import HerbCategory
from backend.core.language import Language
from backend.core.report_models import ReportEffort as ReportEffort
from backend.core.report_models import ReportModel as ReportModel

if TYPE_CHECKING:
    from backend.ai.categories import CategoryTree
    from backend.ai.condition_ai import AIConditionResult
    from backend.ai.conditions import ResolvedQuery
    from backend.ai.message_classification import MessageClassification
    from backend.ai.report_validation import ValidatedReport
    from backend.core.models import SessionSnapshot
    from backend.core.report_metrics import (
        ReportBatchUsage,
        ReportDurationEstimate,
        ReportMetrics,
        ReportOutputRecommendation,
    )


class TranscriptEntry(TypedDict):
    role: str
    content: str


class IdentifiedCondition(TypedDict):
    index: int
    name: str
    terms: list[str]


class ProfilePayload(TypedDict):
    language: NotRequired[Language]
    health_problem: str
    health_context: list[str]
    transcript: list[TranscriptEntry]
    ai_conditions: list[IdentifiedCondition]


class FragmentHighlight(TypedDict):
    start: int  # Unicode code points of the displayed text
    end: int
    kind: Literal["searched", "lexical"]


class EvidenceItem(TypedDict):
    language: NotRequired[Language]
    source: str
    text: str
    score: NotRequired[float]
    relevance_percent: NotRequired[float | None]
    lexical_bm25: NotRequired[float | None]
    semantic_rank: NotRequired[int | None]
    semantic_similarity: NotRequired[float | None]
    condition_in_title: NotRequired[bool | None]
    condition_in_text: NotRequired[bool | None]
    business_category: NotRequired[str | None]
    primary_medical_conditions: NotRequired[list[str]]
    secondary_medical_conditions: NotRequired[list[str]]
    found_by_lexical: NotRequired[bool]
    # Where the question's conditions ("searched") and words ("lexical") are in the displayed text.
    highlights: NotRequired[list[FragmentHighlight]]


Evidence = dict[str, EvidenceItem]


# No tokenizer is shared by all providers, so tokens are estimated from UTF-8 bytes.
# Three bytes per token fits Romanian text and JSON framing without being wasteful.
BYTES_PER_TOKEN = 3


def estimate_tokens(size_bytes: int) -> int:
    return -(-size_bytes // BYTES_PER_TOKEN)


@dataclass(frozen=True)
class EvidenceTokenBudget:
    """An estimated token budget (see estimate_tokens), distinct from legacy character budgets."""

    max_tokens: int


@dataclass(frozen=True)
class ReportBatchPlan:
    """How a report would be split: batches, lone fragments over the limit, and that limit."""

    batches: int
    oversized: int
    input_tokens: int


class AIProtocol(Protocol):
    def generate(
        self,
        profile: ProfilePayload,
        evidence: Evidence,
        effort: ReportEffort | None = None,
        batch_max_tokens: int | None = None,
        batch_workers: int | None = None,
        max_output_tokens: int | None = None,
        thinking_tokens: int | None = None,
    ) -> ValidatedReport: ...
    def plan_report_batches(
        self,
        profile: ProfilePayload,
        evidence: Evidence,
        effort: ReportEffort | None = None,
        batch_max_tokens: int | None = None,
        max_output_tokens: int | None = None,
        batch_workers: int | None = None,
        thinking_tokens: int | None = None,
    ) -> ReportBatchPlan: ...
    def is_configured(self) -> bool: ...
    def close(self) -> None: ...


# What a report job shows while the GPU changes hands, before it starts its own timer.
ModelStage = Literal["stopping_model", "warming_model"]


class ReportModelRuntime(Protocol):
    def prepare(
        self,
        model: ReportModel,
        on_stage: Callable[[ModelStage], None],
        checkpoint: Callable[[], None],
    ) -> None: ...

    def close(self) -> None: ...


class EstimateReportDuration(Protocol):
    def __call__(
        self, model: ReportModel, characters: int, effort: ReportEffort | None = None
    ) -> ReportDurationEstimate: ...


class RecommendReportOutput(Protocol):
    def __call__(
        self, model: ReportModel, effort: ReportEffort | None = None
    ) -> ReportOutputRecommendation: ...


class RetrievalProtocol(Protocol):
    @property
    def document_count(self) -> int: ...
    @property
    def category_tree(self) -> CategoryTree | None: ...
    def collect(
        self, session: SessionSnapshot, max_chars: int | EvidenceTokenBudget | None = None
    ) -> Evidence: ...


class EmailProtocol(Protocol):
    def __call__(self, problem: str, pdf_bytes: bytes, filename: str, to_address: str) -> str: ...


IdentifyCondition = Callable[["ResolvedQuery"], "AIConditionResult"]
RenderPDF = Callable[[ProfilePayload, "ValidatedReport", Evidence, float], bytes]
ClassifyMessage = Callable[[str, dict[str, object]], "MessageClassification"]
RecordReportMetrics = Callable[["ReportMetrics"], int]
RecordReportBatchUsage = Callable[
    [ReportModel, "ReportEffort | None", "tuple[ReportBatchUsage, ...]"], None
]
ReportBatchCallback = Callable[[int, int, "ValidatedReport | None"], None]


class HerbCondition(TypedDict):
    id: int
    name: str


HerbEvidenceKind = Literal["positive", "contraindication"]
HerbCautionStatus = Literal["ready", "partial", "not_ready", "stale"]


class HerbContraindication(HerbCondition):
    hasRecommendation: bool


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
    cautionRunId: NotRequired[str | None]
    contraindicationsStatus: NotRequired[HerbCautionStatus]
    contraindicationsCount: NotRequired[int | None]
    contraindications: NotRequired[list[HerbContraindication]]
    contraindicationFragmentsCount: NotRequired[int]
    contraindicationDocumentsCount: NotRequired[int]
    safetyRunId: NotRequired[str | None]
    warningsStatus: NotRequired[HerbCautionStatus]
    warningsCount: NotRequired[int | None]
    warningFragmentsCount: NotRequired[int]
    warningDocumentsCount: NotRequired[int]
    warningCandidateFragmentsCount: NotRequired[int]


LookupHerb = Callable[[str], HerbLookupResult]
LookupHerbImage = Callable[[int], Path | None]


class HerbEvidenceReference(TypedDict):
    language: NotRequired[Language]
    herbId: int
    positiveRunId: str
    conditionIds: list[int]
    cautionRunId: NotRequired[str]
    contraindicationConditionIds: NotRequired[list[int]]


# Offsets are half-open Unicode code-point positions in the unchanged source field.
class HerbHighlight(TypedDict):
    start: int
    end: int
    kind: Literal["herb", "condition", "warning"]


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
    evidenceKind: NotRequired[HerbEvidenceKind]
    cautionRunId: NotRequired[str]


class LookupHerbEvidence(Protocol):
    def __call__(
        self,
        herb_id: int,
        run_id: str,
        *,
        condition_id: int | None = None,
        offset: int = 0,
        evidence_kind: HerbEvidenceKind = "positive",
        caution_run_id: str | None = None,
    ) -> HerbEvidencePage: ...


class HerbSafetyReference(TypedDict):
    language: NotRequired[Language]
    herbId: int
    safetyRunId: str


class HerbWarning(TypedDict):
    id: str
    text: str
    kind: str
    partners: list[str]
    sourcesCount: int


class HerbSafetyPage(TypedDict):
    herbId: int
    safetyRunId: str
    warningsStatus: HerbCautionStatus
    warningsCount: int
    warnings: list[HerbWarning]
    nextOffset: int | None


class HerbSafetyEvidencePage(TypedDict):
    herbId: int
    safetyRunId: str
    warningId: str
    fragmentsCount: int
    documentsCount: int
    fragments: list[HerbEvidenceFragment]
    nextOffset: int | None


class LookupHerbSafety(Protocol):
    def __call__(self, herb_id: int, run_id: str, *, offset: int = 0) -> HerbSafetyPage: ...


class LookupHerbSafetyEvidence(Protocol):
    def __call__(
        self, herb_id: int, run_id: str, *, warning_id: str, offset: int = 0
    ) -> HerbSafetyEvidencePage: ...


class RankedHerb(TypedDict):
    ro: str
    latin: str
    ro_regional: list[str]
    ranking: int
    # Only per-condition tops: L1 and L2 for the requested condition.
    title_fragments: NotRequired[int]
    text_fragments: NotRequired[int]


ListTopHerbs = Callable[[int, HerbCategory | None], list[RankedHerb]]


class ConditionTopResult(TypedDict):
    status: Literal["found", "not_found", "ambiguous"]
    choices: NotRequired[list[str]]
    condition: NotRequired[HerbCondition]
    positiveRunId: NotRequired[str]
    herbs: NotRequired[list[RankedHerb]]


ListTopHerbsForCondition = Callable[[int, HerbCategory | None, str], ConditionTopResult]
