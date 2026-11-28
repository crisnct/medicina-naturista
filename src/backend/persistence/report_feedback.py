"""One short transaction per admin rating of a report, and the example it may keep."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from backend.core.report_feedback import ReportExample, ReportFeedback


@dataclass(frozen=True)
class PostgresReportFeedbackRepository:
    pool: Callable[[], ConnectionPool]

    # The latest rating replaces the earlier one; comment categories are cleared so the next
    # evaluation of the search formula classifies the new comment. Without an example, an
    # earlier example of the same report is deleted.
    def __call__(self, feedback: ReportFeedback, example: ReportExample | None) -> None:
        with self.pool().connection(timeout=1.0) as connection, connection.transaction():
            connection.execute("SELECT set_config('statement_timeout', '2000', true)")
            connection.execute("SELECT set_config('lock_timeout', '500', true)")
            connection.execute(
                "INSERT INTO report_feedback "
                "(report_id, language, score, comment, search_formula, rrf_k, signals, min_score) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (report_id) DO UPDATE SET "
                "score = EXCLUDED.score, comment = EXCLUDED.comment, comment_categories = NULL, "
                "updated_utc = now()",
                (
                    feedback.report_id,
                    feedback.language,
                    feedback.score,
                    feedback.comment,
                    feedback.search_formula,
                    feedback.rrf_k,
                    feedback.signals,
                    feedback.min_score,
                ),
            )
            if example is None:
                connection.execute(
                    "DELETE FROM report_examples WHERE report_id = %s", (feedback.report_id,)
                )
                return
            connection.execute(
                "INSERT INTO report_examples "
                "(report_id, language, condition_keys, sections, ai_model) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (report_id) DO UPDATE SET "
                "condition_keys = EXCLUDED.condition_keys, sections = EXCLUDED.sections, "
                "ai_model = EXCLUDED.ai_model",
                (
                    example.report_id,
                    example.language,
                    list(example.condition_keys),
                    Jsonb(example.sections),
                    example.ai_model,
                ),
            )
