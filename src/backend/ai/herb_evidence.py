"""Read complete source fragments from one published positive-association generation."""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

import psycopg
from psycopg import Connection
from psycopg_pool import PoolTimeout

from backend.ai.herb_association_rules import NameMatcher
from backend.ai.herb_caution_repository import active_caution_run
from backend.ai.herb_caution_repository import unavailable as caution_unavailable
from backend.ai.herb_index_catalog import normalize_herb_name
from backend.ai.herb_positive_repository import PositiveRepository
from backend.ai.herb_repository import catalog_snapshot
from backend.ai.herb_run_cache import active_run
from backend.ai.index_state import IndexUnavailable
from backend.config import Settings
from backend.config import settings as default_settings
from backend.core.contracts import HerbCondition, HerbEvidenceKind, HerbEvidencePage, HerbHighlight
from backend.core.errors import ApplicationError
from backend.core.language import current_language
from backend.core.operation_context import checkpoint
from backend.core.texts import tr

PAGE_SIZE = 20

# Keep the condition filter separate from the eligible relationships so each returned
# fragment still lists every positive condition it supports for this particular product.
ELIGIBLE_SQL = """
WITH eligible AS (
    SELECT DISTINCT e.chunk_id, e.medical_condition_id
    FROM herb_positive_evidence e
    JOIN herb_positive_pairs p USING (run_id, herb_id, medical_condition_id)
    WHERE e.run_id = %s AND e.herb_id = %s
      AND e.label = 'positive' AND p.state = 'positive'
), selected AS (
    SELECT DISTINCT chunk_id FROM eligible
    WHERE (%s::integer IS NULL OR medical_condition_id = %s)
)
"""

CAUTION_ELIGIBLE_SQL = """
WITH eligible AS (
    SELECT DISTINCT e.chunk_id, e.medical_condition_id
    FROM herb_caution_evidence e
    JOIN herb_caution_pairs p USING (run_id, herb_id, medical_condition_id)
    WHERE e.run_id = %s AND e.herb_id = %s
      AND e.warning_kind = 'prohibition' AND p.prohibition_count > 0
), selected AS (
    SELECT DISTINCT chunk_id FROM eligible
    WHERE (%s::integer IS NULL OR medical_condition_id = %s)
)
"""


def evidence_counts(
    connection: Connection,
    run_id: str,
    herb_id: int,
    condition_id: int | None = None,
    *,
    evidence_kind: HerbEvidenceKind = "positive",
) -> tuple[int, int]:
    eligible_sql = CAUTION_ELIGIBLE_SQL if evidence_kind == "contraindication" else ELIGIBLE_SQL
    row = connection.execute(
        eligible_sql + "SELECT count(*), count(DISTINCT c.source_relative_path) "
        "FROM selected s JOIN chunks c USING (chunk_id)",
        (run_id, herb_id, condition_id, condition_id),
    ).fetchone()
    assert row is not None
    return row[0], row[1]


# Resolve overlaps once on the server; product names win without changing source text.
def highlights(
    text: str, herb_matcher: NameMatcher, condition_matcher: NameMatcher
) -> list[HerbHighlight]:
    herb_spans = [span for span, _ in herb_matcher.spans(text)]
    condition_spans = [span for span, _ in condition_matcher.spans(text)]
    events: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for category, spans in enumerate((herb_spans, condition_spans)):
        for start, end in spans:
            events[start][category] += 1
            events[end][category] -= 1
    result: list[HerbHighlight] = []
    counts = [0, 0]
    previous = 0
    for position, deltas in sorted(events.items()):
        if position > previous and any(counts):
            kind: Literal["herb", "condition"] = "herb" if counts[0] else "condition"
            if result and result[-1]["end"] == previous and result[-1]["kind"] == kind:
                result[-1]["end"] = position
            else:
                result.append({"start": previous, "end": position, "kind": kind})
        counts = [count + delta for count, delta in zip(counts, deltas, strict=True)]
        previous = position
    return result


def lookup_herb_evidence(
    herb_id: int,
    run_id: str,
    *,
    condition_id: int | None = None,
    offset: int = 0,
    evidence_kind: HerbEvidenceKind = "positive",
    caution_run_id: str | None = None,
    settings: Settings = default_settings,
) -> HerbEvidencePage:
    try:
        if evidence_kind not in {"positive", "contraindication"}:
            raise ApplicationError("INVALID_REQUEST", tr("errors.request_invalid"), 422)
        with PositiveRepository().transaction() as connection:
            if active_run(connection, settings) != run_id:
                raise ApplicationError("HERB_EVIDENCE_STALE", tr("errors.herb_evidence_stale"), 409)
            if evidence_kind == "contraindication" or caution_run_id is not None:
                current_caution, status = active_caution_run(connection, run_id)
                if caution_run_id is None:
                    raise caution_unavailable(status == "stale")
                if current_caution != caution_run_id:
                    raise ApplicationError(
                        "HERB_EVIDENCE_STALE", tr("errors.herb_evidence_stale"), 409
                    )
            source_run_id = caution_run_id if evidence_kind == "contraindication" else run_id
            assert source_run_id is not None
            eligible_sql = (
                CAUTION_ELIGIBLE_SQL if evidence_kind == "contraindication" else ELIGIBLE_SQL
            )
            herb = catalog_snapshot(connection).catalog.by_id(herb_id)
            if herb is None:
                raise ApplicationError("HERB_EVIDENCE_STALE", tr("errors.herb_evidence_stale"), 409)
            fragments_count, documents_count = evidence_counts(
                connection, source_run_id, herb_id, condition_id, evidence_kind=evidence_kind
            )
            rows = connection.execute(
                eligible_sql + "SELECT c.chunk_id,c.source_relative_path,c.line_start,c.line_end,"
                "c.heading,c.text FROM selected s JOIN chunks c USING (chunk_id) "
                "ORDER BY c.source_relative_path,c.line_start,c.chunk_id LIMIT %s OFFSET %s",
                (source_run_id, herb_id, condition_id, condition_id, PAGE_SIZE, offset),
            ).fetchall()
            relations = connection.execute(
                (
                    eligible_sql + "SELECT e.chunk_id,mc.id,mc.name,s.synonym FROM eligible e "
                    "JOIN medical_conditions mc ON mc.id=e.medical_condition_id "
                    "LEFT JOIN medical_condition_synonyms s ON s.medical_condition_id=mc.id "
                    "WHERE e.chunk_id=ANY(%s) ORDER BY e.chunk_id,mc.name,mc.id,s.id"
                ).replace("mc.name", "mc.en" if current_language() == "en" else "mc.name"),
                (source_run_id, herb_id, condition_id, condition_id, [row[0] for row in rows]),
            ).fetchall()
            by_chunk: dict[int, dict[int, HerbCondition]] = defaultdict(dict)
            terms: dict[int, set[str]] = defaultdict(set)
            for chunk_id, identifier, name, synonym in relations:
                by_chunk[chunk_id][identifier] = {"id": identifier, "name": name}
                terms[identifier].add(normalize_herb_name(name))
                if synonym:
                    terms[identifier].add(normalize_herb_name(synonym))
            herb_matcher = NameMatcher(
                tuple((normalize_herb_name(name), (herb_id,)) for name in herb.names),
                product_forms=True,
            )
            page: HerbEvidencePage = {
                "herbId": herb_id,
                "positiveRunId": run_id,
                "evidenceKind": evidence_kind,
                "fragmentsCount": fragments_count,
                "documentsCount": documents_count,
                "fragments": [],
                "nextOffset": offset + len(rows)
                if rows and offset + len(rows) < fragments_count
                else None,
            }
            if caution_run_id is not None:
                page["cautionRunId"] = caution_run_id
            for chunk_id, document, line_start, line_end, heading, text in rows:
                checkpoint()
                conditions = list(by_chunk[chunk_id].values())
                condition_matcher = NameMatcher(
                    tuple(
                        (term, (condition["id"],))
                        for condition in conditions
                        for term in sorted(terms[condition["id"]])
                    )
                )
                page["fragments"].append(
                    {
                        "chunkId": chunk_id,
                        "document": document,
                        "lineStart": line_start,
                        "lineEnd": line_end,
                        "heading": heading,
                        "text": text,
                        "conditions": conditions,
                        "headingHighlights": highlights(heading, herb_matcher, condition_matcher),
                        "textHighlights": highlights(text, herb_matcher, condition_matcher),
                    }
                )
            return page
    except (psycopg.Error, PoolTimeout):
        raise IndexUnavailable("INDEX_HERBS_UNAVAILABLE") from None
