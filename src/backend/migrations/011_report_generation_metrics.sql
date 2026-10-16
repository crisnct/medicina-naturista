-- PostgreSQL. Applied transactionally by scripts.migrate_database.
-- One row per successfully published report; identical measurements are valid.
CREATE TABLE report_generation_metrics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY CHECK (id > 0),
    medical_condition TEXT NOT NULL CHECK (btrim(medical_condition) <> ''),
    min_score INTEGER NOT NULL CHECK (min_score BETWEEN 0 AND 100),
    characters BIGINT NOT NULL CHECK (characters >= 0),
    ai_model TEXT NOT NULL CHECK (btrim(ai_model) <> ''),
    ai_effort TEXT CHECK (ai_effort IS NULL OR btrim(ai_effort) <> ''),
    duration BIGINT NOT NULL CHECK (duration >= 0)
);

COMMENT ON TABLE report_generation_metrics IS
    'Report generation measurements. Initial historical measurements are supplied separately.';
COMMENT ON COLUMN report_generation_metrics.medical_condition IS
    'Condition label(s) associated with the report search snapshot.';
COMMENT ON COLUMN report_generation_metrics.min_score IS
    'Selected minimum relevance percentage, as a whole number from 0 to 100.';
COMMENT ON COLUMN report_generation_metrics.characters IS
    'Number of Unicode characters in evidence text actually supplied to the report AI; excludes prompts and output.';
COMMENT ON COLUMN report_generation_metrics.ai_model IS
    'Application report model choice, including the ollama- prefix for local models.';
COMMENT ON COLUMN report_generation_metrics.ai_effort IS
    'Configured reasoning effort for the selected client; NULL if unspecified. Does not assert provider support.';
COMMENT ON COLUMN report_generation_metrics.duration IS
    'Elapsed generation time in milliseconds, excluding queue wait and the metrics INSERT.';
