"""Validated bilingual copy with immutable catalogs selected by execution context."""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from string import Formatter
from types import MappingProxyType

from backend.core.language import Language, current_language, validate_language
from backend.core.text_contract import TEXT_PARAMETERS

CATALOG_PATH = Path(__file__).resolve().parents[1] / "resources" / "texts.ro.toml"
PUBLIC_SECTIONS = frozenset(("common", "interface"))


def validate_catalog(source: Mapping[str, object]) -> Mapping[str, str]:
    values: dict[str, str] = {}
    for section, entries in source.items():
        if not isinstance(entries, dict):
            raise ValueError(f"Text catalog section {section!r} must be a table")
        for name, value in entries.items():
            key = f"{section}.{name}"
            if not isinstance(value, str):
                raise ValueError(f"Text catalog value {key!r} must be a string")
            values[key] = value
    missing = TEXT_PARAMETERS.keys() - values.keys()
    unknown = values.keys() - TEXT_PARAMETERS.keys()
    if missing or unknown:
        raise ValueError(f"Text catalog keys: missing={sorted(missing)}, unknown={sorted(unknown)}")
    for key, value in values.items():
        try:
            fields = list(Formatter().parse(value))
        except ValueError as exc:
            raise ValueError(f"Invalid text template {key}: {exc}") from exc
        parameters = set()
        for _, field, spec, conversion in fields:
            if field is None:
                continue
            if not field.isidentifier() or spec or conversion:
                raise ValueError(f"Invalid named parameter in text template {key}: {field!r}")
            parameters.add(field)
        if parameters != set(TEXT_PARAMETERS[key]):
            raise ValueError(f"Text parameters for {key}: expected {TEXT_PARAMETERS[key]}")
        if re.search(r"<\s*/?\s*[a-zA-Z][^>]*>", value):
            raise ValueError(f"HTML is not allowed in text template {key}")
    return MappingProxyType(values)


@lru_cache(maxsize=2)
def catalog(language: Language = "ro") -> Mapping[str, str]:
    selected = validate_language(language)
    with CATALOG_PATH.with_name(f"texts.{selected}.toml").open("rb") as stream:
        return validate_catalog(tomllib.load(stream))


def tr(key: str, *, language: str | None = None, **parameters: object) -> str:
    expected = set(TEXT_PARAMETERS[key])
    if parameters.keys() != expected:
        raise ValueError(f"Text parameters for {key}: expected {sorted(expected)}")
    return catalog(validate_language(language) if language is not None else current_language())[
        key
    ].format_map(parameters)


def public_catalog(language: Language | None = None) -> dict[str, str]:
    return {
        key: value
        for key, value in catalog(language or current_language()).items()
        if key.split(".", 1)[0] in PUBLIC_SECTIONS
    }


def script_json(value: object) -> str:
    # JSON script elements must never be terminable by editable copy.
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
