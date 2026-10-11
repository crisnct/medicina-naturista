"""Ordered PostgreSQL condition snapshots shared by retrieval and indexing."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from threading import Lock

from psycopg import Connection

from backend.ai.conditions import Condition, ConditionDictionary, _normalize, make_condition
from backend.core.errors import ApplicationError

FINGERPRINT_VERSION = 1
_cache_lock = Lock()
_cache: OrderedDict[tuple, CatalogSnapshot] = OrderedDict()


class CatalogUnavailable(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "CONDITION_CATALOG_UNAVAILABLE",
            "Catalogul de afecțiuni lipsește sau este invalid. Rulați reindexarea.",
            503,
        )


@dataclass(frozen=True)
class CatalogSnapshot:
    fingerprint: str
    fingerprint_version: int
    dictionary: ConditionDictionary


def catalog_fingerprint(conditions: Sequence[Condition]) -> str:
    payload = [FINGERPRINT_VERSION, [[item.name, list(item.terms)] for item in conditions]]
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def clear_catalog_cache() -> None:
    with _cache_lock:
        _cache.clear()


def read_conditions(connection: Connection) -> tuple[Condition, ...]:
    rows = connection.execute(
        "SELECT c.id, c.name, s.synonym "
        "FROM medical_conditions c LEFT JOIN medical_condition_synonyms s "
        "ON s.medical_condition_id = c.id ORDER BY c.id, s.id"
    ).fetchall()
    items: list[Condition] = []
    previous_id = None
    name = ""
    terms: list[str] = []
    names: set[str] = set()
    for condition_id, current_name, synonym in rows:
        if condition_id != previous_id:
            if previous_id is not None:
                items.append(make_condition(name, terms))
            previous_id = condition_id
            name = current_name
            terms = []
            key = _normalize(name)
            if not key or key in names or name != " ".join(name.split()):
                raise CatalogUnavailable()
            names.add(key)
        if synonym is not None:
            if not isinstance(synonym, str) or not _normalize(synonym):
                raise CatalogUnavailable()
            terms.append(synonym)
    if previous_id is not None:
        items.append(make_condition(name, terms))
    if not items:
        raise CatalogUnavailable()
    return tuple(items)


def catalog_snapshot(connection: Connection) -> CatalogSnapshot:
    """Read the two tables under the caller's index lock; cache matching in memory."""
    conditions = read_conditions(connection)
    fingerprint = catalog_fingerprint(conditions)
    info = connection.info
    key = (info.host, info.port, info.dbname, info.user, fingerprint)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
        snapshot = CatalogSnapshot(
            fingerprint, FINGERPRINT_VERSION, ConditionDictionary(conditions)
        )
        _cache[key] = snapshot
        while len(_cache) > 4:
            _cache.popitem(last=False)
        return snapshot
