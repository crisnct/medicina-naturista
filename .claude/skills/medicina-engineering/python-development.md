# Senior Python developer — general development

Python ≥ 3.11, targeting 3.11 (`target-version = "py311"`). Write code that a reviewer
cannot distinguish from what is already in `src/backend/core/`.

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

## Typing discipline

`pyproject.toml`'s `[tool.mypy] files` is a gradually-expanding allowlist. Modules in the
`disallow_untyped_defs` / `disallow_any_generics` override
(`core.contracts`, `core.operation_context`, `ai.content_evaluation`) must stay fully
annotated. CI also runs mypy over the herb modules and the index-build scripts with
explicit per-file invocations — check `.github/workflows/ci.yml` before assuming a file is
unchecked. Prefer extending the allowlist when you touch a module heavily.

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
