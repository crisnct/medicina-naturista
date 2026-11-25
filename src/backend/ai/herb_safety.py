"""Read published model-knowledge messages; consultation never invokes a model."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from typing import Literal, cast

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
from backend.ai.herb_product_safety_repository import unavailable
from backend.ai.herb_repository import catalog_snapshot
from backend.ai.herbs import Herb
from backend.ai.index_state import IndexUnavailable
from backend.config import Settings
from backend.config import settings as default_settings
from backend.core.contracts import (
    HerbHighlight,
    HerbSafetyEvidencePage,
    HerbSafetyKind,
    HerbSafetyPage,
    ReportHerbSafety,
)
from backend.core.errors import ApplicationError
from backend.core.language import current_language
from backend.core.texts import tr

PAGE_SIZE = 20

logger = logging.getLogger("naturist.herbs")


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


def _capitalized(name: str) -> str:
    return name[:1].upper() + name[1:]


# The catalog stores lowercase names. The report capitalizes the product name and the Latin
# genus (the species epithet stays lowercase) and names the product once when both are equal.
def report_herb_title(herb: Herb) -> str:
    name = (herb.en or herb.latin or herb.ro) if current_language() == "en" else herb.ro
    title = _capitalized(name)
    if herb.latin and herb.latin.casefold() != name.casefold():
        title += f" ({_capitalized(herb.latin)})"
    return title


# Every catalog product named by a report label, once, with its messages from the active
# generation of the current language. The report must not fail for these extra items, so an
# unavailable database or generation yields none.
def load_report_herb_safety(
    labels: Sequence[str], *, settings: Settings = default_settings
) -> tuple[ReportHerbSafety, ...]:
    if not labels:
        return ()
    try:
        with SafetyRepository().transaction() as connection:
            run_id, _ = active_safety_run(connection, settings)
            if run_id is None:
                return ()
            catalog = catalog_snapshot(connection).catalog
            herbs = {
                herb.id: herb for label in dict.fromkeys(labels) for herb in catalog.mentions(label)
            }
            if not herbs:
                return ()
            rows = connection.execute(
                "SELECT herb_id,message_type,problem FROM herb_safety_messages "
                "WHERE run_id=%s AND herb_id=ANY(%s) ORDER BY herb_id,CASE message_type "
                "WHEN 'warning' THEN 0 WHEN 'contraindication' THEN 1 ELSE 2 END,problem,message_id",
                (run_id, list(herbs)),
            ).fetchall()
    except (psycopg.Error, PoolTimeout, IndexUnavailable) as error:
        logger.error("report_herb_safety_unavailable error_type=%s", type(error).__name__)
        return ()
    messages: dict[int, list[tuple[HerbSafetyKind, str]]] = {}
    for herb_id, kind, problem in rows:
        messages.setdefault(herb_id, []).append((cast(HerbSafetyKind, kind), problem))
    return tuple(
        ReportHerbSafety(report_herb_title(herbs[herb_id]), tuple(items))
        for herb_id, items in messages.items()
    )


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
