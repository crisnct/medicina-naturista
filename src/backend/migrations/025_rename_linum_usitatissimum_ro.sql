-- Rename only the requested species; retain its identity, taxonomy and ranking evidence.
DO $rename$
DECLARE
    renamed_count integer;
BEGIN
    UPDATE herbs SET ro = 'seminte de in'
    WHERE latin = 'linum usitatissimum' AND ro = 'in';

    GET DIAGNOSTICS renamed_count = ROW_COUNT;
    IF renamed_count <> 1 THEN
        RAISE EXCEPTION 'LINUM_USITATISSIMUM_RENAME_IDENTITY_MISMATCH';
    END IF;
END
$rename$;
