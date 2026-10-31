# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-10-31T01:11:43.859Z
> Files: 251 tracked | Anatomy hits: 0 | Misses: 0

> Project structure index. Auto-maintained by OpenWolf hooks and daemon.
> Run `openwolf scan` to generate, or wait for the first Claude Code session.
> Status: Pending initial scan

## ./

- `.dockerignore` (~107 tok)
- `AGENTS.md` — AGENTS.md (~3128 tok)
- `CLAUDE.md` — Claude Code entry point (~384 tok)
- `docker-compose.yaml` — Docker Compose: 4 services (~2378 tok)
- `pyproject.toml` — " = ["E402"] (~629 tok)
- `README.md` — Project documentation (~39463 tok)

## .claude/

- `README.md` — Project documentation (~1335 tok)

## .claude/agents/

- `app-tester.md` — Environment (~3712 tok)

## .claude/hooks/

- `block-git-commit.js` — PreToolUse(Bash) guard: refuse any command that would create a commit or (~785 tok)
- `README.md` — Project documentation (~855 tok)
- `ruff-format-check.js` — PostToolUse(Write|Edit|MultiEdit) advisory: after a .py file under src/ is (~1154 tok)

## .claude/skills/medicina-engineering/

- `architecture.md` — Senior architect — architecture documentation (~2215 tok)
- `database-engineering.md` — Senior Python developer — database expert (~2050 tok)
- `devops-docker-ci.md` — DevOps engineer — Docker, Compose, GitHub Actions (~1438 tok)
- `draw-io.md` — draw.io diagrams (~920 tok)
- `embeddings-engineering.md` — Senior Python developer — embeddings specialist (~2110 tok)
- `python-code-review.md` — Senior Python lead — code review (~1190 tok)
- `python-development.md` — Senior Python developer — general development (~3387 tok)
- `SKILL.md` — Engineering roles for medicina-naturista (~971 tok)
- `xmind-architecture.md` — Senior architect — the architecture diagrams (~849 tok)
- `xmind.md` — XMind 8 — file format and editing (~1060 tok)

## .github/workflows/

- `ci.yml` — CI: Verify application (~1516 tok)

## aiPlans/

- `2026-10-21-optimizare-procesare-topuri.md` — Optimizarea procesării topurilor — implementare și validare, 22 octombrie 2026 (~2574 tok)
- `2026-10-21-topuri-recomandari-pozitive-activare.md` — Activarea clasamentului pozitiv — actualizat la 22 octombrie 2026 (~1476 tok)
- `2026-10-21-topuri-recomandari-pozitive-fara-contraindicatii.md` — Topuri bazate pe recomandări pozitive din surse (~8284 tok)
- `2026-10-22-algoritm-structural-topuri.md` — Algoritm structural pentru topuri: context, roluri si restrictii (~1324 tok)
- `2026-10-22-calibrare-prompturi-topuri.md` — Calibrarea prompturilor pentru topurile pozitive (~1495 tok)
- `2026-10-25-clean-documents-stable.md` — Stable document cleaning (~527 tok)
- `2026-10-26-atentionari-si-interactiuni-produse-naturiste.md` — Plan: atenționări și interacțiuni pentru toate produsele naturiste (~21296 tok)
- `2026-10-26-plante-afectiuni-utile-si-interzise.md` — Plan: afecțiuni în care o plantă este utilă sau interzisă (~8307 tok)
- `2026-10-26-top-produse-naturiste-pentru-afectiune.md` — Plan: top produse naturiste pentru o afectiune (~4761 tok)
- `2026-10-27-afisare-imagini-produse-in-chat.md` — Afișarea imaginilor produselor în chat (~2023 tok)
- `2026-10-27-imagini-produse-naturiste.md` — Imagini pentru produsele din herbs (~1032 tok)
- `2026-10-28-detalii-ai-in-timpul-generarii.md` — Detalii AI în timpul generării (~398 tok)
- `2026-10-28-diagnostic-ollama-si-validare-raport.md` — Diagnostic Ollama și validare raport (~1008 tok)
- `2026-10-28-previzualizare-separata-pe-lot.md` — Previzualizare separată pentru fiecare lot (~681 tok)
- `2026-10-29-doua-loturi-paralele.md` — Două loturi simultane în același raport (~939 tok)
- `2026-10-29-eliminare-estimare-fixa.md` — Eliminarea estimării fixe per 44.500 caractere (~340 tok)
- `2026-10-29-gemma3-provider-error.md` — Gemma3 1B: eroare in fluxul Ollama (~1317 tok)
- `2026-10-29-loturi-raport-buget-tokeni.md` — Loturi de raport cu buget in tokeni (~1938 tok)
- `2026-10-29-nutritie-campuri-fara-continut.md` — Nutritie: marcaje text fara continut (~577 tok)
- `2026-10-29-rapoarte-ai-engleza-traducere-locala-romana.md` — Generarea raportului în engleză, cu traducere locală și afișare în română (~5806 tok)
- `2026-10-29-report-batch-workers-env.md` — Configurare REPORT_BATCH_WORKERS (~348 tok)
- `2026-10-29-suport-romana-engleza.md` — Plan: aplicație în română și engleză (~8477 tok)
- `2026-10-30-clean-documents-english.md` — English document cleanup (~224 tok)
- `plan-effort-generare-raport.md` — Plan: selector de effort AI la generarea raportului (~3459 tok)

## aiPlans/tmp/

- `benchmark-condition-synonyms.py` — Exercise the real ranking pipeline on the frozen sample with an in-memory repository. (~3676 tok)
- `benchmark-frozen-concurrency.py` — Compare bounded concurrent local classification on a frozen herb sample. (~6659 tok)
- `benchmark-full-fragment-pipeline.py` — Exercise the real ranking pipeline on the frozen sample with an in-memory repository. (~2907 tok)
- `benchmark-herb-associations.py` — Measure one herb's complete published condition set without production writes. (~5365 tok)
- `benchmark-local-condition-scope.py` — Exercise the real ranking pipeline on the frozen sample with an in-memory repository. (~4009 tok)
- `bilingual_final_probe.py` — Manual synthetic acceptance checks; no AI, active database or corpus access. (~2681 tok)
- `build_product_condition_xmind.py` — Build a source-pinned XMind 8 description of the existing classifier. (~9794 tok)
- `caution-preview.mjs` — Declares workspace (~1435 tok)
- `compare-ranking-context.py` — Read-only, uncached paired local-Ollama context experiment over a bounded sample. (~5004 tok)
- `herb_images_batch.py` — Prepare read-only catalog queues and atomically save resumable image outputs. (~2388 tok)
- `investigate-ollama-classification.py` — Bounded read-only ablations of three classifier failures; no production edits or cache writes. (~2582 tok)
- `parallel-report-probe.py` — Manual, synthetic concurrency probe; no model, database or application service is contacted. (~3767 tok)
- `positive-ranking-activate.py` — Publish a complete generation under the operator's recorded acceptance criteria. (~735 tok)
- `positive-ranking-audit-prototype.py` (~1050 tok)
- `positive-ranking-baseline.py` — take, heartbeat (~1928 tok)
- `positive-ranking-benchmark-report.py` (~1044 tok)
- `positive-ranking-calibration-check.py` (~1067 tok)
- `positive-ranking-compact-probe.py` (~258 tok)
- `positive-ranking-continuous-supervisor.py` — Run one local ranking with minute progress updates and no thermal monitoring. (~2668 tok)
- `positive-ranking-full-corpus.py` — Prepare an inactive full-corpus ranking with operator progress and no thermal monitoring. (~2712 tok)
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
- `probe-whole-fragment-v8.py` — Compare two frozen-sample requests with reconstructed production batches; read-only DB. (~4088 tok)
- `report-condition-synonyms.py` — Compare the synonym-payload calibration against the previous frozen-sample run. (~2419 tok)
- `report-ranking-context.py` — Summarize the bounded context comparison without changing application state. (~3079 tok)
- `report-scoped-positive-priority.py` — Report calibration of local disease scope and three-label positive-priority inference. (~2176 tok)
- `summarize-simple-prompts.py` — Compare fixed-sample model results before and after prompt simplification. (~3248 tok)

## aiPlans/tmp/2026-10-27-sunatoare-qwen/

- `rezultat.md` — Test real Qwen: sunătoare — Hypericum perforatum (~901 tok)
- `test_qwen_sunatoare.py` — Opt-in live Qwen probe using production safety code; database access is read-only. (~1938 tok)

## aiPlans/tmp/association-optimization-20261025/

- `make-report.py` — Audit saved local calibration runs and report the unchanged reference labels. (~3936 tok)

## aiPlans/tmp/condition-top-20261026/

- `preview_server.py` — Loopback-only preview of the real Composer, with synthetic submission feedback. (~522 tok)
- `preview.cjs` — path: Preview (~357 tok)
- `verify.py` — Disposable manual probes; synthetic data only, outside the maintained test suite. (~2673 tok)

## aiPlans/tmp/gemma3-vs-qwen1-20261025/

- `README.md` — Project documentation (~719 tok)
- `write-report.py` — Audit completed frozen-sample experiments and write a reproducible comparison. (~3996 tok)

## aiPlans/tmp/herb-evidence-20261024/

- `preview.py` — Isolated synthetic UI preview; no corpus, database or provider access. (~789 tok)

## aiPlans/tmp/herb-safety-preview/

- `bundle.cjs` — Declares path (~135 tok)
- `preview.tsx` — groupId (~740 tok)

## aiPlans/tmp/herb-safety-preview/public/

- `mobile.html` — Previzualizare la 390 px (~76 tok)

## aiPlans/tmp/herb-ui-20261027/

- `capture.mjs` — Declares capture (~518 tok)
- `preview.mjs` — API routes: GET (1 endpoints) (~2797 tok)

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

## medicina-naturista-documente/data/documents/en/Partial Safe/Cristians Reports/

- `Natural treatment for influenza.docx.md` — Natural treatments for INFLUENZA (~1675 tok)

## src/backend/

- `config.py` — Environment-backed settings. No patient data belongs in configuration or logs. (~9709 tok)

## src/backend/ai/

- `client.py` — Sequential whole-fragment report batches through the selected AI provider. (~13438 tok)
- `condition_ai.py` — Identification of the condition a message names when the dictionary does not (~3319 tok)
- `conditions.py` — Medical-condition matching over an ordered PostgreSQL catalog snapshot. (~3911 tok)
- `effort.py` — Map the user-selected report effort to each provider's own reasoning parameter. (~264 tok)
- `english_inflections.py` — Catalog-scoped British English noun forms from the bundled Hunspell dictionary. (~970 tok)
- `herb_association_classification.py` — Bounded local-only polarity classification; validated quotations are source provenance. (~6314 tok)
- `herb_association_rules.py` — Conservative source-polarity rules over unchanged indexed text and primary conditions. (~15744 tok)
- `herb_association_scope.py` — Verify local disease identities and source boundaries without fuzzy equivalence. (~2170 tok)
- `herb_caution_projection.py` — Project warnings locally from existing rules and validated model responses; never infer. (~2968 tok)
- `herb_caution_repository.py` — Persist local warning projections and publish compatible positive/caution generations atomically. (~4798 tok)
- `herb_conditions.py` — Read a product's positive conditions from the same published generation as its ranking. (~1771 tok)
- `herb_display.py` — Restore unambiguous product spellings using the operation's bundled dictionary. (~528 tok)
- `herb_evidence.py` — Read complete source fragments from one published positive-association generation. (~2546 tok)
- `herb_images.py` — Resolve catalog product images locally without exposing the source directory. (~710 tok)
- `herb_positive_repository.py` — Short snapshot/cache transactions and atomic publication of source-polarity generations. (~6619 tok)
- `herb_product_safety_repository.py` — Cache per-product knowledge and publish complete catalog generations atomically. (~3784 tok)
- `herb_product_safety.py` — Strict, concise product safety from local model knowledge, independent of the corpus. (~1399 tok)
- `herb_ranking.py` — Read a bounded ranking from one language's published catalog generation. (~1942 tok)
- `herb_repository.py` — Coherent PostgreSQL herb snapshots, cached by database and full content. (~1874 tok)
- `herb_safety_extraction.py` — Inventory product safety independently of disease scope, preserving original source offsets. (~3634 tok)
- `herb_safety_repository.py` — Persist safety generations and validated caches without performing any model or network I/O. (~5302 tok)
- `herb_safety_validation.py` — Validate extractive safety responses; missing coverage never means absence of warnings. (~5366 tok)
- `herb_safety.py` — Read published model-knowledge messages; consultation never invokes a model. (~1384 tok)
- `herbs.py` — PostgreSQL plants/products and the strict parser for offline botanical sources. (~3360 tok)
- `message_classification.py` — Small, validated intent decisions through the existing local Ollama model. (~9335 tok)
- `providers.py` — Per-provider transport settings for report generation. (~1749 tok)
- `report_validation.py` — Validate the report contract against the exact evidence snapshot. (~1940 tok)
- `retrieval.py` — Local-only retrieval over the existing hybrid index. (~2789 tok)

## src/backend/ai/prompts/

- `herb_association_classification_system.md` — Clasificarea afirmatiilor despre produs (~572 tok)
- `herb_association_classification_transport.md` — Raspuns JSON (~189 tok)
- `herb_association_with_warnings_transport.md` — Clasificare si atentionari in acelasi raspuns (~289 tok)
- `herb_product_safety_system.md` — Siguranta unui singur produs naturist (~717 tok)
- `herb_safety_system.md` — Atentionari si interactiuni sustinute de sursa (~1506 tok)
- `herb_safety_transport.md` — Raspuns exclusiv pentru atentionari (~170 tok)
- `message_classification_system.md` — Rol (~3940 tok)

## src/backend/ai/prompts/en/

- `condition_identification_system.md` — Identify conditions in one user message (~606 tok)
- `generate_report_system.md` — Role (~1492 tok)
- `herb_association_classification_system.md` — Classify source statements about a product (~498 tok)
- `herb_association_classification_transport.md` — Complete-fragment classification output (~213 tok)
- `herb_association_with_warnings_transport.md` — Combined classification and warnings (~245 tok)
- `herb_product_safety_system.md` — Safety of one natural product (~624 tok)
- `herb_safety_system.md` — Source-supported warnings and interactions (~923 tok)
- `herb_safety_transport.md` — Warnings-only output (~149 tok)
- `message_classification_system.md` — Deterministic message intent classification (~1045 tok)

## src/backend/core/

- `contracts.py` — Shared data and port contracts; independent of HTTP and the UI. (~2229 tok)
- `conversation.py` — Conversation orchestration, independent of FastAPI and frontend modules. (~15493 tok)
- `herb_agreement.py` — Romanian product-name agreement, using local noun paradigms and explicit display rules. (~1309 tok)
- `herb_categories.py` — Catalog groups and ranking scopes, independent of taxonomy and matching names. (~992 tok)
- `language.py` — Validated languages and isolated execution scopes; no process-wide mutable locale. (~353 tok)
- `models.py` — Minimal medical context collected before report generation. (~5780 tok)
- `operation_context.py` — Propagate a worker's deadline to synchronous I/O without changing public ports. (~1379 tok)
- `report_batches.py` — Whole-fragment batches and lossless exact deduplication for one report worker. (~825 tok)
- `report_generation.py` — Process-owned execution; session admission bounds the executor's pending work. (~2574 tok)
- `report_models.py` — Supported report choices and their immutable provider routing. (~1316 tok)
- `sessions.py` — Atomic tab lifetimes, operation commits and bounded ephemeral retention. (~16106 tok)
- `text_contract.py` — Generated key/parameter contract. Regenerate with scripts.manage_texts --generate. (~6206 tok)
- `texts.py` — Validated bilingual copy with immutable catalogs selected by execution context. (~1002 tok)

## src/backend/integrations/

- `gmail.py` — Gmail API delivery for generated reports. (~2035 tok)

## src/backend/migrations/

- `018_reclassify_oils_medicines_and_beta_carotene.sql` — Reclassify three existing identities without changing names, taxonomy or rankings. (~854 tok)
- `019_reclassify_additional_oils.sql` — Move only the explicitly approved oil identities; retain names and ranking evidence. (~470 tok)
- `022_add_sunflower_and_pumpkin_oils.sql` — Add only the two requested missing oils; retain all existing catalog identities. (~444 tok)
- `023_positive_herb_rankings.sql` — Additive source-polarity generations. Historical co-occurrences retain their meaning. (~1124 tok)
- `024_merge_fibre_probiotics_into_supplements.sql` — Merge the removed group into supplements without changing identities or ranking evidence. (~628 tok)
- `025_rename_linum_usitatissimum_ro.sql` — Rename only the requested species; retain its identity, taxonomy and ranking evidence. (~112 tok)
- `026_remove_medicines_and_merge_bee_products.sql` — Remove the approved medicine identity; preserve all remaining catalog evidence. (~741 tok)
- `027_essential_oil_source_aliases.sql` — Match mixed Romanian/English oil names without guessing botanical variants or chemotypes. (~279 tok)
- `028_herb_caution_rankings.sql` — Warning projections consume existing decisions; they never schedule inference. (~2496 tok)
- `029_herb_safety_warnings.sql` — Product safety is independent of disease classifications and never mutates their decisions. (~2290 tok)
- `030_herb_safety_concise_messages.sql` — Keep full historical quotations while separating the displayed message from its evidence. (~405 tok)
- `031_herb_product_safety_knowledge.sql` — Model-knowledge safety is versioned independently of corpus-derived evidence and rankings. (~1516 tok)
- `032_bilingual_chunks.sql` — Existing data is Romanian. New importers always supply the root's explicit language. (~480 tok)
- `034_bilingual_derived_generations.sql` — Each language owns its publication pointer; existing generations remain Romanian. (~276 tok)

## src/backend/persistence/

- `report_metrics.py` — Short, bounded transactions for published report measurements. (~743 tok)

## src/backend/reporting/

- `pdf.py` — Readable Romanian PDF report with source references next to each claim. (~15036 tok)
- `recommendations.py` — Pure label extraction and PDF-only ordering of recommendation copies. (~820 tok)
- `service.py` — Prepare database-derived PDF scores before entering the pure renderer. (~762 tok)

## src/backend/resources/

- `texts.en.toml` — English application copy. Keys and named parameters match texts.ro.toml exactly. (~8599 tok)
- `texts.ro.toml` — Textele aplicației. Cheile și parametrii sunt în engleză; mesajele sunt în română. (~9433 tok)

## src/backend/web/

- `dependencies.py` — Injectable boundaries; constructing these objects performs no infrastructure I/O. (~482 tok)
- `main.py` — FastAPI JSON boundary. Slow stages use independent snapshots and atomic commits. (~13958 tok)
- `texts.py` — Bootstrap public copy in the original Vite HTML; assets retain normal static serving. (~558 tok)

## src/frontend/

- `App.test.tsx` — capacityMessage (~1225 tok)
- `App.tsx` — App (~1776 tok)
- `index.html` — __APP_TITLE__ (~135 tok)
- `main.tsx` — queryClient (~220 tok)
- `setupTests.ts` — Declares __APP_TEST_TEXTS__ (~148 tok)
- `styles.css` — Styles: 91 rules, 14 vars (~10558 tok)
- `vite.config.ts` — / <reference types="vitest/config" /> (~1158 tok)

## src/frontend/api/

- `client.test.ts` — Declares lockRequest (~1287 tok)
- `client.ts` — API routes: GET (1 endpoints) (~2630 tok)
- `types.ts` — Mirrors the JSON shapes produced by backend/web/main.py and (~2522 tok)

## src/frontend/components/

- `ChatHistory.tsx` — ChatHistory (~905 tok)
- `Composer.tsx` — MAX_CHAT_CHARS — renders form (~1017 tok)
- `FragmentsPanel.tsx` — CONDITION_OPTIONS (~3158 tok)
- `GeneratePanel.test.tsx` — message (~851 tok)
- `GeneratePanel.tsx` — Display names are editable; provider routing continues to use the original IDs. (~3390 tok)
- `GenerationDurationEstimate.tsx` — GenerationDurationEstimate (~718 tok)
- `GenerationReportPreview.tsx` — BatchPreview (~1545 tok)
- `GenerationStreamPreview.tsx` — GenerationStreamPreview (~456 tok)
- `HerbConditionsPanel.test.tsx` — message (~2834 tok)
- `HerbConditionsPanel.tsx` — Remount for each product so an earlier image's load/error cannot alter its successor. (~2094 tok)
- `HerbEvidencePanel.tsx` — Python offsets count Unicode code points; ordinary JS slice counts UTF-16 units. (~1730 tok)
- `HerbImageViewer.tsx` — Native modal dialogs keep keyboard focus inside and make the page beneath inert. (~432 tok)
- `HerbWarningsPanel.tsx` — groups (~1027 tok)
- `Hero.tsx` — Hero (~505 tok)
- `MessageBubble.tsx` — MessageBubble (~766 tok)

## src/frontend/hooks/

- `useCategories.ts` — Exports useCategories (~388 tok)
- `useConversation.ts` — Exports useConversation (~2366 tok)
- `useReportGeneration.ts` — Exports activeGeneration, useReportGeneration (~3447 tok)
- `useStartup.ts` — Exports useStartup (~248 tok)

## src/frontend/lib/

- `generationFeedback.ts` — Exports AI_ACTIVITY_LABELS, GenerationFeedback (~291 tok)
- `texts.ts` — Exports Language, getLanguage, locale, useLanguage + 3 more (~1135 tok)

## src/scripts/

- `build_hybrid_index.py` — Incrementally sync a traceable, local-only hybrid index for a Markdown (~19158 tok)
- `caution_herb_ranking.py` — Prepare and publish warning projections using indexed data and caches only, without AI. (~284 tok)
- `clean_documents.py` — Rewrite Markdown source files in place so that the fragments sent to the AI (~20372 tok)
- `herb_index_requests.py` — Stream one indexing request per batch and emit aggregate telemetry without source content. (~4390 tok)
- `herb_product_safety_index.py` — One local-model request per uncached catalog product; no corpus or association inference. (~3190 tok)
- `herb_safety_index.py` — Legacy corpus helpers and shared progress; public safety commands use product knowledge. (~6224 tok)
- `manage_texts.py` — Export public copy and regenerate key/parameter metadata, never a second editable catalog. (~783 tok)
- `positive_herb_ranking.py` — Explicit, resumable positive-ranking stages used by the existing index CLI. (~4477 tok)
- `set_gpu_clock.bat` (~827 tok)
- `setup_gpu_clock.bat` (~593 tok)

## src/tests/integration/

- `test_condition_database.py` — Reconstruct disposable databases from SQL, never from the removed JSONL. (~4307 tok)
- `test_herb_conditions.py` — Actual PostgreSQL DISTINCT, aliases and literal ILIKE matching in an isolated DB. (~10090 tok)
- `test_herb_database.py` — Rebuild and upgrade isolated PostgreSQL databases using only packaged SQL. (~6443 tok)
- `test_herbs_index.py` — Atomic derived associations on an isolated PostgreSQL fixture. (~8606 tok)
- `test_index_integrity.py` — Failure injection and actual PostgreSQL advisory-lock semantics. (~3935 tok)
- `test_report_metrics_database.py` — Real metrics transactions against disposable PostgreSQL only. (~1939 tok)

## src/tests/support/

- `postgres.py` — Shared ephemeral Postgres fixture for tests that exercise the hybrid (~1429 tok)

## src/tests/unit/ai/

- `test_build_hybrid_index.py` — FakeClock: make_chunk, embed, fake_embed, test_normalize_text_preserves_composed_romanian_diacritics (~25796 tok)
- `test_client_providers.py` — Tests for the configurable AI provider (REPORT_GENERATION_MODEL_TYPE): selection, payloads, parsing, (~5514 tok)
- `test_condition_ai.py` — Tests for the AI identification of a condition the dictionary does not know (~5725 tok)
- `test_document_spelling.py` — DocumentSpellingTests: setUp, write, clean, rows + 12 more (~4435 tok)
- `test_herb_inflections.py` — Regression examples for Romanian plant names across lookup and routing. (~2003 tok)
- `test_herb_ranking.py` — test_display_preserves_names_and_restores_known_accents, test_bundled_dictionary_restores_inflected_ (~890 tok)
- `test_message_classification.py` — Strict intent contract and local Ollama wiring; no external traffic. (~5471 tok)
- `test_report_validation.py` — report, test_invalid_recommendation_is_removed_whole, test_missing_invalid_and_extra_sections, test_ (~1323 tok)

## src/tests/unit/core/

- `test_settings.py` — Runtime configuration isolation, positivity and budget relationships. (~2055 tok)

## src/tests/unit/web/

- `test_message_routing.py` — Intent routing, cancellation and email claims with isolated HTTP dependencies. (~9203 tok)
- `test_report_metrics.py` — HTTP model binding, strict score validation and receipt idempotency. (~1677 tok)
- `test_sessions_owner.py` — HTTP races, owner revocation and streaming limits, using synthetic dependencies. (~10099 tok)
- `test_web.py` — Smoke tests for the local web application; no live xAI requests. (~29565 tok)
