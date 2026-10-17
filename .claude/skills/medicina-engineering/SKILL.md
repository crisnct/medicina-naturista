---
name: medicina-engineering
description: Senior-engineer role guides for this repository — Python development, Python code review, architecture diagrams, XMind 8 diagrams, draw.io diagrams, PostgreSQL/pgvector work, embeddings work, and Docker/GitHub Actions. Load the matching reference file before writing or reviewing code in that area.
---

# Engineering roles for medicina-naturista

Read `CLAUDE.md` first — it holds the project contract and the invariants. This file only
routes you to the right role guide; each one encodes how *this* codebase does the work.

| Task | Open |
|---|---|
| Writing or changing Python application code | [python-development.md](python-development.md) |
| Reviewing a diff, PR or branch of Python code | [python-code-review.md](python-code-review.md) |
| Any diagram, unless draw.io is named — **the default** | [xmind.md](xmind.md) |
| A diagram in `architecture/`: scope, content, verification | [architecture.md](architecture.md) |
| A diagram the user explicitly asked for in draw.io | [draw-io.md](draw-io.md) |
| Schema, migrations, SQL, psycopg, transactions, locks | [database-engineering.md](database-engineering.md) |
| Embedding model, vectors, chunking, retrieval quality | [embeddings-engineering.md](embeddings-engineering.md) |
| Dockerfile, Compose, CI workflow, dependency locks | [devops-docker-ci.md](devops-docker-ci.md) |

Tasks cross roles. A change to fragment windowing is embeddings **and** database (the
index must be rebuilt atomically) **and** DevOps (the CI integration job must still
pass). Open each relevant file rather than guessing from the nearest one.

## Diagrams: XMind 8 by default

**XMind 8 is the default format.** Asked for a diagram with no format named, or asked for
XMind → [xmind.md](xmind.md). If it belongs in `architecture/`, read
[architecture.md](architecture.md) with it: that file says what the six workbooks cover,
what a diagram may claim, and how claims are verified.

**Only when the user names draw.io** → [draw-io.md](draw-io.md). Never produce a
`.drawio` copy of an `architecture/*.xmind` flow; two sources of truth is worse than one
in an awkward format.

## Testing is a separate role

**The app-tester agent writes every kind of test** (`.claude/agents/app-tester.md`) and
owns the conventions, fixtures and CI collection rules. These guides say how to write
*testable* code — pure logic in `core/`, injected clocks and pools, Protocol-typed ports
— and delegate the suite itself. When a task needs tests written, extended or diagnosed,
hand it over; do not improvise a test file from a role guide.

## Hooks that will interrupt you

Two project hooks act on your tool calls (`.claude/hooks/README.md`):

- **Commits are blocked.** `git commit`, `merge`, `revert`, `cherry-pick`, `am`, `rebase`
  and `push` are refused — committing is the user's decision. Do the work in the working
  tree, then report it for review. `status`, `diff`, `log` and `add` still work. Do not
  look for a way around the block.
- **Python writes are ruff-checked.** After you write a `.py` file under `src/`, the hook
  runs `ruff format --check` and `ruff check` on it and reports a failure immediately.
  Fix it before moving on, and re-read the file afterwards — formatting may have moved
  the lines you were editing.

## Before claiming done

```bash
PYTHONPATH=src .venv/Scripts/python.exe -m ruff check src
.venv/Scripts/python.exe -m ruff format --check src
.venv/Scripts/python.exe -m mypy
PYTHONPATH=src .venv/Scripts/python.exe -m unittest discover -s src/tests/unit -t src -v
```

The CPU environment is `.venv`; GPU index builds use the separate `.venv-gpu`. That is
the minimum gate — `.github/workflows/ci.yml` is authoritative and runs more (extra
per-file mypy invocations, per-job pytest files, integration, frontend, container).
Report what actually ran and what actually failed.
