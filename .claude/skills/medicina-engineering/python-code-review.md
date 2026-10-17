# Senior Python lead — code review

Review for defects that would reach production, then for the project-specific invariants
below, then for clarity. Rank findings by consequence, not by how easy they are to spot.
Say "no issues found" when that is the honest answer.

## Review order

1. **Correctness** — wrong output, crash, data loss, race. Give a concrete failing
   scenario: inputs or state → observed wrong behaviour. A finding you cannot make
   concrete is a question, not a finding.
2. **Project invariants** — the checklist below. These are the failures that pass tests
   and break production.
3. **Security and privacy** — this app handles health descriptions.
4. **Reuse and simplification** — an existing helper not used, a duplicated concept.
5. **Style** — only where it obscures meaning. Ruff already enforces the mechanical part.

## Project invariant checklist

**Concurrency**
- Lock order registry → session anywhere `SessionStore` is touched; no external I/O held
  under either lock.
- No assumption of a second worker or shared process state. `max_concurrent_generations`
  must remain 1.
- Blocking I/O inside an operation uses `remaining_timeout()`; stages call `checkpoint()`.
  A new long call that ignores the budget will outlive its session.
- Late results from a cancelled or superseded operation must be discarded, not committed.

**Layering**
- `core/` importing FastAPI, psycopg, or anything in `web/` — reject.
- A new cross-boundary callable that bypasses `core/contracts.py`.
- `Dependencies` construction doing I/O.

**Configuration**
- An environment variable read outside `Settings.from_env`.
- A new setting with no `__post_init__` validation, or missing from
  `docker-compose.yaml`'s `app.environment` (adding it to `.env` alone does nothing in
  Docker).

**Index and database**
- A migration file edited rather than added. Numbered `NNN_`, forward-only.
- DDL at runtime, or schema changes outside the atomic index publication.
- `TEXT_REPR_VERSION` changed without acknowledging that every document will be
  reprocessed and the running backend will reject the old index.
- A new query without `statement_timeout` / `lock_timeout` where the repository pattern
  sets them.

**AI and reports**
- A model added anywhere other than `core/report_models.py`, or `owner_only` bypassed.
  Authorization must be enforced server-side **before** job admission, not only in the UI.
- Classification or condition identification falling back to a cloud provider — it must
  stay host-Ollama-only and degrade gracefully.
- Report output trusted without `ai/report_validation.py`; dropped citations must still
  mark the report partial.
- Any phrasing that implies citation checking is clinical validation.

**Privacy**
- Fragment text, AI response text, chat content or email addresses reaching logs,
  metrics or exception messages. `report_generation_metrics` is aggregates only.
- A test that needs the personal corpus and is not gated on `RUN_LOCAL_CORPUS_TESTS=1`.
- Corpus files, `.env`, tokens or PDFs added to the repository.

**Tests**
- A unit test that needs Docker, Postgres, network, `.env` or the real model.
- A pytest-style (function) test added without adding it to the explicit pytest list in
  `.github/workflows/ci.yml` — `unittest discover` silently skips it, so it never runs.
- Integration tests that mutate a database other than the ephemeral fixture.
- `time.sleep` where an injected clock exists.

**Language and comments**
- English string shown to the user, or Romanian in an identifier, comment or log.
- A comment restating the signature instead of explaining intent, or a missing *why* on a
  non-obvious trade-off.

## How to write a finding

State the defect in one sentence, give the concrete failure, cite `file.py:line`. Separate
what you verified from what you suspect. Do not pad a review with speculative findings to
look thorough — a short review of real problems is more useful than a long list of
maybes. If the change is correct but the surrounding design makes it fragile, say so once,
as a design note, and do not relitigate it per hunk.
