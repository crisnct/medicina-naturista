<div align="center">

# 🌿 Remedii Naturiste Adjuvante - de la Dr. Cuișor

### Asistent AI de medicină naturistă bazat pe surse

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![Hybrid retrieval](https://img.shields.io/badge/Retrieval-Semantic%20%2B%20FTS5-6A5ACD)](#-cum-funcționează)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128)](LICENSE)

🟢 **surse locale** · 🔵 **căutare semantică** · 🟠 **căutare lexicală** · 🟣 **raport PDF**

</div>

> [!IMPORTANT]
> Aplicația oferă informații orientative și recomandări adjuvante. Nu înlocuiește diagnosticul, consultația, tratamentul prescris sau îngrijirea medicală de urgență.

## ✨ Despre proiect

Proiectul transformă o colecție locală de documente Markdown despre medicină naturistă și terapii complementare într-un index hibrid interogabil. Interfața web primește problema descrisă de utilizator și afișează fragmentele relevante găsite în arhiva locală. După verificarea fragmentelor și acțiunea unui utilizator autorizat, trimite dovezile către xAI pentru redactarea răspunsului structurat și generează un raport PDF cu trimiteri la surse.

| 🧩 Componentă | Rol |
|---|---|
| **Index semantic** | Identifică fragmente apropiate ca sens cu vectori E5 de 384 dimensiuni, stocați în Postgres (`pgvector`). |
| **Index lexical** | Găsește termeni exacți prin `tsvector`/`ts_rank_cd` în Postgres. |
| **Scor combinat** | Fiecare fragment primește un singur scor: `8·P1 + 4·P2 + 2·L + V` (afecțiune în titlu › afecțiune în text › potrivire lexicală › potrivire semantică), calculat într-o singură interogare SQL. |
| **Retriever medical** | Ordonează fragmentele după scorul combinat și păstrează, întregi, cele care încap în bugetul de context. |
| **Chat web** | Oferă sesiuni izolate pe tab și afișează recomandările structurate. |
| **Raport PDF** | Include recomandări, atenționări, citări și bibliografie navigabilă. |
| **Livrare e-mail** | Poate trimite raportul prin Gmail API cu OAuth2, dacă este configurat. |

## 🎨 Cum funcționează

```text
📚 documente Markdown
        ↓
✂️ fragmente coerente, cu sursă și interval de linii
        ↓
🧠 embeddings E5  +  🔎 tsvector, în Postgres/pgvector
        ↓
⚖️ scor combinat P1 › P2 › lexical › semantic și bugetul de context
        ↓
👁️ utilizatorul verifică fragmentele găsite
        ↓
🤖 utilizator autorizat: request structurat către xAI
        ↓
💬 recomandări în chat  +  📄 raport PDF  +  ✉️ e-mail opțional
```

> **Local vs. extern:** documentele, fragmentarea, indexarea și retrieval-ul rulează local. Fragmentele selectate și descrierea problemei sunt trimise, după `AI_PROVIDER`, către xAI, direct către DeepSeek (api.deepseek.com, servere în China), către DeepInfra prin routerul Hugging Face sau către Ollama (Cloud, cu modelele `:cloud`) pentru redactarea raportului; politicile de retenție ale fiecărui furnizor rămân de verificat înainte de activare. Livrarea prin Gmail este opțională.

## 🛠️ Tehnologii folosite

| Zonă | Tehnologii |
|---|---|
| **Limbaj și runtime** | Python 3.11, PowerShell |
| **Interfață și API** | React 19, TypeScript, Vite, TanStack Query, FastAPI, Uvicorn |
| **Embeddings locale** | FastEmbed, ONNX Runtime, `intfloat/multilingual-e5-small` |
| **Stocare index** | PostgreSQL, `pgvector` (similaritate cosinus), `unaccent` + `tsvector` (căutare lexicală) |
| **Scorul fragmentelor** | `8·P1 + 4·P2 + 2·L + V`, cu priorități stricte pentru afecțiunea din titlu și din text |
| **Generare AI** | Responses API (xAI, Hugging Face sau Ollama, după `AI_PROVIDER`), răspuns JSON structurat |
| **Documente** | ReportLab pentru PDF, pypdf pentru procesare și verificare |
| **E-mail** | Gmail API, OAuth2 cu refresh token |
| **Configurare** | python-dotenv, variabile de mediu |
| **Rulare și publicare** | Docker, Docker Compose, Caddy, PostgreSQL (`pgvector/pgvector`) |
| **Testare** | `unittest`, teste unitare și de integrare |

## 🗺️ Documentație de arhitectură

| Document | Ce explică |
|---|---|
| 🧠 [Fluxul de generare a indexului hibrid](architecture/hybrid-index-generation.md) | Fluxul complet: documente → fragmente → embeddings → FTS5 → publicarea atomică a indexului. |
| 📄 [Fluxul de generare a raportului final](architecture/final-report-generation.md) | Fluxul complet: mesaj → retrieval hibrid → fragmente afișate pacientului → „Generează rețeta” (owner) → xAI → PDF → download și trimitere pe e-mail către altă persoană. |
| 🔎 [Căutarea, unirea și scoringul fragmentelor](architecture/fragment-search-and-scoring.md) | Fluxul complet: mesaj → afecțiuni recunoscute → scor `8·P1 + 4·P2 + 2·L + V` pentru toate fragmentele → procent de relevanță → limitarea contextului. |

## 📁 Structura proiectului

```text
medicina-naturista/
├── architecture/                 # documentația fluxurilor principale
├── data/
│   ├── documents/                # corpusul Markdown local
│   └── model_cache/              # modelul ONNX local; ignorat de Git
├── scripts/
│   ├── build_hybrid_index.py     # sincronizarea incrementală a indexului în Postgres
│   ├── rebuild_index.ps1         # lansator PowerShell pentru sincronizare
│   ├── search_index.ps1          # căutare locală din terminal
│   ├── google_oauth_setup.py     # autorizare Gmail OAuth2
│   ├── extract_pdf_text.py       # extragerea textului din PDF
│   ├── extract_pdf_markdown.py   # extragerea structurată în Markdown
│   ├── text_to_markdown.py       # conversia textului în Markdown
│   └── merge_book_pdfs.py        # combinarea părților de carte PDF
├── frontend/                     # aplicația React/TypeScript (Vite)
├── src/medicina_naturista/
│   ├── ai/                       # căutare, retrieval, client xAI și prompturi
│   ├── core/                     # modele și sesiuni izolate
│   ├── integrations/             # integrarea Gmail
│   ├── reporting/                # generarea raportului PDF
│   └── web/                      # API JSON FastAPI (servește și build-ul React)
├── tests/                        # teste unitare și de integrare
├── docker-compose.yaml
├── Dockerfile
└── pyproject.toml
```

## 🚀 Pornire rapidă

### 1. Pregătirea mediului

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
```

Plasați documentele sursă în `data/documents/`. Nu publicați corpusul dacă include materiale private sau protejate.

Aveți nevoie de un Postgres cu extensia `pgvector` pornit și accesibil la `DATABASE_URL` (implicit `postgresql://medicina:medicina@127.0.0.1:5432/medicina`); cel mai simplu e `docker compose up -d db`.

### 2. Sincronizarea indexului

```powershell
.\scripts\rebuild_index.ps1
```

Batch size-ul implicit este `64`; poate fi schimbat astfel:

```powershell
.\scripts\rebuild_index.ps1 -BatchSize 32
```

Prima sincronizare descarcă modelul în `data/model_cache/` și poate dura câteva zeci de minute, apoi scrie fiecare document nou/modificat în Postgres. Următoarele rulări sar complet peste documentele al căror SHA-256 nu s-a schimbat — nu se re-generează embeddings pentru ele. Rularea următoarelor căutări folosește modelul din cache și rulează offline. În timpul embedding-ului sunt afișate progresul, timpul scurs, viteza și ETA.

### 3. Căutarea locală

```powershell
.\scripts\search_index.ps1 "plante și măsuri pentru tuse"
```

Pentru rezultate ușor de procesat programatic:

```powershell
.\scripts\search_index.ps1 "plante și măsuri pentru tuse" -Limit 20 -Json
```

Fiecare rezultat păstrează documentul sursă și intervalul de linii, astfel încât pasajul să poată fi verificat în fișierul original.

### 4. Pornirea aplicației în dezvoltare

Adăugați în fișierul local `.env` cel puțin:

```dotenv
X_API_KEY=...
COOKIE_SECURE=false
```

Apoi porniți aplicația:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn medicina_naturista.web.main:app --host 127.0.0.1 --port 7860
```

Deschideți `http://127.0.0.1:7860`. Endpointul de stare este `http://127.0.0.1:7860/healthz`.

## 📦 Schema indexului hibrid (Postgres)

Sincronizarea scrie în trei tabele:

| Tabel | Conținut |
|---|---|
| `documents` | Un rând per fișier sursă: cale, SHA-256, categorie — folosit și pentru a decide ce fișiere sar la sincronizarea următoare. |
| `chunks` | Un rând per fragment: text, interval de linii, categorie, `conditions`, vectorul semantic (`embedding vector(384)`) și coloana lexicală (`text_search tsvector`). |
| `sync_metadata` | Modelul de embeddings folosit și data ultimei sincronizări. |

Un document al cărui SHA-256 nu s-a schimbat este complet ignorat la sincronizare; un document nou sau modificat își înlocuiește fragmentele într-o singură tranzacție.

Fiecare fragment poartă în `chunks` lista de afecțiuni din `data/medical_conditions.txt` despre care e vorba (`conditions`) și calea titlurilor (`heading`, ex. `Vindecare prin nutritie > Gripa`). Fragmentarea (`src/medicina_naturista/ai/fragmenter.py`) aplică pe rând:

| Criteriu de fragmentare |
|---|
| Numele fișierului sau al unui folder conține o afecțiune → tot documentul e un fragment |
| Document Markdown: un titlu conține o afecțiune → titlul și tot ce ține de el (subtitluri incluse) |
| Document Markdown: o secțiune menționează o afecțiune în textul ei (fără liniile deja luate la criteriul anterior) → titlurile strămoșilor + secțiunea, fără introducerile strămoșilor |
| Document fără titluri, sau textul rămas nefolosit: ≤ 3000 caractere un fragment, altfel bucăți de ~3000 care se termină la sfârșitul propoziției |

Orice fragment mai lung de 8000 de caractere este împărțit, iar părțile păstrează afecțiunile și calea. Prioritatea folosită la clasare se calculează **la căutare**, din afecțiunea introdusă de utilizator: dacă numele ei sau un sinonim apare în titlul/calea fragmentului, PRIORITY=1; dacă apare doar în text, 3; altfel 10. Dacă afecțiunea nu e în dicționar, se caută ca atare, fără sinonime: un fragment se potrivește dacă titlul sau textul conține toate cuvintele importante ale interogării (sau ale unui segment separat prin virgulă). Scorul fuzionat se înmulțește cu `PRIORITY_WEIGHT` din `ai/search.py`: `1 → 1.0`, `3 → 0.7`, `10 → 0.2`. Prioritatea nu se stochează în DB.

Pentru embeddings, un fragment mai lung de `MAX_CHARS = 1400` este împărțit în ferestre care se suprapun cu `OVERLAP_CHARS = 240`, iar vectorii lor se mediază. Diacriticele sunt păstrate prin normalizare Unicode NFC.

## 🐳 Rulare cu Docker Compose

Înainte de pornire, trebuie să existe `data/documents/`, `data/model_cache/` și fișierul local `.env` cu cheia furnizorului AI ales (`X_API_KEY`, `HF_TOKEN` sau `OLLAMA_API_KEY`) și `POSTGRES_PASSWORD`. Serviciul `db` (Postgres + `pgvector`) pornește automat împreună cu restul stivei.

```powershell
docker compose build
docker compose up -d
docker compose ps
Invoke-WebRequest http://localhost:7860/healthz
```

Aplicația rulează într-un container read-only, fără capabilități Linux suplimentare, ca utilizator non-root. Documentele sunt montate read-only, iar fișierele temporare folosesc `tmpfs`. Indexul locuiește în Postgres (volum named `pg_data`), nu mai e nevoie de bind-mount sau de oprirea aplicației la resincronizare.

Oprire fără ștergerea stării Caddy:

```powershell
docker compose down
```

> [!WARNING]
> `docker compose down -v` șterge volumele Caddy, inclusiv starea și certificatele gestionate de acesta.

Pentru publicare, `APP_DOMAIN` conține doar hostname-ul. Cu ngrok, folosiți `CADDY_SITE_SCHEME=http` și tunelul către portul `80`. Pentru un domeniu administrat direct de server, folosiți `CADDY_SITE_SCHEME=https` și configurați DNS-ul și porturile 80/443.

## ⚙️ Configurare

Fișierul `.env` este ignorat de Git. Valorile principale recunoscute de aplicație sunt:

| Variabilă | Implicit | Rol |
|---|---:|---|
| `AI_PROVIDER` | `xai` | Furnizorul AI pentru generarea raportului: `xai`, `huggingface`, `ollama` sau `deepseek`. Valoare necunoscută → eroare la pornire; schimbarea cere repornirea aplicației. |
| `X_API_KEY` | — | Cheia xAI (necesară cu `AI_PROVIDER=xai`). |
| `XAI_MODEL` | `grok-4.3` | Modelul xAI folosit pentru redactare. |
| `XAI_REASONING_EFFORT` | `medium` (direct) / `low` (Docker Compose) | Nivelul de reasoning solicitat. |
| `XAI_API_BASE` | `https://api.x.ai/v1` | URL-ul de bază al API-ului xAI. |
| `HF_TOKEN` | — | Token Hugging Face fine-grained cu permisiunea „Make calls to Inference Providers” (necesar cu `AI_PROVIDER=huggingface`). |
| `HF_MODEL` | `deepseek-ai/DeepSeek-V4-Flash:deepinfra` | Modelul prin routerul HF; sufixul `:deepinfra` fixează furnizorul. |
| `HF_API_BASE` | `https://router.huggingface.co/v1` | URL-ul de bază al routerului HF (Responses API, beta). |
| `HF_REASONING_EFFORT` | _(gol)_ | `low`/`medium`/`high`; se trimite doar dacă este setat. |
| `HF_MAX_CONTEXT_CHARS` | `120000` | Bugetul pentru `AI_PROVIDER=huggingface` (limita routerului HF ≈ 64k tokeni). De calibrat după Faza 0 din `architecture/ai-provider-switch-plan.md`. |
| `DEEPSEEK_API_KEY` | — | Cheia API de pe platform.deepseek.com (necesară cu `AI_PROVIDER=deepseek`). |
| `DEEPSEEK_MODEL` | `deepseek-flash` | Modelul DeepSeek (V4.1 Flash, prin Responses API: `POST {DEEPSEEK_API_BASE}/responses`). |
| `DEEPSEEK_API_BASE` | `https://api.deepseek.com` | URL-ul de bază al API-ului DeepSeek. |
| `DEEPSEEK_REASONING_EFFORT` | _(gol)_ | Se trimite doar dacă este setat. |
| `DEEPSEEK_MAX_CONTEXT_CHARS` | `1000000` | Bugetul pentru `AI_PROVIDER=deepseek`. |
| `OLLAMA_API_BASE` | `http://localhost:11434/v1` | Baza Ollama; în Docker Compose `http://host.docker.internal:11434/v1`. |
| `OLLAMA_MODEL` | `deepseek-v4.1-flash:cloud` | Modelul Ollama (`:cloud` rulează pe serverele Ollama, după `ollama signin`). |
| `OLLAMA_API_KEY` | — | Necesară doar când `OLLAMA_API_BASE` nu este local (ex. `https://ollama.com/v1`). |
| `OLLAMA_REASONING_EFFORT` | _(gol)_ | Se trimite doar dacă este setat. |
| `OLLAMA_MAX_CONTEXT_CHARS` | `1000000` | Bugetul pentru `AI_PROVIDER=ollama`; pentru modele locale mici trebuie coborât. |
| `AI_STREAM` | `false` | Cere răspunsul ca flux de evenimente (`stream: true`). Timeoutul de citire se aplică între evenimente, deci evită tăierea cererilor lungi de un proxy (ex. 504 după 60 s la routerul HF). Dacă furnizorul nu suportă streaming, lăsați `false`. |
| `AI_MAX_OUTPUT_TOKENS` | `20000` | `max_output_tokens` al cererii, pentru toți furnizorii (la modelele cu gândire, reasoning-ul consumă din el). |
| `AI_READ_TIMEOUT_SECONDS` | `300` | Timeoutul de citire al cererii către furnizorul AI. |
| `DOCUMENTS_DIR` | `data/documents` | Directorul documentelor locale. |
| `DATABASE_URL` | `postgresql://medicina:medicina@127.0.0.1:5432/medicina` | Conexiunea Postgres a indexului hibrid (`pgvector` + `tsvector`). |
| `MODEL_CACHE_DIR` | `data/model_cache` | Directorul cache-ului local al modelului ONNX. |
| `SESSION_TEMP_DIR` | `var/sessions` (Windows) / `/tmp/naturist-sessions` | Directorul fișierelor temporare ale sesiunilor. |
| `MAX_CHAT_CHARS` | `4000` | Lungimea maximă a mesajului utilizatorului. |
| `X_AI_MAX_CONTEXT_CHARS` | `1000000` | Bugetul (în caractere de text al fragmentelor) pentru `AI_PROVIDER=xai`: fragmentele afișate și trimise către AI. Toate fragmentele primesc scor, se ordonează descrescător, iar cele de la coadă care nu încap sunt eliminate întregi, nu trunchiate. Nu există un prag de relevanță separat și nici o limită de candidați per semnal. |
| `MAX_REQUESTS_PER_MINUTE` | `60` | Limita de cereri acceptate într-un minut. |
| `SESSION_IDLE_SECONDS` | `3600` | Expirarea unei sesiuni inactive. |
| `SESSION_MAX_SECONDS` | `14400` | Durata maximă a unei sesiuni. |
| `COOKIE_SECURE` | `false` | Impune transmiterea cookie-ului numai prin HTTPS. |
| `OWNER_KEY` | _(gol)_ | Cheie secretă lungă. Doar browserele care au deschis o dată `/owner?key=<OWNER_KEY>` primesc un cookie (valabil ~10 ani) și pot genera rețeta; ceilalți văd un mesaj de indisponibilitate. Fără cheie, nimeni nu poate genera. |
| `LOG_LEVEL` | `INFO` | Nivelul minim al logurilor. |
| `LOG_FRAGMENT_TEXT` | `true` | Include textul fragmentelor în loguri. |
| `LOG_FRAGMENT_TEXT_MAX_CHARS` | `4000` | Limita textului logat per fragment. |
| `LOG_AI_RESPONSE_TEXT` | `false` | Include în loguri textul complet al răspunsului AI, fără limită. |
| `PUBLIC_ROOT_PATH` | gol (direct) / `/medicina` (Docker Compose) | Prefixul căii publice, necesar când aplicația este expusă prin Caddy sub `/medicina` (folosit și la build-ul frontend-ului, ca `PUBLIC_BASE_PATH`). |
| `FRONTEND_DIST_DIR` | `frontend/dist` | Directorul cu build-ul React servit ca fișiere statice de FastAPI. |
| `TRUST_PROXY` | `false` (direct) / `true` (Docker Compose) | Folosește primul IP din `X-Forwarded-For` pentru limitarea cererilor când traficul vine prin proxy de încredere. |

Creșterea limitelor de retrieval și evidence poate mări timpul de procesare și dimensiunea requestului trimis către xAI. În medii în care logurile nu au acces controlat, setați `LOG_FRAGMENT_TEXT=false`.

La pornirea directă, aplicația citește valorile din `.env`; valorile implicite diferă unde este indicat. Docker Compose transmite variabilele enumerate în secțiunea `environment`; `COOKIE_SECURE` este implicit `false` la pornire directă și `true` în Compose. `OWNER_KEY` este opțional, dar fără el generarea raportului este dezactivată; setați o cheie secretă și deschideți `/owner?key=<OWNER_KEY>` în browserul autorizat. `TRUST_PROXY` este activat în Compose deoarece Caddy se află în fața aplicației.

### ✉️ Gmail OAuth2 — opțional

```dotenv
GMAIL_USERNAME=adresa-ta@gmail.com
MAIL_FROM=adresa-ta@gmail.com
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
```

Autorizarea inițială se face o singură dată:

```powershell
.\.venv\Scripts\python.exe scripts\google_oauth_setup.py
```

Este solicitat numai scope-ul `gmail.send`. Tokenul nu este afișat și nu trebuie publicat. Dacă integrarea nu este complet configurată, raportul rămâne disponibil în aplicație, iar livrarea e-mail este omisă.

## 🔐 Confidențialitate și siguranță

- 🔒 `.env` și cache-ul modelului sunt ignorate de Git; indexul locuiește în Postgres, nu în fișiere din repo.
- 🧭 fiecare fragment rămâne legat de fișierul și liniile sursă;
- 🧹 conversațiile și PDF-urile sunt temporare, separate pe sesiune și eliminate la închiderea tabului, la expirare sau la repornirea aplicației;
- 🚫 requesturile xAI folosesc `store=false` (pentru Hugging Face și Ollama parametrul nu se trimite; se aplică politicile lor de retenție);
- 🩺 răspunsurile sunt informative și trebuie verificate medical înainte de utilizare.

## 🧪 Testare

Rulați întreaga suită:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Testele acoperă fragmentarea și progresul construirii indexului, retrieval-ul hibrid, sesiunile web, răspunsurile xAI simulate, generarea PDF și integrarea Gmail simulată. Nu sunt necesare requesturi xAI reale pentru testele unitare.

## 📜 Licență

Codul proiectului este distribuit sub [Apache License 2.0](LICENSE).

---

<div align="center">

🌱 **Surse verificabile · retrieval local · recomandări adjuvante**

</div>
