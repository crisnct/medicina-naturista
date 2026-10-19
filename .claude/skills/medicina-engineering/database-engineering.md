# Senior Python developer — database expert

This guide is shared by Claude and ChatGPT/Codex. Read repository-root `AGENTS.md` and
`.claude/README.md`; adapt tool names and shell syntax to the active host.

PostgreSQL 16 with `pgvector` and `unaccent`, accessed through psycopg 3 and
`psycopg_pool`. No ORM: SQL is written out, parameterised, and lives next to the code that
owns it.

## No ORM — on purpose

Conventional Python guidance reaches for SQLAlchemy + Alembic on any SQL project.
**This project deliberately uses neither**, and migrating the data layer toward them is a
structural change needing explicit approval, not a refactor to slip into another task.

The reasons are concrete, not stylistic:

- **Atomic index publication.** Documents, chunks, embeddings and `sync_metadata` are
  published in one transaction under an advisory lock, including a possible change to the
  `vector(N)` column width. Alembic's model is "migrations own the schema"; here the index
  synchronizer owns part of it, and the two must not race.
- **The scoring query.** Ranking is a single hand-built SQL statement with CTEs,
  `percentile_cont`, a pgvector distance operator and a window function, assembled from
  fragments according to which signals are enabled. An ORM would obscure the one query
  whose exact shape determines retrieval quality.
- **pgvector type registration.** The pool registers the `vector` adapter on connection
  open, which constrains bootstrap ordering in ways an ORM layer would hide.

What dropping the ORM does **not** excuse, and is already the practice here:
parameterised SQL only, the repository pattern in the adapter layer (`persistence/`,
`ai/*_repository.py`) with Protocols declared in `core/`, context-managed connection
lifetime, explicitly configured pooling, and migrations that run as a deliberate step —
never during a Docker build.

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
- **Connections are always context-managed** (`with pool.connection(...)`,
  `with connection.transaction()`). A connection or transaction that can escape its
  `with` block is a defect — under one worker, a leaked connection exhausts a pool of 5.
- Repositories are frozen dataclasses taking a `Callable[[], ConnectionPool]`, exposing a
  Protocol defined in `core/`. Keep SQL out of `core/`.
- **Never hold a database connection across a session lock, an AI call, or any other
  slow boundary.** The lock rule (registry → session, no external I/O under a lock)
  applies to database I/O as much as to HTTP.

## Security

Parameterise everything; no f-string SQL, ever. Use `psycopg.sql.Identifier`/`SQL`
composition when an identifier genuinely must be dynamic (`scripts/bootstrap_database.py`
is the only legitimate case so far). Credentials reach the database layer only through
`Settings.database_url` / `database_bootstrap_url`, both `repr=False` so they cannot leak
into a log line or exception repr — keep them out of error messages you write by hand,
and surface database failures to users as an `ApplicationError` code, never as the driver
message.

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

## Keeping it testable

Tests are written by the **app-tester** role (`.claude/agents/app-tester.md`), which
owns the Postgres fixture and the integration conventions. What this role owes it:

- **Keep pure logic out of SQL.** `estimate_duration_from_totals` is the pattern —
  arithmetic in `core/`, aggregation SQL in `persistence/`. Computation buried in a
  query can only be tested with a live database.
- **Repositories take an injectable pool** (`Callable[[], ConnectionPool]`) and satisfy
  a Protocol declared in `core/`, so callers can be tested against a fake.
- **`close_pool()` exists for tests** that repoint `db.settings` at another database.
  Do not add module-level state that survives it.
- **Every migration must be runnable from scratch**, in order, against an empty
  database — that is exactly what the integration fixture does.
