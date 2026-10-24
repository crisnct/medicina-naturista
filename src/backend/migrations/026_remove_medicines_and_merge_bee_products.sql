-- Remove the approved medicine identity; preserve all remaining catalog evidence.
CREATE TEMP TABLE category_cleanup_before ON COMMIT DROP AS SELECT * FROM herbs;

DO $guard$
BEGIN
    IF (SELECT count(*) FROM herbs WHERE category = 'medicamente') <> 1
        OR NOT EXISTS (
            SELECT FROM herbs WHERE id = 1212 AND category = 'medicamente'
                AND ro = 'aspirina' AND en = 'aspirin' AND family IS NULL AND latin IS NULL
        ) THEN
        RAISE EXCEPTION 'MEDICINE_REMOVAL_IDENTITY_MISMATCH';
    END IF;
END
$guard$;

-- Foreign keys cascade only aspirin's aliases, associations and positive-ranking evidence.
DELETE FROM herbs WHERE id = 1212;
UPDATE herbs SET category = 'suplimente' WHERE category = 'produse apicole';

ALTER TABLE herbs DROP CONSTRAINT herbs_category_check,
    DROP CONSTRAINT herbs_product_species_check;
ALTER TABLE herbs ADD CONSTRAINT herbs_category_check CHECK (category IN (
    'plante medicinale', 'fructe', 'legume', 'cereale', 'seminte',
    'uleiuri esentiale', 'uleiuri', 'suplimente', 'aminoacizi', 'vitamine', 'minerale'
)), ADD CONSTRAINT herbs_product_species_check CHECK (
    (category IN ('plante medicinale', 'fructe', 'legume', 'cereale')
        AND latin IS NOT NULL AND family IS NOT NULL)
    OR (category IN ('seminte', 'uleiuri esentiale', 'uleiuri', 'suplimente',
        'aminoacizi', 'vitamine', 'minerale') AND latin IS NULL AND family IS NULL)
);

DROP INDEX herbs_product_ro_unique;
CREATE UNIQUE INDEX herbs_product_ro_unique ON herbs (lower(btrim(ro)))
    WHERE category IN ('seminte', 'uleiuri esentiale', 'uleiuri', 'suplimente',
        'aminoacizi', 'vitamine', 'minerale');

DO $verify$
BEGIN
    IF (SELECT count(*) FROM herbs) <> (SELECT count(*) - 1 FROM category_cleanup_before)
        OR EXISTS (
            SELECT FROM category_cleanup_before b LEFT JOIN herbs h ON h.id = b.id
            WHERE b.id <> 1212 AND (
                h.id IS NULL OR ROW(h.family, h.latin, h.ro, h.en, h.ranking, h.category)
                    IS DISTINCT FROM ROW(b.family, b.latin, b.ro, b.en, b.ranking,
                        CASE WHEN b.category = 'produse apicole'
                             THEN 'suplimente' ELSE b.category END)
            )
        ) THEN
        RAISE EXCEPTION 'CATALOG_CATEGORY_CLEANUP_MISMATCH';
    END IF;
END
$verify$;

COMMENT ON CONSTRAINT herbs_category_check ON herbs IS
    'Eleven canonical catalog groups; bee products belong to supplements; medicines are excluded.';
COMMENT ON CONSTRAINT herbs_product_species_check ON herbs IS
    'Four botanical groups require taxonomy; seven product groups require SQL NULL family and Latin name.';
COMMENT ON INDEX herbs_product_ro_unique IS
    'One normalized product name across all seven product groups.';
