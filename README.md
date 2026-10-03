<div align="center">

# 🌿 Remedii Naturiste Adjuvante - de la Dr. Cuișor

### Asistent AI de medicină naturistă bazat pe surse

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![Hybrid retrieval](https://img.shields.io/badge/Retrieval-pgvector%20%2B%20tsvector-6A5ACD)](#-cum-funcționează)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128)](LICENSE)

🟢 **surse locale** · 🔵 **căutare semantică** · 🟠 **căutare lexicală** · 🟣 **raport PDF**

</div>

> [!IMPORTANT]
> Aplicația oferă informații orientative și recomandări adjuvante. Nu înlocuiește diagnosticul, consultația, tratamentul prescris sau îngrijirea medicală de urgență.

## ✨ Despre proiect

Proiectul transformă o colecție locală de documente Markdown despre medicină naturistă și terapii complementare într-un index hibrid interogabil. Interfața web primește problema descrisă de utilizator și afișează fragmentele relevante găsite în arhiva locală. După verificarea fragmentelor și acțiunea unui utilizator autorizat, trimite dovezile către furnizorul AI ales (`AI_PROVIDER`: xAI, DeepSeek, Hugging Face sau Ollama) pentru redactarea răspunsului structurat și generează un raport PDF cu trimiteri la surse.

| 🧩 Componentă | Rol |
|---|---|
| **Index semantic** | Identifică fragmente apropiate ca sens cu vectori Qwen3-Embedding de 1024 de dimensiuni, stocați în Postgres (`pgvector`). |
| **Index lexical** | Găsește termeni exacți prin `tsvector`/`ts_rank_cd` în Postgres. |
| **Scor combinat** | Fiecare fragment primește un singur scor: `4·P1 + 2·P2 + L + V` (afecțiune în titlu › afecțiune în text › potrivire lexicală › potrivire semantică), calculat într-o singură interogare SQL. |
| **Fragmentare pe afecțiuni** | Împarte documentele în fragmente R1 (afecțiunea în titlul capitolului), R2 (afecțiunea în textul capitolului) și D1 (restul textului), folosind dicționarul `data/medical_conditions.txt`. |
| **Retriever medical** | Ordonează fragmentele după scorul combinat și păstrează, întregi, cele care încap în bugetul de context al furnizorului AI. |
| **Chat web** | Oferă sesiuni izolate pe tab și afișează recomandările structurate. |
| **Raport PDF** | Include recomandări, atenționări, citări și bibliografie navigabilă. |
| **Livrare e-mail** | Poate trimite raportul prin Gmail API cu OAuth2, dacă este configurat. |

## 🎨 Cum funcționează

```text
📚 documente Markdown
        ↓
✂️ fragmente R1 / R2 / D1, cu afecțiuni, sursă și interval de linii
        ↓
🧠 embeddings Qwen3  +  🔎 tsvector, în Postgres/pgvector
        ↓
⚖️ scor combinat P1 › P2 › lexical › semantic și bugetul de context
        ↓
👁️ utilizatorul verifică fragmentele găsite
        ↓
🤖 utilizator autorizat: request structurat către furnizorul AI
        ↓
💬 recomandări în chat  +  📄 raport PDF  +  ✉️ e-mail opțional
```

> **Local vs. extern:** documentele, fragmentarea, indexarea și retrieval-ul rulează local. Fragmentele selectate și descrierea problemei sunt trimise, după `AI_PROVIDER`, către xAI, direct către DeepSeek (api.deepseek.com, servere în China), către DeepInfra prin routerul Hugging Face sau către Ollama (Cloud, cu modelele `:cloud`) pentru redactarea raportului; politicile de retenție ale fiecărui furnizor rămân de verificat înainte de activare. Livrarea prin Gmail este opțională.

## 🛠️ Tehnologii folosite

| Zonă | Tehnologii |
|---|---|
| **Limbaj și runtime** | Python 3.11, PowerShell |
| **Interfață și API** | React 19, TypeScript, Vite, TanStack Query, FastAPI, Uvicorn |
| **Embeddings locale** | FastEmbed, ONNX Runtime, `Qwen/Qwen3-Embedding-0.6B` (indexare opțională pe GPU, PyTorch fp16) |
| **Stocare index** | PostgreSQL, `pgvector` (similaritate cosinus), `unaccent` + `tsvector` (căutare lexicală) |
| **Scorul fragmentelor** | `4·P1 + 2·P2 + L + V`, cu prioritate pentru afecțiunea din titlu, apoi din text |
| **Generare AI** | Responses API (xAI, DeepSeek, Hugging Face sau Ollama, după `AI_PROVIDER`), răspuns JSON structurat |
| **Documente** | ReportLab pentru PDF, pypdf pentru procesare și verificare |
| **E-mail** | Gmail API, OAuth2 cu refresh token |
| **Configurare** | python-dotenv, variabile de mediu |
| **Rulare și publicare** | Docker, Docker Compose, Caddy, PostgreSQL (`pgvector/pgvector`) |
| **Testare** | `unittest` + `testcontainers` (Postgres efemer) pentru backend, Vitest pentru frontend |

## 🗺️ Documentație de arhitectură

| Document | Ce explică |
|---|---|
| 🧠 [Fluxul de generare a indexului hibrid](architecture/hybrid-index-generation.md) | Fluxul complet: documente → sincronizare incrementală (SHA-256) → fragmente R1/R2/D1 → embeddings → Postgres (`pgvector` + `tsvector`). |
| 📄 [Fluxul de generare a raportului final](architecture/final-report-generation.md) | Fluxul complet: mesaj → retrieval hibrid → fragmente afișate pacientului → „Generează rețeta” (owner) → furnizorul AI → PDF → download și trimitere pe e-mail către altă persoană. |
| 🔎 [Căutarea și scoringul fragmentelor](architecture/fragment-search-and-scoring.md) | Fluxul complet: mesaj → afecțiuni recunoscute → scor `4·P1 + 2·P2 + L + V` pentru toate fragmentele → procent de relevanță → limitarea contextului. |

## 📁 Structura proiectului

```text
medicina-naturista/
├── architecture/                 # documentația fluxurilor principale
├── data/
│   ├── documents/                # corpusul Markdown local
│   ├── medical_conditions.txt    # dicționarul de afecțiuni și sinonime
│   └── model_cache/              # modelul ONNX local; ignorat de Git
├── scripts/
│   ├── build_hybrid_index.py     # sincronizarea incrementală a indexului în Postgres
│   ├── search_index.ps1          # căutare locală din terminal
│   ├── clean_documents.py/.ps1   # curățarea surselor Markdown înainte de indexare
│   ├── fragment_report.py        # simularea fragmentării, fără bază de date
│   ├── evaluate_retrieval.py     # măsurarea calității căutării (P@10, MRR, nDCG)
│   ├── google_oauth_setup.py     # autorizare Gmail OAuth2
│   ├── extract_pdf_text.py       # extragerea textului din PDF
│   ├── extract_pdf_markdown.py   # extragerea structurată în Markdown
│   ├── text_to_markdown.py       # conversia textului în Markdown
│   └── merge_book_pdfs.py        # combinarea părților de carte PDF
├── frontend/                     # aplicația React/TypeScript (Vite)
├── src/medicina_naturista/
│   ├── ai/                       # fragmentare, afecțiuni, căutare, retrieval, clienți AI și prompturi
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

Plasați documentele sursă în `data/documents/`. Nu publicați corpusul dacă include materiale private sau protejate. Opțional, curățați-le înainte de indexare (metadate de extragere PDF, linkuri, marcaje de pagină, trimiteri „Vezi și”, diacritice românești transcrise în litere ASCII: `ă/â → a`, `î → i`, `ș → s`, `ț → t`):

```powershell
.\scripts\clean_documents.ps1 -DryRun   # doar raportează
.\scripts\clean_documents.ps1           # rescrie fișierele modificate
```

Înlocuirea diacriticelor e activă implicit; `.\scripts\clean_documents.ps1 -KeepDiacritics` (sau `--no-fold-diacritics`) le păstrează.

Aveți nevoie de un Postgres cu extensia `pgvector` pornit și accesibil la `DATABASE_URL` (implicit `postgresql://medicina:medicina@127.0.0.1:5432/medicina`); cel mai simplu e `docker compose up -d db`.

### 2. Sincronizarea indexului

```powershell
python scripts\build_hybrid_index.py
```

Baza vine din `DATABASE_URL` (`.env`); `--model` și `--source` sunt opționale. Scriptul pornește cu pythonul din care îl rulezi (pe CPU, fără alt mediu); pe GPU vezi mai jos.

Modelul de embedding este `Qwen/Qwen3-Embedding-0.6B` (vectori de 1024 de dimensiuni); alt model nu este cunoscut de cod. Căutarea citește modelul din `sync_metadata` și scrie întrebările după profilul lui (`ai/embedding_model.py`: instrucțiunea Qwen la întrebare, fără prefix la pasaje). **Dacă baza conține un index făcut cu alt model sau cu altă dimensiune, următorul build reîncorporează toate documentele**, iar coloana `chunks.embedding` este recreată și indexul golit (doar scriptul de build face asta, niciodată aplicația). Pe un PC cu GPU, indexarea durează ~17 minute în loc de ore; rulează din mediul `.venv-gpu`, care are `torch`:

```powershell
$env:EMBEDDING_DEVICE = 'cuda'
.\.venv-gpu\Scripts\python scripts\build_hybrid_index.py
```

Prima sincronizare descarcă modelul în `data/model_cache/` și poate dura câteva zeci de minute, apoi scrie fiecare document nou/modificat în Postgres. Următoarele rulări sar complet peste documentele al căror SHA-256 nu s-a schimbat — nu se re-generează embeddings pentru ele; documentele șterse din `data/documents/` sunt șterse și din index. Când se schimbă regulile de fragmentare (`TEXT_REPR_VERSION` din `build_hybrid_index.py`), următoarea sincronizare reindexează totul. Căutările folosesc modelul din cache și rulează offline. În timpul embedding-ului sunt afișate progresul, timpul scurs, viteza și ETA.

Pentru a vedea ce fragmente ar rezulta, fără bază de date și fără embeddings:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\fragment_report.py
```

### 3. Căutarea locală

```powershell
.\scripts\search_index.ps1 "plante și măsuri pentru tuse"
```

Pentru rezultate ușor de procesat programatic:

```powershell
.\scripts\search_index.ps1 "plante și măsuri pentru tuse" -Json
```

Căutarea din terminal întoarce toate fragmentele cu scor pozitiv (fără limita de context a furnizorului AI). Fiecare rezultat păstrează documentul sursă, intervalul de linii și componentele scorului (`P1`, `P2`, `L`, `V`), astfel încât pasajul să poată fi verificat în fișierul original.

Calitatea căutării se măsoară pe interogările etichetate din `tests/eval/retrieval_queries.json`:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py --output after.json
```

### 4. Pornirea aplicației în dezvoltare

Adăugați în fișierul local `.env` cel puțin cheia furnizorului AI ales (implicit xAI) și cheia de owner, fără de care nimeni nu poate genera rețeta:

```dotenv
AI_PROVIDER=xai
X_API_KEY=...
OWNER_KEY=o-cheie-secreta-lunga
COOKIE_SECURE=false
```

Construiți interfața React (FastAPI servește `frontend/dist`):

```powershell
cd frontend
npm install
npm run build
cd ..
```

Apoi porniți aplicația:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn medicina_naturista.web.main:app --host 127.0.0.1 --port 7860
```

Deschideți o dată `http://127.0.0.1:7860/owner?key=<OWNER_KEY>`, ca browserul să fie marcat ca owner, apoi `http://127.0.0.1:7860`. Endpointul de stare este `http://127.0.0.1:7860/healthz` (503 dacă lipsește cheia furnizorului AI).

Pentru dezvoltarea interfeței cu reîncărcare automată, rulați `npm run dev` în `frontend/`: Vite servește interfața și trimite `/api`, `/healthz` și `/owner` către backend-ul de pe portul 7860.

## 📦 Schema indexului hibrid (Postgres)

Sincronizarea scrie în trei tabele:

| Tabel | Conținut |
|---|---|
| `documents` | Un rând per fișier sursă: cale, SHA-256, codificare, număr de linii; categoria (folderul) este o coloană generată din cale. Folosit și pentru a decide ce fișiere sar la sincronizarea următoare. |
| `chunks` | Un rând per fragment: text, interval de linii, calea titlurilor (`heading`), `business_category` (`R1`/`R2`/`D1`), `primary_medical_conditions`, `secondary_medical_conditions`, vectorul semantic (`embedding vector(1024)`) și coloana lexicală (`text_search tsvector`). |
| `sync_metadata` | Modelul de embeddings, dimensiunea vectorilor, versiunea reprezentării textului și data ultimei sincronizări. |

Un document al cărui SHA-256 nu s-a schimbat este complet ignorat la sincronizare; un document nou sau modificat își înlocuiește fragmentele într-o singură tranzacție.

Fragmentarea (`src/medicina_naturista/ai/fragmenter.py`) folosește dicționarul `data/medical_conditions.txt` (o afecțiune pe linie: numele canonic, apoi sinonimele) și aplică pe rând:

| Categorie | Criteriu |
|---|---|
| **R1** | Titlul unui capitol Markdown numește o afecțiune → titlul și tot subarborele lui rămas liber (subcapitolele cu afecțiune proprie devin fragmente separate). |
| **R2** | Textul propriu al unui capitol rămas (până la următorul titlu) menționează o afecțiune → titlul și acel text. |
| **D1** | Restul textului (inclusiv documentele fără titluri) → bucăți de ~1800 de caractere (1500–2100), tăiate la sfârșit de paragraf sau propoziție, cu suprapunere de cel mult 270 de caractere. |

Afecțiunile se caută pe cuvinte întregi, fără diacritice și majuscule, cu toleranță la terminațiile românești (`gripa`/`gripei`). Numele fișierului și al folderelor nu se compară cu afecțiunile. Fragmentele R1 și R2 primesc `primary_medical_conditions` (afecțiunile din titlu) și `secondary_medical_conditions` (afecțiunile din text); D1 nu are afecțiuni. R1 și R2 nu au limită de lungime.

La căutare, fiecare fragment primește scorul `4·P1 + 2·P2 + L + V` (maximum 8): P1 = afecțiunea căutată este în `primary_medical_conditions`, P2 = este în `secondary_medical_conditions`, L = potrivirea lexicală relativă, V = similaritatea semantică rescalată între mediana și maximul căutării. Scorul nu se stochează în DB; detaliile sunt în [fragment-search-and-scoring.md](architecture/fragment-search-and-scoring.md).

Pentru embeddings, un fragment mai lung de 1400 de caractere este împărțit în ferestre care se suprapun cu 240, iar vectorii lor se mediază (valorile, dimensiunea vectorilor și prefixele de text ale fiecărui model sunt în profilul lui din `ai/embedding_model.py`). Diacriticele sunt păstrate prin normalizare Unicode NFC.

## 🐳 Rulare cu Docker Compose

Înainte de pornire, trebuie să existe `data/documents/`, `data/model_cache/` (cu modelul deja descărcat: containerul rulează offline) și fișierul local `.env` cu cheia furnizorului AI ales (`X_API_KEY`, `DEEPSEEK_API_KEY`, `HF_TOKEN` sau `OLLAMA_API_KEY`), `POSTGRES_PASSWORD` și `OWNER_KEY`. Serviciul `db` (Postgres 16 + `pgvector`, cu `shared_buffers=512MB`) pornește automat împreună cu restul stivei și este expus doar pe `127.0.0.1:5432`, astfel încât indexul se sincronizează de pe host cu `python scripts/build_hybrid_index.py`.

```powershell
docker compose build
docker compose up -d
docker compose ps
Invoke-WebRequest http://localhost:8760/healthz
```

Aplicația este publicată pe host la `127.0.0.1:8760` (`APP_HOST_PORT`; în container rămâne portul 7860, iar 8760 evită intervalul de porturi rezervat de Windows) și, prin Caddy, pe porturile 80/443. Rulează într-un container read-only, fără capabilități Linux suplimentare, ca utilizator non-root. Documentele sunt montate read-only, iar fișierele temporare folosesc `tmpfs`. Indexul locuiește în Postgres (volum named `pg_data`), nu mai e nevoie de bind-mount sau de oprirea aplicației la resincronizare.

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
| `HF_MAX_CONTEXT_CHARS` | `120000` | Bugetul pentru `AI_PROVIDER=huggingface` (limita routerului HF ≈ 64k tokeni). |
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
| `CONDITIONS_FILE` | `data/medical_conditions.txt` | Dicționarul de afecțiuni și sinonime, folosit la fragmentare și la căutare; se reîncarcă automat când se modifică. |
| `DATABASE_URL` | `postgresql://medicina:medicina@127.0.0.1:5432/medicina` | Conexiunea Postgres a indexului hibrid (`pgvector` + `tsvector`). |
| `MODEL_CACHE_DIR` | `data/model_cache` | Directorul cache-ului local al modelului ONNX. |
| `EMBEDDING_THREADS` | `8` (cel mult numărul de nuclee) | Firele de execuție ale modelului de embedding (ONNX Runtime), la indexare și la căutare. Pe procesoare hibride P/E-core, mai puține fire sunt de obicei mai rapide decât toate nucleele. |
| `EMBEDDING_DEVICE` | `cpu` | Dispozitivul modelului de embedding la **construirea** indexului: `cpu` (FastEmbed/ONNX) sau `cuda` (PyTorch fp16, doar din mediul GPU `.venv-gpu`; fără CUDA build-ul se oprește, nu trece pe CPU). Întrebările din aplicație rulează mereu pe CPU. |
| `SEARCH_SEMANTIC_ONLY` | `false` | Experiment: `true` ordonează fragmentele doar după semnalul semantic V (ponderile P1, P2 și L devin 0). `false` păstrează formula `4·P1 + 2·P2 + L + V`. Util pentru a compara modelele de embedding fără influența condițiilor și a căutării lexicale. |
| `SESSION_TEMP_DIR` | `var/sessions` (Windows) / `/tmp/naturist-sessions` | Directorul fișierelor temporare ale sesiunilor. |
| `MAX_CHAT_CHARS` | `4000` | Lungimea maximă a mesajului utilizatorului. |
| `X_AI_MAX_CONTEXT_CHARS` | `1000000` | Bugetul (în caractere de text al fragmentelor) pentru `AI_PROVIDER=xai`: fragmentele afișate și trimise către AI. Toate fragmentele primesc scor, se ordonează descrescător, iar cele de la coadă care nu încap sunt eliminate întregi, nu trunchiate. Nu există un prag de relevanță separat și nici o limită de candidați per semnal. |
| `MAX_REQUESTS_PER_MINUTE` | `60` | Limita de cereri `POST`/`PUT`/`DELETE` către `/api/` acceptate într-un minut, pe IP. |
| `SESSION_IDLE_SECONDS` | `3600` | Expirarea unei sesiuni inactive. |
| `SESSION_MAX_SECONDS` | `14400` | Durata maximă a unei sesiuni. |
| `COOKIE_SECURE` | `false` | Impune transmiterea cookie-ului numai prin HTTPS. |
| `OWNER_KEY` | _(gol)_ | Cheie secretă lungă. Doar browserele care au deschis o dată `/owner?key=<OWNER_KEY>` primesc un cookie (valabil ~10 ani) și pot genera rețeta; ceilalți văd un mesaj de indisponibilitate. Fără cheie, nimeni nu poate genera. |
| `LOG_LEVEL` | `INFO` | Nivelul minim al logurilor. |
| `LOG_FRAGMENT_TEXT` | `true` | Include textul fragmentelor în loguri. |
| `LOG_FRAGMENT_TEXT_MAX_CHARS` | `4000` | Limita textului logat per fragment. |
| `LOG_AI_RESPONSE_TEXT` | `false` | Include în loguri textul complet al răspunsului AI, fără limită. |
| `APP_HOST_PORT` | `8760` (Docker Compose) | Portul de pe host la care Compose publică aplicația. |
| `PUBLIC_ROOT_PATH` | gol (direct) / `/medicina` (Docker Compose) | Prefixul căii publice, necesar când aplicația este expusă prin Caddy sub `/medicina` (folosit și la build-ul frontend-ului, ca `PUBLIC_BASE_PATH`). |
| `FRONTEND_DIST_DIR` | `frontend/dist` | Directorul cu build-ul React servit ca fișiere statice de FastAPI. |
| `TRUST_PROXY` | `false` (direct) / `true` (Docker Compose) | Folosește primul IP din `X-Forwarded-For` pentru limitarea cererilor când traficul vine prin proxy de încredere. |

Creșterea bugetului de context (`*_MAX_CONTEXT_CHARS`) mărește numărul de fragmente afișate, timpul de procesare și dimensiunea requestului trimis către furnizorul AI. În medii în care logurile nu au acces controlat, setați `LOG_FRAGMENT_TEXT=false`.

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
- 🧹 conversațiile și PDF-urile stau doar în memorie, separate pe tab, și sunt eliminate la închiderea paginii, la expirare sau la repornirea aplicației; nicio informație medicală a pacientului nu se scrie în baza de date;
- 🚫 requesturile xAI folosesc `store=false` (pentru DeepSeek, Hugging Face și Ollama parametrul nu se trimite; se aplică politicile lor de retenție);
- 🩺 răspunsurile sunt informative și trebuie verificate medical înainte de utilizare.

## 🧪 Testare

Testele care ating indexul pornesc un Postgres efemer (`pgvector/pgvector:pg16`) prin `testcontainers`, deci au nevoie de Docker pornit și de dependența de dezvoltare:

```powershell
.\.venv\Scripts\python.exe -m pip install "testcontainers[postgres]>=4,<5"
```

Rulați întreaga suită backend:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Testele interfeței:

```powershell
cd frontend
npm test
npm run typecheck
```

Testele acoperă fragmentarea și recunoașterea afecțiunilor, sincronizarea indexului, scorul și retrieval-ul, sesiunile web, răspunsurile simulate ale furnizorilor AI, generarea PDF și integrarea Gmail simulată. Nu sunt necesare requesturi AI reale.

## 📜 Licență

Codul proiectului este distribuit sub [Apache License 2.0](LICENSE).

---

<div align="center">

🌱 **Surse verificabile · retrieval local · recomandări adjuvante**

</div>
