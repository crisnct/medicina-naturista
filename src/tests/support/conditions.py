"""Pure synthetic dictionaries and explicit seed for disposable test databases."""

from __future__ import annotations

from collections.abc import Sequence

from backend.ai.condition_repository import clear_catalog_cache
from backend.ai.conditions import Condition, make_condition


def conditions_from_rows(rows: str) -> list[Condition]:
    conditions = []
    for row in rows.splitlines():
        if row.strip():
            name, *synonyms = row.split(",")
            conditions.append(make_condition(name, synonyms))
    return conditions


def replace_catalog(connection, conditions: Sequence[Condition]) -> None:
    """Test-only replacement; the caller supplies an isolated database connection."""
    from backend.ai.index_state import INDEX_LOCK

    connection.execute("SELECT pg_advisory_xact_lock(%s)", (INDEX_LOCK,))
    connection.execute("TRUNCATE medical_conditions RESTART IDENTITY CASCADE")
    for item in conditions:
        condition_id = connection.execute(
            "INSERT INTO medical_conditions(name,en) VALUES (%s,%s) RETURNING id",
            (item.name, item.english or item.name),
        ).fetchone()[0]
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO medical_condition_synonyms(medical_condition_id, synonym) VALUES (%s,%s)",
                [(condition_id, term) for term in item.terms[1:]],
            )
    clear_catalog_cache()
