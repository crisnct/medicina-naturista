"""Precompute L1, L2 and L3 per product and condition for the active positive generation.

Lives apart from herb_positive_repository.py because that file's source hash is part of the
ranking's semantic fingerprint: editing it would mark every published ranking stale.
"""

from __future__ import annotations

from collections import defaultdict

from psycopg import Connection

from backend.ai.herb_association_rules import NameMatcher
from backend.ai.herb_index_catalog import normalize_herb_name, read_index_catalogs
from backend.ai.herb_positive_repository import PositiveRepository, active_key, snapshot
from backend.core.language import current_language
from backend.core.operation_context import checkpoint

# L1 reuses the classified evidence: a fragment counts once however often it mentions the product.
L1_SQL = (
    "SELECT herb_id,medical_condition_id,count(DISTINCT chunk_id)::int FROM herb_positive_evidence "
    "WHERE run_id=%s AND label='positive' GROUP BY herb_id,medical_condition_id"
)


# Only unambiguous product mentions count; ambiguous names were already resolved by the matcher.
def _text_fragments(
    connection: Connection,
    matcher: NameMatcher,
    condition_ids: dict[str, int],
    eligible: dict[int, set[int]],
) -> dict[tuple[int, int], int]:
    counts: dict[tuple[int, int], int] = defaultdict(int)
    rows = connection.execute(
        "SELECT heading,text,secondary_medical_conditions FROM chunks "
        "WHERE language=%s AND cardinality(secondary_medical_conditions)>0",
        (current_language(),),
    )
    for heading, text, secondary in rows:
        checkpoint()
        conditions = {
            condition_ids[key]
            for name in secondary
            if (key := normalize_herb_name(name)) in condition_ids
        }
        if not conditions:
            continue
        herbs = {
            identifiers[0]
            for _, identifiers in matcher.product_spans(text, (heading,) if heading else ())
            if len(identifiers) == 1 and identifiers[0] in eligible
        }
        for herb_id in herbs:
            for condition_id in conditions & eligible[herb_id]:
                counts[(herb_id, condition_id)] += 1
    return counts


def rebuild_condition_scores(repository: PositiveRepository | None = None) -> dict:
    """Replace the scores of the active positive run of the current language; no inference."""
    with (repository or PositiveRepository()).transaction(write=True) as connection:
        row = connection.execute(
            "SELECT value FROM sync_metadata WHERE key=%s", (active_key(),)
        ).fetchone()
        if row is None:
            raise ValueError("CONDITION_SCORES_NO_ACTIVE_RUN")
        run_id = row[0]
        data = snapshot(connection)
        _, herb_ids, _, names, _, _ = read_index_catalogs(connection)
        matcher = NameMatcher(
            tuple((name, tuple(herb_ids[p] for p in positions)) for name, positions in names),
            product_forms=True,
            preferred_names=data.preferred_names,
        )
        condition_ids = {
            normalize_herb_name(name): ident for ident, name in data.conditions.items()
        }
        eligible: dict[int, set[int]] = defaultdict(set)
        for herb_id, condition_id in connection.execute(
            "SELECT herb_id,medical_condition_id FROM herb_positive_pairs "
            "WHERE run_id=%s AND state='positive'",
            (run_id,),
        ):
            eligible[herb_id].add(condition_id)
        ranking = dict(
            connection.execute(
                "SELECT herb_id,ranking FROM herb_positive_rankings WHERE run_id=%s AND ranking>0",
                (run_id,),
            ).fetchall()
        )
        if {herb: len(items) for herb, items in eligible.items()} != ranking:
            raise ValueError("CONDITION_SCORES_RANKING_MISMATCH")
        title = {
            (herb_id, condition_id): count
            for herb_id, condition_id, count in connection.execute(L1_SQL, (run_id,))
        }
        text = _text_fragments(connection, matcher, condition_ids, eligible)
        rows = [
            (
                run_id,
                condition_id,
                herb_id,
                title.get((herb_id, condition_id), 0),
                text.get((herb_id, condition_id), 0),
                ranking[herb_id],
            )
            for herb_id, conditions in sorted(eligible.items())
            for condition_id in sorted(conditions)
        ]
        # Every eligible pair is backed by at least one positive title fragment.
        if any(row[3] == 0 for row in rows):
            raise ValueError("CONDITION_SCORES_MISSING_TITLE_EVIDENCE")
        connection.execute(
            "DELETE FROM herb_condition_score_runs WHERE positive_run_id=%s", (run_id,)
        )
        connection.execute(
            "INSERT INTO herb_condition_score_runs (positive_run_id,row_count) VALUES (%s,%s)",
            (run_id, len(rows)),
        )
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO herb_condition_scores (positive_run_id,medical_condition_id,herb_id,"
                "title_fragments,text_fragments,conditions_count) VALUES (%s,%s,%s,%s,%s,%s)",
                rows,
            )
        return {
            "stage": "condition_scores",
            "language": current_language(),
            "positive_run_id": run_id,
            "rows": len(rows),
            "pairs_with_text_fragments": sum(1 for row in rows if row[4] > 0),
        }
