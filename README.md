<div align="center">

# 🌿 NaturaMind: AI Assistant for Naturopathic Medicine

### AI naturopathy assistant based on local sources

🌱 **Verifiable sources · local retrieval · adjuvant recommendations**

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![Hybrid retrieval](https://img.shields.io/badge/Retrieval-pgvector%20%2B%20tsvector-6A5ACD)](#-how-it-works)
[![License](https://img.shields.io/badge/License-Business%20Source%201.1-D22128)](LICENSE)

🩺 **6,285 medical conditions** · 🌱 **1,585 plants and natural products**

🟢 **local sources** · 🔵 **semantic search** · 🟠 **lexical search** · 🟣 **PDF report**

</div>

> [!IMPORTANT]
> The application provides guidance and adjuvant recommendations. It does not replace diagnosis, consultation, prescribed treatment or emergency medical care.
> Conversations and reports are kept temporarily in process memory. The description of the problem and the selected fragments may be sent to the configured AI provider; identifying the condition may separately use an external service. Do not enter names, personal numeric IDs, addresses or other identifying data in the chat.

## ✨ About the project

The project turns a local collection of Markdown documents about naturopathy and complementary therapies into a queryable hybrid index. The web interface receives the problem described by the user and displays the relevant fragments found in the local archive. After the fragments are reviewed, the administrator authorized through `/owner` chooses the model for each report, including local Ollama models. The application sends the evidence to the chosen provider to write the structured answer and generates a PDF report with references to the sources. Generation is reserved for the administrator for all models.

> ### 🩺 6,285 &nbsp;medical conditions &nbsp;·&nbsp; 🌱 1,585 &nbsp;plants & natural products &nbsp;·&nbsp; 🗂️ 11 &nbsp;categories
>
> **Name a problem, get the plants.** NaturaMind knows **6,285 medical conditions**, each with its own synonyms, so "flu", "influenza" and "gripa" all lead to the same answer. 🔎
> It also knows **1,585 herbs, fruits, vegetables, seeds, oils, vitamins, minerals and supplements**, and for every one it tells you what it is useful for ✅, what it is forbidden for ⛔ and which warnings, contraindications and interactions to keep in mind ⚠️.
> Ask about a condition and see the best natural products for it 🏆, or ask about a plant and see everything it can do 🌿. All of it comes from your own local library of sources, with the exact passage one click away 📚.

| 🧩 Component | Role |
|---|---|
| **Semantic index** | Identifies fragments with a close meaning using 1024-dimension Qwen3-Embedding vectors, stored in Postgres (`pgvector`). |
| **Lexical index** | BM25 ranking through ParadeDB `pg_search` in Postgres: each comma-separated expression is searched by its words (at least 75%, in any order) and as a phrase (boosted), in the text and in the heading (boosted), with the Romanian or English stemmer and accents folded; when the whole expression is a recognized condition, all its names are searched as phrases. |
| **Combined score** | Each fragment receives a single score, from the signals that the patient ticks in “Sources and search options” (conditions, lexical, semantic). With all three: `4·P1 + 2·P2 + L + V` (condition in title › condition in text › lexical match › semantic match), computed in a single SQL query. |
| **Condition-based fragmentation** | Splits documents into R1 fragments (condition in the chapter title), R2 (condition in the chapter text) and D1 (the rest of the text), using the catalog of conditions and synonyms in PostgreSQL. |
| **Source filtering** | In the same “Sources and search options” panel, the search can be restricted to certain folders under `medicina-naturista-documente/data/documents/` (a document's category is its folder). |
| **Medical retriever** | Orders the fragments by the combined score and keeps whole those that fit within the AI provider's context budget. In “Generation options”, “Minimum score” (relevance percentage) limits the fragments sent to the AI. |
| **Web chat** | Provides sessions isolated per tab and displays the structured recommendations. |
| **PDF report** | Includes recommendations, warnings, citations and a navigable bibliography. |
| **Email delivery** | After generation, it can send the report through the Gmail API with OAuth2 to the address the user writes in the chat, if configured. |

The interface uses a fluid column of at most 640 px, a cream header with a legible title,
Grandpa Cuișor's portrait and discreet botanical decoration. On mobile, the portrait appears below the description.
The identity of a virtual AI assistant and the medical warning remain visible. The same portrait
is used in the header, the conversation avatars, the application icon and the new PDF reports.

## 🎨 How it works

Every message goes through **message classification**: deterministic shortcuts for explicit requests, otherwise local Ollama `gemma3:1b` (`MEDICAL_CONDITION_AI_LOCAL_MODEL`). `POST /api/messages` saves the message and context, then `POST /api/classify` selects one of five flows:

- **Remedies:** resolves the condition and runs the search, with optional AI identification of unknown conditions.
- **Plant/product:** the name or alias is resolved in the catalog (ignoring case, diacritics and hyphens, and accepting Romanian inflections; a name shared by several species asks the user to choose). The answer shows the name and Latin name, the product picture when one exists, and three sections, each with its count in the title:
  - **Useful conditions (N):** the product's `positive` pairs, so N matches its ranking.
  - **Conditions with prohibitions (M):** only pairs with explicit `prohibition` wording in the sources; an AI or historical `caution` label is not enough.
  - **Warnings, contraindications and interactions:** the local model's knowledge about the product, shown in red, without source quotations.

  Titles agree with the gender and number of the Romanian name (`herbAgreement`). The first two sections have a closed “View source excerpts” panel that loads 20 whole fragments at a time, with a condition filter (`GET /api/herb-evidence/{groupId}`), highlighting the product in green and the conditions in yellow; it makes no AI call and no new search, and a changed or expired answer (`HERB_EVIDENCE_STALE`, `HERB_EVIDENCE_UNAVAILABLE`) asks the user to repeat the question. The picture comes from `GET /api/herb-images/{herb_id}`: a PNG found in `HERB_IMAGES_DIR` (default `medicina-naturista-documente/data/images`) by Latin, then Romanian name, shown at most 280 × 280 px and opened full size on click; a missing product or picture returns `404`. A missing or incompatible positive run produces the same error as the rankings, with no fallback to historical co-occurrences. The classification of sources is not clinical validation. How the prohibitions and warnings are prepared: [Warnings and prohibitions data](#warnings-and-prohibitions-data).
- **Top plants/products:** the positive ranking from `herb_positive_rankings`, filtered by category before sorting and limiting. The interface offers “Top 100 natural products” and “Top 10 natural products for flu” as clickable examples. “Top X natural products” without a condition lists the 11 categories by number to choose from; direct commands such as “Top 20 supplements” or “First 20 vitamins” also work, and “Top 100”, “general top” or “all categories” include everything. Without a quantity, 100 entries are returned (1–10000 accepted), and an unknown or multiple category asks for a single choice. The answer shows the number returned, the associations and the regional aliases, with no hybrid search or AI generation.
- **Top for a condition:** “Top 10 natural products for flu” lists only the products with a `positive` pair for that condition, and “Top 5 supplements against flu” adds a category (`pentru`, `contra` and `împotriva` are equivalent). Ordering uses `HERB_CONDITION_TOP_FORMULA` (default `2*L1+L2+100*L3`), then L3, then ID, with the filters applied before the limit N:
  - **L1:** distinct fragments with the condition in the title and a positive mention of the product.
  - **L2:** distinct fragments that mention the product and name the condition in the text.
  - **L3:** the product's total number of positive conditions.

  Each row ends with “· X fragments dedicated to the condition · Y fragments that mention it · useful in N conditions”. The values are precomputed in `herb_condition_scores` (migration `037`). Synonyms and diacritics are resolved locally; an unknown condition asks for rephrasing, and an ambiguous name or several conditions ask for a single one, keeping N and the category. Results may be fewer than N, and an unavailable ranking returns the usual error with no fallback to historical associations.
- **Miscellaneous:** searches by the original message, without AI identification of the condition. Report generation stays as in the remedies flow.
- **Report email:** a locally validated address plus the previous PDF of the same session, with no new search. The message can be an address alone or “Send the report to name@example.com”.

The classification sends local Ollama only the message and minimal routing context (no PDF or corpus), with temperature 0, no API key and no Hugging Face fallback; a JSON schema restricts the answer to the five intents and strict validation is repeated in the application. Plant names are also matched in the local catalog. On failure the existing flow continues with a notification, unclear requests ask for the plant or recipient, and nothing is retried automatically (the message identifier and revision prevent repeating a shipment).

Diagrams: [chatbot-external-connections.xmind](architecture/chatbot-external-connections.xmind) and [message-classification-plan.xmind](architecture/message-classification-plan.xmind) (XMind 8).

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

> **Local vs. external:** documents, fragmentation, indexing and retrieval run locally. Generation sends the consultation profile and the selected fragments to the model chosen in the UI: local models through `OLLAMA_API_BASE`, `deepseek-flash` through the DeepSeek API, `DeepSeek-V4-Flash` through the Hugging Face/DeepInfra router, or `grok-4.3` through the xAI API. Every model requires admin authorization, applies only to the current report and never falls back to another provider. Identifying an unknown condition sends only the message to Ollama on the host; on timeout, error or invalid answer the condition stays unidentified and no other provider is called. Delivery through Gmail is optional.

## 🛠️ Technologies used

| Area | Technologies |
|---|---|
| **Language and runtime** | Python ≥ 3.11 (documented local environment: 3.11), PowerShell, Node.js 22 for the frontend |
| **Interface and API** | React 19, TypeScript, Vite, TanStack Query, FastAPI, Uvicorn |
| **Local embeddings** | FastEmbed, ONNX Runtime, `Qwen/Qwen3-Embedding-0.6B` (optional GPU indexing, PyTorch fp16) |
| **Index storage** | PostgreSQL, `pgvector` (cosine similarity), `pg_search` BM25 (lexical search) |
| **Fragment scoring** | `4·P1 + 2·P2 + L + V` with all signals, prioritizing the condition in the title, then in the text; the patient can choose any combination of signals |
| **AI generation** | Native Ollama `/api/chat` or DeepSeek Responses API (admin only), chosen for each report, structured JSON answer |
| **Documents** | ReportLab for PDF, pypdf for processing and verification |
| **Email** | Gmail API, OAuth2 with refresh token |
| **Configuration** | python-dotenv, environment variables |
| **Running and publishing** | Docker, Docker Compose, Tailscale Funnel, PostgreSQL (`paradedb/paradedb`: pgvector + pg_search) |
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

Diacritic replacement is on by default (`--no-fold-diacritics` keeps them). To clean only the English sources, add `--source medicina-naturista-documente/data/documents/en`.

Spelling correction uses Hunspell dictionaries from `src/scripts/dictionaires/ro/` (`ro_RO`) for Romanian sources and `src/scripts/dictionaires/en/` (`en_GB`) for English ones; the language comes from the `documents/ro` or `documents/en` folder. It joins split OCR fragments, splits glued words and fixes rare unambiguous mistakes (old-spelling modernization is Romanian only). Frequencies are kept per language, and dictionary words, function words and single letters are never joined. Files outside the language folders get spelling correction only if they are detected as Romanian.

Processing is planned in memory and repeated until a pass changes nothing (at most 16 passes; a cycle or the limit aborts before any file is written). A rerun on the same corpus changes nothing, and `--dry-run` computes the same result without writing.

A document in `documents/ro` that is clearly English (at least 20 words, four distinct English function words and the EN verdict of the combined detector) is cleaned with the EN dictionary and announced as `Dictionary override ro -> en`. This affects spelling only, not the language of its fragments at indexing. Short or mixed texts keep the folder's language.

The report `var/spelling_changes.tsv` (or the path in `--spelling-report`) lists the file, line, rule, before/after forms and pass number, also at `--dry-run`. A missing dictionary stops the run before any change, and a file whose doses or numbers would change is left intact and the run ends with an error. Correction is heuristic and cannot guarantee the medical meaning of the text.

A Postgres with `pgvector` must be reachable at `DATABASE_URL` (default `postgresql://medicina:medicina@127.0.0.1:5432/medicina`). The simplest way is `docker compose up -d db`, which needs `POSTGRES_PASSWORD` in `.env`; use the same password in `DATABASE_URL`.

### 2. Synchronizing the index

The default reindex reads both `DOCUMENTS_DIR` (default `data/documents/ro`) and `DOCUMENTS_EN_DIR` (default `data/documents/en`) and publishes one atomic index; `--source-ro` (alias `--source`) and `--source-en` replace the roots. A missing, empty or overlapping folder stops the build before publishing. Sources are identified as `ro/<path>` and `en/<path>`, and fragments, statistics and rankings are filtered by language. After indexing, recommendations and warnings are prepared and published for each language with its own prompt. The dedicated analysis, prepare, resume and publish commands accept `--language ro|en` (a `RUN_ID` only works in its own language), as do `fragment_report.py`, `evaluate_retrieval.py` and the search CLI (`-Language en`).

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe src\scripts\build_hybrid_index.py
```

The script needs `PYTHONPATH=src` and reads `DATABASE_URL` from `.env`; `--model` and `--source` are optional. It runs on CPU with the Python you launch it from (GPU is below).

`TEXT_REPR_VERSION` (`"11"`, in `src/backend/ai/index_constants.py`) is a constant shared by the script and the backend, not an environment variable. Changing it makes the next run reprocess all documents, and until then the backend rejects the old index. Restart the backend after code changes; nothing reindexes automatically.

The embedding model is `Qwen/Qwen3-Embedding-0.6B` (1024 dimensions); no other model is supported. **If the database holds an index made with another model or dimension, the next build re-embeds everything**, recreating `chunks.embedding` in the same transaction; any error keeps the previous generation. GPU indexing needs a separate `.venv-gpu` with the application's dependencies, CUDA `torch` and `sentence-transformers`:

```powershell
$env:PYTHONPATH = "src"
$env:EMBEDDING_DEVICE = 'cuda'
.\.venv-gpu\Scripts\python.exe src\scripts\build_hybrid_index.py
```

`pyahocorasick` (imported as `ahocorasick`) must be installed in every environment used for indexing; the builder checks it before starting and prints the install command. For an existing GPU environment:

```powershell
.\.venv-gpu\Scripts\python.exe -m pip install --no-deps --only-binary=:all: pyahocorasick==2.3.1
```

The model is downloaded to `model_cache/` on the first synchronization; afterwards search works offline (CPU search needs the FastEmbed/ONNX model, even when indexing used the GPU). Later synchronizations process only new or modified documents and drop deleted ones; changing the conditions catalog, the model or the text preparation requires a full rebuild. Progress and the estimated remaining time show in the terminal.

**Reindexing creates the database if it is missing and applies the SQL migrations.** This needs permission to create the database, schema and extensions (optionally a separate account in `DATABASE_BOOTSTRAP_URL`). The web application never migrates at startup. Conditions, plants and synonyms are read from PostgreSQL; add to them through new migrations in `src/backend/migrations/`, never by editing applied ones.

During synchronization, search and the source list return `503`, while generation from fragments already found and PDF downloads continue. The new index is published only after all vectors are computed and validated, so a failure keeps the previous one. A missing or invalid catalog blocks search, and an incompatible index returns `INDEX_RESYNC_REQUIRED`. To rebuild an index, keep the documents, migrations, model and configuration; owner authorizations need a separate backup.

Search uses only the selected sources: an empty selection searches nowhere, and if only some selected sources have disappeared, the valid ones are kept with a warning (if all have, a new selection is requested).

In batch generation, a citation of a nonexistent fragment or of one from another batch invalidates the answer and stops the report (nutrition elements without citations are exempt). No partial PDF is published, and the search is kept for a manual retry. Citation checking is not medical validation, and the AI client logs hold only technical diagnostics.

To preview the fragments without writing to the index or computing embeddings (needs the migrated catalog):

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

If you synchronized the index in step 2, the migrations are already applied; for an existing database, run them separately with `.\.venv\Scripts\python.exe -m scripts.migrate_database` (`PYTHONPATH=src`). The chat is at `http://127.0.0.1:7860/` and the owner login/logout form at `/owner` (`/medicina/owner` under the public prefix). The form posts the key to `POST /api/owner/login` with CSRF, and `POST /api/owner/logout` revokes the token. Authorization survives restarts until logout or key rotation. Never put the key in the URL or terminal history; the old `?key=` route remains only for compatibility. `/healthz` checks the AI provider configuration, and `/readyz` adds index availability and compatibility.

For message classification and local condition identification, run Ollama on `CONDITION_AI_LOCAL_BASE` (default `http://localhost:11434/v1`) and download the model once with `ollama pull gemma3:1b`. It is separate from the report-generation provider.

For interface development with automatic reload, run `npm run dev` in `src/frontend/`. Vite serves the interface at `http://localhost:5173/medicina/` and proxies API requests, health checks and the owner form to the production backend `https://cristiantone.taila68086.ts.net/medicina/`, which must be reachable (`npm run dev` does not start it). `DEV_BACKEND_URL` overrides the address; to use a locally started backend:

```powershell
$env:DEV_BACKEND_URL = "http://127.0.0.1:7860/"
npm run dev
```

The local interface is then at `http://localhost:5173/`. To return to the default backend, run `Remove-Item Env:DEV_BACKEND_URL -ErrorAction SilentlyContinue` and restart Vite. `PUBLIC_BASE_PATH` sets the path for the production build.

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
| `GET /api/report-models` | All the configured models in env order, `defaultModel` (the first model) and `allowedModels` (those permitted to the current user). The visible list is the same for the public and the author; rights are checked separately. For admin only, it also adds the default values of the generation limits, displayed in the panel: `batchMaxTokens` (per model), `batchWorkers` (`max`, `300`) and `maxOutputTokens` (per model). |
| `GET /api/report-duration-estimate?model=...&characters=...` | The estimated duration in seconds and the number of measurements, using all the model's rows in `report_generation_metrics`. Aggregates only, without conditions or medical texts. |
| `GET /api/report-output-recommendation?model=...&effort=...` | The output limit per batch (`recommendedTokens`) that the measured reports of the same model and effort would have fitted, plus 25%, and the number of measurements (`sampleCount`). `recommendedTokens` is `null` below 3 measurements. It comes from `report_generation_metrics.max_batch_output_tokens`, the largest output (reasoning included) of any request of a published report. The panel (admin only) starts from the larger of the catalog default and this value and blocks generation below it. |
| `GET /api/searches/{search_id}/report-batches?model=...&minScore=...&effort=...&batchMaxTokens=...&maxOutputTokens=...` | The number of batches that generation would produce, computed with the same partitioning (`partition_evidence`) from the fragments that reach the minimum score and the chosen limits; it does not call the AI provider. The report panel displays it under “Estimated duration”. |
| Token limits in the report panel (admin only) | Positive integers (groupings like “26 200” / “26.200” are accepted), at most 2,000,000; the minimum input is 1,000. The output must be smaller than the model's `context` (from `REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL`), and `context − output − thinking` must leave at least 1,000 input tokens. “Max thinking tokens per batch” is shown only while the effort lets the model think (medium/high); it starts at the model's `thinking` value, is added to the output limit (which stays the answer's budget) and may be at most a quarter of one request's context. Otherwise the server responds 422 (`OUTPUT_TOKENS_TOO_LARGE`, `THINKING_TOKENS_TOO_LARGE`, `INPUT_TOKENS_TOO_SMALL`, `INPUT_TOKENS_NO_ROOM`). A typed thinking budget is used as typed, for medium and high alike; without it, vLLM medium uses half of `thinking` and the other models use the budget learned from earlier batches. The panel applies the same rules before the request, displays the effective input when the context reduces it, and warns (without blocking) below 2,000 output tokens, when each fragment ends up in a separate batch or when a single fragment exceeds the limit. |
| `POST /api/searches/{search_id}/generate` | Receives `minScore` and `model` from the catalog; without a model it uses `REPORT_GENERATION_MODELS`. Any model without admin authorization → HTTP 403; unknown model → HTTP 422. Applies the selected threshold and processes the batches in parallel according to `batchWorkers` from the request (integer `0`-`300`; `0` and `1` process in succession; without the field, `REPORT_BATCH_WORKERS`, default 2), within a single active report. The optional fields `batchMaxTokens` and `maxOutputTokens` (positive integers) override for this report `REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL`, respectively the configured output limit; for fixed-context models (R1 8B), `maxOutputTokens` must be smaller than the context, otherwise HTTP 422. The same options with the same `requestId` are idempotent; different options → HTTP 409. Generates a single PDF after all batches are validated. A batch whose answer fails validation (for example an empty placeholder item) is requested once more; if the second answer is also invalid only because of malformed items (`INVALID_ITEM`), the batch keeps its valid items and the report is labelled partial, instead of discarding every batch. Answers that are not JSON objects, or that cite unknown or missing evidence, still fail the report (`AI_RESPONSE_INVALID`). |
| `GET /api/reports/{tab_id}/{report_id}` | Downloads the PDF generated in the tab's session. |
| `POST /api/session/end`, `POST /api/session/unload` | Close the tab's session (on request, respectively when the page is closed). |

## Sessions, retention and owner authorization

- **Sessions:** the application can be opened simultaneously in several tabs or browsers from the same PC/IP. Each full page load, including refresh, Shift+F5 or duplicating the tab, starts a new conversation. The identifier is kept only in the page's memory; retries and reconnections from the same page continue the current conversation. The global session limit and the per-minute session-creation limits remain active.
- **Retention:** the history, the fragments and the PDFs stay in process memory. The session expires after one hour of inactivity or at most four hours (`SESSION_IDLE_SECONDS`, `SESSION_MAX_SECONDS`). Closing the page tries to close the session; if the notification does not reach the server, expiry frees the data. Restarting the application removes them. At most 12 searches and 12 reports are kept per session, within the memory budgets.
- **Owner / admin:** set `OWNER_KEY` and authenticate the browser through the `/owner` form to use the external models `deepseek-flash`, `huggingface-deepseek-v4-flash` and `grok-4.3`. The four Ollama models are available without authorization. The “AI model” selector follows the “Minimum score” field; the list updates when returning to the page after authentication. The API checks authorization at each generation with an external model and when reading/cancelling its job. PostgreSQL keeps the token hash and technical data, without conversations or PDFs. Authorization survives a restart; logout revokes it, and changing the key invalidates the existing tokens.

## Plant and product catalog

The catalog and the aliases are read from PostgreSQL. It currently has **1,585 entries in 11 categories**: `plante medicinale` (medicinal herbs), `fructe` (fruits), `legume` (vegetables), `cereale` (cereals), `seminte` (seeds), `uleiuri esentiale` (essential oils), `uleiuri` (oils), `suplimente` (supplements), `aminoacizi` (amino acids), `vitamine` (vitamins) and `minerale` (minerals). Bee products, fibers, probiotics and prebiotics belong to `suplimente`, and there is no medicines category (`aspirina` was removed by migration 026). Categories are technical groupings, with no claim about medical status or efficacy, and they are never used as matching names or aliases. Catalog migrations `014`–`026` added the supplement and food products and reorganized the categories; each keeps the existing IDs, names, aliases, associations and rankings and refuses unexpected identities.

The API intent `planta` covers every product, recognized by its `ro` and `en` names regardless of case, diacritics or hyphens. Products without a species return `species=[]` and are shown without empty parentheses. In plant requests the full name or alias takes priority; otherwise the beginning of a Romanian name, by whole words, offers the candidate species (“plop” asks to choose between plop alb, plop negru, plop tremurător and plop tremurător american). Romanian inflections and wordings with plant parts (“mugurii de plop”) are accepted, and after the choice only the selected species is used. This partial matching does not apply to mentions in the corpus or to citations in reports.

**Tops.**

- “Top N plants” ranks products by the number of distinct conditions with positive recommendations found in the sources, with the regional names and no report. Each entry reads “useful in X conditions” (in agreement with the Romanian name), and a note says that warnings, contraindications and mixed relationships are excluded and that the classification is not clinical validation. The general lists of conditions of a product keep the historical associations, warnings included.
- Per-condition tops reuse this ranking after filtering the positive pairs for the requested condition. They need no migration or reindexing, only a published and compatible positive run.
- Each non-empty top shows, under the title, how to select a product by number (example `1`), before the score explanation and the list. The next message can then be just a position number: `1` opens the same details as the question “what is olive oil good for” for the first product, using the displayed order and no new AI classification. A number outside the list asks for a valid choice and keeps the list; any other request ends the selection.

**Associations.** `build_hybrid_index.py` rebuilds the `herbs_benefits` associations and the `herbs.ranking` ranking automatically, in the same transaction as the index. An association means that the fragment's title names the condition (`primary_medical_conditions`) and the text mentions the plant or an alias. Negative mentions and contraindications are included, so an association does not prove a therapeutic benefit. Extending the catalog or changing aliases rebuilds the associations without recomputing the embeddings of unchanged documents. For an explicit rebuild or audit:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --rebuild-herbs
.\.venv\Scripts\python.exe -m scripts.audit_herbs
```

**Catalog changes without reindexing.** Additions and corrections are made through new SQL migrations in `src/backend/migrations/`, keeping the existing IDs. When a migration adds or reclassifies products, apply it separately from the code change: deliver the compatible code, keep a backup verified by restoration, save the fingerprints (including `xmin`) of `documents`/`chunks`, the catalog, associations and metadata, briefly stop the application, then run only the association rebuild:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m scripts.migrate_database
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --rebuild-herbs-only
```

This mode needs an existing, compatible index and does not scan the corpus, fragment it or load the embedding model. It publishes the associations and ranking differentially in one transaction and updates only the five `herbs_benefits_*` keys. It allows additions with new IDs, but changing or deleting old names, or any change to the old pairs or rankings, stops publishing. `--rebuild-herbs` is the general flow that also synchronizes modified documents; do not use it here. Afterwards the documents/chunks, embeddings, generation and base metadata must be identical to the saved fingerprints; check `/healthz`, `/readyz` and the tops before starting the application. If the rebuild fails after the migration commit, fix it or restore the backup before starting, and do not run the full reindex. A changed catalog fingerprint also requires the positive tops to be prepared and published again, reusing the compatible cache.

A missing or invalid catalog, or unsynchronized associations, block plant results with an explicit error (`503`).


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
| `HERB_SAFETY_GENERATION_MODEL` | `ministral-3:8b` | The local Ollama model of the generation stage of the safety extension; required while the extension is active. On 10 known products, ministral gave the most specific messages among the local models tested. The stage identifier in the cache remains `qwen`, for historical reasons. |
| `HERB_SAFETY_DEDUP_MODEL` | `gemma4:12b` | The local Ollama model that groups equivalent messages. Compared on St John's wort with qwen3.5:9b and qwen3.5:4b: it found 3 of 3 real pairs. |
| `HERB_SAFETY_MINISTRAL_BATCH_SIZE` | `10` | Products per request to the local generation model (and per dedup request). Validated against the output ceilings only while the extension is active. |
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

## Warnings and prohibitions data

The “Conditions with prohibitions” and “Warnings, contraindications and interactions” sections of a product are prepared offline, never at chat time. The application never migrates at startup: the migrations below are applied through the normal indexing command or `python -m scripts.migrate_database`.

### Prohibitions (caution ranking)

Migration `028_herb_caution_rankings.sql` creates the `herb_caution_*` tables. The caution projection reuses the `recommendation`/`prohibition` answers that the positive classification already requests, so it adds no AI requests; version 2 also checks explicit lists of foods to avoid, including broken OCR lines. A warning about another product or procedure in the same fragment does not validate a prohibition. Prohibitions come from `herb_caution_pairs` with explicit `prohibition` evidence, from the caution run linked to the active positive run, and match `herb_caution_rankings.prohibition_ranking`; cautions are kept separate and not counted. Positive preparation also prepares caution, and publishing activates both runs atomically. To populate it separately, without inference or reindexing:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --prepare-caution-ranking
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --publish-caution-ranking RUN_ID
```

The first command prints the new run ID and the number of unknown historical evidence items (recovered locally or marked `unknown`); the second accepts it only if the index, the positive run and the observed activation are still compatible. Both report `ai_requests_sent_total=0`. Updating from projection 1 to 2 needs only a new caution run, with no reindexing; the old run is shown as outdated until the new one is published. A missing caution part is shown as unavailable, and unrecoverable historical data is marked partial.

### Warnings, contraindications and interactions

The section uses only the local Ollama model's knowledge about each catalog product, regardless of category or whether documents mention it. One request is sent per product without a compatible cached result, containing only the product's identity (ID, Romanian and Latin names, English names, category, family, aliases), never fragments or conditions. The answer is strict JSON (`herb_id`, `status=complete|uncertain`, `messages`), each message with a `message_type` (`warning`, `contraindication` or `interaction`) and a `problem` in Romanian (10–25 words preferred, at most 240 characters). Interactions cover medications, supplements, other natural products, foods and drinks. Uncertain identity is marked `uncertain`, and an empty list does not confirm the absence of risks. Valid JSON and a correct identity are not clinical validation.

In the interface the section is red, in two columns (one at most 580 px), each message starting with its bold category and with no “View source”. `GET /api/herb-safety/{groupId}` reads only the published generation, in pages of 20; a changed generation or catalog returns `HERB_SAFETY_STALE`.

Migration `031_herb_product_safety_knowledge.sql` creates `herb_safety_messages` plus the run, result and cache tables (the legacy fragment-based safety tables are dropped by migration `039_drop_legacy_herb_safety_tables.sql`). The cache key covers the product identity and aliases, prompt, JSON rules, model and its digest, so a change affects only the products involved. Each result is saved immediately, an invalid answer stops the preparation and keeps the published generation, and there is no retry or repair. The first population needs one request per product, and later reindexes only the products without a compatible cache. Normal positive preparation also prepares and publishes this data (`--skip-positive-ranking` skips it), or run it separately:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --analyze-safety-warnings
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --prepare-safety-warnings
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --prepare-safety-warnings --resume-safety-warnings RUN_ID
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --publish-safety-warnings RUN_ID
```

Analysis runs no inference, and publishing checks only the database and the model digest. After an interruption, wait for the prompt before relaunching. Progress is reported under `progress_stage=product_safety`. Defaults: `HERB_SAFETY_AI_MAX_REQUESTS=10000`, `HERB_SAFETY_BUILD_TIMEOUT_SECONDS=86400`, `HERB_SAFETY_AI_CONTEXT_TOKENS=65536`, `HERB_SAFETY_AI_MAX_OUTPUT_TOKENS=40000`, 900 s per request, `think=false`, temperature 0.

### Bilingual extension (migration 036)

While `HERB_SAFETY_EXTENSION_PRODUCTS` is empty, the flow above is unchanged. When it is set, `--prepare-safety-warnings` rebuilds the messages of the in-scope products for both languages in a single run, with the local model `HERB_SAFETY_GENERATION_MODEL` (batches of `HERB_SAFETY_MINISTRAL_BATCH_SIZE`). Each message is returned in Romanian and English with the same type, and the prompt asks for at least 7 messages per product without padding. Valid answers are cached per product and stage, so a retry resends only the missing products. Exact duplicates are removed deterministically and semantic ones by the local model `HERB_SAFETY_DEDUP_MODEL`, once per bilingual message so the RO and EN lists stay identical; the removed pairs are written to `aiWork/herb_safety_dedup_pairs.json`. Preparation creates two generations and prints `run_id_ro` and `run_id_en`, each published separately with `--publish-safety-warnings RUN_ID`. Normal reindexing also runs this extension at the end and publishes both. For a pilot, then full activation, set `HERB_SAFETY_EXTENSION_PRODUCTS=hypericum perforatum`, then `first:100` and `all`:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --analyze-safety-warnings
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --prepare-safety-warnings
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --publish-safety-warnings RO_RUN_ID
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index --publish-safety-warnings EN_RUN_ID
```

## 📦 Database schema

The index lives in Postgres (`pgvector` and `unaccent` extensions). The tables below are the result of all the migrations in `src/backend/migrations/`.

**Documents and fragments**

| Table | Content |
|---|---|
| `documents` | One row per source file, keyed by `relative_path` (`ro/<path>` or `en/<path>`): `absolute_path`, `size_bytes`, `modified_utc`, `sha256`, `encoding`, `line_count`, `char_count`. `category_id` is generated from the path (the folder without the language prefix, empty at the root). Used to skip unchanged files at synchronization. |
| `chunks` | One row per fragment (`chunk_id`), tied to its document by `source_relative_path` (cascading delete): `source_absolute_path`, `source_sha256`, `line_start`, `line_end`, `heading` (path of headings), `text`, `text_sha256`, `char_count`, `language` (`ro`/`en`), `category_id` (generated from the path, used by source filtering), `business_category` (`R1`/`R2`/`D1`), `primary_medical_conditions` and `secondary_medical_conditions` (`text[]`, GIN-indexed), `embedding vector(1024)`. The vector is searched exactly, without an ANN index; the lexical search uses the BM25 index `idx_chunks_bm25` (`pg_search`), which has no table of its own. |
| `sync_metadata` | Key/value pairs: `model_name`, `model_dimension`, `passage_profile`, `text_repr_version`, `dictionary_fingerprint` (with its version), `index_generation`, `last_synced_utc`, the five `herbs_benefits_*` markers and the active positive run per language (`herb_positive_active_run`, `herb_positive_active_run_en`). |

**Conditions and catalog**

| Table | Content |
|---|---|
| `medical_conditions` | `id`, `name` (unique canonical Romanian name) and `en` (English equivalent, required); the identity is shared by both languages. `medical_conditions_version` holds a single row with a version counter. |
| `medical_condition_synonyms` | `id`, `medical_condition_id` (cascading delete) and `synonym`, unique per condition. |
| `herbs` | `id, category, family, latin, ro, en, ranking`. `category` is one of 11 values: `plante medicinale`, `fructe`, `legume`, `cereale`, `seminte`, `uleiuri esentiale`, `uleiuri`, `suplimente`, `aminoacizi`, `vitamine`, `minerale`. The four botanical categories have a unique lowercase `latin` and a `family`, and lowercase `ro`/`en`; all other products have `latin` and `family` NULL, keep the capitalization of `ro`/`en`, and a unique `lower(btrim(ro))`. `ranking` counts the distinct conditions associated through fragment titles. |
| `herb_aliases` | `id, herb_id, name, kind` (cascading delete); lowercase aliases, unique per `(herb_id, kind, name)`, with `kind` in `ro_regional`, `latin_synonyms`, `en_alt`. |
| `herbs_benefits` | Co-occurrences `id, herb_id, medical_condition_id, language`, unique per language, published atomically at the end of reindexing. |

**Rankings, safety and operations**

| Tables | Content |
|---|---|
| `herb_positive_runs`, `_evidence`, `_pairs`, `_rankings`, `_cache` | The positive classification of product–condition pairs, per run and language. |
| `herb_caution_runs`, `_evidence`, `_pairs`, `_rankings`, `_cache` | The prohibition and caution projection, linked to a positive run. |
| `herb_condition_score_runs`, `herb_condition_scores` | L1, L2 and L3 per product and condition for the per-condition tops, keyed on the positive run. |
| `herb_product_safety_runs`, `_results`, `_cache`, `_extension_cache`; `herb_safety_messages` | Warnings, contraindications and interactions per product and language. |
| `report_generation_metrics`, `report_batch_usage` | Aggregate report-generation measurements, without conditions or medical text. |
| `owner_sessions` | Owner authorizations: token hash and dates, no conversations or reports. |
| `schema_migrations` | The ledger of the SQL migrations applied once. |

If the index profile and the catalog fingerprint are unchanged, a document with the same SHA-256 is skipped at synchronization; a new or modified document replaces its fragments in a single transaction.

Fragmentation (`src/backend/ai/fragmenter.py`) reads the conditions from `medical_conditions` and the synonyms from `medical_condition_synonyms`, in insertion ID order. Python adds the canonical name to the list of matching terms, without duplicating it in the synonyms table. Then it applies in turn:

| Category | Criterion |
|---|---|
| **R1** | The title of a Markdown chapter names a condition → the title and its whole remaining free subtree (subchapters with their own condition become separate fragments). |
| **R2** | The own text of a remaining chapter (up to the next title) mentions a condition → the title and that text. |
| **D1** | The rest of the text (including documents without titles) → pieces of ~1800 characters (1500–2100), cut at the end of a paragraph or sentence, with an overlap of at most 270 characters. |

Conditions are searched as whole words, without diacritics and capitals, with tolerance for Romanian endings (`gripa`/`gripei`). File and folder names are not compared with the conditions. R1 and R2 fragments receive `primary_medical_conditions` (the conditions in the title) and `secondary_medical_conditions` (the conditions in the text); D1 has no conditions. R1 and R2 have no length limit. A condition that is primary is removed from `secondary_medical_conditions` of the same fragment: the idempotent script `src/backend/index_sql/001_remove_primary_from_secondary_conditions.sql` runs on every indexing, in the publication transaction, and migration `040_remove_primary_from_secondary_conditions.sql` cleans the rows indexed earlier without reindexing (afterwards run `--rebuild-condition-scores` for each language so that the per-condition tops recompute L2).

At search time, each fragment receives the score `4·P1 + 2·P2 + L + V` (maximum 8, with all signals ticked): P1 = the searched condition is in `primary_medical_conditions`, P2 = it is in `secondary_medical_conditions`, L = the BM25 of the fragment divided by the best BM25 of the search (the interface shows the raw BM25), V = the semantic similarity rescaled between the median and the maximum of the search. The patient can untick signals in the “Sources and search options” panel, and the formula adapts (for example `L + V` or only `2·P1 + P2`). The score is not stored in the DB; details are in [fragment-search-and-scoring.xmind](architecture/fragment-search-and-scoring.xmind).

For embeddings, a fragment longer than 1400 characters is split into windows that overlap by 240, and their vectors are averaged (the values, vector dimension and text prefixes of each model are in its profile in `ai/embedding_model.py`). Diacritics are preserved through Unicode NFC normalization.

## 🐳 Running with Docker Compose

Before building, make sure these exist: `medicina-naturista-documente/data/documents/`, `model_cache/` (with the embedding model already downloaded, because the container runs offline) and a local `.env` with `POSTGRES_PASSWORD`, `OWNER_KEY` and the key of the chosen AI provider (`X_API_KEY`, `DEEPSEEK_API_KEY`, `HF_TOKEN` or `OLLAMA_API_KEY`).

The stack has these services:

- **`db`:** Postgres 16 with `pgvector` (`shared_buffers=512MB`), exposed only on `127.0.0.1:5432` (`DB_HOST_PORT`). Synchronize the index from the host with `python src/scripts/build_hybrid_index.py` (`PYTHONPATH=src`, and a `DATABASE_URL` pointing to `127.0.0.1` with `POSTGRES_PASSWORD`) after starting `db` and before using search.
- **`app`:** published on `127.0.0.1:8760` (`APP_HOST_PORT`; the container port stays 7860) and, from there, through Tailscale Funnel, which handles HTTPS. It runs read-only, as a non-root user, without extra Linux capabilities; the documents are mounted read-only and temporary files go to `tmpfs`. The index lives in the `pg_data` volume, so resynchronizing does not require stopping the application.
- **`vllm-supervisor`:** starts and stops the vLLM report containers on demand (see below).

```powershell
docker compose up -d --build
docker compose --profile vllm-report create
docker compose ps
Invoke-WebRequest http://localhost:8760/healthz
```

To stop without deleting data, run `docker compose down`.

> [!WARNING]
> `docker compose down -v` deletes the Compose volumes, including the Postgres index (`pg_data`). The Ollama models on the host are managed separately.

### Ollama on the host

**Ollama runs separately, on the host (Windows), and must be started before the application.** The `app` container reaches it at `http://host.docker.internal:11434/v1` for message classification and condition identification (`CONDITION_AI_LOCAL_BASE`) and for Ollama reports (`OLLAMA_API_BASE`). Download the report model with `ollama pull gemma4:12b` and the model set in `MEDICAL_CONDITION_AI_LOCAL_MODEL` (default `gemma3:1b`); the host's Ollama manages them. Verify the connection from the container:

```powershell
docker compose exec -T app python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/api/version', timeout=5).read().decode())"
```

The client uses Ollama's native `/api/chat` (derived from `OLLAMA_API_BASE` by removing `/v1`) with JSON format, `truncate=false` and `shift=false`: input is never shortened silently, and exceeding the context returns `AI_CONTEXT_LIMIT_EXCEEDED` (select fewer fragments or raise the minimum score). Classification and identification use `think=false` and `reasoning.effort=none`, so thinking models spend their budget on the final JSON.

Each request sends `keep_alive=60` (the model is released after 60 seconds of inactivity, with no preloading at startup), while reindexing uses `keep_alive=3600`. When reindexing or an explicit ranking/safety preparation ends (or fails, or is interrupted with Ctrl+C), `build_hybrid_index.py` asks Ollama to unload the indexing model; the `index_model_release` event reports `released` or a `warning` without changing the indexing result.

For `gemma4:12b` with the maximum context of 262,144 tokens, the configuration measured on the local GPU sets these variables **on Windows** (PowerShell):

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION", "1", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_KV_CACHE_TYPE", "q8_0", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL", "2", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH", "262144", "User")
```

Fully close Ollama from the notification area, start it again and check the effective values in `%LOCALAPPDATA%\Ollama\server.log`. These variables configure the Ollama server, so putting them in `.env` or in the Compose `app` environment has no effect. A quantized KV cache lowers precision, and the speed measurement does not validate report quality on long inputs. For batches to run simultaneously, `OLLAMA_NUM_PARALLEL` must be at least `REPORT_BATCH_WORKERS` (default 2); otherwise requests are processed in succession. The application itself keeps `MAX_CONCURRENT_GENERATIONS=1`. Measurements and their limits: [Ollama investigation](aiPlans/2026-10-15-investigare-performanta-ollama.md).

After changing `.env`, recreate only the application with `docker compose up -d --no-deps --force-recreate app`.

### vLLM report models

`docker compose up` starts no vLLM server. The `create` step above only creates the report containers (`vllm-qwen35`, `vllm-qwen25`); repeat it after changing those services. A report with a vLLM model starts that model's container, waits until `/v1/models` lists the model (the browser shows a warm-up dialog meanwhile) and then sends the requests. The server stays up until a report needs the GPU for another model: an Ollama report, or the other vLLM model, stops it first. When a local report (Ollama or vLLM) uses a different model from the previous local report, its first step is to unload all Ollama models from the GPU, so a model left over from an earlier report does not hold VRAM; repeating the same model releases nothing. The previous model is remembered in memory only, so the first local report after an app restart releases once. Reports with DeepSeek, xAI or Hugging Face leave the GPU untouched. To free the GPU by hand (reindexing, translation, large Ollama models):

```powershell
docker compose --profile vllm-report stop vllm-qwen35 vllm-qwen25
```

`vllm-supervisor` is the only container with the Docker socket, which is root-equivalent on the host. It can start and stop only the two vLLM report servers, refuses to start one while the other (or `vllm-translate`) is running, and only the application can reach it. Set `MODEL_SUPERVISOR_URL` empty to manage the servers by hand.

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
| `VLLM_API_BASE` | `http://localhost:8001/v1` | The address both vLLM report servers share (only one runs at a time); in Docker Compose `http://vllm-report:8000/v1`. |
| `MODEL_SUPERVISOR_URL` | empty (`http://vllm-supervisor:8080` in Docker Compose) | The service that starts and stops the vLLM report servers when a report needs them. Empty means no lifecycle control: the operator starts the server by hand, as in a native run. |
| `VLLM_WARMUP_TIMEOUT_SECONDS` | `900` | How long a report waits for a started vLLM server to list its model before it fails with `VLLM_WARMUP_TIMEOUT`; the first start also downloads the weights. Warm-up does not count against the report time limit. |
| `OLLAMA_MAX_OUTPUT_TOKENS_BY_MODEL` | `{"ollama-deepseek-r1:8b":8192}` | JSON object with the output limit per Ollama model. Omitted keys keep the default values from the catalog (R1 8B: 8192); the other models use the catalog default (20000). The values must be positive integers, and the output must be smaller than the context from the catalog (R1 8B: 32768). Unknown keys, external models and duplicates are rejected. It is the default value displayed in the report panel (admin only), where it can be overridden per report. |
| `MEDICAL_CONDITION_AI_LOCAL_MODEL` | `gemma3:1b` | The local Ollama model for message classification and condition identification; downloaded on the host with `ollama pull <model>`, including when the application runs in Docker. |
| `REPORT_GENERATION_MODELS` | the 9 models of the catalog below that are not local vLLM models | Ordered CSV list of the available models. The first is the default. The order in the UI is the same; rights control generation, not the visibility of the options. Empty lists, empty elements, unknown models and duplicates are rejected at startup. The choice in the UI applies only to that job. |
| `REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL` | `24000` for R1 8B, `25000` for the others; context from the catalog; effort `low` | JSON object with one entry per model: `{"tokens": …, "context": …, "effort": …, "thinking": …}`. `tokens` (required) is the input token budget per batch; it includes the complete serialized request and a reserve of 256 tokens, with local counting estimated at 3 UTF-8 bytes per token. `context` is the model's context window: it is displayed under the chosen model in the panel and limits the output (input + output fit within it). Startup is refused if the default output of an active model leaves fewer than 1,000 input tokens; for R1 8B it must match `num_ctx` from the catalog (32768). `effort` (`low`/`medium`/`high`) is the preselected effort when the user chooses the model. `thinking` is the default thinking budget of a batch (8000): with effort `medium` or `high` it is added to the output limit chosen in the panel, which stays the budget of the JSON answer, and it is capped at a quarter of the request context. `context`, `effort` and `thinking` are optional and have default values from the catalog/`low`/8000; `thinking` may be `0` for a model that does not think. Missing/empty value → the default values; an explicit object must include every enabled model. `tokens` is also the default value displayed in the report panel (admin only), where it can be overridden per report. The value can be written over several lines in `.env`, between single quotes. |
| `REPORT_BATCH_WORKERS` | `2` | Positive integer: the maximum number of batches processed simultaneously in the active report. `1` processes in succession. It does not change the limit of a single active report. It is passed explicitly to the application through Docker Compose. The report panel (admin only) has an editable field from `0` to `300`, starting at `0` (in succession); `0` is sent as `1`. |
| `CONDITION_AI_LOCAL_BASE` | `http://localhost:11434/v1` (direct) / `http://host.docker.internal:11434/v1` (Compose) | The Ollama address on the host, used for message classification and condition identification. |
| `CONDITION_AI_TIMEOUT_SECONDS` | `10` | Timeout for condition identification through local Ollama. |
| `MESSAGE_CLASSIFICATION_TIMEOUT_SECONDS` | `10` | Timeout for classification through local Ollama, independent of condition identification. |
| `MESSAGE_CLASSIFICATION_MAX_OUTPUT_TOKENS` | `300` | The classification JSON budget. |
| `CONDITION_AI_MAX_OUTPUT_TOKENS` | `300` | The answer limit (a small JSON) for condition identification. |
| `REPORT_GENERATION_AI_STREAM` | `false` | Requests the answer as an event stream (`stream: true`). The read timeout applies between events, so it avoids long requests being cut by a proxy (e.g. 504 after 60 s at the HF router). If the provider does not support streaming, leave `false`. |
| `REPORT_GENERATION_READ_TIMEOUT_SECONDS` | `720` | The read timeout of the request to the AI provider. |
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

`src/scripts/extract_pdf_markdown.py` converts a PDF to Markdown locally, infers titles and reading order, and keeps `<!-- Pagina PDF N -->` page markers. Install the optional dependencies, then run:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[pdf]"
.\.venv\Scripts\python.exe src\scripts\extract_pdf_markdown.py "book.pdf"
```

By default the output is `medicina-naturista-documente/data/documents/ro/Surse sigure/book/book.pdf.md` (a folder named after the PDF without its extension, a file keeping the full PDF name plus `.md`), resolved from the project root whatever the launch directory. `-o` / `--output` chooses another file, and `--report` writes a JSON report.

**Text source, per page.** PyMuPDF extracts characters and fonts. Each page is straightened and its columns detected automatically. A page with a real text layer keeps that text. A scanned page carries an old OCR layer that can silently drop paragraphs, so its layer is trusted only if three checks against the page image pass: no dark pixels outside the layer's text boxes, no garbled symbol strings, and a low share of words missing from the bundled Hunspell dictionary (`src/scripts/pdf_layer_check.py`). A page that fails them, or has no layer, is transcribed by a local vision model served by Ollama (`src/scripts/pdf_vision.py`, default `qwen3.5:9b`, address from `OLLAMA_API_BASE`, default `http://localhost:11434/v1`), which is unloaded when the run ends. Without Ollama or the model, those pages fall back to Tesseract in memory (`ron` and `eng` data from `--tessdata` or `TESSDATA_PREFIX`; on Windows `C:\Program Files\Tesseract-OCR\tessdata` is detected), and the report says so. The page image sent to the model is cropped to the printed area, which cuts the tokens per page and the time.

The output never contains diacritics (`ț`, `ș`, `ă`, `â`, `î` become `t`, `s`, `a`, `a`, `i`), in the file header and in the text.

**Headings.** Chapters are not guessed page by page. Without a PDF outline, the script reads the running heads in the text layer, recovers the chapter list and opening pages (`src/scripts/pdf_chapters.py`), and writes one `## CHAPTER TITLE` where each chapter opens; the page's own title lines, running head and lone chapter number are removed, and other headings move one level down. A book without running heads, or with an outline, is left as is, and a head that the old OCR misread on every page is not recognized. Below the chapters, heading levels come from the printed font size in the text layer compared with a size learned from the whole book (`src/scripts/pdf_headings.py`): sections get `###` and parts `####` (a heading ending in a colon is always a part), so a section stays whole for the fragmenter. If the evidence is too thin, the model's own choice is kept. On vision pages, decorative `---` rules are dropped and a “heading” that is really a paragraph is turned back into one, with its label in bold.

`src/scripts/fix_markdown_headings.py "book.pdf.md" "book.pdf"` applies the same heading rules to an existing Markdown file, with no AI call. It changes only heading marks, `---` rules and bold labels, and rewrites the file (`-o` writes elsewhere), so keep a copy.

Useful options (`--help` lists all):

- `--start-page N --end-page N`: convert a range of pages.
- `--ocr vision|auto|always|never`: `vision` (the command-line default) transcribes every page with the vision model; `auto` applies the per-page choice above and is faster; `always` forces Tesseract; `never` uses only the existing text layer. The `Options` class defaults to `auto`, so library calls and tests need no Ollama.
- `--vision-model NAME`: another Ollama model with vision support.
- `--workers N` (default 1): pages sent to the vision model at once. Ollama runs `qwen3.5` requests one after the other, so `N` above 1 saves no time with it; use it only with a model and Ollama version that serve requests in parallel.
- `--columns auto|1|2|3`, `--deskew auto|off`, `--max-skew`, `--dpi` (default 250), `--lang` (default `ron+eng`), `--password`, `--tessdata`.
- `--debug`: logs entry into each function with parameter names (passwords masked, large objects summarized).

The JSON report records the method used for each page (`text`, `vision` or `ocr`), why a scanned page's layer was rejected, the chapters and per-page warnings. Markdown and report are prepared before the old results are replaced, and a failed publish restores the previous versions. OCR rendering is limited to 64 megapixels per page, so lower `--dpi` for very large pages. Check titles, tables and degraded scans: the structure is inferred heuristically and OCR errors are not corrected semantically.

`src/scripts/merge_book_pdfs.py` merges `pag<first>-<last>.pdf` fragments into one PDF, straightening each page in memory with PyMuPDF and without OCR. It warns on page-count mismatches and missing ranges and rejects overlapping ranges. By default the result is saved in the project root, named after the source folder; `--output-dir` changes the destination and `--deskew off` disables straightening. The final PDF is verified before the destination is replaced atomically, and the sources are protected against overwriting.

## Background report generation

### Models and access

The supported models are defined in one backend catalog (`src/backend/core/report_models.py`). `REPORT_GENERATION_MODELS` is the comma-separated list of enabled models, in UI order; the first is the default. `GET /api/report-models` returns all configured models in `models`, the first in `defaultModel` and the ones the current user may use in `allowedModels`.

Report generation is reserved for the administrator, for every model including local Ollama. The public sees all options but gets the message “Recipe generation is available only to the platform administrator.” and a disabled button. On the backend, a request without a valid administrator session gets HTTP 403 `MODEL_FORBIDDEN` before the job is admitted or any AI is called. A request without a model uses the first configured one, with the same check and no automatic switch; a model that is not configured gets HTTP 422 `MODEL_NOT_CONFIGURED`. Reading the status of a job and cancelling it also require the administrator session.

The chat confirmation (“The report is ready and was generated in …”) names the model in bold, and the end of the PDF shows `AI model used: <model>`. Both use the identifier fixed when the job was admitted, so later changes of the default or of the UI selection do not alter them.

| UI option / env | Provider | Model sent |
| --- | --- | --- |
| `ollama-gemma3:1b`, `ollama-gemma4:12b`, `ollama-ministral-3:8b`, `ollama-qwen3.5:9b`, `ollama-qwen3.5:4b`, `ollama-deepseek-r1:8b` | Local Ollama | the tag after `ollama-` |
| `vllm-qwen3.5:4b` | Local vLLM | `qwen3.5-4b` (`Qwen/Qwen3.5-4B`) |
| `vllm-qwen2.5:7b` | Local vLLM | `qwen2.5-7b` (`Qwen/Qwen2.5-7B-Instruct-AWQ`, 4-bit) |
| `deepseek-flash` | DeepSeek | `deepseek-flash` |
| `huggingface-deepseek-v4-flash` | Hugging Face / DeepInfra | `deepseek-ai/DeepSeek-V4-Flash:deepinfra` |
| `grok-4.3` | xAI | `grok-4.3` |

The two vLLM options are not in the default list; add them to `REPORT_GENERATION_MODELS` (and their limits to `REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL`). Clients are built only for configured models.

### Local models

**Ollama** models use the native `/api/chat` route and must be installed on the host. Ollama runs on the host GPU, so the FastAPI container needs no CUDA; check `ollama ps` for `100% GPU` during generation. If Ollama reports a missing model, the job ends with `AI_MODEL_NOT_FOUND`. No warm-up calls are made at startup.

- **`gemma3:1b`** sends `temperature=0`, `repeat_penalty=1.1` and `repeat_last_n=256` to reduce repetition loops in the JSON. This lowers the risk but guarantees neither the end of loops nor the quality of the recommendations. If Ollama aborts with `token repeat limit reached`, the job ends with `AI_REPETITION_LIMIT_EXCEEDED`, the other active batches are cancelled, and nothing is retried or published.
- **`deepseek-r1:8b`** (tag DeepSeek-R1-0528-Qwen3-8B, Q4_K_M, installed with `ollama pull deepseek-r1:8b`) sends `num_ctx=32768` and `num_predict=8192`, with a conservative input budget of 24,000 tokens per batch. This explicit context replaces `OLLAMA_CONTEXT_LENGTH` for these requests.

**vLLM** models run in Compose services started on demand (see [Running with Docker Compose](#-running-with-docker-compose)); the `app` container reaches them at `VLLM_API_BASE` (`http://vllm-report:8000/v1`, or `http://localhost:8001/v1` natively). They need the whole GPU, so they cannot run together with the `vllm` translation service or large Ollama models. By default a vLLM report uses 3,000 output tokens per batch and 24 parallel batches, because the server batches requests continuously.

- **`vllm-qwen3.5:4b`** (service `vllm-qwen35`, first start downloads about 9 GB into `vllm_hf_cache`) uses the Chat Completions API with the report's JSON schema as a structured-output grammar, because vLLM caps the thinking (`thinking_token_budget`) only there. At the budget the server forces the end of the thinking so the answer keeps its own room. Its `--max-model-len` (131,072) is the limit of one request, input plus output, and the catalog `context_window` must equal it. A vLLM request always may use the whole context, whatever the number of parallel batches.
- **`vllm-qwen2.5:7b`** (service `vllm-qwen25`, about 5.5 GB) has no thinking mode, so the effort selector is disabled and no budget is sent; its context is 32,768 tokens, and the server runs with `disable_any_whitespace` so the grammar cannot emit whitespace up to the output limit. The Q4_K_M GGUF build produced garbage on vLLM 0.32, so 4-bit AWQ weights are used. In test reports it also invented safety warnings (pregnancy, allergy, kidney, liver) that appear in none of the cited fragments, and the citation check cannot catch that, so review its reports.

### Effort

At “Generate report” the administrator also chooses an **effort**: `low` (default), `medium` or `high`. It is sent as `effort` in `POST /api/searches/{id}/generate` and translated per model (`src/backend/ai/effort.py`):

| Model | `low` | `medium` | `high` |
|---|---|---|---|
| Ollama `gemma4:12b`, `qwen3.5:9b`, `qwen3.5:4b`, `deepseek-r1:8b` | `think=false` | `think=true` | `think=true` |
| `vllm-qwen3.5:4b`, `deepseek-flash`, `huggingface-deepseek-v4-flash`, `grok-4.3` | `reasoning.effort="none"` | `"medium"` | `"high"` |
| Ollama `gemma3:1b`, `ministral-3:8b`; `vllm-qwen2.5:7b` | no control | no control | no control |

- Ollama accepts only a boolean `think`, so `medium` and `high` produce the same request. For vLLM Qwen 3.5, `high` sends the model's whole `thinking` budget and `medium` half of it.
- DeepSeek maps `medium` to `high` on its own. For Hugging Face only `low`/`medium`/`high` are documented, so `none` on the DeepInfra route must be verified with a real request.
- For models without control the selector is disabled, the server sends nothing and stores `ai_effort = NULL`.
- The effort is part of the request's idempotency: the same `requestId` with another effort gets `IDEMPOTENCY_CONFLICT`.

### Jobs

Generation starts with `POST /api/searches/{searchId}/generate`, which answers `202` with `jobId` and `Location`; the client sends a stable `requestId` per attempt, and duplicates are reconciled without duplicating the generation. `GET /api/report-generations/{jobId}` reads the status (polling launches no AI calls) and `POST /api/report-generations/{jobId}/cancel` requests cancellation. The frontend reconciles the job status with the session snapshot, so an old cached “queued” state cannot replace a final status.

A single FIFO worker (`REPORT_GENERATION_WORKERS = 1`, `MAX_CONCURRENT_GENERATIONS` must be 1) runs one report at a time. Accepted jobs start as `queued`, the status shows `queuePosition`, and cancelling a queued job removes it without an AI call. The queue does not survive a restart. The report timer starts when the worker picks the job up, so queue time is excluded; `REPORT_GENERATION_TIMEOUT_SECONDS` (default 600) limits the whole report (all batches and the PDF), `REPORT_GENERATION_READ_TIMEOUT_SECONDS` (720) limits I/O, and `OPERATION_TIMEOUT_SECONDS` (600) covers other operations. The worker slot stays occupied until the worker actually stops, even after cancellation or expiry.

Sessions and jobs stay in memory in a single process, so a container restart loses them and relaunches nothing. Refreshing the same tab recovers the job if it reconnects within `SESSION_RECONNECT_GRACE_SECONDS` (30); explicit closing cancels immediately. Shutdown waits at most `REPORT_SHUTDOWN_TIMEOUT_SECONDS` (20) within a Docker grace period of 30 s. Job metadata is limited to 32 per session and counted in its memory budget.

If the provider marks an answer incomplete with `max_output_tokens`, the job ends with `AI_OUTPUT_LIMIT_EXCEEDED`: distinct from a timeout or invalid JSON, the received text stays in the panel, and nothing is published or retried.

### Batches

Inside the single report, an executor runs up to `REPORT_BATCH_WORKERS` AI requests at once (default 2; `1` disables parallelism; invalid values are rejected at startup; Docker Compose passes it through `app.environment`). Each request gets the system prompt from `ai/prompts/generate_report_system.md`, the consultation profile and the whole fragments of its batch. When a batch ends, the next is admitted without waiting for the others. There is no automatic retry or consolidation request.

The admin can override the input and output limits, thinking budget and worker count for one report from the panel, without changing `.env`. The defaults come from the catalog and from `REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL`, which sets per model the input `tokens`, `context`, default `effort` and `thinking` budget. It may span several lines in `.env`, between single quotes (read the same way by `python-dotenv` and Docker Compose):

```dotenv
REPORT_BATCH_WORKERS=2
REPORT_GENERATION_BATCH_MAX_TOKENS_BY_MODEL='{
  "ollama-gemma3:1b": {"tokens": 25000, "context": 32768, "effort": "low", "thinking": 8000},
  "ollama-gemma4:12b": {"tokens": 25000, "context": 262144, "effort": "low", "thinking": 8000},
  "grok-4.3": {"tokens": 25000, "context": 1000000, "effort": "low", "thinking": 8000}
}'
```

The default contexts are the published ones (Gemma 3 1B: 32K; Gemma 4 12B, Ministral 3 8B, Qwen 3.5: 256K; DeepSeek V4 Flash: 1M; Grok 4.3: 1M), except R1 8B, which stays at the 32,768 `num_ctx` the application sends. The effective input of a batch is `min(tokens, context − output)`, and with an explicit Ollama `num_ctx` the output is reserved from it. The output limit (catalog default 20,000 tokens, or `OLLAMA_MAX_OUTPUT_TOKENS_BY_MODEL`, or the panel field) applies to each batch request independently of the input budget. `GET /api/report-models` sends `contextTokens` and `defaultEfforts`. The old `REPORT_GENERATION_BATCH_MAX_CHARS_BY_MODEL` is rejected at startup so that characters are never silently read as tokens.

Counting is local and estimated: the UTF-8 bytes of the complete JSON payload (prompt, profile, fragments, sources, IDs, schema, request fields) divided by 3, rounded up, plus 256 tokens of framing. No tokenizer is downloaded and no provider is called; the provider remains the authority on the real context, and a batch that exceeds it ends with `AI_CONTEXT_LIMIT_EXCEEDED` (reduce “Max input tokens”). Because search runs before the model is chosen, it limits the selected content to the largest budget among the active models, keeping fragments whole in score order; each model's limit then splits them into batches.

Fragments are kept whole and ordered by score. A single fragment that alone exceeds the budget goes whole into its own batch, and the local limit is ignored only for such one-fragment requests (logged as `report_batch_token_limit_bypassed`).

### Validation and combining

For Ollama, `format` receives the JSON schema of the five sections (including the Nutrition structure and the IDs allowed in the batch). Each answer is then strictly validated against the IDs of its batch, with no repair or retry, and recommendations outside Nutrition need at least one citation. A valid batch without recommendations is allowed. In Nutrition, empty text fields or ones made only of spaces, dashes and `•` count as no content. A batch whose answer fails only because of malformed items (`INVALID_ITEM`) is requested once more and, if still invalid, keeps its valid items and the report is labelled partial. Answers that are not JSON objects or cite unknown or missing evidence still fail the report (`AI_RESPONSE_INVALID`).

The code combines the batches in their initial order: only identical texts in the same section are removed, with their sources merged; different variants, doses and warnings are kept, and so are distinct recipes. This is no semantic reconciliation or clinical validation.

In the PDF, the items in `uz_intern`, `uz_extern`, `alte_recomandari` and `atentionari` are sorted by the number of distinct cited fragments (two fragments from one document count twice), ties broken by the highest relevance, then the number of distinct references, then the initial position. The count **X** in `● (57) Elderberry fruit tincture: …` is the number of `herbs_benefits` rows of the plant(s) identified in the item name (the maximum if several), without filtering by the report's condition; it is omitted when zero, reflects indexed associations rather than clinical efficacy, and does not influence the sort.

### Failure, cancellation and previews

The first request or validation error stops admitting new batches and asks the other active ones to cancel; the initial error is kept even if another thread's cancellation is observed first. User cancellation and the report timeout propagate to all batches. Blocked I/O calls cannot be killed, so the report's capacity stays occupied until all threads exit within the I/O timeouts. No partial PDF is published; the validated previews and the data of interrupted batches stay in the session, and a new generation replaces them.

The “Report preview” shows one “Batch N of T” panel per planned batch, in processing order, each with its own scrolling, state (pending, active, validated, failed, cancelled, expired) and only its own recommendations and bibliography. While a batch runs, its panel shows the provider's analysis and the raw answer, collapsed after validation; raw text never goes into the report or PDF, and thinking is released after success. The API exposes `batchPreviews` (`index`, `state`, `reportPreview`, `streamPreview`, `thinkingPreview`), `previewVersion`, `batchesCompleted` and `batchesTotal`; the counter counts validated batches in any order and is not a percentage. The `aiActivity` state (`waiting`, `processing`, `thinking`, `answering`) comes from real events of the current request, with speed approximated at 4 characters per token.

The PDF, the “The report is ready” message and one metrics row are published only after all batches end.

### Metrics and duration estimate

After the PDF is published, one row is inserted into `report_generation_metrics`: `medical_condition` (the exact canonical name from `medical_conditions.name`, several names comma-separated; no row if no catalog condition is identified), `min_score` (integer 0–100), `characters` (those actually sent to the AI after score and budget filtering), `ai_model`, `ai_effort` (`NULL` if the model has no control; recorded effort does not guarantee the provider applied it), `duration` (milliseconds, monotonic clock, from pickup to publication, excluding queue, insertion and email) and `max_batch_output_tokens` (the largest output of any request, used by the output recommendation). Cancellations, failures and repeated requests add no row. The insert waits at most 1 s for a connection, with `statement_timeout` 2 s and `lock_timeout` 500 ms; if it fails, the PDF remains available and `report_metrics_persistence_failed` is logged without medical content.

Under “Total number of characters”, the UI shows “Estimated duration: mm:ss” for the eligible characters and the chosen model. It uses all the model's rows with a linear regression through the origin, `duration_ms = selected_characters × SUM(characters × duration) / SUM(characters²)`, rounded up to seconds, and refreshes it when the selection changes or a job finishes. Without usable data it shows “unavailable”, which never blocks generation. `GET /api/report-duration-estimate` returns only the model, characters, `estimatedSeconds` and `sampleCount`.

Migrations `011`–`013` create the table, seed six historical measurements and normalize their condition labels; apply them before activating the code with `python -m scripts.migrate_database` (`PYTHONPATH=src`). Reindexing is not required, and repeating the seed INSERT by hand adds six rows again.

### Startup and diagnostics

The HTTP interface starts without waiting for search. A background probe search loads the embeddings, dictionary and index (`warm_up_started` / `warm_up_finished`), and no warm-up calls go to any AI provider. `/api/startup` returns `initializing`, `ready` or `degraded`; while initializing, submitting questions is disabled and search/AI operations and `/readyz` return `APP_INITIALIZING` (503), while `/healthz`, the interface and the session stay available. If the preparation fails, the application signals degraded mode and still allows a search attempt.

Integration problems are logged with the model, stage and failure type (HTTP/network/timeout, missing model, memory, context or output limit, interrupted stream, invalid JSON, validation). `ai_report_validation_failed` lists the batch, the problem count per code and at most 20 affected positions. `report_ai_timing` records the local times to the first event, analysis and answer text, the AI call duration and, where available, the provider's load, prompt and generation durations or usage; `report_ai_phase_changed` records phase changes only. Logs never include the prompt, fragments, raw answer, thinking or API keys. For runtime diagnostics: `docker compose logs --since 30m app`.

To activate code or configuration changes: `docker compose up -d --build app`, then reload the page. Architecture: [asynchronous generation](architecture/report-generation-background.xmind).

## 📜 License

The project's code is distributed under the [Business Source License 1.1](LICENSE) ([Romanian version](LICENSE.ro.md)). Use in non-production environments is free; use in production requires a separate commercial agreement with the licensor. Apache 2.0 is the license provided for after the change date, according to the terms in `LICENSE`, not the project's initial license.
