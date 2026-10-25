"""Short snapshot/cache transactions and atomic publication of source-polarity generations."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from backend.ai import db
from backend.ai.herb_association_classification import Work, relation_id, semantic_config
from backend.ai.herb_association_rules import (
    POSITIVE_RANKING_VERSION,
    Decision,
    IndexedPassage,
    NameMatcher,
    content_hash,
    extract_units,
    source_context,
)
from backend.ai.herb_index_catalog import read_index_catalogs
from backend.ai.index_state import INDEX_LOCK, IndexUnavailable, read_metadata
from backend.config import Settings
from backend.core.errors import ApplicationError
from backend.core.operation_context import checkpoint, remaining_timeout
from backend.core.texts import tr

ACTIVE_KEY = "herb_positive_active_run"


def unavailable(stale: bool = False) -> ApplicationError:
    return ApplicationError(
        "POSITIVE_RANKING_STALE" if stale else "POSITIVE_RANKING_NOT_READY",
        tr("errors.positive_ranking_stale" if stale else "errors.positive_ranking_not_ready"),
        503,
    )


@dataclass(frozen=True)
class Snapshot:
    manifest: dict[str, Any]
    active: str | None
    herb_ids: tuple[int, ...]
    names: dict[int, str]
    conditions: dict[int, str]
    works: tuple[Work, ...]
    categories: tuple[tuple[int, str], ...] = ()
    condition_synonyms: dict[int, tuple[str, ...]] = field(default_factory=dict)


def snapshot(connection: Connection) -> Snapshot:
    metadata = read_metadata(connection)
    _, herb_ids, _, _, condition_fp, herb_fp = read_index_catalogs(connection)
    base: dict[str, str] = dict(
        connection.execute("SELECT key,value FROM sync_metadata").fetchall()
    )
    active = base.pop(ACTIVE_KEY, None)
    catalog = connection.execute(
        "SELECT id,category,family,latin,ro,en FROM herbs ORDER BY id"
    ).fetchall()
    aliases = connection.execute(
        "SELECT herb_id,name,kind FROM herb_aliases ORDER BY herb_id,kind,name"
    ).fetchall()
    # xmin protects against edits that bypass normal generation publication, including embeddings.
    chunks = connection.execute(
        "SELECT chunk_id,source_relative_path,source_sha256,text_sha256,heading,"
        "primary_medical_conditions,xmin::text FROM chunks ORDER BY chunk_id"
    ).fetchall()
    documents = connection.execute(
        "SELECT relative_path,sha256,xmin::text FROM documents ORDER BY relative_path"
    ).fetchall()
    manifest = {
        "version": POSITIVE_RANKING_VERSION,
        "generation": metadata.index_generation,
        "base": content_hash(base),
        "conditions": condition_fp,
        "herbs": herb_fp,
        "catalog": content_hash([catalog, aliases]),
        "chunks": content_hash(chunks),
        "documents": content_hash(documents),
    }
    conditions: dict[int, str] = dict(
        connection.execute("SELECT id,name FROM medical_conditions ORDER BY id").fetchall()
    )
    synonyms: dict[int, list[str]] = {identifier: [] for identifier in conditions}
    for identifier, synonym in connection.execute(
        "SELECT medical_condition_id,synonym FROM medical_condition_synonyms "
        "ORDER BY medical_condition_id,id"
    ).fetchall():
        synonyms[identifier].append(synonym)
    return Snapshot(
        manifest,
        active,
        herb_ids,
        {r[0]: r[4] + (f" ({r[3]})" if r[3] else "") for r in catalog},
        conditions,
        (),
        tuple((r[0], r[1]) for r in catalog),
        {identifier: tuple(terms) for identifier, terms in synonyms.items()},
    )


def evidence_rows(connection: Connection, run_id: str) -> list:
    return connection.execute(
        "SELECT identity,chunk_id,herb_id,medical_condition_id,unit_start,unit_end,"
        "mention_start,mention_end,label,origin,rule_code,cache_key,provenance "
        "FROM herb_positive_evidence WHERE run_id=%s ORDER BY identity",
        (run_id,),
    ).fetchall()


def assert_integrity(connection: Connection, run_id: str, expected: int, digest: str) -> None:
    rows = evidence_rows(connection, run_id)
    if len(rows) != expected or content_hash(rows) != digest:
        raise ValueError("POSITIVE_INCOMPLETE_EVIDENCE")
    invalid = connection.execute(
        "WITH expected_pairs AS (SELECT herb_id,medical_condition_id,"
        "count(*) FILTER(WHERE label='positive')::int p,"
        "count(*) FILTER(WHERE label='caution')::int c,"
        "count(*) FILTER(WHERE label='mixed')::int m,"
        "count(*) FILTER(WHERE label='unclear')::int u "
        "FROM herb_positive_evidence WHERE run_id=%s GROUP BY herb_id,medical_condition_id),"
        "actual AS (SELECT herb_id,medical_condition_id,positive_count p,caution_count c,"
        "mixed_count m,unclear_count u FROM herb_positive_pairs WHERE run_id=%s) "
        "SELECT EXISTS((SELECT * FROM expected_pairs EXCEPT SELECT * FROM actual) UNION ALL "
        "(SELECT * FROM actual EXCEPT SELECT * FROM expected_pairs))",
        (run_id, run_id),
    ).fetchone()
    mismatch = connection.execute(
        "WITH expected AS (SELECT h.id herb_id,count(p.medical_condition_id)::int ranking "
        "FROM herbs h LEFT JOIN herb_positive_pairs p ON p.herb_id=h.id AND p.run_id=%s "
        "AND p.state='positive' GROUP BY h.id), actual AS (SELECT herb_id,ranking "
        "FROM herb_positive_rankings WHERE run_id=%s) "
        "SELECT EXISTS((SELECT * FROM expected EXCEPT SELECT * FROM actual) UNION ALL "
        "(SELECT * FROM actual EXCEPT SELECT * FROM expected))",
        (run_id, run_id),
    ).fetchone()
    if invalid is None or mismatch is None or invalid[0] or mismatch[0]:
        raise ValueError("POSITIVE_AGGREGATION_MISMATCH")


@dataclass(frozen=True)
class PositiveRepository:
    pool: Callable[[], ConnectionPool] = db.get_pool

    @contextmanager
    def transaction(self, *, write: bool = False) -> Iterator[Connection]:
        with (
            self.pool().connection(timeout=remaining_timeout(5.0)) as connection,
            connection.transaction(),
        ):
            if not write:
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            connection.execute(
                "SELECT set_config('statement_timeout',%s,true)",
                (str(max(1, int(remaining_timeout(30) * 1000))),),
            )
            connection.execute(
                "SELECT set_config('lock_timeout',%s,true)",
                (str(max(1, int(remaining_timeout(2) * 1000))),),
            )
            lock = (
                "SELECT pg_try_advisory_xact_lock(%s)"
                if write
                else "SELECT pg_try_advisory_xact_lock_shared(%s)"
            )
            locked = connection.execute(lock, (INDEX_LOCK,)).fetchone()
            if locked is None or not locked[0]:
                raise IndexUnavailable()
            schema = connection.execute("SELECT to_regclass('herb_positive_runs')").fetchone()
            if schema is None or not schema[0]:
                raise unavailable()
            yield connection
            checkpoint()

    def read_snapshot(self) -> Snapshot:
        with self.transaction() as connection:
            data = snapshot(connection)
            condition_ids, herb_ids, terms, names, _, _ = read_index_catalogs(connection)
            rows = connection.execute(
                "SELECT chunk_id,source_relative_path,source_sha256,text_sha256,heading,text,"
                "primary_medical_conditions FROM chunks "
                "WHERE cardinality(primary_medical_conditions)>0 ORDER BY chunk_id"
            ).fetchall()
        # Segmentation and matching own no database connection or advisory lock.
        from backend.ai.herb_index_catalog import normalize_herb_name

        herb_names = tuple(
            (name, tuple(herb_ids[p] for p in positions)) for name, positions in names
        )
        condition_names = tuple(
            (normalize_herb_name(name), tuple(condition_ids[p] for p in positions))
            for name, positions in terms.items()
        )
        herb_matcher = NameMatcher(herb_names, product_forms=True)
        condition_matcher = NameMatcher(condition_names)
        canonical_conditions = {
            normalize_herb_name(name): identifier for identifier, name in data.conditions.items()
        }
        works: list[Work] = []
        categories = dict(data.categories)
        for row in rows:
            checkpoint()
            passage = IndexedPassage(row[0], row[1], row[2], row[3], row[4], row[5], tuple(row[6]))
            for unit in extract_units(
                passage,
                herb_matcher,
                condition_matcher,
                canonical_conditions=canonical_conditions,
                herb_categories=categories,
            ):
                works.extend((unit, candidate) for candidate in unit.candidates)
        return replace(data, works=tuple(works))

    def cached(self, keys: list[str]) -> dict[str, Decision]:
        if not keys:
            return {}
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT cache_key,decision FROM herb_positive_cache WHERE cache_key=ANY(%s)",
                (keys,),
            ).fetchall()
        return {
            key: Decision(
                value["label"],
                value["origin"],
                value["rule"],
                tuple(tuple(s) for s in value["quotes"]),
            )
            for key, value in rows
        }

    def save_cache(self, entries: dict[str, Decision]) -> None:
        with self.transaction(write=True) as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO herb_positive_cache(cache_key,decision) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                    [(key, Jsonb(asdict(value))) for key, value in entries.items()],
                )

    def analysis_digest(self, semantic: dict[str, Any]) -> str | None:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT model_digest FROM herb_positive_runs WHERE semantic=%s ORDER BY created_at DESC LIMIT 1",
                (Jsonb(semantic),),
            ).fetchone()
            return row[0] if row else None

    def admit_request(self, run_id: str, maximum: int) -> None:
        with self.transaction(write=True) as connection:
            row = connection.execute(
                "UPDATE herb_positive_runs SET counters=jsonb_set(counters,'{attempts}',"
                "to_jsonb(COALESCE((counters->>'attempts')::int,0)+1)) "
                "WHERE run_id=%s AND status='preparing' "
                "AND COALESCE((counters->>'attempts')::int,0)<%s RETURNING run_id",
                (run_id, maximum),
            ).fetchone()
            if row is None:
                raise ValueError("POSITIVE_REQUEST_LIMIT")

    def create_run(
        self, run_id: str, data: Snapshot, semantic: dict[str, Any], digest: str, resume: bool
    ) -> dict:
        UUID(run_id)
        with self.transaction(write=True) as connection:
            if snapshot(connection).manifest != data.manifest:
                raise unavailable(True)
            row = connection.execute(
                "SELECT manifest,semantic,model_digest,status,expected_count,evidence_hash FROM herb_positive_runs WHERE run_id=%s FOR UPDATE",
                (run_id,),
            ).fetchone()
            if resume:
                if row is None or row[:3] != (data.manifest, semantic, digest):
                    raise ValueError("POSITIVE_RESUME_INPUT_CHANGED")
                if row[3] == "ready":
                    assert_integrity(connection, run_id, row[4], row[5])
                return {"status": row[3]}
            if row:
                raise ValueError("POSITIVE_RUN_EXISTS")
            connection.execute(
                "INSERT INTO herb_positive_runs(run_id,status,manifest,semantic,model_digest,expected_active,expected_count) VALUES(%s,'preparing',%s,%s,%s,%s,%s)",
                (
                    run_id,
                    Jsonb(data.manifest),
                    Jsonb(semantic),
                    digest,
                    data.active,
                    len(data.works),
                ),
            )
            return {"status": "preparing"}

    def finish(
        self,
        run_id: str,
        data: Snapshot,
        decisions: dict[str, Decision],
        keys: dict[str, str],
        counters: dict,
    ) -> None:
        if decisions.keys() != {relation_id(w) for w in data.works}:
            raise ValueError("POSITIVE_INCOMPLETE_COVERAGE")
        with self.transaction(write=True) as connection:
            connection.execute(
                "LOCK TABLE documents,chunks,herbs,herb_aliases,medical_conditions,medical_condition_synonyms IN SHARE MODE"
            )
            if snapshot(connection).manifest != data.manifest:
                raise unavailable(True)
            status = connection.execute(
                "SELECT status FROM herb_positive_runs WHERE run_id=%s FOR UPDATE", (run_id,)
            ).fetchone()
            if status != ("preparing",):
                raise ValueError("POSITIVE_RUN_IMMUTABLE")
            connection.execute("DELETE FROM herb_positive_evidence WHERE run_id=%s", (run_id,))
            rows = []
            for work in data.works:
                unit, candidate = work
                identifier = relation_id(work)
                decision = decisions[identifier]
                provenance = {
                    "document": unit.passage.document,
                    "source_hash": unit.passage.source_hash,
                    "chunk_hash": unit.passage.text_hash,
                    "heading_hash": content_hash(unit.headings),
                    "context_hash": content_hash(source_context(unit)),
                    "context_spans": unit.scope,
                    "table_header_span": unit.table_header,
                    "quotes": decision.quotes,
                }
                rows.append(
                    (
                        run_id,
                        identifier,
                        unit.passage.chunk_id,
                        candidate.herb_id,
                        candidate.condition_id,
                        unit.start,
                        unit.end,
                        *candidate.mention,
                        decision.label,
                        decision.origin,
                        decision.rule,
                        keys.get(identifier),
                        Jsonb(provenance),
                    )
                )
            with connection.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO herb_positive_evidence(run_id,identity,chunk_id,herb_id,medical_condition_id,unit_start,unit_end,mention_start,mention_end,label,origin,rule_code,cache_key,provenance) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    rows,
                )
            connection.execute(
                "INSERT INTO herb_positive_pairs SELECT run_id,herb_id,medical_condition_id,"
                "count(*) FILTER(WHERE label='positive'),count(*) FILTER(WHERE label='caution'),"
                "count(*) FILTER(WHERE label='mixed'),count(*) FILTER(WHERE label='unclear'),"
                "CASE WHEN bool_or(label='mixed') OR (bool_or(label='positive') AND bool_or(label='caution')) THEN 'mixed' WHEN bool_or(label='positive') THEN 'positive' WHEN bool_or(label='caution') THEN 'caution' ELSE 'unclear' END "
                "FROM herb_positive_evidence WHERE run_id=%s GROUP BY run_id,herb_id,medical_condition_id",
                (run_id,),
            )
            connection.execute(
                "INSERT INTO herb_positive_rankings SELECT %s,h.id,count(p.medical_condition_id) FROM herbs h LEFT JOIN herb_positive_pairs p ON p.herb_id=h.id AND p.run_id=%s AND p.state='positive' GROUP BY h.id",
                (run_id, run_id),
            )
            digest = content_hash(evidence_rows(connection, run_id))
            assert_integrity(connection, run_id, len(data.works), digest)
            connection.execute(
                "UPDATE herb_positive_runs SET status='ready',evidence_hash=%s,counters=counters || %s WHERE run_id=%s",
                (digest, Jsonb(counters), run_id),
            )

    def publish(self, run_id: str, settings: Settings, *, digest: str) -> None:
        UUID(run_id)
        with self.transaction(write=True) as connection:
            connection.execute(
                "LOCK TABLE documents,chunks,herbs,herb_aliases,medical_conditions,medical_condition_synonyms,sync_metadata IN SHARE MODE"
            )
            row = connection.execute(
                "SELECT status,manifest,semantic,expected_active,expected_count,evidence_hash,model_digest FROM herb_positive_runs WHERE run_id=%s FOR UPDATE",
                (run_id,),
            ).fetchone()
            if row is None or row[0] != "ready":
                raise unavailable()
            if row[6] != digest:
                raise ValueError("POSITIVE_MODEL_CHANGED")
            data = snapshot(connection)
            if row[1] != data.manifest or row[2] != semantic_config(settings):
                raise unavailable(True)
            assert_integrity(connection, run_id, row[4], row[5])
            if data.active == run_id:
                return
            if data.active != row[3]:
                raise ValueError("POSITIVE_PUBLICATION_CONFLICT")
            connection.execute(
                "INSERT INTO sync_metadata(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
                (ACTIVE_KEY, run_id),
            )


def active_run(connection: Connection, settings: Settings) -> str:
    schema = connection.execute("SELECT to_regclass('herb_positive_runs')").fetchone()
    if schema is None or not schema[0]:
        raise unavailable()
    data = snapshot(connection)
    if not data.active:
        raise unavailable()
    try:
        UUID(data.active)
    except ValueError:
        raise unavailable() from None
    row = connection.execute(
        "SELECT status,manifest,semantic,expected_count,evidence_hash FROM herb_positive_runs WHERE run_id=%s",
        (data.active,),
    ).fetchone()
    if row is None or row[0] != "ready":
        raise unavailable()
    if row[1] != data.manifest or row[2] != semantic_config(settings):
        raise unavailable(True)
    try:
        assert_integrity(connection, data.active, row[3], row[4])
    except ValueError:
        raise unavailable(True) from None
    return data.active
