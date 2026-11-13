-- BM25 lexical index (ParadeDB pg_search) next to the pgvector and GIN indexes. The fragment
-- text and heading are indexed once per language with that language's stemmer; accents are
-- folded by the tokenizer, so neither the index nor the question needs unaccent(). The
-- chunks.text_search column and its GIN index were dropped by migration 045.
-- Safe to run more than once.
CREATE EXTENSION IF NOT EXISTS pg_search;

CREATE INDEX IF NOT EXISTS idx_chunks_bm25 ON chunks USING bm25 (
    chunk_id,
    (text::pdb.simple('stemmer=romanian', 'ascii_folding=true', 'alias=text_ro')),
    (text::pdb.simple('stemmer=english', 'ascii_folding=true', 'alias=text_en')),
    (heading::pdb.simple('stemmer=romanian', 'ascii_folding=true', 'alias=heading_ro')),
    (heading::pdb.simple('stemmer=english', 'ascii_folding=true', 'alias=heading_en'))
);
