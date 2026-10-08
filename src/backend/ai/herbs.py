"""Catalogue of medicinal plants (medicina-naturista-documente/data/herbs.jsonl): one species per line, as a
JSON object with the keys of FIELDS. The accepted Latin name identifies the
species; `id` is a stable slug that survives a later change of that name; the
Romanian name `ro` may be shared by several species ("Paducel" is both
Crataegus monogyna and C. laevigata), so a lookup by name returns a list.
Fungi, lichens, mosses and algae are in the catalogue too. Nothing in search or
fragmentation uses it yet."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.ai.conditions import _normalize
from backend.config import settings

logger = logging.getLogger("naturist.herbs")

# The keys of a line, in the order they are written.
FIELDS = ("id", "ro", "ro_regional", "latin", "latin_synonyms", "en", "en_alt", "family")
_STRINGS = ("id", "ro", "latin", "en", "family")
_LISTS = ("ro_regional", "latin_synonyms", "en_alt")


@dataclass(frozen=True)
class Herb:
    id: str
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
        return tuple(name for name in (
            self.ro, *self.ro_regional, self.latin, *self.latin_synonyms, self.en, *self.en_alt,
        ) if name)


# Parse the catalogue text (JSON Lines). Blank lines are skipped; a line whose
# keys or value types differ from FIELDS raises ValueError with its number. Every
# string field must be non-empty except `en`.
def parse_herbs(text: str) -> list[Herb]:
    herbs: list[Herb] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"herbs line {number}: invalid JSON ({error.msg})") from None
        if not isinstance(record, dict) or set(record) != set(FIELDS):
            raise ValueError(f"herbs line {number}: expected an object with exactly the keys {', '.join(FIELDS)}")
        for key in _STRINGS:
            value = record[key]
            if not isinstance(value, str) or (key != "en" and not value.strip()):
                raise ValueError(f"herbs line {number}: '{key}' must be a non-empty string")
        for key in _LISTS:
            value = record[key]
            if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
                raise ValueError(f"herbs line {number}: '{key}' must be a list of non-empty strings")
        herbs.append(Herb(**{key: tuple(record[key]) if key in _LISTS else record[key] for key in FIELDS}))
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

    def by_id(self, herb_id: str) -> Herb | None:
        return self._by_id.get(herb_id)

    # The species whose accepted Latin name or Latin synonym this is (case ignored).
    def by_latin(self, latin: str) -> Herb | None:
        return self._by_latin.get(_normalize(latin))

    # Every species that carries `name` as any of its names (case and
    # diacritics ignored); several when a popular name is shared.
    def lookup(self, name: str) -> list[Herb]:
        key = _normalize(name)
        return list(self._by_name.get(key, ())) if key else []


@lru_cache(maxsize=4)
def _load(path: str, mtime_ns: int) -> HerbCatalog:
    herbs = parse_herbs(Path(path).read_text(encoding="utf-8"))
    logger.info("herbs_loaded path=%s herbs=%s", path, len(herbs))
    return HerbCatalog(herbs)


# The catalogue from settings.herbs_file, reloaded when the file changes.
# A missing file yields an empty catalogue, never an error.
def load_herbs(path: Path | None = None) -> HerbCatalog:
    path = path or settings.herbs_file
    try:
        return _load(str(path), path.stat().st_mtime_ns)
    except OSError:
        logger.warning("herbs_file_unavailable path=%s", path)
        return HerbCatalog([])
