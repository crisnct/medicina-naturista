"""Read a bounded ranking from one language's published catalog generation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import PoolTimeout

from backend.ai import db
from backend.ai.condition_repository import catalog_snapshot
from backend.ai.conditions import _normalize
from backend.ai.herb_display import romanian_herb_name
from backend.ai.herb_positive_repository import active_run
from backend.ai.index_state import INDEX_LOCK, IndexUnavailable
from backend.config import Settings
from backend.config import settings as default_settings
from backend.core.contracts import ConditionTopResult, RankedHerb
from backend.core.herb_categories import HERB_CATEGORIES, HerbCategory
from backend.core.language import current_language
from backend.core.operation_context import remaining_timeout

TOP_HERBS_SQL = """
WITH top_herbs AS (
    SELECT h.id, h.ro, h.latin, r.ranking
    FROM herbs h JOIN herb_positive_rankings r ON r.herb_id=h.id
    WHERE r.run_id=%s AND r.ranking>0
    {category_filter}
    {condition_filter}
    ORDER BY ranking DESC, id
    LIMIT %s
)
SELECT h.ro, h.latin, h.ranking,
       COALESCE(array_agg(a.name ORDER BY a.id)
                FILTER (WHERE a.id IS NOT NULL), ARRAY[]::text[])
FROM top_herbs h
LEFT JOIN herb_aliases a ON a.herb_id = h.id AND a.kind = 'ro_regional'
GROUP BY h.id, h.ro, h.latin, h.ranking
ORDER BY h.ranking DESC, h.id
"""

CONDITION_FILTER_SQL = """
AND EXISTS (
    SELECT 1 FROM herb_positive_pairs p
    WHERE p.run_id = r.run_id AND p.herb_id = h.id
      AND p.medical_condition_id = %s AND p.state = 'positive'
)
"""


def _validate_scope(count: int, category: HerbCategory | None) -> None:
    if type(count) is not int or not 1 <= count <= 10000:
        raise ValueError("INVALID_HERB_TOP_COUNT")
    if category is not None and category not in HERB_CATEGORIES:
        raise ValueError("INVALID_HERB_TOP_CATEGORY")


@contextmanager
def _ranking_connection() -> Iterator[psycopg.Connection]:
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
            row = connection.execute(
                "SELECT pg_try_advisory_xact_lock_shared(%s)", (INDEX_LOCK,)
            ).fetchone()
            if row is None or not row[0]:
                raise IndexUnavailable()
            connection.execute("SELECT set_config('lock_timeout', '1000', true)")
            yield connection
    except (psycopg.Error, PoolTimeout):
        raise IndexUnavailable("INDEX_HERBS_UNAVAILABLE") from None


def _ranking_rows(
    connection: psycopg.Connection,
    run_id: str,
    count: int,
    category: HerbCategory | None,
    condition_id: int | None = None,
) -> list[RankedHerb]:
    query = TOP_HERBS_SQL.replace(
        "{category_filter}", "AND h.category = %s" if category else ""
    ).replace("{condition_filter}", CONDITION_FILTER_SQL if condition_id is not None else "")
    if current_language() == "en":
        query = query.replace(
            "h.id, h.ro, h.latin", "h.id, COALESCE(NULLIF(h.en,''),h.latin) AS ro, h.latin", 1
        ).replace("a.kind = 'ro_regional'", "a.kind = 'en_alt'")
    parameters: list[object] = [run_id]
    if category is not None:
        parameters.append(category)
    if condition_id is not None:
        parameters.append(condition_id)
    parameters.append(count)
    rows = connection.execute(query, parameters).fetchall()
    return [
        {
            "ro": romanian_herb_name(name, latin=latin or "") if name != latin else name,
            "latin": "" if latin is None else latin,
            "ro_regional": list(dict.fromkeys(romanian_herb_name(alias) for alias in aliases)),
            "ranking": ranking,
        }
        for name, latin, ranking, aliases in rows
    ]


def list_top_herbs(
    count: int, category: HerbCategory | None = None, *, settings: Settings = default_settings
) -> list[RankedHerb]:
    _validate_scope(count, category)
    with _ranking_connection() as connection:
        return _ranking_rows(connection, active_run(connection, settings), count, category)


def list_top_herbs_for_condition(
    count: int,
    category: HerbCategory | None,
    condition: str,
    *,
    settings: Settings = default_settings,
) -> ConditionTopResult:
    _validate_scope(count, category)
    if not isinstance(condition, str) or not condition.strip() or len(condition) > 240:
        raise ValueError("INVALID_HERB_TOP_CONDITION")
    with _ranking_connection() as connection:
        run_id = active_run(connection, settings)
        dictionary = catalog_snapshot(connection).dictionary
        matches = dictionary.exact_matches(condition)
        if not matches:
            resolved = dictionary.resolve(condition)
            # Approximate spellings and multiple conditions require an explicit choice.
            # Extra qualifiers such as "la copii" must never broaden a disease filter.
            if resolved.segments and all(
                segment.conditions
                and (
                    segment.whole_condition
                    or _normalize(segment.remainder) in {"", "si", "sau", "ori"}
                )
                for segment in resolved.segments
            ):
                choices = list(dict.fromkeys(item.display_name for item in resolved.conditions))[
                    :10
                ]
                if choices:
                    return {"status": "ambiguous", "choices": choices}
            return {"status": "not_found"}
        if len(matches) > 1:
            return {"status": "ambiguous", "choices": [item.display_name for item in matches[:10]]}
        row = connection.execute(
            "SELECT id, "
            + ("en" if current_language() == "en" else "name")
            + " FROM medical_conditions WHERE name = %s",
            (matches[0].name,),
        ).fetchone()
        if row is None:
            raise IndexUnavailable("INDEX_RESYNC_REQUIRED")
        condition_id, name = row
        return {
            "status": "found",
            "condition": {"id": condition_id, "name": name},
            "positiveRunId": run_id,
            "herbs": _ranking_rows(connection, run_id, count, category, condition_id),
        }
