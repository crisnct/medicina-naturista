# OpenWolf

This project uses OpenWolf for context management. The always-on rules live in `.claude/rules/openwolf.md`; the hooks handle bookkeeping (anatomy index, memory log, read tracking) automatically.

For the full operating protocol (session handoff, memory discipline, bug logging), load the `openwolf` skill, or read `.wolf/OPENWOLF.md`. Regenerate the session handoff with `/handoff`.


# CLAUDE.md

Guidance for Claude Code and ChatGPT Desktop when working in this repository.

## What this is

A Romanian-language naturopathy assistant. A private local corpus of Markdown documents is
turned into a **hybrid retrieval index** in PostgreSQL (pgvector + tsvector). A FastAPI backend
serves a React SPA: the user describes a health problem, the app classifies the message, searches
the corpus, shows the retrieved fragments for review, and only then sends the selected evidence to
a chosen LLM to draft a structured report, rendered as a PDF and optionally emailed via Gmail.

**Privacy is a design constraint, not a feature.** Documents, fragmentation, indexing, retrieval,
message classification and condition identification all run locally. Only the consultation profile
plus the fragments the user approved ever leave the machine, and only to the model picked for that
one report.

License: Business Source License 1.1 (non-production use free; production needs a commercial
agreement). Do not relicense files or add code under incompatible terms.

## Layout

```
src/backend/
  config.py            Settings (frozen dataclass) + heavy __post_init__ validation
  core/                Framework-free domain: sessions, conversation, report orchestration,
                       contracts (Protocols/TypedDicts), owner auth, rate limits, errors
  ai/                  Fragmentation, condition & herb catalogs, hybrid search, retrieval,
                       embedding model, LLM clients, provider configs, prompts/*.md
  web/                 FastAPI boundary (main.py), DI container, body limit, static serving
  reporting/           PDF (ReportLab) and chat message rendering
  integrations/        Gmail OAuth2 delivery
  persistence/         Postgres repositories (report metrics)
  migrations/          Versioned, append-only SQL (schema + condition/herb catalogs)
src/frontend/          React 19 + TypeScript + Vite + TanStack Query (Vitest)
src/scripts/           Operator CLIs: index build, migrations, audits, PDF→Markdown, locks
src/tests/             unit/ (no I/O), integration/ (ephemeral pgvector), eval/, support/
architecture/          XMind 8 diagrams (the canonical architecture docs)
```

`README.md` is the long-form spec, in Romanian, and it is kept current — read the relevant
section before changing behaviour it describes, and update it when behaviour changes.

## Running commands

Windows host, `bash` shell, local venv at `.venv`. `PYTHONPATH=src` is required for anything that
imports `backend` or `scripts`.

```bash
PYTHONPATH=src .venv/Scripts/python.exe -m unittest discover -s src/tests/unit -t src -v
```

Full CI equivalent (see `.github/workflows/ci.yml` for the authoritative list):

```bash
PYTHONPATH=src .venv/Scripts/python.exe -m ruff check src && .venv/Scripts/python.exe -m ruff format --check src && .venv/Scripts/python.exe -m mypy
```

- **Unit tests** need no Docker, Postgres, `.env`, corpus or AI. Keep it that way.
- **Integration tests** start an ephemeral `pgvector/pgvector:pg16` container via testcontainers.
  `TEST_POSTGRES_URL` may point at a **disposable** database only — fixtures rewrite its schema.
- A few older function-style tests are pytest-only; `unittest discover` does not collect them.
  CI runs `test_report_validation.py`, `test_report_integrity.py`, `test_index_integrity.py`
  under pytest explicitly. Mirror that when adding function-style tests.
- Corpus/catalog tests over personal data require `RUN_LOCAL_CORPUS_TESTS=1` and never run in CI.
- Frontend: `npm --prefix src/frontend run test | typecheck | build`.

## Conventions that matter here

**Comments and docstrings.** The codebase explains *why*, above the definition, in English, as a
`#` comment — module docstrings are one or two lines stating the module's contract and its
invariants. Match that: terse, intent-bearing, no restating of the signature.

**User-facing strings are Romanian.** Error messages returned to the browser, chat text, PDF
labels. Code identifiers, comments and logs are English. Keep the split.

**Typing.** `from __future__ import annotations` everywhere. `src/backend/core/contracts.py` holds
the Protocols/TypedDicts that keep `core` independent of FastAPI, psycopg and the frontend.
Depend on those ports, not on concrete classes. Mypy's `files` list in `pyproject.toml` is a
gradually-expanding allowlist; modules in the `disallow_untyped_defs` override must stay fully
annotated.

**Dependency injection.** `backend/web/dependencies.py::Dependencies` is the container; building it
performs no I/O. `core` never imports `web`.

**Settings.** One frozen `Settings` dataclass; `from_env` is the only place environment variables
are read, and `__post_init__` rejects invalid combinations loudly at startup (URLs without
credentials, budget hierarchies, `deployment_profile=public` requiring HTTPS + Secure cookies +
no content logging). Add new config there, with validation, and add the variable to
`docker-compose.yaml`'s `app.environment` — putting it in `.env` alone does **not** reach the
container.

**Errors.** Raise `ApplicationError(code, romanian_message, status)` from `core`; the HTTP boundary
translates it. Codes are part of the API contract (`INDEX_MAINTENANCE`, `INDEX_RESYNC_REQUIRED`,
`MODEL_FORBIDDEN`, `MODEL_NOT_CONFIGURED`, `GENERATION_QUEUE_FULL`, …).

**Line length 100.** Ruff rules `E4, E7, E9, F, I`; ruff format is checked, not applied, in CI.
`src/scripts/dictionaires` (third-party Hunspell) and `src/scripts/icd10_work` are excluded.

## Invariants you must not break

1. **Single Uvicorn worker.** Sessions, capacity limits and the report queue live in process
   memory. `max_concurrent_generations` is validated to be exactly `1`.
2. **Lock ordering in `core/sessions.py`:** acquire registry → session, never the reverse, and
   never perform external I/O while holding either.
3. **`TEXT_REPR_VERSION`** (`ai/index_constants.py`) is a shared constant, not an env var.
   Changing it makes the next index build reprocess every document and makes the running backend
   reject the old index until resynced.
4. **Index publication is atomic.** A failed build leaves the previous generation and embedding
   dimension intact. Search may answer `503` while a sync runs.
5. **Migrations are append-only.** Add `NNN_description.sql`; never edit an applied file. The web
   app does not migrate at startup — `scripts/migrate_database.py` and the index build do.
6. **Report model catalog is one source of truth:** `core/report_models.py`. The `ReportModel`
   literal, provider routing and `owner_only` flags live there; `REPORT_GENERATION_MODELS` only
   selects and orders which of them are enabled. Authorization is enforced server-side before
   job admission (403 `MODEL_FORBIDDEN`), independently of what the UI shows.
7. **No patient data in configuration, logs or metrics.** `report_generation_metrics` stores
   aggregates only. `LOG_FRAGMENT_TEXT` / `LOG_AI_RESPONSE_TEXT` must be off for public profiles.
8. **Long operations run under `OperationBudget`** (`core/operation_context.py`), which bounds
   synchronous I/O and discards late results. It cannot kill threads — capacity stays owned by
   `SessionStore` until the worker actually exits.
9. **The personal corpus is never committed** and never reaches CI. Tests use the synthetic corpus
   in `src/tests/eval/synthetic_corpus`.

## Dependencies

`pyproject.toml` is the single declaration source. Locks are pip-tools output with hashes, one
pair per environment (Windows/py311 and Linux/py311), fingerprinted in `requirements-locks.json`.
CI fails if declarations changed without regeneration. After editing dependencies:

```bash
PYTHONPATH=src .venv/Scripts/python.exe -m scripts.manage_dependencies --generate
```

Regenerate each pair on its own OS. `requirements-web.txt` and `requirements-lock.txt` are
aliases for the Windows lock.

## AI/LLM specifics

- Four report providers behind one `AIProtocol`: Ollama (local, open to all users), DeepSeek, xAI
  and Hugging Face routing (owner-only). Transport differences — JSON-mode field, `store`,
  reasoning effort, context budget — live in `ai/providers.py`, not in call sites.
- Message classification and unknown-condition identification use **only** the host Ollama model
  (`MEDICAL_CONDITION_AI_LOCAL_MODEL`, temperature 0, strict JSON schema), with no fallback to a
  cloud provider. A failure degrades gracefully to the existing flow; it never escalates.
- Model output is re-validated in `ai/report_validation.py`: recommendations citing fragments that
  do not exist are dropped, and a partially valid report is labelled as partial in chat and PDF.
  Citation checking is not clinical validation — never imply that it is.
- Prompts are Markdown files under `ai/prompts/`, loaded at runtime. Edit them there.
- Embeddings are `Qwen/Qwen3-Embedding-0.6B`, 1024 dimensions; queries always embed on CPU via
  FastEmbed/ONNX even when the index was built on GPU. No other model is understood by the code.

## Scoring

One SQL query produces one score per fragment from the signals the user enabled:
`4·P1 + 2·P2 + L + V` (condition in title › condition in text › lexical › semantic), with weights
fixed per signal combination in `ai/search.py`. Changing weights changes retrieval quality —
measure before and after with `scripts/evaluate_retrieval.py --content` against a labelled
baseline, and say plainly that synthetic rankings validate the metric mechanism, not model quality.

## Commits

You are not allowed to commit any files to git