-- Plain English names of Gripa; the catalog only had "seasonal flu". Safe to run more than once.
INSERT INTO medical_condition_synonyms (medical_condition_id, synonym)
SELECT c.id, s.synonym
FROM medical_conditions c
CROSS JOIN (VALUES ('flu'), ('the flu')) AS s(synonym)
WHERE c.name = 'Gripa'
ON CONFLICT (medical_condition_id, synonym) DO NOTHING;
