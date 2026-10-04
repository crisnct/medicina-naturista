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

from backend.ai.embedding_model import DEFAULT_MODEL, get_profile
from backend.config import settings

# Vector width of a table created without an explicit dimension.
DEFAULT_DIMENSION = get_profile(DEFAULT_MODEL).dimension

# __DIMENSION__ is the embedding model's vector width (see ensure_schema()).
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
    embedding             vector(__DIMENSION__) NOT NULL,
    text_search           tsvector NOT NULL,
    business_category     TEXT CHECK (business_category IN ('R1', 'R2', 'D1')),
    primary_medical_conditions   TEXT[] NOT NULL DEFAULT '{}',
    secondary_medical_conditions TEXT[] NOT NULL DEFAULT '{}'
);
-- business_category (R1/R2/D1) and the two condition columns (canonical names
-- from medical_conditions.txt found in the fragment's title / in its text) are
-- filled by ai/fragmenter.py. They replace the old `conditions` column;
-- existing databases get them here and are refilled by the next index sync,
-- which is why business_category stays nullable (there is no honest default for
-- a row written before it existed). Priority is not stored: it is decided per
-- search (ai/search.py).
ALTER TABLE chunks DROP COLUMN IF EXISTS priority;
ALTER TABLE chunks DROP COLUMN IF EXISTS conditions;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS business_category TEXT
    CHECK (business_category IN ('R1', 'R2', 'D1'));
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS primary_medical_conditions TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS secondary_medical_conditions TEXT[] NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS idx_chunks_business_category ON chunks(business_category);
CREATE INDEX IF NOT EXISTS idx_chunks_primary_conditions ON chunks USING GIN(primary_medical_conditions);
CREATE INDEX IF NOT EXISTS idx_chunks_secondary_conditions ON chunks USING GIN(secondary_medical_conditions);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_relative_path, line_start);
CREATE INDEX IF NOT EXISTS idx_chunks_category ON chunks(category_id);
CREATE INDEX IF NOT EXISTS idx_chunks_text_search ON chunks USING GIN(text_search);

CREATE TABLE IF NOT EXISTS sync_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_pool: ConnectionPool | None = None


# Configure pgvector's numpy<->vector adapter on every pooled connection.
def _configure_connection(conn: Connection) -> None:
    from pgvector.psycopg import register_vector

    register_vector(conn)


# Width of the vector column of `chunks`, or None when the table does not exist.
def _embedding_dimension(connection: Connection) -> int | None:
    row = connection.execute(
        """
        SELECT a.atttypmod FROM pg_attribute a
        WHERE a.attrelid = to_regclass('chunks') AND a.attname = 'embedding' AND NOT a.attisdropped
        """
    ).fetchone()
    return row[0] if row else None


# Create every extension/table/index the hybrid index needs, if not already
# present. Uses a raw, unpooled connection — deliberately not get_pool() —
# because the pool's own connections register pgvector's `vector` type on
# open (see _configure_connection), which fails until CREATE EXTENSION
# vector has actually run. This must complete before the pool ever opens
# its first connection.
#
# `dimension` is the vector width the caller is about to write. When the
# existing `embedding` column has another width (a model change), the column is
# recreated and every indexed document is dropped, in one transaction: vectors
# of two widths (or two models) cannot share an index, and the index is fully
# rebuildable from the source documents. Only the index build passes it; the web
# app calls ensure_schema() without one and never touches existing data.
def ensure_schema(dimension: int | None = None) -> None:
    width = int(dimension or DEFAULT_DIMENSION)
    with psycopg.connect(settings.database_url) as connection:
        connection.execute(SCHEMA_SQL.replace("__DIMENSION__", str(width)))
        if dimension is not None:
            current = _embedding_dimension(connection)
            if current != width:
                # DELETE first so the new column can be NOT NULL: it cannot be
                # added as such to a table that still has rows.
                connection.execute("DELETE FROM documents")
                connection.execute("DELETE FROM sync_metadata")
                connection.execute("ALTER TABLE chunks DROP COLUMN embedding")
                connection.execute(f"ALTER TABLE chunks ADD COLUMN embedding vector({width})")
                connection.execute("ALTER TABLE chunks ALTER COLUMN embedding SET NOT NULL")
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
