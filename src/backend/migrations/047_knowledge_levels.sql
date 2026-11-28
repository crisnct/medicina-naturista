-- PostgreSQL. Applied transactionally by scripts.migrate_database.
-- Storage of the multilevel knowledge L1-L4 derived from the index fragments (L0). Nothing writes
-- these tables yet: the extraction (scripts.build_knowledge) comes in a later stage. Provenance
-- is tied to chunks.text_sha256, never to chunk_id, so it survives reindexing.
CREATE TABLE knowledge_runs (
    run_id BIGSERIAL PRIMARY KEY,
    language TEXT NOT NULL CHECK (language IN ('ro', 'en')),
    level SMALLINT NOT NULL CHECK (level BETWEEN 1 AND 4),
    model TEXT NOT NULL CHECK (btrim(model) <> ''),
    prompt_sha256 TEXT NOT NULL CHECK (prompt_sha256 ~ '^[0-9a-f]{64}$'),
    status TEXT NOT NULL
        CHECK (status IN ('queued', 'running', 'paused', 'stopping', 'ready', 'failed')),
    is_active BOOLEAN NOT NULL DEFAULT false CHECK (NOT is_active OR status = 'ready'),
    units_total INTEGER CHECK (units_total IS NULL OR units_total >= 0),
    units_done INTEGER NOT NULL DEFAULT 0
        CHECK (units_done >= 0 AND (units_total IS NULL OR units_done <= units_total)),
    counters JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(counters) = 'object'),
    created_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_utc TIMESTAMPTZ,
    finished_utc TIMESTAMPTZ CHECK (finished_utc IS NULL OR started_utc IS NOT NULL),
    published_utc TIMESTAMPTZ CHECK (published_utc IS NULL OR status = 'ready')
);

CREATE UNIQUE INDEX knowledge_runs_active_idx ON knowledge_runs (language, level) WHERE is_active;
CREATE INDEX knowledge_runs_level_idx ON knowledge_runs (level, language, created_utc DESC);

COMMENT ON TABLE knowledge_runs IS
    'One build of one knowledge level in one language; at most one ready run per language and level is active.';
COMMENT ON COLUMN knowledge_runs.level IS
    'Knowledge level: 1 claims and questions, 2 dossiers, 3 themes, 4 creative deductions.';
COMMENT ON COLUMN knowledge_runs.model IS
    'Application model name (core/report_models.py) from KNOWLEDGE_L<level>_MODEL; local Ollama or vLLM only.';
COMMENT ON COLUMN knowledge_runs.prompt_sha256 IS
    'Hash of the prompt and output schema version the run used.';
COMMENT ON COLUMN knowledge_runs.status IS
    'queued, running, paused (yields the GPU to a report), stopping (after the current batch), ready or failed.';
COMMENT ON COLUMN knowledge_runs.is_active IS
    'The published run of its language and level; switched atomically, the previous one stays until then.';
COMMENT ON COLUMN knowledge_runs.units_total IS
    'Work units counted at the start (L1 fragments, L2 dossiers, L3 themes, L4 batches); NULL before counting.';
COMMENT ON COLUMN knowledge_runs.units_done IS
    'Work units finished so far; drives the progress and the ETA.';
COMMENT ON COLUMN knowledge_runs.counters IS
    'Aggregate counters only (rejections, cache hits, durations); no corpus text.';
COMMENT ON COLUMN knowledge_runs.started_utc IS
    'When the run first started working; NULL while queued.';
COMMENT ON COLUMN knowledge_runs.finished_utc IS
    'When the run became ready or failed.';
COMMENT ON COLUMN knowledge_runs.published_utc IS
    'When the run was last made active.';

CREATE TABLE knowledge_items (
    item_id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES knowledge_runs ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN (
        'claim', 'question', 'fact', 'dossier', 'theme', 'pattern', 'gap',
        'connection', 'hypothesis', 'research_gap', 'safety_conflict'
    )),
    subject_key TEXT CHECK (subject_key IS NULL OR subject_key ~ '^[a-z_]+:\S'),
    body TEXT NOT NULL CHECK (btrim(body) <> ''),
    attributes JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(attributes) = 'object'),
    input_sha256 TEXT NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    origin TEXT NOT NULL DEFAULT 'corpus'
        CHECK (origin IN ('corpus', 'warning') AND (origin = 'corpus' OR kind = 'safety_conflict')),
    verification_status TEXT
        CHECK (verification_status IS NULL OR (
            verification_status IN ('unverified', 'supported', 'contradicted', 'no_evidence')
            AND kind IN ('connection', 'hypothesis', 'research_gap', 'safety_conflict')
        )),
    source_count INTEGER NOT NULL CHECK (source_count >= 0),
    ancestor_count INTEGER NOT NULL CHECK (ancestor_count >= 0),
    embedding vector
);

CREATE INDEX knowledge_items_run_kind_idx ON knowledge_items (run_id, kind);
CREATE INDEX knowledge_items_run_subject_idx ON knowledge_items (run_id, subject_key)
    WHERE subject_key IS NOT NULL;
CREATE INDEX knowledge_items_run_input_idx ON knowledge_items (run_id, input_sha256);

COMMENT ON TABLE knowledge_items IS
    'One piece of derived knowledge of a run. Derived knowledge is never evidence: it always leads back to its L0 fragments.';
COMMENT ON COLUMN knowledge_items.kind IS
    'L1 claim, question, fact; L2 dossier; L3 theme, pattern, gap; L4 connection, hypothesis, research_gap, safety_conflict.';
COMMENT ON COLUMN knowledge_items.subject_key IS
    'Catalog entity the item is about, as <kind>:<catalog name> (condition:Gripa, as in report_examples); NULL when none.';
COMMENT ON COLUMN knowledge_items.body IS
    'The knowledge as text, in the run''s language.';
COMMENT ON COLUMN knowledge_items.attributes IS
    'Structured fields of the kind (an L1 claim: subject, relation, object, dose, duration, population, quote offsets).';
COMMENT ON COLUMN knowledge_items.input_sha256 IS
    'Hash of the sorted parent hashes, the prompt version and the model: the cache and incremental (Merkle) key.';
COMMENT ON COLUMN knowledge_items.origin IS
    'corpus, or warning for an L4 safety_conflict that cites an existing safety warning.';
COMMENT ON COLUMN knowledge_items.verification_status IS
    'L4 only: result of searching the claim in L0; NULL on L1-L3.';
COMMENT ON COLUMN knowledge_items.source_count IS
    'Number of L0 fragments in knowledge_item_sources; 0 means no sources left in the index (accepted).';
COMMENT ON COLUMN knowledge_items.ancestor_count IS
    'Number of intermediate items in knowledge_item_ancestors.';
COMMENT ON COLUMN knowledge_items.embedding IS
    'Embedding by the index model, in the same space as chunks.embedding; no fixed width so it follows the index model. NULL until embedded.';

CREATE TABLE knowledge_item_sources (
    item_id BIGINT NOT NULL REFERENCES knowledge_items ON DELETE CASCADE,
    language TEXT NOT NULL CHECK (language IN ('ro', 'en')),
    text_sha256 TEXT NOT NULL CHECK (text_sha256 ~ '^[0-9a-f]{64}$'),
    source_relative_path TEXT NOT NULL CHECK (btrim(source_relative_path) <> ''),
    line_start INTEGER NOT NULL CHECK (line_start >= 1),
    line_end INTEGER NOT NULL CHECK (line_end >= line_start),
    PRIMARY KEY (item_id, text_sha256, source_relative_path, line_start)
);

CREATE INDEX knowledge_item_sources_fragment_idx ON knowledge_item_sources (language, text_sha256);

COMMENT ON TABLE knowledge_item_sources IS
    'Every L0 fragment an item comes from, through all intermediate levels; never truncated.';
COMMENT ON COLUMN knowledge_item_sources.text_sha256 IS
    'Content hash of the fragment (chunks.text_sha256), stable across reindexing.';
COMMENT ON COLUMN knowledge_item_sources.source_relative_path IS
    'The fragment''s document (chunks.source_relative_path) when the item was built.';
COMMENT ON COLUMN knowledge_item_sources.line_start IS
    'First line of the fragment in the document, 1-based, as chunks.line_start.';
COMMENT ON COLUMN knowledge_item_sources.line_end IS
    'Last line of the fragment in the document, inclusive, as chunks.line_end.';

CREATE TABLE knowledge_item_ancestors (
    item_id BIGINT NOT NULL REFERENCES knowledge_items ON DELETE CASCADE,
    ancestor_item_id BIGINT NOT NULL REFERENCES knowledge_items ON DELETE CASCADE,
    ancestor_level SMALLINT NOT NULL CHECK (ancestor_level BETWEEN 1 AND 3),
    PRIMARY KEY (item_id, ancestor_item_id),
    CHECK (ancestor_item_id <> item_id)
);

CREATE INDEX knowledge_item_ancestors_ancestor_idx ON knowledge_item_ancestors (ancestor_item_id);

COMMENT ON TABLE knowledge_item_ancestors IS
    'Every intermediate item (L1-L3) an item comes from: its parents and their ancestors; never truncated.';
COMMENT ON COLUMN knowledge_item_ancestors.ancestor_level IS
    'Level of the ancestor''s run, kept here so the UI can page ancestors by level.';

CREATE TABLE knowledge_links (
    child_item_id BIGINT NOT NULL REFERENCES knowledge_items ON DELETE CASCADE,
    parent_item_id BIGINT REFERENCES knowledge_items ON DELETE CASCADE,
    parent_text_sha256 TEXT CHECK (parent_text_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (num_nonnulls(parent_item_id, parent_text_sha256) = 1),
    CHECK (parent_item_id <> child_item_id)
);

CREATE UNIQUE INDEX knowledge_links_item_parent_idx ON knowledge_links (child_item_id, parent_item_id)
    WHERE parent_item_id IS NOT NULL;
CREATE UNIQUE INDEX knowledge_links_fragment_parent_idx
    ON knowledge_links (child_item_id, parent_text_sha256)
    WHERE parent_text_sha256 IS NOT NULL;
CREATE INDEX knowledge_links_parent_idx ON knowledge_links (parent_item_id)
    WHERE parent_item_id IS NOT NULL;

COMMENT ON TABLE knowledge_links IS
    'The direct derivation step of an item: each immediate parent, an item or an L0 fragment.';
COMMENT ON COLUMN knowledge_links.parent_item_id IS
    'Immediate parent item; NULL when the parent is an L0 fragment.';
COMMENT ON COLUMN knowledge_links.parent_text_sha256 IS
    'Immediate L0 parent (chunks.text_sha256); NULL when the parent is an item.';

CREATE TABLE kg_edges (
    run_id BIGINT NOT NULL REFERENCES knowledge_runs ON DELETE CASCADE,
    src_key TEXT NOT NULL CHECK (src_key ~ '^[a-z_]+:\S'),
    relation TEXT NOT NULL CHECK (relation ~ '^[a-z_]+$'),
    dst_key TEXT NOT NULL CHECK (dst_key ~ '^[a-z_]+:\S'),
    support_count INTEGER NOT NULL CHECK (support_count >= 0),
    against_count INTEGER NOT NULL CHECK (against_count >= 0),
    fact_item_id BIGINT REFERENCES knowledge_items ON DELETE CASCADE,
    PRIMARY KEY (run_id, src_key, relation, dst_key),
    CHECK (support_count + against_count > 0)
);

CREATE INDEX kg_edges_dst_idx ON kg_edges (run_id, dst_key);

COMMENT ON TABLE kg_edges IS
    'The typed graph of an L1 run between catalog entities; neighbourhoods are read with WITH RECURSIVE.';
COMMENT ON COLUMN kg_edges.src_key IS
    'Source entity as <kind>:<catalog name>, like knowledge_items.subject_key.';
COMMENT ON COLUMN kg_edges.relation IS
    'Relation of the L1 claims (helps, treats, contraindicated, interacts, dose, preparation, caution, ...).';
COMMENT ON COLUMN kg_edges.support_count IS
    'Claims that state the relation.';
COMMENT ON COLUMN kg_edges.against_count IS
    'Claims that deny it; together with support_count > 0 the edge is a conflict.';
COMMENT ON COLUMN kg_edges.fact_item_id IS
    'The consolidated L1 fact the edge stands for, when there is one.';

CREATE TABLE knowledge_cache (
    input_sha256 TEXT NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    prompt_sha256 TEXT NOT NULL CHECK (prompt_sha256 ~ '^[0-9a-f]{64}$'),
    model TEXT NOT NULL CHECK (btrim(model) <> ''),
    output JSONB NOT NULL,
    created_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (input_sha256, prompt_sha256, model)
);

COMMENT ON TABLE knowledge_cache IS
    'Validated model output per input, prompt and model, so an unchanged input is never sent again; inputs that gave nothing are kept too.';
COMMENT ON COLUMN knowledge_cache.input_sha256 IS
    'Same key as knowledge_items.input_sha256.';
COMMENT ON COLUMN knowledge_cache.model IS
    'Application model name, as knowledge_runs.model.';
COMMENT ON COLUMN knowledge_cache.output IS
    'The validated output; an empty result is stored as well.';
