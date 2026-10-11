"""One PostgreSQL advisory lock and compatibility contract for the index."""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar

import psycopg
from pydantic import BaseModel

from backend.ai import db
from backend.ai.conditions import dictionary_from_bytes
from backend.ai.embedding_model import get_profile
from backend.config import settings
from backend.core.errors import ApplicationError

INDEX_LOCK = 7261040202
TEXT_REPR_VERSION = "10"
_reader = ContextVar("index_reader", default=None)
_dictionary = ContextVar("index_dictionary", default=None)

def active_dictionary():
    return _dictionary.get()


class IndexUnavailable(ApplicationError):
    def __init__(self, code="INDEX_MAINTENANCE"):
        super().__init__(code, "Indexul este temporar indisponibil. Încercați din nou după resincronizare.", 503)


class IndexMetadata(BaseModel):
    model_name: str
    model_dimension: int
    dictionary_fingerprint: str
    passage_profile: str
    text_repr_version: str
    index_generation: str


def passage_profile(profile) -> str:
    return json.dumps([profile.passage_template, profile.max_chars, profile.overlap_chars], separators=(",", ":"))


def dictionary_snapshot():
    raw = settings.conditions_file.read_bytes()
    return hashlib.sha256(raw).hexdigest(), dictionary_from_bytes(raw)


def read_metadata(connection, fingerprint=None) -> IndexMetadata:
    try:
        metadata = IndexMetadata.model_validate(dict(connection.execute("SELECT key, value FROM sync_metadata").fetchall()))
        profile = get_profile(metadata.model_name)
        if fingerprint is None:
            fingerprint, _ = dictionary_snapshot()
        if (metadata.dictionary_fingerprint != fingerprint
                or metadata.model_dimension != profile.dimension
                or metadata.passage_profile != passage_profile(profile)
                or metadata.text_repr_version != TEXT_REPR_VERSION
                or db._embedding_dimension(connection) != metadata.model_dimension):
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
                locked = connection.execute("SELECT pg_try_advisory_xact_lock_shared(%s)", (INDEX_LOCK,)).fetchone()[0]
                if not locked:
                    raise IndexUnavailable()
                try:
                    fingerprint, dictionary = dictionary_snapshot()
                except (OSError, ValueError, UnicodeError):
                    raise IndexUnavailable("INDEX_RESYNC_REQUIRED") from None
                metadata = read_metadata(connection, fingerprint)
                token = _reader.set((connection, metadata))
                dictionary_token = _dictionary.set(dictionary)
                try:
                    yield connection, metadata
                    try:
                        unchanged = hashlib.sha256(settings.conditions_file.read_bytes()).hexdigest() == fingerprint
                    except OSError:
                        unchanged = False
                    if not unchanged:
                        raise IndexUnavailable("INDEX_RESYNC_REQUIRED")
                finally:
                    _dictionary.reset(dictionary_token)
                    _reader.reset(token)
    except psycopg.Error:
        raise IndexUnavailable("INDEX_UNAVAILABLE") from None


@contextmanager
def index_writer():
    """Dedicated connection: session lock survives preparation transactions."""
    with psycopg.connect(db.settings.database_url, autocommit=True) as connection:
        connection.execute("SELECT pg_advisory_lock(%s)", (INDEX_LOCK,))
        try:
            db._configure_connection(connection)
            yield connection
        finally:
            # Closing the dedicated connection also releases a lock after a disconnect.
            if not connection.closed and not connection.broken:
                connection.execute("SELECT pg_advisory_unlock(%s)", (INDEX_LOCK,))
