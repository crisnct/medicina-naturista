"""Restore unambiguous product spellings using the operation's bundled dictionary."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from backend.ai.english_inflections import spelling_variants
from backend.ai.query_terms import plain
from backend.core.language import Language, current_language
from scripts.clean_documents import HUNSPELL_DIR, build_dictionary

WORDS = re.compile(r"[^\W\d_]+")


@lru_cache(maxsize=2)
def _dictionary(language: Language = "ro") -> dict[str, set[str]]:
    variants: dict[str, set[str]] = {}
    if language == "en":
        return spelling_variants()
    try:
        build_dictionary(HUNSPELL_DIR, spelling_variants=variants)
    except OSError:
        # A missing dictionary must not prevent displaying catalog names.
        return {}
    return variants


def romanian_herb_name(name: str, *, latin: str = "") -> str:
    """Leave ambiguous, unknown and explicitly accented words as stored."""
    language = current_language()
    # The species resolves the dictionary's par/păr ambiguity without changing catalog identity.
    if (
        language == "ro"
        and plain(name).casefold() == "par"
        and latin.casefold() == "pyrus communis"
    ):
        return "Păr" if name[:1].isupper() else "păr"
    dictionary = _dictionary(language)

    def replace(match: re.Match) -> str:
        word = match[0]
        if len(word) <= 2 or plain(word) != word:
            return word
        candidates = dictionary.get(word, set())
        return next(iter(candidates)) if len(candidates) == 1 else word

    normalized = unicodedata.normalize("NFC", name)
    if language == "ro":
        normalized = normalized.replace("ş", "ș").replace("ţ", "ț")
    return WORDS.sub(replace, normalized)
