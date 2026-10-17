# DevOps engineer — Docker, Compose, GitHub Actions

## The image

Two stages. `node:22-slim` builds the React bundle (`PUBLIC_BASE_PATH` build arg mirrors
the backend's `PUBLIC_ROOT_PATH`, so a reverse-proxy sub-path is configured once for both
sides). Runtime is `python:3.11-slim-bookworm`, installing **only** the Linux runtime lock
with `--require-hashes`.

Properties that must survive any edit:

- `HF_HUB_OFFLINE=1` and `ORT_DISABLE_TELEMETRY=1` — the image never reaches a model hub.
- Non-root `appuser` (uid 10001); `/app/model_cache` and the documents mount are owned by it.
- DejaVu and Liberation fonts are installed because ReportLab needs them for Romanian
  diacritics in the PDF. CI installs them too; removing them breaks PDF tests.
- `HEALTHCHECK` hits `/healthz`; `--workers 1` is mandatory, not a default.
- torch is never installed — the GPU path lives only in the operator's `.venv-gpu`.

## Compose

`db` is `pgvector/pgvector:pg16` with `shared_buffers=512MB`, because the ~150 MB chunks
table must fit or the first search after a restart costs ~0.5 s of disk reads.

`app` runs hardened: `read_only: true`, `cap_drop: [ALL]`, `no-new-privileges`,
`pids_limit: 256`, `mem_limit: 4g`, uid 10001, `init: true`,
`stop_grace_period: 30s`, writable state only via `tmpfs /tmp`. The documents bind mount is
`read_only`. Ports bind to `127.0.0.1` only; the host app port is `8760` because
7772–7871 is Windows-reserved, while the container stays on 7860.

**Every setting must be listed explicitly in `app.environment`.** Adding a variable to
`.env` does not pass it to the container — this bites people repeatedly. New settings
land in three places: `Settings.from_env`, `docker-compose.yaml`, and the README's
configuration table.

Ollama runs on the **host**, not in Compose, reached through
`host.docker.internal:host-gateway`. The Windows server-side tuning noted in the compose
comments (`OLLAMA_FLASH_ATTENTION`, `OLLAMA_KV_CACHE_TYPE`, `OLLAMA_NUM_PARALLEL`,
`OLLAMA_CONTEXT_LENGTH`) applies to the Ollama process, not to the app container.

For public exposure (Tailscale Funnel): `DEPLOYMENT_PROFILE=public`, `PUBLIC_ORIGIN=https://…`,
`COOKIE_SECURE=true`, `LOG_FRAGMENT_TEXT=false`, `LOG_AI_RESPONSE_TEXT=false`, and
`FORWARDED_ALLOW_IPS` listing the trusted proxies. `Settings.__post_init__` enforces the
first four — a misconfigured public deployment fails to start rather than leaking.

## CI (`.github/workflows/ci.yml`)

Five jobs: `static`, `unit`, `integration`, `frontend`, `container`.

- All actions are **pinned to a commit SHA** with the version in a trailing comment. Keep
  that when bumping; never move to a floating tag.
- `permissions: contents: read` at workflow level. Do not widen without reason.
- Python installs are `--require-hashes` from `requirements-dev-py311-linux.lock`.
- `static` runs `manage_dependencies --check`, ruff, ruff format --check, then **three**
  mypy invocations — the default config plus two explicit file lists. A file can be
  type-checked in CI and not by a bare `mypy`.
- `unit` sets `HF_HUB_OFFLINE=1`, runs `pip check`, `unittest discover`, then **named
  pytest files** (`test_report_validation.py`, `test_report_integrity.py`) because
  function-style tests are not collected by unittest. Add new ones to that list or they
  never run. It also runs the synthetic content-metrics evaluation.
- `integration` uses a `pgvector/pgvector:pg16` service with a health check and
  `TEST_POSTGRES_URL`; `TESTCONTAINERS_RYUK_DISABLED=true`.
- `container` builds the image with `PUBLIC_BASE_PATH=/medicina`. Both catalogues ship as
  SQL; documents and the model cache stay operator-owned, so the build needs neither.

CI must keep running on synthetic data only. Nothing in a workflow may require the
personal corpus, a real API key, or a live model.

## Dependency locks

`pyproject.toml` declares; pip-tools generates four locks (runtime/dev × Windows/Linux)
with hashes and preserved pins. `requirements-locks.json` fingerprints the declarations
and each lock; `manage_dependencies --check` fails CI when they diverge.

```bash
PYTHONPATH=src .venv/Scripts/python.exe -m scripts.manage_dependencies --generate
```

Run it on **each** OS for that OS's pair — the script refuses anything but Python 3.11 on
Windows or Linux. `requirements-web.txt` and `requirements-lock.txt` are aliases for the
Windows runtime lock. Hashing normalises CRLF→LF, so line endings do not cause spurious
mismatches.

## Operational facts worth preserving

- One worker. Sessions, limits and the report queue are in-process; restarting drops them.
- `/healthz` = app + AI configuration (used by the Docker healthcheck); `/readyz` also
  checks index availability and compatibility, returning 503 with `Retry-After: 60`.
- Reindexing creates a missing database and applies migrations; the web app does neither.
- Backups: documents, migrations, model and configuration reconstruct the index. Owner
  authorizations live in Postgres and need their own backup.
