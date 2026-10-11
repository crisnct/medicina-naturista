"""Generate self-contained SQL additions; existing conditions are never replaced."""

from __future__ import annotations

from collections.abc import Sequence

from psycopg import sql

from backend.ai.conditions import Condition, _normalize


def additions_sql(conditions: Sequence[Condition]) -> str:
    if not conditions:
        raise ValueError("EMPTY_CONDITION_ADDITIONS")
    names: set[str] = set()
    rows = []
    for ordinal, condition in enumerate(conditions):
        key = _normalize(condition.name)
        keys = [_normalize(term) for term in condition.terms]
        if (
            not key
            or key in names
            or not condition.terms
            or condition.terms[0] != condition.name
            or any(not term_key for term_key in keys)
            or len(set(keys)) != len(keys)
            or any(term != " ".join(term.split()) for term in condition.terms)
        ):
            raise ValueError("INVALID_CONDITION_ADDITIONS")
        names.add(key)
        rows.append(
            sql.SQL("({}, {}, ARRAY[{}]::text[])").format(
                sql.Literal(ordinal),
                sql.Literal(condition.name),
                sql.SQL(", ").join(map(sql.Literal, condition.terms[1:])),
            )
        )
    return (
        sql.SQL("""-- Add missing conditions, preserving existing names, terms and order.
WITH source(ordinal, name, synonyms) AS (
    VALUES
    {rows}
), missing AS (
    SELECT source.*
    FROM source
    WHERE NOT EXISTS (
        SELECT 1 FROM medical_conditions c WHERE lower(c.name) = lower(source.name)
    )
), inserted AS (
    INSERT INTO medical_conditions(name)
    SELECT name FROM missing ORDER BY ordinal
    ON CONFLICT (name) DO NOTHING
    RETURNING id, name
)
INSERT INTO medical_condition_synonyms(medical_condition_id, synonym)
SELECT inserted.id, s.synonym
FROM inserted JOIN source USING (name)
CROSS JOIN LATERAL unnest(source.synonyms)
    WITH ORDINALITY AS s(synonym, position)
ORDER BY source.ordinal, s.position;
""")
        .format(rows=sql.SQL(",\n    ").join(rows))
        .as_string()
    )
