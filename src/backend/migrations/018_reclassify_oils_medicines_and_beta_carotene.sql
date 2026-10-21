-- Reclassify three existing identities without changing names, taxonomy or rankings.
CREATE TEMP TABLE product_category_moves (
    id bigint PRIMARY KEY,
    ro text NOT NULL,
    en text NOT NULL,
    category text NOT NULL
) ON COMMIT DROP;
INSERT INTO product_category_moves (id, ro, en, category) VALUES
    (1212, 'aspirina', 'aspirin', 'medicamente'),
    (1215, 'beta-caroten', 'beta-carotene', 'vitamine'),
    (1307, 'ulei de masline', 'olive oil', 'uleiuri');

DO $guard$
BEGIN
    IF EXISTS (
        SELECT FROM product_category_moves m LEFT JOIN herbs h ON h.id = m.id
        WHERE h.id IS NULL OR h.ro IS DISTINCT FROM m.ro OR h.en IS DISTINCT FROM m.en
            OR h.category <> 'suplimente' OR h.family IS NOT NULL OR h.latin IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'PRODUCT_CATEGORY_IDENTITY_MISMATCH';
    END IF;
END
$guard$;

CREATE TEMP TABLE product_categories_before ON COMMIT DROP AS SELECT * FROM herbs;

ALTER TABLE herbs DROP CONSTRAINT herbs_category_check,
    DROP CONSTRAINT herbs_product_species_check;
ALTER TABLE herbs ADD CONSTRAINT herbs_category_check CHECK (category IN (
    'plante medicinale', 'fructe', 'legume', 'cereale', 'seminte',
    'uleiuri esentiale', 'uleiuri', 'suplimente', 'medicamente', 'aminoacizi',
    'vitamine', 'minerale', 'produse apicole', 'fibre, probiotice, prebiotice'
)), ADD CONSTRAINT herbs_product_species_check CHECK (
    (category IN ('plante medicinale', 'fructe', 'legume', 'cereale')
        AND latin IS NOT NULL AND family IS NOT NULL)
    OR (category IN ('seminte', 'uleiuri esentiale', 'uleiuri', 'suplimente',
        'medicamente', 'aminoacizi', 'vitamine', 'minerale', 'produse apicole',
        'fibre, probiotice, prebiotice') AND latin IS NULL AND family IS NULL)
);
DROP INDEX herbs_product_ro_unique;
CREATE UNIQUE INDEX herbs_product_ro_unique ON herbs (lower(btrim(ro)))
    WHERE category IN ('seminte', 'uleiuri esentiale', 'uleiuri', 'suplimente',
        'medicamente', 'aminoacizi', 'vitamine', 'minerale', 'produse apicole',
        'fibre, probiotice, prebiotice');

UPDATE herbs h SET category = m.category FROM product_category_moves m WHERE h.id = m.id;

DO $verify$
BEGIN
    IF (SELECT count(*) FROM herbs) <> (SELECT count(*) FROM product_categories_before)
        OR EXISTS (
            SELECT FROM product_categories_before b LEFT JOIN herbs h ON h.id = b.id
            LEFT JOIN product_category_moves m ON m.id = b.id
            WHERE h.id IS NULL OR ROW(h.family, h.latin, h.ro, h.en, h.ranking, h.category)
                IS DISTINCT FROM ROW(b.family, b.latin, b.ro, b.en, b.ranking,
                    coalesce(m.category, b.category))
        ) THEN
        RAISE EXCEPTION 'PRODUCT_CATEGORY_PUBLICATION_MISMATCH';
    END IF;
END
$verify$;

COMMENT ON CONSTRAINT herbs_category_check ON herbs IS
    'Fourteen canonical catalog groups, without diacritics.';
COMMENT ON CONSTRAINT herbs_product_species_check ON herbs IS
    'Four botanical groups require taxonomy; ten product groups require SQL NULL family and Latin name.';
COMMENT ON INDEX herbs_product_ro_unique IS
    'One normalized product name across all ten product groups, including oils and medicines.';
