"""Ordered PostgreSQL condition snapshots shared by retrieval and indexing."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from threading import Lock

from psycopg import Connection
from psycopg.errors import UndefinedTable

from backend.ai.conditions import Condition, ConditionDictionary, _normalize, make_condition
from backend.core.errors import ApplicationError
from backend.core.language import current_language
from backend.core.texts import tr

logger = logging.getLogger("naturist.conditions")
FINGERPRINT_VERSION = 2
_cache_lock = Lock()
_cache: OrderedDict[tuple, CatalogSnapshot] = OrderedDict()
# Database and language -> (value of medical_conditions_version, snapshot read at that value).
_versioned: OrderedDict[tuple, tuple[int, CatalogSnapshot]] = OrderedDict()


class CatalogUnavailable(ApplicationError):
    def __init__(self, code: str = "CONDITION_CATALOG_UNAVAILABLE") -> None:
        super().__init__(
            code,
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
        _versioned.clear()
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


def read_version(connection: Connection) -> int:
    """The change counter of the two dictionary tables, kept by database triggers."""
    try:
        row = connection.execute("SELECT version FROM medical_conditions_version").fetchone()
    except UndefinedTable:
        logger.error("condition_version_schema_missing: run database migrations")
        raise CatalogUnavailable("CONDITION_VERSION_SCHEMA_MISSING") from None
    if row is None:
        raise CatalogUnavailable("CONDITION_VERSION_SCHEMA_MISSING")
    return int(row[0])


def catalog_snapshot(connection: Connection, *, refresh: bool = False) -> CatalogSnapshot:
    """Read the two tables under the caller's index lock; cache matching in memory.

    While the change counter is unchanged the snapshot read at that value is returned without
    reading the tables; `refresh` always reads them, for a caller that distrusts the counter."""
    info = connection.info
    scope = (info.host, info.port, info.dbname, info.user, current_language())
    version = read_version(connection)
    with _cache_lock:
        known = _versioned.get(scope)
        if known is not None and known[0] == version and not refresh:
            _versioned.move_to_end(scope)
            return known[1]
    conditions = read_conditions(connection)
    fingerprint = catalog_fingerprint(conditions)
    key = (*scope[:4], fingerprint, scope[4])
    with _cache_lock:
        snapshot = _cache.get(key)
        if snapshot is None:
            snapshot = CatalogSnapshot(
                fingerprint, FINGERPRINT_VERSION, ConditionDictionary(conditions)
            )
            _cache[key] = snapshot
        _cache.move_to_end(key)
        while len(_cache) > 4:
            _cache.popitem(last=False)
        # The counter was read before the tables, so a change in between only makes the entry
        # look older than its data and costs one extra read later.
        _versioned[scope] = (version, snapshot)
        _versioned.move_to_end(scope)
        while len(_versioned) > 8:
            _versioned.popitem(last=False)
        return snapshot
