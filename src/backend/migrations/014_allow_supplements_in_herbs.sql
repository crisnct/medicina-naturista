-- Product families are technical catalog groups; they do not classify clinical efficacy.
ALTER TABLE herbs ALTER COLUMN latin DROP NOT NULL;
ALTER TABLE herbs DROP CONSTRAINT herbs_ro_check1;
ALTER TABLE herbs DROP CONSTRAINT herbs_en_check;

ALTER TABLE herbs ADD CONSTRAINT herbs_product_species_check CHECK (
    CASE WHEN family IN (
        'suplimente', 'uleiuri esentiale', 'aminoacizi', 'vitamine', 'minerale',
        'produse apicole', 'fibre, probiotice, prebiotice'
    ) THEN latin IS NULL
    ELSE latin IS NOT NULL AND btrim(latin) <> '' END
);
ALTER TABLE herbs ADD CONSTRAINT herbs_ro_case_check CHECK (
    family IN (
        'suplimente', 'uleiuri esentiale', 'aminoacizi', 'vitamine', 'minerale',
        'produse apicole', 'fibre, probiotice, prebiotice'
    ) OR ro = lower(ro)
);
ALTER TABLE herbs ADD CONSTRAINT herbs_en_case_check CHECK (
    family IN (
        'suplimente', 'uleiuri esentiale', 'aminoacizi', 'vitamine', 'minerale',
        'produse apicole', 'fibre, probiotice, prebiotice'
    ) OR en = lower(en)
);
CREATE UNIQUE INDEX herbs_product_ro_unique ON herbs (lower(btrim(ro)))
WHERE family IN (
    'suplimente', 'uleiuri esentiale', 'aminoacizi', 'vitamine', 'minerale',
    'produse apicole', 'fibre, probiotice, prebiotice'
);

COMMENT ON COLUMN herbs.latin IS
    'Unique botanical species name; SQL NULL for the seven technical product families.';
COMMENT ON COLUMN herbs.family IS
    'Botanical family or an explicitly supported technical product group; existing groups are preserved.';
COMMENT ON CONSTRAINT herbs_product_species_check ON herbs IS
    'Products have no invented species; botanical entries still require a nonempty Latin name.';
COMMENT ON CONSTRAINT herbs_ro_case_check ON herbs IS
    'Product labels preserve requested capitalization; botanical names remain lowercase.';
COMMENT ON CONSTRAINT herbs_en_case_check ON herbs IS
    'Product English names preserve requested capitalization; botanical names remain lowercase.';
COMMENT ON INDEX herbs_product_ro_unique IS
    'One product name across all seven product families, irrespective of case or surrounding spaces.';
