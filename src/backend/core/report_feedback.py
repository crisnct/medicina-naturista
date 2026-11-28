"""The admin's rating of a published report and the example it may keep, independent of storage.

An example holds only the report's validated recommendations, its catalog conditions, language and
model: never the consultation profile, the question or the PDF. Citations become content hashes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.core.contracts import Evidence
from backend.core.language import Language
from backend.core.report_metrics import SHA256_HEX

MAX_FEEDBACK_SCORE = 10
MAX_FEEDBACK_COMMENT_CHARS = 4000
# A report rated at least this high may be saved as an example.
EXAMPLE_MIN_SCORE = 8

ReportSections = dict[str, list[dict[str, Any]]]


@dataclass(frozen=True)
class ReportFeedbackContext:
    """What a report's rating and example need, kept with its PDF while the chat shows it."""

    language: Language
    # Code of the signals the report's search was scored with.
    signals: str
    min_score: int
    ai_model: str
    condition_keys: tuple[str, ...]
    sections: ReportSections
    # The report_generation_metrics row; None until the measurements are stored, and for good
    # when storing them failed (the report then cannot be rated).
    report_id: int | None = None


@dataclass(frozen=True)
class ReportFeedback:
    report_id: int
    language: Language
    score: int
    comment: str
    search_formula: str
    rrf_k: int
    signals: str
    min_score: int

    def __post_init__(self) -> None:
        if type(self.report_id) is not int or self.report_id <= 0:
            raise ValueError("Feedback needs a positive report id")
        if self.language not in ("ro", "en"):
            raise ValueError("Feedback language must be ro or en")
        if type(self.score) is not int or not 0 <= self.score <= MAX_FEEDBACK_SCORE:
            raise ValueError("Feedback score must be an integer from 0 to 10")
        if not isinstance(self.comment, str) or len(self.comment) > MAX_FEEDBACK_COMMENT_CHARS:
            raise ValueError("Feedback comment must be text of at most 4000 characters")
        for label in (self.search_formula, self.signals):
            if not isinstance(label, str) or not label.strip():
                raise ValueError("Feedback search formula and signals must be nonempty")
        if type(self.rrf_k) is not int or self.rrf_k <= 0:
            raise ValueError("Feedback RRF constant must be a positive integer")
        if type(self.min_score) is not int or not 0 <= self.min_score <= 100:
            raise ValueError("Feedback minimum score must be from 0 to 100")


@dataclass(frozen=True)
class ReportExample:
    report_id: int
    language: Language
    condition_keys: tuple[str, ...]
    sections: ReportSections
    ai_model: str

    def __post_init__(self) -> None:
        if type(self.report_id) is not int or self.report_id <= 0:
            raise ValueError("An example needs a positive report id")
        if self.language not in ("ro", "en"):
            raise ValueError("Example language must be ro or en")
        if not isinstance(self.ai_model, str) or not self.ai_model.strip():
            raise ValueError("Example model must be nonempty")
        for section in self.sections.values():
            for item in section:
                if not all(SHA256_HEX.match(value) for value in item.get("evidence_ids", [])):
                    raise ValueError("Example citations must be content hashes")


def condition_keys(names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"condition:{name}" for name in names)


# Evidence ids are valid only inside one report's batch; the fragment's text hash keeps the
# example tied to its sources across reindexing. A citation without a hash is dropped.
def example_sections(sections: ReportSections, evidence: Evidence) -> ReportSections:
    result: ReportSections = {}
    for section, items in sections.items():
        result[section] = []
        for item in items:
            cited = (evidence.get(token) for token in item["evidence_ids"])
            hashes = (source.get("text_sha256") for source in cited if source is not None)
            result[section].append(
                {**item, "evidence_ids": list(dict.fromkeys(h for h in hashes if h))}
            )
    return result


# The rating and, when the admin keeps it and the score allows, the example. Without an example
# any earlier one of the same report is deleted.
def build_report_feedback(
    context: ReportFeedbackContext,
    score: int,
    comment: str,
    save_example: bool,
    *,
    search_formula: str,
    rrf_k: int,
) -> tuple[ReportFeedback, ReportExample | None]:
    assert context.report_id is not None
    feedback = ReportFeedback(
        report_id=context.report_id,
        language=context.language,
        score=score,
        comment=comment,
        search_formula=search_formula,
        rrf_k=rrf_k,
        signals=context.signals,
        min_score=context.min_score,
    )
    example = (
        ReportExample(
            report_id=context.report_id,
            language=context.language,
            condition_keys=context.condition_keys,
            sections=context.sections,
            ai_model=context.ai_model,
        )
        if save_example and score >= EXAMPLE_MIN_SCORE
        else None
    )
    return feedback, example
