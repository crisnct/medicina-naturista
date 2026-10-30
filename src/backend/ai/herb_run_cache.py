"""Verify the active positive ranking once per published state, not on every request."""

from __future__ import annotations

import hashlib

from psycopg import Connection

from backend.ai import condition_repository
from backend.ai.conditions import ConditionDictionary
from backend.ai.herb_caution_repository import clear_verified_cautions
from backend.ai.herb_positive_repository import active_key
from backend.ai.herb_positive_repository import active_run as verify_active_run
from backend.config import Settings
from backend.core.language import current_language

# Full verification re-reads the whole catalog and every evidence row (seconds), so it runs once
# per published state: startup, then again only when sync_metadata changes. Out-of-band edits
# to the tables themselves are therefore caught at the next startup, not per request.
# This lives apart from herb_positive_repository.py because that file's source hash is part of
# the ranking's semantic fingerprint: editing it would mark every published ranking stale.
_verified: dict[str, tuple[str, str]] = {}


_conditions: dict[str, tuple[str, ConditionDictionary]] = {}


def clear_verified_runs() -> None:
    _verified.clear()
    _conditions.clear()
    clear_verified_cautions()


condition_repository.cache_clear_hooks.append(_conditions.clear)


def _published_state(connection: Connection) -> tuple[str | None, str]:
    rows = connection.execute("SELECT key,value FROM sync_metadata ORDER BY key").fetchall()
    return dict(rows).get(active_key()), hashlib.sha256(repr(rows).encode()).hexdigest()


def active_run(connection: Connection, settings: Settings) -> str:
    language = current_language()
    active, state = _published_state(connection)
    if active is not None and _verified.get(language) == (active, state):
        return active
    run_id = verify_active_run(connection, settings)
    _verified[language] = (run_id, state)
    return run_id


# Re-reading every condition and synonym costs hundreds of milliseconds, so the matching
# dictionary is rebuilt only when the published state changes.
def condition_dictionary(connection: Connection) -> ConditionDictionary:
    language = current_language()
    _, state = _published_state(connection)
    cached = _conditions.get(language)
    if cached is not None and cached[0] == state:
        return cached[1]
    dictionary = condition_repository.catalog_snapshot(connection).dictionary
    _conditions[language] = (state, dictionary)
    return dictionary
