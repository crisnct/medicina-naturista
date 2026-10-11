"""Validate the report contract against the exact evidence snapshot."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

SECTIONS = ("uz_intern", "nutritie", "uz_extern", "alte_recomandari", "atentionari")
PARTIAL_NOTICE = "Raportul este parțial: unele recomandări nu au putut fi validate."
Section = Literal["uz_intern", "nutritie", "uz_extern", "alte_recomandari", "atentionari"]


class ReportValidationError(ValueError):
    pass


class Recommendation(BaseModel):
    model_config = ConfigDict(strict=True)
    text: str
    evidence_ids: list[str]


class ValidationWarning(BaseModel):
    code: str
    section: Section | None = None
    index: int | None = None
    count: int | None = None


class ValidatedReport(BaseModel):
    sections: dict[Section, list[Recommendation]]
    partial: bool
    validationWarnings: list[ValidationWarning]

    def section_payload(self) -> dict[str, list[dict[str, Any]]]:
        return {key: [item.model_dump() for item in items] for key, items in self.sections.items()}


NUTRITION_FIELDS = {
    "retete": "RETETA",
    "recomandate": "RECOMANDAT",
    "nerecomandate": "NERECOMANDAT",
    "interzise": "INTERZIS",
    "alte": "ALTE",
}


def normalize_nutrition(value: dict) -> list[tuple[Any, str]]:
    """Accepted scalar/list forms; retain malformed items for validation."""
    items = []
    for field, prefix in NUTRITION_FIELDS.items():
        raw = value.get(field, [])
        if raw is None:
            continue
        for item in raw if isinstance(raw, list) else [raw]:
            if isinstance(item, str):
                if not item.strip():
                    continue
                item = {"text": item, "evidence_ids": []}
            items.append((item, f"[{prefix}]: "))
    return items


def validate_report(value: Any, evidence: dict) -> ValidatedReport:
    if not isinstance(value, dict):
        raise ReportValidationError("REPORT_INVALID")
    sections = {key: [] for key in SECTIONS}
    warnings: list[ValidationWarning] = []

    def warn(code, section=None, index=None, count=None):
        warnings.append(ValidationWarning(code=code, section=section, index=index, count=count))

    if value.keys() - set(SECTIONS):
        warn("EXTRA_KEYS", count=len(value.keys() - set(SECTIONS)))
    for section in SECTIONS:
        if section not in value:
            warn("MISSING_SECTION", section)
            continue
        items = value[section]
        structured = section == "nutritie" and isinstance(items, dict)
        if structured:
            if items.keys() - NUTRITION_FIELDS.keys():
                warn("EXTRA_KEYS", section, count=len(items.keys() - NUTRITION_FIELDS.keys()))
            items = normalize_nutrition(items)
        elif isinstance(items, list):
            items = [(item, "") for item in items]
        else:
            warn("INVALID_SECTION", section)
            continue
        for index, (item, prefix) in enumerate(items):
            if not isinstance(item, dict):
                warn("INVALID_ITEM", section, index)
                continue
            if item.keys() - {"text", "evidence_ids"}:
                warn("EXTRA_KEYS", section, index)
            text, ids = item.get("text"), item.get("evidence_ids", [])
            if (
                not isinstance(text, str)
                or not text.strip(" -•\r\n\t")
                or not isinstance(ids, list)
                or any(type(token) is not str for token in ids)
            ):
                warn("INVALID_ITEM", section, index)
                continue
            if any(token not in evidence for token in ids):
                warn("UNKNOWN_EVIDENCE", section, index)
                continue
            if not ids and section != "nutritie":
                warn("MISSING_EVIDENCE", section, index)
                continue
            text = "\n".join(
                line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()
            )
            sections[section].append(
                Recommendation(text=prefix + text, evidence_ids=list(dict.fromkeys(ids)))
            )
    if not any(sections.values()):
        raise ReportValidationError("REPORT_EMPTY")
    return ValidatedReport(sections=sections, partial=bool(warnings), validationWarnings=warnings)
