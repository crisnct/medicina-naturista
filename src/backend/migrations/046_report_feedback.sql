-- PostgreSQL. Applied transactionally by scripts.migrate_database.
-- The admin's rating of a published report, the numeric citation log of its search and the
-- reports the admin kept as examples. The log holds only numbers and content hashes; the
-- feedback comment and the example recommendations are text the admin chose to save.
CREATE TABLE report_feedback (
    report_id BIGINT PRIMARY KEY REFERENCES report_generation_metrics (id) ON DELETE CASCADE,
    language TEXT NOT NULL CHECK (language IN ('ro', 'en')),
    score SMALLINT NOT NULL CHECK (score BETWEEN 0 AND 10),
    comment TEXT NOT NULL DEFAULT '' CHECK (length(comment) <= 4000),
    comment_categories TEXT[],
    search_formula TEXT NOT NULL CHECK (btrim(search_formula) <> ''),
    rrf_k INTEGER NOT NULL CHECK (rrf_k > 0),
    signals TEXT NOT NULL CHECK (btrim(signals) <> ''),
    min_score INTEGER NOT NULL CHECK (min_score BETWEEN 0 AND 100),
    created_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_utc TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE report_feedback IS
    'The admin''s rating of one published report; the latest submission replaces the previous one.';
COMMENT ON COLUMN report_feedback.score IS
    'Rating from 0 (worst) to 10 (best).';
COMMENT ON COLUMN report_feedback.comment IS
    'Optional plain-text comment written by the admin, stored as written.';
COMMENT ON COLUMN report_feedback.comment_categories IS
    'Fixed categories a local model assigns to the comment when the search formula is evaluated; NULL until then.';
COMMENT ON COLUMN report_feedback.search_formula IS
    'SEARCH_SCORE_FORMULA in force when the report''s search ran.';
COMMENT ON COLUMN report_feedback.rrf_k IS
    'SEARCH_RRF_K in force when the report''s search ran.';
COMMENT ON COLUMN report_feedback.signals IS
    'Code of the search signals the report''s search was scored with.';
COMMENT ON COLUMN report_feedback.min_score IS
    'Minimum relevance percentage selected for the report, as a whole number from 0 to 100.';

CREATE TABLE report_evidence_log (
    report_id BIGINT NOT NULL REFERENCES report_generation_metrics (id) ON DELETE CASCADE,
    text_sha256 TEXT NOT NULL CHECK (text_sha256 ~ '^[0-9a-f]{64}$'),
    p1 SMALLINT CHECK (p1 IS NULL OR p1 IN (0, 1)),
    p2 SMALLINT CHECK (p2 IS NULL OR p2 IN (0, 1)),
    l_rank INTEGER CHECK (l_rank IS NULL OR l_rank > 0),
    v_rank INTEGER CHECK (v_rank IS NULL OR v_rank > 0),
    q_rank INTEGER CHECK (q_rank IS NULL OR q_rank > 0),
    sent BOOLEAN NOT NULL,
    cited BOOLEAN NOT NULL CHECK (sent OR NOT cited),
    PRIMARY KEY (report_id, text_sha256)
);

COMMENT ON TABLE report_evidence_log IS
    'The best search candidates of one published report, with their score signals and whether the report model received and cited them. Numbers and content hashes only.';
COMMENT ON COLUMN report_evidence_log.text_sha256 IS
    'Content hash of the fragment (chunks.text_sha256), stable across reindexing.';
COMMENT ON COLUMN report_evidence_log.p1 IS
    'Searched condition in the fragment title (1) or not (0); NULL when the conditions signal was off.';
COMMENT ON COLUMN report_evidence_log.p2 IS
    'Searched condition in the fragment text (1) or not (0); NULL when the conditions signal was off.';
COMMENT ON COLUMN report_evidence_log.l_rank IS
    'Lexical (BM25) rank; NULL when the signal was off or the fragment had no lexical match.';
COMMENT ON COLUMN report_evidence_log.v_rank IS
    'Semantic rank; NULL when the signal was off.';
COMMENT ON COLUMN report_evidence_log.q_rank IS
    'Synthetic-question rank; NULL until that signal exists.';
COMMENT ON COLUMN report_evidence_log.sent IS
    'The fragment was above the minimum score and was sent to the report model.';
COMMENT ON COLUMN report_evidence_log.cited IS
    'A validated recommendation of the report cites the fragment.';

CREATE TABLE report_examples (
    report_id BIGINT PRIMARY KEY REFERENCES report_feedback (report_id) ON DELETE CASCADE,
    language TEXT NOT NULL CHECK (language IN ('ro', 'en')),
    condition_keys TEXT[] NOT NULL,
    sections JSONB NOT NULL CHECK (jsonb_typeof(sections) = 'object'),
    ai_model TEXT NOT NULL CHECK (btrim(ai_model) <> ''),
    created_utc TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX report_examples_language_idx ON report_examples (language, created_utc DESC);

COMMENT ON TABLE report_examples IS
    'Validated recommendations of a report rated 8 or more that the admin saved as an example. Never the consultation profile, the question or the PDF.';
COMMENT ON COLUMN report_examples.condition_keys IS
    'condition:<catalog name> of each catalog condition the report''s search recognised.';
COMMENT ON COLUMN report_examples.sections IS
    'Report sections with their recommendations; each evidence_ids entry is the cited fragment''s text_sha256.';
COMMENT ON COLUMN report_examples.ai_model IS
    'Application report model choice, as in report_generation_metrics.ai_model.';
