
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
    embedding             vector(1024) NOT NULL,
    text_search           tsvector NOT NULL,
    business_category     TEXT CHECK (business_category IN ('R1', 'R2', 'D1')),
    primary_medical_conditions   TEXT[] NOT NULL DEFAULT '{}',
    secondary_medical_conditions TEXT[] NOT NULL DEFAULT '{}'
);
-- business_category (R1/R2/D1) and the two condition columns (canonical names
-- from medical_conditions.jsonl found in the fragment's title / in its text) are
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
