<div align="center">

# 🌿 Adjuvant Natural Remedies - from Dr. Cuișor

### AI naturopathy assistant based on local sources

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![Hybrid retrieval](https://img.shields.io/badge/Retrieval-pgvector%20%2B%20tsvector-6A5ACD)](#-how-it-works)
[![License](https://img.shields.io/badge/License-Business%20Source%201.1-D22128)](LICENSE)

🟢 **local sources** · 🔵 **semantic search** · 🟠 **lexical search** · 🟣 **PDF report**

</div>

> [!IMPORTANT]
> The application provides guidance and adjuvant recommendations. It does not replace diagnosis, consultation, prescribed treatment or emergency medical care.
> Conversations and reports are kept temporarily in process memory. The description of the problem and the selected fragments may be sent to the configured AI provider; identifying the condition may separately use an external service. Do not enter names, personal numeric IDs, addresses or other identifying data in the chat.

## ✨ About the project

The project turns a local collection of Markdown documents about naturopathy and complementary therapies into a queryable hybrid index. The web interface receives the problem described by the user and displays the relevant fragments found in the local archive. After the fragments are reviewed, the administrator authorized through `/owner` chooses the model for each report, including local Ollama models. The application sends the evidence to the chosen provider to write the structured answer and generates a PDF report with references to the sources. Generation is reserved for the administrator for all models.

| 🧩 Component | Role |
|---|---|
| **Semantic index** | Identifies fragments with a close meaning using 1024-dimension Qwen3-Embedding vectors, stored in Postgres (`pgvector`). |
| **Lexical index** | Finds expressions with the terms in the same order, through `tsvector` in Postgres; uses prefixes for inflections and synonyms when the whole expression is a recognized condition. |
| **Combined score** | Each fragment receives a single score, from the signals that the patient ticks in “Sources and search options” (conditions, lexical, semantic). With all three: `4·P1 + 2·P2 + L + V` (condition in title › condition in text › lexical match › semantic match), computed in a single SQL query. |
| **Condition-based fragmentation** | Splits documents into R1 fragments (condition in the chapter title), R2 (condition in the chapter text) and D1 (the rest of the text), using the catalog of conditions and synonyms in PostgreSQL. |
| **Source filtering** | In the same “Sources and search options” panel, the search can be restricted to certain folders under `medicina-naturista-documente/data/documents/` (a document's category is its folder). |
| **Medical retriever** | Orders the fragments by the combined score and keeps whole those that fit within the AI provider's context budget. In “Generation options”, “Minimum score” (relevance percentage) limits the fragments sent to the AI. |
| **Web chat** | Provides sessions isolated per tab and displays the structured recommendations. |
| **PDF report** | Includes recommendations, warnings, citations and a navigable bibliography. |
| **Email delivery** | After generation, it can send the report through the Gmail API with OAuth2 to the address the user writes in the chat, if configured. |

The interface uses a fluid column of at most 640 px, a cream header with a legible title,
Dr. Cuișor's portrait and discreet botanical decoration. On mobile, the portrait appears below the description.
The identity of a virtual AI assistant and the medical warning remain visible. The same portrait
is used in the header, the conversation avatars, the application icon and the new PDF reports.

## 🎨 How it works

Every message goes through **Message classification**, with deterministic shortcuts for explicit requests and local Ollama `gemma3:1b` (`MEDICAL_CONDITION_AI_LOCAL_MODEL`) when needed. `POST /api/messages` quickly displays the message and saves the context, then `POST /api/classify` selects:

- **Remedies:** condition resolution and the existing search, with optional AI identification.
- **Plant/product:** the name/alias is resolved in the catalog, then the answer shows
  the name and the available Latin name in the header, with two distinct lists below.
  The number of conditions appears in the section title, without repetition in the header.
  Section titles and ranking entries use the same agreement with
  the Romanian name: masculine → “util/interzis”, feminine or neuter → “utilă/interzisă”,
  plural → “utile/interzise” and “sunt”. The determination uses the local Romanian dictionary,
  the first noun of the name and rules for ambiguous or irregular forms; “gutui”
  and “pătlăgele” are treated as plural. For unlisted words,
  the endings are used; unusual names may need additional lexical rules.
  No AI requests, migration or reindexing are needed. New structured messages include
  `herbAgreement`, used by the frontend; old messages without the field keep the feminine form.
  The number M of prohibitions appears only in the title of the dedicated section. The uses
  read the same `positive` pairs and the same published run as the rankings; the number N
  matches the product's ranking. The prohibitions read the `herb_caution_pairs` pairs
  with explicit `prohibition` evidence, from the caution run linked to that positive run;
  M matches `herb_caution_rankings.prohibition_ranking`. Cautions are kept
  separate and are not counted as prohibitions. Prohibitions require an explicit wording in the
  text about the respective product and condition; an AI or historical `caution` label is not
  enough. Recommendations alone do not appear in the list of prohibitions. The classification of sources
  is not clinical validation. A missing/incompatible positive run produces the same error
  as the rankings, without falling back to historical co-occurrences. A missing caution part is displayed as
  unavailability, and historical information that cannot be recovered is explicitly marked as partial.
  For any entry in `herbs`, each section has the number of conditions in its title.
  The product picture is loaded locally through `GET /api/herb-images/{herb_id}`, by the ID
  from the catalog. The search tries the Latin name, then the Romanian name, in `HERB_IMAGES_DIR`
  (by default `medicina-naturista-documente/data/images`), PNG files only. It ignores
  upper/lower case and applies the replacement of disallowed characters from the
  generation process; ambiguous matches are omitted. The folder is mounted read-only in Docker
  and excluded from the container image. The endpoint does not expose the registry or other files.
  After a successful load, the picture appears on the left (at most 280 × 280 px, without cropping),
  and the short lists remain in two columns on the right. When the text exceeds the space
  next to the image, the list of useful conditions flows into three columns: the first starts below the picture,
  the other two to its right and continue aligned down to the bottom. Long lists thus
  also use the space below the image. The alphabetical order reads from top to bottom
  in each column, then in the next column. The title and the sources remain full
  width; the prohibitions and warnings are not rearranged. Until loading, or
  if the picture is missing/fails, the existing three-column display remains on desktop.
  At most 640 px, the picture appears above the two-column list; at most 420 px, the list
  has one column. A missing product, folder or picture produces `404`, without a placeholder.
  New images are found on the next request, without reindexing or AI calls.
  A click on the picture opens the image in a modal panel as large as the page, above the
  interface, with proportions preserved and without cropping. Escape or the X button at the
  top close the panel and return focus to the picture. The image can also be opened
  from the keyboard, with Enter/Space; the page behind stays inactive while the panel is open.
  The product name is 24 px and the section titles are 20 px; the whole text of the prohibitions section, including
  the sources, is orange. The three sections are separated by 3 px lines;
  the source panels have no outer borders. Each “View source excerpts — N excerpts from M documents” panel
  is initially closed. On opening,
  20 whole fragments are loaded, with a filter by condition and “Load more”.
  Filters and pagination are independent. Empty sections keep the panel with zero sources,
  without HTTP requests. Each fragment appears only once in its section, with all
  the eligible conditions, the title, the document and the source lines. The product/aliases are
  highlighted in green; the conditions and their synonyms, in yellow. The original text is kept.
  `GET /api/herb-evidence/{groupId}?evidenceKind=positive|contraindication&conditionId=…&offset=…`
  selects the sources of the requested section (`positive` by default) and is limited to the session
  and tab that own the message. The filter must belong to the section. It does not call the AI and
  does not run a new hybrid search.
  Changing the run produces `HERB_EVIDENCE_STALE`; an expired/evicted answer produces
  `HERB_EVIDENCE_UNAVAILABLE`. The interface asks for the question to be repeated, without combining
  generations. The loaded fragments are kept only temporarily in the interface.

  The additive migration `028_herb_caution_rankings.sql` creates `herb_caution_runs`,
  `herb_caution_evidence`, `herb_caution_pairs`, `herb_caution_rankings` and
  `herb_caution_cache`. The caution projection reuses the local rules and the
  `recommendation`/`prohibition` values from the answers that the positive classification already requests.
  The caution projection adds no AI requests and keeps the classification rules. Information
  missing from the old caution cache is recovered only locally or marked `unknown`.
  The product warnings section uses the mechanism described separately below.
  Caution projection version 2 also checks the explicit lists of foods to avoid,
  including broken OCR lines. A warning about another product or procedure in the
  same fragment does not validate a prohibition for the product asked about.
  Positive preparation also prepares caution; publishing through the CLI atomically activates the two
  compatible runs. The active caution marker stays in `herb_caution_runs.is_active`,
  outside the metadata that enters the fingerprint of the positive index.

  After the operator has explicitly applied the migrations, populating the already-active
  positive ranking can be done separately, without inference or reindexing:

  ```powershell
  $env:PYTHONPATH = 'src'
  .\.venv\Scripts\python.exe -m scripts.build_hybrid_index --prepare-caution-ranking
  .\.venv\Scripts\python.exe -m scripts.build_hybrid_index --publish-caution-ranking RUN_ID
  ```

  The first command returns the ID of the new caution run and the number of unknown historical evidence items.
  The second accepts that ID only if the index, the positive run and the activation observed at
  preparation are still compatible. Both report `ai_requests_sent_total=0` and call
  neither the provider nor the model verification endpoint. Applying the migration
  alone does not populate or activate this data. The application does not migrate at startup.

  When updating from caution projection 1 to 2, only a new caution run is
  prepared and published through the commands above, using the updated code. Caches
  or tables are not deleted and the documents/embeddings are not reindexed. A caution
  run with the old version is displayed as outdated until the new one is published.

  **Warnings, contraindications and interactions:** the section uses exclusively the knowledge of the
  local Ollama model about each product in `herbs`, regardless of category and of whether
  documents or product–condition associations exist. On reindexing, a single request is sent
  for each product without a compatible result in the cache. The request contains only
  the product's identity: ID, Romanian name, Latin name when present, English names,
  category, family and aliases. It contains no fragments, conditions or quotations.
  The Latin species must be respected; a missing species is not invented.

  The answer is strict JSON with `herb_id`, `status=complete|uncertain` and `messages`.
  Each element has exactly `message_type=warning|contraindication|interaction` and
  `problem`. The messages are in Romanian, preferably 10–25 words, at most 240
  characters and 40 words, without automatic truncation. Interactions take into account
  medications, drug classes, supplements, other natural products, fruits,
  vegetables, foods and drinks. Uncertain identity or insufficient knowledge is
  marked `uncertain`; an empty list does not confirm the absence of risks.

  The additive migration `031_herb_product_safety_knowledge.sql` creates the table
  `herb_safety_messages`: `herb_id`, `message_type`, `problem`, plus `run_id` and
  `message_id` for publishing and deduplication. A product has several rows.
  `herb_product_safety_results` explicitly keeps the products with an empty list too,
  `herb_product_safety_cache` keeps the validated answers, and
  `herb_product_safety_runs` manages the atomic preparation and activation.
  For the current messages, `herb_safety_messages` is filtered through the generation with
  `herb_product_safety_runs.is_active=true`; publication deletes the superseded generations
  of the language (their results and messages go with them).
  The fragment-based tables `herb_safety_runs`, `herb_safety_cache`, `herb_safety_analysis`,
  `herb_safety_warnings` and `herb_safety_evidence` (migrations 029-030) were never part of this
  flow and are dropped by migration `039_drop_legacy_herb_safety_tables.sql`. The migration is
  applied through the normal indexing command or through the migration operator, never at
  application startup.

  The cache key depends on that product's identity and aliases, the prompt,
  the version of the JSON rules, the model and its digest. Changing another product, the
  documents or the conditions does not invalidate the answers of unchanged products.
  Valid empty or uncertain results are reused too. Each product's result
  is saved immediately; a failure does not lose the products already processed. A normal run
  without parameters creates a new generation and reuses the compatible cache.
  A change of product, prompt or model requires a new answer for the affected product.
  The old document-extraction cache cannot substitute for this analysis.

  Warnings are no longer added to the product–condition requests and requests
  per product/fragment are no longer planned. The existing list **Conditions with prohibitions** stays
  from `herb_caution_*`, with the same sources and rules; the new section displays separately
  Warnings, Contraindications and Interactions from the model's knowledge. The interface
  indicates this provenance and shows no quotations or “View source” for them.
  The entire warnings section is red, with a main title of 20 px. The provenance
  note spans the width of both columns and has the same size as the messages
  about partial data. Each
  problem starts with the category name in bold, followed by a period: “Warnings. …”,
  “Contraindications. …” or “Interactions. …”; there are no separate subtitles.
  The whole content of the section is split into two columns. On screens of at most 580 px a single
  column is used. The counter “Showing N of M warnings” is not displayed; loading
  further messages stays available when there are additional pages.
  Valid JSON and a correct identity do not constitute clinical validation.

  `GET /api/herb-safety/{groupId}` reads only the published generation, in pages of 20.
  The references stay tied to the message, session and tab; a changed generation or catalog
  produces `HERB_SAFETY_STALE`. There is no inference in the chat. The old evidence route does not
  invent sources for the model's answers and responds unavailable.

  The first population requires one request for each product in the catalog; subsequent
  reindexes request only the products without a compatible cache. Normal positive preparation
  also prepares this generation, and publishing activates it after checks.
  `--skip-positive-ranking` keeps the behavior of also skipping the AI safety stage.
  It can also be prepared/published separately, after applying migration 031:

  ```powershell
  $env:PYTHONPATH = 'src'
  .\.venv\Scripts\python.exe -m scripts.build_hybrid_index --analyze-safety-warnings
  .\.venv\Scripts\python.exe -m scripts.build_hybrid_index --prepare-safety-warnings
  .\.venv\Scripts\python.exe -m scripts.build_hybrid_index --prepare-safety-warnings --resume-safety-warnings RUN_ID
  .\.venv\Scripts\python.exe -m scripts.build_hybrid_index --publish-safety-warnings RUN_ID
  ```

  The analysis performs no inference; publishing checks only the database and the model digest.
  `RUN_ID` must belong to the new algorithm; the historical fragment-based runs are not
  compatible. On interruption, wait for the prompt to return before relaunching.
  The product in progress without a valid result can be resent; there is no automatic retry.
  The model digest is also checked before saving each answer; these reads
  of Ollama metadata run no inference and add no AI requests for the product.
  An invalid answer stops the preparation and keeps the previously published generation.
  Messages are not repaired heuristically, shortened or replaced with empty results.

  Progress uses `progress_stage=product_safety`, `safety_products_total`,
  `safety_products_completed`, `safety_cache_hits`, `product_safety_ai_requests`,
  `safety_batches` and `safety_batches_completed`; a batch is now a single product.
  `warnings_only_ai_requests` is kept as a compatibility alias of the number of
  new safety requests. The ETA is measured after the first validated and saved AI product;
  it stays `null` before the first measurement and is zero at `ready`/`published`.
  The request metrics include `herb_id`, `safety_source=model_knowledge`, times/tokens,
  the context, the output and the timeout. They do not include names, problems or generated text.

  The default safety parameters are `HERB_SAFETY_AI_MAX_REQUESTS=10000`,
  `HERB_SAFETY_BUILD_TIMEOUT_SECONDS=86400`, `HERB_SAFETY_AI_CONTEXT_TOKENS=65536`
  and `HERB_SAFETY_AI_MAX_OUTPUT_TOKENS=40000`. The request and time budgets were increased
  because the limit now applies to products, not to fragment batches. The budget of the
  combined command covers the time for associations plus the safety time; safety also has its
  own deadline. The per-request timeout stays 900 seconds, `think=false`,
  zero temperature and local streaming, with no cloud or repair AI requests.

  **The bilingual extension (migration 036).** While `HERB_SAFETY_EXTENSION_PRODUCTS` is empty, the flow
  above stays unchanged. When it is set, `--prepare-safety-warnings` rebuilds from scratch the
  warnings, contraindications and interactions of the in-scope products, in a single run
  for both languages: the local model `HERB_SAFETY_GENERATION_MODEL` (batches of `HERB_SAFETY_MINISTRAL_BATCH_SIZE`), then DeepSeek (always active,
  batches of `HERB_SAFETY_DEEPSEEK_BATCH_SIZE`, requires `DEEPSEEK_API_KEY`; without the key the preparation stops
  before any request).
  Each request receives only the identity of the products from the catalog (no fragments, conditions or
  user data) and returns each message in Romanian and English with the same type. The prompt
  `herb_product_safety_bilingual_system.md` asks for at least 7 messages in total, with no minimum per
  category and without padding with invented messages; the minimum is not validated. The existing list is not
  sent to the models. Valid answers are saved per product and stage in
  `herb_product_safety_extension_cache`; an invalid or missing product stays uncached, and the
  next preparation resends only the missing products. An invalid JSON envelope stops the preparation.
  The list is merged with DeepSeek taking priority, then the local model (the real anticoagulants case showed that DeepSeek was the correct one). Exact duplicates are removed deterministically; semantic
  ones are found by a local model, `HERB_SAFETY_DEDUP_MODEL` (migration 037, stage `dedup`, prompt
  `herb_product_safety_dedup_system.md`, batches of `HERB_SAFETY_MINISTRAL_BATCH_SIZE` products, per-product
  cache, the model's own digest): the model groups equivalent messages, regardless of type, and from each group the
  message of the higher-priority source remains (for the same source, the more severe type). Removal is done once
  on the bilingual message, so that the RO and EN lists stay identical in count, order and type.
  Embeddings with a threshold do not separate real duplicates from distinct messages and are not used. The removed
  pairs are written to `aiWork/herb_safety_dedup_pairs.json`. Contradictory messages about the
  same partner are not resolved automatically.
  The preparation creates two generations (RO and EN), copies the out-of-scope products from the language's
  active generations and displays `run_id_ro` and `run_id_en`; each is published separately,
  with `--publish-safety-warnings RUN_ID` (the language is read from the generation). While the extension is
  active, positive preparation/publishing no longer touches the safety generations. Normal reindexing
  (`build_hybrid_index` with no mode flags, which does not use `--skip-positive-ranking`) also runs at the
  end the extension for the in-scope products, for both languages, and publishes the two generations;
  all AI requests are made in this offline phase,
  never at the chat question, which reads only the published generation.
  The DeepSeek stage sends catalog data to an external model; the quality is not clinically validated.

  Pilot, then full activation (`HERB_SAFETY_EXTENSION_PRODUCTS=hypericum perforatum`, then
  `first:100` and `all`):

  ```powershell
  $env:PYTHONPATH = 'src'
  .\.venv\Scripts\python.exe -m scripts.build_hybrid_index --analyze-safety-warnings
  .\.venv\Scripts\python.exe -m scripts.build_hybrid_index --prepare-safety-warnings
  .\.venv\Scripts\python.exe -m scripts.build_hybrid_index --publish-safety-warnings RO_RUN_ID
  .\.venv\Scripts\python.exe -m scripts.build_hybrid_index --publish-safety-warnings EN_RUN_ID
  ```

  Matching of Romanian names accepts inflections from the bundled Hunspell dictionary (article, plural, genitive), with or without diacritics, including in multi-word names. The general rules for incomplete entries are validated with the same dictionary, without per-plant exception lists. The exact form takes priority; names shared by several species require choosing the species.
- **Top plants/products:** positive ranking from `herb_positive_rankings`, filtered exactly by the requested category before sorting and limiting. The interface offers the examples “Top 100 natural products” and “Top 10 natural products for flu”; a click fills in the field and gives it focus, then the user sends the message. “Top X natural products” without a condition displays the 11 categories, each on a numbered row; the user answers with the category number and receives up to X products from that category. An invalid choice repeats the list without changing X. Direct commands such as “Top 20 supplements”, “Top 10 medicinal herbs”, “First 20 vitamins” and “Top 100 seeds” remain available. “Top 100”, “Top 100 plants”, “general top” and “all categories” include all categories. Without a quantity, 100 entries are used; unknown or multiple categories ask for a single category to be chosen, and an invalid number asks for a quantity between 1 and 10000. Clarifications keep the requested category/number. The answer shows the number actually returned, the associations and the regional aliases; no hybrid search or AI generation for explicit commands.
- **Top for a condition:** “Top 10 natural products for flu” selects directly, from all categories, only the products with a `positive` pair for the condition from the catalog. “Top 5 supplements against flu” adds the exact category filter; the Romanian words for “for” (`pentru`) and “against” (`contra`, `împotriva`) are equivalent. Eligibility from `herb_positive_pairs` and the ranking from `herb_positive_rankings` use the same compatible published run, in a single transaction. The order is the descending score `HERB_CONDITION_TOP_FORMULA` (default `2*L1+L2+100*L3`), then L3 descending, then ID ascending, with the condition and category filters applied before the limit N. L1 = the distinct fragments with the condition in the title and a positive mention of the product; L2 = the distinct fragments that mention the product and name the condition in the text (title excluded, no polarity classification); L3 = the product's total number of positive conditions, displayed at the end of the row as “· useful in N conditions”, after “· X fragments dedicated to the condition · Y fragments that mention it” (L1 and L2; the L2 part is missing when it is zero) and after the regional names. The values are precomputed in `herb_condition_scores` (migration `037`), keyed on the active positive run, so the request reads a single index range and sorts in memory. The top without a condition stays ordered by L3. Synonyms and forms with/without diacritics are resolved locally; an unknown condition asks for rephrasing, while ambiguous names, approximations and requests with several conditions ask for a single condition to be chosen, keeping N and the category. Unrecognized qualifiers are not removed to widen the filter. The results may be fewer than N or zero; ranking unavailability produces the existing error, without falling back to historical associations. The flow does not generate a report, PDF or email and does not constitute clinical validation.
- **Miscellaneous:** search by the original message, without identifying the condition through AI and without the notifications about the unknown condition. Generation of the naturopathy report stays as in the remedies flow.
- **Report email:** locally validated address and the previous PDF from the same session; no new search. The message can be an address alone or a request such as “Send the report to name@example.com”.

The classification sends to local Ollama only the message and minimal routing context, with no PDF or corpus. It reuses `CONDITION_AI_LOCAL_BASE` and `MEDICAL_CONDITION_AI_LOCAL_MODEL`, with temperature 0, no API key and no Hugging Face fallback. The JSON schema enforces one of the five intents and the allowed fields; strict validation is repeated in the application. Plant names and aliases are also recognized in the local catalog, regardless of diacritics or hyphens. An explicit name completes the clarification. If the name matches several plants, the application displays the Romanian and Latin names and asks the user to choose; this selects a single species and its associations. It is independent of `REPORT_GENERATION_MODELS`. On failure, the existing flow continues, with a notification; explicit email requests ask for clarification, and an address alone keeps the existing deterministic command. Unclear requests ask for the plant or the recipient. Classification and sending are not retried automatically; the message identifier and the revision prevent repeating the same shipment.

Updated diagram: [chatbot-external-connections.xmind](architecture/chatbot-external-connections.xmind). Message classification and routing (XMind 8): [message-classification-plan.xmind](architecture/message-classification-plan.xmind).

```text
📚 Markdown documents
        ↓
✂️ R1 / R2 / D1 fragments, with conditions, source and line range
        ↓
🧠 Qwen3 embeddings  +  🔎 tsvector, in Postgres/pgvector
        ↓
⚖️ combined score from the chosen signals (P1 › P2 › lexical › semantic) and the context budget
        ↓
👁️ the user reviews the fragments found
        ↓
🤖 chosen model: Ollama for all users / DeepSeek for admin only
        ↓
💬 recommendations in chat  +  📄 PDF report  +  ✉️ optional email
```

> **Local vs. external:** the documents, fragmentation, indexing and retrieval run locally. Generation sends the consultation profile and the selected fragments to the model chosen in the UI: local models through `OLLAMA_API_BASE`, `deepseek-flash` through the DeepSeek API, `DeepSeek-V4-Flash` through the Hugging Face/DeepInfra router or `grok-4.3` through the xAI API. Generation with any model requires admin authorization. The selection applies only to the current report, without modifying environment variables or falling back to another provider. Identifying an unknown condition sends only the message to Ollama on the host. On timeout, communication error or invalid answer, the condition stays unidentified; no other AI provider is called. Delivery through Gmail is optional.

## 🛠️ Technologies used

| Area | Technologies |
|---|---|
| **Language and runtime** | Python ≥ 3.11 (documented local environment: 3.11), PowerShell, Node.js 22 for the frontend |
| **Interface and API** | React 19, TypeScript, Vite, TanStack Query, FastAPI, Uvicorn |
| **Local embeddings** | FastEmbed, ONNX Runtime, `Qwen/Qwen3-Embedding-0.6B` (optional GPU indexing, PyTorch fp16) |
| **Index storage** | PostgreSQL, `pgvector` (cosine similarity), `unaccent` + `tsvector` (lexical search) |
| **Fragment scoring** | `4·P1 + 2·P2 + L + V` with all signals, prioritizing the condition in the title, then in the text; the patient can choose any combination of signals |
| **AI generation** | Native Ollama `/api/chat` or DeepSeek Responses API (admin only), chosen for each report, structured JSON answer |
| **Documents** | ReportLab for PDF, pypdf for processing and verification |
| **Email** | Gmail API, OAuth2 with refresh token |
| **Configuration** | python-dotenv, environment variables |
| **Running and publishing** | Docker, Docker Compose, Tailscale Funnel, PostgreSQL (`pgvector/pgvector`) |
| **Testing** | `unittest`, `pytest` + `testcontainers` (ephemeral Postgres) for the backend, Vitest for the frontend |

## 🗺️ Architecture documentation

| Document | What it explains |
|---|---|
| 🧠 [Hybrid index generation flow (XMind 8)](architecture/hybrid-index-generation.xmind) | The complete flow: documents → incremental synchronization (SHA-256) → R1/R2/D1 fragments → embeddings → Postgres (`pgvector` + `tsvector`). |
| 📄 [Final report generation flow (XMind 8)](architecture/final-report-generation.xmind) | The complete flow: message → hybrid retrieval → fragments displayed to the patient → “Generate report” → the AI provider → PDF → download and sending by email to another person. |
| 🔎 [Fragment search and scoring (XMind 8)](architecture/fragment-search-and-scoring.xmind) | The complete flow: message → recognized conditions → score (`4·P1 + 2·P2 + L + V` with all chosen signals) for all fragments → relevance percentage → context limiting. |

## 📁 Project structure

```text
medicina-naturista/
├── architecture/                 # diagrams of the main flows in XMind format
├── medicina-naturista-documente/
│   └── data/
│       └── documents/                # the local Markdown corpus
├── model_cache/                  # the local models; ignored by Git
├── src/
│   ├── backend/
│   │   ├── ai/                       # fragmentation, conditions, search, retrieval, AI clients and prompts
│   │   ├── core/                     # models and isolated sessions
│   │   ├── migrations/               # PostgreSQL schema and the initial catalogs of conditions/plants
│   │   ├── integrations/             # Gmail integration
│   │   ├── reporting/                # PDF report generation
│   │   └── web/                      # FastAPI JSON API (also serves the React build)
│   ├── frontend/                 # the React/TypeScript application (Vite)
│   ├── scripts/
│   │   ├── build_hybrid_index.py     # incremental synchronization of the index in Postgres
│   │   ├── bootstrap_database.py     # creates the missing database before indexing
│   │   ├── migrate_database.py       # applies the versioned SQL migrations
│   │   ├── condition_sql.py          # generates SQL for new conditions
│   │   ├── manage_dependencies.py    # generates and verifies the locks
│   │   ├── search_index.ps1          # local search from the terminal
│   │   ├── clean_documents.py        # cleaning and OCR/spelling correction with the bundled dictionary
│   │   ├── fragment_report.py        # fragmentation simulation; reads the catalog from the DB, no embeddings
│   │   ├── audit_conditions.py       # read-only audit of the conditions dictionary
│   │   ├── audit_near_dupes.py       # near-duplicate canonical conditions (read-only)
│   │   ├── audit_herbs.py            # read-only report on the plants in PostgreSQL (in tmp/herbs_review.md)
│   │   ├── icd10_work/               # one-off scripts for completing the dictionary from ICD-10
│   │   ├── evaluate_retrieval.py     # measuring search quality (P@10, MRR, nDCG)
│   │   ├── google_oauth_setup.py     # Gmail OAuth2 authorization
│   │   ├── extract_pdf_markdown.py   # structured extraction to Markdown
│   │   └── merge_book_pdfs.py        # merging book parts from PDFs
│   └── tests/                    # unit and integration tests
├── docker-compose.yaml
├── Dockerfile
├── pyproject.toml
├── requirements-runtime*.lock    # pinned runtime dependencies, with hashes
├── requirements-dev*.lock        # runtime + development/testing tools
└── requirements-web.txt          # compatibility alias for Windows/Python 3.11
```

## 🚀 Quick start

### 1. Preparing the environment

PowerShell commands are run from the project root. Install Python 3.11 and Node.js 22/npm; PostgreSQL with `pgvector` must be reachable before indexing. The corpus `medicina-naturista-documente/data/documents/` is provided separately. The catalogs of conditions and plants are rebuilt from the shipped SQL migrations.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-runtime.lock
```

Place the Romanian documents in `medicina-naturista-documente/data/documents/ro/` and the English documents in `medicina-naturista-documente/data/documents/en/`. Moving the old sources from the `documents` root into `documents/ro` is done manually. The cleaning below walks both directories, RO and EN, recursively. Do not publish the corpus if it includes private or protected material. Optionally, clean them before indexing (PDF extraction metadata, links, page markers, “See also” references, Romanian diacritics transcribed into ASCII letters: `ă/â → a`, `î → i`, `ș → s`, `ț → t`):

```powershell
.\.venv\Scripts\python.exe src\scripts\clean_documents.py --dry-run
.\.venv\Scripts\python.exe src\scripts\clean_documents.py
```

Diacritic replacement is active by default; the `--no-fold-diacritics` option keeps them. Word correction uses the Hunspell files `ro_RO.dic` and `ro_RO.aff` from `src/scripts/dictionaires/ro/` for the RO sources, and `en_GB.dic` and `en_GB.aff` from `src/scripts/dictionaires/en/` for the EN sources, located relative to the script. The language is determined from the `documents/ro` or `documents/en` directory, including when `--source` points to a subdirectory of it. To process only the English sources, add `--source medicina-naturista-documente/data/documents/en`.

Correction runs after cleaning for the RO and EN sources: it joins two unrecognized OCR fragments, splits glued words and fixes rare unambiguous mistakes. Modernization of old spelling applies only to Romanian. Frequencies and function words are separated per language, so that the RO corpus does not influence the EN corrections and vice versa. For files outside the language directories, the previous handling is kept: only texts detected as Romanian receive spelling corrections; English or mixed ones receive only the general cleaning. Joining protects dictionary words, function words such as `la`, `de`, `si` and single-letter fragments; expressions such as `tumora la san` and `pieptul e` stay separate. The whole processing is planned in memory: frequencies are recomputed after each pass, until a complete pass changes nothing. Only then are the files rewritten. With the same corpus, dictionary and options, a new successful run no longer changes the documents or their modification dates. A cycle or exceeding the limit of 16 passes stops execution before any rewriting of the sources. `--dry-run` computes the same stable result, without modifying the documents.

Documents in `documents/ro` clearly detected as English use the EN dictionary during
cleaning, without moving the files. Overriding the folder's language requires a minimum of 20
words, at least four distinct function words specific to English and
the EN result of the combined detector. Short texts or those classified as mixed/uncertain keep the folder's language.
Detection combines the frequency of function words with the distinct vocabulary found exclusively
in one of the dictionaries. Common and unknown words are neutral. The vocabulary
vote requires at least five distinct exclusive words, coverage of at least 20%
and a ratio of at least 2:1; a conflict with the function-word method produces the
mixed result. Both dictionaries are loaded once, before the language selection,
and reused for detection and correction. Hunspell expansion combines at most one
prefix with a compatible suffix, without arbitrary accumulation of prefixes.
The selection is announced in the console through `Dictionary override ro -> en`, including at
`--dry-run`. This selection concerns only spelling correction; the language of the fragments
at indexing stays that of the source folder.

The report `var/spelling_changes.tsv` contains the file, the line in the text cleaned at that pass, the rule, the before/after forms and the `pass` column with the pass number. It records the correction steps; later passes may remove lines and change the numbering. It is also generated at `--dry-run`. Use `--spelling-report` for another destination. A missing dictionary stops execution before the documents are modified. The protection of doses and numbers checks the result of each pass; files that violate it are kept intact and execution ends with an error. `--no-fold-diacritics` keeps the diacritics and uses the dictionary forms for replacements. Correction remains heuristic; it cannot guarantee the medical meaning of the text and does not automatically repair wrong joins produced by earlier versions.

You need a Postgres with the `pgvector` extension running and reachable at `DATABASE_URL` (by default `postgresql://medicina:medicina@127.0.0.1:5432/medicina`); the simplest way is `docker compose up -d db`, which requires `POSTGRES_PASSWORD` in `.env` (the user and database are `medicina` by default), so `DATABASE_URL` must use the same password.

### 2. Synchronizing the index

The default reindex reads both roots, `DOCUMENTS_DIR` (by default
`data/documents/ro`) and `DOCUMENTS_EN_DIR` (by default `data/documents/en`), and publishes
a single atomic index. `--source-ro` (alias `--source`) and `--source-en` explicitly
replace the roots. A missing, empty folder or one overlapping the other stops the build before
publishing. The source identities are `ro/<path>` and `en/<path>`; the prefix is not a
category. Fragments, score statistics, sources and rankings are filtered by language.
After indexing, the default preparation/publishing of the recommendations and warnings runs
for each language with its own prompt. The dedicated analysis, preparation, resume or
publish commands accept `--language ro|en`; RUN_ID must be used in the language in which it was created.
The search CLI accepts `-Language en`, and `fragment_report.py` and
`evaluate_retrieval.py` accept `--language en`. Changing the representation version to
`11` requires reindexing; the application does not apply migrations and does not start reindexing at startup.


```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe src\scripts\build_hybrid_index.py
```

The script imports the `backend` package, so it needs `PYTHONPATH=src`. The database comes from `DATABASE_URL` (`.env`); `--model` and `--source` are optional. The script starts with the Python you run it from (on CPU, no other environment); for GPU see below.

`TEXT_REPR_VERSION` is defined once in `src/backend/ai/index_constants.py`, with the value `"11"`. The indexing script and the backend read the same constant; it is not an environment variable. Changing the value makes the next script run reprocess all documents; until synchronization, the backend rejects the index with the old version. Modifying the constant does not automatically start reindexing. Restart the backend after changing the code.

The embedding model is `Qwen/Qwen3-Embedding-0.6B` (1024-dimension vectors); another model is not known to the code. Search reads the model from `sync_metadata` and writes the queries according to its profile (`ai/embedding_model.py`: the Qwen instruction on the query, no prefix on passages). **If the database contains an index made with another model or another dimension, the next build re-embeds all documents**, and the `chunks.embedding` column is recreated in the same transaction as the new documents and metadata. Any error keeps the previous generation and dimension. The duration depends on the corpus and hardware. GPU indexing requires a separate `.venv-gpu` environment, with the application's dependencies, `torch` with CUDA support and `sentence-transformers` already installed:

```powershell
$env:PYTHONPATH = "src"
$env:EMBEDDING_DEVICE = 'cuda'
.\.venv-gpu\Scripts\python.exe src\scripts\build_hybrid_index.py
```

Update the runtime dependencies in every Python environment used for indexing. The package `pyahocorasick` is imported as `ahocorasick`; installing it in `.venv` does not make it available in `.venv-gpu` or in the global Python. For an existing GPU environment that lacks this dependency:

```powershell
.\.venv-gpu\Scripts\python.exe -m pip install --no-deps --only-binary=:all: pyahocorasick==2.3.1
```

The builder checks that the package is available before starting the workers and shows the interpreter and the install command if the import fails.

On the first synchronization, the model is downloaded to `model_cache/` if it is missing. After that, search works offline. CPU search requires the FastEmbed/ONNX model, even if indexing was done on GPU with PyTorch.

On subsequent synchronizations, only new or modified documents are processed, and deleted ones are removed from the index. Changing the conditions catalog, the model or the way the text is prepared requires a complete rebuild of the index. Progress and the estimated remaining time are displayed in the terminal.

**Reindexing creates the database if it is missing and automatically applies the SQL migrations.** Permissions to create the database, the schema and the extensions are required; optionally, `DATABASE_BOOTSTRAP_URL` can provide a separate account for creation. The web application does not run migrations at startup. Conditions, plants and synonyms are read from PostgreSQL; additions are made through new migrations in `src/backend/migrations/`, without modifying those already applied.

During synchronization, search and the source list are temporarily unavailable (`503`). Generation from fragments already found and PDF downloads can continue. The new index is published only after all vectors have been computed and validated; a failure keeps the previous index. If the catalog has changed in the meantime, search requires the reindex to finish. A missing or invalid catalog blocks search, and an incompatible index requires resynchronization (`INDEX_RESYNC_REQUIRED`).

To rebuild the index, keep the source documents, the SQL migrations, the model and the configuration. Owner authorizations require a separate backup.

Search uses only the selected sources. An empty selection searches nowhere; if all the selected sources have disappeared, the application asks for a new selection. If only some have disappeared, it keeps the valid ones and displays a warning.

In batch generation, a reference to a nonexistent fragment or to one from another batch invalidates the answer and stops the whole report; nutrition elements without citations remain exempt. The reusable validator keeps the compatible partial-report mode for other consumers, but the new generation flow calls it strictly and does not publish a partial PDF. On failure, the search is kept for a manual retry. Citation checking is not medical validation. The AI client logs contain only technical diagnostics, without the text of the fragments or of the answer.

To see which fragments would result, without writing to the index and without embeddings (requires the migrated catalog from PostgreSQL):

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe src\scripts\fragment_report.py
```

### 3. Local search

```powershell
.\src\scripts\search_index.ps1 "plante și măsuri pentru tuse"
```

For results that are easy to process programmatically:

```powershell
.\src\scripts\search_index.ps1 "plante și măsuri pentru tuse" -Json
```

Terminal search returns all fragments with a positive score (without the AI provider's context limit). Each result keeps the source document, the line range and the score components (`P1`, `P2`, `L`, `V`), so that the passage can be checked in the original file. `--signals` chooses the score signals (any combination of `A` conditions, `B` lexical, `C` semantic; default `ABC`), for example `python -m backend.ai.search "gripa" --signals AB`. The example queries above are Romanian search phrases, as the default corpus is Romanian (“plants and measures for cough”, “flu”).

Search quality is measured on the labeled queries in `src/tests/eval/retrieval_queries.json`:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe src\scripts\evaluate_retrieval.py --output after.json
```

### 4. Starting the application in development

For reports, install the `gemma4:12b` model in Ollama on the host. For the admin's DeepSeek option, add the DeepSeek key and the owner key to the local `.env` file:

```dotenv
REPORT_GENERATION_MODELS=ollama-gemma3:1b,ollama-gemma4:12b,ollama-ministral-3:8b,ollama-qwen3.5:9b,ollama-qwen3.5:4b,ollama-deepseek-r1:8b,deepseek-flash,huggingface-deepseek-v4-flash,grok-4.3
DEEPSEEK_API_KEY=...
OWNER_KEY=a-long-secret-key
COOKIE_SECURE=false
```

Build the React interface (FastAPI serves `src/frontend/dist`):

```powershell
cd src/frontend
npm ci
npm run build
cd ..\..
```

Then start the application:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn backend.web.main:app --host 127.0.0.1 --port 7860
```

If you synchronized the index in step 2, the migrations are already applied. To maintain an existing database, you can run them separately with `.\.venv\Scripts\python.exe -m scripts.migrate_database` (with `PYTHONPATH=src`). Open the chat at `http://127.0.0.1:7860/`, and `http://127.0.0.1:7860/owner` for login/logout. The form sends the key through `POST /api/owner/login`, with CSRF; logout revokes the token through `POST /api/owner/logout`. With the public prefix, the form is `/medicina/owner` on the configured HTTPS origin. The key must not be put in the URL or in the terminal history. Authorization remains valid across restarts until logout or key rotation. The old route with the key in the query remains only for compatibility. `/healthz` also checks the AI provider configuration; `/readyz` adds the check of the availability and compatibility of the index.

For message classification and local identification of conditions, start Ollama on `CONDITION_AI_LOCAL_BASE` (default `http://localhost:11434/v1`) and download the model once with `ollama pull gemma3:1b`. This model is separate from the provider chosen for report generation.

For interface development with automatic reload, run `npm run dev` in `src/frontend/`. Vite serves the interface locally at `http://localhost:5173/medicina/` and sends the API requests, health checks and the owner form to the production backend `https://cristiantone.taila68086.ts.net/medicina/`. Messages, searches and reports use this backend. The interface's TypeScript files are served locally, without being sent through the proxy. The backend must be available; `npm run dev` does not start it. `DEV_BACKEND_URL` can override the backend address.

To use a locally started backend instead, set the address before launching Vite:

```powershell
$env:DEV_BACKEND_URL = "http://127.0.0.1:7860/"
npm run dev
```

In this variant, the local interface is at `http://localhost:5173/`. To return to the default production backend, remove the variable with `Remove-Item Env:DEV_BACKEND_URL -ErrorAction SilentlyContinue` and restart Vite. `PUBLIC_BASE_PATH` continues to configure the path for the production build.

The JSON API (`src/backend/web/main.py`) is used by the React interface; the OpenAPI documentation (`/docs`) is disabled. `/api/...` requests with a session send the `X-Tab-Id` header (the tab identifier).

| Endpoint | Role |
|---|---|
| `GET /healthz` | Application status and AI key configuration; independent of index maintenance or compatibility. Used by the Docker healthcheck. |
| `GET /readyz` | Also checks the index; 503 with `INDEX_MAINTENANCE`, `INDEX_RESYNC_REQUIRED` or `INDEX_UNAVAILABLE` and `Retry-After: 60`. |
| `GET /owner` | The owner login/logout form. The old variant with `?key=...` is still accepted but not recommended: it exposes the key in the URL. |
| `GET /api/owner` | Authorization status and the CSRF token for the browser. |
| `POST /api/owner/login`, `POST /api/owner/logout` | Issue, respectively revoke, the individual authorization; require a valid origin and a CSRF token. |
| `GET /api/session` | Creates the tab's session and returns the conversation history. |
| `GET /api/categories` | The tree of categories (the sources' folders) and the default selection (all). |
| `POST /api/messages` | Saves the message, the categories and the signals; returns `classifyMessage` and `contextRevision`. An optional `messageId` prevents duplicating the request. |
| `POST /api/classify` | Applies the deterministic shortcuts or classifies through local Ollama; routes to `remedii`, `planta`, `top_plante`, `diverse` or `email_raport`. Requires `X-Context-Revision`. |
| `POST /api/condition` | Identifies through AI the condition that the dictionary does not know (local Ollama, no fallback). |
| `POST /api/search` | Runs the search and returns the fragments found and the “Generate report” section. |
| `GET /api/report-models` | All the configured models in env order, `defaultModel` (the first model) and `allowedModels` (those permitted to the current user). The visible list is the same for the public and the author; rights are checked separately. For admin only, it also adds the default values of the generation limits, displayed in the panel: `batchMaxTokens` (per model), `batchWorkers` (`default` and `options` `[1, 2]`) and `maxOutputTokens` (per model). |
| `GET /api/report-duration-estimate?model=...&characters=...` | The estimated duration in seconds and the number of measurements, using all the model's rows in `report_generation_metrics`. Aggregates only, without conditions or medical texts. |
| `GET /api/searches/{search_id}/report-batches?model=...&minScore=...&effort=...&batchMaxTokens=...&maxOutputTokens=...` | The number of batches that generation would produce, computed with the same partitioning (`partition_evidence`) from the fragments that reach the minimum score and the chosen limits; it does not call the AI provider. The report panel displays it under “Estimated duration”. |
| Token limits in the report panel (admin only) | Positive integers (groupings like “26 200” / “26.200” are accepted), at most 2,000,000; the minimum input is 1,000. The output must be smaller than the model's `context` (from `REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL`), and `context − output` must leave at least 1,000 input tokens; otherwise the server responds 422 (`OUTPUT_TOKENS_TOO_LARGE`, `INPUT_TOKENS_TOO_SMALL`, `INPUT_TOKENS_NO_ROOM`). The panel applies the same rules before the request, displays the effective input when the context reduces it, and warns (without blocking) below 2,000 output tokens, when each fragment ends up in a separate batch or when a single fragment exceeds the limit. |
| `POST /api/searches/{search_id}/generate` | Receives `minScore` and `model` from the catalog; without a model it uses `REPORT_GENERATION_MODELS`. Any model without admin authorization → HTTP 403; unknown model → HTTP 422. Applies the selected threshold and processes the batches in parallel according to `batchWorkers` from the request (`1`, `2` or `3`; without the field, `REPORT_BATCH_WORKERS`, default 2), within a single active report. The optional fields `batchMaxTokens` and `maxOutputTokens` (positive integers) override for this report `REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL`, respectively the configured output limit; for fixed-context models (R1 8B), `maxOutputTokens` must be smaller than the context, otherwise HTTP 422. The same options with the same `requestId` are idempotent; different options → HTTP 409. Generates a single PDF after all batches are validated. |
| `GET /api/reports/{tab_id}/{report_id}` | Downloads the PDF generated in the tab's session. |
| `POST /api/session/end`, `POST /api/session/unload` | Close the tab's session (on request, respectively when the page is closed). |

## Sessions, retention and owner authorization

- **Sessions:** the application can be opened simultaneously in several tabs or browsers from the same PC/IP. Each full page load, including refresh, Shift+F5 or duplicating the tab, starts a new conversation. The identifier is kept only in the page's memory; retries and reconnections from the same page continue the current conversation. The global session limit and the per-minute session-creation limits remain active.
- **Retention:** the history, the fragments and the PDFs stay in process memory. The session expires after one hour of inactivity or at most four hours (`SESSION_IDLE_SECONDS`, `SESSION_MAX_SECONDS`). Closing the page tries to close the session; if the notification does not reach the server, expiry frees the data. Restarting the application removes them. At most 12 searches and 12 reports are kept per session, within the memory budgets.
- **Owner / admin:** set `OWNER_KEY` and authenticate the browser through the `/owner` form to use the external models `deepseek-flash`, `huggingface-deepseek-v4-flash` and `grok-4.3`. The four Ollama models are available without authorization. The “AI model” selector follows the “Minimum score” field; the list updates when returning to the page after authentication. The API checks authorization at each generation with an external model and when reading/cancelling its job. PostgreSQL keeps the token hash and technical data, without conversations or PDFs. Authorization survives a restart; logout revokes it, and changing the key invalidates the existing tokens.

## Plant and product catalog

Each non-empty top displays right under the title the instruction for selecting by product number, with the example `1` for the first product, before the score explanation and the list.

After a plants or products top is displayed (general, per category or for a condition), the next message can be just the number of the position in the list: `1` opens the same details as the question `la ce e bun Ulei de măsline` (“what is olive oil good for”), if that is the first product displayed. The exact order of the displayed top is used, without a new AI classification. A number outside the list asks for a valid choice and keeps the list for a retry. Any other request ends this selection; the menus for category, number of entries or condition keep their own rules.

The catalog of plants and products and the aliases are read from PostgreSQL. A plant search ignores differences in case, diacritics and hyphens; a name shared by several species asks the user to choose. The “Top N plants” requests display the ranking of plants and products by the number of distinct conditions with positive recommendations identified in the sources, and the regional names, without generating a report. Each entry uses the wording “useful in X conditions” (in Romanian “util/utilă/utile în X afecțiuni”, in agreement with the Romanian name); the note states that warnings, contraindications and mixed relationships are excluded from the score and that this classification is not clinical validation. The general lists of conditions of a product keep the historical associations, including warnings.

The per-condition tops reuse this global ranking after filtering the positive pairs for the requested condition. A product with a higher ranking that has no positive association with the condition is excluded. The filter requires no migration or reindexing; it requires an already published and compatible positive run. The new local code and the examples from the text catalog become available in the running application only after the explicit delivery of the compatible version and a page reload.

The accepted product categories are `seminte` (seeds), `suplimente` (supplements), `uleiuri esentiale` (essential oils), `uleiuri` (oils), `aminoacizi` (amino acids), `vitamine` (vitamins) and `minerale` (minerals). Bee products, fibers, probiotics and prebiotics belong to the `suplimente` category. The `medicamente` (medicines) category and the `aspirina` entry are removed by migration 026. These are technical catalog groupings, without establishing the medical status or efficacy of the product. The API intent `planta` and the existing routes also cover products, recognized by `ro` and `en`, regardless of case or diacritics. Products without a species return `species=[]` and are displayed without empty parentheses.

Migrations `014`/`015` add 391 products (including the 12 commercial names confirmed under `suplimente`), reuse the records for psyllium, ashwagandha, brewer's yeast, spirulina and chlorella and add only to the plant Thuja the aliases `arborele vietii` and `thuya occidentalis`. The historical vitamin names and the three labels for jasmine, vanilla and white lotus oils are kept per the catalog requirement, with no claims about chemical identity or extraction. “Bilberry oil or extract” is excluded. The initial total after migration is 1,579 entries: 1,188 botanical and 391 products. The catalog does not automatically introduce synonyms such as `NAC`: the available canonical name is `N-acetilcisteina`.

For migrations `014`/`015`, the compatible code must be delivered before the migration; after the migration, `scripts.build_hybrid_index --rebuild-herbs` is run for associations, ranking and fingerprints. Between these stages, the catalog results may require resynchronization. Unchanged documents keep their embeddings if their profile has not changed.

Migration `016_separate_herb_category.sql` separates the category from the botanical family and rebuilds only the `herbs` table for the physical order `id, category, family, latin, ro, en, ranking`. For an upgrade from 015: prepare the compatible image, verify the backup and data snapshots, briefly stop the application, explicitly run `python -m scripts.migrate_database` with `PYTHONPATH=src` and the target database configuration, then start the new image and check `/healthz` and `/readyz`. The migration is transactional, keeps the IDs, names, aliases, associations and ranking; it refuses configurations or additional dependencies it does not cover. **For 016, reindexing, `--rebuild-herbs` or embeddings are not run**: the matching fingerprint and all the `sync_metadata` values remain unchanged. SQL NULL for family/latin is normalized to an empty string only in the runtime objects; the parser of the historical JSONL sources remains botanical. The runtime catalog fingerprint is versioned separately and includes the category and the family.

Migration `017_food_categories_in_herbs.sql` introduces 12 categories: `plante medicinale` (medicinal herbs), `fructe` (fruits), `legume` (vegetables), `cereale` (cereals), `seminte`, `uleiuri esentiale`, `suplimente`, `aminoacizi`, `vitamine`, `minerale`, `produse apicole` (bee products), `fibre, probiotice, prebiotice` (fibers, probiotics, prebiotics). The four botanical groups keep the Latin name and the family. The food classification puts tomatoes under fruits, nuts/hazelnuts under fruits, food legumes under vegetables and buckwheat/quinoa/food amaranth under cereals. Whole genera or families are not moved. Source species and seeds consumed separately are distinct entries: the four seed products (sunflower, pumpkin, grape, flax) have SQL NULL `latin` and `family`. An oil from seeds stays in its own category. Categories do not become matching names or aliases.

017 explicitly reclassifies 161 existing rows and adds the four seeds plus `chenopodium quinoa` (`amaranthaceae`): the seed total is **1,584**, with all the old IDs/names/families/aliases kept. The new rows receive identity IDs and an initial ranking of 0. The forms with/without a hyphen are already equivalent in matching and need no duplicate aliases. The common definitions are in `core/herb_categories.py`; the historical sources parser remains botanical.

Migration `018_reclassify_oils_medicines_and_beta_carotene.sql`, applied after 017, extends the catalog to **14 categories** and moves only three entries: `beta-caroten` → `vitamine`, `ulei de masline` → the new category `uleiuri`, `aspirina` → the new category `medicamente`. It keeps the IDs, names, aliases, ranking, associations and the total of 1,584 entries. “Top N oils” and “Top N medicines” use the new filters; “essential oils” remains a distinct category. For 018 alone, the associations, fragments or embeddings are not rebuilt. If 017 is still unapplied, the rollout requirements for 017 below remain valid. The migration refuses unexpected identities or source categories and is not applied automatically at application startup.

Migration `019_reclassify_additional_oils.sql` explicitly moves from `suplimente` to `uleiuri` the seven existing products: primrose, avocado, krill, fish, sea buckthorn, flax and coconut oil. It changes no IDs, names, rankings, aliases or associations; it keeps the total of 1,584 entries and the matching fingerprint. For this reclassification alone, the associations, fragments or embeddings are not rebuilt.

Migration `020_reclassify_remaining_requested_oils.sql` moves another 13 existing products from `suplimente` to `uleiuri`: argan oil, okra - seeds, apricot - kernels, cucumber - seeds, cherry - kernels, black currant - seeds, pistachio, macadamia, rosehip, neem, papaya - seeds, tamanu and rice bran. It keeps all the other data, including the rankings of 0, and does not require rebuilding the associations, fragments or embeddings. Together with 018 and 019, the `uleiuri` category contains 21 products; the catalog total stays 1,584. Each migration explicitly checks the identities and the source category and refuses any deviation.

Migration `021_reclassify_probiotic_products.sql` moves `Biogaia Prodendis`, `Biothin Probiotic`, `Digestive Advantage` and `Mood Probiotic` to the category `fibre, probiotice, prebiotice`, keeping the IDs, names, rankings and associations. It does not require rebuilding the associations or embeddings.

Migration `022_add_sunflower_and_pumpkin_oils.sql` adds only `ulei de floarea-soarelui` and `ulei de dovleac`, with English names `sunflower oil` and `pumpkin seed oil`, in the `uleiuri` category. Both have SQL NULL family/latin, a new identity ID and an initial ranking of 0. No evening primrose oil or aliases for it are added. The audit checks the Romanian, English and Latin names and the aliases to refuse duplicates. The seed total becomes **1,586** entries, of which **23 are oils**. Being new products, after 022 `--rebuild-herbs-only` is run separately, following the procedure for 017 below: only associations/rankings from the existing fragments, without rebuilding the documents or embeddings. Applying the migrations and rebuilding the associations are not part of the local code changes.

**Applying 017 is done separately from the implementation.** Prepare the compatible image and a backup verified by restoration; first save the complete fingerprints and xmin for `documents`/`chunks`, the catalog, associations and metadata. Briefly stop the application, explicitly apply the migration and then run only the rebuild of the associations:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m scripts.migrate_database
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --rebuild-herbs-only
```

This mode requires an existing and compatible index, does not scan the corpus, does not fragment and does not load the embedding model. It publishes the associations and the ranking differentially in the same transaction and updates exclusively the five `herbs_benefits_*` keys, using the existing generation. It checks the previous catalog fingerprint: it allows additions with new IDs after those already indexed; modifying/deleting old names or any change to the old pairs/rankings stops publishing. `--rebuild-herbs` is still the general flow and can synchronize modified documents; do not use it for this application.

Compare the fingerprints after the operation: the documents/chunks (including xmin), embeddings, generation and base metadata must be identical. Start the compatible application only after these checks; verify `/healthz`, `/readyz` and the tops. If the rebuild of the associations fails after the migration commit, fix the operation or restore the backup before starting. **Do not run the full reindex.**

In plant requests, the full name or full alias takes priority. If it does not exist, the beginning of a Romanian name, by whole words, offers the candidate species: “plop” (poplar) asks to choose between plop alb (white poplar), plop negru (black poplar), plop tremurător (aspen) and plop tremurător american (American aspen). Romanian inflections and wordings with plant parts are also accepted, such as “muguri de plop” (poplar buds) or “mugurii de plop” (the poplar buds). After the choice, the result includes only the selected species. This partial matching does not apply to mentions in the corpus or to citations in reports.

`build_hybrid_index.py` automatically rebuilds the `herbs_benefits` associations and the `herbs.ranking` ranking. An association means that the fragment's title names the condition (`primary_medical_conditions`), and the text mentions the plant or an alias. Negative mentions and contraindications are included: the association does not prove a therapeutic benefit.

The associations are published in the same transaction as the index. Extending the plants/products catalog or changing the aliases rebuilds the associations without recomputing the embeddings for unchanged documents. For an explicit rebuild or audit:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --rebuild-herbs
.\.venv\Scripts\python.exe -m scripts.audit_herbs
```

Additions and corrections to the catalogs are made through new SQL migrations in `src/backend/migrations/`, keeping the existing IDs. A missing or invalid catalog and unsynchronized associations block the plant results with an explicit error (`503`).

### Merging fibers, probiotics and prebiotics into supplements

The append-only migration `024_merge_fibre_probiotics_into_supplements.sql` moves all the entries
from the old group into `suplimente` and removes the old value from the category
constraints/index. After 024, the catalog had **13 categories**. On the complete seed there are 11 moved entries,
61 supplements and 1,586 entries in total. The IDs, names, aliases, family, species,
associations and historical scores are kept. The references above to the categories
of migrations 014–021 describe the historical stages, replaced at this point by migration 024.

“Top 100 probiotics”, “Top 100 prebiotics”, “Top 100 fibers” and the old
full name now ask for the `suplimente` top, without additional AI classification for the
explicit commands. The number and the rules of the strictly positive top stay the same.

Applying to the active database is done separately, after a backup and a check of the pending versions;
the usual migration command applies all the remaining migrations, including 023 if missing.
Rebuilding the co-occurrences, fragments or embeddings is not necessary. The catalog fingerprint
changes: an already published positive ranking requires a new preparation/publication, reusing
the unaffected cache. The application is not started with the new definition over the old unmigrated catalog.

### Removing medicines and merging bee products

The append-only migration `026_remove_medicines_and_merge_bee_products.sql` removes aspirin
(ID 1212) from the catalog, together with its aliases, associations and ranking evidence through
the foreign keys with cascading delete. It checks the identity before deleting and refuses
other unexpected medicines. It moves all bee products to `suplimente`: on the complete
seed, propolis, honey, pollen, bee bread and royal jelly. These products keep their
IDs, names, aliases, associations and scores.

The current catalog has **11 categories**, **1,585 entries** and **66 supplements** on the complete
seed. The SQL constraints forbid the removed categories. The menu keeps positions 1–8,
then continues with `9. aminoacizi`, `10. vitamine`, `11. minerale`. The requests “Top N bee
products” select `suplimente`; “Top N medicines” asks for a valid category to be chosen.
The classifier's JSON schema and the prompt use the same list of 11 categories.

Applying to the active database remains a separate step, together with the new version of the application.
The documents, fragments or embeddings are not rebuilt. Removing aspirin changes the matching
fingerprint: the associations are resynchronized in a controlled way with `--rebuild-herbs-only`, then the positive
tops are prepared and published again, reusing the compatible cache. The migration alone
does not publish a new positive ranking.

## Rankings with positive recommendations

### Recognizing essential oils

Migration `027_essential_oil_source_aliases.sql` adds 183 aliases for the mixed
Romanian/English forms in the sources, such as `ulei esential de peppermint`, using the full
English name of the existing product. It creates no new products and assigns no generic
name to all species, variants or chemotypes. The aliases are in `en_alt`,
not in the regional names displayed in the top.

In `Uleiuri esentiale.md`, the 55 lists confirmed by the operator as recommendations
are explicitly labeled `Uleiuri recomandate` (recommended oils) and have one product per line. The 309
mentions and the titles are kept. The rules recognize explicit list introductions
for oils, without turning a simple mention or a disease title into a recommendation.
Sources without recognized primary conditions and unidentified names stay outside the
score. At the next indexing run by the operator, the migration is applied, the changed
document is updated and the new run is prepared/published; the previous run is not modified.

`herbs_benefits` and `herbs.ranking` keep the historical co-occurrences. The tops separately read
`herb_positive_rankings.ranking`: the number of distinct **primary** conditions with at least one
positive recommendation and no negative mention. Positive + negative, including in different
documents, means `mixed` and a score of zero for the pair. `unclear` adds no points and does not
cancel an explicit positive evidence item. Repetitions do not multiply the score.

When the ranking is prepared, a unique main Romanian name takes priority over
the exclusively regional aliases of other products. For example, `par` by default identifies
`Pyrus communis` (pear), not the service tree (`Cormus domestica`), which has the same regional alias.
An explicit name in parentheses or in the local title can however indicate the regional species;
contradictory hints and collisions between main names remain ambiguous.
For the homonym `par` (which also means “hair” and, as a verb form, “I seem”), the lack of an explicit botanical context keeps the classification `unclear`,
so as not to attribute to the tree mentions about body hair or the verb “a părea” (“to seem”).
Identifying the product does not automatically declare it useful: the recommendation and the condition must
still be classified from the sources. Changing the rules requires a new preparation and
publication at the reindexing started by the operator; the active scores are not rewritten directly.
In the interface, `Pyrus communis` is displayed as “Păr” (pear), including in the tops and in the product page;
the name `par` and its ID stay unchanged in the database.

The additive migration `023_positive_herb_rankings.sql` creates runs, evidence with positions in the text,
pairs, scores and cache. It classifies and activates nothing. **Applying it to the active database
requires separate authorization**, a backup verified by restoration and the evaluation described below.
The application does not apply migrations at startup.

After the explicit application of the migration in a prepared environment, the usual command also updates
the tops at the end by default:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index
```

After the indexing transaction ends, the CLI sequentially runs the analysis, the preparation of a
new run and its atomic publication. The same flow runs after `--rebuild-herbs` or
`--rebuild-herbs-only`. The separate tops options are not needed for the complete flow.
`herb_positive_runs` receives the new run; `herb_positive_evidence`, `herb_positive_pairs`
and `herb_positive_rankings` are populated for it. `herb_positive_cache` reuses
the compatible decisions and saves the new validated decisions. The tables are not emptied and
the history of runs is kept. Even when the index does not change, the command creates a
new run, reusing the cache. No additional migration is needed.

The additive migration `037_herb_condition_scores.sql` creates `herb_condition_score_runs` (the “scores computed” marker) and `herb_condition_scores` (L1, L2, L3 per product and condition for the `positive` pairs). The scores are recomputed automatically after each publication of the positive ranking, without AI or embeddings; for a language's active run, without reindexing:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --rebuild-condition-scores --language ro
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --rebuild-condition-scores --language en
```

Until the migration is applied and the scores computed, the per-condition tops respond with `INDEX_HERBS_UNAVAILABLE`, without falling back to the old order.

In native execution on Windows, the CLI translates the Ollama address `host.docker.internal`
inherited from the Docker configuration to `127.0.0.1`, keeping the protocol, port and path.
In the container the Docker address stays unchanged; an explicitly configured
local address is also kept. There is no retry or change of model/provider.

`--skip-positive-ranking` explicitly disables this stage. An indexing failure does not
launch the classification; a later failure in preparing or publishing the tops returns
exit code 1, without activating partial results. The already published index is not rolled back.

For separate operations, the explicit modes remain available:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --analyze-positive-ranking
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --prepare-positive-ranking
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --prepare-positive-ranking --resume-positive-ranking RUN_ID
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --publish-positive-ranking RUN_ID
```

The modes are mutually exclusive with rebuilding the associations. The analysis does not call Ollama and
does not write: it reports the units, the rule-based decisions, the ambiguous cases, the cache hits and the computed
batches. The digest used for the cache analysis is that of the last preparation with the same
configuration, if one exists; it is marked unverified. The preparation checks the installed model through
`/api/tags`, before and after processing, and publishes only an inactive `ready` run. The model
is not downloaded automatically. Publishing rechecks the model digest, the input, the coverage, the aggregates and the pointer
observed at preparation, under lock, then activates in a single commit. A concurrent publication
cannot be overwritten by an old run. Repeating the publication of the same run is idempotent.

The rules work on the **indexed** text, without modifying the fragments or embeddings.
The units are separated at the boundaries of paragraphs, list items and table rows,
with the relevant headings. Paragraphs keep the context between sentences, including indirect
references to products. These units are used only for the local rules. The unresolved
cases are grouped by indexed fragment and product–condition pair; Ollama receives
the whole `chunks.text`, with all the paragraphs and headings of that fragment. Mentions and
quotations are reported against the complete fragment, including in the persisted evidence.
`cache_semantics=6` separates the decisions obtained with the whole fragment and the current schema from
the decisions saved under the earlier protocols.
A fragment that exceeds the technical budgets explicitly stops the preparation, without truncation.
Each indexed fragment reaches Ollama in a single `units[].text` field, with the whole
`chunks.text` exactly, without splitting, paragraph selection or truncation. The short delimitations
used for the persisted evidence are computed locally after the answer; they do not appear in the payload.
List introductions and table headers are taken only from the indexed text;
columns without an available header receive no assumed meaning. A simple disease title
does not justify a positive classification. The v3 rules handle explicit lists and clear grammatical
collisions of aliases, alcoholic vehicles, ingredients added only for
taste and some strictly nutritional descriptions. Fully interpreted explicit prohibitions
(`interzis` “prohibited”, `contraindicat`, `contraindicată`, `contraindicate` “contraindicated”, `nu este permis a se consuma` “must not be consumed”)
locally receive the label `caution` for the named product and the verified primary condition,
without an AI request for a unit resolved in this way. Explicit negative lists
are also recognized. Negations of the prohibition, secondary conditions, dose limits and incomplete
wordings stay with the AI. A certain prohibition from a complex passage is kept separately
and combined with the model's/cache's answer; it does not remove the evaluation of the other mentions.
Only in the product matcher, the unambiguous alias `rosie` (tomato) also covers the explicit forms
`rosii`, `rosiile`, `rosia`, `rosiei`, `rosiilor`, keeping the catalog ID; the existing
aliases take priority, and color adjectives do not identify the vegetable. The OCR header
of a table is inherited only from the
indexed text preceding the same section; a new section interrupts inheritance. The positive
local classification checks the condition domain, not just the existence of an instruction. Uncertain
cases keep the whole context for the AI.
The v4 rules remove the direct classification `ingredient_quantity_only_v3`: an enumeration of
ingredients or quantities continues through the other rules and, if these do not decide,
is evaluated by the local model. It does not automatically become a positive recommendation. Changing the rules
requires a new preparation/publication of the tops, but allows reusing the model's decisions
for compatible text, context, prompt and model. Changing the prompt changes the model's cache
key; the already published ranking is not modified automatically.
The classification prompts allow establishing the condition from the section title, without repeating the
disease for each ingredient or instruction. Administration alone is not a
caution; `caution` requires an effective restriction for the evaluated pair.
The matcher uses the existing names and aliases, with no automatically deduced oil aliases.
The local context limits the candidate conditions; warnings about other conditions,
exceptions and uncertain relationships go to the local classifier.

Common names that indicate several catalog identities and bibliography mentions
stay unclear and add no points. The classifier receives each whole fragment in a
single `units[].text` field, without segments. The product–condition decisions do not require citation IDs;
the separate `warnings` component uses the reference catalog described above.
The JSON schema enforces all
the relationship identifiers and only three factual answers: `local_condition`,
`recommendation`, `prohibition`. The positions of the mentions and the full text remain in the local source;
the validator locally finds the evidence for persistence after the answer.
Each candidate includes the canonical name in `condition` and all the synonyms from the catalog
in `condition_synonyms`, in their catalog order, without limiting the list. The synonyms
are equivalent names of the target and are included both in the request budget and in the
cache key; changing the list requires re-evaluating the model's decision.
Repeated mentions of the same product–condition
pair within a unit receive a single evaluation, then distributed to all the original
mentions. Aggregation across units remains separate; no mention is
omitted after a contraindication is found.
Certain local warnings are combined with the model's decision after evaluating all the
mentions, including when the answer comes from the cache. Consulting a doctor before
using a product imposes caution only when the same statement explicitly names the
product and the candidate condition; negations and competing conditions stay with the AI.

Protocol v8 requires three facts for each relationship: `local_condition`, `recommendation` and
`prohibition`. Ollama receives the whole fragment in a single field, and the answer does not
contain references to quotations. The code checks the local name through the full catalog (including
synonyms and inflections, without fuzzy matching), finds all its occurrences in the text and confirms the
candidate's mention in the source. Synonyms made of an alphabetic abbreviation written in
capitals are checked separately, keeping the capitals: the Romanian preposition “pe” (“on”) does not identify the synonym
“PE”. Full names continue to be recognized without case distinction.
A local title or introduction can establish the condition
even when the model omits the name. A name that identifies another condition is rejected. Markdown
headings, short clinical titles and explicit wordings like “În tratarea X” (“In the treatment of X”) delimit the
context; clinical titles in capitals preceded by one or two residual OCR
words are also recognized. A foreign context produces `unclear`. The recommendation takes priority over the prohibition
for the same relationship in the same fragment. The final labels remain `unclear`, `positive`,
`caution`; `mixed` is kept only internally for contradictions between distinct fragments.
`cache_semantics=6` separates the decisions validated under this protocol from the earlier ones.
The prompt allows recommending a plant as an ingredient indicated in a therapeutic recipe.
A botanical enumeration of the species in a natural material does not automatically transfer the material's
indications to each species.
The v6 rules recognize as descriptive the enumerations of plants found in a habitat,
in the absence of a therapeutic statement in the same sentence; recipes and lists administered
for treatment continue through the existing rules or the model.
Lists of alternatives take over the indication of the treatment they continue. The prompt asks for
tracking topic changes in OCR fragments with several sections; the first title
does not automatically establish the indication of all the products in the fragment.
Explicit lists of recommended products, with unambiguous identity and a confirmed local
condition, are kept as positive evidence even when the model omits the recommendation. The local
evidence is combined with the model's raw decision, which is kept separately in the cache.
The classification prompt and the transport contract are separate Markdown documents, written
in Romanian without diacritics. The first establishes the decision rules and the binding of the local condition;
the second defines the JSON fields and the passing of the whole fragment. The
product–condition decisions do not use citation IDs; the safety references are independent.
The semantic identity includes the text, the full context passed, the name, the grouped mentions,
the classification policy and the model digest. The versions of the rules and of the transport are
separate: a changed transport does not invalidate the same semantic decisions. The old cache
is kept, without artificially declaring compatibility with the new policy.
The run profile also includes the fingerprint of the rules implementation; a change to them
requires a new compatible generation. The cache of the model's raw decisions stays separate
from this fingerprint, and the current rules are reapplied before the final aggregation.
The profile also checks the policy for extracting catalog metadata. A complete and
unambiguous alias of the condition can verify the title; a partial match is not enough.
The per-unit analyses keep separately the product's role in the table, the explicit administration
and the restrictions. A collective warning for supplements is tied to the corresponding
categories and to the named condition, then combined with the AI result. Recognized
dose limits do not automatically become contraindications for the condition.
Batch construction serializes each unit once and binary-searches the
largest prefix that respects all the budgets, using the real complete envelope.

Batches can group short complete fragments for the same primary condition. Long
fragments, tables, multiple conditions and complex exceptions are processed separately. In
ordinary batches there can be at most six indexed fragments. Each fragment appears once,
whole, in `units[].text`, regardless of the number of relationships. A long fragment is sent
whole, alone in the request. The instructions, the context and the schema fall within the configurable
ceiling of 100,000 characters for the complete request. At most 20 distinct relationships are kept.
The prompts are frozen and rechecked before finalization. Publishing checks the compatible
profile again.

| Variable | Default | Role |
|---|---|---|
| `HERB_ASSOCIATION_AI_BASE` | `CONDITION_AI_LOCAL_BASE`, otherwise `http://localhost:11434/v1` | Localhost or the Docker host only; Compose uses `host.docker.internal` by default. |
| `HERB_ASSOCIATION_AI_MODEL` | `qwen3.5:9b` | Independent of the conversational classification and the report model. |
| `HERB_ASSOCIATION_AI_MAX_UNITS` / `HERB_ASSOCIATION_AI_MAX_PAIRS` | `6` / `20` | At most six whole fragments for ordinary batches; fragments that are too large are sent in isolation. At most 20 distinct relationships per request, regardless of repetitions. |
| `HERB_ASSOCIATION_AI_MAX_PASSAGE_CHARS` | `1000` | Threshold for grouping simple fragments and the limit of the short evidence saved locally; it does not split the text sent to Ollama. |
| `HERB_ASSOCIATION_AI_MAX_INPUT_CHARS` | `100000` | Technical ceiling for the whole serialized request, including the prompt, the context and the schema. Exceeding it stops the preparation; it does not shorten the fragment. |
| `HERB_ASSOCIATION_AI_CONTEXT_TOKENS` / `HERB_ASSOCIATION_AI_MAX_OUTPUT_TOKENS` | `32768` / `2048` | Context and answer reserve. |
| `HERB_SAFETY_AI_CONTEXT_TOKENS` | `65536` | Window for the AI knowledge request of a single product; independent of the classification context. |
| `HERB_SAFETY_AI_MAX_OUTPUT_TOKENS` | `40000` | Output ceiling for all the short messages of a product or of a batch in the bilingual extension. |
| `HERB_SAFETY_AI_MAX_REQUESTS` | `10000` | Ceiling of attempts per generation, including retries. One request for each product without a cache. |
| `HERB_SAFETY_BUILD_TIMEOUT_SECONDS` | `86400` | Deadline of the safety preparation; the first population can process the whole catalog. |
| `HERB_SAFETY_EXTENSION_PRODUCTS` | empty (disabled) | The scope of the bilingual extension: empty, a CSV list of exact Latin names, `first:N` or `all`. |
| `HERB_CONDITION_TOP_FORMULA` | `2*L1+L2+100*L3` | The score of the “products for a condition” tops. Only numbers, `L1`, `L2`, `L3`, `+ - * /` and parentheses; validated at startup (no `eval`, defined for any values ≥ 0). Changing it requires restarting the application, not reindexing. |
| `HERB_SAFETY_GENERATION_MODEL` | `ministral-3:8b` | The local Ollama model of the generation stage of the safety extension; empty disables the local stage and generates only with DeepSeek. On 10 known products, ministral gave the most specific messages among the local models tested. The stage identifier in the cache remains `qwen`, for historical reasons. |
| `HERB_SAFETY_DEDUP_MODEL` | `gemma4:12b` | The local Ollama model that groups equivalent messages. Compared on St John's wort with qwen3.5:9b and qwen3.5:4b: it found 3 of 3 real pairs. |
| `HERB_SAFETY_MINISTRAL_BATCH_SIZE` / `HERB_SAFETY_DEEPSEEK_BATCH_SIZE` | `10` / `100` | Products per request to the local generation model (and per dedup request), respectively to DeepSeek. Validated against the output ceilings only while the extension is active. |
| `HERB_SAFETY_DEEPSEEK_MAX_OUTPUT_TOKENS` | `160000` | Output ceiling of a DeepSeek batch, reasoning included. |
| `HERB_ASSOCIATION_AI_TIMEOUT_SECONDS` / `HERB_ASSOCIATION_BUILD_TIMEOUT_SECONDS` | `900` / `7200` | Budget per AI batch and I/O wait limit, respectively the deadline per command. The command's remaining time limits each batch. |
| `HERB_ASSOCIATION_AI_KEEP_ALIVE_SECONDS` | `3600` | For reindexing only: keeps the Ollama model for up to 60 minutes of inactivity between requests, including those for safety. `0` unloads after each request; `-1` keeps it indefinitely between requests. At the end of the flow, the CLI requests immediate unloading anyway. |
| `HERB_ASSOCIATION_AI_MAX_REQUESTS` | `1000` | Ceiling of attempts for RUN_ID, including on resume. |

All the variables are validated by `Settings` and propagated through Compose. A
single in-flight request, zero temperature and JSON with a strict schema are used, with no retry/fallback.
The classifications and the separate product-knowledge requests use native Ollama
streaming in the same POST. The chunks are reassembled internally; JSON validation and saving
to the cache happen after the final marker is received. An interrupted stream or a timeout does not
save an incomplete result. The 900-second budget is checked between chunks
and when leaving the batch, together with the command's deadline; I/O keeps its wait limit.

Each request produces on stdout JSON events with `stage=herb_ai_batch`,
`event=started` and `event=completed`/`failed`. They include:

- The run, the type (`associations` or `product_safety`), the batch number, the model,
  the context, the output limit and the configured/effective time limits.
- The number of fragments/targets and the lengths of the source, payload and system prompt.
- `herb_id` and `safety_source=model_knowledge` for the new per-product analysis;
  `warning_items_max_total` is a historical field of fragment-based extraction, zero here.
- The batch duration, the time to the first chunk and first text, the last activity,
  the number of events and the number of characters received, without their content.
- The Ollama times for loading, prompt processing and generation, the input tokens,
  the cached prompt tokens, the generated tokens and the generation speed.
- The error type and a controlled technical reason, without raw provider messages.

Missing native values, including when the stream is interrupted, are `null`. The native
durations are converted from nanoseconds to milliseconds; `duration_ms` measures the complete batch,
including validation/saving. Batch events and heartbeats are serialized on
distinct JSON lines. Streaming and the metrics keep the batches, the number of requests and the
fingerprints of the semantic caches; no requests are added for diagnostics or automatic retry.

As adjusted on October 23, processing and the operator controller do not check
the GPU temperature, do not stop at 82°C and introduce no thermal or preventive pauses.
The GPU frequency is managed by the user.
The exact set of candidates and the exact quotations are checked; incomplete results are rejected.
Valid quotations prove provenance, not semantic correctness. The number of characters does not
measure tokens. The request ceiling limits memory, and Ollama checks the real token window
with `truncate=false` and `shift=false`; exceeding it is an explicit error, with no
retry using a shortened fragment. Calibration on the real model remains necessary.

The cache keeps only validated labels and relative positions, including `unclear`, without
full text or raw answers. The key includes the passage/context, the candidate and
its name, the prompt policy, the semantic configuration and the model digest. The rules version
and the transport form do not change the key of a raw decision on their own. Timeouts
do not change the key. Successful batches are saved in short transactions, without DB connections or
locks held during inference. An explicit resume recovers only the gaps;
the same input and digest produce zero new classification requests. After a changed input,
a new run is started that can reuse the unaffected cache entries.

The tops do not call the classifier and work with Ollama stopped if the published run
is valid. They return up to X entries with a strictly positive score; they do not pad with zeros.
A category with no results is a valid result. The lack of a valid run gives 503
`POSITIVE_RANKING_NOT_READY`, and a change of input/configuration gives
`POSITIVE_RANKING_STALE`; there is no fallback to the historical score. The base index codes
remain applicable. The normal indexing command automatically updates the tops at the end,
unless `--skip-positive-ranking` is used. Until the new run is published, an old
incompatible top stays unavailable; no partial or historical results are displayed.
The run fingerprint includes content hashes (`text` and the fragments' embedding, the rows
of `documents`), not `xmin`; thus, a `pg_restore` restoration of a backup (which rewrites all
rows) does not invalidate the published ranking, but any real change to the content invalidates it.

The offline evaluation uses representative batches, including fruits/cereals, and an independent
sample of 80 units and at least 100 relationships. For the activation of October 23,
the user accepted the measured precision of 89.33% on the samples already reviewed and
the existing speedup, with no additional minimum speed threshold. This does not certify an
independent evaluation of the final profile or a 2× speedup. The precision and speed
evaluations are not executed automatically at each indexing run; automatic publishing checks
the integrity, the complete coverage and the compatibility of the sources, profile and model.
For speed comparisons, use two runs without cache for each variant,
on the same snapshot and model; exclude any pauses from `classification_seconds`.
Keep the previous run and compare the hashes/xmin of the index, co-occurrences and
historical scores in evaluations that do not modify the index.
Returning to a previous pointer requires an explicit operation, with the same manifest still
valid; an old run cannot be republished over a new one through the usual command.
Classification progress displays, about every 60 seconds, only IDs and aggregates, duration,
rate and the fields `elapsed(hh:mm:ss)` and `ETA(hh:mm:ss)`, for example
`"elapsed(hh:mm:ss)": "00:10:00"` and `"ETA(hh:mm:ss)": "02:10:05"`.
Until the remaining time can be estimated, `ETA(hh:mm:ss)` is `null`. Transitions and completion
are reported immediately.
`ai_requests_sent_total` shows the number of classification requests launched in the current run,
including those that fail; `requests` keeps the same counter. Results from the cache,
local rules and model digest checks are not classification requests.
`batches` is the planned number of requests. After publishing, the line
`"stage": "positive_ranking_summary"` repeats the total sent in the preparation stage.
On a resume, the displayed counter includes only the new requests of that run; the cumulative limit
for `RUN_ID` continues to be checked separately in the database.

## 📦 Hybrid index schema (Postgres)

The main tables of the index, the catalog and the migrations are:

| Table | Content |
|---|---|
| `documents` | One row per source file: path, SHA-256, encoding, line count; the category (folder) is a column generated from the path. Also used to decide which files are skipped at the next synchronization. |
| `medical_conditions` | `id`, `name` (the canonical Romanian name) and `en` (the English equivalent, filled in through SQL); the condition identity is shared by both languages. |
| `medical_condition_synonyms` | Only `id`, `medical_condition_id` and `synonym`: the synonyms tied to the condition by FK. |
| `herbs` | Physical columns `id, category, family, latin, ro, en, ranking`; numeric identity ID. Plants keep lowercase names/families and a unique Latin name; products have `latin = NULL` and keep the capitalization requested for `ro`/`en`. The uniqueness of the product name (`lower(btrim(ro))`) is shared by all ten product categories, including `seminte`. Botanical entries use `plante medicinale`, `fructe`, `legume` or `cereale`; `family` keeps the original botanical family. For products, the technical category is only in `category`, and `family` is SQL NULL. `ranking` counts the distinct associated conditions from the fragment titles. Folk names can be shared by several species. |
| `herb_aliases` | Columns `id, herb_id, name, kind`; lowercase aliases, FK with cascading delete, types `ro_regional`, `latin_synonyms`, `en_alt`. |
| `herbs_benefits` | Associations derived from co-occurrence in the corpus: `id, herb_id, medical_condition_id, language`; unique pair per language, FK with cascading delete and individual indexes. Published atomically at the end of reindexing. |
| `schema_migrations` | The ledger of the SQL migrations applied once. |
| `owner_sessions` | Persistent owner authorizations: hashes and technical metadata; no conversations or reports. |
| `chunks` | One row per fragment, with `language` (`ro`/`en`, RO for the existing rows): text, line range, the path of the headings (`heading`), the category generated from the path (`category_id`, used by source filtering), `business_category` (`R1`/`R2`/`D1`), `primary_medical_conditions`, `secondary_medical_conditions`, the semantic vector (`embedding vector(1024)`) and the lexical column (`text_search tsvector`). |
| `sync_metadata` | The model, the dimension, the passage profile, the text version, the SHA-256 fingerprint of the dictionary, the index generation, the synchronization date and the five `herbs_benefits_*` markers. |

If the index profile and the catalog fingerprint are unchanged, a document with the same SHA-256 is skipped at synchronization; a new or modified document replaces its fragments in a single transaction.

Fragmentation (`src/backend/ai/fragmenter.py`) reads the conditions from `medical_conditions` and the synonyms from `medical_condition_synonyms`, in insertion ID order. Python adds the canonical name to the list of matching terms, without duplicating it in the synonyms table. Then it applies in turn:

| Category | Criterion |
|---|---|
| **R1** | The title of a Markdown chapter names a condition → the title and its whole remaining free subtree (subchapters with their own condition become separate fragments). |
| **R2** | The own text of a remaining chapter (up to the next title) mentions a condition → the title and that text. |
| **D1** | The rest of the text (including documents without titles) → pieces of ~1800 characters (1500–2100), cut at the end of a paragraph or sentence, with an overlap of at most 270 characters. |

Conditions are searched as whole words, without diacritics and capitals, with tolerance for Romanian endings (`gripa`/`gripei`). File and folder names are not compared with the conditions. R1 and R2 fragments receive `primary_medical_conditions` (the conditions in the title) and `secondary_medical_conditions` (the conditions in the text); D1 has no conditions. R1 and R2 have no length limit. A condition that is primary is removed from `secondary_medical_conditions` of the same fragment: the idempotent script `src/backend/index_sql/001_remove_primary_from_secondary_conditions.sql` runs on every indexing, in the publication transaction, and migration `040_remove_primary_from_secondary_conditions.sql` cleans the rows indexed earlier without reindexing (afterwards run `--rebuild-condition-scores` for each language so that the per-condition tops recompute L2).

At search time, each fragment receives the score `4·P1 + 2·P2 + L + V` (maximum 8, with all signals ticked): P1 = the searched condition is in `primary_medical_conditions`, P2 = it is in `secondary_medical_conditions`, L = the fraction of expressions (separated by commas) found in the fragment, V = the semantic similarity rescaled between the median and the maximum of the search. The patient can untick signals in the “Sources and search options” panel, and the formula adapts (for example `L + V` or only `2·P1 + P2`). The score is not stored in the DB; details are in [fragment-search-and-scoring.xmind](architecture/fragment-search-and-scoring.xmind).

For embeddings, a fragment longer than 1400 characters is split into windows that overlap by 240, and their vectors are averaged (the values, vector dimension and text prefixes of each model are in its profile in `ai/embedding_model.py`). Diacritics are preserved through Unicode NFC normalization.

## 🐳 Running with Docker Compose

Before building/starting, `medicina-naturista-documente/data/documents/`, `model_cache/` (with the embedding model already downloaded: the container runs offline) and the local `.env` file with the key of the chosen AI provider (`X_API_KEY`, `DEEPSEEK_API_KEY`, `HF_TOKEN` or `OLLAMA_API_KEY`), `POSTGRES_PASSWORD` and `OWNER_KEY` must exist. The stack has two services: `db` and `app`. The `db` service (Postgres 16 + `pgvector`, with `shared_buffers=512MB`) is exposed only on `127.0.0.1:5432` (`DB_HOST_PORT`), so the index is synchronized from the host with `python src/scripts/build_hybrid_index.py` (with `PYTHONPATH=src` and a `DATABASE_URL` pointing to `127.0.0.1` with the password `POSTGRES_PASSWORD`).

**Ollama runs separately, on the host (Windows), and must be started before the application.** The `app` container accesses it through `http://host.docker.internal:11434/v1`, both for message classification and condition identification (`CONDITION_AI_LOCAL_BASE`) and for reports with `ollama-gemma4:12b` (`OLLAMA_API_BASE`). Download the report model with `ollama pull gemma4:12b` and the model chosen in `MEDICAL_CONDITION_AI_LOCAL_MODEL` (default `gemma3:1b`). The models are managed by the Ollama installation on the host.

For Ollama reports, the client derives `/api/chat` from `OLLAMA_API_BASE` by removing the `/v1` suffix. It uses native JSON format, `truncate=false` and `shift=false`: the input is not shortened automatically and no portions are removed from the context in order to continue generation. Exceeding the context is reported as `AI_CONTEXT_LIMIT_EXCEEDED`, with the message to select fewer fragments or raise the minimum score. R1 8B has an explicit per-request context; for the other models, if there is no override, the Ollama server configuration is kept. Batches use conservative input token budgets; these do not replace the real context checked by Ollama. The input, the instructions and the output must fit together in the context. Message classification and condition identification also use the native `/api/chat` client, with `think=false`, to send the retention duration in the same request.

The application sends `keep_alive=60` for each Ollama request: the model is released after
60 seconds of inactivity, without preloading at application startup. Reindexing separately uses
`keep_alive=3600`. At the end of reindexing or of an explicit ranking/safety preparation,
`build_hybrid_index.py` sends a control request with no prompt, with `keep_alive=0`, for the configured
indexing model. Unloading is also requested on error or Ctrl+C; a forced stop of the
process may skip the cleanup. The analysis, separate publishing, the caution projection without AI and
`--skip-positive-ranking` do not unload the model. The `index_model_release` event confirms
`released` only after Ollama's answer; on failure it displays `warning` without changing the result of the
indexing. The control request generates no text and does not count in the number of inference requests.

For `gemma4:12b` with the maximum context of 262,144 tokens, the performance configuration measured on the local GPU uses the following variables **on Windows**, in PowerShell:

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION", "1", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_KV_CACHE_TYPE", "q8_0", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL", "2", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH", "262144", "User")
```

Fully close Ollama from the notification area and start it again from Start. Check the effective values and `offloaded …/49` in the log `%LOCALAPPDATA%\Ollama\server.log`; the desktop application may have its own settings. These variables configure the Ollama server, not the Python client: adding them to `.env` or to the environment of the Compose `app` service does not change the Ollama on the host.

`q4_0` reduces the precision of the KV cache; the speed measurement does not validate the quality of reports on long inputs. For the batches to be actually processed simultaneously, the Ollama server must allow at least the number of requests per model configured through `REPORT_BATCH_WORKERS` (default `OLLAMA_NUM_PARALLEL>=2`). If it allows only one, the requests sent by the application may be processed in succession. Simultaneous contexts require more memory; speedup is not guaranteed and the server configuration is not changed automatically. The application separately keeps `MAX_CONCURRENT_GENERATIONS=1`. The historical local results and the limits of the measurement are in the [Ollama investigation](aiPlans/2026-10-15-investigare-performanta-ollama.md).

```dotenv
CONDITION_AI_LOCAL_BASE=http://host.docker.internal:11434/v1
MEDICAL_CONDITION_AI_LOCAL_MODEL=gemma4:12b
CONDITION_AI_TIMEOUT_SECONDS=30
MESSAGE_CLASSIFICATION_TIMEOUT_SECONDS=30
```

The two timeouts in the example are 30 seconds. Local classification and identification request `reasoning.effort=none`, so that models with “thinking” use the answer budget for the final JSON.

To verify the connection from the container:

```powershell
docker compose exec -T app python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/api/version', timeout=5).read().decode())"
```

After changing the configuration in `.env`, recreate the application with `docker compose up -d --no-deps --force-recreate app`. If you are migrating from the old Ollama service, stop and remove only the old container with `docker stop medicina-ollama` and `docker rm medicina-ollama`; its volume with models can be kept for recovery. The required models must be downloaded separately in the Ollama on the host.

Synchronize the index after starting the `db` service, before using search.

```powershell
docker compose up -d --build
docker compose ps
Invoke-WebRequest http://localhost:8760/healthz
```

The application is published on the host at `127.0.0.1:8760` (`APP_HOST_PORT`; inside the container the port stays 7860, and 8760 avoids the port range reserved by Windows) and published through Tailscale Funnel, which handles HTTPS. It runs in a read-only container, without additional Linux capabilities, as a non-root user. The documents are mounted read-only, and the temporary directories use `tmpfs`. The index lives in Postgres (named volume `pg_data`), so there is no longer a need for a bind mount or for stopping the application during resynchronization.

Stopping without deleting the volumes:

```powershell
docker compose down
```

> [!WARNING]
> `docker compose down -v` deletes the named volumes declared in Compose: the Postgres index (`pg_data`). The Ollama models on the host are managed separately.

### Publishing through Tailscale Funnel

On Windows, Tailscale Funnel sends requests directly to the application's local port, without Nginx or Caddy on this path. The `/medicina` prefix allows other applications to be published later on the same hostname. Port `8760` stays bound exclusively to `127.0.0.1`.

In `.env`, set `PUBLIC_ORIGIN=https://cristiantone.taila68086.ts.net` (the exact origin of the Tailscale device) and keep `COOKIE_SECURE=true`. `PUBLIC_ROOT_PATH` stays `/medicina`, the default value in Compose. Add to `FORWARDED_ALLOW_IPS` only the address of the Docker gateway through which the host proxy's requests arrive; in this installation it is `172.20.0.1`, verified in the request log. Do not use `*` or the whole subnet: Tailscale replaces the forwarded headers, and Uvicorn must accept them only from the known proxy. The gateway addresses can change if the Docker network is recreated.

After changing `.env`, recreate only the application:

```powershell
docker compose up -d --no-deps --force-recreate app
```

With Tailscale installed and connected to the account, start Funnel from PowerShell:

```powershell
& "C:\Program Files\Tailscale\tailscale.exe" funnel --bg --set-path=/medicina http://127.0.0.1:8760
& "C:\Program Files\Tailscale\tailscale.exe" funnel status
```

On first use, follow the activation link displayed by Tailscale. The application will be available at `https://cristiantone.taila68086.ts.net/medicina/`, and the availability check at `/medicina/readyz`. The exact hostname can be found from `tailscale status --json`, the field `Self.DNSName`. For another hostname, also update `PUBLIC_ORIGIN` and the development address `DEV_BACKEND_URL`.

`--bg` keeps the Funnel configuration after a restart. For access before signing in to Windows, enable `Preferences → Run unattended` in Tailscale; Docker and the application container must be started separately. Also check the device key's expiry in the Tailscale console for continuous operation. To stop only this application's route:

```powershell
& "C:\Program Files\Tailscale\tailscale.exe" funnel --bg --set-path=/medicina http://127.0.0.1:8760 off
```

Migrating this application does not require modifying the shared Nginx proxy or stopping ngrok for the other projects. The Caddy service and configuration were removed; HTTPS is managed by Tailscale. The old access to Medicina Naturistă through ngrok is no longer the authorized origin for modifying requests after `PUBLIC_ORIGIN` was changed.

## Application language and fixed texts

The “Română / English” selector in the header changes the language of the interface and of the
following operations. The first visit uses RO; the preference is saved in `localStorage` for
new tabs. Tabs that are already open keep their language. The change is blocked while
there is an active operation in that tab and does not recreate the session or the history.

Each message, search and report keeps its original language. Actions on historical
results use that language: a report generated from an RO search stays RO even if the
interface has switched to EN, including the PDF and the email. For an EN report a new
EN search is needed. EN search does not use RO fragments when EN results are missing.

The texts are in two independent UTF-8 catalogs:
`src/backend/resources/texts.ro.toml` and `src/backend/resources/texts.en.toml`.
The RO catalog was kept unchanged when the EN language was introduced. Both have exactly the same
468 keys and the same named parameters. The `common` and `interface` sections are public;
`conversation`, `errors`, `authorization`, `report` and `email` stay on the backend.
Missing or unknown keys, incompatible parameters or HTML stop validation;
there is no fallback of the EN texts to RO.

```powershell
$env:PYTHONPATH = 'src'
.venv/Scripts/python.exe -m scripts.manage_texts
.venv/Scripts/python.exe -m scripts.manage_texts --public-json --language en
```

The HTML bootstrap passes both public catalogs before React starts.
`GET /api/texts?language=en` exposes the public EN catalog; without a language, the compatible answer
is RO. UI requests send `X-App-Language: ro|en`; navigation to authorization uses
a validated language parameter. `POST /api/language` changes the session preference without
deleting the conversation. The HTML and the public texts are `no-store`.

The backend and each worker use an isolated language context derived from the operation's
snapshot, without modifying a global AI client. The RO prompts stay in
`ai/prompts/`; the EN variants are in `ai/prompts/en/`, with the same JSON keys and
citation rules. Classification and condition identification remain exclusively local. The product
warnings are prepared at reindexing for both languages, with separate caches and active generations;
UI lookups do not initiate AI calls.

`medical_conditions.en` is populated through an SQL migration from the bilingual aliases of the
catalog, without changing the IDs and without AI translation at runtime. Products use
`herbs.en`; when there is no common EN name, the scientific name is kept. Later
additions of conditions through `scripts.condition_sql.additions_sql` must explicitly
provide `Condition.english`. Source classification and citation checking are not
medical validation of the translations or of the recommendations.

In the UI, product names use the dictionary of the operation's language: `ro_RO` for RO
and `src/scripts/dictionaires/en/en_GB.dic` / `en_GB.aff` for EN. When recognizing
EN names, plurals validated by the dictionary's nominal rules are accepted,
including in alternative names and multi-word expressions. Latin names stay
exact; prefixes and derivations that change the meaning do not extend the matches. The display
keeps ambiguous or unknown forms. The catalog caches are separate per
language; entered messages and documents are not corrected automatically by this integration.
The conditions catalog in PostgreSQL remains separate from the Hunspell spelling dictionary.

When keys/parameters change, `python -m scripts.manage_texts --generate` regenerates
only the common Python/TypeScript metadata. It does not duplicate the messages in the frontend. Compose
mounts both catalogs read-only. Activating the new code requires rebuilding the application;
later editing of only the values requires restarting the process and reloading the page.
Vite in development must be connected to a backend that includes the bilingual contract.

## ⚙️ Configuration

The `.env` file is ignored by Git. The main values recognized by the application are:

| Variable | Default | Role |
|---|---:|---|
| `X_API_KEY` | — | The xAI key (required when using the `grok-4.3` model). |
| `XAI_API_BASE` | `https://api.x.ai/v1` | The base URL of the xAI API. |
| `HF_TOKEN` | — | Hugging Face token with the permission “Make calls to Inference Providers”; required when using the `huggingface-deepseek-v4-flash` model. |
| `HF_API_BASE` | `https://router.huggingface.co/v1` | The base URL of the HF router; the client calls the `/responses` route. |
| `DEEPSEEK_API_KEY` | — | The API key from platform.deepseek.com, required when the admin chooses `deepseek-flash`. Its absence does not block Ollama reports. |
| `DEEPSEEK_API_BASE` | `https://api.deepseek.com` | The base URL of the DeepSeek API. |
| `OLLAMA_API_BASE` | `http://localhost:11434/v1` | The Ollama base; in Docker Compose `http://host.docker.internal:11434/v1`. |
| `OLLAMA_KEEP_ALIVE_SECONDS` | `60` | Retention duration after the application's last Ollama request (report, classification or identification). `0` unloads after each request. It does not change the context size and does not control reindexing. |
| `OLLAMA_API_KEY` | — | Required only when `OLLAMA_API_BASE` is not local (e.g. `https://ollama.com/v1`). |
| `OLLAMA_MAX_OUTPUT_TOKENS_BY_MODEL` | `{"ollama-deepseek-r1:8b":8192}` | JSON object with the output limit per Ollama model. Omitted keys keep the default values from the catalog (R1 8B: 8192); the other models use `REPORT_GENERATION_MAX_OUTPUT_TOKENS`. The values must be positive integers, and the output must be smaller than the context from the catalog (R1 8B: 32768). Unknown keys, external models and duplicates are rejected. It is the default value displayed in the report panel (admin only), where it can be overridden per report. |
| `MEDICAL_CONDITION_AI_LOCAL_MODEL` | `gemma3:1b` | The local Ollama model for message classification and condition identification; downloaded on the host with `ollama pull <model>`, including when the application runs in Docker. |
| `REPORT_GENERATION_MODELS` | the 9 models in the catalog order below | Ordered CSV list of the available models. The first is the default. The order in the UI is the same; rights control generation, not the visibility of the options. Empty lists, empty elements, unknown models and duplicates are rejected at startup. The choice in the UI applies only to that job. |
| `REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL` | `24000` for R1 8B, `25000` for the others; context from the catalog; effort `low` | JSON object with one entry per model: `{"tokens": …, "context": …, "effort": …}`. `tokens` (required) is the input token budget per batch; it includes the complete serialized request and a reserve of 256 tokens, with local counting estimated at 3 UTF-8 bytes per token. `context` is the model's context window: it is displayed under the chosen model in the panel and limits the output (input + output fit within it). Startup is refused if the default output of an active model leaves fewer than 1,000 input tokens; for R1 8B it must match `num_ctx` from the catalog (32768). `effort` (`low`/`medium`/`high`) is the preselected effort when the user chooses the model. `context` and `effort` are optional and have default values from the catalog/`low`. Missing/empty value → the default values; an explicit object must include every enabled model. `tokens` is also the default value displayed in the report panel (admin only), where it can be overridden per report. The value can be written over several lines in `.env`, between single quotes. |
| `REPORT_BATCH_WORKERS` | `2` | Positive integer: the maximum number of batches processed simultaneously in the active report. `1` processes in succession. It does not change the limit of a single active report. It is passed explicitly to the application through Docker Compose. The report panel (admin only) offers “No” (`1`), `2` or `3`; the default value displayed is `min(REPORT_BATCH_WORKERS, 3)`. |
| `CONDITION_AI_LOCAL_BASE` | `http://localhost:11434/v1` (direct) / `http://host.docker.internal:11434/v1` (Compose) | The Ollama address on the host, used for message classification and condition identification. |
| `CONDITION_AI_TIMEOUT_SECONDS` | `10` | Timeout for condition identification through local Ollama. |
| `MESSAGE_CLASSIFICATION_TIMEOUT_SECONDS` | `10` | Timeout for classification through local Ollama, independent of condition identification. |
| `MESSAGE_CLASSIFICATION_MAX_OUTPUT_TOKENS` | `300` | The classification JSON budget. |
| `CONDITION_AI_MAX_OUTPUT_TOKENS` | `300` | The answer limit (a small JSON) for condition identification. |
| `REPORT_GENERATION_AI_STREAM` | `false` | Requests the answer as an event stream (`stream: true`). The read timeout applies between events, so it avoids long requests being cut by a proxy (e.g. 504 after 60 s at the HF router). If the provider does not support streaming, leave `false`. |
| `REPORT_GENERATION_MAX_OUTPUT_TOKENS` | `20000` | The request's `max_output_tokens`, for all providers (for models with thinking, reasoning consumes from it). It is the default value displayed in the report panel (admin only), where it can be overridden per report. |
| `REPORT_GENERATION_READ_TIMEOUT_SECONDS` | `300` | The read timeout of the request to the AI provider. |
| `DOCUMENTS_DIR` | `medicina-naturista-documente/data/documents` | The directory of the local documents. |
| `HERB_IMAGES_DIR` | `medicina-naturista-documente/data/images` | The optional directory with the products' PNG pictures; mounted read-only in Docker. |
| `DATABASE_URL` | `postgresql:// medicina:medicina @127.0.0.1:5432/medicina` | The Postgres connection of the hybrid index (`pgvector` + `tsvector`). |
| `DATABASE_BOOTSTRAP_URL` | empty | Optional maintenance connection for creating a missing database, on the same server as `DATABASE_URL`; used only by reindexing. By default the target's credentials on the `postgres` database are used. |
| `MODEL_CACHE_DIR` | `model_cache` | The directory of the local ONNX model cache. |
| `EMBEDDING_THREADS` | `8` (at most the number of cores) | The execution threads of the embedding model (ONNX Runtime), at indexing and at search. On hybrid P/E-core processors, fewer threads are usually faster than all the cores. |
| `EMBEDDING_DEVICE` | `cpu` | The embedding model's device when **building** the index: `cpu` (FastEmbed/ONNX) or `cuda` (PyTorch fp16, only from the GPU environment `.venv-gpu`; without CUDA the build stops, it does not fall back to CPU). Questions in the application always run on CPU. |
| `SESSION_TEMP_DIR` | `var/sessions` (Windows) / `/tmp/naturist-sessions` | The directory of the sessions' temporary files. |
| `MAX_CHAT_CHARS` | `4000` | The maximum length of the user's message. |
| `MAX_REQUESTS_PER_MINUTE` | `60` | The limit of `POST`/`PUT`/`PATCH`/`DELETE` requests to `/api/`, per minute and IP; the owner login has a separate limit. |
| `SESSION_IDLE_SECONDS` | `3600` | Expiry of an inactive session. |
| `SESSION_MAX_SECONDS` | `14400` | The maximum duration of a session. |
| `MAX_ACTIVE_SESSIONS` | `100` | The maximum number of sessions in the process. |
| `NEW_SESSIONS_PER_COOKIE_MINUTE` | `5` | The number of new conversations per minute for the same browser cookie; reloading the page opens a new conversation. The local installation uses `60`, through `.env`. |
| `NEW_SESSIONS_PER_IP_MINUTE` | `10` | The number of new conversations per minute for the same IP. The local installation uses `120`, through `.env`. When exceeded, the `429` answer includes `Retry-After` with the time remaining until the quota is freed. |
| `MAX_API_BODY_BYTES` | `262144` | The maximum size of an API request body. |
| `MAX_CONCURRENT_SEARCHES` / `MAX_CONCURRENT_GENERATIONS` | `2` / `1` | Two simultaneous searches; report generation is serial (the value 1 is mandatory). |
| `MAX_QUEUED_GENERATIONS` | `20` | The maximum number of waiting reports, in addition to the running report. |
| `OPERATION_TIMEOUT_SECONDS` | `600` | The total duration accepted for an operation. |
| `DEPLOYMENT_PROFILE` | `local` | `public` validates HTTPS, secure cookies and disabling content logging; it must be passed explicitly in Compose. |
| `COOKIE_SECURE` | `false` (direct) / `true` (Compose) | Enforces sending the cookie only over HTTPS. |
| `OWNER_KEY` | _(empty)_ | A long secret key, entered in the `/owner` form and sent through `POST /api/owner/login`. Individual authorizations persist in PostgreSQL until logout; rotating the key invalidates them. The cookie is renewed with a Max-Age of 365 days on authorized activity. |
| `LOG_LEVEL` | `INFO` | The minimum log level. |
| `LOG_FRAGMENT_TEXT` | `false` (direct) / `true` (Compose) | Compatibility option; the current AI client logs only technical metadata, without the fragment text. The `public` profile requires `false`. |
| `LOG_FRAGMENT_TEXT_MAX_CHARS` | `4000` | Compatibility option; the current AI client does not log the fragment text. |
| `LOG_AI_RESPONSE_TEXT` | `false` | Compatibility option; the current AI client does not log the answer body even if it is enabled. The `public` profile requires `false`. |
| `APP_HOST_PORT` | `8760` (Docker Compose) | The host port on which Compose publishes the application. |
| `POSTGRES_PASSWORD` | — (required in Docker Compose) | The Postgres password of the `db` service; Compose builds `DATABASE_URL` for the application from it. |
| `POSTGRES_USER` / `POSTGRES_DB` | `medicina` / `medicina` (Docker Compose) | The user and database of the `db` service. |
| `DB_HOST_PORT` | `5432` (Docker Compose) | The host port (only `127.0.0.1`) on which Compose publishes Postgres. |
| `PUBLIC_ROOT_PATH` | empty (direct) / `/medicina` (Docker Compose) | The public path prefix, required when the application is exposed by a reverse proxy under `/medicina`: it goes into the PDF download link and, at the image build, becomes `PUBLIC_BASE_PATH` for the frontend. |
| `PUBLIC_ORIGIN` | empty | The exact public origin (`https://hostname`, without `/medicina`), for origin validation when TLS terminates at ngrok/proxy and the backend receives HTTP. If empty, it is compared with the ASGI request's origin. |
| `FRONTEND_DIST_DIR` | `src/frontend/dist` | The directory with the React build served as static files by FastAPI. |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Uvicorn allowlist for the IPs/CIDRs of the authorized proxies; the application does not directly interpret `X-Forwarded-For`. |

The size of the content budget (the largest value in `REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL` for the active models) influences the number of fragments displayed, the processing time and the total volume sent to the AI provider. The per-batch limit separately controls the size of each request. In environments where the logs do not have controlled access, set `LOG_FRAGMENT_TEXT=false`.

On direct startup, the application reads the values from `.env`; the default values differ where indicated. Docker Compose passes the variables listed in the `environment` section; `COOKIE_SECURE` is `false` by default on direct startup and `true` in Compose. `OWNER_KEY` is optional, but without it report generation is disabled; set a secret key and authorize the browser through the `/owner` form. The IP for limits is provided by the ASGI server; the application does not interpret `X-Forwarded-For`. In the proxy deployment, configure Uvicorn's explicit `FORWARDED_ALLOW_IPS` allowlist for the authorized proxies; the old `TRUST_PROXY` no longer grants trust to the headers.

### ✉️ Gmail OAuth2 — optional

```dotenv
GMAIL_USERNAME=your-address@gmail.com
MAIL_FROM=your-address@gmail.com
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
```

The initial authorization is done once:

```powershell
.\.venv\Scripts\python.exe src\scripts\google_oauth_setup.py
```

Only the `gmail.send` scope is requested. The token is not displayed and must not be published. If the integration is not fully configured, the report remains available in the application, and email delivery is skipped.

If Google rejects the refresh with `invalid_grant`, first check whether the valid token from `.env` was loaded into the container. For Docker, apply the current configuration with `docker compose up -d --no-deps --force-recreate app`; a simple restart does not update the container's environment variables. Recreating closes the active sessions and removes the reports from memory, so save the PDFs beforehand. If the local token is also rejected, reauthorize the account with the same script. It replaces the token in `.env`. Reauthorization does not automatically send a report.

## 🔐 Privacy and safety

- 🔒 `.env` and the model cache are ignored by Git; the index lives in Postgres, not in files in the repo.
- 🧭 each fragment stays tied to the source file and lines;
- 🧹 conversations and PDFs stay only in process memory, separated per tab; closing notified to the server, expiry or restart removes them. No medical information of the patient is written to the database;
- 🚫 xAI requests use `store=false` (for DeepSeek, Hugging Face and Ollama the parameter is not sent; their retention policies apply);
- 🩺 the answers are informative and must be medically verified before use.

## 🧪 Testing

Commands are run from the project root.

Install the development tools in the CPU environment (not in `.venv-gpu`):

```powershell
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s src/tests/unit -t src -v
.\.venv\Scripts\python.exe -m pytest src/tests/unit/ai/test_report_validation.py src/tests/unit/web/test_report_integrity.py -q
```

The unit tests use simulated dependencies and do not require Docker, PostgreSQL, `.env` or the personal corpus. The integration tests by default use an ephemeral PostgreSQL/pgvector and a synthetic corpus:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s src/tests/integration -t src -v
.\.venv\Scripts\python.exe -m pytest src/tests/integration/test_index_integrity.py -q
```

Docker must be available for integration. Alternatively, `TEST_POSTGRES_URL` can point **exclusively to a disposable test database**: the fixtures modify its schema and data. Do not use the application's database. The personal corpus and catalog tests separately require `RUN_LOCAL_CORPUS_TESTS=1`; they are not enabled in CI.

Static and frontend checks:

```powershell
.\.venv\Scripts\python.exe -m ruff check src
.\.venv\Scripts\python.exe -m ruff format --check src
.\.venv\Scripts\python.exe -m mypy
npm --prefix src/frontend ci
npm --prefix src/frontend run test
npm --prefix src/frontend run typecheck
npm --prefix src/frontend run build
```

Ruff does not rewrite files in CI. Mypy gradually checks the configuration, the contracts, the models, the conversation service, the operations budget and the content evaluator. The third-party dictionaries in `src/scripts/dictionaires` and the experimental `icd10_work` scripts are excluded from the application's formatting/linting.

### Dependencies and CI

`pyproject.toml` is the source of the declarations. The locks are generated with pip-tools, include the transitive dependencies and the distribution hashes, and keep the existing versions without an implicit upgrade:

| Environment | Runtime | Development |
|---|---|---|
| Windows, Python 3.11 | `requirements-runtime.lock` | `requirements-dev.lock` |
| Linux, Python 3.11 | `requirements-runtime-py311-linux.lock` | `requirements-dev-py311-linux.lock` |

Generate each pair on the corresponding system and Python version:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m scripts.manage_dependencies --generate
.\.venv\Scripts\python.exe -m scripts.manage_dependencies --check
```

`requirements-locks.json` records the hash of the declarations and of each lock. CI refuses changed declarations without regeneration. `requirements-web.txt` and `requirements-lock.txt` are aliases for the Windows/Python 3.11 lock; on Linux use the Linux pair. The existing GPU environment and the `Qwen/Qwen3-Embedding-0.6B` model are kept.

The workflow `.github/workflows/ci.yml` separates the static checks, the Python 3.11 unit tests, the pgvector integration, the frontend and the Docker build. It uses synthetic data and does not publish the personal corpus.

### Content-level retrieval evaluation

The existing structural evaluator remains available. The new `--content` mode uses exactly 30 cases from `src/tests/eval/content_cases.json`, covering conditions, synonyms, free-form wordings and warnings. Each fragment is identified by relative path and the SHA-256 of its text, independent of the PostgreSQL ID.

The shipped cases are labeled for the synthetic corpus in `src/tests/eval/synthetic_corpus`. The rankings in `synthetic_rankings.json` and the ideal analytic baseline verify the metrics mechanism; **they do not measure the model's quality on the personal corpus**:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_retrieval --content --rankings src/tests/eval/synthetic_rankings.json --baseline src/tests/eval/synthetic_baseline.json --output var/output/synthetic-metrics.json
```

For a real index, prepare locally 30 cases with hashes from that corpus, then measure the baseline before changing the scoring. Personal data and local labels stay in `var/output`:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_retrieval --content --dotenv --cases var/output/content-cases-local.json --output var/output/retrieval-before.json
.\.venv\Scripts\python.exe -m scripts.evaluate_retrieval --content --dotenv --cases var/output/content-cases-local.json --baseline var/output/retrieval-before.json --output var/output/retrieval-after.json
```

The report includes Recall@50 of the labeled relevant fragments, nDCG@10 with grades 0–3, the number of results labeled irrelevant in the top 10, the unlabeled fragments in the top 10 and the coverage of the expected warnings in the top 50. The comparison refuses different corpora/cases/configurations and reports regressions for each case, with exit code 2. A new generation of the same content can be compared. These metrics do not clinically validate the sources.

## Operation and limits

Run the application with **a single Uvicorn worker**: sessions and limits are managed in process memory. By default two searches and one simultaneous generation are allowed (`MAX_CONCURRENT_SEARCHES=2`, `MAX_CONCURRENT_GENERATIONS=1`). Additional reports receive `202` and wait in a FIFO queue in process memory; the next one starts after the previous worker has actually stopped. At most `MAX_QUEUED_GENERATIONS=20` waiting requests are admitted, within the memory budgets. Exceeding the queue capacity produces `429 GENERATION_QUEUE_FULL`; an operation with different options already running on the same search may produce `409`.

Operations have a total budget of 600 seconds (`OPERATION_TIMEOUT_SECONDS`), with no automatic retry. After expiry or after the session is closed, late results are discarded; a call that has already started may continue, occupying capacity until it finishes.

Use `/healthz` for the AI configuration and `/readyz` for the index availability. Reindexing creates the missing database and applies the migrations; the web application does not run them at startup. During index synchronization, search may respond `503`; a failure keeps the previous generation.

For public exposure, set `DEPLOYMENT_PROFILE=public`, `PUBLIC_ORIGIN=https://...`, `COOKIE_SECURE=true`, `LOG_FRAGMENT_TEXT=false` and `LOG_AI_RESPONSE_TEXT=false`. In Compose, explicitly add `DEPLOYMENT_PROFILE` to `app.environment`; simply adding it to `.env` does not pass it to the container. Configure the authorized proxies through `FORWARDED_ALLOW_IPS` (Uvicorn); for Funnel on the host and Docker, the loopback and the gateway of the application's internal network are authorized.

## PDF to Markdown extraction

`src/scripts/extract_pdf_markdown.py` locally converts PDFs to Markdown, infers the titles and the reading order and keeps the `<!-- Pagina PDF N -->` markers (“PDF page N”). Install the optional dependencies, then run the conversion:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[pdf]"
.\.venv\Scripts\python.exe src\scripts\extract_pdf_markdown.py "book.pdf"
```

By default, for `book.pdf`, the script creates the folder `medicina-naturista-documente/data/documents/Surse sigure/book/` and saves `book.pdf.md` there. The folder receives the PDF's name without the extension, and the Markdown file keeps the PDF's full name, with `.md` added. The destination is relative to the project root, computed from the script's location, regardless of the launch directory. `-o` / `--output` allows explicitly choosing another output file.

PyMuPDF extracts the characters and font information and renders the pages. By default, each page is straightened separately before extraction and the columns are detected automatically. The text source is chosen per page. A page with a real text layer (born-digital) keeps that text. A scanned page carries an old OCR layer that can drop whole paragraphs without any error, so its layer is trusted only if three checks against the page image pass: no dark pixels outside the layer's text boxes, no garbled symbol strings, and a low share of words missing from the bundled Hunspell dictionary (`src/scripts/pdf_layer_check.py`; the thresholds were calibrated on a scanned Romanian book). A page that fails them, or that has no layer, is transcribed to Markdown by a local vision model served by Ollama (`src/scripts/pdf_vision.py`, default `qwen3.5:9b`, address from `OLLAMA_API_BASE` with `http://localhost:11434/v1` as default). If Ollama or the model is not available, those pages fall back to Tesseract and the report says so. The model is unloaded when the run ends. Tesseract runs in memory through `Page.get_textpage_ocr`, without starting its executable and without intermediate images or TSV files; it uses the language files `ron.traineddata` and `eng.traineddata`, found through `--tessdata` or `TESSDATA_PREFIX` (on Windows `C:\Program Files\Tesseract-OCR\tessdata` is detected by default).

The output never contains diacritics: `ț`, `ș`, `ă`, `â`, `î` and the other accented letters are written as `t`, `s`, `a`, `a`, `i` and so on, in the file name header and in the text. The vision model chooses its own heading levels (`##` and `###`), and its pages are not merged with the following page.

Chapters are not guessed page by page. If the PDF has no outline, the script reads the running heads in the text layer (the chapter title printed at the top of every other page, and the book or author title that repeats on all pages), recovers the chapter list and the page where each chapter opens (`src/scripts/pdf_chapters.py`), and writes one `## CHAPTER TITLE` at the opening page of each chapter in every `--ocr` mode. On those pages the page's own title lines, its running head and the lone chapter number are removed, and all other headings are moved one level down (`###`, `####`), so that chapters are the only `##` headings. Running heads of different levels can alternate on facing pages (the part title on one side, a chapter or an article on the other, as in a reference book); a head joins the most recent run of pages whose head agrees with it, and a run that shares pages with a larger one is treated as part of it, so only the top level (for example the parts of a book) becomes `##` and the rest is left to the headings of the pages. Garbage made of upper-case letters without vowels (OCR of ornaments and contents pages) is not read as a head. A book without running heads, or with an outline, is not changed by this step. The chapter list and opening pages are in the JSON report (`chapters`). The result depends on the quality of the embedded text layer: a head that the old OCR misread on every page is not recognized.

Below the chapters, heading levels do not depend on what the vision model decides for each page (it sees one page and, on a page that holds only small headings, would call them main headings). The printed size of each heading is read from the text layer (`src/scripts/pdf_headings.py`) and compared with a size learned from the whole book: pages where the model itself saw two heading styles show which size is a section and which is a part, and a heading that ends in a colon is a part wherever it stands. Sections get `###` and parts `####`, so a section (for example a remedy) always contains its parts and stays one fragment for the fragmenter. No heading text is hard-coded. If a book gives too little evidence, or a heading has no matching line in the layer, the model's own choice on that page is kept. Two clean-ups run on every vision page: decorative `---` rules are dropped, and a "heading" that is really a paragraph (longer than 100 characters, starting in lower case, or a label followed by a whole sentence) is turned back into a paragraph, with the label in bold.

`src/scripts/fix_markdown_headings.py "book.pdf.md" "book.pdf"` applies these rules to a Markdown file that already exists, with no AI call: it re-reads only the heading sizes from the PDF, leaves the book title and the chapters (`##`) as they are, and changes nothing but heading marks, `---` rules and bold labels. It rewrites the file (`-o` writes elsewhere), so keep a copy first; the JSON report of a new extraction records the size it used in `section_heading_size`.

Useful options:

- `--start-page N --end-page N`: converting a range of pages.
- `--ocr vision|auto|always|never`: `vision` (default on the command line) transcribes every page with the vision model; `auto` is the per-page choice described above, which keeps a scanned page's text layer only when it passes the checks and is faster; `always` forces Tesseract, `never` uses only the existing text layer. Without Ollama, `vision` falls back to Tesseract and the report says so. The default of the Python `Options` class stays `auto`, so library calls and unit tests need no Ollama.
- `--vision-model NAME`: another Ollama model with vision support.
- `--workers N` (default 1): pages sent to the vision model at the same time. The pages are prepared on one thread, in parallel with the requests, and written in page order; one page is always prepared ahead. Measured with `qwen3.5:9b`: Ollama logs `model architecture does not currently support parallel requests` for it and runs two simultaneous requests one after the other, so `N` above 1 saves no time with that model (8 pages: 186 s with 1 worker, 184 s with 2). Use it only with a model and an Ollama version that do run requests in parallel (`OLLAMA_NUM_PARALLEL` at least `N`).
- The page image sent to the model is cropped to the printed area before it is sent, which removes the white scan margins: about 1,200 image tokens instead of 3,000 per page, around 10% less time per page with no loss of accuracy on the six pages checked.
- `--columns 1|2|3` and `--deskew off`: manual control for ambiguous documents.
- `--debug`: logging the entry into each explicit function/method, with the parameter names; passwords are masked, and large collections and objects are summarized. By default progress is displayed at `INFO` level.
- `--help`: the full list of options.

The JSON report describes the extraction (the method used for each page: `text`, `vision` or `ocr`, and why a scanned page's layer was rejected) and the per-page warnings. The Markdown and the report are prepared before the results are replaced; if publishing fails, the script tries to restore the previous versions and keeps the recovery copies if restoration is blocked. Destinations that coincide with the source, including hardlinks, are rejected. OCR rendering is limited to 64 megapixels per page; reduce `--dpi` for very large pages. Check the titles, tables and degraded scans: the structure is inferred heuristically, and OCR errors are not corrected semantically.

`src/scripts/merge_book_pdfs.py` merges the fragments `pag<first>-<last>.pdf` and straightens each page in memory, using PyMuPDF for all PDF operations. Each fragment is opened only once; the page count is checked during merging, and mismatches and missing ranges produce warnings. Overlapping ranges are rejected, including on direct calls from Python. It performs no OCR and generates no intermediate images. By default, the final PDF is saved in the project root (`D:\Workspace\medicina-naturista` in the current checkout), with the source folder's name and the `.pdf` extension; the destination is computed from the script's location, regardless of the directory it is launched from. `--output-dir` changes the destination, and `--deskew off` disables straightening. `--debug` enables logging the entry into each explicit function/method, with named parameters and large objects summarized. Progress is displayed at `INFO` level. The final PDF is verified before the atomic replacement of the destination; the sources, including aliases/hardlinks, are protected against overwriting.

## 📜 License

The project's code is distributed under the [Business Source License 1.1](LICENSE) ([Romanian version](LICENSE.ro.md)). Use in non-production environments is free; use in production requires a separate commercial agreement with the licensor. Apache 2.0 is the license provided for after the change date, according to the terms in `LICENSE`, not the project's initial license.

---

<div align="center">

🌱 **Verifiable sources · local retrieval · adjuvant recommendations**

</div>


## Background report generation

The supported models are defined in a single backend catalog. `REPORT_GENERATION_MODELS` is the CSV list of the enabled models, in the UI order; the first model is the default. `/api/report-models` returns all the configured models in `models`, the first in `defaultModel` and, separately, the models permitted to the current user in `allowedModels`. All options remain visible and selectable for the public. Recipe/report generation is reserved for the administrator for all models, including local Ollama. An unauthorized user sees the message “Recipe generation is available only to the platform administrator.” and the generation button disabled for any model. `allowedModels` is empty for the public and contains the configured models for the administrator; missing permission metadata disables generation in the UI. The authenticated administrator can generate with all configured models. The same protection applies on the backend for all models: the request receives HTTP 403 with `MODEL_FORBIDDEN`, before the job is admitted or the AI is called, if the author session is not valid. Requests without a model use the first configured model and the same check, with no automatic switch to another model. An explicit model that is not configured is rejected with HTTP 422 and `MODEL_NOT_CONFIGURED`. The status and cancellation of a job also require a valid administrator session. Clients are built only for the configured models. The previous singular variable has been removed.

In the chat, the confirmation “The report is ready and was generated in …” also includes `using the AI model **<model>**`, with the effective model identifier displayed in bold. The information is kept in the report message in the session history, independent of later selections in the UI.

At the end of the PDF, after the bibliography and the generation summary, `AI model used: <model>` appears. The effective identifier sent to the provider is displayed, fixed from the client chosen for the report; a later change of the default does not modify this information for requests already admitted to the queue.

| UI option / env | Provider | Model sent in the request |
| --- | --- | --- |
| `ollama-gemma3:1b` | Local Ollama | `gemma3:1b` |
| `ollama-gemma4:12b` | Local Ollama | `gemma4:12b` |
| `ollama-ministral-3:8b` | Local Ollama | `ministral-3:8b` |
| `ollama-qwen3.5:9b` | Local Ollama | `qwen3.5:9b` |
| `ollama-qwen3.5:4b` | Local Ollama | `qwen3.5:4b` |
| `ollama-deepseek-r1:8b` | Local Ollama | `deepseek-r1:8b` |
| `deepseek-flash` | DeepSeek | `deepseek-flash` |
| `huggingface-deepseek-v4-flash` | Hugging Face / DeepInfra | `deepseek-ai/DeepSeek-V4-Flash:deepinfra` |
| `grok-4.3` | xAI | `grok-4.3` |

All Ollama models for reports use the native `/api/chat` route. Install the chosen local model on the host before use; the option `ollama-ministral-3:8b` uses the Ollama tag `ministral-3:8b`.

#### The report's AI effort

At “Generate report” the owner chooses, next to the model, an **effort**: `low` (default), `medium` or `high`. The value goes into the body of the request `POST /api/searches/{id}/generate` (`effort`) and is translated for each model; the `*_REASONING_EFFORT` environment variables no longer exist.

| Model | `low` | `medium` | `high` |
|---|---|---|---|
| Ollama `gemma4:12b`, `qwen3.5:9b`, `qwen3.5:4b`, `deepseek-r1:8b` | `think=false` | `think=true` | `think=true` |
| `deepseek-flash`, `huggingface-deepseek-v4-flash`, `grok-4.3` | `reasoning.effort="none"` (reasoning off) | `"medium"` | `"high"` |
| Ollama `gemma3:1b`, `ministral-3:8b` | no control | no control | no control |

- For these models Ollama accepts only a boolean `think`, so `medium` and `high` produce the same request.
- DeepSeek documents `none`/`low`/`high`/`max` and maps `medium` to `high` on its own; xAI documents `none`/`low`/`medium`/`high`. For Hugging Face only `low`/`medium`/`high` are documented: `none` on the DeepInfra route is not confirmed and must be verified with a real request (the mapping is in `src/backend/ai/effort.py`).
- For models without control the selector is disabled, the server ignores the value, sends nothing and saves `ai_effort = NULL` in the metrics.
- The chosen effort is saved in `report_generation_metrics.ai_effort`. The duration estimate (`GET /api/report-duration-estimate?model=…&characters=…&effort=…`) first uses the samples of the same effort and, if none exist, the model's samples.
- The effort is part of the request's idempotency: the same `requestId` with a different effort receives `IDEMPOTENCY_CONFLICT`.

For the `ollama-gemma3:1b` reports, the profile from the catalog sends `temperature=0`, `repeat_penalty=1.1` and `repeat_last_n=256`, to reduce repetition loops in the JSON answers. These options apply only to report generation with this model; the schema, the whole fragments, the context and the output limit are kept. The profile reduces the risk of repetitions, without guaranteeing their elimination or the semantic quality of the recommendations.

If Ollama interrupts the stream with `prediction aborted, token repeat limit reached`, the application recognizes it as `repetition_limit`, logs it without the generated text and ends the job with `AI_REPETITION_LIMIT_EXCEEDED`. The message explains the repetition loop, instead of reporting a generic JSON validation error. The other active batches are cancelled; there is no automatic retry, truncation or publishing of an incomplete PDF. The exception from the local budget for single-fragment requests remains valid.

For `ollama-deepseek-r1:8b`, install the model with `ollama pull deepseek-r1:8b`. The current tag is DeepSeek-R1-0528-Qwen3-8B, Q4_K_M, which accepts the existing `system` prompt. The default profile sends `num_ctx=32768`, `num_predict=8192` and uses a conservative budget of 24,000 input tokens per batch, including the instructions, the profile and the JSON schema. The context was increased so that the conservative estimate of the instructions leaves room for the fragments too. The global output limit does not replace the R1-specific limit. A fragment that does not fit in the conservative budget is sent whole in a separate request; the real context limit remains checked by Ollama, with no truncation or fallback. Increasing the context may increase Ollama's memory consumption.

Ollama runs on the host's GPU; the FastAPI container does not need CUDA access for reports. The explicit R1 context replaces, for this request, the global value `OLLAMA_CONTEXT_LENGTH`. During generation, check `ollama ps`: `100% GPU` indicates the model is fully loaded on the GPU. The configuration alone does not guarantee fitting in VRAM. No warm-up calls are added at startup. R1 14B is not integrated.

If Ollama responds that the requested model is not found, the job receives `AI_MODEL_NOT_FOUND`, and the interface displays that the selected model is not installed or not available.



Generation starts through `POST /api/searches/{searchId}/generate` and responds with `202`, `jobId` and `Location`. The client sends a stable `requestId` for each attempt. `GET /api/report-generations/{jobId}` reads the status, and `POST /api/report-generations/{jobId}/cancel` requests cancellation. Periodic checking launches no additional AI calls. The same execution works with all the supported AI clients; the chosen model is fixed at admission. The existing access restrictions for the chosen model also apply to reading/cancelling the operation.

The frontend reconciles the job status with the session snapshot: on returning to a tab, an old cached “queued” state cannot replace a final status received together with the report. The same reconciled state controls the message, the generation indicator and the polling; stopping the worker is not reversed by an old snapshot.

In the PDF, the items in `uz_intern`, `uz_extern`, `alte_recomandari` and `atentionari` are ordered descending by the **number of cited fragments**. Each valid fragment ID is counted once for an item; two different fragments from the same document are two sources. **X** stays displayed and computed as before: `● (57) Elderberry fruit tincture: description...`. Plants are identified only in the name, including through the catalog synonyms; for each plant the rows in `herbs_benefits` are counted, without filtering by the report's condition. If the name contains several plants, X is the maximum of the counts; if no plant is identified or there are no associations, X is zero and neither the number nor the parentheses are displayed. On a tie in the number of fragments, the maximum relevance of the cited fragments, the number of distinct references and the initial position are used. X reflects the indexed associations, not a measure of clinical efficacy, and does not influence sorting. Nutrition and the report text in the chat keep the existing ordering. The rule applies to newly generated PDFs.

The report timer stays at `00:00` while the request waits for admission or is in the queue. It starts when the worker picks up the report, using `startedAt`, without including the wait. Stage changes and status updates do not reset it; a new attempt receives a new timer.

If the provider marks the answer as incomplete with the reason `max_output_tokens`, the job receives `AI_OUTPUT_LIMIT_EXCEEDED` and a message explaining that the token limit was reached before the report was finished. This is distinct from a timeout and from an invalid JSON. The text received stays in the panel; an incomplete answer is not published as a report/PDF and is not retried automatically.

After the complete PDF is successfully published, the application inserts a single measurement into the PostgreSQL table `report_generation_metrics`: `id`, `medical_condition`, `min_score`, `characters`, `ai_model`, `ai_effort`, `duration`. The condition is identified from the search snapshot and saved with the exact name from `medical_conditions.name`: for “Remedii naturiste pentru gripă” (“Natural remedies for flu”) `Gripa` is stored. For several conditions, the canonical names are kept in the order of identification, separated by commas. AI answers are accepted here only if they are mapped to the catalog; if there is no condition from the catalog, the measurement is not inserted, and the PDF remains available. `characters` counts the Unicode characters in the fragments actually provided to the AI, after filtering by score and budget. `ai_model` keeps the choice from the catalog (for example `ollama-gemma4:12b`), and `ai_effort` keeps the effort configured for the selected client, with `NULL` if unspecified. The recorded effort does not guarantee that the provider applies it. The API accepts `minScore` only as an integer between 0 and 100.

`duration` is a `BIGINT` in **milliseconds**, measured with a monotonic clock until after publishing in the session; it excludes the queue, the statistics insertion and the email. Cancellations, failures and repeated requests for the same job add no measurements. The insertion uses the existing pool, with a wait of at most 1 s for a connection, `statement_timeout` of 2 s and `lock_timeout` of 500 ms in the transaction. If the insertion fails, the PDF remains available, and the log `report_metrics_persistence_failed` identifies the operation without medical content. There is no automatic retry or guarantee of recording if the database is unavailable or the process stops between publishing and INSERT.

Under “Total number of characters”, the UI displays “Estimated duration: mm:ss (min:sec)” for the number of eligible characters and the chosen model. The calculation uses all the model's rows, without filters by condition, score or effort: linear regression through the origin, `duration_ms = selected_characters × SUM(characters × duration) / SUM(characters²)`. The durations in the table are in milliseconds; the result is rounded up to seconds. When the model or the characters change, the estimate is requested again, and the answers for earlier selections cannot overwrite the current selection. After a job finishes, the estimate is refreshed to include the new history. Without usable data, the UI displays “unavailable”; DB/network unavailability does not block generation. The route returns only the model, the characters, `estimatedSeconds` and `sampleCount`; the estimate launches no AI requests and does not change the generation rights.

Migrations `011_report_generation_metrics.sql` and `012_seed_report_generation_metrics.sql` create the table and insert the six historical measurements provided (53,924 characters each). Apply them before activating the code, through `python -m scripts.migrate_database` with `PYTHONPATH=src` and the target database configuration; the migration registry prevents re-applying the seed. Reindexing is not required. Manually repeating the INSERT from migration 012 adds another six rows.

Migration `013_canonical_report_metric_conditions.sql` corrects the historical labels that exactly match a name from the catalog, including the form “Remedii naturiste pentru <condition>” (“Natural remedies for <condition>”). The other values of the measurement are kept; texts without a match remain for manual verification.

`REPORT_GENERATION_TIMEOUT_SECONDS` limits the whole report, including all the batches and the PDF build (default 600 s; configurable). `OPERATION_TIMEOUT_SECONDS` remains separate for the other operations, and `REPORT_GENERATION_READ_TIMEOUT_SECONDS` limits I/O. Waiting in the application queue does not start the report's timer.

### A single active report, with configurable parallel batches

The single FIFO worker (`REPORT_GENERATION_WORKERS = 1`) keeps a single active report.
Inside it, a separate executor uses `REPORT_BATCH_WORKERS` from `.env`
(default `2`) as the limit of simultaneous AI requests, exclusively for the batches of that
report. `1` disables parallelism; non-integer or non-positive values are rejected
at startup. Docker Compose passes the setting through `app.environment`.
After a
batch ends, the next one can be admitted, without waiting for the other active batches. The operation context,
the deadline and the batch ID are propagated explicitly into each thread. There is no automatic
retry or consolidation AI request. Each request receives the same system prompt
from `ai/prompts/generate_report_system.md`, the consultation profile and the whole fragments
of its batch.

`REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL` allows different input budgets per model and batch, plus each model's default context and effort. The value can be written over several lines in `.env`, between single quotes (read the same way by `python-dotenv` and by Docker Compose). Example with the default values:

```dotenv
REPORT_BATCH_WORKERS=2
REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL='{
  "ollama-gemma3:1b": {"tokens": 25000, "context": 32768, "effort": "low"},
  "ollama-gemma4:12b": {"tokens": 25000, "context": 262144, "effort": "low"},
  "ollama-ministral-3:8b": {"tokens": 25000, "context": 262144, "effort": "low"},
  "ollama-qwen3.5:9b": {"tokens": 25000, "context": 262144, "effort": "low"},
  "ollama-qwen3.5:4b": {"tokens": 25000, "context": 262144, "effort": "low"},
  "ollama-deepseek-r1:8b": {"tokens": 24000, "context": 32768, "effort": "low"},
  "deepseek-flash": {"tokens": 25000, "context": 1048576, "effort": "low"},
  "huggingface-deepseek-v4-flash": {"tokens": 25000, "context": 1048576, "effort": "low"},
  "grok-4.3": {"tokens": 25000, "context": 1000000, "effort": "low"}
}'
```

The contexts are those published for each model (Gemma 3 1B: 32K; Gemma 4 12B, Ministral 3 8B, Qwen 3.5: 256K; DeepSeek V4 Flash: 1M; Grok 4.3: 1M). R1 8B stays at 32768, the `num_ctx` value sent by the application, not the model's 128K. The effective input of a batch is `min(tokens, context − output)`. `GET /api/report-models` sends everyone `contextTokens` and `defaultEfforts` for the configured models.

Counting is local and estimated: tokens are estimated as the UTF-8 bytes of the complete JSON payload divided by 3 (rounded up), plus a fixed reserve of 256 tokens for message framing. The system prompt, the profile, the fragments, the sources, the IDs, the JSON schema and the request fields are included. No tokenizers are downloaded and the providers are not called for counting. The estimate is not the exact number produced by the model's tokenizer, and the provider remains the authority for the real context; if a batch exceeds the context, reduce “Max input tokens”.

For Ollama with an explicit `num_ctx`, the effective input budget is the minimum of the configured limit and `num_ctx - num_predict`, so that the output has reserved space. Without an explicit context, the Ollama server configuration remains; the input budget must be chosen together with the output limit and the server context. `REPORT_GENERATION_MAX_OUTPUT_TOKENS` and the output overrides remain per-batch limits, independent of the input budget. The four variables (`REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL`, `REPORT_BATCH_WORKERS`, `REPORT_GENERATION_MAX_OUTPUT_TOKENS`, `OLLAMA_MAX_OUTPUT_TOKENS_BY_MODEL`) provide the default values in the report panel; the admin can change them for a single report, without modifying `.env`.

The fragments are kept whole and ordered by score. If a single fragment with the whole overhead exceeds the budget, it is isolated in a batch and sent whole. The local per-batch limit is ignored only for requests with exactly one fragment, including when the effective budget is reduced by reserving the output from the explicit context. Batches with several fragments still respect the limit. The content is not shortened and the context or the output limit sent to the provider are not changed. The provider can still reject a request that exceeds the real context; the error remains `AI_CONTEXT_LIMIT_EXCEEDED`. The logs use `input_tokens_upper_bound` and `counting=utf8_bytes_div3`, and the local exception is marked by `report_batch_token_limit_bypassed` with `fragments=1`.

Search runs before the model is chosen, so it limits the total of the selected content to the largest value in `REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL` among the active models (`REPORT_GENERATION_MODELS`); each model's limit then splits the content into batches. Tokens are estimated from the fragments' UTF-8 bytes (3 bytes per token) with IDs, sources, titles and serialization; the prefix is kept in score order, without shortening the fragments. The prompt, the profile, the schema and the output are budgeted separately per request. SQL uses the budget multiplied by 3 as a prefilter in characters, then retrieval explicitly checks the estimate from UTF-8 bytes: thus, the token limit is not treated as a character limit. These local estimates are not the exact number of tokens computed by the providers.

The old variable `REPORT_GENERATION_BATCH_MAX_CHARS_BY_MODEL` must be removed and replaced with values chosen in the new unit; if it reaches the application's environment, startup rejects it explicitly, to avoid silently reinterpreting characters as tokens. After modifying `.env` and the code, the service's configuration and image must be updated by the operator.

Each answer is strictly validated against the IDs of its batch; a valid batch without recommendations is allowed. The results are combined by code: only identical texts in the same section are removed and their sources are merged. Different variants, doses and warnings are kept. The food lists remove only identical elements in the same subcategory; distinct culinary recipes from all batches are kept, without an additional global ceiling. Combining performs no semantic reconciliation or global clinical validation.

In the structured form of the Nutrition section, text fields that are empty or made up only of spaces, ASCII dashes and `•` markers are normalized as no content; for example, `"interzise": "-"` creates no empty recommendation and does not invalidate the batch. Recommendation objects without useful text, invalid citations, missing required fields and the other deviations continue to be rejected by strict validation.

For Ollama reports, `format` receives the JSON schema of the five sections,
including the Nutrition structure and the IDs allowed from the current batch. Recommendations outside
Nutrition require at least one citation. The schema guides generation; the local validator
remains mandatory and rejects invalid answers, without repair or automatic retry.

Ollama integration problems are logged with the model, the stage and the failure type:
HTTP/network/timeout, missing model, insufficient loading or memory, context or output
limit, interrupted protocol/stream, invalid JSON and result validation.
`ai_report_validation_failed` includes the batch, the number of problems per code and at most
20 affected positions (section/index), for example `UNKNOWN_EVIDENCE`,
`MISSING_EVIDENCE`, `INVALID_ITEM` or `MISSING_NUTRITION_FIELD`.
Message classification, condition identification, the model inventory and indexing
use the same transport diagnostics; indexing also includes the known validation
codes. Unexpected errors are logged by type, without the exception arguments.
The logs do not include the prompt, the fragments, the raw answer, thinking or API keys;
arbitrary provider messages are replaced with known technical reasons.
For runtime diagnostics: `docker compose logs --since 30m app`.

The “Report preview” area displays a separate “Batch N of T” panel for
each planned batch, in processing order. Each panel keeps exclusively the
recommendations and bibliography of its own batch, with its own scrolling; the previews do not
accumulate. Pending, active, validated, failed, cancelled or expired batches
have distinct states. During processing, the batch details display the analysis
sent by the provider and the raw answer, including incomplete JSON. After validation,
the raw details are collapsed; after success the validated previews of
all batches remain. On failure/cancellation the details of the interrupted batch are also kept,
and those not started are marked as unprocessed. The raw texts are not validated
and do not go directly into the report or PDF.

The API exposes `batchPreviews`, with `index`, `state`, `reportPreview`, `streamPreview`
and `thinkingPreview` for each batch, plus `previewVersion`, `batchesCompleted`
and `batchesTotal`. The compatible field `reportPreview` contains the last validated batch.
Each batch owns its own answer/analysis fragments and its own `aiActivity`,
so that simultaneous text does not get mixed. The aggregate compatibility fields
are built at read time, in batch order, without additional raw copies
retained in the session. The formatted snapshots, the text and the batches' metadata (including
a reserve of 2 KiB per batch for activity) are counted in the existing budgets.
The counter of finished batches counts the validated batches, even if batch 2 finishes
before batch 1; the versions grow monotonically. It is not a progress
percentage. The final report and the PDF continue to combine all the batches in the backend,
with the same validation and deduplication rules.

The first request or validation error stops admitting the following batches and requests
cooperative cancellation of the other active batches. The initial error is kept even if
the cancellation of another thread is observed first by the coordinator. User cancellation
and the report timeout propagate to all active batches. I/O calls already blocked cannot
be killed as Python threads: the report's capacity stays occupied until all threads
actually exit, within the I/O timeouts. No partial PDF is published.
The validated previews and the data of the interrupted batches remain in the session. Thinking and
the raw answer do not go into the PDF or logs; thinking is released after success. A new
generation replaces the previous preview. On success, the results are combined
in the initial order of the batches, regardless of the order in which they arrive.

The PDF, the message “The report is ready” and a single `report_generation_metrics` measurement are published only after all the batches have ended. The duration is the real time of the report, not the sum of fictitious per-batch durations. The existing estimate continues to use all the model's observations; history with a single request may have different performance from the batch flow.

The `aiActivity` state (`waiting`, `processing`, `thinking`, `answering`) and “Last activity received” are updated from the real events of the current request, without polling resetting the time. The speed remains approximated at 4 characters/token, separately for thinking and answer, without the diagnostic separators; it does not represent the tokens billed by the provider. Connection errors, cancellation and the validation/PDF stages take priority. No percentage progress bar is displayed.

`report_ai_timing` records the local times until the first event, the first analysis and the first text of the answer, plus the duration of the AI call. For Ollama it includes the final durations of loading, prompt processing and generation, converted to milliseconds; for DeepSeek, the available usage, including reasoning tokens. Unknown values remain absent or `null`. `report_ai_phase_changed` records only the phase changes, without the content of the analysis or of the answer.

The HTTP interface starts without waiting for the local search to be ready. In the background a single probe search runs to load the embeddings, the dictionary and the index, with `warm_up_started` / `warm_up_finished` times for the `search` stage. At startup no warm-up calls are made to Ollama, DeepSeek or Grok. `/api/startup` returns `initializing`, `ready` or `degraded`; the UI checks the state every second and displays the initialization. While the preparation runs, submitting questions is disabled, and the search/AI operations and `/readyz` respond with `APP_INITIALIZING` (503). `/healthz`, the interface and the session remain accessible. If the search preparation fails, the application signals degraded mode and allows a search to be attempted. The preparation task is tracked and awaited with a limit at shutdown; resources still in use are not closed prematurely.

`MAX_CONCURRENT_GENERATIONS` must be 1. Accepted requests initially have the stage `queued`; the status query returns `queuePosition` (from 1), displayed in the interface. Cancelling a queued request removes it without an AI call. Duplicate requests are reconciled through `requestId`, without duplicating the generation. The waiting time does not consume the `REPORT_GENERATION_TIMEOUT_SECONDS` budget, which starts at pickup; the session's maximum duration remains applicable. The queue does not persist across a process restart. The slot stays occupied until the worker actually stops, including after logical cancellation or expiry. The terminal states and error codes can be read independently of the starting connection. The metadata is limited to 32 operations per session and is included in its memory budget.

Refreshing the same tab recovers the operation if it reconnects within `SESSION_RECONNECT_GRACE_SECONDS` (default 30 s). Explicit closing cancels immediately; without reconnection, the unload closes the session after this window. Sessions and operations stay in memory, in a single process: a container restart loses the results and does not automatically relaunch AI requests. Shutdown waits at most `REPORT_SHUTDOWN_TIMEOUT_SECONDS` (default 20 s), with a Docker grace period of 30 s; a blocked synchronous call may require stopping the process.

To activate code/configuration changes: `docker compose up -d --build app`, then reload the page. Architecture details: [asynchronous generation](architecture/report-generation-background.xmind).

Migration `039_medical_conditions_version.sql` adds the counter `medical_conditions_version`, incremented by triggers on `medical_conditions` and `medical_condition_synonyms`. As long as the counter does not change, each read from the index reuses the in-memory conditions dictionary instead of reading it again (from ~300 ms to a few milliseconds). Apply the migration before activating the code, through `python -m scripts.migrate_database`; without it requests fail with `CONDITION_VERSION_SCHEMA_MISSING`. Reindexing is not required. After restoring a backup made before this migration, run the migrations again: the restoration removes the triggers, and the (idempotent) migration recreates them. If the index metadata does not match the cached dictionary, the reader re-reads the tables once before reporting `INDEX_RESYNC_REQUIRED`.
