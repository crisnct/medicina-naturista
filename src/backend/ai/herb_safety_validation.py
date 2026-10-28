"""Validate extractive safety responses; missing coverage never means absence of warnings."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from backend.ai.herb_association_rules import content_hash
from backend.ai.herb_index_catalog import normalize_herb_name
from backend.ai.herb_safety_extraction import (
    EXTRACTION_VERSION,
    SUMMARY_MAX_CHARS,
    SUMMARY_MAX_WORDS,
    WARNING_KINDS,
    WARNING_TERMS,
    SafetyTarget,
    eligible_warning_statements,
    source_passages,
    statement_summary,
    supports_quote,
    supports_warning_statement,
    warning_statements,
)
from backend.config import Settings

PROMPT_PATH = Path(__file__).parent / "prompts" / "herb_safety_system.md"
TRANSPORT_PATH = PROMPT_PATH.with_name("herb_safety_transport.md")
COMBINED_PATH = PROMPT_PATH.with_name("herb_association_with_warnings_transport.md")


@dataclass(frozen=True)
class SafetyWarning:
    kind: str
    text: str
    start: int
    end: int
    partners: tuple[str, ...] = ()
    summary: str = ""
    focus_start: int | None = None
    focus_end: int | None = None

    def identity(self, herb_id: int) -> str:
        # One concise warning can retain independently verifiable quotations from several sources.
        return content_hash([herb_id, self.kind, self.summary or self.text, self.partners])


@dataclass(frozen=True)
class SafetyResult:
    status: Literal["complete", "unclear", "local", "uncovered"]
    items: tuple[SafetyWarning, ...] = ()


def safety_semantic(settings: Settings) -> dict[str, Any]:
    return {
        "version": EXTRACTION_VERSION,
        "citation_protocol": "source_statement_summary_v2",
        "prompt": content_hash(PROMPT_PATH.read_text(encoding="utf-8")),
        "transport": content_hash(TRANSPORT_PATH.read_text(encoding="utf-8")),
        "combined_transport": content_hash(COMBINED_PATH.read_text(encoding="utf-8")),
        "validation": content_hash(Path(__file__).read_text(encoding="utf-8")),
        "extraction": content_hash(
            Path(__file__).with_name("herb_safety_extraction.py").read_text(encoding="utf-8")
        ),
        "model": settings.herb_association_ai_model,
    }


def safety_prompt() -> str:
    return "\n\n".join(
        path.read_text(encoding="utf-8").strip() for path in (PROMPT_PATH, TRANSPORT_PATH)
    )


def warning_schema(payload: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for target in payload["safety_targets"]:
        unit = payload["units"][target["unit"]]
        identifiers = list(unit["citation_passages"])
        focuses = target["warning_statement_ids"]
        reference: dict[str, Any] = {"type": "string"}
        if identifiers:
            reference["enum"] = identifiers
        item = {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "passage_ids", "focus_id", "summary", "partners"],
            "properties": {
                "kind": {"type": "string", "enum": list(WARNING_KINDS)},
                "focus_id": {"type": "string", "enum": focuses or ["unavailable"]},
                "summary": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": SUMMARY_MAX_CHARS,
                    "pattern": rf"^[^\r\n]{{1,{SUMMARY_MAX_CHARS}}}$",
                },
                "passage_ids": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": max(1, len(identifiers)),
                    "uniqueItems": True,
                    "items": reference,
                },
                "partners": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": max(1, len(unit["text"])),
                    },
                },
            },
        }
        certain = target.get("certain") is True
        items: dict[str, Any] = {"type": "array", "uniqueItems": True, "items": item}
        if not certain or not identifiers or not focuses:
            items = {"type": "array", "maxItems": 0}
        # Coverage cannot exceed the identity that can be verified against the source.
        properties[target["id"]] = {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "items"],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["complete", "unclear"] if certain else ["unclear"],
                },
                "items": items,
            },
        }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


# Display wording stays short without truncation, invented quantities or stronger prohibitions.
def _validated_summary(value: Any, quote: str, focus: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or "\n" in value
        or "\r" in value
        or len(value.strip()) > SUMMARY_MAX_CHARS
        or len(value.split()) > SUMMARY_MAX_WORDS
        or re.match(r"^\s*(?:[-*#•]|\d+[.)]\s)", value)
    ):
        raise ValueError("HERB_SAFETY_UNSUPPORTED_SUMMARY")
    summary = value.strip()

    def numerals(text: str) -> set[str]:
        return {token.replace(",", ".") for token in re.findall(r"\d+(?:[.,]\d+)?", text)}

    if not numerals(summary) <= numerals(quote):
        raise ValueError("HERB_SAFETY_UNSUPPORTED_SUMMARY")

    def quantities(text: str) -> set[tuple[str, str]]:
        def unit_key(unit: str) -> str:
            return "".join(
                char
                for char in unicodedata.normalize("NFD", unit.casefold())
                if not unicodedata.combining(char)
            )

        return {
            (number.replace(",", "."), unit_key(unit))
            for number, unit in re.findall(
                r"(\d+(?:[.,]\d+)?)\s*"
                r"(mg|mcg|[µμ]g|g|kg|ml|l|ui|%|or[ăa]|ore|zi|zile|luni|an|ani|"
                r"s[ăa]pt[ăa]m[âa]ni|minute|minut)(?!\w)",
                text,
                re.IGNORECASE,
            )
        }

    if not quantities(summary) <= quantities(quote):
        raise ValueError("HERB_SAFETY_UNSUPPORTED_SUMMARY")
    if not quantities(focus) <= quantities(summary):
        raise ValueError("HERB_SAFETY_UNSUPPORTED_SUMMARY")
    if re.search(
        r"\b(?:interzis\w*|contraindicat\w*)\b", normalize_herb_name(summary)
    ) and not re.search(
        r"\b(?:interzis\w*|contraindicat\w*|nu (?:se )?"
        r"(?:consum|folos|administr|recomand|asoci|utiliz|aplic|depas)\w*)\b",
        normalize_herb_name(focus),
    ):
        raise ValueError("HERB_SAFETY_UNSUPPORTED_SUMMARY")
    return summary


# Reference IDs select exact offsets in this target's original source, independently of the payload.
def _reference_warning(
    target: SafetyTarget, item: Any, passages: dict[str, tuple[int, int]]
) -> SafetyWarning:
    if (
        not isinstance(item, dict)
        or set(item) != {"kind", "passage_ids", "focus_id", "summary", "partners"}
        or not isinstance(item["kind"], str)
        or item["kind"] not in WARNING_KINDS
        or not isinstance(item["passage_ids"], list)
        or not item["passage_ids"]
        or any(not isinstance(identifier, str) for identifier in item["passage_ids"])
        or not isinstance(item["focus_id"], str)
        or not isinstance(item["partners"], list)
        or any(not isinstance(partner, str) or not partner.strip() for partner in item["partners"])
    ):
        raise ValueError("HERB_SAFETY_INVALID_REFERENCE_ITEM")
    if any(identifier not in passages for identifier in item["passage_ids"]):
        raise ValueError("HERB_SAFETY_UNKNOWN_PASSAGE")
    positions = {identifier: position for position, identifier in enumerate(passages)}
    selected_positions = sorted({positions[identifier] for identifier in item["passage_ids"]})
    if any(right != left + 1 for left, right in zip(selected_positions, selected_positions[1:])):
        raise ValueError("HERB_SAFETY_NONCONTIGUOUS_PASSAGES")
    selected = sorted({passages[identifier] for identifier in item["passage_ids"]})
    start, end = selected[0][0], selected[-1][1]
    if any(not supports_quote(target, *span) for span in selected):
        raise ValueError("HERB_SAFETY_PASSAGE_SCOPE")
    statements = warning_statements(target)
    if item["focus_id"] not in statements:
        raise ValueError("HERB_SAFETY_UNKNOWN_STATEMENT")
    focus_start, focus_end = statements[item["focus_id"]]
    if not start <= focus_start < focus_end <= end or not supports_warning_statement(
        target, focus_start, focus_end
    ):
        raise ValueError("HERB_SAFETY_STATEMENT_SCOPE")
    quote = target.text[start:end]
    if any(partner not in quote for partner in item["partners"]):
        raise ValueError("HERB_SAFETY_PASSAGE_PARTNER")
    summary = _validated_summary(item["summary"], quote, target.text[focus_start:focus_end])
    return SafetyWarning(
        item["kind"],
        quote,
        start,
        end,
        tuple(sorted(set(item["partners"]))),
        summary,
        focus_start,
        focus_end,
    )


# Invalid references cannot discard other evidence or silently become complete coverage.
def validate_reference_warnings(
    raw: Any, targets: list[SafetyTarget]
) -> tuple[dict[str, SafetyResult], dict[str, int]]:
    expected = {f"s{position}": target for position, target in enumerate(targets)}
    if not isinstance(raw, dict) or raw.keys() != expected.keys():
        raise ValueError("HERB_SAFETY_INCOMPLETE_RESPONSE")
    reasons = {
        "HERB_SAFETY_UNKNOWN_PASSAGE": "safety_rejected_passage_id",
        "HERB_SAFETY_NONCONTIGUOUS_PASSAGES": "safety_rejected_passage_sequence",
        "HERB_SAFETY_PASSAGE_SCOPE": "safety_rejected_quote_scope",
        "HERB_SAFETY_PASSAGE_PARTNER": "safety_rejected_partner",
        "HERB_SAFETY_UNKNOWN_STATEMENT": "safety_rejected_statement_id",
        "HERB_SAFETY_STATEMENT_SCOPE": "safety_rejected_quote_scope",
        "HERB_SAFETY_UNSUPPORTED_SUMMARY": "safety_rejected_summary",
    }
    results: dict[str, SafetyResult] = {}
    diagnostics: dict[str, int] = {}
    for identifier, target in expected.items():
        value = raw[identifier]
        if (
            not isinstance(value, dict)
            or set(value) != {"status", "items"}
            or not isinstance(value["status"], str)
            or value["status"] not in {"complete", "unclear"}
            or not isinstance(value["items"], list)
        ):
            raise ValueError("HERB_SAFETY_INVALID_RESPONSE")
        if not target.certain and (value["status"] != "unclear" or value["items"] != []):
            raise ValueError("HERB_SAFETY_AMBIGUOUS_TARGET")
        status: Literal["complete", "unclear"] = (
            "complete" if value["status"] == "complete" else "unclear"
        )
        warnings: dict[tuple[str, int, int], SafetyWarning] = {}
        rejected = False
        passages = source_passages(target)
        for item in value["items"]:
            try:
                warning = _reference_warning(target, item, passages)
            except ValueError as error:
                reason = reasons.get(str(error))
                if reason is None:
                    raise
                rejected = True
                diagnostics[reason] = diagnostics.get(reason, 0) + 1
                diagnostics["safety_rejected_quotes"] = (
                    diagnostics.get("safety_rejected_quotes", 0) + 1
                )
            else:
                warnings[(warning.identity(target.herb_id), warning.start, warning.end)] = warning
        if rejected:
            status = "unclear"
            diagnostics["safety_unclear_after_validation"] = (
                diagnostics.get("safety_unclear_after_validation", 0) + 1
            )
        results[target.identity] = SafetyResult(status, tuple(warnings.values()))
    return results, diagnostics


def validate_items(target: SafetyTarget, entries: Any) -> tuple[SafetyWarning, ...]:
    if not isinstance(entries, list):
        raise ValueError("HERB_SAFETY_INVALID_ITEMS")
    if not entries:
        return ()
    statements = eligible_warning_statements(target)
    result: dict[tuple[str, int, int], SafetyWarning] = {}
    for item in entries:
        if (
            not isinstance(item, dict)
            or set(item) != {"kind", "quote", "partners"}
            or item["kind"] not in WARNING_KINDS
            or not isinstance(item["quote"], str)
            or not item["quote"].strip()
            or not isinstance(item["partners"], list)
            or any(not isinstance(p, str) or not p.strip() for p in item["partners"])
        ):
            raise ValueError("HERB_SAFETY_INVALID_ITEM")
        quote = item["quote"]
        spans = [
            (match.start(), match.end()) for match in re.finditer(re.escape(quote), target.text)
        ]
        valid_spans = [span for span in spans if supports_quote(target, *span)]
        if not valid_spans or any(partner not in quote for partner in item["partners"]):
            raise ValueError("HERB_SAFETY_UNSUPPORTED_QUOTE")
        summary = statement_summary(quote)
        if len(summary) > SUMMARY_MAX_CHARS or len(summary.split()) > SUMMARY_MAX_WORDS:
            raise ValueError("HERB_SAFETY_UNSUPPORTED_SUMMARY")
        recovered = False
        for valid in valid_spans:
            for focus_start, focus_end in statements.values():
                focus = target.text[focus_start:focus_end]
                if (
                    not valid[0] <= focus_start < focus_end <= valid[1]
                    or not WARNING_TERMS.search(normalize_herb_name(focus))
                    or any(partner not in focus for partner in item["partners"])
                ):
                    continue
                warning = SafetyWarning(
                    item["kind"],
                    quote,
                    *valid,
                    tuple(sorted(set(item["partners"]))),
                    _validated_summary(summary, quote, focus),
                    focus_start,
                    focus_end,
                )
                result[(warning.identity(target.herb_id), warning.start, warning.end)] = warning
                recovered = True
        if not recovered:
            raise ValueError("HERB_SAFETY_UNSUPPORTED_QUOTE")
    return tuple(result.values())


def validate_warnings(raw: Any, targets: list[SafetyTarget]) -> dict[str, SafetyResult]:
    expected = {f"s{position}": target for position, target in enumerate(targets)}
    if not isinstance(raw, dict) or raw.keys() != expected.keys():
        raise ValueError("HERB_SAFETY_INCOMPLETE_RESPONSE")
    results = {}
    for identifier, target in expected.items():
        value = raw[identifier]
        if (
            not isinstance(value, dict)
            or set(value) != {"status", "items"}
            or not isinstance(value["status"], str)
            or value["status"] not in {"complete", "unclear"}
        ):
            raise ValueError("HERB_SAFETY_INVALID_RESPONSE")
        if not target.certain and (value["status"] != "unclear" or value["items"] != []):
            raise ValueError("HERB_SAFETY_AMBIGUOUS_TARGET")
        status: Literal["complete", "unclear"] = (
            "complete" if value["status"] == "complete" else "unclear"
        )
        results[target.identity] = SafetyResult(status, validate_items(target, value["items"]))
    return results


def encode_result(result: SafetyResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "items": [{**asdict(item), "partners": list(item.partners)} for item in result.items],
    }


def decode_result(value: Any, target: SafetyTarget) -> SafetyResult:
    if (
        not isinstance(value, dict)
        or set(value) != {"status", "items"}
        or not isinstance(value["status"], str)
        or value["status"] not in {"complete", "unclear"}
        or not isinstance(value["items"], list)
    ):
        raise ValueError("HERB_SAFETY_INVALID_CACHE")
    warnings: dict[tuple[str, int, int], SafetyWarning] = {}
    eligible = set(eligible_warning_statements(target).values())
    for item in value["items"]:
        if (
            not isinstance(item, dict)
            or set(item)
            != {"kind", "text", "start", "end", "partners", "summary", "focus_start", "focus_end"}
            or not isinstance(item["kind"], str)
            or item["kind"] not in WARNING_KINDS
            or not isinstance(item["text"], str)
            or not item["text"].strip()
            or not isinstance(item["partners"], list)
            or any(
                not isinstance(partner, str) or not partner.strip() for partner in item["partners"]
            )
            or type(item["start"]) is not int
            or type(item["end"]) is not int
            or not 0 <= item["start"] < item["end"] <= len(target.text)
            or target.text[item["start"] : item["end"]] != item["text"]
            or type(item["focus_start"]) is not int
            or type(item["focus_end"]) is not int
            or not item["start"] <= item["focus_start"] < item["focus_end"] <= item["end"]
            or (item["focus_start"], item["focus_end"]) not in eligible
            or not supports_quote(target, item["start"], item["end"])
            or any(partner not in item["text"] for partner in item["partners"])
        ):
            raise ValueError("HERB_SAFETY_INVALID_CACHE")
        try:
            summary = _validated_summary(
                item["summary"], item["text"], target.text[item["focus_start"] : item["focus_end"]]
            )
        except ValueError:
            raise ValueError("HERB_SAFETY_INVALID_CACHE") from None
        warning = SafetyWarning(
            item["kind"],
            item["text"],
            item["start"],
            item["end"],
            tuple(sorted(set(item["partners"]))),
            summary,
            item["focus_start"],
            item["focus_end"],
        )
        warnings[(warning.identity(target.herb_id), warning.start, warning.end)] = warning
    if not target.certain and (value["status"] != "unclear" or warnings):
        raise ValueError("HERB_SAFETY_INVALID_CACHE")
    status: Literal["complete", "unclear"] = (
        "complete" if value["status"] == "complete" else "unclear"
    )
    return SafetyResult(status, tuple(warnings.values()))
