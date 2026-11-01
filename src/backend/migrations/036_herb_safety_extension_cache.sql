-- One bilingual answer per product and stage serves both languages, so it has no language column.
CREATE TABLE herb_product_safety_extension_cache (
    cache_key TEXT PRIMARY KEY CHECK (length(cache_key)=64),
    herb_id INTEGER NOT NULL REFERENCES herbs ON DELETE CASCADE,
    stage TEXT NOT NULL CHECK (stage IN ('qwen','deepseek')),
    semantic JSONB NOT NULL CHECK (jsonb_typeof(semantic)='object'),
    model_digest TEXT CHECK (model_digest IS NULL OR length(model_digest)>=64),
    response JSONB NOT NULL CHECK (jsonb_typeof(response)='object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX herb_product_safety_extension_cache_by_product
ON herb_product_safety_extension_cache (herb_id,stage);

COMMENT ON TABLE herb_product_safety_extension_cache IS 'Validated bilingual per-product answers of one model stage; merged and projected per language into herb_product_safety_cache.';
COMMENT ON COLUMN herb_product_safety_extension_cache.cache_key IS 'Product identity, stage semantics and model identity hash; independent of batch composition.';
COMMENT ON COLUMN herb_product_safety_extension_cache.herb_id IS 'Product owning this cached answer.';
COMMENT ON COLUMN herb_product_safety_extension_cache.stage IS 'Model stage that produced the answer: local qwen or external deepseek.';
COMMENT ON COLUMN herb_product_safety_extension_cache.semantic IS 'Stage prompt, validator and model semantics.';
COMMENT ON COLUMN herb_product_safety_extension_cache.model_digest IS 'Verified local model weights digest; absent for an external API model.';
COMMENT ON COLUMN herb_product_safety_extension_cache.response IS 'Strictly validated bilingual JSON answer, without local source fragments.';
COMMENT ON COLUMN herb_product_safety_extension_cache.created_at IS 'Technical validation timestamp.';
