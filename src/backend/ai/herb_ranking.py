"""Read a bounded ranking from one language's published catalog generation."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import PoolTimeout

from backend.ai import db
from backend.ai.conditions import _normalize
from backend.ai.herb_display import romanian_herb_name, warm_up_names
from backend.ai.herb_run_cache import (
    active_run,
    condition_dictionary,
    condition_ids,
    published_state,
)
from backend.ai.index_state import INDEX_LOCK, IndexUnavailable
from backend.config import Settings
from backend.config import settings as default_settings
from backend.core.contracts import ConditionTopResult, RankedHerb
from backend.core.errors import ApplicationError
from backend.core.herb_categories import HERB_CATEGORIES, HerbCategory
from backend.core.language import LANGUAGES, current_language, language_scope
from backend.core.operation_context import remaining_timeout
from backend.core.score_formula import compile_formula

logger = logging.getLogger("naturist.herbs")

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

# L1, L2 and L3 are precomputed per condition, so a request reads one index range and sorts it.
CONDITION_SCORES_SQL = """
SELECT s.herb_id, s.title_fragments, s.text_fragments, s.conditions_count
FROM herb_condition_scores s {category_join}
WHERE s.positive_run_id=%s AND s.medical_condition_id=%s
"""

HERB_DETAILS_SQL = """
SELECT h.id, h.ro, h.latin,
       COALESCE(array_agg(a.name ORDER BY a.id)
                FILTER (WHERE a.id IS NOT NULL), ARRAY[]::text[])
FROM herbs h
LEFT JOIN herb_aliases a ON a.herb_id = h.id AND a.kind = 'ro_regional'
WHERE h.id = ANY(%s)
GROUP BY h.id, h.ro, h.latin
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
            # One round trip: the shared advisory lock and both timeouts.
            row = connection.execute(
                "SELECT pg_try_advisory_xact_lock_shared(%s), "
                "set_config('statement_timeout', %s, true), set_config('lock_timeout', '1000', true)",
                (INDEX_LOCK, str(max(1, int(remaining_timeout(10.0) * 1000)))),
            ).fetchone()
            if row is None or not row[0]:
                raise IndexUnavailable()
            yield connection
    except (psycopg.Error, PoolTimeout):
        raise IndexUnavailable("INDEX_HERBS_UNAVAILABLE") from None


def _ranked(rows: list) -> list[RankedHerb]:
    return [
        {
            "ro": romanian_herb_name(name, latin=latin or "") if name != latin else name,
            "latin": "" if latin is None else latin,
            "ro_regional": list(dict.fromkeys(romanian_herb_name(alias) for alias in aliases)),
            "ranking": ranking,
        }
        for name, latin, ranking, aliases in rows
    ]


def _english(query: str) -> str:
    if current_language() != "en":
        return query
    return query.replace(
        "h.id, h.ro, h.latin", "h.id, COALESCE(NULLIF(h.en,''),h.latin) AS ro, h.latin", 1
    ).replace("a.kind = 'ro_regional'", "a.kind = 'en_alt'")


def _ranking_rows(
    connection: psycopg.Connection, run_id: str, count: int, category: HerbCategory | None
) -> list[RankedHerb]:
    query = _english(
        TOP_HERBS_SQL.replace("{category_filter}", "AND h.category = %s" if category else "")
    )
    parameters: list[object] = [run_id]
    if category is not None:
        parameters.append(category)
    parameters.append(count)
    rows = connection.execute(query, parameters).fetchall()
    return _ranked(rows)


# Orders eligible products by the operator's formula, then by L3 and ID so ties stay stable.
def _condition_rows(
    connection: psycopg.Connection,
    run_id: str,
    count: int,
    category: HerbCategory | None,
    condition_id: int,
    formula: str,
) -> list[RankedHerb]:
    query = CONDITION_SCORES_SQL.replace(
        "{category_join}",
        "JOIN herbs h ON h.id = s.herb_id AND h.category = %s" if category else "",
    )
    parameters: list[object] = [category] if category is not None else []
    scores = connection.execute(query, [*parameters, run_id, condition_id]).fetchall()
    if not scores:
        # An absent marker means the scores were never computed; an empty set is a valid answer.
        if (
            connection.execute(
                "SELECT 1 FROM herb_condition_score_runs WHERE positive_run_id=%s", (run_id,)
            ).fetchone()
            is None
        ):
            raise IndexUnavailable("INDEX_HERBS_UNAVAILABLE")
        return []
    score = compile_formula(formula)
    top = sorted(scores, key=lambda row: (-score(row[1], row[2], row[3]), -row[3], row[0]))[:count]
    details = {
        row[0]: row
        for row in connection.execute(
            _english(HERB_DETAILS_SQL), ([herb_id for herb_id, *_ in top],)
        ).fetchall()
    }
    ranked = _ranked(
        [
            (details[herb_id][1], details[herb_id][2], l3, details[herb_id][3])
            for herb_id, _, _, l3 in top
        ]
    )
    for herb, (_, l1, l2, _) in zip(ranked, top, strict=True):
        herb["title_fragments"] = l1
        herb["text_fragments"] = l2
    return ranked


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
        state = published_state(connection)
        run_id = active_run(connection, settings, state)
        dictionary = condition_dictionary(connection, state)
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
        row = condition_ids(connection, state).get(matches[0].name)
        if row is None:
            raise IndexUnavailable("INDEX_RESYNC_REQUIRED")
        condition_id, name = row
        return {
            "status": "found",
            "condition": {"id": condition_id, "name": name},
            "positiveRunId": run_id,
            "herbs": _condition_rows(
                connection,
                run_id,
                count,
                category,
                condition_id,
                settings.herb_condition_top_formula,
            ),
        }


# Pays the per-language costs once at startup: name dictionaries, ranking and caution
# verification, and the herb catalog behind a product lookup.
def warm_up(settings: Settings = default_settings) -> None:
    from backend.ai.herb_conditions import lookup_herb_conditions

    for language in LANGUAGES:
        with language_scope(language):
            warm_up_names()
            try:
                with _ranking_connection() as connection:
                    condition_dictionary(connection)
                top = list_top_herbs(1, settings=settings)
                if top:
                    lookup_herb_conditions(top[0]["latin"] or top[0]["ro"], settings=settings)
            except (ApplicationError, IndexUnavailable) as exc:
                # An unpublished or stale ranking is reported on use; startup stays healthy.
                logger.warning(
                    "herb_warm_up_skipped language=%s type=%s", language, type(exc).__name__
                )
