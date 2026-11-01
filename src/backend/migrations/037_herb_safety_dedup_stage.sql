-- The local-model deduplication of a product's messages is cached beside the generation stages.
ALTER TABLE herb_product_safety_extension_cache
    DROP CONSTRAINT herb_product_safety_extension_cache_stage_check;
ALTER TABLE herb_product_safety_extension_cache
    ADD CONSTRAINT herb_product_safety_extension_cache_stage_check
    CHECK (stage IN ('qwen','deepseek','dedup'));

COMMENT ON COLUMN herb_product_safety_extension_cache.stage IS 'Model stage that produced the answer: local qwen, external deepseek, or the local qwen grouping of equivalent messages (dedup).';
