-- Keep only diseases and their synonyms. Preserve existing disease IDs.
-- Applied atomically with the migration ledger before fragmentation.
ALTER TABLE medical_conditions RENAME COLUMN condition_id TO id;

CREATE TABLE medical_condition_synonyms (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    medical_condition_id BIGINT NOT NULL REFERENCES medical_conditions(id) ON DELETE CASCADE,
    synonym TEXT NOT NULL CHECK (btrim(synonym) <> ''),
    UNIQUE (medical_condition_id, synonym)
);

INSERT INTO medical_condition_synonyms (medical_condition_id, synonym)
SELECT c.id, t.term
FROM medical_conditions c
JOIN medical_condition_terms t ON t.condition_id = c.id
WHERE t.position > 0
ORDER BY c.sort_order, t.position;

DROP TABLE medical_condition_terms;
DROP TABLE medical_condition_catalog;
ALTER TABLE medical_conditions DROP COLUMN normalized_name;
ALTER TABLE medical_conditions DROP COLUMN sort_order;
