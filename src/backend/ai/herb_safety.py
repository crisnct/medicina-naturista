"""Read published model-knowledge messages; consultation never invokes a model."""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

import psycopg
from psycopg import Connection
from psycopg_pool import PoolTimeout

from backend.ai.herb_association_rules import NameMatcher
from backend.ai.herb_product_safety_repository import (
    ProductSafetyRepository as SafetyRepository,
)
from backend.ai.herb_product_safety_repository import (
    active_product_safety_run as active_safety_run,
)
from backend.ai.herb_safety_repository import unavailable
from backend.config import Settings
from backend.config import settings as default_settings
from backend.core.contracts import HerbHighlight, HerbSafetyEvidencePage, HerbSafetyPage
from backend.core.errors import ApplicationError
from backend.core.texts import tr

PAGE_SIZE = 20


def require_run(connection: Connection, run_id: str, settings: Settings) -> None:
    active, status = active_safety_run(connection, settings)
    if active is None:
        raise unavailable(status == "stale")
    if active != run_id:
        raise unavailable(True)


def source_unavailable() -> ApplicationError:
    return ApplicationError("HERB_SAFETY_UNAVAILABLE", tr("errors.herb_safety_unavailable"), 404)


def lookup_herb_safety(
    herb_id: int, run_id: str, *, offset: int = 0, settings: Settings = default_settings
) -> HerbSafetyPage:
    try:
        with SafetyRepository().transaction() as connection:
            require_run(connection, run_id, settings)
            total = connection.execute(
                "SELECT count(*) FROM herb_safety_messages WHERE run_id=%s AND herb_id=%s",
                (run_id, herb_id),
            ).fetchone()
            analysis = connection.execute(
                "SELECT status FROM herb_product_safety_results WHERE run_id=%s AND herb_id=%s",
                (run_id, herb_id),
            ).fetchone()
            rows = connection.execute(
                "SELECT message_id,problem,message_type FROM herb_safety_messages "
                "WHERE run_id=%s AND herb_id=%s ORDER BY CASE message_type "
                "WHEN 'warning' THEN 0 WHEN 'contraindication' THEN 1 ELSE 2 END,problem,message_id "
                "LIMIT %s OFFSET %s",
                (run_id, herb_id, PAGE_SIZE, offset),
            ).fetchall()
            if analysis is None:
                raise unavailable(True)
            assert total is not None
            return {
                "herbId": herb_id,
                "safetyRunId": run_id,
                "warningsStatus": "ready" if analysis[0] == "complete" else "partial",
                "warningsCount": total[0],
                "warnings": [
                    {
                        "id": identifier,
                        "text": text,
                        "kind": kind,
                        "partners": [],
                        "sourcesCount": 0,
                    }
                    for identifier, text, kind in rows
                ],
                "nextOffset": offset + len(rows)
                if rows and offset + len(rows) < total[0]
                else None,
            }
    except (psycopg.Error, PoolTimeout):
        raise ApplicationError(
            "HERB_SAFETY_UNAVAILABLE", tr("errors.herb_safety_unavailable"), 503
        ) from None


# A warning highlight may contain a product highlight; emit non-overlapping code-point spans.
def warning_highlights(
    text: str, matcher: NameMatcher, quotes: list[tuple[int, int]]
) -> list[HerbHighlight]:
    events: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for index, spans in enumerate((list(span for span, _ in matcher.spans(text)), quotes)):
        for start, end in spans:
            if 0 <= start < end <= len(text):
                events[start][index] += 1
                events[end][index] -= 1
    counts = [0, 0]
    previous = 0
    result: list[HerbHighlight] = []
    for position, delta in sorted(events.items()):
        if previous < position and any(counts):
            kind: Literal["herb", "warning"] = "herb" if counts[0] else "warning"
            if result and result[-1]["kind"] == kind and result[-1]["end"] == previous:
                result[-1]["end"] = position
            else:
                result.append({"start": previous, "end": position, "kind": kind})
        counts = [count + change for count, change in zip(counts, delta, strict=True)]
        previous = position
    return result


def lookup_herb_safety_evidence(
    herb_id: int,
    run_id: str,
    *,
    warning_id: str,
    offset: int = 0,
    settings: Settings = default_settings,
) -> HerbSafetyEvidencePage:
    # Model knowledge has no local evidence; the legacy authenticated route must not invent it.
    raise source_unavailable()
