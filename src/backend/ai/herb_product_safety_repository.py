"""Cache per-product knowledge and publish complete catalog generations atomically."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from backend.ai import db
from backend.ai.herb_association_rules import content_hash
from backend.ai.herb_positive_repository import PositiveRepository
from backend.ai.herb_product_safety import (
    BilingualResult,
    ProductSafetyResult,
    Stage,
    catalog_identity,
    product_cache_key,
    semantic_is_current,
    stage_cache_key,
    validate_bilingual_product,
    validate_dedup_groups,
    validate_product_response,
)
from backend.ai.herb_repository import read_herbs
from backend.ai.herb_safety_repository import unavailable
from backend.ai.herbs import Herb
from backend.ai.index_state import IndexUnavailable
from backend.config import Settings
from backend.core.contracts import HerbCautionStatus, HerbLookupResult
from backend.core.language import current_language
from backend.core.operation_context import checkpoint

WRITE_LOCK_ATTEMPTS = 12
WRITE_LOCK_WAIT_SECONDS = 5


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
        or not semantic_is_current(row[3], settings)
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

    # A write needs the exclusive index lock, which any reader (the web app) holds for a moment;
    # a build must not fail on such a moment, so only writes wait for it.
    @contextmanager
    def transaction(self, *, write: bool = False) -> Iterator[Connection]:
        with ExitStack() as stack:
            for attempt in range(1, WRITE_LOCK_ATTEMPTS + 1):
                try:
                    connection = stack.enter_context(
                        PositiveRepository(self.pool).transaction(write=write)
                    )
                    break
                except IndexUnavailable:
                    if not write or attempt == WRITE_LOCK_ATTEMPTS:
                        raise
                    time.sleep(WRITE_LOCK_WAIT_SECONDS)
                    checkpoint()
            yield connection

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
        *,
        key: str | None = None,
    ) -> ProductSafetyResult:
        result = validate_product_response(result.payload(), herb.id)
        key = key or product_cache_key(herb, semantic, digest)
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
            if row[1] != catalog_identity(read_herbs(connection)) or not semantic_is_current(
                row[2], settings
            ):
                raise unavailable(True)
            assert_integrity(connection, run_id, row[4], row[5])
            active = connection.execute(
                "SELECT run_id::text FROM herb_product_safety_runs WHERE is_active AND language=%s",
                (current_language(),),
            ).fetchone()
            current = active[0] if active else None
            if current != run_id:
                if current != row[3]:
                    raise ValueError("HERB_PRODUCT_SAFETY_PUBLICATION_CONFLICT")
                connection.execute(
                    "UPDATE herb_product_safety_runs SET is_active=false "
                    "WHERE is_active AND language=%s",
                    (current_language(),),
                )
                connection.execute(
                    "UPDATE herb_product_safety_runs SET is_active=true WHERE run_id=%s",
                    (run_id,),
                )
            # Only the active generation is read; the superseded ones and the unfinished runs
            # older than it (they were not resumable, or a newer run was started) only take space.
            # Their results and messages go with them (ON DELETE CASCADE).
            connection.execute(
                "DELETE FROM herb_product_safety_runs WHERE language=%s AND NOT is_active "
                "AND (status='ready' OR created_at < (SELECT created_at "
                "FROM herb_product_safety_runs WHERE run_id=%s))",
                (current_language(), run_id),
            )

    # --- Bilingual extension: stage answers are cached per product and serve both languages. ---

    def extension_schema_available(self) -> bool:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT to_regclass('herb_product_safety_extension_cache')"
            ).fetchone()
            return bool(row and row[0])

    def stage_digest(self, stage: Stage | Literal["dedup"], semantic: dict[str, Any]) -> str | None:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT model_digest FROM herb_product_safety_extension_cache "
                "WHERE stage=%s AND semantic=%s ORDER BY created_at DESC LIMIT 1",
                (stage, Jsonb(semantic)),
            ).fetchone()
            return row[0] if row else None

    def cached_stage(
        self,
        herbs: tuple[Herb, ...],
        stage: Stage,
        semantic: dict[str, Any],
        digest: str | None,
    ) -> dict[int, BilingualResult]:
        keys = {stage_cache_key(herb, semantic, digest): herb.id for herb in herbs}
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT cache_key,response FROM herb_product_safety_extension_cache "
                "WHERE stage=%s AND cache_key=ANY(%s)",
                (stage, list(keys)),
            ).fetchall()
        return {keys[key]: validate_bilingual_product(raw, keys[key]) for key, raw in rows}

    # Valid products of a batch are kept even when the rest of the batch is rejected.
    def save_stage(
        self,
        stage: Stage,
        answers: list[tuple[Herb, BilingualResult]],
        semantic: dict[str, Any],
        digest: str | None,
    ) -> dict[int, BilingualResult]:
        saved: dict[int, BilingualResult] = {}
        with self.transaction(write=True) as connection:
            for herb, answer in answers:
                checkpoint()
                answer = validate_bilingual_product(answer.payload(), herb.id)
                key = stage_cache_key(herb, semantic, digest)
                connection.execute(
                    "INSERT INTO herb_product_safety_extension_cache"
                    "(cache_key,herb_id,stage,semantic,model_digest,response) "
                    "VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (key, herb.id, stage, Jsonb(semantic), digest, Jsonb(answer.payload())),
                )
                canonical = connection.execute(
                    "SELECT response FROM herb_product_safety_extension_cache WHERE cache_key=%s",
                    (key,),
                ).fetchone()
                assert canonical is not None
                saved[herb.id] = validate_bilingual_product(canonical[0], herb.id)
        return saved

    # The newest unfinished run with identical inputs, if it still has the active run as predecessor.
    def resumable_run(
        self, semantic: dict[str, Any], digest: str, herbs: tuple[Herb, ...]
    ) -> str | None:
        language = current_language()
        with self.transaction() as connection:
            if not schema_available(connection):
                return None
            row = connection.execute(
                "SELECT run_id::text FROM herb_product_safety_runs WHERE status='preparing' "
                "AND language=%s AND semantic=%s AND model_digest=%s AND catalog_hash=%s "
                "AND expected_active IS NOT DISTINCT FROM (SELECT run_id FROM "
                "herb_product_safety_runs WHERE is_active AND language=%s) "
                "ORDER BY created_at DESC LIMIT 1",
                (language, Jsonb(semantic), digest, catalog_identity(herbs), language),
            ).fetchone()
            return row[0] if row else None

    def run_language(self, run_id: str) -> str | None:
        UUID(run_id)
        with self.transaction() as connection:
            if not schema_available(connection):
                return None
            row = connection.execute(
                "SELECT language FROM herb_product_safety_runs WHERE run_id=%s", (run_id,)
            ).fetchone()
            return row[0] if row else None

    def run_state(self, run_id: str) -> str | None:
        UUID(run_id)
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT status FROM herb_product_safety_runs WHERE run_id=%s", (run_id,)
            ).fetchone()
            return row[0] if row else None

    # Products outside the scope keep the exact published answer of the active generation.
    def copy_active(self, run_id: str, herb_ids: list[int]) -> int:
        UUID(run_id)
        if not herb_ids:
            return 0
        with self.transaction(write=True) as connection:
            state = connection.execute(
                "SELECT status FROM herb_product_safety_runs WHERE run_id=%s FOR UPDATE",
                (run_id,),
            ).fetchone()
            if state != ("preparing",):
                raise ValueError("HERB_PRODUCT_SAFETY_NOT_PREPARING")
            active = connection.execute(
                "SELECT run_id::text FROM herb_product_safety_runs WHERE is_active AND language=%s",
                (current_language(),),
            ).fetchone()
            if active is None:
                raise ValueError("HERB_PRODUCT_SAFETY_NO_ACTIVE_RUN")
            connection.execute(
                "DELETE FROM herb_safety_messages WHERE run_id=%s AND herb_id=ANY(%s)",
                (run_id, herb_ids),
            )
            connection.execute(
                "DELETE FROM herb_product_safety_results WHERE run_id=%s AND herb_id=ANY(%s)",
                (run_id, herb_ids),
            )
            copied = connection.execute(
                "INSERT INTO herb_product_safety_results(run_id,herb_id,cache_key,status) "
                "SELECT %s,herb_id,cache_key,status FROM herb_product_safety_results "
                "WHERE run_id=%s AND herb_id=ANY(%s)",
                (run_id, active[0], herb_ids),
            ).rowcount
            if copied != len(herb_ids):
                raise ValueError("HERB_PRODUCT_SAFETY_ACTIVE_RESULTS_INCOMPLETE")
            connection.execute(
                "INSERT INTO herb_safety_messages(run_id,herb_id,message_id,message_type,problem) "
                "SELECT %s,herb_id,message_id,message_type,problem FROM herb_safety_messages "
                "WHERE run_id=%s AND herb_id=ANY(%s)",
                (run_id, active[0], herb_ids),
            )
        return copied

    def has_active(self) -> bool:
        with self.transaction() as connection:
            if not schema_available(connection):
                return False
            row = connection.execute(
                "SELECT 1 FROM herb_product_safety_runs WHERE is_active AND language=%s",
                (current_language(),),
            ).fetchone()
            return row is not None

    # Model-found groups of equivalent messages, keyed per product by the exact list grouped.
    def cached_dedup(self, keys: dict[str, int]) -> dict[int, list[list[int]]]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT cache_key,response FROM herb_product_safety_extension_cache "
                "WHERE stage='dedup' AND cache_key=ANY(%s)",
                (list(keys),),
            ).fetchall()
        return {keys[key]: validate_dedup_groups(raw["groups"], raw["size"]) for key, raw in rows}

    def save_dedup(
        self,
        items: list[tuple[int, str, int, list[list[int]]]],
        semantic: dict[str, Any],
        digest: str,
    ) -> None:
        with self.transaction(write=True) as connection:
            for herb_id, key, size, groups in items:
                checkpoint()
                response = {"size": size, "groups": validate_dedup_groups(groups, size)}
                connection.execute(
                    "INSERT INTO herb_product_safety_extension_cache"
                    "(cache_key,herb_id,stage,semantic,model_digest,response) "
                    "VALUES(%s,%s,'dedup',%s,%s,%s) ON CONFLICT DO NOTHING",
                    (key, herb_id, Jsonb(semantic), digest, Jsonb(response)),
                )
