"""PostgreSQL medicinal plants and the pure parser for offline source conversion.

Popular names may belong to several species. Plants are not used in retrieval yet.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.ai.conditions import _normalize

logger = logging.getLogger("naturist.herbs")

# The keys of a line, in the order they are written.
FIELDS = ("id", "ro", "ro_regional", "latin", "latin_synonyms", "en", "en_alt", "family")
_STRINGS = ("id", "ro", "latin", "en", "family")
_LISTS = ("ro_regional", "latin_synonyms", "en_alt")


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
        for herb in herbs:
            for latin in (herb.latin, *herb.latin_synonyms):
                self._by_latin.setdefault(_normalize(latin), herb)
            for name in herb.names:
                owners = self._by_name.setdefault(_normalize(name), [])
                if herb not in owners:
                    owners.append(herb)

    def by_id(self, herb_id: int) -> Herb | None:
        return self._by_id.get(herb_id) if type(herb_id) is int else None

    # The species whose accepted Latin name or Latin synonym this is (case ignored).
    def by_latin(self, latin: str) -> Herb | None:
        return self._by_latin.get(_normalize(latin))

    # Every species that carries `name` as any of its names (case and
    # diacritics ignored); several when a popular name is shared.
    def lookup(self, name: str) -> list[Herb]:
        key = _normalize(name)
        return list(self._by_name.get(key, ())) if key else []


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
