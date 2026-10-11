CREATE TABLE herbs (
    id BIGINT GENERATED ALWAYS AS IDENTITY (START WITH 1 INCREMENT BY 1) PRIMARY KEY CHECK (id > 0),
    family TEXT NOT NULL CHECK (btrim(family) <> '') CHECK (family = lower(family)),
    latin TEXT NOT NULL UNIQUE CHECK (btrim(latin) <> '') CHECK (latin = lower(latin)),
    ro TEXT NOT NULL CHECK (btrim(ro) <> '') CHECK (ro = lower(ro)),
    en TEXT NOT NULL DEFAULT '' CHECK (en = lower(en))
);
CREATE TABLE herb_aliases (
    id BIGINT GENERATED ALWAYS AS IDENTITY (START WITH 1 INCREMENT BY 1) PRIMARY KEY CHECK (id > 0),
    herb_id BIGINT NOT NULL REFERENCES herbs(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (btrim(name) <> '') CHECK (name = lower(name)),
    kind TEXT NOT NULL CHECK (kind IN ('ro_regional', 'latin_synonyms', 'en_alt')),
    UNIQUE (herb_id, kind, name)
);
CREATE INDEX herb_aliases_herb_id_id ON herb_aliases (herb_id, id);
