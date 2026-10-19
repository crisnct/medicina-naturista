"""Whole-fragment batches and lossless exact deduplication for one report worker."""

from __future__ import annotations

from typing import Final

from backend.ai.report_validation import SECTIONS, Recommendation, ValidatedReport
from backend.core.contracts import Evidence

REPORT_GENERATION_WORKERS: Final = 1


# Oversized fragments keep their original text and citation in a request of their own.
def partition_evidence(evidence: Evidence, max_chars: int) -> list[Evidence]:
    if type(max_chars) is not int or max_chars <= 0:
        raise ValueError("Batch character limit must be a positive integer")
    batches: list[Evidence] = []
    current: Evidence = {}
    characters = 0
    for token in sorted(
        evidence, key=lambda key: evidence[key].get("score", float("-inf")), reverse=True
    ):
        item = evidence[token]
        size = len(item["text"])
        if current and characters + size > max_chars:
            batches.append(current)
            current, characters = {}, 0
        current[token] = item
        characters += size
        if size > max_chars:
            batches.append(current)
            current, characters = {}, 0
    if current:
        batches.append(current)
    return batches


# Text equality is deliberate: differing doses and warnings must never be merged away.
def combine_reports(reports: list[ValidatedReport]) -> ValidatedReport:
    result = ValidatedReport(
        sections={key: [] for key in SECTIONS}, partial=False, validationWarnings=[]
    )
    for section in SECTIONS:
        by_text: dict[str, Recommendation] = {}
        food_lists: dict[str, dict[str, None]] = {}
        for report in reports:
            for item in report.sections[section]:
                key = item.text
                text = item.text
                if section == "nutritie" and item.text.startswith(
                    ("[RECOMANDAT]: ", "[NERECOMANDAT]: ", "[INTERZIS]: ")
                ):
                    prefix, foods = item.text.split(": ", 1)
                    values = food_lists.setdefault(prefix, {})
                    values.update(
                        dict.fromkeys(food.strip() for food in foods.split(",") if food.strip())
                    )
                    key = prefix
                    text = f"{prefix}: {', '.join(values)}"
                previous = by_text.get(key)
                if previous is None:
                    by_text[key] = Recommendation(text=text, evidence_ids=list(item.evidence_ids))
                else:
                    previous.text = text
                    previous.evidence_ids = list(
                        dict.fromkeys([*previous.evidence_ids, *item.evidence_ids])
                    )
        result.sections[section] = list(by_text.values())
    return result
