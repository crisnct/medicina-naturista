"""Read a bounded catalog ranking with regional Romanian names."""

from __future__ import annotations

import psycopg
from psycopg_pool import PoolTimeout

from backend.ai import db
from backend.ai.herb_display import romanian_herb_name
from backend.ai.index_state import INDEX_LOCK, IndexUnavailable
from backend.core.contracts import RankedHerb

TOP_HERBS_SQL = """
WITH top_herbs AS (
    SELECT id, ro, latin, ranking
    FROM herbs
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


def list_top_herbs(count: int) -> list[RankedHerb]:
    if type(count) is not int or not 1 <= count <= 10000:
        raise ValueError("INVALID_HERB_TOP_COUNT")
    try:
        with db.get_pool().connection() as connection, connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            row = connection.execute(
                "SELECT pg_try_advisory_xact_lock_shared(%s)", (INDEX_LOCK,)
            ).fetchone()
            if row is None or not row[0]:
                raise IndexUnavailable()
            rows = connection.execute(TOP_HERBS_SQL, (count,)).fetchall()
    except (psycopg.Error, PoolTimeout):
        raise IndexUnavailable("INDEX_HERBS_UNAVAILABLE") from None
    return [
        {
            "ro": romanian_herb_name(name) if name != latin else name,
            "latin": latin,
            "ro_regional": list(dict.fromkeys(romanian_herb_name(alias) for alias in aliases)),
            "ranking": ranking,
        }
        for name, latin, ranking, aliases in rows
    ]
