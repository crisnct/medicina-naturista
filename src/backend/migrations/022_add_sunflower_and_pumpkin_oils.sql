-- Add only the two requested missing oils; retain all existing catalog identities.
CREATE TEMP TABLE new_oils (ro text PRIMARY KEY, en text NOT NULL) ON COMMIT DROP;
INSERT INTO new_oils (ro, en) VALUES
    ('ulei de floarea-soarelui', 'sunflower oil'),
    ('ulei de dovleac', 'pumpkin seed oil');

DO $guard$
BEGIN
    IF EXISTS (
        SELECT FROM new_oils n JOIN (
            SELECT ro AS name FROM herbs UNION ALL SELECT latin FROM herbs
            UNION ALL SELECT en FROM herbs UNION ALL SELECT name FROM herb_aliases
        ) names ON btrim(regexp_replace(lower(unaccent(names.name)), '[^a-z0-9]+', ' ', 'g'))
            IN (btrim(regexp_replace(n.ro, '[^a-z0-9]+', ' ', 'g')), n.en)
    ) THEN
        RAISE EXCEPTION 'NEW_OIL_ALREADY_EXISTS';
    END IF;
END
$guard$;

CREATE TEMP TABLE new_oils_before ON COMMIT DROP AS SELECT * FROM herbs;
INSERT INTO herbs (category, family, latin, ro, en)
    SELECT 'uleiuri', NULL, NULL, ro, en FROM new_oils ORDER BY ro;

DO $verify$
BEGIN
    IF (SELECT count(*) FROM herbs) <> (SELECT count(*) + 2 FROM new_oils_before)
        OR EXISTS (
            SELECT FROM new_oils_before b LEFT JOIN herbs h ON h.id = b.id
            WHERE h.id IS NULL OR ROW(h.category, h.family, h.latin, h.ro, h.en, h.ranking)
                IS DISTINCT FROM ROW(b.category, b.family, b.latin, b.ro, b.en, b.ranking)
        )
        OR (SELECT count(*) FROM new_oils n JOIN herbs h
            ON h.ro = n.ro AND h.en = n.en AND h.category = 'uleiuri'
            AND h.latin IS NULL AND h.family IS NULL AND h.ranking = 0) <> 2
    THEN
        RAISE EXCEPTION 'NEW_OIL_PUBLICATION_MISMATCH';
    END IF;
END
$verify$;
