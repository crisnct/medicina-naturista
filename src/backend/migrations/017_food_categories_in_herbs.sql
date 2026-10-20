-- Explicit food grouping, preserving taxonomy, identities and the physical table.
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '120s';
LOCK TABLE herbs, herb_aliases, herbs_benefits IN ACCESS EXCLUSIVE MODE;
DO $guard$
BEGIN
    IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute
        WHERE attrelid='herbs'::regclass AND attnum>0 AND NOT attisdropped)
        IS DISTINCT FROM ARRAY['id','category','family','latin','ro','en','ranking']
        OR NOT EXISTS (SELECT FROM schema_migrations WHERE version='016_separate_herb_category.sql')
        OR (SELECT count(*) FROM pg_constraint WHERE conrelid='herbs'::regclass
            AND conname IN ('herbs_category_check','herbs_product_species_check',
                'herbs_ro_case_check','herbs_en_case_check')) <> 4
        OR to_regclass('herbs_product_ro_unique') IS NULL
        OR EXISTS (SELECT FROM pg_trigger WHERE tgrelid='herbs'::regclass AND NOT tgisinternal)
    THEN RAISE EXCEPTION 'HERB_FOOD_UNEXPECTED_SCHEMA'; END IF;
END
$guard$;
CREATE TEMP TABLE herb_food_updates (id bigint PRIMARY KEY, latin text UNIQUE, ro text, category text) ON COMMIT DROP;
INSERT INTO herb_food_updates (id,latin,ro,category) VALUES
    (3, 'malpighia glabra', 'acerola', 'fructe'),
    (10, 'vaccinium myrtillus', 'afin', 'fructe'),
    (15, 'ribes uva-crispa', 'agris', 'fructe'),
    (16, 'allium victorialis', 'ai de munte', 'legume'),
    (17, 'allium scorodoprasum', 'aiul sarpelui', 'legume'),
    (27, 'corylus avellana', 'alun', 'fructe'),
    (28, 'corylus colurna', 'alun turcesc', 'fructe'),
    (29, 'amaranthus paniculatus', 'amarant paniculat', 'cereale'),
    (30, 'amaranthus viridis', 'amaranthus viridis', 'legume'),
    (35, 'phyllanthus emblica', 'amla', 'fructe'),
    (38, 'ananas comosus', 'ananas', 'fructe'),
    (41, 'cichorium endivia', 'andiva', 'legume'),
    (47, 'cynara scolymus', 'anghinare', 'legume'),
    (52, 'arachis hypogaea', 'arahide', 'fructe'),
    (63, 'capsicum annuum', 'ardei', 'legume'),
    (64, 'capsicum frutescens', 'ardei iute', 'legume'),
    (69, 'allium schoenoprasum', 'arpagic', 'legume'),
    (80, 'crataegus azarolus', 'azarol', 'fructe'),
    (83, 'abelmoschus esculentus', 'bame', 'legume'),
    (84, 'musa paradisiaca', 'banan', 'fructe'),
    (95, 'vicia faba', 'bob', 'legume'),
    (145, 'prunus armeniaca', 'cais', 'fructe'),
    (147, 'citrus microcarpa', 'calamondin', 'fructe'),
    (158, 'fragaria x ananassa', 'capsun', 'fructe'),
    (159, 'fragaria viridis', 'capsun de camp', 'fructe'),
    (166, 'cynara cardunculus', 'cardon', 'legume'),
    (168, 'solanum tuberosum', 'cartof', 'legume'),
    (169, 'ipomoea batatas', 'cartof dulce', 'legume'),
    (172, 'castanea sativa', 'castan comestibil', 'fructe'),
    (174, 'cucumis sativus', 'castravete', 'legume'),
    (175, 'momordica charantia', 'castravete amar', 'legume'),
    (178, 'hippophae rhamnoides', 'catina-alba', 'fructe'),
    (189, 'allium cepa', 'ceapa', 'legume'),
    (208, 'citrus medica', 'chitru', 'fructe'),
    (210, 'cichorium intybus', 'cicoare', 'legume'),
    (233, 'prunus avium', 'cires', 'fructe'),
    (247, 'ribes aureum', 'coacaz auriu', 'fructe'),
    (248, 'ribes nigrum', 'coacaz negru', 'fructe'),
    (249, 'ribes rubrum', 'coacaz rosu', 'fructe'),
    (260, 'coccinia grandis', 'coccinia grandis', 'legume'),
    (263, 'cocos nucifera', 'cocotier', 'fructe'),
    (279, 'cornus mas', 'corn', 'fructe'),
    (290, 'lepidium sativum', 'creson', 'legume'),
    (309, 'phoenix dactylifera', 'curmal', 'fructe'),
    (310, 'diospyros virginiana', 'curmal american', 'fructe'),
    (336, 'cucurbita pepo', 'dovleac', 'legume'),
    (337, 'cucurbita maxima', 'dovleac turcesc', 'legume'),
    (338, 'berberis vulgaris', 'dracila', 'fructe'),
    (339, 'rumex scutatus', 'dragavei', 'legume'),
    (346, 'morus alba', 'dud alb', 'fructe'),
    (347, 'morus nigra', 'dud negru', 'fructe'),
    (369, 'phaseolus vulgaris', 'fasole', 'legume'),
    (374, 'foeniculum vulgare', 'fenicul', 'legume'),
    (391, 'fragaria vesca', 'frag', 'fructe'),
    (392, 'fragaria moschata', 'frag de gradina', 'fructe'),
    (414, 'gaylussacia brachycera', 'gaylussacia brachycera', 'fructe'),
    (439, 'lycium barbarum', 'goji', 'fructe'),
    (443, 'triticum aestivum', 'grau', 'cereale'),
    (444, 'citrus x paradisi', 'grepfrut', 'fructe'),
    (449, 'cyamopsis tetragonoloba', 'guar', 'legume'),
    (460, 'cydonia oblonga', 'gutui', 'fructe'),
    (466, 'anthriscus cerefolium', 'hasmatuchi', 'legume'),
    (472, 'armoracia rusticana', 'hrean', 'legume'),
    (473, 'armoracia macrocarpa', 'hrean salbaticit', 'legume'),
    (474, 'fagopyrum esculentum', 'hrisca', 'cereale'),
    (489, 'portulaca oleracea', 'iarba-grasa', 'legume'),
    (536, 'juglans major', 'juglans major', 'fructe'),
    (542, 'citrus limon', 'lamai', 'fructe'),
    (551, 'lathyrus sativus', 'latir', 'legume'),
    (562, 'allium ursinum', 'leurda', 'legume'),
    (563, 'levisticum officinale', 'leustean', 'legume'),
    (582, 'citrus aurantiifolia', 'lime', 'fructe'),
    (588, 'vicia lens', 'linte', 'legume'),
    (598, 'atriplex hortensis', 'loboda', 'legume'),
    (612, 'lupinus albus', 'lupin', 'legume'),
    (622, 'rosa canina', 'maces', 'fructe'),
    (623, 'rosa pendulina', 'maces de munte', 'fructe'),
    (624, 'rumex acetosa', 'macris', 'legume'),
    (626, 'rumex acetosella', 'macris marunt', 'legume'),
    (633, 'prunus padus', 'malin', 'fructe'),
    (634, 'citrus reticulata', 'mandarin', 'fructe'),
    (635, 'mangifera indica', 'mango', 'fructe'),
    (637, 'malus domestica', 'mar', 'fructe'),
    (638, 'malus sylvestris', 'mar paduret', 'fructe'),
    (639, 'anethum graveolens', 'marar', 'legume'),
    (645, 'olea europaea', 'maslin', 'fructe'),
    (652, 'lathyrus oleraceus', 'mazare', 'legume'),
    (654, 'panicum miliaceum', 'mei', 'cereale'),
    (657, 'vaccinium vitis-idaea', 'merisor', 'fructe'),
    (658, 'vaccinium macrocarpon', 'merisor american', 'fructe'),
    (675, 'prunus dulcis', 'migdal', 'fructe'),
    (678, 'setaria italica', 'mohor', 'cereale'),
    (682, 'daucus carota', 'morcov', 'legume'),
    (684, 'mespilus germanica', 'mosmon', 'fructe'),
    (685, 'amaranthus caudatus', 'motul curcanului', 'cereale'),
    (687, 'rubus fruticosus', 'mur', 'fructe'),
    (688, 'rubus plicatus', 'mur', 'fructe'),
    (689, 'rubus caesius', 'mur de camp', 'fructe'),
    (717, 'brassica rapa', 'nap', 'legume'),
    (721, 'nasturtium officinale', 'nasturel', 'legume'),
    (722, 'cicer arietinum', 'naut', 'legume'),
    (728, 'morinda citrifolia', 'noni', 'fructe'),
    (733, 'juglans regia', 'nuc', 'fructe'),
    (734, 'juglans cinerea', 'nuc cenusiu', 'fructe'),
    (735, 'juglans nigra', 'nuc negru', 'fructe'),
    (750, 'lathyrus tuberosus', 'oresnita', 'legume'),
    (751, 'oryza sativa', 'orez', 'cereale'),
    (752, 'hordeum vulgare', 'orz', 'cereale'),
    (756, 'avena sativa', 'ovaz', 'cereale'),
    (769, 'carica papaya', 'papaya', 'fructe'),
    (771, 'pyrus communis', 'par', 'fructe'),
    (775, 'pastinaca sativa', 'pastarnac', 'legume'),
    (778, 'solanum lycopersicum', 'patlagele rosii', 'fructe'),
    (783, 'petroselinum crispum', 'patrunjel', 'legume'),
    (801, 'cucumis melo', 'pepene galben', 'fructe'),
    (802, 'citrullus lanatus', 'pepene verde', 'fructe'),
    (820, 'prunus persica', 'piersic', 'fructe'),
    (838, 'citrus grandis', 'pomelo', 'fructe'),
    (844, 'citrus x sinensis', 'portocal', 'fructe'),
    (845, 'citrus x aurantium', 'portocal amar', 'fructe'),
    (846, 'zea mays', 'porumb', 'cereale'),
    (847, 'prunus spinosa', 'porumbar', 'fructe'),
    (848, 'allium ampeloprasum', 'praz', 'legume'),
    (850, 'prunus domestica', 'prun', 'fructe'),
    (884, 'raphanus sativus', 'ridiche', 'legume'),
    (885, 'raphanus niger', 'ridiche neagra', 'legume'),
    (889, 'punica granatum', 'rodie', 'fructe'),
    (899, 'ceratonia siliqua', 'roscov', 'fructe'),
    (907, 'rheum rhabarbarum', 'rubarba', 'legume'),
    (908, 'eruca sativa', 'rucola', 'legume'),
    (909, 'eruca vesicaria', 'rucola', 'legume'),
    (914, 'lactuca sativa', 'salata', 'legume'),
    (926, 'elaeagnus angustifolia', 'salcioara', 'fructe'),
    (966, 'cormus domestica', 'scorus', 'fructe'),
    (967, 'sorbus aucuparia', 'scorus de munte', 'fructe'),
    (973, 'secale cereale', 'secara', 'cereale'),
    (979, 'beta vulgaris', 'sfecla', 'legume'),
    (980, 'beta rubra', 'sfecla rosie', 'legume'),
    (993, 'ficus carica', 'smochin', 'fructe'),
    (994, 'sambucus nigra', 'soc', 'fructe'),
    (995, 'sambucus canadensis', 'soc american', 'fructe'),
    (998, 'glycine max', 'soia', 'legume'),
    (1006, 'torminalis glaberrima', 'sorb', 'fructe'),
    (1011, 'spinacia oleracea', 'spanac', 'legume'),
    (1014, 'asparagus officinalis', 'sparanghel', 'legume'),
    (1033, 'rumex patientia', 'stevie', 'legume'),
    (1034, 'amaranthus graecizans', 'stir african', 'legume'),
    (1036, 'amaranthus blitum', 'stir verde', 'legume'),
    (1076, 'apium graveolens', 'telina', 'legume'),
    (1078, 'lagenaria siceraria', 'tidva', 'legume'),
    (1084, 'helianthus tuberosus', 'topinambur', 'legume'),
    (1132, 'urtica dioica', 'urzica', 'legume'),
    (1133, 'urtica urens', 'urzica mica', 'legume'),
    (1136, 'allium sativum', 'usturoi', 'legume'),
    (1141, 'brassica oleracea', 'varza', 'legume'),
    (1163, 'solanum melongena', 'vinete', 'legume'),
    (1168, 'prunus cerasus', 'visin', 'fructe'),
    (1169, 'vitis vinifera', 'vita-de-vie', 'fructe'),
    (1179, 'pinus cembra', 'zambru', 'fructe'),
    (1185, 'ziziphus mauritiana', 'ziziphus mauritiana', 'fructe'),
    (1187, 'rubus idaeus', 'zmeur', 'fructe');
CREATE TEMP TABLE herb_food_additions (ro text PRIMARY KEY,en text,category text,latin text,family text) ON COMMIT DROP;
INSERT INTO herb_food_additions (ro,en,category,latin,family) VALUES
    ('seminte de floarea-soarelui', 'sunflower seeds', 'seminte', NULL, NULL),
    ('seminte de dovleac', 'pumpkin seeds', 'seminte', NULL, NULL),
    ('seminte de struguri', 'grape seeds', 'seminte', NULL, NULL),
    ('seminte de in', 'flax seeds', 'seminte', NULL, NULL),
    ('quinoa', 'quinoa', 'cereale', 'chenopodium quinoa', 'amaranthaceae');
CREATE TEMP TABLE herb_food_before ON COMMIT DROP AS SELECT * FROM herbs;
DO $guard$
BEGIN
    IF EXISTS (SELECT FROM herb_food_updates u LEFT JOIN herbs h ON h.id=u.id
        WHERE h.id IS NULL OR h.latin IS DISTINCT FROM u.latin OR h.ro IS DISTINCT FROM u.ro
        OR h.category <> 'plante medicinale') THEN
        RAISE EXCEPTION 'HERB_FOOD_IDENTITY_MISMATCH';
    END IF;
    IF EXISTS (
        SELECT FROM herb_food_additions n JOIN (
            SELECT ro AS name FROM herbs UNION ALL SELECT latin FROM herbs
            UNION ALL SELECT en FROM herbs UNION ALL SELECT name FROM herb_aliases
        ) names ON btrim(regexp_replace(lower(unaccent(names.name)), '[^a-z0-9]+', ' ', 'g'))
            IN (btrim(regexp_replace(n.ro, '[^a-z0-9]+', ' ', 'g')), n.latin, n.en)
    ) THEN RAISE EXCEPTION 'HERB_FOOD_ADDITION_ALREADY_EXISTS'; END IF;
END
$guard$;
ALTER TABLE herbs DROP CONSTRAINT herbs_category_check,
    DROP CONSTRAINT herbs_product_species_check,
    DROP CONSTRAINT herbs_ro_case_check, DROP CONSTRAINT herbs_en_case_check;
ALTER TABLE herbs ADD CONSTRAINT herbs_category_check CHECK (category IN (
    'plante medicinale', 'fructe', 'legume', 'cereale', 'seminte', 'uleiuri esentiale', 'suplimente', 'aminoacizi', 'vitamine', 'minerale', 'produse apicole', 'fibre, probiotice, prebiotice')),
    ADD CONSTRAINT herbs_product_species_check CHECK (
        (category IN ('plante medicinale','fructe','legume','cereale') AND latin IS NOT NULL AND family IS NOT NULL)
        OR (category IN ('seminte', 'uleiuri esentiale', 'suplimente', 'aminoacizi', 'vitamine', 'minerale', 'produse apicole', 'fibre, probiotice, prebiotice') AND latin IS NULL AND family IS NULL)),
    ADD CONSTRAINT herbs_ro_case_check CHECK (
        category NOT IN ('plante medicinale','fructe','legume','cereale') OR ro=lower(ro)),
    ADD CONSTRAINT herbs_en_case_check CHECK (
        category NOT IN ('plante medicinale','fructe','legume','cereale') OR en=lower(en));
DROP INDEX herbs_product_ro_unique;
CREATE UNIQUE INDEX herbs_product_ro_unique ON herbs (lower(btrim(ro)))
    WHERE category IN ('seminte', 'uleiuri esentiale', 'suplimente', 'aminoacizi', 'vitamine', 'minerale', 'produse apicole', 'fibre, probiotice, prebiotice');
UPDATE herbs h SET category=u.category FROM herb_food_updates u WHERE h.id=u.id;
INSERT INTO herbs (category,family,latin,ro,en)
    SELECT category,family,latin,ro,en FROM herb_food_additions ORDER BY ro;
-- Hyphen/space variants already normalize identically; no duplicate alias is inserted.
DO $verify$
BEGIN
    IF (SELECT count(*) FROM herbs) <> (SELECT count(*)+5 FROM herb_food_before)
        OR EXISTS (
            SELECT FROM herb_food_before b LEFT JOIN herbs h ON h.id=b.id
            LEFT JOIN herb_food_updates u ON u.id=b.id
            WHERE h.id IS NULL OR ROW(h.family,h.latin,h.ro,h.en,h.ranking,h.category)
                IS DISTINCT FROM ROW(b.family,b.latin,b.ro,b.en,b.ranking,coalesce(u.category,b.category)))
        OR (SELECT count(*) FROM herb_food_additions n JOIN herbs h
            ON h.ro=n.ro AND h.en=n.en AND h.category=n.category
            AND h.latin IS NOT DISTINCT FROM n.latin AND h.family IS NOT DISTINCT FROM n.family
            AND h.ranking=0) <> 5
    THEN RAISE EXCEPTION 'HERB_FOOD_PUBLICATION_MISMATCH'; END IF;
END
$verify$;
COMMENT ON COLUMN herbs.category IS 'One approved catalog group per entry, independent of taxonomy or therapeutic efficacy.';
COMMENT ON COLUMN herbs.family IS 'Original lowercase botanical family for the four botanical groups; SQL NULL for products.';
COMMENT ON COLUMN herbs.latin IS 'Unique lowercase species name for botanical groups; SQL NULL for products including seeds.';
COMMENT ON CONSTRAINT herbs_category_check ON herbs IS 'Twelve canonical catalog groups, without diacritics.';
COMMENT ON CONSTRAINT herbs_product_species_check ON herbs IS 'Four botanical groups require taxonomy; eight product groups require SQL NULL family and Latin name.';
COMMENT ON CONSTRAINT herbs_ro_case_check ON herbs IS 'Romanian botanical names stay lowercase in all four botanical groups.';
COMMENT ON CONSTRAINT herbs_en_case_check ON herbs IS 'English botanical names stay lowercase in all four botanical groups.';
COMMENT ON INDEX herbs_product_ro_unique IS 'One normalized product name across all eight product groups including seeds.';
