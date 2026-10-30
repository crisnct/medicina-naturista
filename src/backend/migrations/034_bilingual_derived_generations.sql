-- Each language owns its publication pointer; existing generations remain Romanian.
ALTER TABLE herb_positive_runs ADD COLUMN language TEXT NOT NULL DEFAULT 'ro' CHECK(language IN ('ro','en'));
ALTER TABLE herb_caution_runs ADD COLUMN language TEXT NOT NULL DEFAULT 'ro' CHECK(language IN ('ro','en'));
ALTER TABLE herb_product_safety_runs ADD COLUMN language TEXT NOT NULL DEFAULT 'ro' CHECK(language IN ('ro','en'));
COMMENT ON COLUMN herb_positive_runs.language IS 'Language of every supporting chunk and of the classification prompt.';
COMMENT ON COLUMN herb_caution_runs.language IS 'Language inherited from the positive generation.';
COMMENT ON COLUMN herb_product_safety_runs.language IS 'Language of the system prompt and stored safety messages.';
DROP INDEX herb_caution_one_active;
CREATE UNIQUE INDEX herb_caution_one_active ON herb_caution_runs(language) WHERE is_active;
DROP INDEX herb_product_safety_one_active;
CREATE UNIQUE INDEX herb_product_safety_one_active ON herb_product_safety_runs(language) WHERE is_active;

-- Repositories set this validated value transaction-locally before creating a run.
ALTER TABLE herb_positive_runs ALTER COLUMN language SET DEFAULT coalesce(nullif(current_setting('app.language',true),''),'ro');
ALTER TABLE herb_caution_runs ALTER COLUMN language SET DEFAULT coalesce(nullif(current_setting('app.language',true),''),'ro');
ALTER TABLE herb_product_safety_runs ALTER COLUMN language SET DEFAULT coalesce(nullif(current_setting('app.language',true),''),'ro');
