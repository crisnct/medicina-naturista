"""Query-word helpers shared by retrieval.py (query building) and search.py
(lexical matching). Kept in their own module because retrieval imports
search, so search cannot import back from retrieval."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

GENERIC_QUERY_WORDS_PATH = (
    Path(__file__).resolve().parent / "resources" / "generic_query_words.txt"
)
GENERIC_QUERY_WORDS = frozenset(
    GENERIC_QUERY_WORDS_PATH.read_text(encoding="utf-8").split()
)


# Normalize text for case-insensitive and diacritic-insensitive comparisons.
def plain(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


# Extract searchable words while excluding short and generic terms.
def meaningful_words(value: str) -> set[str]:
    return {
        word for word in re.findall(r"\w+", plain(value))
        if len(word) >= 4 and word not in GENERIC_QUERY_WORDS
    }
