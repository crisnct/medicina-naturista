"""Validated languages and isolated execution scopes; no process-wide mutable locale."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Literal, cast

Language = Literal["ro", "en"]
LANGUAGES: tuple[Language, ...] = ("ro", "en")
_language: ContextVar[Language] = ContextVar("application_language", default="ro")


def validate_language(value: str) -> Language:
    if value not in LANGUAGES:
        raise ValueError("INVALID_LANGUAGE")
    return cast(Language, value)


def current_language() -> Language:
    return _language.get()


@contextmanager
def language_scope(language: Language) -> Iterator[None]:
    token = _language.set(validate_language(language))
    try:
        yield
    finally:
        _language.reset(token)


def prompt_path(path: Path, language: Language | None = None) -> Path:
    selected = validate_language(language or current_language())
    return path if selected == "ro" else path.parent / "en" / path.name


def read_prompt(path: Path, language: Language | None = None) -> str:
    return prompt_path(path, language).read_text(encoding="utf-8").strip()
