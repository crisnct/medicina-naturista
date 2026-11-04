-- PostgreSQL. Applied transactionally by scripts.migrate_database.
-- The largest output (reasoning included) one batch request of the report consumed. It lets the
-- report panel recommend an output limit that the model has been seen to need.
ALTER TABLE report_generation_metrics
    ADD COLUMN max_batch_output_tokens BIGINT CHECK (max_batch_output_tokens IS NULL OR max_batch_output_tokens >= 0);

COMMENT ON COLUMN report_generation_metrics.max_batch_output_tokens IS
    'Largest output_tokens reported by any request of the report, retries included; NULL for reports measured before this column or whose provider reported no usage.';
