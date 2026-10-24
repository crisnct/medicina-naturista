"""Read a product's positive conditions from the same published generation as its ranking."""

from __future__ import annotations

import psycopg
from psycopg_pool import PoolTimeout

from backend.ai import db
from backend.ai.herb_evidence import evidence_counts
from backend.ai.herb_positive_repository import active_run
from backend.ai.herb_repository import catalog_snapshot
from backend.ai.index_state import INDEX_LOCK, IndexUnavailable
from backend.config import Settings
from backend.config import settings as default_settings
from backend.core.contracts import HerbLookupResult
from backend.core.operation_context import remaining_timeout

HERB_CONDITIONS_SQL = """
SELECT DISTINCT mc.id, mc.name
FROM herbs AS h
JOIN herb_positive_pairs AS hp ON hp.herb_id = h.id
JOIN medical_conditions AS mc ON mc.id = hp.medical_condition_id
WHERE hp.run_id = %s AND hp.state = 'positive' AND h.ro ILIKE %s AND h.id = %s
ORDER BY mc.name
"""


def literal_pattern(name: str) -> str:
    return name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def lookup_herb_conditions(name: str, *, settings: Settings = default_settings) -> HerbLookupResult:
    try:
        with (
            db.get_pool().connection(timeout=remaining_timeout(5.0)) as connection,
            connection.transaction(),
        ):
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            connection.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (str(max(1, int(remaining_timeout(10.0) * 1000))),),
            )
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
            species = [selected.latin] if selected.latin else []
            run_id = active_run(connection, settings)
            rows = connection.execute(
                HERB_CONDITIONS_SQL, (run_id, literal_pattern(canonical), selected.id)
            ).fetchall()
            fragments_count, documents_count = evidence_counts(connection, run_id, selected.id)
            return {
                "status": "found",
                "herbId": selected.id,
                "positiveRunId": run_id,
                "fragmentsCount": fragments_count,
                "documentsCount": documents_count,
                "herbName": canonical,
                "species": species,
                "entriesCount": len(rows),
                "conditions": [
                    {"id": condition_id, "name": condition} for condition_id, condition in rows
                ],
            }
    except (psycopg.Error, PoolTimeout):
        raise IndexUnavailable("INDEX_HERBS_UNAVAILABLE") from None
