"""Coherent PostgreSQL herb snapshots, cached by database and full content."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from threading import Lock

from psycopg import Connection

from backend.ai.conditions import _normalize
from backend.ai.herb_validation import ALIASES, catalog_problems
from backend.ai.herbs import FIELDS, Herb, HerbCatalog
from backend.core.errors import ApplicationError

FINGERPRINT_VERSION = 1
logger = logging.getLogger("naturist.herbs")
_cache_lock = Lock()
_cache: OrderedDict[tuple, HerbCatalogSnapshot] = OrderedDict()


class HerbCatalogUnavailable(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "HERB_CATALOG_UNAVAILABLE",
            "Catalogul de plante lipsește sau este invalid. Rulați migrările.",
            503,
        )


@dataclass(frozen=True)
class HerbCatalogSnapshot:
    fingerprint: str
    fingerprint_version: int
    catalog: HerbCatalog


def catalog_fingerprint(herbs: Sequence[Herb]) -> str:
    payload = [FINGERPRINT_VERSION, [[getattr(item, key) for key in FIELDS] for item in herbs]]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def clear_herb_catalog_cache() -> None:
    with _cache_lock:
        _cache.clear()


def read_herbs(connection: Connection) -> tuple[Herb, ...]:
    rows = connection.execute(
        "SELECT h.id, h.family, h.latin, h.ro, h.en, a.name, a.kind "
        "FROM herbs h LEFT JOIN herb_aliases a ON a.herb_id = h.id ORDER BY h.id, a.id"
    ).fetchall()
    records: dict[int, dict] = {}
    for herb_id, family, latin, ro, en, name, kind in rows:
        if type(herb_id) is not int or not all(isinstance(v, str) for v in (family, latin, ro, en)):
            raise HerbCatalogUnavailable()
        record = records.setdefault(
            herb_id,
            dict(
                id=herb_id, family=family, latin=latin, ro=ro, en=en, **{key: [] for key in ALIASES}
            ),
        )
        if kind is not None or name is not None:
            if kind not in ALIASES or not isinstance(name, str):
                raise HerbCatalogUnavailable()
            record[kind].append(name)
    items = tuple(
        sorted(
            (
                Herb(
                    id=record["id"],
                    family=record["family"],
                    latin=record["latin"],
                    ro=record["ro"],
                    en=record["en"],
                    ro_regional=tuple(record["ro_regional"]),
                    latin_synonyms=tuple(record["latin_synonyms"]),
                    en_alt=tuple(record["en_alt"]),
                )
                for record in records.values()
            ),
            key=lambda herb: (_normalize(herb.ro), _normalize(herb.latin), herb.id),
        )
    )
    problems = catalog_problems(items, source=False)
    if problems:
        logger.error("herb_catalog_unavailable stage=validate problems=%s", problems[:20])
        raise HerbCatalogUnavailable()
    return items


def catalog_snapshot(connection: Connection) -> HerbCatalogSnapshot:
    herbs = read_herbs(connection)
    fingerprint = catalog_fingerprint(herbs)
    info = connection.info
    key = (info.host, info.port, info.dbname, info.user, fingerprint)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
        snapshot = HerbCatalogSnapshot(fingerprint, FINGERPRINT_VERSION, HerbCatalog(list(herbs)))
        _cache[key] = snapshot
        while len(_cache) > 4:
            _cache.popitem(last=False)
        return snapshot
