-- Match mixed Romanian/English oil names without guessing botanical variants or chemotypes.
WITH oil_names AS (
    SELECT id AS herb_id,
           'ulei esential de ' || regexp_replace(lower(btrim(en)), ' essential oil$', '') AS name
    FROM herbs
    WHERE category = 'uleiuri esentiale' AND lower(btrim(en)) LIKE '% essential oil'
), unambiguous AS (
    SELECT min(herb_id) AS herb_id, name
    FROM oil_names
    GROUP BY name
    HAVING count(DISTINCT herb_id) = 1
)
INSERT INTO herb_aliases(herb_id, name, kind)
SELECT u.herb_id, u.name, 'en_alt'
FROM unambiguous u
JOIN herbs h ON h.id = u.herb_id
WHERE lower(btrim(h.ro)) <> u.name
  AND lower(btrim(h.en)) <> u.name
  AND NOT EXISTS (
      SELECT FROM herbs other
      WHERE other.id <> u.herb_id
        AND (lower(btrim(other.ro)) = u.name OR lower(btrim(other.en)) = u.name)
  )
  AND NOT EXISTS (
      SELECT FROM herb_aliases a
      WHERE lower(btrim(a.name)) = u.name AND a.herb_id <> u.herb_id
  )
ORDER BY u.herb_id, u.name
ON CONFLICT (herb_id, kind, name) DO NOTHING;
