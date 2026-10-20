"""Read the requested plant's distinct corpus associations in one snapshot."""

from __future__ import annotations

import psycopg
from psycopg_pool import PoolTimeout

from backend.ai import db
from backend.ai.herb_index_catalog import read_index_catalogs
from backend.ai.herb_repository import HERBS_INDEX_VERSION, catalog_snapshot
from backend.ai.index_state import INDEX_LOCK, IndexUnavailable
from backend.core.contracts import HerbLookupResult

HERB_CONDITIONS_SQL = """
SELECT DISTINCT mc.id, mc.name
FROM herbs AS h
JOIN herbs_benefits AS hb ON hb.herb_id = h.id
JOIN medical_conditions AS mc ON mc.id = hb.medical_condition_id
WHERE h.ro ILIKE %s AND h.id = %s
ORDER BY mc.name
"""


def literal_pattern(name: str) -> str:
    return name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def lookup_herb_conditions(name: str) -> HerbLookupResult:
    try:
        with db.get_pool().connection() as connection, connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            lock_row = connection.execute(
                "SELECT pg_try_advisory_xact_lock_shared(%s)", (INDEX_LOCK,)
            ).fetchone()
            if lock_row is None or not lock_row[0]:
                raise IndexUnavailable()
            herbs = catalog_snapshot(connection)
            specific = herbs.catalog.by_latin(name)
            matches = [specific] if specific is not None else herbs.catalog.request_matches(name)
            if not matches:
                return {"status": "not_found"}
            if len(matches) > 1:
                return {"status": "ambiguous", "choices": sorted(herb.choice for herb in matches)}
            selected = matches[0]
            canonical = selected.ro
            species = [selected.latin]
            metadata: dict[str, str] = dict(
                connection.execute("SELECT key, value FROM sync_metadata").fetchall()
            )
            *_, conditions_fingerprint, herbs_fingerprint = read_index_catalogs(connection)
            required = {
                "herbs_benefits_index_version",
                "herbs_benefits_chunks_generation",
                "herbs_benefits_conditions_fingerprint",
                "herbs_benefits_herbs_fingerprint",
                "herbs_benefits_row_count",
                "index_generation",
            }
            if (
                not required <= metadata.keys()
                or metadata["herbs_benefits_index_version"] != str(HERBS_INDEX_VERSION)
                or metadata["herbs_benefits_chunks_generation"] != metadata["index_generation"]
                or metadata["herbs_benefits_herbs_fingerprint"] != herbs_fingerprint
                or metadata["herbs_benefits_conditions_fingerprint"] != conditions_fingerprint
            ):
                raise IndexUnavailable("INDEX_HERBS_RESYNC_REQUIRED")
            count_row = connection.execute("SELECT count(*) FROM herbs_benefits").fetchone()
            if count_row is None or metadata["herbs_benefits_row_count"] != str(count_row[0]):
                raise IndexUnavailable("INDEX_HERBS_RESYNC_REQUIRED")
            rows = connection.execute(
                HERB_CONDITIONS_SQL, (literal_pattern(canonical), selected.id)
            ).fetchall()
            return {
                "status": "found",
                "herbName": canonical,
                "species": species,
                "entriesCount": len(rows),
                "conditions": [
                    {"id": condition_id, "name": condition} for condition_id, condition in rows
                ],
            }
    except (psycopg.Error, PoolTimeout):
        raise IndexUnavailable("INDEX_HERBS_UNAVAILABLE") from None
