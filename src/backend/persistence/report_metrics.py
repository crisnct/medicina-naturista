"""Short, bounded transactions for report measurements."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from psycopg_pool import ConnectionPool

from backend.core.report_metrics import (
    BUDGET_PERCENTILE,
    RECENT_BATCH_SAMPLES,
    ReportBatchUsage,
    ReportDurationEstimate,
    ReportMetrics,
    ReportOutputRecommendation,
    estimate_duration_from_totals,
    recommend_tokens,
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

    # Only batches of the same model and effort count: another effort says nothing about how
    # much a model reasons. The answer budget is what the report panel's output field sets.
    def recommend_output_tokens(
        self, model: ReportModel, effort: ReportEffort | None = None
    ) -> ReportOutputRecommendation:
        return self._recommend("answer_tokens", model, effort)

    # The thinking budget the batches of this model and effort have been seen to need.
    def recommend_thinking_tokens(
        self, model: ReportModel, effort: ReportEffort | None = None
    ) -> ReportOutputRecommendation:
        return self._recommend("reasoning_tokens", model, effort)

    def _recommend(
        self, column: str, model: ReportModel, effort: ReportEffort | None
    ) -> ReportOutputRecommendation:
        assert column in ("answer_tokens", "reasoning_tokens")
        with self.pool().connection(timeout=1.0) as connection, connection.transaction():
            connection.execute("SELECT set_config('statement_timeout', '2000', true)")
            connection.execute("SELECT set_config('lock_timeout', '500', true)")
            row = connection.execute(
                f"SELECT COUNT(value), percentile_cont(%s) WITHIN GROUP (ORDER BY value) "
                f"FROM (SELECT {column} AS value FROM report_batch_usage "
                "WHERE ai_model = %s AND ai_effort IS NOT DISTINCT FROM %s "
                f"AND {column} IS NOT NULL ORDER BY id DESC LIMIT %s) AS recent",
                (BUDGET_PERCENTILE, model, effort, RECENT_BATCH_SAMPLES),
            ).fetchone()
        assert row is not None
        return recommend_tokens(int(row[0]), None if row[1] is None else float(row[1]))

    # Published and failed reports alike, so the batches cut off by their limit are measured.
    def record_batch_usage(
        self,
        model: ReportModel,
        effort: ReportEffort | None,
        batches: tuple[ReportBatchUsage, ...],
    ) -> None:
        if not batches:
            return
        with self.pool().connection(timeout=1.0) as connection, connection.transaction():
            connection.execute("SELECT set_config('statement_timeout', '2000', true)")
            connection.execute("SELECT set_config('lock_timeout', '500', true)")
            with connection.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO report_batch_usage "
                    "(ai_model, ai_effort, reasoning_tokens, answer_tokens, truncated) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    [
                        (
                            model,
                            effort,
                            batch.reasoning_tokens,
                            batch.answer_tokens,
                            batch.truncated,
                        )
                        for batch in batches
                    ],
                )

    def __call__(self, metrics: ReportMetrics) -> int:
        with self.pool().connection(timeout=1.0) as connection, connection.transaction():
            connection.execute("SELECT set_config('statement_timeout', '2000', true)")
            connection.execute("SELECT set_config('lock_timeout', '500', true)")
            row = connection.execute(
                "INSERT INTO report_generation_metrics "
                "(medical_condition, min_score, characters, ai_model, ai_effort, duration, "
                "max_batch_output_tokens) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (
                    metrics.medical_condition,
                    metrics.min_score,
                    metrics.characters,
                    metrics.ai_model,
                    metrics.ai_effort,
                    metrics.duration,
                    metrics.max_batch_output_tokens,
                ),
            ).fetchone()
            assert row is not None
            return row[0]
