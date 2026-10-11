-- Derived corpus co-occurrences; populated atomically by the hybrid index builder.
CREATE TABLE herbs_benefits (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY CHECK (id > 0),
    herb_id BIGINT NOT NULL REFERENCES herbs(id) ON DELETE CASCADE,
    medical_condition_id BIGINT NOT NULL
        REFERENCES medical_conditions(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX herbs_benefits_herb_condition_uq
    ON herbs_benefits (herb_id, medical_condition_id);
CREATE INDEX herbs_benefits_herb_id_idx ON herbs_benefits (herb_id);
CREATE INDEX herbs_benefits_medical_condition_id_idx
    ON herbs_benefits (medical_condition_id);
