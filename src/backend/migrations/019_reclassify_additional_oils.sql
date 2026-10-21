-- Move only the explicitly approved oil identities; retain names and ranking evidence.
CREATE TEMP TABLE additional_oil_moves (
    id bigint PRIMARY KEY,
    ro text NOT NULL,
    en text NOT NULL
) ON COMMIT DROP;
INSERT INTO additional_oil_moves (id, ro, en) VALUES
    (1294, 'ulei de avocado', 'avocado oil'),
    (1298, 'ulei de catina', 'sea buckthorn oil'),
    (1301, 'ulei de cocos', 'coconut oil'),
    (1303, 'ulei de in', 'flaxseed oil'),
    (1304, 'ulei de krill', 'krill oil'),
    (1310, 'ulei de peste', 'fish oil'),
    (1311, 'ulei de primula', 'evening primrose oil');

DO $guard$
BEGIN
    IF EXISTS (
        SELECT FROM additional_oil_moves m LEFT JOIN herbs h ON h.id = m.id
        WHERE h.id IS NULL OR h.ro IS DISTINCT FROM m.ro OR h.en IS DISTINCT FROM m.en
            OR h.category <> 'suplimente' OR h.family IS NOT NULL OR h.latin IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'ADDITIONAL_OIL_IDENTITY_MISMATCH';
    END IF;
END
$guard$;

CREATE TEMP TABLE additional_oils_before ON COMMIT DROP AS SELECT * FROM herbs;
UPDATE herbs h SET category = 'uleiuri' FROM additional_oil_moves m WHERE h.id = m.id;

DO $verify$
BEGIN
    IF (SELECT count(*) FROM herbs) <> (SELECT count(*) FROM additional_oils_before)
        OR EXISTS (
            SELECT FROM additional_oils_before b LEFT JOIN herbs h ON h.id = b.id
            LEFT JOIN additional_oil_moves m ON m.id = b.id
            WHERE h.id IS NULL OR ROW(h.family, h.latin, h.ro, h.en, h.ranking, h.category)
                IS DISTINCT FROM ROW(b.family, b.latin, b.ro, b.en, b.ranking,
                    CASE WHEN m.id IS NULL THEN b.category ELSE 'uleiuri' END)
        ) THEN
        RAISE EXCEPTION 'ADDITIONAL_OIL_PUBLICATION_MISMATCH';
    END IF;
END
$verify$;
