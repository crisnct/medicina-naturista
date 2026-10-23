-- Additive source-polarity generations. Historical co-occurrences retain their meaning.
CREATE TABLE herb_positive_runs (
    run_id UUID PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('preparing', 'ready')),
    manifest JSONB NOT NULL CHECK (jsonb_typeof(manifest) = 'object'),
    semantic JSONB NOT NULL CHECK (jsonb_typeof(semantic) = 'object'),
    model_digest TEXT NOT NULL CHECK (length(model_digest) >= 64),
    expected_active TEXT,
    expected_count INTEGER NOT NULL CHECK (expected_count >= 0),
    evidence_hash TEXT,
    counters JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(counters) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (status <> 'ready' OR evidence_hash IS NOT NULL)
);
CREATE TABLE herb_positive_cache (
    cache_key TEXT PRIMARY KEY CHECK (length(cache_key) = 64),
    decision JSONB NOT NULL CHECK (jsonb_typeof(decision) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE herb_positive_evidence (
    run_id UUID NOT NULL REFERENCES herb_positive_runs ON DELETE CASCADE,
    identity TEXT NOT NULL CHECK (length(identity) = 64),
    chunk_id BIGINT NOT NULL REFERENCES chunks ON DELETE CASCADE,
    herb_id INTEGER NOT NULL REFERENCES herbs ON DELETE CASCADE,
    medical_condition_id INTEGER NOT NULL REFERENCES medical_conditions ON DELETE CASCADE,
    unit_start INTEGER NOT NULL CHECK (unit_start >= 0),
    unit_end INTEGER NOT NULL CHECK (unit_end > unit_start),
    mention_start INTEGER NOT NULL CHECK (mention_start >= 0),
    mention_end INTEGER NOT NULL CHECK (mention_end > mention_start),
    label TEXT NOT NULL CHECK (label IN ('positive', 'caution', 'mixed', 'unclear')),
    origin TEXT NOT NULL CHECK (origin IN ('rule', 'model')),
    rule_code TEXT NOT NULL,
    cache_key TEXT REFERENCES herb_positive_cache,
    provenance JSONB NOT NULL CHECK (jsonb_typeof(provenance) = 'object'),
    PRIMARY KEY (run_id, identity),
    UNIQUE (run_id, chunk_id, herb_id, medical_condition_id, unit_start, unit_end, mention_start, mention_end),
    CHECK (mention_end <= unit_end - unit_start),
    CHECK ((origin = 'rule' AND rule_code <> '') OR (origin = 'model' AND cache_key IS NOT NULL))
);
CREATE TABLE herb_positive_pairs (
    run_id UUID NOT NULL REFERENCES herb_positive_runs ON DELETE CASCADE,
    herb_id INTEGER NOT NULL REFERENCES herbs ON DELETE CASCADE,
    medical_condition_id INTEGER NOT NULL REFERENCES medical_conditions ON DELETE CASCADE,
    positive_count INTEGER NOT NULL CHECK (positive_count >= 0),
    caution_count INTEGER NOT NULL CHECK (caution_count >= 0),
    mixed_count INTEGER NOT NULL CHECK (mixed_count >= 0),
    unclear_count INTEGER NOT NULL CHECK (unclear_count >= 0),
    state TEXT NOT NULL CHECK (state IN ('positive', 'caution', 'mixed', 'unclear')),
    PRIMARY KEY (run_id, herb_id, medical_condition_id),
    CHECK (positive_count + caution_count + mixed_count + unclear_count > 0),
    CHECK (state = CASE WHEN mixed_count > 0 OR (positive_count > 0 AND caution_count > 0)
           THEN 'mixed' WHEN positive_count > 0 THEN 'positive'
           WHEN caution_count > 0 THEN 'caution' ELSE 'unclear' END)
);
CREATE TABLE herb_positive_rankings (
    run_id UUID NOT NULL REFERENCES herb_positive_runs ON DELETE CASCADE,
    herb_id INTEGER NOT NULL REFERENCES herbs ON DELETE CASCADE,
    ranking INTEGER NOT NULL CHECK (ranking >= 0),
    PRIMARY KEY (run_id, herb_id)
);
CREATE INDEX ON herb_positive_rankings (run_id, ranking DESC, herb_id);
CREATE INDEX ON herb_positive_evidence (run_id, herb_id, medical_condition_id);
COMMENT ON TABLE herb_positive_runs IS 'Complete, immutable ready generations; activation is a separate compare-and-swap.';
COMMENT ON TABLE herb_positive_evidence IS 'Source polarity provenance; quotations are offsets, never clinical validation.';
COMMENT ON TABLE herb_positive_cache IS 'Validated semantic decisions without corpus text, raw responses or patient metrics.';
COMMENT ON TABLE herb_positive_pairs IS 'All distinct source relationships, including mixed exclusions.';
COMMENT ON TABLE herb_positive_rankings IS 'Distinct exclusively positive primary conditions; zero is a valid score.';
COMMENT ON COLUMN herb_positive_runs.run_id IS 'Technical generation identifier.';
COMMENT ON COLUMN herb_positive_runs.status IS 'Preparing or complete ready generation; never partially activated.';
COMMENT ON COLUMN herb_positive_runs.manifest IS 'Fingerprints of the coherent source index and catalogs.';
COMMENT ON COLUMN herb_positive_runs.semantic IS 'Rules, schema, prompt and local model semantic configuration.';
COMMENT ON COLUMN herb_positive_runs.model_digest IS 'Installed Ollama model digest verified before and after preparation.';
COMMENT ON COLUMN herb_positive_runs.expected_active IS 'Pointer observed at preparation, compared atomically on publication.';
COMMENT ON COLUMN herb_positive_runs.expected_count IS 'Complete candidate mention count required for publication.';
COMMENT ON COLUMN herb_positive_runs.evidence_hash IS 'Digest of the complete ordered evidence rows.';
COMMENT ON COLUMN herb_positive_runs.counters IS 'Aggregate operational counters and request attempts only.';
COMMENT ON COLUMN herb_positive_runs.created_at IS 'Database timestamp of creation.';
COMMENT ON COLUMN herb_positive_cache.cache_key IS 'Content and semantic configuration identity for a validated decision.';
COMMENT ON COLUMN herb_positive_cache.decision IS 'Validated label and relative quotation offsets; no source text.';
COMMENT ON COLUMN herb_positive_cache.created_at IS 'Database timestamp of creation.';
COMMENT ON COLUMN herb_positive_evidence.run_id IS 'Technical generation identifier.';
COMMENT ON COLUMN herb_positive_evidence.identity IS 'Unique candidate mention identity within the generation.';
COMMENT ON COLUMN herb_positive_evidence.chunk_id IS 'Existing indexed fragment supplying the source text.';
COMMENT ON COLUMN herb_positive_evidence.herb_id IS 'Unchanged catalog product identity.';
COMMENT ON COLUMN herb_positive_evidence.medical_condition_id IS 'Eligible primary condition identity, never a secondary inference.';
COMMENT ON COLUMN herb_positive_evidence.unit_start IS 'Inclusive original fragment character offset.';
COMMENT ON COLUMN herb_positive_evidence.unit_end IS 'Exclusive original fragment character offset.';
COMMENT ON COLUMN herb_positive_evidence.mention_start IS 'Inclusive mention offset relative to the unit.';
COMMENT ON COLUMN herb_positive_evidence.mention_end IS 'Exclusive mention offset relative to the unit.';
COMMENT ON COLUMN herb_positive_evidence.label IS 'Source polarity, not clinical efficacy.';
COMMENT ON COLUMN herb_positive_evidence.origin IS 'Local deterministic rule or validated local model.';
COMMENT ON COLUMN herb_positive_evidence.rule_code IS 'Deterministic rule identifier; empty for model decisions.';
COMMENT ON COLUMN herb_positive_evidence.cache_key IS 'Content and semantic configuration identity for a validated decision.';
COMMENT ON COLUMN herb_positive_evidence.provenance IS 'Document and chunk hashes, heading hash and relative quote spans.';
COMMENT ON COLUMN herb_positive_pairs.run_id IS 'Technical generation identifier.';
COMMENT ON COLUMN herb_positive_pairs.herb_id IS 'Unchanged catalog product identity.';
COMMENT ON COLUMN herb_positive_pairs.medical_condition_id IS 'Eligible primary condition identity, never a secondary inference.';
COMMENT ON COLUMN herb_positive_pairs.positive_count IS 'Nonnegative number of mentions bearing this polarity.';
COMMENT ON COLUMN herb_positive_pairs.caution_count IS 'Nonnegative number of mentions bearing this polarity.';
COMMENT ON COLUMN herb_positive_pairs.mixed_count IS 'Nonnegative number of mentions bearing this polarity.';
COMMENT ON COLUMN herb_positive_pairs.unclear_count IS 'Nonnegative number of mentions bearing this polarity.';
COMMENT ON COLUMN herb_positive_pairs.state IS 'Computed exclusively from all source polarity counts.';
COMMENT ON COLUMN herb_positive_rankings.run_id IS 'Technical generation identifier.';
COMMENT ON COLUMN herb_positive_rankings.herb_id IS 'Unchanged catalog product identity.';
COMMENT ON COLUMN herb_positive_rankings.ranking IS 'Distinct positive primary conditions excluding every mixed pair.';
