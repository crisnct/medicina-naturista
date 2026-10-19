"""Pure label extraction and PDF-only ordering of recommendation copies."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

HERB_SECTIONS = frozenset({"uz_intern", "uz_extern", "alte_recomandari", "atentionari"})
BENEFIT_COUNT = "_herb_benefit_count"


def split_recommendation(text: str) -> tuple[str, str]:
    """Share the display label with matching; never use an undelimited description."""
    clean = " ".join(str(text or "").split())
    match = re.match(
        r"^(?P<label>.+?)(?P<separator>:\s*|\s+[–—-]\s+)(?P<description>.+)$",
        clean,
    )
    if match:
        return match.group("label").strip(), match.group("description").strip()
    # Compatibility with older reports without an explicit name separator.
    match = re.match(
        r"^(?P<label>.{2,160}?)(?P<separator>"
        r"\s+(?=pentru\b|pulbere\b|administrat\b|preparat\b|"
        r"se\s+(?:ține|bea|ia|consumă|prepară)\b|"
        r"(?:½|¼|\d+(?:[.,]\d+)?)\s*(?:linguri?țe?|linguri?|ml|g|capsule?|picături?)\b))",
        clean,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group("label").strip(), clean[match.end("label") :].strip()
    return "", clean


def recommendation_labels(sections: dict[str, list[dict[str, Any]]]) -> list[str]:
    return list(
        dict.fromkeys(
            label
            for key, items in sections.items()
            if key in HERB_SECTIONS
            for item in items
            if (label := split_recommendation(item["text"])[0])
        )
    )


def rank_pdf_recommendations(
    sections: dict[str, list[dict[str, Any]]],
    herb_scores: Mapping[str, int],
) -> dict[str, list[dict[str, Any]]]:
    """Stable score sort after relevance ordering; leave input and nutrition intact."""
    ordered = {}
    for key, items in sections.items():
        if key not in HERB_SECTIONS:
            ordered[key] = items
            continue
        scored = [
            {**item, BENEFIT_COUNT: herb_scores.get(split_recommendation(item["text"])[0], 0)}
            for item in items
        ]
        ordered[key] = sorted(scored, key=lambda item: -item[BENEFIT_COUNT])
    return ordered
