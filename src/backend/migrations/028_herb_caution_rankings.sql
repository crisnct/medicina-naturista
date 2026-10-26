-- Warning projections consume existing decisions; they never schedule inference.
CREATE TABLE herb_caution_runs (
    run_id UUID PRIMARY KEY,
    positive_run_id UUID NOT NULL REFERENCES herb_positive_runs ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('preparing', 'ready')),
    manifest JSONB NOT NULL CHECK (jsonb_typeof(manifest) = 'object'),
    projection_version INTEGER NOT NULL CHECK (projection_version > 0),
    model_digest TEXT NOT NULL CHECK (length(model_digest) >= 64),
    expected_active UUID,
    expected_count INTEGER NOT NULL CHECK (expected_count >= 0),
    unknown_count INTEGER NOT NULL CHECK (unknown_count BETWEEN 0 AND expected_count),
    evidence_hash TEXT,
    is_active BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (status <> 'ready' OR evidence_hash IS NOT NULL),
    CHECK (NOT is_active OR status = 'ready')
);
-- Activation metadata stays outside sync_metadata, whose contents fingerprint positive runs.
CREATE UNIQUE INDEX herb_caution_one_active ON herb_caution_runs (is_active) WHERE is_active;
CREATE INDEX ON herb_caution_runs (positive_run_id, created_at DESC);

CREATE TABLE herb_caution_cache (
    cache_key TEXT NOT NULL REFERENCES herb_positive_cache ON DELETE CASCADE,
    projection_version INTEGER NOT NULL CHECK (projection_version > 0),
    decision JSONB NOT NULL CHECK (jsonb_typeof(decision) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (cache_key, projection_version)
);

CREATE TABLE herb_caution_evidence (
    run_id UUID NOT NULL REFERENCES herb_caution_runs ON DELETE CASCADE,
    identity TEXT NOT NULL CHECK (length(identity) = 64),
    chunk_id BIGINT NOT NULL REFERENCES chunks ON DELETE CASCADE,
    herb_id INTEGER NOT NULL REFERENCES herbs ON DELETE CASCADE,
    medical_condition_id INTEGER NOT NULL REFERENCES medical_conditions ON DELETE CASCADE,
    unit_start INTEGER NOT NULL CHECK (unit_start >= 0),
    unit_end INTEGER NOT NULL CHECK (unit_end > unit_start),
    mention_start INTEGER NOT NULL CHECK (mention_start >= 0),
    mention_end INTEGER NOT NULL CHECK (mention_end > mention_start),
    warning_kind TEXT NOT NULL CHECK (warning_kind IN ('prohibition','precaution','none','unknown')),
    has_recommendation BOOLEAN NOT NULL,
    origin TEXT NOT NULL CHECK (origin IN ('rule','model')),
    rule_code TEXT NOT NULL,
    cache_key TEXT REFERENCES herb_positive_cache,
    provenance JSONB NOT NULL CHECK (jsonb_typeof(provenance) = 'object'),
    PRIMARY KEY (run_id, identity),
    CHECK (mention_end <= unit_end - unit_start),
    UNIQUE (run_id, chunk_id, herb_id, medical_condition_id,
            unit_start, unit_end, mention_start, mention_end)
);
CREATE INDEX ON herb_caution_evidence (run_id, herb_id, medical_condition_id);

CREATE TABLE herb_caution_pairs (
    run_id UUID NOT NULL REFERENCES herb_caution_runs ON DELETE CASCADE,
    herb_id INTEGER NOT NULL REFERENCES herbs ON DELETE CASCADE,
    medical_condition_id INTEGER NOT NULL REFERENCES medical_conditions ON DELETE CASCADE,
    prohibition_count INTEGER NOT NULL CHECK (prohibition_count >= 0),
    precaution_count INTEGER NOT NULL CHECK (precaution_count >= 0),
    none_count INTEGER NOT NULL CHECK (none_count >= 0),
    unknown_count INTEGER NOT NULL CHECK (unknown_count >= 0),
    has_recommendation BOOLEAN NOT NULL,
    PRIMARY KEY (run_id, herb_id, medical_condition_id),
    CHECK (prohibition_count + precaution_count + none_count + unknown_count > 0)
);
CREATE TABLE herb_caution_rankings (
    run_id UUID NOT NULL REFERENCES herb_caution_runs ON DELETE CASCADE,
    herb_id INTEGER NOT NULL REFERENCES herbs ON DELETE CASCADE,
    ranking INTEGER NOT NULL CHECK (ranking >= 0),
    prohibition_ranking INTEGER NOT NULL CHECK (prohibition_ranking BETWEEN 0 AND ranking),
    PRIMARY KEY (run_id, herb_id)
);
CREATE INDEX ON herb_caution_rankings (run_id, prohibition_ranking DESC, herb_id);

COMMENT ON TABLE herb_caution_runs IS 'Immutable warning generations linked to positive runs; only activation metadata changes after readiness.';
COMMENT ON TABLE herb_caution_cache IS 'Versioned projections of already available model decisions; a miss never schedules inference.';
COMMENT ON TABLE herb_caution_evidence IS 'Source warnings with unchanged-text provenance, distinct from clinical validation.';
COMMENT ON TABLE herb_caution_pairs IS 'Distinct product-condition warnings, including explicit historical unknowns.';
COMMENT ON TABLE herb_caution_rankings IS 'Distinct warning and prohibition conditions per product, including zero scores.';

COMMENT ON COLUMN herb_caution_runs.run_id IS 'Technical warning generation identifier.';
COMMENT ON COLUMN herb_caution_runs.positive_run_id IS 'Positive generation with the identical source manifest.';
COMMENT ON COLUMN herb_caution_runs.status IS 'Preparation state; only complete evidence coverage may become ready.';
COMMENT ON COLUMN herb_caution_runs.manifest IS 'Unchanged index and catalog fingerprints copied from the positive generation.';
COMMENT ON COLUMN herb_caution_runs.projection_version IS 'Local projection semantics, independent of positive model cache keys.';
COMMENT ON COLUMN herb_caution_runs.model_digest IS 'Model provenance already recorded by the positive generation; no model lookup.';
COMMENT ON COLUMN herb_caution_runs.expected_active IS 'Warning pointer observed at preparation for compare-and-swap publication.';
COMMENT ON COLUMN herb_caution_runs.expected_count IS 'Required number of projected positive evidence identities.';
COMMENT ON COLUMN herb_caution_runs.unknown_count IS 'Evidence identities whose historical prohibition information cannot be recovered locally.';
COMMENT ON COLUMN herb_caution_runs.evidence_hash IS 'Digest of ordered evidence, including warning metadata and provenance.';
COMMENT ON COLUMN herb_caution_runs.is_active IS 'Mutable activation pointer excluded from positive source fingerprints.';
COMMENT ON COLUMN herb_caution_runs.created_at IS 'Technical creation timestamp.';
COMMENT ON COLUMN herb_caution_cache.cache_key IS 'Existing positive model cache identity; never invalidated by a warning cache miss.';
COMMENT ON COLUMN herb_caution_cache.projection_version IS 'Local warning projection version.';
COMMENT ON COLUMN herb_caution_cache.decision IS 'Validated warning kind, recommendation flag and source offsets; no raw response.';
COMMENT ON COLUMN herb_caution_cache.created_at IS 'Technical creation timestamp.';
COMMENT ON COLUMN herb_caution_evidence.run_id IS 'Owning warning generation.';
COMMENT ON COLUMN herb_caution_evidence.identity IS 'Original positive evidence identity.';
COMMENT ON COLUMN herb_caution_evidence.chunk_id IS 'Original indexed fragment.';
COMMENT ON COLUMN herb_caution_evidence.herb_id IS 'Unchanged catalog product identity.';
COMMENT ON COLUMN herb_caution_evidence.medical_condition_id IS 'Verified primary condition identity.';
COMMENT ON COLUMN herb_caution_evidence.unit_start IS 'Inclusive original fragment character offset.';
COMMENT ON COLUMN herb_caution_evidence.unit_end IS 'Exclusive original fragment character offset.';
COMMENT ON COLUMN herb_caution_evidence.mention_start IS 'Inclusive mention offset relative to the unit.';
COMMENT ON COLUMN herb_caution_evidence.mention_end IS 'Exclusive mention offset relative to the unit.';
COMMENT ON COLUMN herb_caution_evidence.warning_kind IS 'Explicit prohibition, precaution, no identified warning, or unrecoverable historical unknown.';
COMMENT ON COLUMN herb_caution_evidence.has_recommendation IS 'Recommendation evidence survives independently of a warning.';
COMMENT ON COLUMN herb_caution_evidence.origin IS 'Existing rule or model decision provenance.';
COMMENT ON COLUMN herb_caution_evidence.rule_code IS 'Local projection or verified warning rule identifier.';
COMMENT ON COLUMN herb_caution_evidence.cache_key IS 'Source positive cache identity when available.';
COMMENT ON COLUMN herb_caution_evidence.provenance IS 'Original source hashes and offsets plus locally recovered warning spans.';
COMMENT ON COLUMN herb_caution_pairs.run_id IS 'Owning warning generation.';
COMMENT ON COLUMN herb_caution_pairs.herb_id IS 'Unchanged catalog product identity.';
COMMENT ON COLUMN herb_caution_pairs.medical_condition_id IS 'Verified primary condition identity.';
COMMENT ON COLUMN herb_caution_pairs.prohibition_count IS 'Number of explicit prohibition evidence rows.';
COMMENT ON COLUMN herb_caution_pairs.precaution_count IS 'Number of precaution evidence rows.';
COMMENT ON COLUMN herb_caution_pairs.none_count IS 'Number of evaluated rows without an identified warning.';
COMMENT ON COLUMN herb_caution_pairs.unknown_count IS 'Number of unrecoverable historical rows.';
COMMENT ON COLUMN herb_caution_pairs.has_recommendation IS 'At least one source also recommends the product for this condition.';
COMMENT ON COLUMN herb_caution_rankings.run_id IS 'Owning warning generation.';
COMMENT ON COLUMN herb_caution_rankings.herb_id IS 'Unchanged catalog product identity.';
COMMENT ON COLUMN herb_caution_rankings.ranking IS 'Distinct primary conditions with a prohibition or precaution.';
COMMENT ON COLUMN herb_caution_rankings.prohibition_ranking IS 'Distinct primary conditions with explicit prohibitions, used by the chat count.';
