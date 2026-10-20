-- Rebuild only herbs to provide the requested physical column order.
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '120s';
LOCK TABLE herbs, herb_aliases, herbs_benefits IN ACCESS EXCLUSIVE MODE;

DO $migration$
DECLARE
    categories CONSTANT text[] := ARRAY[
        'suplimente', 'uleiuri esentiale', 'aminoacizi', 'vitamine', 'minerale',
        'produse apicole', 'fibre, probiotice, prebiotice'
    ];
    item record;
    owner_name text;
    sequence_comment text;
BEGIN
    IF to_regclass('herbs_next') IS NOT NULL OR to_regclass('herbs_previous') IS NOT NULL THEN
        RAISE EXCEPTION 'HERB_CATEGORY_INTERMEDIATE_TABLE_EXISTS';
    END IF;
    IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute
        WHERE attrelid='herbs'::regclass AND attnum > 0 AND NOT attisdropped)
        <> ARRAY['id','family','latin','ro','en','ranking'] THEN
        RAISE EXCEPTION 'HERB_CATEGORY_UNEXPECTED_COLUMNS';
    END IF;
    -- Unknown privileges, policies, triggers or dependencies need an explicit migration.
    IF EXISTS (SELECT FROM pg_class WHERE oid='herbs'::regclass
        AND (relacl IS NOT NULL OR relrowsecurity OR relforcerowsecurity
             OR relkind <> 'r' OR relispartition OR reloptions IS NOT NULL
             OR reltablespace <> 0 OR relreplident <> 'd' OR relpersistence <> 'p'))
        OR EXISTS (SELECT FROM pg_attribute WHERE attrelid='herbs'::regclass
                   AND (attacl IS NOT NULL OR attisdropped))
        OR EXISTS (SELECT FROM pg_trigger WHERE tgrelid='herbs'::regclass AND NOT tgisinternal)
        OR EXISTS (SELECT FROM pg_policy WHERE polrelid='herbs'::regclass)
        OR EXISTS (SELECT FROM pg_inherits WHERE inhparent='herbs'::regclass
                   OR inhrelid='herbs'::regclass) THEN
        RAISE EXCEPTION 'HERB_CATEGORY_UNSUPPORTED_TABLE_CONFIGURATION';
    END IF;
    IF (SELECT array_agg(indexrelid::regclass::text ORDER BY indexrelid::regclass::text)
        FROM pg_index WHERE indrelid='herbs'::regclass)
        <> ARRAY['herbs_latin_key','herbs_pkey','herbs_product_ro_unique'] THEN
        RAISE EXCEPTION 'HERB_CATEGORY_UNEXPECTED_INDEXES';
    END IF;
    IF (SELECT count(*) FROM pg_constraint WHERE conrelid='herbs'::regclass) <> 12
        OR EXISTS (SELECT FROM pg_constraint WHERE conrelid='herbs'::regclass
                   AND conname NOT IN ('herbs_id_check','herbs_family_check',
                       'herbs_family_check1','herbs_latin_check','herbs_latin_check1',
                       'herbs_ro_check','herbs_pkey','herbs_latin_key','herbs_ranking_check',
                       'herbs_product_species_check','herbs_ro_case_check','herbs_en_case_check'))
        OR (SELECT count(*) FROM pg_constraint WHERE confrelid='herbs'::regclass) <> 2
        OR EXISTS (SELECT FROM pg_constraint WHERE confrelid='herbs'::regclass AND NOT (
            contype='f' AND confdeltype='c' AND confupdtype='a' AND confmatchtype='s'
            AND NOT condeferrable AND convalidated AND conkey=ARRAY[2]::smallint[]
            AND confkey=ARRAY[1]::smallint[] AND (
                (conrelid='herb_aliases'::regclass AND conname='herb_aliases_herb_id_fkey') OR
                (conrelid='herbs_benefits'::regclass AND conname='herbs_benefits_herb_id_fkey')))) THEN
        RAISE EXCEPTION 'HERB_CATEGORY_UNEXPECTED_CONSTRAINTS';
    END IF;
    IF EXISTS (SELECT FROM pg_depend d WHERE refclassid='pg_class'::regclass
        AND refobjid='herbs'::regclass AND deptype='n' AND NOT (
            classid='pg_constraint'::regclass AND EXISTS (
                SELECT FROM pg_constraint c WHERE c.oid=d.objid AND
                (c.conrelid='herbs'::regclass OR c.conname IN
                 ('herb_aliases_herb_id_fkey','herbs_benefits_herb_id_fkey'))))) THEN
        RAISE EXCEPTION 'HERB_CATEGORY_UNSUPPORTED_DEPENDENCY';
    END IF;
    IF EXISTS (SELECT FROM pg_depend WHERE refclassid='pg_type'::regclass
        AND refobjid=(SELECT reltype FROM pg_class WHERE oid='herbs'::regclass)
        AND deptype='n') THEN
        RAISE EXCEPTION 'HERB_CATEGORY_UNSUPPORTED_ROW_TYPE_DEPENDENCY';
    END IF;
    IF EXISTS (SELECT FROM herbs WHERE
        (latin IS NULL AND (family IS NULL OR family <> ALL(categories))) OR
        (latin IS NOT NULL AND (btrim(latin)='' OR family IS NULL
            OR btrim(family)='' OR family=ANY(categories)))) THEN
        RAISE EXCEPTION 'HERB_CATEGORY_UNMAPPED_ROW';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_attribute WHERE attrelid='herbs'::regclass
        AND attname='id' AND attidentity='a')
        OR pg_get_serial_sequence('herbs','id') <> 'public.herbs_id_seq' THEN
        RAISE EXCEPTION 'HERB_CATEGORY_UNEXPECTED_IDENTITY';
    END IF;
    IF EXISTS (SELECT FROM pg_attribute WHERE attrelid='herbs'::regclass AND attnum>0
        AND (atttypid <> CASE WHEN attname IN ('id','ranking') THEN 'bigint'::regtype
                             ELSE 'text'::regtype END
             OR atttypmod <> -1 OR attgenerated <> ''
             OR attcollation <> CASE WHEN attname IN ('id','ranking') THEN 0
                                    ELSE 'default'::regcollation::oid END
             OR attnotnull <> (attname <> 'latin')))
        OR EXISTS (SELECT FROM pg_sequence
            WHERE seqrelid=pg_get_serial_sequence('herbs','id')::regclass
            AND (seqtypid <> 'bigint'::regtype OR seqstart <> 1 OR seqincrement <> 1
                 OR seqmin <> 1 OR seqmax <> 9223372036854775807 OR seqcache <> 1 OR seqcycle)) THEN
        RAISE EXCEPTION 'HERB_CATEGORY_UNEXPECTED_COLUMN_OR_SEQUENCE_TYPE';
    END IF;

    CREATE TABLE herbs_next (
        id BIGINT GENERATED ALWAYS AS IDENTITY (START WITH 1 INCREMENT BY 1)
            PRIMARY KEY CHECK (id > 0),
        category TEXT NOT NULL CHECK (category IN (
            'plante medicinale', 'suplimente', 'uleiuri esentiale', 'aminoacizi',
            'vitamine', 'minerale', 'produse apicole', 'fibre, probiotice, prebiotice')),
        family TEXT CHECK (btrim(family) <> '') CHECK (family=lower(family)),
        latin TEXT UNIQUE CHECK (btrim(latin) <> '') CHECK (latin=lower(latin)),
        ro TEXT NOT NULL CHECK (btrim(ro) <> ''),
        en TEXT NOT NULL DEFAULT '',
        ranking BIGINT NOT NULL DEFAULT 0 CHECK (ranking >= 0),
        CONSTRAINT herbs_product_species_check CHECK (
            (category='plante medicinale' AND latin IS NOT NULL AND family IS NOT NULL)
            OR (category <> 'plante medicinale' AND latin IS NULL AND family IS NULL)),
        CONSTRAINT herbs_ro_case_check CHECK (category <> 'plante medicinale' OR ro=lower(ro)),
        CONSTRAINT herbs_en_case_check CHECK (category <> 'plante medicinale' OR en=lower(en))
    );
    CREATE UNIQUE INDEX herbs_next_product_ro_unique ON herbs_next (lower(btrim(ro)))
        WHERE category IN ('suplimente','uleiuri esentiale','aminoacizi','vitamine',
            'minerale','produse apicole','fibre, probiotice, prebiotice');
    -- Copy unchanged checks/defaults verbatim, including any stricter local definitions.
    FOR item IN SELECT conname, pg_get_constraintdef(oid) AS definition,
        obj_description(oid,'pg_constraint') AS description
        FROM pg_constraint WHERE conrelid='herbs'::regclass
        AND conname NOT IN ('herbs_product_species_check','herbs_ro_case_check','herbs_en_case_check')
    LOOP
        IF item.conname NOT IN ('herbs_pkey','herbs_latin_key') THEN
            EXECUTE format('ALTER TABLE herbs_next DROP CONSTRAINT %I',
                replace(item.conname,'herbs_','herbs_next_'));
            EXECUTE format('ALTER TABLE herbs_next ADD CONSTRAINT %I %s',
                replace(item.conname,'herbs_','herbs_next_'),item.definition);
        END IF;
        EXECUTE format('COMMENT ON CONSTRAINT %I ON herbs_next IS %L',
            replace(item.conname,'herbs_','herbs_next_'),item.description);
    END LOOP;
    FOR item IN SELECT a.attname, pg_get_expr(d.adbin,d.adrelid) AS expression
        FROM pg_attribute a LEFT JOIN pg_attrdef d
        ON d.adrelid=a.attrelid AND d.adnum=a.attnum
        WHERE a.attrelid='herbs'::regclass AND a.attname IN ('en','ranking')
    LOOP
        IF item.expression IS NULL THEN
            EXECUTE format('ALTER TABLE herbs_next ALTER COLUMN %I DROP DEFAULT',item.attname);
        ELSE
            EXECUTE format('ALTER TABLE herbs_next ALTER COLUMN %I SET DEFAULT %s',
                item.attname,item.expression);
        END IF;
    END LOOP;
    INSERT INTO herbs_next (id,category,family,latin,ro,en,ranking) OVERRIDING SYSTEM VALUE
    SELECT id, CASE WHEN latin IS NOT NULL THEN 'plante medicinale' ELSE family END,
        CASE WHEN latin IS NOT NULL THEN family ELSE NULL END, latin,ro,en,ranking FROM herbs;
    IF EXISTS (
        (SELECT id, CASE WHEN latin IS NOT NULL THEN 'plante medicinale' ELSE family END,
            CASE WHEN latin IS NOT NULL THEN family ELSE NULL END, latin,ro,en,ranking FROM herbs
         EXCEPT ALL SELECT id,category,family,latin,ro,en,ranking FROM herbs_next)
        UNION ALL
        (SELECT id,category,family,latin,ro,en,ranking FROM herbs_next EXCEPT ALL
         SELECT id, CASE WHEN latin IS NOT NULL THEN 'plante medicinale' ELSE family END,
            CASE WHEN latin IS NOT NULL THEN family ELSE NULL END, latin,ro,en,ranking FROM herbs)
    ) THEN
        RAISE EXCEPTION 'HERB_CATEGORY_COPY_MISMATCH';
    END IF;

    SELECT pg_get_userbyid(relowner) INTO owner_name FROM pg_class WHERE oid='herbs'::regclass;
    SELECT obj_description('herbs_id_seq'::regclass,'pg_class') INTO sequence_comment;
    EXECUTE format('ALTER TABLE herbs_next OWNER TO %I', owner_name);
    IF (SELECT relacl FROM pg_class WHERE oid='herbs_next'::regclass) IS NOT NULL THEN
        RAISE EXCEPTION 'HERB_CATEGORY_UNEXPECTED_DEFAULT_PRIVILEGES';
    END IF;
    FOR item IN SELECT a.attname, col_description(a.attrelid,a.attnum) AS description
        FROM pg_attribute a WHERE a.attrelid='herbs'::regclass AND a.attnum>0
    LOOP
        EXECUTE format('COMMENT ON COLUMN herbs_next.%I IS %L', item.attname,item.description);
    END LOOP;
    EXECUTE format('COMMENT ON TABLE herbs_next IS %L', obj_description('herbs'::regclass));
    FOR item IN SELECT indexrelid::regclass::text AS name,
        obj_description(indexrelid,'pg_class') AS description FROM pg_index
        WHERE indrelid='herbs'::regclass AND indexrelid <> 'herbs_product_ro_unique'::regclass
    LOOP
        EXECUTE format('COMMENT ON INDEX %I IS %L',
            replace(item.name,'herbs_','herbs_next_'),item.description);
    END LOOP;
    FOR item IN SELECT conname, obj_description(oid,'pg_constraint') AS description
        FROM pg_constraint WHERE conrelid='herbs'::regclass
        AND conname IN ('herbs_product_species_check','herbs_ro_case_check','herbs_en_case_check')
    LOOP
        EXECUTE format('COMMENT ON CONSTRAINT %I ON herbs_next IS %L',item.conname,item.description);
    END LOOP;
    ALTER TABLE herb_aliases DROP CONSTRAINT herb_aliases_herb_id_fkey;
    ALTER TABLE herbs_benefits DROP CONSTRAINT herbs_benefits_herb_id_fkey;
    ALTER TABLE herbs RENAME TO herbs_previous;
    ALTER TABLE herbs_next RENAME TO herbs;
    ALTER TABLE herb_aliases ADD CONSTRAINT herb_aliases_herb_id_fkey
        FOREIGN KEY (herb_id) REFERENCES herbs(id) ON DELETE CASCADE;
    ALTER TABLE herbs_benefits ADD CONSTRAINT herbs_benefits_herb_id_fkey
        FOREIGN KEY (herb_id) REFERENCES herbs(id) ON DELETE CASCADE;
    DROP TABLE herbs_previous RESTRICT;
    FOR item IN SELECT conname FROM pg_constraint WHERE conrelid='herbs'::regclass
        AND conname LIKE 'herbs_next_%'
    LOOP
        EXECUTE format('ALTER TABLE herbs RENAME CONSTRAINT %I TO %I',
            item.conname, replace(item.conname,'herbs_next_','herbs_'));
    END LOOP;
    ALTER INDEX herbs_next_product_ro_unique RENAME TO herbs_product_ro_unique;
    ALTER SEQUENCE herbs_next_id_seq RENAME TO herbs_id_seq;
    EXECUTE format('COMMENT ON SEQUENCE herbs_id_seq IS %L',sequence_comment);
    PERFORM setval('herbs_id_seq', COALESCE((SELECT max(id) FROM herbs),1),
        EXISTS (SELECT FROM herbs));
END
$migration$;

COMMENT ON COLUMN herbs.category IS
    'Technical catalog category, separate from botanical taxonomy; not a clinical efficacy claim.';
COMMENT ON COLUMN herbs.family IS
    'Original lowercase botanical family for plante medicinale; SQL NULL for products.';
COMMENT ON COLUMN herbs.latin IS
    'Unique lowercase botanical species name; SQL NULL for products.';
COMMENT ON CONSTRAINT herbs_product_species_check ON herbs IS
    'Botanical entries require family and Latin name; products require SQL NULL for both.';
COMMENT ON INDEX herbs_product_ro_unique IS
    'One product name across all seven product categories, irrespective of case or surrounding spaces.';
