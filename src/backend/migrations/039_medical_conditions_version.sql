-- A change counter for the condition dictionary, so a reader can tell with one tiny query
-- that medical_conditions and medical_condition_synonyms are unchanged since it last read them.
CREATE TABLE IF NOT EXISTS medical_conditions_version (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    version BIGINT NOT NULL DEFAULT 1
);
INSERT INTO medical_conditions_version DEFAULT VALUES ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION bump_medical_conditions_version() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE medical_conditions_version SET version = version + 1;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS medical_conditions_version_bump ON medical_conditions;
CREATE TRIGGER medical_conditions_version_bump
    AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON medical_conditions
    FOR EACH STATEMENT EXECUTE FUNCTION bump_medical_conditions_version();

DROP TRIGGER IF EXISTS medical_condition_synonyms_version_bump ON medical_condition_synonyms;
CREATE TRIGGER medical_condition_synonyms_version_bump
    AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON medical_condition_synonyms
    FOR EACH STATEMENT EXECUTE FUNCTION bump_medical_conditions_version();

COMMENT ON TABLE medical_conditions_version IS 'Single row counting every statement that changed medical_conditions or medical_condition_synonyms; readers cache the dictionary per value.';
COMMENT ON COLUMN medical_conditions_version.singleton IS 'Always true; keeps the table to one row.';
COMMENT ON COLUMN medical_conditions_version.version IS 'Increased by statement-level triggers on both dictionary tables.';
COMMENT ON FUNCTION bump_medical_conditions_version() IS 'Trigger function increasing medical_conditions_version.';
