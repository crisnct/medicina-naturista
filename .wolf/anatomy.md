# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-10-23T10:24:28.778Z
> Files: 103 tracked | Anatomy hits: 0 | Misses: 0

> Project structure index. Auto-maintained by OpenWolf hooks and daemon.
> Run `openwolf scan` to generate, or wait for the first Claude Code session.
> Status: Pending initial scan

## ./

- `docker-compose.yaml` — Docker Compose: 4 services (~2177 tok)
- `pyproject.toml` — " = ["E402"] (~629 tok)
- `README.md` — Project documentation (~28179 tok)

## .claude/agents/

- `app-tester.md` — Environment (~3390 tok)

## .claude/hooks/

- `block-git-commit.js` — PreToolUse(Bash) guard: refuse any command that would create a commit or (~785 tok)
- `README.md` — Project documentation (~855 tok)
- `ruff-format-check.js` — PostToolUse(Write|Edit|MultiEdit) advisory: after a .py file under src/ is (~1154 tok)

## .claude/skills/medicina-engineering/

- `architecture.md` — Senior architect — architecture documentation (~2136 tok)
- `database-engineering.md` — Senior Python developer — database expert (~2050 tok)
- `devops-docker-ci.md` — DevOps engineer — Docker, Compose, GitHub Actions (~1438 tok)
- `draw-io.md` — draw.io diagrams (~920 tok)
- `embeddings-engineering.md` — Senior Python developer — embeddings specialist (~2028 tok)
- `python-code-review.md` — Senior Python lead — code review (~1076 tok)
- `python-development.md` — Senior Python developer — general development (~3198 tok)
- `SKILL.md` — Engineering roles for medicina-naturista (~971 tok)
- `xmind-architecture.md` — Senior architect — the architecture diagrams (~849 tok)
- `xmind.md` — XMind 8 — file format and editing (~1060 tok)

## .github/workflows/

- `ci.yml` — CI: Verify application (~1361 tok)

## aiPlans/

- `2026-10-21-optimizare-procesare-topuri.md` — Optimizarea procesării topurilor — implementare și validare, 22 octombrie 2026 (~2574 tok)
- `2026-10-21-topuri-recomandari-pozitive-activare.md` — Activarea clasamentului pozitiv — actualizat la 22 octombrie 2026 (~1476 tok)
- `2026-10-21-topuri-recomandari-pozitive-fara-contraindicatii.md` — Topuri bazate pe recomandări pozitive din surse (~8284 tok)
- `2026-10-22-algoritm-structural-topuri.md` — Algoritm structural pentru topuri: context, roluri si restrictii (~1324 tok)
- `2026-10-22-calibrare-prompturi-topuri.md` — Calibrarea prompturilor pentru topurile pozitive (~1495 tok)

## aiPlans/tmp/

- `build_product_condition_xmind.py` — Build a source-pinned XMind 8 description of the existing classifier. (~9794 tok)
- `positive-ranking-activate.py` — Publish a complete generation under the operator's recorded acceptance criteria. (~735 tok)
- `positive-ranking-audit-prototype.py` (~1050 tok)
- `positive-ranking-baseline.py` — take, heartbeat (~1928 tok)
- `positive-ranking-benchmark-report.py` (~1044 tok)
- `positive-ranking-calibration-check.py` (~1067 tok)
- `positive-ranking-compact-probe.py` (~258 tok)
- `positive-ranking-continuous-supervisor.py` — Resume one local ranking with a one-minute thermal restart policy and live progress. (~3776 tok)
- `positive-ranking-full-corpus.py` — Prepare an inactive full-corpus ranking under the external thermal supervisor. (~3066 tok)
- `positive-ranking-full-supervisor.ps1` — Declares Save (~1172 tok)
- `positive-ranking-independent-sample.py` — take (~1522 tok)
- `positive-ranking-independent2-gold.py` — Declares are (~3070 tok)
- `positive-ranking-independent3-gold.py` (~3372 tok)
- `positive-ranking-optimized-benchmark.py` — MemoryRepository: source_fingerprints, read_snapshot, cached, create_run + 4 more (~1640 tok)
- `positive-ranking-parallel-pilot.py` — temperature, cool, classify (~1099 tok)
- `positive-ranking-ready-audit.py` — Audit a completed generation against existing textual gold without inference or mutation. (~2281 tok)
- `positive-ranking-review-gold.py` — Declares is (~1999 tok)
- `positive-ranking-serial-report.py` (~1472 tok)
- `positive-ranking-serial-validation.py` — MemoryRepository: load, read_snapshot, cached, create_run + 5 more (~2255 tok)
- `positive-ranking-six-passages-audit.py` (~1078 tok)
- `positive-ranking-structural-inventory.py` (~1006 tok)
- `positive-ranking-template-probe.py` (~417 tok)
- `positive-ranking-workload-plan.py` — ReadOnlyRepository: load, read_snapshot, analysis_digest, cached + 1 more (~614 tok)

## aiPlans/tmp/positive-ranking-optimization/

- `positive-audit-prototype.md` — Audit semantic al unei asocieri propuse (~543 tok)
- `precision-current-state.json` (~579 tok)
- `semantic-policy-candidate.md` (~651 tok)
- `semantic-policy-restored.md` (~744 tok)
- `validation-report.md` — Validarea optimizarii topurilor - actualizare 22 octombrie 2026, seara (~4475 tok)

## aiPlans/tmp/product-condition-diagram/

- `InspectXmind.java` — InspectXmind: main (~120 tok)
- `ValidateXmind.java` — ValidateXmind: main (~430 tok)

## architecture/

- `README.md` — Project documentation (~410 tok)

## src/backend/

- `config.py` — Environment-backed settings. No patient data belongs in configuration or logs. (~9105 tok)

## src/backend/ai/

- `client.py` — Sequential whole-fragment report batches through the selected AI provider. (~8801 tok)
- `herb_association_classification.py` — Bounded local-only polarity classification; validated quotations are source provenance. (~5563 tok)
- `herb_association_rules.py` — Conservative source-polarity rules over unchanged indexed text and primary conditions. (~16063 tok)
- `herb_positive_repository.py` — Short snapshot/cache transactions and atomic publication of source-polarity generations. (~5422 tok)
- `herb_ranking.py` — Read a bounded catalog ranking with regional Romanian names. (~886 tok)
- `message_classification.py` — Small, validated intent decisions through the existing local Ollama model. (~7160 tok)

## src/backend/ai/prompts/

- `herb_association_classification_system.md` — Clasificator de dovezi produs-afectiune (~1441 tok)
- `herb_association_classification_transport.md` — Protocol JSON strict (~458 tok)
- `message_classification_system.md` — Rol (~3485 tok)

## src/backend/core/

- `conversation.py` — Conversation orchestration, independent of FastAPI and frontend modules. (~13282 tok)
- `herb_categories.py` — Catalog groups and ranking scopes, independent of taxonomy and matching names. (~1055 tok)
- `texts.py` — Validated Romanian copy; imports are inert and each process owns one immutable snapshot. (~867 tok)

## src/backend/integrations/

- `gmail.py` — Gmail API delivery for generated reports. (~2035 tok)

## src/backend/migrations/

- `018_reclassify_oils_medicines_and_beta_carotene.sql` — Reclassify three existing identities without changing names, taxonomy or rankings. (~854 tok)
- `019_reclassify_additional_oils.sql` — Move only the explicitly approved oil identities; retain names and ranking evidence. (~470 tok)
- `022_add_sunflower_and_pumpkin_oils.sql` — Add only the two requested missing oils; retain all existing catalog identities. (~444 tok)
- `023_positive_herb_rankings.sql` — Additive source-polarity generations. Historical co-occurrences retain their meaning. (~1124 tok)
- `024_merge_fibre_probiotics_into_supplements.sql` — Merge the removed group into supplements without changing identities or ranking evidence. (~628 tok)
- `025_rename_linum_usitatissimum_ro.sql` — Rename only the requested species; retain its identity, taxonomy and ranking evidence. (~112 tok)

## src/backend/reporting/

- `pdf.py` — Readable Romanian PDF report with source references next to each claim. (~14459 tok)

## src/backend/resources/

- `texts.ro.toml` — Textele aplicației. Cheile și parametrii sunt în engleză; mesajele sunt în română. (~7500 tok)

## src/backend/web/

- `main.py` — FastAPI JSON boundary. Slow stages use independent snapshots and atomic commits. (~10888 tok)
- `texts.py` — Bootstrap public copy in the original Vite HTML; assets retain normal static serving. (~558 tok)

## src/frontend/

- `App.test.tsx` — capacityMessage (~1222 tok)
- `index.html` — __APP_TITLE__ (~135 tok)
- `main.tsx` — queryClient (~220 tok)
- `setupTests.ts` — Declares __APP_TEST_TEXTS__ (~148 tok)
- `styles.css` — Styles: 91 rules, 13 vars (~8591 tok)
- `vite.config.ts` — / <reference types="vitest/config" /> (~1158 tok)

## src/frontend/api/

- `client.test.ts` — Declares lockRequest (~1287 tok)
- `client.ts` — API routes: GET (1 endpoints) (~2195 tok)

## src/frontend/components/

- `Composer.tsx` — MAX_CHAT_CHARS — renders form (~986 tok)
- `FragmentsPanel.tsx` — CONDITION_OPTIONS (~3158 tok)
- `GeneratePanel.tsx` — Display names are editable; provider routing continues to use the original IDs. (~2894 tok)

## src/frontend/lib/

- `texts.ts` — Exports tr (~582 tok)

## src/scripts/

- `build_hybrid_index.py` — Incrementally sync a traceable, local-only hybrid index for a Markdown (~16529 tok)
- `manage_texts.py` — Export public copy and regenerate key/parameter metadata, never a second editable catalog. (~783 tok)
- `positive_herb_ranking.py` — Explicit, resumable positive-ranking stages used by the existing index CLI. (~2505 tok)
- `set_gpu_clock.bat` (~827 tok)
- `setup_gpu_clock.bat` (~593 tok)

## src/tests/integration/

- `test_condition_database.py` — Reconstruct disposable databases from SQL, never from the removed JSONL. (~4307 tok)
- `test_herb_conditions.py` — Actual PostgreSQL DISTINCT, aliases and literal ILIKE matching in an isolated DB. (~5066 tok)
- `test_herb_database.py` — Rebuild and upgrade isolated PostgreSQL databases using only packaged SQL. (~5558 tok)

## src/tests/support/

- `postgres.py` — Shared ephemeral Postgres fixture for tests that exercise the hybrid (~1419 tok)

## src/tests/unit/ai/

- `test_build_hybrid_index.py` — FakeClock: make_chunk, embed, fake_embed, test_normalize_text_preserves_composed_romanian_diacritics (~14444 tok)
- `test_message_classification.py` — Strict intent contract and local Ollama wiring; no external traffic. (~5385 tok)

## src/tests/unit/core/

- `test_settings.py` — Runtime configuration isolation, positivity and budget relationships. (~1617 tok)

## src/tests/unit/web/

- `test_message_routing.py` — Intent routing, cancellation and email claims with isolated HTTP dependencies. (~7345 tok)
