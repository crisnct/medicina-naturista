---
name: medicina-engineering
description: Senior-engineer role guides for this repository — Python development, Python code review, architecture diagrams, the XMind 8 file format, draw.io diagrams, PostgreSQL/pgvector work, embeddings work, and Docker/GitHub Actions. Load the matching reference file before writing or reviewing code in that area.
---

# Engineering roles for medicina-naturista

Eight role guides. Each encodes how *this* codebase does the work — its invariants, its
conventions, and the checks that must pass — not generic best practice. Read `CLAUDE.md`
first for the project contract, then open the one role file that matches the task.

| Task | Open |
|---|---|
| Writing or changing Python application code | [python-development.md](python-development.md) |
| Reviewing a diff, PR or branch of Python code | [python-code-review.md](python-code-review.md) |
| Updating this project's architecture diagrams | [architecture.md](architecture.md) |
| Creating or editing an `.xmind` file (format, styles, rezip) | [xmind.md](xmind.md) |
| Producing a `.drawio` diagram when one is asked for | [draw-io.md](draw-io.md) |
| Schema, migrations, SQL, psycopg, transactions, locks | [database-engineering.md](database-engineering.md) |
| Embedding model, vectors, chunking, retrieval quality | [embeddings-engineering.md](embeddings-engineering.md) |
| Dockerfile, Compose, CI workflow, dependency locks | [devops-docker-ci.md](devops-docker-ci.md) |

Several tasks cross roles. A change to fragment windowing is embeddings **and** database
(the index must be rebuilt atomically) **and** DevOps (the CI integration job must still
pass). Read each relevant file rather than guessing from the nearest one.

## Which diagram format

Three guides, and they are **not** interchangeable:

- **[architecture.md](architecture.md) is the architect's guide** — which diagrams exist,
  what they must model, the format rules, and the verification convention (re-read the
  source, refresh the review date and the source file's SHA-256 in the central topic's
  notes). `architecture/` is XMind 8 only; `architecture/README.md` says so.
- **[xmind.md](xmind.md) is the XMind 8 format reference** — ZIP anatomy, `content.xml`
  structures, the named style palette, `xmind:`/`xap:` links, and the unzip/edit/rezip
  workflow with its id-stability rules. Read it with the architecture guide whenever you
  create or edit an `.xmind`, and on its own if you only need to read one.
- **[draw-io.md](draw-io.md) is for diagrams asked for outside that set** — a throwaway
  visual for a PR or an explanation, or a `.drawio` file the user explicitly requests.
  Do not use it to replace, mirror or "modernise" an `architecture/*.xmind` workbook; two
  sources of truth for the same flow is worse than one in an awkward format. If you think
  a diagram belongs in `architecture/`, it is XMind 8.

Two caveats on that skill before you follow it literally. Its *"never write markdown
tables or plain lists"* rule does not hold here — prose and tables are the normal way to
answer a question in this repo, and a diagram is warranted only when the user asks for
one or the structure genuinely needs it. And its execution handlers reference
`./dist/index.js`, `drawio-cli` and a drawio-desktop install, **none of which exist in
this checkout or on PATH**; write the `mxfile`/`mxGraphModel` XML directly and tell the
user to open it, rather than reporting a validation or PNG export you could not run.

## Strict mode, project stack

Work to production standards: complete implementations with no placeholders or `TODO`s,
strict typing, validated external input, parameterised SQL, secrets only from the
environment, structured logging with no PII, a custom exception hierarchy, and tests for
every new module.

But apply them through **this project's pinned stack**, not a generic one. Python 3.11
(not 3.13), pip-tools with hashed locks (not `uv`), psycopg with hand-written SQL (not
SQLAlchemy/Alembic), a frozen `Settings` dataclass (not `pydantic-settings`),
line-length 100, `src/backend/` layering. [python-development.md](python-development.md)
has the full table with the reason behind each choice. Migrating toward generic defaults
is a structural change requiring explicit approval — never a side effect of another task.

## Non-negotiable across every role

1. **One Uvicorn worker.** Sessions, limits and the report queue live in process memory;
   `max_concurrent_generations` is validated to be exactly `1`. Never introduce code that
   assumes multiple workers or a shared cache.
2. **No patient data in config, logs, metrics or commits.** The personal corpus never
   enters the repository or CI; tests use `src/tests/eval/synthetic_corpus`.
3. **`core/` stays framework-free.** It depends on the Protocols in `core/contracts.py`,
   never on FastAPI, psycopg or the frontend.
4. **Romanian for user-facing strings, English for code, comments and logs.**
5. **Migrations are append-only**, and the web app never migrates at startup.
6. **Comment the *why*, above the definition, as a `#` line.** One- or two-line module
   docstrings stating the contract. Never restate the signature.

## Verify before claiming done

```bash
PYTHONPATH=src .venv/Scripts/python.exe -m ruff check src
.venv/Scripts/python.exe -m ruff format --check src
.venv/Scripts/python.exe -m mypy
PYTHONPATH=src .venv/Scripts/python.exe -m unittest discover -s src/tests/unit -t src -v
```

`.github/workflows/ci.yml` is the authoritative list, including the three pytest-only test
files and the extra per-file mypy invocations that the default `mypy` run does not cover.
Report what actually ran and what actually failed.
