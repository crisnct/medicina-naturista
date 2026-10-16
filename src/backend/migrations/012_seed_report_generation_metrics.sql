-- Historical measurements supplied by the user; not independently benchmarked.
-- Prerequisite: 011_report_generation_metrics.sql.
-- 53.924 is the Romanian thousands notation for 53924 characters.
-- duration is milliseconds: minutes * 60000; seconds * 1000.
-- Apply once through scripts.migrate_database and its schema_migrations ledger.
-- Directly rerunning this INSERT creates another six rows.
INSERT INTO report_generation_metrics
    (medical_condition, min_score, characters, ai_model, ai_effort, duration)
VALUES
    ('Gripa', 50, 53924, 'ollama-gemma4:12b',      'medium',  300000),
    ('Gripa', 50, 53924, 'ollama-qwen3.5:4b',     'medium',  300000),
    ('Gripa', 50, 53924, 'ollama-qwen3.5:9b',     'medium',  600000),
    ('Gripa', 50, 53924, 'ollama-ministral-3:8b',  'medium', 1020000),
    ('Gripa', 50, 53924, 'deepseek-flash',        'low',     180000),
    ('Gripa', 50, 53924, 'grok-4.3',              'medium',   40000);
