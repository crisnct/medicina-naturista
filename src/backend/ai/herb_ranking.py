"""Read a bounded catalog ranking with regional Romanian names."""

from __future__ import annotations

import psycopg
from psycopg_pool import PoolTimeout

from backend.ai import db
from backend.ai.herb_display import romanian_herb_name
from backend.ai.herb_positive_repository import active_run
from backend.ai.index_state import INDEX_LOCK, IndexUnavailable
from backend.config import Settings
from backend.config import settings as default_settings
from backend.core.contracts import RankedHerb
from backend.core.herb_categories import HERB_CATEGORIES, HerbCategory
from backend.core.operation_context import remaining_timeout

TOP_HERBS_SQL = """
WITH top_herbs AS (
    SELECT h.id, h.ro, h.latin, r.ranking
    FROM herbs h JOIN herb_positive_rankings r ON r.herb_id=h.id
    WHERE r.run_id=%s AND r.ranking>0
    {category_filter}
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


def list_top_herbs(
    count: int, category: HerbCategory | None = None, *, settings: Settings = default_settings
) -> list[RankedHerb]:
    if type(count) is not int or not 1 <= count <= 10000:
        raise ValueError("INVALID_HERB_TOP_COUNT")
    if category is not None and category not in HERB_CATEGORIES:
        raise ValueError("INVALID_HERB_TOP_CATEGORY")
    query = TOP_HERBS_SQL.replace("{category_filter}", "AND h.category = %s" if category else "")
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
            run_id = active_run(connection, settings)
            parameters = (run_id, category, count) if category else (run_id, count)
            rows = connection.execute(query, parameters).fetchall()
    except (psycopg.Error, PoolTimeout):
        raise IndexUnavailable("INDEX_HERBS_UNAVAILABLE") from None
    return [
        {
            "ro": romanian_herb_name(name) if name != latin else name,
            "latin": "" if latin is None else latin,
            "ro_regional": list(dict.fromkeys(romanian_herb_name(alias) for alias in aliases)),
            "ranking": ranking,
        }
        for name, latin, ranking, aliases in rows
    ]
