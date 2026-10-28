"""Read a product's positive conditions from the same published generation as its ranking."""

from __future__ import annotations

import psycopg
from psycopg_pool import PoolTimeout

from backend.ai import db
from backend.ai.herb_caution_repository import active_caution_run
from backend.ai.herb_display import romanian_herb_name
from backend.ai.herb_evidence import evidence_counts
from backend.ai.herb_positive_repository import active_run
from backend.ai.herb_product_safety_repository import safety_metadata
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
ORDER BY mc.name, mc.id
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
                return {
                    "status": "ambiguous",
                    "choices": sorted(
                        romanian_herb_name(herb.ro, latin=herb.latin)
                        + (f" ({herb.latin})" if herb.latin else "")
                        for herb in matches
                    ),
                }
            selected = matches[0]
            canonical = selected.ro
            species = [selected.latin] if selected.latin else []
            run_id = active_run(connection, settings)
            rows = connection.execute(
                HERB_CONDITIONS_SQL, (run_id, literal_pattern(canonical), selected.id)
            ).fetchall()
            fragments_count, documents_count = evidence_counts(connection, run_id, selected.id)
            result: HerbLookupResult = {
                "status": "found",
                "herbId": selected.id,
                "positiveRunId": run_id,
                "fragmentsCount": fragments_count,
                "documentsCount": documents_count,
                "herbName": romanian_herb_name(canonical, latin=selected.latin),
                "species": species,
                "entriesCount": len(rows),
                "conditions": [
                    {"id": condition_id, "name": condition} for condition_id, condition in rows
                ],
            }
            caution_run, caution_status = active_caution_run(connection, run_id)
            result.update(
                {
                    "cautionRunId": caution_run,
                    "contraindicationsStatus": caution_status,
                    "contraindicationsCount": None,
                    "contraindications": [],
                    "contraindicationFragmentsCount": 0,
                    "contraindicationDocumentsCount": 0,
                }
            )
            if caution_run is not None:
                contraindications = connection.execute(
                    "SELECT mc.id,mc.name,p.has_recommendation OR COALESCE("
                    "hp.positive_count>0 OR hp.mixed_count>0,false) "
                    "FROM herb_caution_pairs p JOIN medical_conditions mc ON mc.id=p.medical_condition_id "
                    "LEFT JOIN herb_positive_pairs hp ON hp.run_id=%s AND hp.herb_id=p.herb_id "
                    "AND hp.medical_condition_id=p.medical_condition_id "
                    "WHERE p.run_id=%s AND p.herb_id=%s AND p.prohibition_count>0 ORDER BY mc.name,mc.id",
                    (run_id, caution_run, selected.id),
                ).fetchall()
                unknown = connection.execute(
                    "SELECT COALESCE(sum(unknown_count),0) FROM herb_caution_pairs WHERE run_id=%s AND herb_id=%s",
                    (caution_run, selected.id),
                ).fetchone()
                negative_fragments, negative_documents = evidence_counts(
                    connection, caution_run, selected.id, evidence_kind="contraindication"
                )
                result.update(
                    {
                        "contraindicationsStatus": "partial" if unknown and unknown[0] else "ready",
                        "contraindicationsCount": len(contraindications),
                        "contraindications": [
                            {"id": identifier, "name": condition, "hasRecommendation": recommended}
                            for identifier, condition, recommended in contraindications
                        ],
                        "contraindicationFragmentsCount": negative_fragments,
                        "contraindicationDocumentsCount": negative_documents,
                    }
                )
            result.update(safety_metadata(connection, selected.id, settings))
            return result
    except (psycopg.Error, PoolTimeout):
        raise IndexUnavailable("INDEX_HERBS_UNAVAILABLE") from None
