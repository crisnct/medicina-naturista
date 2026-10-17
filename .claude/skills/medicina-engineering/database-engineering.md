# Senior Python developer — database expert

PostgreSQL 16 with `pgvector` and `unaccent`, accessed through psycopg 3 and
`psycopg_pool`. No ORM: SQL is written out, parameterised, and lives next to the code that
owns it.

## The schema

`documents` (one row per corpus file, SHA-256 + mtime for incremental sync) and `chunks`
(one row per fragment) in `backend/ai/db.py::SCHEMA_SQL`, with migrations in
`src/backend/migrations/`. Plus `medical_conditions`, `herbs`, `herbs_benefits`,
`owner_sessions`, `report_generation_metrics`, `sync_metadata`, `schema_migrations`.

Design notes that are load-bearing:

- **`category_id` is a `GENERATED ALWAYS … STORED` column** derived from the path, on both
  tables — there is no independent value that can drift. Keep it that way; never write it.
- **`chunks.embedding vector(__DIMENSION__)`** — the width is substituted at schema
  preparation from the embedding profile, not hardcoded.
- **`chunks.text_search tsvector`, GIN-indexed** — the lexical index. GIN indexes also
  cover `primary_medical_conditions` and `secondary_medical_conditions` (both `TEXT[]`).
- **`business_category` (R1/R2/D1) stays nullable** because rows written before it existed
  have no honest default; the next sync refills them.
- **Priority is not stored.** It is decided per search in `ai/search.py`.
- There is **no ANN index** on `embedding`: the search is an exact scan whose scoring
  depends on per-search cosine statistics. Do not add ivfflat/hnsw without redoing the
  scoring analysis — see below.

## Migrations

Append-only, numbered `NNN_description.sql`, applied by `scripts/migrate_database.py`:
advisory lock → `schema_migrations` ledger → each unapplied file in sorted order, all in
one transaction. **Never edit an applied migration.** The web app does not migrate at
startup; the index build and the explicit CLI do.

Two advisory locks matter: the migration lock `7310192026` and `INDEX_LOCK = 7261040202`
from `ai/index_state.py`. Migration takes both, so it cannot interleave with an index
publication.

Write `CHECK` constraints and `COMMENT ON` for every new column — `011_report_generation_metrics.sql`
is the reference for the expected density of both.

## Runtime rules

- **No DDL at runtime.** `ensure_schema()` is explicit preparation, uses a deliberately
  *unpooled* connection (the pool registers the `vector` type on open, which fails before
  `CREATE EXTENSION vector` has run), and must complete before the pool opens.
- **Bound every statement.** The repository pattern is:

  ```python
  with self.pool().connection(timeout=1.0) as connection, connection.transaction():
      connection.execute("SELECT set_config('statement_timeout', '2000', true)")
      connection.execute("SELECT set_config('lock_timeout', '500', true)")
  ```

  New queries follow it. Short transactions; `connect_timeout=5` on direct connections.
- **Parameterise.** `psycopg.sql` composition for identifiers (see
  `scripts/bootstrap_database.py`), `%s` placeholders for values. No f-string SQL.
- **The pool is process-wide and lazy** (`get_pool()`), `min_size=1, max_size=5`, with
  `close_pool()` for tests that repoint at another database.
- Repositories are frozen dataclasses taking a `Callable[[], ConnectionPool]`, exposing a
  Protocol defined in `core/`. Keep SQL out of `core/`.

## Atomic index publication

The whole point of the design: documents, chunks, embeddings and `sync_metadata` are
published in **one transaction** under `INDEX_LOCK`. A failure leaves the previous
generation and embedding dimension intact. A dimension change is published by the
synchronizer together with its rows, never by a migration — `ensure_schema` raises
`INDEX_DIMENSION_CHANGE_REQUIRES_SYNC` if asked to do otherwise. Readers go through
`index_reader()`, which validates compatibility and raises `IndexUnavailable`
(`INDEX_MAINTENANCE` / `INDEX_RESYNC_REQUIRED`, HTTP 503) rather than serving a stale or
mismatched index.

## The scoring query

One SQL statement computes the whole ranking (`ai/search.py`): a candidate pool, exact
cosine via `-(embedding <#> %(vector)s)`, per-search `percentile_cont(0.5)` and `max`
cosine used to rescale `V` into `[0,1]`, lexical hit fraction `L`, condition flags
`P1`/`P2`, then `score` and a window function accumulating `running_chars` so the context
budget can be applied in the same pass. Signals the user switched off are not computed at
all — the query is assembled from fragments (`_COSINE_COLUMN`, `_COSINE_STATS`,
`_COSINE_JOIN`, …).

Consequences for anyone editing it: `V` is **relative to the current result set**, so
changing the candidate pool changes scores for unchanged documents; and the weights per
signal combination are deliberate, not arbitrary. Measure before and after with
`scripts/evaluate_retrieval.py --content` against a labelled baseline.

## Testing database code

`tests/support/postgres.py` starts one `pgvector/pgvector:pg16` container per **module**
(`setUpModule`/`tearDownModule`) and calls `reset()` between tests — per-test containers
are too slow. `TEST_POSTGRES_URL` may only point at a disposable database; the fixture
rewrites its schema and data. Integration tests run migrations through the real
`migrate()`, so a broken migration fails there.

Unit tests must not reach a database. If logic needs testing without one, push it into a
pure function (`estimate_duration_from_totals` is the pattern: arithmetic in `core`,
aggregation SQL in `persistence`).
