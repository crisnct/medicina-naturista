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
    # The model sometimes drops the separator and writes "Name (dose) ..."; the name is
    # then the text before a parenthesis that opens with a quantity.
    match = re.match(
        r"^(?P<label>[^():]{2,120}?)\s+(?=\((?:½|¼|\d|(?:o|un|una|două|doua|trei|patru|cinci|a|an|one|two|three)\s))",
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


def product_fragment_ids(
    item: dict[str, Any],
    product_fragments: Mapping[str, frozenset[str]] | None,
) -> frozenset[str] | None:
    """Evidence ids whose text names the item's product; None when it cannot be checked."""
    if not product_fragments:
        return None
    return product_fragments.get(split_recommendation(item["text"])[0])


def attach_herb_benefit_counts(
    sections: dict[str, list[dict[str, Any]]],
    herb_scores: Mapping[str, int],
) -> dict[str, list[dict[str, Any]]]:
    """Attach X for display to herb recommendations; item order is left unchanged."""
    return {
        key: [
            {**item, BENEFIT_COUNT: herb_scores.get(split_recommendation(item["text"])[0], 0)}
            for item in items
        ]
        if key in HERB_SECTIONS
        else items
        for key, items in sections.items()
    }
