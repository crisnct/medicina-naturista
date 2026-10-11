CREATE TABLE medical_conditions (
    condition_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK (btrim(name) <> ''),
    normalized_name TEXT NOT NULL UNIQUE CHECK (btrim(normalized_name) <> ''),
    sort_order INTEGER NOT NULL UNIQUE CHECK (sort_order >= 0)
);

CREATE TABLE medical_condition_terms (
    condition_id BIGINT NOT NULL REFERENCES medical_conditions(condition_id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    term TEXT NOT NULL CHECK (btrim(term) <> ''),
    normalized_term TEXT NOT NULL CHECK (btrim(normalized_term) <> ''),
    PRIMARY KEY (condition_id, position),
    UNIQUE (condition_id, normalized_term)
);

-- Written by the migration runner after validating the ordered catalog, in
-- the same transaction as SQL data changes and the migration ledger.
CREATE TABLE medical_condition_catalog (
    singleton_id SMALLINT PRIMARY KEY CHECK (singleton_id = 1),
    revision BIGINT NOT NULL CHECK (revision > 0),
    fingerprint TEXT NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    fingerprint_version INTEGER NOT NULL CHECK (fingerprint_version > 0),
    condition_count INTEGER NOT NULL CHECK (condition_count > 0),
    term_count INTEGER NOT NULL CHECK (term_count >= condition_count),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
