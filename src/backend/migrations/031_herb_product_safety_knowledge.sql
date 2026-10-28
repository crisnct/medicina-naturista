-- Model-knowledge safety is versioned independently of corpus-derived evidence and rankings.
CREATE TABLE herb_product_safety_runs (
    run_id UUID PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('preparing','ready')),
    catalog_hash TEXT NOT NULL CHECK (length(catalog_hash)=64),
    semantic JSONB NOT NULL CHECK (jsonb_typeof(semantic)='object'),
    model_digest TEXT NOT NULL CHECK (length(model_digest)>=64),
    expected_active UUID,
    expected_count INTEGER NOT NULL CHECK (expected_count>=0),
    response_hash TEXT CHECK (length(response_hash)=64),
    request_count INTEGER NOT NULL DEFAULT 0 CHECK (request_count>=0),
    is_active BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (status<>'ready' OR response_hash IS NOT NULL),
    CHECK (NOT is_active OR status='ready')
);
CREATE UNIQUE INDEX herb_product_safety_one_active ON herb_product_safety_runs (is_active)
WHERE is_active;

CREATE TABLE herb_product_safety_cache (
    cache_key TEXT PRIMARY KEY CHECK (length(cache_key)=64),
    herb_id INTEGER NOT NULL REFERENCES herbs ON DELETE CASCADE,
    semantic JSONB NOT NULL CHECK (jsonb_typeof(semantic)='object'),
    model_digest TEXT NOT NULL CHECK (length(model_digest)>=64),
    response JSONB NOT NULL CHECK (jsonb_typeof(response)='object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (cache_key,herb_id)
);

CREATE TABLE herb_product_safety_results (
    run_id UUID NOT NULL REFERENCES herb_product_safety_runs ON DELETE CASCADE,
    herb_id INTEGER NOT NULL REFERENCES herbs ON DELETE CASCADE,
    cache_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('complete','uncertain')),
    PRIMARY KEY (run_id,herb_id),
    FOREIGN KEY (cache_key,herb_id) REFERENCES herb_product_safety_cache (cache_key,herb_id)
);

CREATE TABLE herb_safety_messages (
    run_id UUID NOT NULL,
    herb_id INTEGER NOT NULL REFERENCES herbs ON DELETE CASCADE,
    message_id TEXT NOT NULL CHECK (length(message_id)=64),
    message_type TEXT NOT NULL CHECK (message_type IN ('warning','contraindication','interaction')),
    problem TEXT NOT NULL CHECK (
        length(btrim(problem))>0 AND char_length(problem)<=240 AND problem !~ E'[\r\n]'
    ),
    PRIMARY KEY (run_id,herb_id,message_id),
    FOREIGN KEY (run_id,herb_id) REFERENCES herb_product_safety_results ON DELETE CASCADE
);
CREATE INDEX herb_safety_messages_by_product ON herb_safety_messages (herb_id,run_id,message_type);

COMMENT ON TABLE herb_safety_messages IS 'Concise AI-knowledge safety messages; not corpus citations or clinical validation.';
COMMENT ON COLUMN herb_safety_messages.run_id IS 'Prepared or published safety generation.';
COMMENT ON COLUMN herb_safety_messages.herb_id IS 'Unchanged product identity from herbs.';
COMMENT ON COLUMN herb_safety_messages.message_id IS 'Exact message deduplication hash preserving doses and qualifiers.';
COMMENT ON COLUMN herb_safety_messages.message_type IS 'Warning, contraindication or interaction.';
COMMENT ON COLUMN herb_safety_messages.problem IS 'Short Romanian message, independent of local documents.';
COMMENT ON TABLE herb_product_safety_runs IS 'Atomic publication of model-knowledge answers for the entire herbs catalog.';
COMMENT ON COLUMN herb_product_safety_runs.run_id IS 'Technical generation identifier.';
COMMENT ON COLUMN herb_product_safety_runs.status IS 'Preparation or completed validation state.';
COMMENT ON COLUMN herb_product_safety_runs.catalog_hash IS 'Product identities and aliases, excluding corpus and rankings.';
COMMENT ON COLUMN herb_product_safety_runs.semantic IS 'Prompt, validator and model semantics.';
COMMENT ON COLUMN herb_product_safety_runs.model_digest IS 'Verified local model weights digest.';
COMMENT ON COLUMN herb_product_safety_runs.expected_active IS 'Optimistic publication predecessor.';
COMMENT ON COLUMN herb_product_safety_runs.expected_count IS 'Number of catalog products requiring a result, including empty answers.';
COMMENT ON COLUMN herb_product_safety_runs.response_hash IS 'Integrity digest of results and messages.';
COMMENT ON COLUMN herb_product_safety_runs.request_count IS 'Admitted requests across resumptions; one per uncached product.';
COMMENT ON COLUMN herb_product_safety_runs.is_active IS 'Independent safety activation pointer.';
COMMENT ON COLUMN herb_product_safety_runs.created_at IS 'Technical creation timestamp.';
COMMENT ON TABLE herb_product_safety_cache IS 'Validated per-product answers, including uncertain and explicit empty answers.';
COMMENT ON COLUMN herb_product_safety_cache.cache_key IS 'Product identity, prompt, validator and model digest hash.';
COMMENT ON COLUMN herb_product_safety_cache.herb_id IS 'Product owning this cached answer.';
COMMENT ON COLUMN herb_product_safety_cache.semantic IS 'Safety generation semantics.';
COMMENT ON COLUMN herb_product_safety_cache.model_digest IS 'Verified local model weights digest.';
COMMENT ON COLUMN herb_product_safety_cache.response IS 'Strictly validated JSON answer, without local source fragments.';
COMMENT ON COLUMN herb_product_safety_cache.created_at IS 'Technical validation timestamp.';
COMMENT ON TABLE herb_product_safety_results IS 'A result for every product, distinguishing empty knowledge from missing data.';
COMMENT ON COLUMN herb_product_safety_results.run_id IS 'Owning safety generation.';
COMMENT ON COLUMN herb_product_safety_results.herb_id IS 'Catalog product.';
COMMENT ON COLUMN herb_product_safety_results.cache_key IS 'Validated reusable answer.';
COMMENT ON COLUMN herb_product_safety_results.status IS 'Completed model analysis or explicitly uncertain knowledge.';
