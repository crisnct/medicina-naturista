-- One-time cleanup of the rows indexed before backend/index_sql/001_remove_primary_from_secondary_conditions.sql
-- existed: a condition that is already primary must not also count as secondary.
-- Touches neither the text, the embeddings nor the primary column, so published rankings stay valid.
UPDATE chunks
SET secondary_medical_conditions = ARRAY(
    SELECT item
    FROM unnest(secondary_medical_conditions) WITH ORDINALITY AS t(item, position)
    WHERE item <> ALL (primary_medical_conditions)
    ORDER BY position
)
WHERE secondary_medical_conditions && primary_medical_conditions;
