"""Validated measurements for one published report, independent of storage."""

from __future__ import annotations

from dataclasses import dataclass

from backend.core.errors import ApplicationError
from backend.core.texts import tr

MAX_BIGINT = (1 << 63) - 1


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


# Reports with a measured batch output needed before the panel trusts them, and the margin
# added to the largest one.
MIN_OUTPUT_SAMPLES = 3
OUTPUT_RECOMMENDATION_MARGIN_PERCENT = 125


@dataclass(frozen=True)
class ReportOutputRecommendation:
    # None until enough reports were measured for the model and effort.
    tokens: int | None
    sample_count: int


def recommend_output_tokens(sample_count: int, largest_output: int) -> ReportOutputRecommendation:
    """The output limit per batch that every measured report would have fitted, with a margin."""
    if sample_count < MIN_OUTPUT_SAMPLES or largest_output <= 0:
        return ReportOutputRecommendation(None, sample_count)
    margin = OUTPUT_RECOMMENDATION_MARGIN_PERCENT
    return ReportOutputRecommendation((largest_output * margin + 99) // 100, sample_count)


def validate_min_score(value: int) -> None:
    if type(value) is not int or not 0 <= value <= 100:
        raise ApplicationError("INVALID_MIN_SCORE", tr("errors.minimum_score_invalid"), 422)


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
