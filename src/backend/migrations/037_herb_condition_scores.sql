-- Per-condition fragment counts of the eligible products, precomputed so a top never scans fragments.
CREATE TABLE herb_condition_score_runs (
    positive_run_id UUID PRIMARY KEY REFERENCES herb_positive_runs ON DELETE CASCADE,
    row_count INTEGER NOT NULL CHECK (row_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE herb_condition_scores (
    positive_run_id UUID NOT NULL REFERENCES herb_condition_score_runs ON DELETE CASCADE,
    medical_condition_id INTEGER NOT NULL REFERENCES medical_conditions ON DELETE CASCADE,
    herb_id INTEGER NOT NULL REFERENCES herbs ON DELETE CASCADE,
    title_fragments INTEGER NOT NULL CHECK (title_fragments >= 0),
    text_fragments INTEGER NOT NULL CHECK (text_fragments >= 0),
    conditions_count INTEGER NOT NULL CHECK (conditions_count > 0),
    PRIMARY KEY (positive_run_id, medical_condition_id, herb_id)
);

COMMENT ON TABLE herb_condition_score_runs IS 'Marks a positive run whose condition scores are complete; an absent marker means not computed, not empty.';
COMMENT ON TABLE herb_condition_scores IS 'L1, L2 and L3 of every product with a positive pair for a condition; the ordering formula is applied at request time.';
COMMENT ON COLUMN herb_condition_score_runs.positive_run_id IS 'Positive generation the counts belong to.';
COMMENT ON COLUMN herb_condition_score_runs.row_count IS 'Number of score rows written for the run.';
COMMENT ON COLUMN herb_condition_score_runs.created_at IS 'Database timestamp of creation.';
COMMENT ON COLUMN herb_condition_scores.positive_run_id IS 'Positive generation the counts belong to.';
COMMENT ON COLUMN herb_condition_scores.medical_condition_id IS 'Condition named by the fragments.';
COMMENT ON COLUMN herb_condition_scores.herb_id IS 'Unchanged catalog product identity.';
COMMENT ON COLUMN herb_condition_scores.title_fragments IS 'L1: distinct fragments naming the condition in the title with a positive mention of the product.';
COMMENT ON COLUMN herb_condition_scores.text_fragments IS 'L2: distinct fragments mentioning the product and naming the condition in the text, title excluded.';
COMMENT ON COLUMN herb_condition_scores.conditions_count IS 'L3: distinct conditions with a positive pair for the product (herb_positive_rankings.ranking).';
