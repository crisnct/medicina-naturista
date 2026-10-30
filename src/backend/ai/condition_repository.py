"""Ordered PostgreSQL condition snapshots shared by retrieval and indexing."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from threading import Lock

from psycopg import Connection

from backend.ai.conditions import Condition, ConditionDictionary, _normalize, make_condition
from backend.core.errors import ApplicationError
from backend.core.language import current_language
from backend.core.texts import tr

FINGERPRINT_VERSION = 2
_cache_lock = Lock()
_cache: OrderedDict[tuple, CatalogSnapshot] = OrderedDict()


class CatalogUnavailable(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "CONDITION_CATALOG_UNAVAILABLE",
            tr("errors.condition_catalog_unavailable"),
            503,
        )


@dataclass(frozen=True)
class CatalogSnapshot:
    fingerprint: str
    fingerprint_version: int
    dictionary: ConditionDictionary


def catalog_fingerprint(conditions: Sequence[Condition]) -> str:
    payload = [
        FINGERPRINT_VERSION,
        [[item.name, item.english, list(item.terms)] for item in conditions],
    ]
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# Derived caches elsewhere register here so a reset of this cache cannot leave them stale.
cache_clear_hooks: list[Callable[[], None]] = []


def clear_catalog_cache() -> None:
    with _cache_lock:
        _cache.clear()
    for hook in cache_clear_hooks:
        hook()


def read_conditions(connection: Connection) -> tuple[Condition, ...]:
    rows = connection.execute(
        "SELECT c.id, c.name, c.en, s.synonym "
        "FROM medical_conditions c LEFT JOIN medical_condition_synonyms s "
        "ON s.medical_condition_id = c.id ORDER BY c.id, s.id"
    ).fetchall()
    items: list[Condition] = []
    previous_id = None
    name = ""
    english = ""
    terms: list[str] = []
    names: set[str] = set()
    for condition_id, current_name, current_english, synonym in rows:
        if condition_id != previous_id:
            if previous_id is not None:
                items.append(replace(make_condition(name, terms), english=english))
            previous_id = condition_id
            name = current_name
            english = current_english
            if not isinstance(english, str) or not english.strip():
                raise CatalogUnavailable()
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
        items.append(replace(make_condition(name, terms), english=english))
    if not items:
        raise CatalogUnavailable()
    return tuple(items)


def catalog_snapshot(connection: Connection) -> CatalogSnapshot:
    """Read the two tables under the caller's index lock; cache matching in memory."""
    conditions = read_conditions(connection)
    fingerprint = catalog_fingerprint(conditions)
    info = connection.info
    key = (info.host, info.port, info.dbname, info.user, fingerprint, current_language())
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
