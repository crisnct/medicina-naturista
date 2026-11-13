-- The lexical search reads the BM25 index (044_bm25_index.sql) only; the tsvector column and its
-- GIN index that served the previous lexical search are no longer written or read.
-- Irreversible: restore a backup to go back. Safe to run more than once.
DROP INDEX IF EXISTS idx_chunks_text_search;
ALTER TABLE chunks DROP COLUMN IF EXISTS text_search;
