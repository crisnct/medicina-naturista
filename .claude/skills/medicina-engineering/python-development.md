# Senior Python developer — general development

Python ≥ 3.11, targeting 3.11 (`target-version = "py311"`). Write code that a reviewer
cannot distinguish from what is already in `src/backend/core/`.

## Non-negotiable directives

These override convenience, always:

1. **No placeholders.** No `TODO`, no bare `pass` as a stand-in, no `... rest of code`,
   no `# implement here`, no half-wired function left for later. A stub passes review and
   fails in production. If you cannot finish something, say so in your reply rather than
   leaving it in the tree.
2. **Production-ready or not delivered.** Code you hand over is typed, linted, tested and
   secure by default — not a sketch to be hardened later.
3. **The stack is fixed.** Work within the pinned choices below. Introducing a different
   framework, package manager, ORM or base image is a structural change needing explicit
   approval, never a side effect of another task.
4. **Scope discipline, both directions.** Fix typing, lint, formatting and comment
   violations in code you are already editing — that is coordinated cleanup. But renaming
   classes, changing business logic, altering the DB schema, moving module boundaries or
   refactoring architecture beyond the request requires approval first: list such findings
   at the end of your reply instead of applying them. "Make minimal changes" from the user
   overrides even the cleanup half.

## The pinned stack

Generic strict-mode Python guidance (3.13 + distroless, `uv`, `pydantic-settings`,
SQLAlchemy + Alembic, line-length 88, Google docstrings, 80% coverage gates) does **not**
apply to this repository. It is an existing system whose choices are load-bearing, and
`pyproject.toml` plus `.github/workflows/ci.yml` are authoritative over any external
standard.

| Concern | This project | Why it is not the generic default |
|---|---|---|
| Python / runtime image | 3.11, `python:3.11-slim-bookworm` | Hashed lock files, ONNX/fastembed wheels, and the DejaVu/Liberation fonts ReportLab needs for Romanian diacritics — distroless has no shell and no fonts |
| Configuration | frozen `Settings` dataclass + `from_env` | One validated snapshot per process; tests inject a mapping and never read `.env` |
| Dependencies | pip-tools, four committed hashed locks | `--require-hashes` installs, fingerprinted in `requirements-locks.json`, checked in CI |
| Database access | psycopg 3 + hand-written SQL + numbered SQL migrations | Atomic index publication must be one transaction under an advisory lock; see [database-engineering.md](database-engineering.md) |
| Layering | `src/backend/{core,ai,web,reporting,persistence,integrations}` | Same separation under different names: `core` = domain + services, `persistence`/`integrations` = adapters, `web` = interface |
| Lint / format | line-length 100, ruff `E4, E7, E9, F, I`, `format --check` in CI | Ruff does not rewrite in CI; format locally before pushing |
| Docstrings | one-line contract docstring + `#` why-comments | The established convention in every module here (see below) |
| Tests | `src/tests/{unit,integration}`, `unittest` first, no coverage gate | `pytest.ini_options.testpaths = ["src/tests"]`; CI has no `--cov-fail-under` |
| Output language | English throughout; targeted edits, not full-file rewrites | Repo and tooling convention |

What generic guidance gets right and this project already does: complete implementations,
strict typing, validated external input, parameterised SQL, secrets only from the
environment, structured logging with no PII, a custom exception hierarchy, non-root
containers, and tests for every new module.

## House style, as the codebase actually practises it

**`from __future__ import annotations` at the top of every module.** Then plain builtin
generics and `X | None`, never `Optional`/`Dict`/`List`.

**Module docstring: one or two lines stating the contract and its invariants.** Look at
real ones before writing a new one:

```python
"""Atomic tab lifetimes, operation commits and bounded ephemeral retention.

Every API acquires registry -> session. Callers must never acquire the registry
while holding a session lock. External I/O is forbidden inside these APIs.
"""
```

**Comments go above the definition and say *why*.** This is the single most distinctive
convention here:

```python
# Profile of a known model; an unknown name is an error, never a silent guess.
def get_profile(model_name: str) -> EmbeddingProfile:
```

Do not write `# Returns the profile` — the signature says that. If a line needs no
explanation of intent, trade-off or hazard, it needs no comment.

**Frozen dataclasses for values** (`Settings`, `ProviderConfig`, `SearchSignals`,
`ReportMetrics`, `EmbeddingProfile`). Validate in `__post_init__` and raise `ValueError`
for programmer/config errors. `MappingProxyType` for module-level mappings that must not
be mutated (see `core/report_models.py`).

**Protocols and TypedDicts over base classes.** New boundaries go in
`core/contracts.py`; `core` must stay importable without FastAPI or psycopg. Callables
that cross a boundary get a named alias (`IdentifyCondition`, `RenderPDF`,
`ClassifyMessage`) rather than an inline `Callable[...]` repeated at each site.

**Dependency injection through `web/dependencies.py::Dependencies`.** Constructing it
performs no I/O. Optional collaborators are `None`-defaulted fields, not globals.

**Line length 100.** Ruff lints `E4, E7, E9, F, I`; `ruff format --check` runs in CI and
does not rewrite. Format locally before pushing.

## Errors

Domain failures are `ApplicationError(code, romanian_message, status, retry_after=None)`
raised from `core`; the HTTP layer translates them. The `code` is part of the public API
contract — adding one means the frontend and README may need updating. Use
`OperationCancelled` for a superseded, closed or timed-out operation whose result must be
discarded.

`ValueError` is for invalid configuration and programmer error, surfaced at startup.
`RuntimeError` is for an impossible runtime state (see `INDEX_DIMENSION_CHANGE_REQUIRES_SYNC`).
Never swallow an exception to keep a flow alive unless the degradation is deliberate,
documented and visible to the user — the local-classification fallback is the model for that.

Never raise or catch bare `Exception`; catch the specific types. An `except` block that
does nothing is a defect. And user-facing messages must not leak internals — no paths,
module names, SQL, provider payloads or stack traces in the Romanian text that reaches
the browser. `ApplicationError` exists precisely so the technical detail stays in the log
and the user gets a sentence they can act on.

## Logging

`logging.getLogger("naturist.<area>")` per module — the existing names are `naturist.web`,
`naturist.ai`, `naturist.sessions`, `naturist.conversation`, `naturist.reports`,
`naturist.retrieval`, `naturist.condition_ai`, `naturist.classification`,
`naturist.herbs`. Reuse an existing name rather than inventing a parallel one.

`print()` is for operator CLIs in `src/scripts/` only (progress output is part of their
interface). It does not belong in `backend/`.

Never log fragment text, AI response text, chat content, email addresses or keys.
`LOG_FRAGMENT_TEXT` and `LOG_AI_RESPONSE_TEXT` gate the diagnostic cases and must be off
for public deployments — `Settings.__post_init__` enforces that. Secrets are `repr=False`
dataclass fields; keep them out of exception messages too.

## Typing discipline

`pyproject.toml`'s `[tool.mypy] files` is a gradually-expanding allowlist. Modules in the
`disallow_untyped_defs` / `disallow_any_generics` override
(`core.contracts`, `core.operation_context`, `ai.content_evaluation`) must stay fully
annotated. CI also runs mypy over the herb modules and the index-build scripts with
explicit per-file invocations — check `.github/workflows/ci.yml` before assuming a file is
unchecked. Prefer extending the allowlist when you touch a module heavily.

## Security baseline

- **Secrets come from the environment through `Settings`**, never hardcoded, never in a
  default, never in a build arg or image layer. `.env` is gitignored; nothing resembling
  a key, token or password is committed.
- **Validate every external input at the boundary.** Request bodies are Pydantic models
  in `web/main.py` with `Field` patterns and validators (`SignalsPayload` rejects an
  all-off selection; `messageId`/`requestId` are regex-constrained; `minScore` is
  `strict=True, ge=0, le=100`). AI responses go through `ai/report_validation.py` and
  strict JSON schemas — model output is untrusted input.
- **SQL is parameterised**, always. `%s` placeholders for values, `psycopg.sql`
  composition for identifiers. No f-string SQL anywhere.
- **Paths from outside are not trusted.** Report downloads are scoped to the tab's
  session; `public_root_path` is validated against traversal and odd characters.
- **Owner-only enforcement is server-side**, before job admission — never rely on the UI
  hiding a control.

## Async discipline

The app is sync-first: `core/` is synchronous and testable without an event loop, and
FastAPI handlers bridge to it. Blocking work called from async code goes through
`asyncio.to_thread` — that is how the retriever, search warm-up, session sweep and
report-service shutdown are invoked in `web/main.py`'s lifespan. Never call blocking I/O
directly inside an `async def`; it stalls the single worker.

Request-scoped state uses `contextvars.ContextVar`, never module-level mutables — see
`OperationBudget` and `index_reader`. Shutdown is graceful: drain workers within
`REPORT_SHUTDOWN_TIMEOUT_SECONDS`, then close.

## Concurrency and lifetime

- **Lock order is registry → session**, never the reverse, and **no external I/O under a
  lock** (`core/sessions.py`). Violating this deadlocks the single worker.
- Long work runs under `OperationBudget` (`core/operation_context.py`): call
  `remaining_timeout()` before blocking I/O and `checkpoint()` between stages. The budget
  bounds I/O and rejects late results; it **cannot** kill a thread, so capacity stays owned
  by `SessionStore` until the worker really exits.
- Report jobs go through `ReportGenerationService`'s single-worker executor with a FIFO
  queue; over-capacity requests get `429 GENERATION_QUEUE_FULL`.
- Progress/streaming is published with `emit_report_output` / `emit_report_thinking` /
  `emit_report_activity`, not by reaching into session state.

## Configuration

All environment reading happens in `Settings.from_env`. Add the field, its default, its
`_int`/`_bool` parsing, and its validation in `__post_init__` — then add the variable to
`docker-compose.yaml`'s `app.environment`, because `.env` alone does not reach the
container. Tests construct `Settings(...)` directly or pass a mapping; they never load
`.env`.

## Tests you must write

Unit tests go in `src/tests/unit/<area>/`, use `unittest.TestCase`, and must run with **no**
Docker, Postgres, `.env`, corpus or network. Deterministic clocks are injected
(`SessionStore(..., clock=lambda: self.now)`) — follow that instead of sleeping. If you add
a function-style (pytest) test, add it to the explicit pytest list in CI, because
`unittest discover` will not collect it.

Integration tests use `tests/support/postgres.py` (one ephemeral pgvector container per
module, `reset()` between tests). Anything touching the personal corpus must be gated on
`RUN_LOCAL_CORPUS_TESTS=1`.

## Before you say it works

Run ruff, ruff format --check, mypy and the unit suite. State plainly what passed, what
failed and what you did not run.
