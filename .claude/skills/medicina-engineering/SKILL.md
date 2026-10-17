---
name: medicina-engineering
description: Senior-engineer role guides for this repository — Python development, Python code review, XMind 8 architecture diagrams, PostgreSQL/pgvector work, embeddings work, and Docker/GitHub Actions. Load the matching reference file before writing or reviewing code in that area.
---

# Engineering roles for medicina-naturista

Six role guides. Each encodes how *this* codebase does the work — its invariants, its
conventions, and the checks that must pass — not generic best practice. Read `CLAUDE.md`
first for the project contract, then open the one role file that matches the task.

| Task | Open |
|---|---|
| Writing or changing Python application code | [python-development.md](python-development.md) |
| Reviewing a diff, PR or branch of Python code | [python-code-review.md](python-code-review.md) |
| Creating or updating an architecture diagram | [xmind-architecture.md](xmind-architecture.md) |
| Schema, migrations, SQL, psycopg, transactions, locks | [database-engineering.md](database-engineering.md) |
| Embedding model, vectors, chunking, retrieval quality | [embeddings-engineering.md](embeddings-engineering.md) |
| Dockerfile, Compose, CI workflow, dependency locks | [devops-docker-ci.md](devops-docker-ci.md) |

Several tasks cross roles. A change to fragment windowing is embeddings **and** database
(the index must be rebuilt atomically) **and** DevOps (the CI integration job must still
pass). Read each relevant file rather than guessing from the nearest one.

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
