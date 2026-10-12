-- Add premenopauza and its synonyms. Safe to run more than once.
INSERT INTO medical_conditions (name)
VALUES ('premenopauza')
ON CONFLICT (name) DO NOTHING;

INSERT INTO medical_condition_synonyms (medical_condition_id, synonym)
SELECT c.id, s.synonym
FROM medical_conditions c
CROSS JOIN (
    VALUES
        (1, 'perimenopauză'),
        (2, 'tranziție la menopauză'),
        (3, 'climateriu'),
        (4, 'debutul menopauzei'),
        (5, 'Perimenopause'),
        (6, 'menopausal transition'),
        (7, 'climacteric'),
        (8, 'premenopause'),
        (9, 'early stage of menopause')
) AS s(position, synonym)
WHERE c.name = 'premenopauza'
ORDER BY s.position
ON CONFLICT (medical_condition_id, synonym) DO NOTHING;
