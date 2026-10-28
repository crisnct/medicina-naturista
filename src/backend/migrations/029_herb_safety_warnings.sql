-- Product safety is independent of disease classifications and never mutates their decisions.
CREATE TABLE herb_safety_runs (
    run_id UUID PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('preparing','ready')),
    manifest JSONB NOT NULL CHECK (jsonb_typeof(manifest)='object'),
    semantic JSONB NOT NULL CHECK (jsonb_typeof(semantic)='object'),
    model_digest TEXT NOT NULL CHECK (length(model_digest)>=64),
    expected_active UUID,
    expected_count INTEGER NOT NULL CHECK (expected_count>=0),
    counters JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(counters)='object'),
    evidence_hash TEXT CHECK (evidence_hash IS NULL OR length(evidence_hash)=64),
    is_active BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (status<>'ready' OR evidence_hash IS NOT NULL),
    CHECK (NOT is_active OR status='ready')
);
CREATE UNIQUE INDEX herb_safety_one_active ON herb_safety_runs (is_active) WHERE is_active;

CREATE TABLE herb_safety_cache (
    cache_key TEXT PRIMARY KEY CHECK (length(cache_key)=64),
    semantic JSONB NOT NULL CHECK (jsonb_typeof(semantic)='object'),
    model_digest TEXT NOT NULL CHECK (length(model_digest)>=64),
    decision JSONB NOT NULL CHECK (jsonb_typeof(decision)='object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE herb_safety_analysis (
    run_id UUID NOT NULL REFERENCES herb_safety_runs ON DELETE CASCADE,
    identity TEXT NOT NULL CHECK (length(identity)=64),
    herb_id INTEGER NOT NULL REFERENCES herbs ON DELETE CASCADE,
    chunk_id BIGINT NOT NULL REFERENCES chunks ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('complete','unclear','local','uncovered')),
    mandatory BOOLEAN NOT NULL,
    cache_key TEXT REFERENCES herb_safety_cache,
    PRIMARY KEY (run_id,identity),
    UNIQUE (run_id,identity,herb_id,chunk_id),
    UNIQUE (run_id,herb_id,chunk_id),
    CHECK (NOT mandatory OR status IN ('complete','unclear'))
);
CREATE INDEX ON herb_safety_analysis (run_id,herb_id,status);

CREATE TABLE herb_safety_warnings (
    run_id UUID NOT NULL REFERENCES herb_safety_runs ON DELETE CASCADE,
    warning_id TEXT NOT NULL CHECK (length(warning_id)=64),
    herb_id INTEGER NOT NULL REFERENCES herbs ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('high_dose','adverse_effect','drug_interaction','product_interaction','administration','population')),
    text TEXT NOT NULL CHECK (length(btrim(text))>0),
    partners JSONB NOT NULL CHECK (jsonb_typeof(partners)='array'),
    PRIMARY KEY (run_id,warning_id),
    UNIQUE (run_id,warning_id,herb_id)
);
CREATE INDEX ON herb_safety_warnings (run_id,herb_id,warning_id);

CREATE TABLE herb_safety_evidence (
    run_id UUID NOT NULL,
    warning_id TEXT NOT NULL,
    herb_id INTEGER NOT NULL,
    identity TEXT NOT NULL,
    chunk_id BIGINT NOT NULL,
    quote_start INTEGER NOT NULL CHECK (quote_start>=0),
    quote_end INTEGER NOT NULL CHECK (quote_end>quote_start),
    source_hash TEXT NOT NULL CHECK (length(source_hash)=64),
    text_hash TEXT NOT NULL CHECK (length(text_hash)=64),
    heading_hash TEXT NOT NULL CHECK (length(heading_hash)=64),
    PRIMARY KEY (run_id,warning_id,chunk_id,quote_start,quote_end),
    FOREIGN KEY (run_id,warning_id,herb_id) REFERENCES herb_safety_warnings(run_id,warning_id,herb_id) ON DELETE CASCADE,
    FOREIGN KEY (run_id,identity,herb_id,chunk_id) REFERENCES herb_safety_analysis(run_id,identity,herb_id,chunk_id) ON DELETE CASCADE
);
CREATE INDEX ON herb_safety_evidence (run_id,herb_id,warning_id);

COMMENT ON TABLE herb_safety_runs IS 'Versioned local product safety data with source provenance; not clinical validation.';
COMMENT ON COLUMN herb_safety_runs.run_id IS 'Technical safety generation identifier.';
COMMENT ON COLUMN herb_safety_runs.status IS 'Only fully inventoried and validated generations become ready.';
COMMENT ON COLUMN herb_safety_runs.manifest IS 'Source index and catalog fingerprints; excludes activation pointers.';
COMMENT ON COLUMN herb_safety_runs.semantic IS 'Versioned extraction semantics independent of association classification.';
COMMENT ON COLUMN herb_safety_runs.model_digest IS 'Local Ollama model provenance used for safety cache validation.';
COMMENT ON COLUMN herb_safety_runs.expected_active IS 'Active safety pointer observed at preparation for compare-and-swap publication.';
COMMENT ON COLUMN herb_safety_runs.expected_count IS 'Number of distinct product and fragment targets in this inventory.';
COMMENT ON COLUMN herb_safety_runs.counters IS 'Aggregate progress and admitted warning-only requests; no corpus or patient text.';
COMMENT ON COLUMN herb_safety_runs.evidence_hash IS 'Digest of ordered analysis, warnings and source provenance.';
COMMENT ON COLUMN herb_safety_runs.is_active IS 'Atomic safety activation pointer, deliberately outside sync_metadata.';
COMMENT ON COLUMN herb_safety_runs.created_at IS 'Technical creation timestamp.';

COMMENT ON TABLE herb_safety_cache IS 'Versioned local product safety data with source provenance; not clinical validation.';
COMMENT ON COLUMN herb_safety_cache.cache_key IS 'Identity of complete source, product, context, semantic version and model digest.';
COMMENT ON COLUMN herb_safety_cache.semantic IS 'Safety extraction semantics; a miss cannot invalidate association labels.';
COMMENT ON COLUMN herb_safety_cache.model_digest IS 'Verified model digest reused from the indexing coordinator.';
COMMENT ON COLUMN herb_safety_cache.decision IS 'Validated extractive safety result, including explicit empty and unclear results.';
COMMENT ON COLUMN herb_safety_cache.created_at IS 'Technical cache creation timestamp.';

COMMENT ON TABLE herb_safety_analysis IS 'Versioned local product safety data with source provenance; not clinical validation.';
COMMENT ON COLUMN herb_safety_analysis.run_id IS 'Owning safety generation.';
COMMENT ON COLUMN herb_safety_analysis.identity IS 'Stable product and chunk identity within this generation.';
COMMENT ON COLUMN herb_safety_analysis.herb_id IS 'Unchanged product catalog identity.';
COMMENT ON COLUMN herb_safety_analysis.chunk_id IS 'Original full indexed source fragment.';
COMMENT ON COLUMN herb_safety_analysis.status IS 'Complete AI analysis, unclear AI analysis, local recovery or uncovered source.';
COMMENT ON COLUMN herb_safety_analysis.mandatory IS 'A locally resolved association requires valid AI safety analysis before publication.';
COMMENT ON COLUMN herb_safety_analysis.cache_key IS 'Optional validated AI result; association caches are not safety results.';

COMMENT ON TABLE herb_safety_warnings IS 'Versioned local product safety data with source provenance; not clinical validation.';
COMMENT ON COLUMN herb_safety_warnings.run_id IS 'Owning safety generation.';
COMMENT ON COLUMN herb_safety_warnings.warning_id IS 'Conservative deduplication of product, warning wording, kind and named partners.';
COMMENT ON COLUMN herb_safety_warnings.herb_id IS 'Product whose safety statement is supported by source evidence.';
COMMENT ON COLUMN herb_safety_warnings.kind IS 'Source warning category, independent of disease recommendation or prohibition.';
COMMENT ON COLUMN herb_safety_warnings.text IS 'Extractive display text preserving source qualifiers and product form.';
COMMENT ON COLUMN herb_safety_warnings.partners IS 'Interaction partners quoted in source, without synthetic catalog additions.';

COMMENT ON TABLE herb_safety_evidence IS 'Versioned local product safety data with source provenance; not clinical validation.';
COMMENT ON COLUMN herb_safety_evidence.run_id IS 'Owning safety generation.';
COMMENT ON COLUMN herb_safety_evidence.warning_id IS 'Warning supported by this exact source quotation.';
COMMENT ON COLUMN herb_safety_evidence.herb_id IS 'Product constrained to both the warning and analyzed target.';
COMMENT ON COLUMN herb_safety_evidence.identity IS 'Analyzed product and fragment identity.';
COMMENT ON COLUMN herb_safety_evidence.chunk_id IS 'Original unchanged source fragment.';
COMMENT ON COLUMN herb_safety_evidence.quote_start IS 'Inclusive Unicode code-point offset in original fragment text.';
COMMENT ON COLUMN herb_safety_evidence.quote_end IS 'Exclusive Unicode code-point offset in original fragment text.';
COMMENT ON COLUMN herb_safety_evidence.source_hash IS 'Original document content hash.';
COMMENT ON COLUMN herb_safety_evidence.text_hash IS 'Original full fragment content hash.';
COMMENT ON COLUMN herb_safety_evidence.heading_hash IS 'Original heading hash supporting product attribution.';

