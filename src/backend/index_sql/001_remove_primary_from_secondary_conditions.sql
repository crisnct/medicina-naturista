-- Runs on every index build, after the chunk condition columns are filled: a condition that is
-- already primary (named in the fragment title) must not also count as secondary.
-- Idempotent; keeps the order of the remaining elements.
UPDATE chunks
SET secondary_medical_conditions = ARRAY(
    SELECT item
    FROM unnest(secondary_medical_conditions) WITH ORDINALITY AS t(item, position)
    WHERE item <> ALL (primary_medical_conditions)
    ORDER BY position
)
WHERE secondary_medical_conditions && primary_medical_conditions;
