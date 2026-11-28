"""Validated measurements for one published report, independent of storage."""

from __future__ import annotations

import math
import re
from collections.abc import Collection
from dataclasses import dataclass, replace

from backend.core.contracts import Evidence
from backend.core.errors import ApplicationError
from backend.core.texts import tr

MAX_BIGINT = (1 << 63) - 1
MAX_INTEGER = (1 << 31) - 1


@dataclass(frozen=True)
class ReportDurationEstimate:
    estimated_seconds: int | None
    sample_count: int


def estimate_duration_from_totals(
    characters: int,
    sample_count: int,
    character_duration_sum: int,
    squared_characters_sum: int,
) -> ReportDurationEstimate:
    """Fit duration = rate * characters using every observation for one model."""
    if type(characters) is not int or not 0 <= characters <= MAX_BIGINT:
        raise ValueError("Characters must be a nonnegative BIGINT")
    if characters == 0:
        return ReportDurationEstimate(0, sample_count)
    if sample_count == 0 or squared_characters_sum == 0:
        return ReportDurationEstimate(None, sample_count)
    numerator = characters * character_duration_sum
    denominator = squared_characters_sum * 1000  # Stored durations are milliseconds.
    return ReportDurationEstimate((numerator + denominator - 1) // denominator, sample_count)


# Budgets are learned from the most recent batch requests of one model and effort: their 95th
# percentile plus a margin. The percentile, not the largest value, keeps one reasoning loop from
# raising the budget for good; the rare larger request is left to the output-limit recovery.
MIN_BATCH_SAMPLES = 20
RECENT_BATCH_SAMPLES = 200
BUDGET_PERCENTILE = 0.95
BUDGET_MARGIN_PERCENT = 125


@dataclass(frozen=True)
class ReportOutputRecommendation:
    # None until enough batches were measured for the model and effort.
    tokens: int | None
    sample_count: int


def recommend_tokens(sample_count: int, percentile: float | None) -> ReportOutputRecommendation:
    """A per-batch budget from the percentile of the recent measured batches, with a margin."""
    if sample_count < MIN_BATCH_SAMPLES or percentile is None or percentile <= 0:
        return ReportOutputRecommendation(None, sample_count)
    tokens = (math.ceil(percentile) * BUDGET_MARGIN_PERCENT + 99) // 100
    return ReportOutputRecommendation(tokens, sample_count)


@dataclass(frozen=True)
class ReportBatchUsage:
    """The tokens one AI request of a report used; a truncated one is a lower bound."""

    reasoning_tokens: int | None
    answer_tokens: int
    truncated: bool

    def __post_init__(self) -> None:
        for value in (self.answer_tokens, self.reasoning_tokens):
            if value is not None and (type(value) is not int or not 0 <= value <= MAX_BIGINT):
                raise ValueError("Batch tokens must be nonnegative BIGINT values")
        if type(self.truncated) is not bool:
            raise ValueError("Batch truncation must be a boolean")


def validate_min_score(value: int) -> None:
    if type(value) is not int or not 0 <= value <= 100:
        raise ApplicationError("INVALID_MIN_SCORE", tr("errors.minimum_score_invalid"), 422)


# The citation log keeps this many of the search's best candidates, sent or not, so a new score
# formula can also be judged on fragments the current one left out. Sent fragments past them are
# logged too: every cited fragment must be in the log.
EVIDENCE_LOG_CANDIDATES = 200
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ReportEvidenceEntry:
    """One search candidate of a report: its score signals and what the report did with it."""

    text_sha256: str
    p1: int | None
    p2: int | None
    l_rank: int | None
    v_rank: int | None
    sent: bool
    cited: bool
    # The synthetic-question rank, empty until that signal exists.
    q_rank: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text_sha256, str) or not SHA256_HEX.match(self.text_sha256):
            raise ValueError("Evidence log entries need a lowercase hexadecimal SHA-256")
        for flag in (self.p1, self.p2):
            if flag is not None and flag not in (0, 1):
                raise ValueError("Condition signals must be 0, 1 or None")
        for rank in (self.l_rank, self.v_rank, self.q_rank):
            if rank is not None and (type(rank) is not int or not 0 < rank <= MAX_INTEGER):
                raise ValueError("Signal ranks must be positive INTEGER values or None")
        if type(self.sent) is not bool or type(self.cited) is not bool:
            raise ValueError("Evidence log flags must be booleans")
        if self.cited and not self.sent:
            raise ValueError("A cited fragment must have been sent")


def _condition_flag(value: object) -> int | None:
    return None if value is None else int(bool(value))


# The log of one report from its search's evidence (best score first), the evidence ids sent to
# the model and the ids its validated recommendations cite. A text shared by several fragments is
# one entry: the best-ranked one's signals, sent or cited if any of them was.
def report_evidence_log(
    evidence: Evidence, sent_ids: Collection[str], cited_ids: Collection[str]
) -> tuple[ReportEvidenceEntry, ...]:
    entries: dict[str, ReportEvidenceEntry] = {}
    ranked = sorted(evidence.items(), key=lambda pair: -float(pair[1].get("score") or 0.0))
    for position, (evidence_id, item) in enumerate(ranked):
        sent = evidence_id in sent_ids
        text_sha256 = item.get("text_sha256")
        if text_sha256 is None or (position >= EVIDENCE_LOG_CANDIDATES and not sent):
            continue
        cited = sent and evidence_id in cited_ids
        previous = entries.get(text_sha256)
        if previous is not None:
            entries[text_sha256] = replace(
                previous, sent=previous.sent or sent, cited=previous.cited or cited
            )
            continue
        entries[text_sha256] = ReportEvidenceEntry(
            text_sha256=text_sha256,
            p1=_condition_flag(item.get("condition_in_title")),
            p2=_condition_flag(item.get("condition_in_text")),
            l_rank=item.get("lexical_rank"),
            v_rank=item.get("semantic_rank"),
            sent=sent,
            cited=cited,
        )
    return tuple(entries.values())


@dataclass(frozen=True)
class ReportMetrics:
    medical_condition: str
    min_score: int
    characters: int
    ai_model: str
    ai_effort: str | None
    duration: int
    # The largest output of any request of the report; None when the provider reported none.
    max_batch_output_tokens: int | None = None
    # The citation log, written in the same transaction as the measurements.
    evidence: tuple[ReportEvidenceEntry, ...] = ()

    def __post_init__(self) -> None:
        validate_min_score(self.min_score)
        for value in (self.characters, self.duration):
            if type(value) is not int or not 0 <= value <= MAX_BIGINT:
                raise ValueError("Report measurements must be nonnegative BIGINT values")
        if self.max_batch_output_tokens is not None and (
            type(self.max_batch_output_tokens) is not int
            or not 0 <= self.max_batch_output_tokens <= MAX_BIGINT
        ):
            raise ValueError("Report output tokens must be a nonnegative BIGINT or None")
        for label in (self.medical_condition, self.ai_model):
            if not isinstance(label, str) or not label.strip():
                raise ValueError("Report condition and model must be nonempty strings")
        if self.ai_effort is not None and (
            not isinstance(self.ai_effort, str) or not self.ai_effort.strip()
        ):
            raise ValueError("Report effort must be a nonempty string or None")
