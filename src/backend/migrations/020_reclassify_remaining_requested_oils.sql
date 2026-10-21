-- Move only the explicitly approved oil identities; retain names and ranking evidence.
CREATE TEMP TABLE requested_oil_moves (
    id bigint PRIMARY KEY,
    ro text NOT NULL,
    en text NOT NULL
) ON COMMIT DROP;
INSERT INTO requested_oil_moves (id, ro, en) VALUES
    (1293, 'ulei de argan', 'argan oil'),
    (1295, 'ulei de bame - seminte', 'okra seed oil'),
    (1296, 'ulei de caise - samburi', 'apricot kernel oil'),
    (1297, 'ulei de castraveti - seminte', 'cucumber seed oil'),
    (1299, 'ulei de cirese - samburi', 'cherry kernel oil'),
    (1300, 'ulei de coacaze negre - seminte', 'blackcurrant seed oil'),
    (1302, 'ulei de fistic', 'pistachio oil'),
    (1305, 'ulei de macadamia', 'macadamia oil'),
    (1306, 'ulei de macese', 'rosehip oil'),
    (1308, 'ulei de neem', 'neem oil'),
    (1309, 'ulei de papaya - seminte', 'papaya seed oil'),
    (1312, 'ulei de tamanu', 'tamanu oil'),
    (1313, 'ulei de tarate de orez', 'rice bran oil');

DO $guard$
BEGIN
    IF EXISTS (
        SELECT FROM requested_oil_moves m LEFT JOIN herbs h ON h.id = m.id
        WHERE h.id IS NULL OR h.ro IS DISTINCT FROM m.ro OR h.en IS DISTINCT FROM m.en
            OR h.category <> 'suplimente' OR h.family IS NOT NULL OR h.latin IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'REQUESTED_OIL_IDENTITY_MISMATCH';
    END IF;
END
$guard$;

CREATE TEMP TABLE requested_oils_before ON COMMIT DROP AS SELECT * FROM herbs;
UPDATE herbs h SET category = 'uleiuri' FROM requested_oil_moves m WHERE h.id = m.id;

DO $verify$
BEGIN
    IF (SELECT count(*) FROM herbs) <> (SELECT count(*) FROM requested_oils_before)
        OR EXISTS (
            SELECT FROM requested_oils_before b LEFT JOIN herbs h ON h.id = b.id
            LEFT JOIN requested_oil_moves m ON m.id = b.id
            WHERE h.id IS NULL OR ROW(h.family, h.latin, h.ro, h.en, h.ranking, h.category)
                IS DISTINCT FROM ROW(b.family, b.latin, b.ro, b.en, b.ranking,
                    CASE WHEN m.id IS NULL THEN b.category ELSE 'uleiuri' END)
        ) THEN
        RAISE EXCEPTION 'REQUESTED_OIL_PUBLICATION_MISMATCH';
    END IF;
END
$verify$;
