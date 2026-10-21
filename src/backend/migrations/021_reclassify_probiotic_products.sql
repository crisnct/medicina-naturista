-- Reclassify four existing probiotic products without changing identity or ranking evidence.
CREATE TEMP TABLE probiotic_moves (
    id bigint PRIMARY KEY,
    ro text NOT NULL,
    en text NOT NULL
) ON COMMIT DROP;
INSERT INTO probiotic_moves (id, ro, en) VALUES
    (1191, 'Biogaia Prodendis', 'Biogaia Prodendis'),
    (1192, 'Biothin Probiotic', 'Biothin Probiotic'),
    (1195, 'Digestive Advantage', 'Digestive Advantage'),
    (1198, 'Mood Probiotic', 'Mood Probiotic');

DO $guard$
BEGIN
    IF EXISTS (
        SELECT FROM probiotic_moves m LEFT JOIN herbs h ON h.id = m.id
        WHERE h.id IS NULL OR h.ro IS DISTINCT FROM m.ro OR h.en IS DISTINCT FROM m.en
            OR h.category <> 'suplimente' OR h.family IS NOT NULL OR h.latin IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'PROBIOTIC_IDENTITY_MISMATCH';
    END IF;
END
$guard$;

CREATE TEMP TABLE probiotics_before ON COMMIT DROP AS SELECT * FROM herbs;
UPDATE herbs h SET category = 'fibre, probiotice, prebiotice' FROM probiotic_moves m WHERE h.id = m.id;

DO $verify$
BEGIN
    IF (SELECT count(*) FROM herbs) <> (SELECT count(*) FROM probiotics_before)
        OR EXISTS (
            SELECT FROM probiotics_before b LEFT JOIN herbs h ON h.id = b.id
            LEFT JOIN probiotic_moves m ON m.id = b.id
            WHERE h.id IS NULL OR ROW(h.family, h.latin, h.ro, h.en, h.ranking, h.category)
                IS DISTINCT FROM ROW(b.family, b.latin, b.ro, b.en, b.ranking,
                    CASE WHEN m.id IS NULL THEN b.category ELSE 'fibre, probiotice, prebiotice' END)
        ) THEN
        RAISE EXCEPTION 'PROBIOTIC_PUBLICATION_MISMATCH';
    END IF;
END
$verify$;
