"""Cache per-product knowledge and publish complete catalog generations atomically."""

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
from backend.ai.herb_positive_repository import PositiveRepository
from backend.ai.herb_product_safety import (
    ProductSafetyResult,
    catalog_identity,
    product_cache_key,
    product_semantic,
    validate_product_response,
)
from backend.ai.herb_repository import read_herbs
from backend.ai.herb_safety_repository import unavailable
from backend.ai.herbs import Herb
from backend.config import Settings
from backend.core.contracts import HerbCautionStatus, HerbLookupResult
from backend.core.language import current_language
from backend.core.operation_context import checkpoint


def schema_available(connection: Connection) -> bool:
    row = connection.execute("SELECT to_regclass('herb_safety_messages')").fetchone()
    return bool(row and row[0])


def response_digest(connection: Connection, run_id: str) -> str:
    results = connection.execute(
        "SELECT herb_id,cache_key,status FROM herb_product_safety_results "
        "WHERE run_id=%s ORDER BY herb_id",
        (run_id,),
    ).fetchall()
    messages = connection.execute(
        "SELECT herb_id,message_id,message_type,problem FROM herb_safety_messages "
        "WHERE run_id=%s ORDER BY herb_id,message_id",
        (run_id,),
    ).fetchall()
    return content_hash([results, messages])


def assert_integrity(connection: Connection, run_id: str, expected: int, digest: str) -> None:
    count = connection.execute(
        "SELECT count(*) FROM herb_product_safety_results WHERE run_id=%s",
        (run_id,),
    ).fetchone()
    invalid = connection.execute(
        "SELECT EXISTS(SELECT 1 FROM herb_product_safety_results r "
        "JOIN herb_product_safety_cache c USING(cache_key,herb_id) WHERE r.run_id=%s AND ("
        "r.status<>(c.response->>'status') OR "
        "(SELECT count(*) FROM herb_safety_messages m WHERE m.run_id=r.run_id "
        "AND m.herb_id=r.herb_id)<>jsonb_array_length(c.response->'messages') OR "
        "EXISTS(SELECT 1 FROM jsonb_array_elements(c.response->'messages') AS entries(item) "
        "WHERE NOT EXISTS(SELECT 1 FROM herb_safety_messages m WHERE m.run_id=r.run_id "
        "AND m.herb_id=r.herb_id AND m.message_type=(item->>'message_type') "
        "AND m.problem=(item->>'problem')))))",
        (run_id,),
    ).fetchone()
    if count != (expected,) or invalid != (False,) or response_digest(connection, run_id) != digest:
        raise ValueError("HERB_PRODUCT_SAFETY_INCOMPLETE")


def active_product_safety_run(
    connection: Connection,
    settings: Settings,
) -> tuple[str | None, HerbCautionStatus]:
    if not schema_available(connection):
        return None, "not_ready"
    row = connection.execute(
        "SELECT run_id::text,status,catalog_hash,semantic FROM herb_product_safety_runs "
        "WHERE is_active AND language=%s",
        (current_language(),),
    ).fetchone()
    if row is None:
        return None, "not_ready"
    if (
        row[1] != "ready"
        or row[2] != catalog_identity(read_herbs(connection))
        or row[3] != product_semantic(settings)
    ):
        return None, "stale"
    return row[0], "ready"


def safety_metadata(connection: Connection, herb_id: int, settings: Settings) -> HerbLookupResult:
    run_id, status = active_product_safety_run(connection, settings)
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
        row = connection.execute(
            "SELECT r.status,(SELECT count(*) FROM herb_safety_messages m "
            "WHERE m.run_id=r.run_id AND m.herb_id=r.herb_id) "
            "FROM herb_product_safety_results r WHERE r.run_id=%s AND r.herb_id=%s",
            (run_id, herb_id),
        ).fetchone()
        if row is None:
            raise unavailable(True)
        result.update(
            {
                "warningsStatus": "ready" if row[0] == "complete" else "partial",
                "warningsCount": row[1],
            }
        )
    return result


@dataclass(frozen=True)
class ProductSafetyRepository:
    pool: Callable[[], ConnectionPool] = db.get_pool

    def transaction(self, *, write: bool = False) -> AbstractContextManager[Connection]:
        return PositiveRepository(self.pool).transaction(write=write)

    def read_products(self) -> tuple[Herb, ...]:
        with self.transaction() as connection:
            if not schema_available(connection):
                raise unavailable()
            return tuple(sorted(read_herbs(connection), key=lambda herb: herb.id))

    def analysis_digest(self, semantic: dict[str, Any]) -> str | None:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT model_digest FROM herb_product_safety_runs WHERE semantic=%s "
                "ORDER BY created_at DESC LIMIT 1",
                (Jsonb(semantic),),
            ).fetchone()
            return row[0] if row else None

    def cached(
        self,
        herbs: tuple[Herb, ...],
        semantic: dict[str, Any],
        digest: str,
    ) -> dict[int, ProductSafetyResult]:
        keys = {product_cache_key(herb, semantic, digest): herb.id for herb in herbs}
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT cache_key,response FROM herb_product_safety_cache WHERE cache_key=ANY(%s)",
                (list(keys),),
            ).fetchall()
        return {keys[key]: validate_product_response(raw, keys[key]) for key, raw in rows}

    def create_run(
        self,
        run_id: str,
        herbs: tuple[Herb, ...],
        semantic: dict[str, Any],
        digest: str,
        resume: bool,
        *,
        require_existing: bool = False,
    ) -> str:
        UUID(run_id)
        manifest = catalog_identity(herbs)
        with self.transaction(write=True) as connection:
            if catalog_identity(read_herbs(connection)) != manifest:
                raise unavailable(True)
            existing = connection.execute(
                "SELECT status,catalog_hash,semantic,model_digest FROM herb_product_safety_runs "
                "WHERE run_id=%s FOR UPDATE",
                (run_id,),
            ).fetchone()
            if existing:
                if not resume or existing[1:] != (manifest, semantic, digest):
                    raise ValueError("HERB_PRODUCT_SAFETY_RESUME_INPUT_CHANGED")
                return existing[0]
            if require_existing:
                raise ValueError("HERB_PRODUCT_SAFETY_RESUME_NOT_FOUND")
            active = connection.execute(
                "SELECT run_id::text FROM herb_product_safety_runs WHERE is_active AND language=%s",
                (current_language(),),
            ).fetchone()
            connection.execute(
                "INSERT INTO herb_product_safety_runs(run_id,status,catalog_hash,semantic,"
                "model_digest,expected_active,expected_count) VALUES(%s,'preparing',%s,%s,%s,%s,%s)",
                (
                    run_id,
                    manifest,
                    Jsonb(semantic),
                    digest,
                    active[0] if active else None,
                    len(herbs),
                ),
            )
        return "preparing"

    def admit_request(self, run_id: str, limit: int) -> None:
        with self.transaction(write=True) as connection:
            row = connection.execute(
                "UPDATE herb_product_safety_runs SET request_count=request_count+1 "
                "WHERE run_id=%s AND status='preparing' AND request_count<%s RETURNING request_count",
                (run_id, limit),
            ).fetchone()
            if row is None:
                raise ValueError("HERB_PRODUCT_SAFETY_REQUEST_LIMIT")

    def save_result(
        self,
        run_id: str,
        herb: Herb,
        result: ProductSafetyResult,
        semantic: dict[str, Any],
        digest: str,
    ) -> ProductSafetyResult:
        result = validate_product_response(result.payload(), herb.id)
        key = product_cache_key(herb, semantic, digest)
        with self.transaction(write=True) as connection:
            state = connection.execute(
                "SELECT status FROM herb_product_safety_runs WHERE run_id=%s FOR UPDATE",
                (run_id,),
            ).fetchone()
            if state != ("preparing",):
                raise ValueError("HERB_PRODUCT_SAFETY_NOT_PREPARING")
            connection.execute(
                "INSERT INTO herb_product_safety_cache(cache_key,herb_id,semantic,model_digest,response) "
                "VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (key, herb.id, Jsonb(semantic), digest, Jsonb(result.payload())),
            )
            canonical = connection.execute(
                "SELECT response FROM herb_product_safety_cache WHERE cache_key=%s",
                (key,),
            ).fetchone()
            assert canonical is not None
            result = validate_product_response(canonical[0], herb.id)
            connection.execute(
                "INSERT INTO herb_product_safety_results(run_id,herb_id,cache_key,status) "
                "VALUES(%s,%s,%s,%s) ON CONFLICT (run_id,herb_id) DO UPDATE "
                "SET cache_key=excluded.cache_key,status=excluded.status",
                (run_id, herb.id, key, result.status),
            )
            connection.execute(
                "DELETE FROM herb_safety_messages WHERE run_id=%s AND herb_id=%s",
                (run_id, herb.id),
            )
            for message in result.messages:
                checkpoint()
                connection.execute(
                    "INSERT INTO herb_safety_messages(run_id,herb_id,message_id,message_type,problem) "
                    "VALUES(%s,%s,%s,%s,%s)",
                    (run_id, herb.id, message.identity, message.message_type, message.problem),
                )
        return result

    def finish(
        self,
        run_id: str,
        herbs: tuple[Herb, ...],
        semantic: dict[str, Any],
    ) -> None:
        with self.transaction(write=True) as connection:
            row = connection.execute(
                "SELECT catalog_hash,semantic FROM herb_product_safety_runs WHERE run_id=%s FOR UPDATE",
                (run_id,),
            ).fetchone()
            if row != (catalog_identity(herbs), semantic) or row[0] != catalog_identity(
                read_herbs(connection)
            ):
                raise unavailable(True)
            digest = response_digest(connection, run_id)
            assert_integrity(connection, run_id, len(herbs), digest)
            connection.execute(
                "UPDATE herb_product_safety_runs SET status='ready',response_hash=%s WHERE run_id=%s",
                (digest, run_id),
            )

    def is_ready(self, run_id: str) -> bool:
        with self.transaction() as connection:
            if not schema_available(connection):
                return False
            row = connection.execute(
                "SELECT status FROM herb_product_safety_runs WHERE run_id=%s",
                (run_id,),
            ).fetchone()
            return row == ("ready",)

    def publish(self, run_id: str, settings: Settings, *, digest: str) -> None:
        UUID(run_id)
        with self.transaction(write=True) as connection:
            connection.execute("LOCK TABLE herbs,herb_aliases IN SHARE MODE")
            row = connection.execute(
                "SELECT status,catalog_hash,semantic,expected_active::text,expected_count,response_hash,model_digest "
                "FROM herb_product_safety_runs WHERE run_id=%s FOR UPDATE",
                (run_id,),
            ).fetchone()
            if row is None or row[0] != "ready":
                raise unavailable()
            if row[6] != digest:
                raise unavailable(True)
            if row[1] != catalog_identity(read_herbs(connection)) or row[2] != product_semantic(
                settings
            ):
                raise unavailable(True)
            assert_integrity(connection, run_id, row[4], row[5])
            active = connection.execute(
                "SELECT run_id::text FROM herb_product_safety_runs WHERE is_active AND language=%s",
                (current_language(),),
            ).fetchone()
            current = active[0] if active else None
            if current == run_id:
                return
            if current != row[3]:
                raise ValueError("HERB_PRODUCT_SAFETY_PUBLICATION_CONFLICT")
            connection.execute(
                "UPDATE herb_product_safety_runs SET is_active=false WHERE is_active AND language=%s",
                (current_language(),),
            )
            connection.execute(
                "UPDATE herb_product_safety_runs SET is_active=true WHERE run_id=%s",
                (run_id,),
            )
