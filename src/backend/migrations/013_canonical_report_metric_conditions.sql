-- Replace historical request labels only when they map exactly to a catalog name.
-- Preserve every other measurement and leave unknown/ambiguous free text untouched.
UPDATE report_generation_metrics AS metrics
SET medical_condition = condition.name
FROM medical_conditions AS condition
WHERE lower(unaccent(btrim(metrics.medical_condition))) IN (
    lower(unaccent(condition.name)),
    'remedii naturiste pentru ' || lower(unaccent(condition.name))
)
AND metrics.medical_condition IS DISTINCT FROM condition.name;

COMMENT ON COLUMN report_generation_metrics.medical_condition IS
    'Exact medical_conditions.name values, joined by comma for multiple identified conditions; never the user request or report title.';
