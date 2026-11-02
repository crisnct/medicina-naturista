"""Prompt paths and the warnings schema still shared with the association classification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

SUMMARY_MAX_CHARS = 240
WARNING_KINDS = (
    "high_dose",
    "adverse_effect",
    "drug_interaction",
    "product_interaction",
    "administration",
    "population",
)
PROMPT_PATH = Path(__file__).parent / "prompts" / "herb_safety_system.md"
COMBINED_PATH = PROMPT_PATH.with_name("herb_association_with_warnings_transport.md")


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
