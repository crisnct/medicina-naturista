"""Read-only snapshot of the multilevel knowledge runs for the learning control, in one short
transaction; it never writes and never waits for the index or build locks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import psycopg
from psycopg_pool import ConnectionPool

from backend.ai.index_state import INDEX_LOCK
from backend.ai.knowledge_repository import KNOWLEDGE_LOCK, RUN_COLUMNS, run_from_row
from backend.core.errors import ApplicationError
from backend.core.learning import IMPLEMENTED_LEVELS, LearningSnapshot
from backend.core.texts import tr

# Built once from constants: no value ever enters the statement text.
_LATEST_SQL = (
    "SELECT DISTINCT ON (language, level) "
    + RUN_COLUMNS
    + " FROM knowledge_runs WHERE NOT counters ? 'sample' "
    "ORDER BY language, level, created_utc DESC, run_id DESC"
)
_ACTIVE_SQL = "SELECT " + RUN_COLUMNS + " FROM knowledge_runs WHERE is_active"
# A bigint advisory key shows in pg_locks as its high (classid) and low (objid) halves.
_BUILD_LOCK_SQL = (
    "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND granted "
    "AND classid::bigint = %s AND objid::bigint = %s AND objsubid = 1)"
)
_SPEED_SQL = (
    "SELECT (counters->>'seconds_per_unit')::float8 FROM knowledge_runs "
    "WHERE level = %s AND model = %s AND status = 'ready' AND counters ? 'seconds_per_unit' "
    "ORDER BY finished_utc DESC NULLS LAST LIMIT 1"
)


@dataclass(frozen=True)
class PostgresLearningSnapshot:
    pool: Callable[[], ConnectionPool]
    # The configured model of each level, for the speed of its previous run.
    models: Mapping[int, str]

    # Any database failure, a schema without migration 047 included, is one "unavailable" for the
    # admin; the log has its type.
    def __call__(self) -> LearningSnapshot:
        try:
            return self._read()
        except psycopg.Error as exc:
            raise ApplicationError(
                "KNOWLEDGE_STATE_UNAVAILABLE", tr("errors.knowledge_state_unavailable"), 503
            ) from exc

    def _read(self) -> LearningSnapshot:
        with self.pool().connection(timeout=1.0) as connection, connection.transaction():
            connection.execute("SELECT set_config('statement_timeout', '3000', true)")
            shared = connection.execute(
                "SELECT pg_try_advisory_xact_lock_shared(%s)", (INDEX_LOCK,)
            ).fetchone()
            held = connection.execute(
                _BUILD_LOCK_SQL, (KNOWLEDGE_LOCK >> 32, KNOWLEDGE_LOCK & 0xFFFFFFFF)
            ).fetchone()
            latest = tuple(run_from_row(row) for row in connection.execute(_LATEST_SQL))
            active = tuple(run_from_row(row) for row in connection.execute(_ACTIVE_SQL))
            fragments = {
                str(language): int(count)
                for language, count in connection.execute(
                    "SELECT language, count(DISTINCT text_sha256) FROM chunks GROUP BY language"
                )
            }
            generation = connection.execute(
                "SELECT value FROM sync_metadata WHERE key = 'index_generation'"
            ).fetchone()
            speeds: dict[int, float] = {}
            for level in IMPLEMENTED_LEVELS:
                row = connection.execute(_SPEED_SQL, (level, self.models[level])).fetchone()
                if row and row[0] and row[0] > 0:
                    speeds[level] = float(row[0])
        return LearningSnapshot(
            latest,
            active,
            fragments,
            str(generation[0]) if generation else None,
            not (shared and shared[0]),
            bool(held and held[0]),
            speeds,
        )
