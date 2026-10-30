-- Corpus associations and product names share the catalog language contract.
ALTER TABLE herbs_benefits ADD COLUMN language TEXT NOT NULL DEFAULT 'ro'
    CHECK (language IN ('ro','en'));
COMMENT ON COLUMN herbs_benefits.language IS 'Language of the corpus supporting this co-occurrence.';
DROP INDEX herbs_benefits_herb_condition_uq;
ALTER TABLE herbs_benefits ADD UNIQUE (herb_id,medical_condition_id,language);

-- Species without a common English name retain their scientific name, never a Romanian substitute.
UPDATE herbs h SET en=coalesce((SELECT a.name FROM herb_aliases a WHERE a.herb_id=h.id AND a.kind='en_alt' ORDER BY a.id LIMIT 1),h.latin) WHERE btrim(h.en)='' AND h.latin IS NOT NULL;
