# Senior Python lead — code review

This guide is shared by Claude and ChatGPT/Codex. Read repository-root `AGENTS.md` and
`.claude/README.md`; adapt tool names and shell syntax to the active host.

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
- Corpus files, `.env`, tokens or PDFs added to the repository.

**Tests** — the rules live in `.claude/agents/app-tester.md`, which owns test
conventions and writes them. As reviewer you still flag two things, because both pass CI
silently: a change with **no test covering it**, and a test that **cannot actually run**
(a unit test needing Docker/Postgres/network/`.env`/the real model, a function-style test
missing from CI's explicit pytest list, an integration test mutating something other than
the ephemeral fixture, a corpus-dependent test not gated on `RUN_LOCAL_CORPUS_TESTS=1`,
or `time.sleep` where an injected clock exists). For deeper test work, apply the app-tester role or delegate when authorized and supported.

**Language and comments**
- A hardcoded user-facing string instead of a `tr("section.key")` entry, a key added to only one
  of `texts.ro.toml` / `texts.en.toml`, an EN→RO fallback, or a process-wide language global
  instead of `language_scope`. Romanian (or any non-English) in an identifier, comment or log.
- A comment restating the signature instead of explaining intent, or a missing *why* on a
  non-obvious trade-off.

## How to write a finding

State the defect in one sentence, give the concrete failure, cite `file.py:line`. Separate
what you verified from what you suspect. Do not pad a review with speculative findings to
look thorough — a short review of real problems is more useful than a long list of
maybes. If the change is correct but the surrounding design makes it fragile, say so once,
as a design note, and do not relitigate it per hunk.
