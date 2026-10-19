"""Prepare database-derived PDF scores before entering the pure renderer."""

from __future__ import annotations

from typing import Any

from backend.ai.herb_repository import load_herb_benefit_scores
from backend.ai.report_validation import ValidatedReport
from backend.reporting.pdf import create_pdf
from backend.reporting.recommendations import recommendation_labels


def create_ranked_pdf(
    profile: dict[str, Any],
    sections: ValidatedReport | dict[str, list[dict[str, Any]]],
    evidence: dict[str, dict[str, Any]],
    min_score: float = 0,
    *,
    ai_model: str | None = None,
) -> bytes:
    payload = sections.section_payload() if isinstance(sections, ValidatedReport) else sections
    scores = load_herb_benefit_scores(recommendation_labels(payload))
    return create_pdf(profile, sections, evidence, min_score, ai_model=ai_model, herb_scores=scores)
