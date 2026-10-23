-- Merge the removed group into supplements without changing identities or ranking evidence.
CREATE TEMP TABLE supplements_merge_before ON COMMIT DROP AS SELECT * FROM herbs;

UPDATE herbs SET category = 'suplimente'
WHERE category = 'fibre, probiotice, prebiotice';

ALTER TABLE herbs DROP CONSTRAINT herbs_category_check,
    DROP CONSTRAINT herbs_product_species_check;
ALTER TABLE herbs ADD CONSTRAINT herbs_category_check CHECK (category IN (
    'plante medicinale', 'fructe', 'legume', 'cereale', 'seminte',
    'uleiuri esentiale', 'uleiuri', 'suplimente', 'medicamente', 'aminoacizi',
    'vitamine', 'minerale', 'produse apicole'
)), ADD CONSTRAINT herbs_product_species_check CHECK (
    (category IN ('plante medicinale', 'fructe', 'legume', 'cereale')
        AND latin IS NOT NULL AND family IS NOT NULL)
    OR (category IN ('seminte', 'uleiuri esentiale', 'uleiuri', 'suplimente',
        'medicamente', 'aminoacizi', 'vitamine', 'minerale', 'produse apicole')
        AND latin IS NULL AND family IS NULL)
);

DROP INDEX herbs_product_ro_unique;
CREATE UNIQUE INDEX herbs_product_ro_unique ON herbs (lower(btrim(ro)))
    WHERE category IN ('seminte', 'uleiuri esentiale', 'uleiuri', 'suplimente',
        'medicamente', 'aminoacizi', 'vitamine', 'minerale', 'produse apicole');

DO $verify$
BEGIN
    IF (SELECT count(*) FROM herbs) <> (SELECT count(*) FROM supplements_merge_before)
        OR EXISTS (
            SELECT FROM supplements_merge_before b LEFT JOIN herbs h ON h.id = b.id
            WHERE h.id IS NULL OR ROW(h.family, h.latin, h.ro, h.en, h.ranking, h.category)
                IS DISTINCT FROM ROW(b.family, b.latin, b.ro, b.en, b.ranking,
                    CASE WHEN b.category = 'fibre, probiotice, prebiotice'
                         THEN 'suplimente' ELSE b.category END)
        ) THEN
        RAISE EXCEPTION 'SUPPLEMENTS_CATEGORY_MERGE_MISMATCH';
    END IF;
END
$verify$;

COMMENT ON CONSTRAINT herbs_category_check ON herbs IS
    'Thirteen canonical catalog groups; fibres, probiotics and prebiotics belong to supplements.';
COMMENT ON CONSTRAINT herbs_product_species_check ON herbs IS
    'Four botanical groups require taxonomy; nine product groups require SQL NULL family and Latin name.';
COMMENT ON INDEX herbs_product_ro_unique IS
    'One normalized product name across all nine product groups.';
