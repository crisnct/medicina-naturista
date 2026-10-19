# STATUS — medicina-naturista

Last updated: 2026-10-19.

## ✅ Done

- Report/recipe generation is admin-only for every model, including local Ollama. Admission/status/cancel enforce verified owner authorization; public model permissions and UI fallbacks are empty. HTTP and rendered UI probes covered all 8 models, default selection, forged credentials and revoked sessions; 18 existing owner/FIFO checks passed. No deploy/restart.

- Implemented sequential report batches with one hardcoded FIFO worker for all models. The original system prompt is unchanged. Per-model character limits default to 25,000, configured through Settings, .env and Compose.
- Whole oversized fragments are sent alone. Each batch validates only its own citations. Exact duplicates combine their evidence IDs; variants, warnings and distinct recipes remain.
- One formatted preview updates after each validated batch, with monotonic versions and retained incomplete results on failure. Raw thinking/answer diagnostics remain session-budgeted and are not shown as the report.
- The final report/PDF/metric publish once after all batches succeed. Failed, cancelled or timed-out batches never launch later requests or publish a partial PDF.
- Targeted backend checks: 85 passed / 20 subtests; all eight models verified with synthetic HTTP; real PDF rendering and memory accounting verified. React SSR, frontend build/typecheck, changed-file formatting, lint, mypy and read-only Compose validation passed.

## 🚀 Next quest

User review of the completed local changes. No deployment or service restart is authorized. Actual-provider smoke testing and browser visual verification remain unperformed; do not imply that the running container contains the changes.

## Context

- CLAUDE.md and relevant .claude guides were loaded after the user's git pull. Do not commit, restart containers/Ollama or alter test sources.
- Preserve the user's pre-existing AD staged/deleted files and untracked corpus. .env, aiPlans and temporary probes may be gitignored; they exist locally.
- Full unit suite: 454 tests, 4 old expectation failures and 1 error from an old test expecting partial validation instead of the newly requested strict stop. Vitest: 52 passed / 6 baseline failures. Four unchanged files fail repository-wide ruff formatting. Details are in the implementation plan.
- Architecture XMind workbooks were not refreshed; README and the updated plan document batching.

## References

- aiPlans/2026-10-16-generare-raport-loturi-paralele.md
- aiPlans/tmp/report-batches-probe.py
- aiPlans/tmp/report-batches-unit.log
