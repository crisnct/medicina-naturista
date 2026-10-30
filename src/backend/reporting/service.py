"""Prepare database-derived PDF scores before entering the pure renderer."""

from __future__ import annotations

from typing import Any

from backend.ai.herb_repository import load_herb_benefit_scores
from backend.ai.herbs import load_herbs
from backend.ai.report_validation import ValidatedReport
from backend.core.language import current_language, language_scope, validate_language
from backend.reporting.pdf import create_pdf
from backend.reporting.recommendations import (
    HERB_SECTIONS,
    recommendation_labels,
    split_recommendation,
)


def product_fragments(
    payload: dict[str, list[dict[str, Any]]],
    evidence: dict[str, dict[str, Any]],
) -> dict[str, frozenset[str]]:
    """Map each catalogue product label to the cited fragments whose text names that product.

    A label the herb catalogue does not recognise has no entry, so its relevance is not
    restricted; a recognised one whose cited fragments never name it gets an empty set.
    """
    cited: dict[str, set[str]] = {}
    for key in HERB_SECTIONS:
        for item in payload.get(key, []):
            if label := split_recommendation(item["text"])[0]:
                cited.setdefault(label, set()).update(
                    token for token in item.get("evidence_ids", []) if token in evidence
                )
    if not cited:
        return {}
    catalog = load_herbs()
    named: dict[str, frozenset[int]] = {}

    def herbs_named_in(token: str) -> frozenset[int]:
        if token not in named:
            named[token] = frozenset(herb.id for herb in catalog.mentions(evidence[token]["text"]))
        return named[token]

    result: dict[str, frozenset[str]] = {}
    for label, tokens in cited.items():
        wanted = {herb.id for herb in catalog.mentions(label)}
        if wanted:
            result[label] = frozenset(token for token in tokens if wanted & herbs_named_in(token))
    return result


def create_ranked_pdf(
    profile: dict[str, Any],
    sections: ValidatedReport | dict[str, list[dict[str, Any]]],
    evidence: dict[str, dict[str, Any]],
    min_score: float = 0,
    *,
    ai_model: str | None = None,
) -> bytes:
    with language_scope(validate_language(profile.get("language", current_language()))):
        payload = sections.section_payload() if isinstance(sections, ValidatedReport) else sections
        scores = load_herb_benefit_scores(recommendation_labels(payload))
        return create_pdf(
            profile,
            sections,
            evidence,
            min_score,
            ai_model=ai_model,
            herb_scores=scores,
            product_fragments=product_fragments(payload, evidence),
        )
