"""Short, bounded transactions for published report measurements."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from psycopg_pool import ConnectionPool

from backend.core.report_metrics import (
    ReportDurationEstimate,
    ReportMetrics,
    estimate_duration_from_totals,
)
from backend.core.report_models import ReportEffort, ReportModel


@dataclass(frozen=True)
class PostgresReportMetricsRepository:
    pool: Callable[[], ConnectionPool]

    # Samples of the same effort are preferred; without any, the model's samples stand in.
    def estimate_duration(
        self, model: ReportModel, characters: int, effort: ReportEffort | None = None
    ) -> ReportDurationEstimate:
        query = (
            "SELECT COUNT(*), "
            "COALESCE(SUM(characters::numeric * duration), 0), "
            "COALESCE(SUM(characters::numeric * characters), 0) "
            "FROM report_generation_metrics WHERE ai_model = %s"
        )
        with self.pool().connection(timeout=1.0) as connection, connection.transaction():
            connection.execute("SELECT set_config('statement_timeout', '2000', true)")
            connection.execute("SELECT set_config('lock_timeout', '500', true)")
            row = None
            if effort is not None:
                row = connection.execute(query + " AND ai_effort = %s", (model, effort)).fetchone()
            if row is None or int(row[0]) == 0:
                row = connection.execute(query, (model,)).fetchone()
        assert row is not None
        return estimate_duration_from_totals(characters, int(row[0]), int(row[1]), int(row[2]))

    def __call__(self, metrics: ReportMetrics) -> int:
        with self.pool().connection(timeout=1.0) as connection, connection.transaction():
            connection.execute("SELECT set_config('statement_timeout', '2000', true)")
            connection.execute("SELECT set_config('lock_timeout', '500', true)")
            row = connection.execute(
                "INSERT INTO report_generation_metrics "
                "(medical_condition, min_score, characters, ai_model, ai_effort, duration) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (
                    metrics.medical_condition,
                    metrics.min_score,
                    metrics.characters,
                    metrics.ai_model,
                    metrics.ai_effort,
                    metrics.duration,
                ),
            ).fetchone()
            assert row is not None
            return row[0]
