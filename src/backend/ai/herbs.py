"""PostgreSQL medicinal plants and the pure parser for offline source conversion.

Popular names may belong to several species. Plants are not used in retrieval yet.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from backend.ai.conditions import _normalize
from backend.ai.romanian_inflections import word_variants

logger = logging.getLogger("naturist.herbs")

# The keys of a line, in the order they are written.
FIELDS = ("id", "ro", "ro_regional", "latin", "latin_synonyms", "en", "en_alt", "family")
_STRINGS = ("id", "ro", "latin", "en", "family")
_LISTS = ("ro_regional", "latin_synonyms", "en_alt")
_PLANT_PARTS = frozenset(
    ("mugur", "mugure", "floare", "frunza", "radacina", "scoarta", "coaja", "fruct", "samanta")
)


@dataclass(frozen=True)
class HerbNames:
    ro: str
    ro_regional: tuple[str, ...]
    latin: str
    latin_synonyms: tuple[str, ...]
    en: str  # "" when the species has no common English name
    en_alt: tuple[str, ...]
    family: str

    # Every non-empty name of the species: ro, regional, latin, latin synonyms, en, en_alt.
    @property
    def names(self) -> tuple[str, ...]:
        return tuple(
            name
            for name in (
                self.ro,
                *self.ro_regional,
                self.latin,
                *self.latin_synonyms,
                self.en,
                *self.en_alt,
            )
            if name
        )


@dataclass(frozen=True)
class SourceHerb(HerbNames):
    id: str


@dataclass(frozen=True)
class Herb(HerbNames):
    id: int

    @property
    def choice(self) -> str:
        return f"{self.ro} ({self.latin})"


# Parse the catalogue text (JSON Lines). Blank lines are skipped; a line whose
# keys or value types differ from FIELDS raises ValueError with its number. Every
# string field must be non-empty except `en`.
def parse_herbs(text: str) -> list[SourceHerb]:
    herbs: list[SourceHerb] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"herbs line {number}: invalid JSON ({error.msg})") from None
        if not isinstance(record, dict) or set(record) != set(FIELDS):
            raise ValueError(
                f"herbs line {number}: expected an object with exactly the keys {', '.join(FIELDS)}"
            )
        for key in _STRINGS:
            value = record[key]
            if not isinstance(value, str) or (key != "en" and not value.strip()):
                raise ValueError(f"herbs line {number}: '{key}' must be a non-empty string")
        for key in _LISTS:
            value = record[key]
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                raise ValueError(
                    f"herbs line {number}: '{key}' must be a list of non-empty strings"
                )
        herbs.append(
            SourceHerb(
                id=record["id"],
                ro=record["ro"],
                ro_regional=tuple(record["ro_regional"]),
                latin=record["latin"],
                latin_synonyms=tuple(record["latin_synonyms"]),
                en=record["en"],
                en_alt=tuple(record["en_alt"]),
                family=record["family"],
            )
        )
    return herbs


class HerbCatalog:
    def __init__(self, herbs: list[Herb]) -> None:
        self.herbs = herbs
        self._by_id = {herb.id: herb for herb in herbs}
        # normalized Latin name or Latin synonym -> species
        self._by_latin: dict[str, Herb] = {}
        # normalized name of any kind -> species carrying it, in catalogue order
        self._by_name: dict[str, list[Herb]] = {}
        romanian_names: set[str] = set()
        for herb in herbs:
            romanian_names.update(_normalize(name) for name in (herb.ro, *herb.ro_regional))
            for latin in (herb.latin, *herb.latin_synonyms):
                self._by_latin.setdefault(_normalize(latin), herb)
            for name in herb.names:
                owners = self._by_name.setdefault(_normalize(name), [])
                if herb not in owners:
                    owners.append(herb)
        variants = word_variants(
            frozenset(word for name in romanian_names for word in name.split()) | _PLANT_PARTS
        )
        self._romanian_names = frozenset(romanian_names)
        self._plant_parts = frozenset(form for part in _PLANT_PARTS for form in variants[part])
        # Expand Romanian names word by word; Latin and English stay exact.
        # There is no Cartesian product of multiword names and no fuzzy spelling.
        self._phrases: dict[str, list[tuple[str, tuple[frozenset[str], ...]]]] = {}
        for name in sorted(self._by_name):
            phrase = tuple(
                variants[word] if name in romanian_names else frozenset((word,))
                for word in name.split()
            )
            if not phrase:
                continue
            for first in phrase[0]:
                self._phrases.setdefault(first, []).append((name, phrase))
        for phrases in self._phrases.values():
            phrases.sort(key=lambda item: -len(item[1]))

    def by_id(self, herb_id: int) -> Herb | None:
        return self._by_id.get(herb_id) if type(herb_id) is int else None

    # The species whose accepted Latin name or Latin synonym this is (case ignored).
    def by_latin(self, latin: str) -> Herb | None:
        return self._by_latin.get(_normalize(latin))

    # Every species that carries `name` as any of its names (case and
    # diacritics ignored, Romanian inflections accepted); several when shared.
    def lookup(self, name: str) -> list[Herb]:
        key = _normalize(name)
        if not key:
            return []
        if key in self._by_name:
            return list(self._by_name[key])
        words = key.split()
        names, _ = self._matching_names(words, 0, whole=True)
        owners = {herb.id for term in names for herb in self._by_name[term]}
        return [herb for herb in self.herbs if herb.id in owners]

    # Request-only candidates must not broaden corpus mentions or report citations.
    # Complete names win; a Romanian prefix uses whole words and preserves ambiguity.
    def request_matches(self, name: str) -> list[Herb]:
        matches = self.lookup(name)
        if matches:
            return matches
        key = _normalize(name)
        part, separator, subject = key.partition(" de ")
        if separator and part in self._plant_parts:
            key = subject
            matches = self.lookup(key)
            if matches:
                return matches
        words = key.split()
        if not words:
            return []
        names = {
            term
            for term, phrase in self._phrases.get(words[0], ())
            if term in self._romanian_names
            and len(words) < len(phrase)
            and all(word in forms for word, forms in zip(words, phrase))
        }
        owners = {herb.id for term in names for herb in self._by_name[term]}
        return [herb for herb in self.herbs if herb.id in owners]

    def _matching_names(
        self, words: list[str], position: int, *, whole: bool = False
    ) -> tuple[list[str], int]:
        names: list[str] = []
        length = 0
        for name, phrase in self._phrases.get(words[position], ()):
            size = len(phrase)
            if length and size < length:
                break
            if position + size > len(words) or (whole and size != len(words)):
                continue
            if all(words[position + offset] in forms for offset, forms in enumerate(phrase)):
                names.append(name)
                length = size
        # A literal name takes precedence over another name's inflection.
        exact = " ".join(words[position : position + length])
        return ([exact] if exact in names else names), length

    def selected_choice(self, message: str, choices: Sequence[str]) -> Herb | None:
        allowed = {_normalize(choice) for choice in choices}
        reply = _normalize(message)
        matches = [
            herb
            for herb in self.herbs
            if _normalize(herb.choice) in allowed
            and reply in {_normalize(herb.choice), _normalize(herb.ro), _normalize(herb.latin)}
        ]
        if not matches:
            matches = [herb for herb in self.lookup(message) if _normalize(herb.choice) in allowed]
        return matches[0] if len(matches) == 1 else None

    def mentioned_names(self, message: str) -> list[str]:
        words = _normalize(message).split()
        names: dict[str, None] = {}
        position = 0
        while position < len(words):
            matched, length = self._matching_names(words, position)
            names.update(dict.fromkeys(matched))
            position += length or 1
        return list(names)

    def mentions(self, message: str) -> list[Herb]:
        """Catalog names in free text, with word boundaries and longest names first."""
        matches: dict[int, Herb] = {}
        for name in self.mentioned_names(message):
            for herb in self.lookup(name):
                matches.setdefault(herb.id, herb)
        return list(matches.values())


# Read only at call time; imports never connect or create tables.
def load_herbs() -> HerbCatalog:
    import psycopg
    from psycopg_pool import PoolTimeout

    from backend.ai.db import get_pool
    from backend.ai.herb_repository import HerbCatalogUnavailable, catalog_snapshot

    try:
        with get_pool().connection() as connection:
            return catalog_snapshot(connection).catalog
    except (psycopg.Error, PoolTimeout) as error:
        logger.error(
            "herb_catalog_unavailable stage=read error_type=%s sqlstate=%s",
            type(error).__name__,
            getattr(error, "sqlstate", None),
        )
        raise HerbCatalogUnavailable() from None
