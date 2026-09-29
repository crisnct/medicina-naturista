"""Postgres connection pool and schema for the hybrid retrieval index.

Replaces the old file-based index (embeddings.npy + index.sqlite3 + JSON/JSONL
manifests). `chunks.embedding` (pgvector) is the semantic index; `chunks.text_search`
(tsvector, GIN-indexed) is the lexical index. See scripts/build_hybrid_index.py
for how rows are written and ai/search.py for how they are queried.
"""
from __future__ import annotations

import psycopg
from psycopg import Connection
from psycopg_pool import ConnectionPool

from medicina_naturista.config import settings

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- category_id is never written directly: it's always the containing folder
-- of the path column on the same row (everything before the last "/", or ""
-- when there is none), so a GENERATED column makes it impossible for the two
-- to drift apart — there is no independent value to keep in sync.
CREATE TABLE IF NOT EXISTS documents (
    relative_path   TEXT PRIMARY KEY,
    absolute_path   TEXT NOT NULL,
    size_bytes      BIGINT NOT NULL,
    modified_utc    TIMESTAMPTZ NOT NULL,
    sha256          TEXT NOT NULL,
    encoding        TEXT NOT NULL,
    line_count      INTEGER NOT NULL,
    char_count      INTEGER NOT NULL,
    category_id     TEXT GENERATED ALWAYS AS (
        CASE WHEN relative_path LIKE '%/%'
             THEN regexp_replace(relative_path, '/[^/]*$', '')
             ELSE ''
        END
    ) STORED
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id              BIGSERIAL PRIMARY KEY,
    source_relative_path  TEXT NOT NULL REFERENCES documents(relative_path) ON DELETE CASCADE,
    source_absolute_path  TEXT NOT NULL,
    source_sha256         TEXT NOT NULL,
    line_start            INTEGER NOT NULL,
    line_end              INTEGER NOT NULL,
    heading               TEXT NOT NULL,
    text                  TEXT NOT NULL,
    text_sha256           TEXT NOT NULL,
    char_count            INTEGER NOT NULL,
    category_id           TEXT GENERATED ALWAYS AS (
        CASE WHEN source_relative_path LIKE '%/%'
             THEN regexp_replace(source_relative_path, '/[^/]*$', '')
             ELSE ''
        END
    ) STORED,
    embedding             vector(384) NOT NULL,
    text_search           tsvector NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_relative_path, line_start);
CREATE INDEX IF NOT EXISTS idx_chunks_category ON chunks(category_id);
CREATE INDEX IF NOT EXISTS idx_chunks_text_search ON chunks USING GIN(text_search);

CREATE TABLE IF NOT EXISTS sync_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Afflictions extracted from chunk text (see scripts/build_evidence_index.py,
-- not yet written) plus the fragments that provide treatment evidence for
-- each. Synonyms are not clustered onto a shared canonical entry in v1: every
-- distinct extracted name gets its own affliction row, and query-time nearest-
-- neighbour search over affliction_synonyms.embedding is what lets close
-- variants ("cancer de sân" / "cancer mamar") both surface their evidence.
CREATE TABLE IF NOT EXISTS afflictions (
    id              BIGSERIAL PRIMARY KEY,
    canonical_name  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS affliction_synonyms (
    id             BIGSERIAL PRIMARY KEY,
    affliction_id  BIGINT NOT NULL REFERENCES afflictions(id) ON DELETE CASCADE,
    text           TEXT NOT NULL,
    embedding      vector(384) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_affliction_synonyms_affliction ON affliction_synonyms(affliction_id);

-- evidence_type: 1 = the chunk's heading/section is the affliction itself and
-- the text states a treatment; 2 = the affliction is not the chunk's heading,
-- but the chunk's text links a remedy to it via a benefit/usage statement.
CREATE TABLE IF NOT EXISTS affliction_chunks (
    affliction_id  BIGINT NOT NULL REFERENCES afflictions(id) ON DELETE CASCADE,
    chunk_id       BIGINT NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    evidence_type  SMALLINT NOT NULL CHECK (evidence_type IN (1, 2)),
    PRIMARY KEY (affliction_id, chunk_id)
);
"""

_pool: ConnectionPool | None = None


# Configure pgvector's numpy<->vector adapter on every pooled connection.
def _configure_connection(conn: Connection) -> None:
    from pgvector.psycopg import register_vector

    register_vector(conn)


# Create every extension/table/index the hybrid index needs, if not already
# present. Uses a raw, unpooled connection — deliberately not get_pool() —
# because the pool's own connections register pgvector's `vector` type on
# open (see _configure_connection), which fails until CREATE EXTENSION
# vector has actually run. This must complete before the pool ever opens
# its first connection.
def ensure_schema() -> None:
    with psycopg.connect(settings.database_url) as connection:
        connection.execute(SCHEMA_SQL)
        connection.commit()


# Return the process-wide connection pool, opening it lazily on first use.
# Bootstraps the schema first (see ensure_schema()) so every pooled
# connection can safely register the vector type when it opens.
def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        ensure_schema()
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=5,
            configure=_configure_connection,
            open=True,
        )
    return _pool


# Close and forget the process-wide pool, so the next get_pool() call opens a
# fresh one — used by tests to point db.settings at a different database
# between runs (e.g. an ephemeral testcontainers Postgres).
def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
