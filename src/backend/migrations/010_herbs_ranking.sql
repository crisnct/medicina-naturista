-- Number of distinct medical conditions associated with each herb.
-- Rerun this script to refresh ranking after herbs_benefits changes.
ALTER TABLE herbs
    ADD COLUMN IF NOT EXISTS ranking BIGINT NOT NULL DEFAULT 0
        CHECK (ranking >= 0);

UPDATE herbs AS h
SET ranking = counts.total_conditions
FROM (
    SELECT herb.id AS herb_id, COUNT(DISTINCT mc.id) AS total_conditions
    FROM herbs AS herb
    LEFT JOIN herbs_benefits AS hb ON hb.herb_id = herb.id
    LEFT JOIN medical_conditions AS mc ON mc.id = hb.medical_condition_id
    GROUP BY herb.id
) AS counts
WHERE h.id = counts.herb_id;
