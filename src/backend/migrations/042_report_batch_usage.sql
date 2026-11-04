-- PostgreSQL. Applied transactionally by scripts.migrate_database.
-- One row per AI request of a report, published or failed, so the batches cut off by their
-- output limit are measured too. It holds no medical data: only the model, the effort and tokens.
CREATE TABLE report_batch_usage (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ai_model TEXT NOT NULL CHECK (btrim(ai_model) <> ''),
    ai_effort TEXT CHECK (ai_effort IS NULL OR btrim(ai_effort) <> ''),
    reasoning_tokens BIGINT CHECK (reasoning_tokens IS NULL OR reasoning_tokens >= 0),
    answer_tokens BIGINT NOT NULL CHECK (answer_tokens >= 0),
    truncated BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX report_batch_usage_model_effort_idx
    ON report_batch_usage (ai_model, ai_effort, id DESC);

COMMENT ON TABLE report_batch_usage IS
    'Token usage of each report AI request; the report panel recommends output and thinking budgets from the recent rows.';
COMMENT ON COLUMN report_batch_usage.reasoning_tokens IS
    'Thinking tokens of the request; NULL when the provider reported none. Ollama counts are estimated from the thinking text.';
COMMENT ON COLUMN report_batch_usage.answer_tokens IS
    'Output tokens minus thinking tokens: the JSON answer.';
COMMENT ON COLUMN report_batch_usage.truncated IS
    'The request reached its output limit; its tokens are then a lower bound of what it needed.';
