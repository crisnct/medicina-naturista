"""Persist local warning projections and publish compatible positive/caution generations atomically."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Literal
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from backend.ai import db
from backend.ai.herb_association_classification import group_fragment_works, semantic_config
from backend.ai.herb_association_rules import content_hash
from backend.ai.herb_association_scope import LocalConditionScope
from backend.ai.herb_caution_projection import (
    PROJECTION_VERSION,
    CautionDecision,
    combine_projections,
    corroborate_projection,
    decode_projection,
    list_prohibition,
    local_projection,
)
from backend.ai.herb_positive_repository import (
    PositiveRepository,
    active_key,
    active_run,
    snapshot,
)
from backend.ai.herb_positive_repository import (
    assert_integrity as assert_positive_integrity,
)
from backend.ai.herb_positive_repository import (
    unavailable as positive_unavailable,
)
from backend.config import Settings
from backend.core.errors import ApplicationError
from backend.core.language import current_language
from backend.core.operation_context import checkpoint
from backend.core.texts import tr

CautionStatus = Literal["ready", "partial", "not_ready", "stale"]


def unavailable(stale: bool = False) -> ApplicationError:
    return ApplicationError(
        "CAUTION_RANKING_STALE" if stale else "CAUTION_RANKING_NOT_READY",
        tr("errors.caution_ranking_stale" if stale else "errors.caution_ranking_not_ready"),
        503,
    )


def schema_available(connection: Connection) -> bool:
    row = connection.execute("SELECT to_regclass('herb_caution_runs')").fetchone()
    return bool(row and row[0])


def evidence_rows(connection: Connection, run_id: str) -> list:
    return connection.execute(
        "SELECT identity,chunk_id,herb_id,medical_condition_id,unit_start,unit_end,"
        "mention_start,mention_end,warning_kind,has_recommendation,origin,rule_code,"
        "cache_key,provenance FROM herb_caution_evidence WHERE run_id=%s ORDER BY identity",
        (run_id,),
    ).fetchall()


PAIR_SELECT = """
SELECT run_id,herb_id,medical_condition_id,
count(*) FILTER(WHERE warning_kind='prohibition')::int,
count(*) FILTER(WHERE warning_kind='precaution')::int,
count(*) FILTER(WHERE warning_kind='none')::int,
count(*) FILTER(WHERE warning_kind='unknown')::int,
bool_or(has_recommendation)
FROM herb_caution_evidence WHERE run_id=%s GROUP BY run_id,herb_id,medical_condition_id
"""
RANKING_SELECT = """
SELECT %s::uuid,h.id,
count(p.medical_condition_id) FILTER(WHERE p.prohibition_count>0 OR p.precaution_count>0)::int,
count(p.medical_condition_id) FILTER(WHERE p.prohibition_count>0)::int
FROM herbs h LEFT JOIN herb_caution_pairs p ON p.herb_id=h.id AND p.run_id=%s GROUP BY h.id
"""


def assert_integrity(
    connection: Connection,
    run_id: str,
    positive_run_id: str,
    expected: int,
    unknown_count: int,
    digest: str,
) -> None:
    rows = evidence_rows(connection, run_id)
    if (
        len(rows) != expected
        or content_hash(rows) != digest
        or sum(row[8] == "unknown" for row in rows) != unknown_count
    ):
        raise ValueError("CAUTION_INCOMPLETE_EVIDENCE")
    identities = connection.execute(
        "SELECT identity,chunk_id,herb_id,medical_condition_id,unit_start,unit_end,"
        "mention_start,mention_end FROM herb_positive_evidence WHERE run_id=%s ORDER BY identity",
        (positive_run_id,),
    ).fetchall()
    if [row[:8] for row in rows] != identities:
        raise ValueError("CAUTION_SOURCE_MISMATCH")
    for expected_sql, parameters, actual_sql in (
        (PAIR_SELECT, (run_id,), "SELECT * FROM herb_caution_pairs WHERE run_id=%s"),
        (RANKING_SELECT, (run_id, run_id), "SELECT * FROM herb_caution_rankings WHERE run_id=%s"),
    ):
        mismatch = connection.execute(
            "WITH expected AS (" + expected_sql + "), actual AS (" + actual_sql + ") "
            "SELECT EXISTS((SELECT * FROM expected EXCEPT SELECT * FROM actual) UNION ALL "
            "(SELECT * FROM actual EXCEPT SELECT * FROM expected))",
            (*parameters, run_id),
        ).fetchone()
        if mismatch is None or mismatch[0]:
            raise ValueError("CAUTION_AGGREGATION_MISMATCH")


_verified_cautions: set[tuple[object, ...]] = set()


def clear_verified_cautions() -> None:
    _verified_cautions.clear()


# The positive reader validates its own manifest first; caution cannot change that fingerprint.
def active_caution_run(
    connection: Connection, positive_run_id: str
) -> tuple[str | None, CautionStatus]:
    if not schema_available(connection):
        return None, "not_ready"
    row = connection.execute(
        "SELECT run_id::text,positive_run_id::text,status,manifest,projection_version,"
        "expected_count,unknown_count,evidence_hash FROM herb_caution_runs WHERE is_active AND language=%s",
        (current_language(),),
    ).fetchone()
    if row is None:
        return None, "not_ready"
    positive = connection.execute(
        "SELECT manifest FROM herb_positive_runs WHERE run_id=%s", (positive_run_id,)
    ).fetchone()
    if (
        row[1] != positive_run_id
        or row[2] != "ready"
        or row[4] != PROJECTION_VERSION
        or positive is None
        or row[3] != positive[0]
    ):
        return None, "stale"
    # Integrity re-reads every caution evidence row, so it runs once per published run; see
    # herb_run_cache for the accepted trade-off against out-of-band table edits.
    identity = (current_language(), *row[:2], *row[5:8])
    if identity not in _verified_cautions:
        try:
            assert_integrity(connection, row[0], positive_run_id, row[5], row[6], row[7])
        except ValueError:
            return None, "stale"
        _verified_cautions.add(identity)
    return row[0], "ready"


@dataclass(frozen=True)
class CautionRepository:
    pool: Callable[[], ConnectionPool] = db.get_pool

    def save_cache(self, entries: dict[str, CautionDecision]) -> None:
        if not entries:
            return
        with PositiveRepository(self.pool).transaction(write=True) as connection:
            if not schema_available(connection):
                raise unavailable()
            with connection.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO herb_caution_cache(cache_key,projection_version,decision) "
                    "VALUES(%s,%s,%s) ON CONFLICT(cache_key,projection_version) DO UPDATE "
                    "SET decision=EXCLUDED.decision "
                    "WHERE herb_caution_cache.decision->>'warning_kind'='unknown'",
                    [
                        (key, PROJECTION_VERSION, Jsonb(asdict(value)))
                        for key, value in entries.items()
                    ],
                )

    def prepared_for_positive(self, positive_run_id: str) -> str | None:
        with PositiveRepository(self.pool).transaction() as connection:
            if not schema_available(connection):
                raise unavailable()
            row = connection.execute(
                "SELECT run_id::text FROM herb_caution_runs WHERE positive_run_id=%s "
                "AND status='ready' AND projection_version=%s ORDER BY created_at DESC LIMIT 1",
                (positive_run_id, PROJECTION_VERSION),
            ).fetchone()
            return row[0] if row else None

    # Reconstruct only what the indexed text and existing caches can establish without inference.
    def prepare(self, positive_run_id: str, settings: Settings) -> dict[str, Any]:
        UUID(positive_run_id)
        positive_repository = PositiveRepository(self.pool)
        data = positive_repository.read_snapshot()
        scope_catalog = LocalConditionScope(data.conditions, data.condition_synonyms)
        local = {
            (
                group.work[0].passage.chunk_id,
                group.work[1].herb_id,
                group.work[1].condition_id,
            ): combine_projections(
                [
                    local_projection(group.originals),
                    list_prohibition(
                        group.work,
                        scope_catalog=scope_catalog,
                        condition_name=data.conditions[group.work[1].condition_id],
                        condition_synonyms=data.condition_synonyms.get(
                            group.work[1].condition_id, ()
                        ),
                    ),
                ]
            )
            for group in group_fragment_works(data.works, data.conditions)
        }
        with positive_repository.transaction() as connection:
            if not schema_available(connection):
                raise unavailable()
            source = connection.execute(
                "SELECT status,manifest,semantic,model_digest,expected_count,evidence_hash "
                "FROM herb_positive_runs WHERE run_id=%s",
                (positive_run_id,),
            ).fetchone()
            if source is None or source[0] != "ready":
                raise positive_unavailable()
            if source[1] != data.manifest or source[2] != semantic_config(settings):
                raise positive_unavailable(True)
            assert_positive_integrity(connection, positive_run_id, source[4], source[5])
            previous = connection.execute(
                "SELECT run_id::text FROM herb_caution_runs WHERE is_active AND language=%s",
                (current_language(),),
            ).fetchone()
            records = connection.execute(
                "SELECT e.identity,e.chunk_id,e.herb_id,e.medical_condition_id,e.unit_start,"
                "e.unit_end,e.mention_start,e.mention_end,e.label,e.origin,e.rule_code,"
                "e.cache_key,e.provenance,p.decision,c.decision,ch.char_count "
                "FROM herb_positive_evidence e LEFT JOIN herb_positive_cache p USING(cache_key) "
                "LEFT JOIN herb_caution_cache c ON c.cache_key=e.cache_key AND c.projection_version=%s "
                "JOIN chunks ch ON ch.chunk_id=e.chunk_id WHERE e.run_id=%s ORDER BY e.identity",
                (PROJECTION_VERSION, positive_run_id),
            ).fetchall()
        projected = []
        unknown = 0
        for row in records:
            checkpoint()
            base = CautionDecision(
                "unknown", row[8] in {"positive", "mixed"}, row[9], "historical_unknown"
            )
            if row[14] is not None:
                base = decode_projection(row[14])
                if any(b > row[15] for _, b in base.quotes):
                    raise ValueError("CAUTION_INVALID_CACHE")
            elif row[13] is not None and row[13].get("label") == "caution":
                # This is only a historical model claim; scoped source support is checked below.
                base = CautionDecision("prohibition", False, "model", "existing_model_caution")
            decision = corroborate_projection(
                base,
                local.get(
                    tuple(row[1:4]),
                    CautionDecision("unknown", False, "rule", "historical_unknown"),
                ),
            )
            recommended = decision.has_recommendation or row[8] in {"positive", "mixed"}
            unknown += decision.warning_kind == "unknown"
            provenance = {**row[12], "warning_quotes": decision.quotes}
            projected.append(
                (
                    *row[:8],
                    decision.warning_kind,
                    recommended,
                    decision.origin,
                    decision.rule_code,
                    row[11],
                    Jsonb(provenance),
                )
            )
        run_id = str(uuid4())
        with positive_repository.transaction(write=True) as connection:
            connection.execute(
                "LOCK TABLE documents,chunks,herbs,herb_aliases,medical_conditions,medical_condition_synonyms IN SHARE MODE"
            )
            if snapshot(connection).manifest != data.manifest:
                raise unavailable(True)
            assert_positive_integrity(connection, positive_run_id, source[4], source[5])
            connection.execute(
                "INSERT INTO herb_caution_runs(run_id,positive_run_id,status,manifest,projection_version,"
                "model_digest,expected_active,expected_count,unknown_count) VALUES(%s,%s,'preparing',%s,%s,%s,%s,%s,%s)",
                (
                    run_id,
                    positive_run_id,
                    Jsonb(data.manifest),
                    PROJECTION_VERSION,
                    source[3],
                    previous[0] if previous else None,
                    len(records),
                    unknown,
                ),
            )
            with connection.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO herb_caution_evidence(run_id,identity,chunk_id,herb_id,medical_condition_id,"
                    "unit_start,unit_end,mention_start,mention_end,warning_kind,has_recommendation,"
                    "origin,rule_code,cache_key,provenance) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    [(run_id, *row) for row in projected],
                )
            connection.execute("INSERT INTO herb_caution_pairs " + PAIR_SELECT, (run_id,))
            connection.execute(
                "INSERT INTO herb_caution_rankings " + RANKING_SELECT, (run_id, run_id)
            )
            digest = content_hash(evidence_rows(connection, run_id))
            assert_integrity(connection, run_id, positive_run_id, len(records), unknown, digest)
            connection.execute(
                "UPDATE herb_caution_runs SET status='ready',evidence_hash=%s WHERE run_id=%s",
                (digest, run_id),
            )
        return {
            "run_id": run_id,
            "positive_run_id": positive_run_id,
            "status": "ready",
            "evidence_count": len(records),
            "unknown_count": unknown,
            "ai_requests_sent_total": 0,
        }

    # This is the original positive publication gate plus the caution pointer in the same transaction.
    def publish(
        self, run_id: str, settings: Settings, *, positive_digest: str | None = None
    ) -> None:
        UUID(run_id)
        with PositiveRepository(self.pool).transaction(write=True) as connection:
            connection.execute(
                "LOCK TABLE documents,chunks,herbs,herb_aliases,medical_conditions,medical_condition_synonyms,sync_metadata IN SHARE MODE"
            )
            row = connection.execute(
                "SELECT positive_run_id::text,status,manifest,projection_version,expected_active::text,"
                "expected_count,unknown_count,evidence_hash FROM herb_caution_runs WHERE run_id=%s FOR UPDATE",
                (run_id,),
            ).fetchone()
            if row is None or row[1] != "ready":
                raise unavailable()
            positive = connection.execute(
                "SELECT status,manifest,semantic,expected_active,expected_count,evidence_hash,model_digest "
                "FROM herb_positive_runs WHERE run_id=%s FOR UPDATE",
                (row[0],),
            ).fetchone()
            data = snapshot(connection)
            if positive is None or positive[0] != "ready":
                raise positive_unavailable()
            if positive[1] != data.manifest or positive[2] != semantic_config(settings):
                raise positive_unavailable(True)
            if row[2] != positive[1] or row[3] != PROJECTION_VERSION:
                raise unavailable(True)
            if positive_digest is not None and positive[6] != positive_digest:
                raise ValueError("POSITIVE_MODEL_CHANGED")
            assert_positive_integrity(connection, row[0], positive[4], positive[5])
            assert_integrity(connection, run_id, row[0], row[5], row[6], row[7])
            if data.active != row[0]:
                if positive_digest is None:
                    raise ValueError("CAUTION_PUBLICATION_CONFLICT")
                if data.active != positive[3]:
                    raise ValueError("POSITIVE_PUBLICATION_CONFLICT")
            current = connection.execute(
                "SELECT run_id::text FROM herb_caution_runs WHERE is_active AND language=%s",
                (current_language(),),
            ).fetchone()
            current_id = current[0] if current else None
            if current_id == run_id and data.active == row[0]:
                return
            if current_id != row[4]:
                raise ValueError("CAUTION_PUBLICATION_CONFLICT")
            connection.execute(
                "UPDATE herb_caution_runs SET is_active=false WHERE is_active AND language=%s",
                (current_language(),),
            )
            connection.execute(
                "UPDATE herb_caution_runs SET is_active=true WHERE run_id=%s", (run_id,)
            )
            if data.active != row[0]:
                connection.execute(
                    "INSERT INTO sync_metadata(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
                    (active_key(), row[0]),
                )

    def active_positive(self, settings: Settings) -> str:
        with PositiveRepository(self.pool).transaction() as connection:
            return active_run(connection, settings)
