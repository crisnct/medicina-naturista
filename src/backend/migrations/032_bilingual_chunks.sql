-- Existing data is Romanian. New importers always supply the root's explicit language.
ALTER TABLE chunks ADD COLUMN language TEXT NOT NULL DEFAULT 'ro'
    CHECK (language IN ('ro','en'));
COMMENT ON COLUMN chunks.language IS 'Source corpus language, assigned by the configured ro/en root.';

-- The namespace prevents source collisions without becoming a visible category.
ALTER TABLE chunks DROP COLUMN category_id;
ALTER TABLE documents DROP COLUMN category_id;
ALTER TABLE documents ADD COLUMN category_id TEXT GENERATED ALWAYS AS (
    CASE WHEN regexp_replace(relative_path, '^(ro|en)/', '') LIKE '%/%'
         THEN regexp_replace(regexp_replace(relative_path, '^(ro|en)/', ''), '/[^/]*$', '')
         ELSE '' END
) STORED;
ALTER TABLE chunks ADD COLUMN category_id TEXT GENERATED ALWAYS AS (
    CASE WHEN regexp_replace(source_relative_path, '^(ro|en)/', '') LIKE '%/%'
         THEN regexp_replace(regexp_replace(source_relative_path, '^(ro|en)/', ''), '/[^/]*$', '')
         ELSE '' END
) STORED;
COMMENT ON COLUMN documents.category_id IS 'Containing folder excluding the corpus language namespace.';
COMMENT ON COLUMN chunks.category_id IS 'Containing folder excluding the corpus language namespace.';
CREATE INDEX idx_documents_category ON documents(category_id);
CREATE INDEX idx_chunks_category ON chunks(category_id);
CREATE INDEX idx_chunks_language_category ON chunks(language,category_id);
