-- The local generation stage is no longer tied to one model family: its cached answers are
-- identified by the stage name `ministral`; answers of the earlier local model are discarded.
DELETE FROM herb_product_safety_extension_cache WHERE stage='qwen';
ALTER TABLE herb_product_safety_extension_cache
    DROP CONSTRAINT herb_product_safety_extension_cache_stage_check;
ALTER TABLE herb_product_safety_extension_cache
    ADD CONSTRAINT herb_product_safety_extension_cache_stage_check
    CHECK (stage IN ('ministral','deepseek','dedup'));

COMMENT ON COLUMN herb_product_safety_extension_cache.stage IS 'Stage that produced the answer: the local generation model (ministral), the external deepseek model, or the local grouping of equivalent messages (dedup).';
