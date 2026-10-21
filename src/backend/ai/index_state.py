"""One PostgreSQL advisory lock and compatibility contract for the index."""

from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar

import psycopg
from pydantic import BaseModel

from backend.ai import db, index_constants
from backend.ai.condition_repository import (
    FINGERPRINT_VERSION,
    CatalogUnavailable,
    catalog_snapshot,
)
from backend.ai.embedding_model import get_profile
from backend.core.errors import ApplicationError
from backend.core.texts import tr

INDEX_LOCK = 7261040202
_reader: ContextVar[tuple[psycopg.Connection, IndexMetadata] | None] = ContextVar(
    "index_reader", default=None
)
_dictionary = ContextVar("index_dictionary", default=None)


def active_dictionary():
    return _dictionary.get()


class IndexUnavailable(ApplicationError):
    def __init__(self, code="INDEX_MAINTENANCE"):
        super().__init__(code, tr("errors.index_unavailable"), 503)


class IndexMetadata(BaseModel):
    model_name: str
    model_dimension: int
    dictionary_fingerprint: str
    dictionary_fingerprint_version: int
    passage_profile: str
    text_repr_version: str
    index_generation: str


def passage_profile(profile) -> str:
    return json.dumps(
        [profile.passage_template, profile.max_chars, profile.overlap_chars], separators=(",", ":")
    )


def dictionary_snapshot(connection=None):
    if connection is not None:
        snapshot = catalog_snapshot(connection)
        return snapshot.fingerprint, snapshot.dictionary
    try:
        with db.get_pool().connection() as connection:
            with connection.transaction():
                if not connection.execute(
                    "SELECT pg_try_advisory_xact_lock_shared(%s)", (INDEX_LOCK,)
                ).fetchone()[0]:
                    raise IndexUnavailable()
                snapshot = catalog_snapshot(connection)
                return snapshot.fingerprint, snapshot.dictionary
    except psycopg.Error:
        raise IndexUnavailable("INDEX_UNAVAILABLE") from None


def read_metadata(connection, fingerprint=None) -> IndexMetadata:
    try:
        metadata = IndexMetadata.model_validate(
            dict(connection.execute("SELECT key, value FROM sync_metadata").fetchall())
        )
        profile = get_profile(metadata.model_name)
        if fingerprint is None:
            fingerprint, _ = dictionary_snapshot(connection)
        if (
            metadata.dictionary_fingerprint != fingerprint
            or metadata.dictionary_fingerprint_version != FINGERPRINT_VERSION
            or metadata.model_dimension != profile.dimension
            or metadata.passage_profile != passage_profile(profile)
            or metadata.text_repr_version != index_constants.TEXT_REPR_VERSION
            or db._embedding_dimension(connection) != metadata.model_dimension
        ):
            raise IndexUnavailable("INDEX_RESYNC_REQUIRED")
        return metadata
    except (ValueError, OSError, UnicodeError):
        raise IndexUnavailable("INDEX_RESYNC_REQUIRED") from None


@contextmanager
def index_reader():
    """Nested readers share one connection, transaction and generation."""
    active = _reader.get()
    if active is not None:
        yield active
        return
    try:
        with db.get_pool().connection() as connection:
            with connection.transaction():
                lock_row = connection.execute(
                    "SELECT pg_try_advisory_xact_lock_shared(%s)", (INDEX_LOCK,)
                ).fetchone()
                locked = lock_row is not None and lock_row[0]
                if not locked:
                    raise IndexUnavailable()
                try:
                    fingerprint, dictionary = dictionary_snapshot(connection)
                except (CatalogUnavailable, ValueError, UnicodeError):
                    raise IndexUnavailable("INDEX_RESYNC_REQUIRED") from None
                metadata = read_metadata(connection, fingerprint)
                token = _reader.set((connection, metadata))
                dictionary_token = _dictionary.set(dictionary)
                try:
                    yield connection, metadata
                    unchanged = dictionary_snapshot(connection)[0] == fingerprint
                    if not unchanged:
                        raise IndexUnavailable("INDEX_RESYNC_REQUIRED")
                finally:
                    _dictionary.reset(dictionary_token)
                    _reader.reset(token)
    except psycopg.Error:
        raise IndexUnavailable("INDEX_UNAVAILABLE") from None


@contextmanager
def index_writer(*, lock_timeout_ms: int | None = None):
    """Dedicated connection: session lock survives preparation transactions."""
    with psycopg.connect(db.settings.database_url, autocommit=True) as connection:
        if lock_timeout_ms is not None:
            if lock_timeout_ms <= 0:
                raise ValueError("INVALID_INDEX_LOCK_TIMEOUT")
            connection.execute(
                "SELECT set_config('lock_timeout', %s, false)", (str(lock_timeout_ms),)
            )
        connection.execute("SELECT pg_advisory_lock(%s)", (INDEX_LOCK,))
        try:
            db._configure_connection(connection)
            yield connection
        finally:
            # Closing the dedicated connection also releases a lock after a disconnect.
            if not connection.closed and not connection.broken:
                connection.execute("SELECT pg_advisory_unlock(%s)", (INDEX_LOCK,))
