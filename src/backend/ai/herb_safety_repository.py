"""Persist safety generations and validated caches without performing any model or network I/O."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from backend.ai import db
from backend.ai.herb_association_rules import content_hash
from backend.ai.herb_index_catalog import read_index_catalogs
from backend.ai.herb_positive_repository import PositiveRepository, snapshot
from backend.ai.herb_safety_extraction import (
    SUMMARY_MAX_CHARS,
    SafetyTarget,
    inventory_targets,
    product_matcher,
)
from backend.ai.herb_safety_validation import (
    SafetyResult,
    decode_result,
    encode_result,
    safety_semantic,
)
from backend.config import Settings
from backend.core.contracts import HerbCautionStatus, HerbLookupResult
from backend.core.errors import ApplicationError
from backend.core.operation_context import checkpoint
from backend.core.texts import tr


def unavailable(stale: bool = False) -> ApplicationError:
    return ApplicationError(
        "HERB_SAFETY_STALE" if stale else "HERB_SAFETY_NOT_READY",
        tr("errors.herb_safety_stale" if stale else "errors.herb_safety_not_ready"),
        409 if stale else 503,
    )


def schema_available(connection: Connection) -> bool:
    row = connection.execute(
        "SELECT to_regclass('herb_safety_runs') IS NOT NULL AND ("
        "SELECT count(*)=3 FROM pg_attribute "
        "WHERE attrelid=to_regclass('herb_safety_evidence') AND NOT attisdropped "
        "AND attname IN ('quote_text','focus_start','focus_end'))"
    ).fetchone()
    return bool(row and row[0])


def source_manifest(connection: Connection) -> dict[str, Any]:
    # Positive activation is already excluded by snapshot; its algorithm version is unrelated.
    return {key: value for key, value in snapshot(connection).manifest.items() if key != "version"}


@dataclass(frozen=True)
class SafetySnapshot:
    manifest: dict[str, Any]
    targets: tuple[SafetyTarget, ...]


def evidence_digest(connection: Connection, run_id: str) -> str:
    analysis = connection.execute(
        "SELECT identity,herb_id,chunk_id,status,mandatory,cache_key FROM herb_safety_analysis "
        "WHERE run_id=%s ORDER BY identity",
        (run_id,),
    ).fetchall()
    warnings = connection.execute(
        "SELECT warning_id,herb_id,kind,text,partners FROM herb_safety_warnings "
        "WHERE run_id=%s ORDER BY warning_id",
        (run_id,),
    ).fetchall()
    evidence = connection.execute(
        "SELECT warning_id,herb_id,identity,chunk_id,quote_start,quote_end,source_hash,"
        "text_hash,heading_hash,quote_text,focus_start,focus_end "
        "FROM herb_safety_evidence WHERE run_id=%s "
        "ORDER BY warning_id,chunk_id,quote_start,quote_end",
        (run_id,),
    ).fetchall()
    return content_hash([analysis, warnings, evidence])


def assert_integrity(connection: Connection, run_id: str, expected: int, digest: str) -> None:
    count = connection.execute(
        "SELECT count(*) FROM herb_safety_analysis WHERE run_id=%s", (run_id,)
    ).fetchone()
    invalid = connection.execute(
        "SELECT EXISTS(SELECT 1 FROM herb_safety_evidence e JOIN chunks c USING(chunk_id) "
        "JOIN herb_safety_warnings w USING(run_id,warning_id,herb_id) WHERE e.run_id=%s "
        "AND (e.quote_end>char_length(c.text) OR e.source_hash<>c.source_sha256 "
        "OR e.text_hash<>c.text_sha256 "
        "OR substring(c.text FROM e.quote_start+1 FOR e.quote_end-e.quote_start)<>e.quote_text "
        "OR e.focus_start<e.quote_start OR e.focus_end>e.quote_end "
        "OR char_length(w.text)>%s)) "
        "OR EXISTS(SELECT 1 FROM herb_safety_warnings w WHERE w.run_id=%s AND NOT EXISTS("
        "SELECT 1 FROM herb_safety_evidence e WHERE e.run_id=w.run_id "
        "AND e.warning_id=w.warning_id))",
        (run_id, SUMMARY_MAX_CHARS, run_id),
    ).fetchone()
    if (
        count != (expected,)
        or invalid is None
        or invalid[0]
        or evidence_digest(connection, run_id) != digest
    ):
        raise ValueError("HERB_SAFETY_INCOMPLETE_EVIDENCE")


def active_safety_run(
    connection: Connection, settings: Settings
) -> tuple[str | None, HerbCautionStatus]:
    if not schema_available(connection):
        return None, "not_ready"
    row = connection.execute(
        "SELECT run_id::text,status,manifest,semantic,expected_count,evidence_hash "
        "FROM herb_safety_runs WHERE is_active"
    ).fetchone()
    if row is None:
        return None, "not_ready"
    if (
        row[1] != "ready"
        or row[2] != source_manifest(connection)
        or row[3] != safety_semantic(settings)
    ):
        return None, "stale"
    try:
        assert_integrity(connection, row[0], row[4], row[5])
    except ValueError:
        return None, "stale"
    return row[0], "ready"


def safety_metadata(connection: Connection, herb_id: int, settings: Settings) -> HerbLookupResult:
    run_id, status = active_safety_run(connection, settings)
    result: HerbLookupResult = {
        "status": "found",
        "safetyRunId": run_id,
        "warningsStatus": status,
        "warningsCount": None,
        "warningFragmentsCount": 0,
        "warningDocumentsCount": 0,
        "warningCandidateFragmentsCount": 0,
    }
    if run_id is not None:
        counts = connection.execute(
            "SELECT count(*),count(*) FILTER(WHERE status<>'complete') "
            "FROM herb_safety_analysis WHERE run_id=%s AND herb_id=%s",
            (run_id, herb_id),
        ).fetchone()
        warnings = connection.execute(
            "SELECT count(*) FROM herb_safety_warnings WHERE run_id=%s AND herb_id=%s",
            (run_id, herb_id),
        ).fetchone()
        sources = connection.execute(
            "SELECT count(DISTINCT e.chunk_id),count(DISTINCT c.source_relative_path) "
            "FROM herb_safety_evidence e JOIN chunks c USING(chunk_id) "
            "WHERE e.run_id=%s AND e.herb_id=%s",
            (run_id, herb_id),
        ).fetchone()
        assert counts is not None and warnings is not None and sources is not None
        result.update(
            {
                "warningsStatus": "partial" if counts[1] else "ready",
                "warningsCount": warnings[0],
                "warningCandidateFragmentsCount": counts[0],
                "warningFragmentsCount": sources[0],
                "warningDocumentsCount": sources[1],
            }
        )
    return result


@dataclass(frozen=True)
class SafetyRepository:
    pool: Callable[[], ConnectionPool] = db.get_pool

    def transaction(self, *, write: bool = False) -> AbstractContextManager[Connection]:
        return PositiveRepository(self.pool).transaction(write=write)

    def is_ready(self, run_id: str) -> bool:
        with self.transaction() as connection:
            if not schema_available(connection):
                return False
            row = connection.execute(
                "SELECT status FROM herb_safety_runs WHERE run_id=%s", (run_id,)
            ).fetchone()
            return row == ("ready",)

    def analysis_digest(self, semantic: dict[str, Any]) -> str | None:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT model_digest FROM herb_safety_runs WHERE semantic=%s "
                "ORDER BY created_at DESC LIMIT 1",
                (Jsonb(semantic),),
            ).fetchone()
            return row[0] if row else None

    def read_snapshot(self) -> SafetySnapshot:
        with self.transaction() as connection:
            if not schema_available(connection):
                raise unavailable()
            data = snapshot(connection)
            _, identifiers, _, terms, _, _ = read_index_catalogs(connection)
            rows = connection.execute(
                "SELECT chunk_id,source_relative_path,source_sha256,text_sha256,heading,text "
                "FROM chunks ORDER BY source_relative_path,line_start,chunk_id"
            ).fetchall()
        matcher = product_matcher(
            tuple((name, tuple(identifiers[p] for p in positions)) for name, positions in terms)
        )
        return SafetySnapshot(
            {key: value for key, value in data.manifest.items() if key != "version"},
            inventory_targets(rows, matcher, data.names, data.manifest["catalog"]),
        )

    def cached(
        self, data: SafetySnapshot, semantic: dict[str, Any], digest: str
    ) -> dict[str, SafetyResult]:
        targets = {target.cache_key(semantic, digest): target for target in data.targets}
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT cache_key,decision FROM herb_safety_cache WHERE cache_key=ANY(%s)",
                (list(targets),),
            ).fetchall()
        result = {}
        for key, value in rows:
            checkpoint()
            target = targets[key]
            result[target.identity] = decode_result(value, target)
        return result

    def save_cache(
        self,
        targets: list[SafetyTarget],
        results: dict[str, SafetyResult],
        semantic: dict[str, Any],
        digest: str,
    ) -> None:
        with self.transaction(write=True) as connection, connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO herb_safety_cache(cache_key,semantic,model_digest,decision) "
                "VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                [
                    (
                        target.cache_key(semantic, digest),
                        Jsonb(semantic),
                        digest,
                        Jsonb(encode_result(results[target.identity])),
                    )
                    for target in targets
                ],
            )

    def create_run(
        self,
        run_id: str,
        data: SafetySnapshot,
        semantic: dict[str, Any],
        digest: str,
        resume: bool,
        *,
        require_existing: bool = False,
    ) -> str:
        UUID(run_id)
        with self.transaction(write=True) as connection:
            if source_manifest(connection) != data.manifest:
                raise unavailable(True)
            existing = connection.execute(
                "SELECT status,manifest,semantic,model_digest FROM herb_safety_runs "
                "WHERE run_id=%s FOR UPDATE",
                (run_id,),
            ).fetchone()
            if existing:
                if not resume or existing[1:] != (data.manifest, semantic, digest):
                    raise ValueError("HERB_SAFETY_RESUME_INPUT_CHANGED")
                return existing[0]
            if require_existing:
                raise ValueError("HERB_SAFETY_RESUME_NOT_FOUND")
            previous = connection.execute(
                "SELECT run_id::text FROM herb_safety_runs WHERE is_active"
            ).fetchone()
            connection.execute(
                "INSERT INTO herb_safety_runs(run_id,status,manifest,semantic,model_digest,"
                "expected_active,expected_count) VALUES(%s,'preparing',%s,%s,%s,%s,%s)",
                (
                    run_id,
                    Jsonb(data.manifest),
                    Jsonb(semantic),
                    digest,
                    previous[0] if previous else None,
                    len(data.targets),
                ),
            )
        return "preparing"

    def admit_request(self, run_id: str, maximum: int) -> None:
        with self.transaction(write=True) as connection:
            row = connection.execute(
                "UPDATE herb_safety_runs SET counters=jsonb_set(counters,'{attempts}',"
                "to_jsonb(COALESCE((counters->>'attempts')::int,0)+1)) WHERE run_id=%s "
                "AND status='preparing' AND COALESCE((counters->>'attempts')::int,0)<%s RETURNING run_id",
                (run_id, maximum),
            ).fetchone()
            if row is None:
                raise ValueError("HERB_SAFETY_REQUEST_LIMIT")

    def finish(
        self,
        run_id: str,
        data: SafetySnapshot,
        results: dict[str, SafetyResult],
        mandatory: set[str],
        semantic: dict[str, Any],
        digest: str,
        counters: dict[str, Any],
    ) -> None:
        if set(results) != {target.identity for target in data.targets} or any(
            results[key].status not in {"complete", "unclear"} for key in mandatory
        ):
            raise ValueError("HERB_SAFETY_INCOMPLETE_COVERAGE")
        with self.transaction(write=True) as connection:
            connection.execute(
                "LOCK TABLE documents,chunks,herbs,herb_aliases,medical_conditions,"
                "medical_condition_synonyms IN SHARE MODE"
            )
            if source_manifest(connection) != data.manifest:
                raise unavailable(True)
            state = connection.execute(
                "SELECT status FROM herb_safety_runs WHERE run_id=%s FOR UPDATE", (run_id,)
            ).fetchone()
            if state != ("preparing",):
                raise ValueError("HERB_SAFETY_RUN_IMMUTABLE")
            connection.execute("DELETE FROM herb_safety_analysis WHERE run_id=%s", (run_id,))
            connection.execute("DELETE FROM herb_safety_warnings WHERE run_id=%s", (run_id,))
            with connection.cursor() as cursor:
                for target in data.targets:
                    checkpoint()
                    result = results[target.identity]
                    cursor.execute(
                        "INSERT INTO herb_safety_analysis(run_id,identity,herb_id,chunk_id,status,"
                        "mandatory,cache_key) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                        (
                            run_id,
                            target.identity,
                            target.herb_id,
                            target.chunk_id,
                            result.status,
                            target.identity in mandatory,
                            target.cache_key(semantic, digest)
                            if result.status in {"complete", "unclear"}
                            else None,
                        ),
                    )
                    for warning in result.items:
                        if (
                            not warning.summary
                            or len(warning.summary) > SUMMARY_MAX_CHARS
                            or warning.focus_start is None
                            or warning.focus_end is None
                        ):
                            raise ValueError("HERB_SAFETY_MISSING_DISPLAY_EVIDENCE")
                        identifier = warning.identity(target.herb_id)
                        cursor.execute(
                            "INSERT INTO herb_safety_warnings(run_id,warning_id,herb_id,kind,text,"
                            "partners) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (
                                run_id,
                                identifier,
                                target.herb_id,
                                warning.kind,
                                warning.summary,
                                Jsonb(warning.partners),
                            ),
                        )
                        cursor.execute(
                            "INSERT INTO herb_safety_evidence(run_id,warning_id,herb_id,identity,"
                            "chunk_id,quote_start,quote_end,source_hash,text_hash,heading_hash,"
                            "quote_text,focus_start,focus_end) "
                            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                            "ON CONFLICT DO NOTHING",
                            (
                                run_id,
                                identifier,
                                target.herb_id,
                                target.identity,
                                target.chunk_id,
                                warning.start,
                                warning.end,
                                target.source_hash,
                                target.text_hash,
                                content_hash(target.heading),
                                warning.text,
                                warning.focus_start,
                                warning.focus_end,
                            ),
                        )
            evidence_hash = evidence_digest(connection, run_id)
            assert_integrity(connection, run_id, len(data.targets), evidence_hash)
            connection.execute(
                "UPDATE herb_safety_runs SET status='ready',evidence_hash=%s,"
                "counters=counters || %s WHERE run_id=%s",
                (evidence_hash, Jsonb(counters), run_id),
            )

    def publish(self, run_id: str, settings: Settings) -> None:
        UUID(run_id)
        with self.transaction(write=True) as connection:
            connection.execute(
                "LOCK TABLE documents,chunks,herbs,herb_aliases,medical_conditions,"
                "medical_condition_synonyms,sync_metadata IN SHARE MODE"
            )
            row = connection.execute(
                "SELECT status,manifest,semantic,expected_active::text,expected_count,evidence_hash "
                "FROM herb_safety_runs WHERE run_id=%s FOR UPDATE",
                (run_id,),
            ).fetchone()
            if row is None or row[0] != "ready":
                raise unavailable()
            if row[1] != source_manifest(connection) or row[2] != safety_semantic(settings):
                raise unavailable(True)
            assert_integrity(connection, run_id, row[4], row[5])
            current = connection.execute(
                "SELECT run_id::text FROM herb_safety_runs WHERE is_active"
            ).fetchone()
            active = current[0] if current else None
            if active == run_id:
                return
            if active != row[3]:
                raise ValueError("HERB_SAFETY_PUBLICATION_CONFLICT")
            connection.execute("UPDATE herb_safety_runs SET is_active=false WHERE is_active")
            connection.execute(
                "UPDATE herb_safety_runs SET is_active=true WHERE run_id=%s", (run_id,)
            )
