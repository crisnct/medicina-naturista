<div align="center">

# 🌿 Remedii Naturiste Adjuvante - de la Dr. Cuișor

### Asistent AI de medicină naturistă bazat pe surse locale

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![Hybrid retrieval](https://img.shields.io/badge/Retrieval-pgvector%20%2B%20tsvector-6A5ACD)](#-cum-funcționează)
[![License](https://img.shields.io/badge/License-Business%20Source%201.1-D22128)](LICENSE)

🟢 **surse locale** · 🔵 **căutare semantică** · 🟠 **căutare lexicală** · 🟣 **raport PDF**

</div>

> [!IMPORTANT]
> Aplicația oferă informații orientative și recomandări adjuvante. Nu înlocuiește diagnosticul, consultația, tratamentul prescris sau îngrijirea medicală de urgență.
> Conversațiile și rapoartele sunt păstrate temporar în memoria procesului. Descrierea problemei și fragmentele selectate pot fi trimise furnizorului AI configurat; identificarea afecțiunii poate folosi separat un serviciu extern. Nu introduceți nume, CNP, adrese sau alte date de identificare în chat.

## ✨ Despre proiect

Proiectul transformă o colecție locală de documente Markdown despre medicină naturistă și terapii complementare într-un index hibrid interogabil. Interfața web primește problema descrisă de utilizator și afișează fragmentele relevante găsite în arhiva locală. După verificarea fragmentelor și acțiunea unui utilizator autorizat, trimite dovezile către furnizorul AI ales (`AI_PROVIDER`: xAI, DeepSeek, Hugging Face sau Ollama) pentru redactarea răspunsului structurat și generează un raport PDF cu trimiteri la surse.

| 🧩 Componentă | Rol |
|---|---|
| **Index semantic** | Identifică fragmente apropiate ca sens cu vectori Qwen3-Embedding de 1024 de dimensiuni, stocați în Postgres (`pgvector`). |
| **Index lexical** | Găsește expresiile căutate, ca fraze exacte, prin `tsvector` în Postgres. |
| **Scor combinat** | Fiecare fragment primește un singur scor, din semnalele pe care pacientul le bifează în „Căutare avansată” (afecțiuni, lexical, semantic). Cu toate trei: `4·P1 + 2·P2 + L + V` (afecțiune în titlu › afecțiune în text › potrivire lexicală › potrivire semantică), calculat într-o singură interogare SQL. |
| **Fragmentare pe afecțiuni** | Împarte documentele în fragmente R1 (afecțiunea în titlul capitolului), R2 (afecțiunea în textul capitolului) și D1 (restul textului), folosind catalogul de afecțiuni și sinonime din PostgreSQL. |
| **Filtrare pe surse** | În același panou „Căutare avansată”, căutarea poate fi restrânsă la anumite foldere din `medicina-naturista-documente/data/documents/` (categoria unui document este folderul lui). |
| **Retriever medical** | Ordonează fragmentele după scorul combinat și păstrează, întregi, cele care încap în bugetul de context al furnizorului AI. Lângă „Generează rețeta”, „Scor minim” (procent de relevanță) limitează fragmentele trimise către AI. |
| **Chat web** | Oferă sesiuni izolate pe tab și afișează recomandările structurate. |
| **Raport PDF** | Include recomandări, atenționări, citări și bibliografie navigabilă. |
| **Livrare e-mail** | După generare, poate trimite raportul prin Gmail API cu OAuth2 la adresa scrisă de utilizator în chat, dacă este configurat. |

## 🎨 Cum funcționează

```text
📚 documente Markdown
        ↓
✂️ fragmente R1 / R2 / D1, cu afecțiuni, sursă și interval de linii
        ↓
🧠 embeddings Qwen3  +  🔎 tsvector, în Postgres/pgvector
        ↓
⚖️ scor combinat din semnalele alese (P1 › P2 › lexical › semantic) și bugetul de context
        ↓
👁️ utilizatorul verifică fragmentele găsite
        ↓
🤖 utilizator autorizat: request structurat către furnizorul AI
        ↓
💬 recomandări în chat  +  📄 raport PDF  +  ✉️ e-mail opțional
```

> **Local vs. extern:** documentele, fragmentarea, indexarea și retrieval-ul rulează local. Fragmentele selectate și descrierea problemei sunt trimise, după `AI_PROVIDER`, către xAI, direct către DeepSeek (api.deepseek.com, servere în China), către DeepInfra prin routerul Hugging Face sau către Ollama (Cloud, cu modelele `:cloud`) pentru redactarea raportului; politicile de retenție ale fiecărui furnizor rămân de verificat înainte de activare. Când dicționarul de afecțiuni nu recunoaște mesajul, acesta este trimis (doar textul mesajului) întâi unui model local Ollama și, dacă backendul local eșuează, routerului Hugging Face (`CONDITION_AI_BACKENDS`); varianta locală nu trimite nimic în afara mașinii. Livrarea prin Gmail este opțională.

## 🛠️ Tehnologii folosite

| Zonă | Tehnologii |
|---|---|
| **Limbaj și runtime** | Python ≥ 3.11 (mediu local documentat: 3.11), PowerShell, Node.js 22 pentru frontend |
| **Interfață și API** | React 19, TypeScript, Vite, TanStack Query, FastAPI, Uvicorn |
| **Embeddings locale** | FastEmbed, ONNX Runtime, `Qwen/Qwen3-Embedding-0.6B` (indexare opțională pe GPU, PyTorch fp16) |
| **Stocare index** | PostgreSQL, `pgvector` (similaritate cosinus), `unaccent` + `tsvector` (căutare lexicală) |
| **Scorul fragmentelor** | `4·P1 + 2·P2 + L + V` cu toate semnalele, cu prioritate pentru afecțiunea din titlu, apoi din text; pacientul poate alege oricare combinație de semnale |
| **Generare AI** | Responses API (xAI, DeepSeek, Hugging Face sau Ollama, după `AI_PROVIDER`), răspuns JSON structurat |
| **Documente** | ReportLab pentru PDF, pypdf pentru procesare și verificare |
| **E-mail** | Gmail API, OAuth2 cu refresh token |
| **Configurare** | python-dotenv, variabile de mediu |
| **Rulare și publicare** | Docker, Docker Compose, Caddy, PostgreSQL (`pgvector/pgvector`) |
| **Testare** | `unittest`, `pytest` + `testcontainers` (Postgres efemer) pentru backend, Vitest pentru frontend |

## 🗺️ Documentație de arhitectură

| Document | Ce explică |
|---|---|
| 🧠 [Fluxul de generare a indexului hibrid](architecture/hybrid-index-generation.md) | Fluxul complet: documente → sincronizare incrementală (SHA-256) → fragmente R1/R2/D1 → embeddings → Postgres (`pgvector` + `tsvector`). |
| 📄 [Fluxul de generare a raportului final](architecture/final-report-generation.md) | Fluxul complet: mesaj → retrieval hibrid → fragmente afișate pacientului → „Generează rețeta” (owner) → furnizorul AI → PDF → download și trimitere pe e-mail către altă persoană. |
| 🔎 [Căutarea și scoringul fragmentelor](architecture/fragment-search-and-scoring.md) | Fluxul complet: mesaj → afecțiuni recunoscute → scor (`4·P1 + 2·P2 + L + V` cu toate semnalele alese) pentru toate fragmentele → procent de relevanță → limitarea contextului. |

## 📁 Structura proiectului

```text
medicina-naturista/
├── architecture/                 # documentația fluxurilor principale și planurile de lucru (plan-*.md)
├── medicina-naturista-documente/
│   └── data/
│       ├── documents/                # corpusul Markdown local
│       └── herbs.jsonl               # catalogul de plante medicinale (o specie pe linie)
├── model_cache/                  # modelele locale; ignorat de Git
├── src/
│   ├── backend/
│   │   ├── ai/                       # fragmentare, afecțiuni, căutare, retrieval, clienți AI și prompturi
│   │   ├── core/                     # modele și sesiuni izolate
│   │   ├── migrations/               # schema PostgreSQL și catalogul inițial de afecțiuni
│   │   ├── integrations/             # integrarea Gmail
│   │   ├── reporting/                # generarea raportului PDF
│   │   └── web/                      # API JSON FastAPI (servește și build-ul React)
│   ├── frontend/                 # aplicația React/TypeScript (Vite)
│   ├── scripts/
│   │   ├── build_hybrid_index.py     # sincronizarea incrementală a indexului în Postgres
│   │   ├── bootstrap_database.py     # creează baza lipsă înainte de indexare
│   │   ├── migrate_database.py       # aplică migrările SQL versionate
│   │   ├── condition_sql.py          # generează SQL pentru afecțiuni noi
│   │   ├── manage_dependencies.py    # generează și verifică lockurile
│   │   ├── search_index.ps1          # căutare locală din terminal
│   │   ├── clean_documents.py        # curățare și corectare OCR/de scriere cu dicționarul inclus
│   │   ├── fragment_report.py        # simularea fragmentării; citește catalogul din DB, fără embeddings
│   │   ├── audit_conditions.py       # audit read-only al dicționarului de afecțiuni
│   │   ├── audit_near_dupes.py       # afecțiuni canonice aproape duplicate (read-only)
│   │   ├── audit_herbs.py            # raport read-only despre herbs.jsonl (în tmp/herbs_review.md)
│   │   ├── icd10_work/               # scripturi one-off pentru completarea dicționarului după ICD-10
│   │   ├── evaluate_retrieval.py     # măsurarea calității căutării (P@10, MRR, nDCG)
│   │   ├── google_oauth_setup.py     # autorizare Gmail OAuth2
│   │   ├── extract_pdf_markdown.py   # extragerea structurată în Markdown
│   │   └── merge_book_pdfs.py        # combinarea părților de carte PDF
│   └── tests/                    # teste unitare și de integrare
├── Caddyfile
├── docker-compose.yaml
├── Dockerfile
├── pyproject.toml
├── requirements-runtime*.lock    # dependențe runtime fixate, cu hashuri
├── requirements-dev*.lock        # runtime + unelte de dezvoltare/testare
└── requirements-web.txt          # alias compatibil pentru Windows/Python 3.11
```

## 🚀 Pornire rapidă

### 1. Pregătirea mediului

Comenzile PowerShell se execută din rădăcina proiectului. Instalați Python 3.11 și Node.js 22/npm; PostgreSQL cu `pgvector` trebuie să fie accesibil înainte de indexare. Corpusul `medicina-naturista-documente/data/documents/` și catalogul `medicina-naturista-documente/data/herbs.jsonl` sunt furnizate separat.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-runtime.lock
```

Plasați documentele sursă în `medicina-naturista-documente/data/documents/`. Nu publicați corpusul dacă include materiale private sau protejate. Opțional, curățați-le înainte de indexare (metadate de extragere PDF, linkuri, marcaje de pagină, trimiteri „Vezi și”, diacritice românești transcrise în litere ASCII: `ă/â → a`, `î → i`, `ș → s`, `ț → t`):

```powershell
.\.venv\Scripts\python.exe src\scripts\clean_documents.py --dry-run
.\.venv\Scripts\python.exe src\scripts\clean_documents.py
```

Înlocuirea diacriticelor este activă implicit; opțiunea `--no-fold-diacritics` le păstrează. Corectarea cuvintelor folosește fișierele Hunspell `ro_RO.dic` și `ro_RO.aff` incluse în `src/scripts/dictionaires/ro/`, localizate relativ la script.

Corectarea rulează după curățare, numai pentru documentele detectate ca românești: unește fragmente OCR, separă cuvinte lipite, corectează greșeli rare neambigue și ortografia veche. Frecvențele sunt calculate din corpusul curățat înainte de rescriere. Raportul `var/spelling_changes.tsv` conține fișierul, linia din textul curățat, regula și formele înainte/după; se generează și la `--dry-run`, fără modificarea documentelor. Folosiți `--spelling-report` pentru altă destinație. Lipsa dicționarului oprește execuția înainte de modificarea documentelor. Protecția dozelor și numerelor verifică și rezultatul corectării. `--no-fold-diacritics` păstrează diacriticele și folosește formele din dicționar pentru înlocuiri.

Aveți nevoie de un Postgres cu extensia `pgvector` pornit și accesibil la `DATABASE_URL` (implicit `postgresql://medicina:medicina@127.0.0.1:5432/medicina`); cel mai simplu e `docker compose up -d db`, care cere `POSTGRES_PASSWORD` în `.env` (utilizatorul și baza sunt implicit `medicina`), deci `DATABASE_URL` trebuie să folosească aceeași parolă.

### 2. Sincronizarea indexului

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe src\scripts\build_hybrid_index.py
```

Scriptul importă pachetul `backend`, deci are nevoie de `PYTHONPATH=src`. Baza vine din `DATABASE_URL` (`.env`); `--model` și `--source` sunt opționale. Scriptul pornește cu pythonul din care îl rulezi (pe CPU, fără alt mediu); pe GPU vezi mai jos.

Modelul de embedding este `Qwen/Qwen3-Embedding-0.6B` (vectori de 1024 de dimensiuni); alt model nu este cunoscut de cod. Căutarea citește modelul din `sync_metadata` și scrie întrebările după profilul lui (`ai/embedding_model.py`: instrucțiunea Qwen la întrebare, fără prefix la pasaje). **Dacă baza conține un index făcut cu alt model sau cu altă dimensiune, următorul build reîncorporează toate documentele**, iar coloana `chunks.embedding` este recreată în aceeași tranzacție cu documentele și metadata noi. Orice eroare păstrează generația și dimensiunea anterioare. Durata depinde de corpus și hardware. Indexarea pe GPU necesită un mediu separat `.venv-gpu`, cu dependențele aplicației, `torch` cu suport CUDA și `sentence-transformers` deja instalate:

```powershell
$env:PYTHONPATH = "src"
$env:EMBEDDING_DEVICE = 'cuda'
.\.venv-gpu\Scripts\python.exe src\scripts\build_hybrid_index.py
```

La prima sincronizare, modelul este descărcat în `model_cache/` dacă lipsește. Apoi căutarea funcționează offline. Căutarea pe CPU necesită modelul FastEmbed/ONNX, chiar dacă indexarea a fost făcută pe GPU cu PyTorch.

La următoarele sincronizări, se procesează doar documentele noi sau modificate, iar cele șterse sunt eliminate din index. Schimbarea catalogului de afecțiuni, a modelului sau a modului de pregătire a textului impune refacerea completă a indexului. Progresul și timpul estimat rămas sunt afișate în terminal.

**Reindexarea creează baza dacă lipsește și aplică automat migrările SQL.** Sunt necesare permisiuni pentru crearea bazei, a schemei și a extensiilor; opțional, `DATABASE_BOOTSTRAP_URL` poate furniza un cont separat pentru creare. Aplicația web nu execută migrări la pornire. Afecțiunile și sinonimele sunt citite din PostgreSQL; completările se fac prin migrări noi în `src/backend/migrations/`, fără modificarea celor deja aplicate.

În timpul sincronizării, căutarea și lista surselor sunt temporar indisponibile (`503`). Generarea din fragmente deja găsite și descărcarea PDF-urilor pot continua. Indexul nou este publicat numai după calcularea și validarea tuturor vectorilor; un eșec păstrează indexul anterior. Dacă între timp s-a schimbat catalogul, căutarea necesită finalizarea reindexării. Un catalog lipsă sau invalid blochează căutarea, iar un index incompatibil cere resincronizare (`INDEX_RESYNC_REQUIRED`).

Pentru reconstruirea indexului, păstrați documentele sursă, migrările SQL, modelul și configurația. Autorizările owner necesită backup separat.

Căutarea folosește numai sursele selectate. O selecție goală nu caută nicăieri; dacă toate sursele selectate au dispărut, aplicația cere reselecția. Dacă au dispărut doar unele, le păstrează pe cele valide și afișează un avertisment.

Recomandările cu trimiteri la fragmente inexistente sunt eliminate; elementele de nutriție fără citări sunt exceptate. Dacă rămâne doar o parte din rezultat, chatul și PDF-ul indică un raport parțial. Dacă generarea eșuează complet, căutarea se păstrează pentru o reîncercare manuală. Verificarea citărilor nu reprezintă validare medicală. Logurile clientului AI conțin doar diagnostic tehnic, fără textul fragmentelor sau al răspunsului.

Pentru a vedea ce fragmente ar rezulta, fără scriere în index și fără embeddings (necesită catalogul migrat din PostgreSQL):

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe src\scripts\fragment_report.py
```

### 3. Căutarea locală

```powershell
.\src\scripts\search_index.ps1 "plante și măsuri pentru tuse"
```

Pentru rezultate ușor de procesat programatic:

```powershell
.\src\scripts\search_index.ps1 "plante și măsuri pentru tuse" -Json
```

Căutarea din terminal întoarce toate fragmentele cu scor pozitiv (fără limita de context a furnizorului AI). Fiecare rezultat păstrează documentul sursă, intervalul de linii și componentele scorului (`P1`, `P2`, `L`, `V`), astfel încât pasajul să poată fi verificat în fișierul original. `--signals` alege semnalele scorului (orice combinație de `A` afecțiuni, `B` lexical, `C` semantic; implicit `ABC`), de exemplu `python -m backend.ai.search "gripa" --signals AB`.

Calitatea căutării se măsoară pe interogările etichetate din `src/tests/eval/retrieval_queries.json`:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe src\scripts\evaluate_retrieval.py --output after.json
```

### 4. Pornirea aplicației în dezvoltare

Adăugați în fișierul local `.env` cel puțin cheia furnizorului AI ales (implicit xAI) și cheia de owner, fără de care nimeni nu poate genera rețeta:

```dotenv
AI_PROVIDER=xai
X_API_KEY=...
OWNER_KEY=o-cheie-secreta-lunga
COOKIE_SECURE=false
```

Construiți interfața React (FastAPI servește `src/frontend/dist`):

```powershell
cd src/frontend
npm ci
npm run build
cd ..\..
```

Apoi porniți aplicația:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn backend.web.main:app --host 127.0.0.1 --port 7860
```

Dacă ați sincronizat indexul la pasul 2, migrările sunt deja aplicate. Pentru mentenanța unei baze existente, le puteți executa separat cu `.\.venv\Scripts\python.exe -m scripts.migrate_database` (cu `PYTHONPATH=src`). Deschideți chatul la `http://127.0.0.1:7860/`, respectiv `http://127.0.0.1:7860/owner` pentru login/logout. Formularul trimite cheia prin `POST /api/owner/login`, cu CSRF; logoutul revocă tokenul prin `POST /api/owner/logout`. Cu prefixul public, formularul este `/medicina/owner` pe originea HTTPS configurată. Cheia nu trebuie pusă în URL sau în istoricul terminalului. Autorizarea rămâne valabilă peste restart până la logout sau rotația cheii. Ruta veche cu cheia în query rămâne doar pentru compatibilitate. `/healthz` verifică inclusiv configurarea furnizorului AI; `/readyz` adaugă verificarea disponibilității și compatibilității indexului.

Pentru dezvoltarea interfeței cu reîncărcare automată, rulați `npm run dev` în `src/frontend/`: Vite servește interfața și trimite `/api`, `/healthz` și `/owner` către backend-ul de pe portul 7860.

API-ul JSON (`src/backend/web/main.py`) este folosit de interfața React; documentația OpenAPI (`/docs`) este dezactivată. Cererile `/api/...` cu sesiune trimit antetul `X-Tab-Id` (identificatorul tabului).

| Endpoint | Rol |
|---|---|
| `GET /healthz` | Starea aplicației și configurarea cheii AI; independent de mentenanța sau compatibilitatea indexului. Folosit de healthcheck-ul Docker. |
| `GET /readyz` | Verifică și indexul; 503 cu `INDEX_MAINTENANCE`, `INDEX_RESYNC_REQUIRED` sau `INDEX_UNAVAILABLE` și `Retry-After: 60`. |
| `GET /owner` | Formularul de autentificare/deconectare owner. Varianta veche cu `?key=...` este încă acceptată, dar nu este recomandată: expune cheia în URL. |
| `GET /api/owner` | Starea autorizării și tokenul CSRF pentru browser. |
| `POST /api/owner/login`, `POST /api/owner/logout` | Emit, respectiv revocă autorizarea individuală; necesită origine validă și token CSRF. |
| `GET /api/session` | Creează sesiunea tabului și întoarce istoricul conversației. |
| `GET /api/categories` | Arborele categoriilor (folderele surselor) și selecția implicită (toate). |
| `POST /api/messages` | Salvează mesajul, categoriile și semnalele alese; dacă există deja un raport, o adresă de e-mail trimite raportul. |
| `POST /api/condition` | Identifică prin AI afecțiunea pe care dicționarul nu o cunoaște (`CONDITION_AI_BACKENDS`). |
| `POST /api/search` | Rulează căutarea și întoarce fragmentele găsite și secțiunea „Generează rețeta”. |
| `POST /api/searches/{search_id}/generate` | Doar owner: trimite către AI fragmentele cu relevanța ≥ `minScore` și generează PDF-ul. |
| `GET /api/reports/{tab_id}/{report_id}` | Descarcă PDF-ul generat în sesiunea tabului. |
| `POST /api/session/end`, `POST /api/session/unload` | Închid sesiunea tabului (la cerere, respectiv la închiderea paginii). |

## Sesiuni, retenție și autorizare owner

[Documentația de operare](architecture/session-runtime.md) descrie limitele configurabile, codurile HTTP, migrarea, proxy-urile autorizate și contractul de anulare. Limitele sunt pe proces: rulați aplicația cu **un singur worker**. Datele medicale rămân temporare; tabela `owner_sessions` păstrează numai hashuri și metadata tehnică de revocare.

Implicit este permisă o singură sesiune activă per adresă IP (`MAX_SESSIONS_PER_IP=1`), inclusiv între Edge și Chrome; persoanele din aceeași rețea/NAT împart această limită. Un al doilea tab/browser afișează mesajul explicit de blocare și „Verifică din nou”, fără să permită căutarea. Pentru tunelul ngrok existent prin proxy-ul JobsHunter, porniți normal cu `docker compose up -d`. Configurația include legătura Caddy cu rețeaua existentă `jobshunter-net` (`PUBLIC_PROXY_NETWORK` pentru alt nume); configurați allowlisturile IP conform documentației de operare.

## 📦 Schema indexului hibrid (Postgres)

Tabelele principale ale indexului, catalogului și migrărilor sunt:

| Tabel | Conținut |
|---|---|
| `documents` | Un rând per fișier sursă: cale, SHA-256, codificare, număr de linii; categoria (folderul) este o coloană generată din cale. Folosit și pentru a decide ce fișiere sar la sincronizarea următoare. |
| `medical_conditions` | Numai `id` și `name`: o înregistrare pentru fiecare afecțiune. |
| `medical_condition_synonyms` | Numai `id`, `medical_condition_id` și `synonym`: sinonimele legate prin FK de afecțiune. |
| `schema_migrations` | Ledgerul migrărilor SQL aplicate o singură dată. |
| `owner_sessions` | Autorizări owner persistente: hashuri și metadata tehnică; fără conversații sau rapoarte. |
| `chunks` | Un rând per fragment: text, interval de linii, calea titlurilor (`heading`), categoria generată din cale (`category_id`, folosită de filtrarea pe surse), `business_category` (`R1`/`R2`/`D1`), `primary_medical_conditions`, `secondary_medical_conditions`, vectorul semantic (`embedding vector(1024)`) și coloana lexicală (`text_search tsvector`). |
| `sync_metadata` | Modelul, dimensiunea, profilul pasajelor, versiunea textului, fingerprintul SHA-256 al dicționarului, generația indexului și data sincronizării. |

Dacă profilul indexului și fingerprintul catalogului sunt neschimbate, un document cu același SHA-256 este ignorat la sincronizare; un document nou sau modificat își înlocuiește fragmentele într-o singură tranzacție.

Fragmentarea (`src/backend/ai/fragmenter.py`) citește afecțiunile din `medical_conditions` și sinonimele din `medical_condition_synonyms`, în ordinea ID-urilor de inserare. Python adaugă numele canonic în lista termenilor de potrivire, fără să-l dubleze în tabela sinonimelor. Apoi aplică pe rând:

| Categorie | Criteriu |
|---|---|
| **R1** | Titlul unui capitol Markdown numește o afecțiune → titlul și tot subarborele lui rămas liber (subcapitolele cu afecțiune proprie devin fragmente separate). |
| **R2** | Textul propriu al unui capitol rămas (până la următorul titlu) menționează o afecțiune → titlul și acel text. |
| **D1** | Restul textului (inclusiv documentele fără titluri) → bucăți de ~1800 de caractere (1500–2100), tăiate la sfârșit de paragraf sau propoziție, cu suprapunere de cel mult 270 de caractere. |

Afecțiunile se caută pe cuvinte întregi, fără diacritice și majuscule, cu toleranță la terminațiile românești (`gripa`/`gripei`). Numele fișierului și al folderelor nu se compară cu afecțiunile. Fragmentele R1 și R2 primesc `primary_medical_conditions` (afecțiunile din titlu) și `secondary_medical_conditions` (afecțiunile din text); D1 nu are afecțiuni. R1 și R2 nu au limită de lungime.

La căutare, fiecare fragment primește scorul `4·P1 + 2·P2 + L + V` (maximum 8, cu toate semnalele bifate): P1 = afecțiunea căutată este în `primary_medical_conditions`, P2 = este în `secondary_medical_conditions`, L = fracțiunea de expresii (separate prin virgulă) regăsite în fragment, V = similaritatea semantică rescalată între mediana și maximul căutării. Pacientul poate debifa semnale în panoul „Căutare avansată”, iar formula se adaptează (de exemplu `L + V` sau doar `2·P1 + P2`). Scorul nu se stochează în DB; detaliile sunt în [fragment-search-and-scoring.md](architecture/fragment-search-and-scoring.md).

Pentru embeddings, un fragment mai lung de 1400 de caractere este împărțit în ferestre care se suprapun cu 240, iar vectorii lor se mediază (valorile, dimensiunea vectorilor și prefixele de text ale fiecărui model sunt în profilul lui din `ai/embedding_model.py`). Diacriticele sunt păstrate prin normalizare Unicode NFC.

## 🐳 Rulare cu Docker Compose

Înainte de build/pornire, trebuie să existe `medicina-naturista-documente/data/herbs.jsonl`, `medicina-naturista-documente/data/documents/`, `model_cache/` (cu modelul deja descărcat: containerul rulează offline) și fișierul local `.env` cu cheia furnizorului AI ales (`X_API_KEY`, `DEEPSEEK_API_KEY`, `HF_TOKEN` sau `OLLAMA_API_KEY`), `POSTGRES_PASSWORD` și `OWNER_KEY`. Stiva are patru servicii: `db`, `ollama`, `app` și `caddy`. Serviciul `db` (Postgres 16 + `pgvector`, cu `shared_buffers=512MB`) este expus doar pe `127.0.0.1:5432` (`DB_HOST_PORT`), astfel încât indexul se sincronizează de pe host cu `python src/scripts/build_hybrid_index.py` (cu `PYTHONPATH=src` și un `DATABASE_URL` spre `127.0.0.1` cu parola `POSTGRES_PASSWORD`). Serviciul `ollama` rulează modelul local de identificare a afecțiunii (`CONDITION_AI_LOCAL_BASE=http://ollama:11434/v1`), este accesibil doar din rețeaua internă, rezervă GPU-urile NVIDIA (`deploy.resources.reservations`) și are nevoie ca modelul să fie descărcat o dată: `docker compose exec ollama ollama pull gemma3:1b`.

Rețeaua externă `jobshunter-net` (sau valoarea `PUBLIC_PROXY_NETWORK`) trebuie să existe înainte de pornirea Caddy; Compose nu o creează. Verificați-o cu `docker network inspect jobshunter-net` (sau numele configurat). Sincronizați indexul după pornirea serviciului `db`, înainte de a folosi căutarea.

```powershell
docker compose up -d --build
docker compose ps
Invoke-WebRequest http://localhost:8760/healthz
```

Aplicația este publicată pe host la `127.0.0.1:8760` (`APP_HOST_PORT`; în container rămâne portul 7860, iar 8760 evită intervalul de porturi rezervat de Windows) și, prin Caddy, pe porturile 80/443. Rulează într-un container read-only, fără capabilități Linux suplimentare, ca utilizator non-root. Documentele sunt montate read-only, iar directoarele temporare folosesc `tmpfs`. Indexul locuiește în Postgres (volum named `pg_data`), nu mai e nevoie de bind-mount sau de oprirea aplicației la resincronizare.

Oprire fără ștergerea volumelor:

```powershell
docker compose down
```

> [!WARNING]
> `docker compose down -v` șterge toate volumele named: indexul din Postgres (`pg_data`), modelele Ollama (`ollama_models`) și starea și certificatele Caddy (`caddy_data`, `caddy_config`).

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
| `HF_MAX_CONTEXT_CHARS` | `120000` | Bugetul de caractere al fragmentelor pentru `AI_PROVIDER=huggingface`; nu reprezintă o limită de tokeni garantată de furnizor. |
| `DEEPSEEK_API_KEY` | — | Cheia API de pe platform.deepseek.com (necesară cu `AI_PROVIDER=deepseek`). |
| `DEEPSEEK_MODEL` | `deepseek-flash` | Identificatorul modelului trimis către DeepSeek (prin Responses API: `POST {DEEPSEEK_API_BASE}/responses`). |
| `DEEPSEEK_API_BASE` | `https://api.deepseek.com` | URL-ul de bază al API-ului DeepSeek. |
| `DEEPSEEK_REASONING_EFFORT` | _(gol)_ | Se trimite doar dacă este setat. |
| `DEEPSEEK_MAX_CONTEXT_CHARS` | `1000000` | Bugetul pentru `AI_PROVIDER=deepseek`. |
| `OLLAMA_API_BASE` | `http://localhost:11434/v1` | Baza Ollama; în Docker Compose `http://host.docker.internal:11434/v1`. |
| `OLLAMA_MODEL` | `deepseek-v4.1-flash:cloud` | Modelul Ollama (`:cloud` rulează pe serverele Ollama, după `ollama signin`). |
| `OLLAMA_API_KEY` | — | Necesară doar când `OLLAMA_API_BASE` nu este local (ex. `https://ollama.com/v1`). |
| `OLLAMA_REASONING_EFFORT` | _(gol)_ | Se trimite doar dacă este setat. |
| `OLLAMA_MAX_CONTEXT_CHARS` | `1000000` | Bugetul pentru `AI_PROVIDER=ollama`; pentru modele locale mici trebuie coborât. |
| `CONDITION_AI_BACKENDS` | `local,huggingface` | Backendurile care identifică afecțiunea când catalogul PostgreSQL nu o găsește, în ordinea încercării: `local` (Ollama), `huggingface` (routerul HF, `HF_TOKEN`) sau ambele (HF dacă backendul local eșuează, inclusiv la timeout sau răspuns invalid). Gol → pasul AI este dezactivat. Afecțiunea întoarsă se folosește ca una din dicționar: în chat, în căutare și în titlul PDF-ului. |
| `CONDITION_AI_LOCAL_MODEL` | `gemma3:1b` | Modelul Ollama local (descărcare: `ollama pull gemma3:1b`; în Docker: `docker compose exec ollama ollama pull gemma3:1b`). |
| `CONDITION_AI_LOCAL_BASE` | `http://localhost:11434/v1` (direct) / `http://ollama:11434/v1` (Compose) | Adresa Ollama folosită pentru identificarea afecțiunii. |
| `CONDITION_AI_HF_MODEL` | valoarea `HF_MODEL` | Modelul HF pentru fallback (prin `HF_API_BASE` și `HF_TOKEN`). |
| `CONDITION_AI_TIMEOUT_SECONDS` | `10` | Timeout per backend la identificarea afecțiunii. |
| `CONDITION_AI_MAX_OUTPUT_TOKENS` | `300` | Limita răspunsului (un JSON mic) la identificarea afecțiunii. |
| `AI_STREAM` | `false` | Cere răspunsul ca flux de evenimente (`stream: true`). Timeoutul de citire se aplică între evenimente, deci evită tăierea cererilor lungi de un proxy (ex. 504 după 60 s la routerul HF). Dacă furnizorul nu suportă streaming, lăsați `false`. |
| `AI_MAX_OUTPUT_TOKENS` | `20000` | `max_output_tokens` al cererii, pentru toți furnizorii (la modelele cu gândire, reasoning-ul consumă din el). |
| `AI_READ_TIMEOUT_SECONDS` | `300` | Timeoutul de citire al cererii către furnizorul AI. |
| `DOCUMENTS_DIR` | `medicina-naturista-documente/data/documents` | Directorul documentelor locale. |
| `HERBS_FILE` | `medicina-naturista-documente/data/herbs.jsonl` | Catalogul de plante medicinale (JSON Lines, o specie pe linie), citit de `backend/ai/herbs.py`; se reîncarcă automat când se modifică. Încă nu e folosit de căutare sau de fragmentare. |
| `DATABASE_URL` | `postgresql:// medicina:medicina @127.0.0.1:5432/medicina` | Conexiunea Postgres a indexului hibrid (`pgvector` + `tsvector`). |
| `DATABASE_BOOTSTRAP_URL` | gol | Conexiune de mentenanță opțională pentru crearea unei baze lipsă, pe același server ca `DATABASE_URL`; folosită numai de reindexare. Implicit se folosesc credențialele țintei pe baza `postgres`. |
| `MODEL_CACHE_DIR` | `model_cache` | Directorul cache-ului local al modelului ONNX. |
| `EMBEDDING_THREADS` | `8` (cel mult numărul de nuclee) | Firele de execuție ale modelului de embedding (ONNX Runtime), la indexare și la căutare. Pe procesoare hibride P/E-core, mai puține fire sunt de obicei mai rapide decât toate nucleele. |
| `EMBEDDING_DEVICE` | `cpu` | Dispozitivul modelului de embedding la **construirea** indexului: `cpu` (FastEmbed/ONNX) sau `cuda` (PyTorch fp16, doar din mediul GPU `.venv-gpu`; fără CUDA build-ul se oprește, nu trece pe CPU). Întrebările din aplicație rulează mereu pe CPU. |
| `SESSION_TEMP_DIR` | `var/sessions` (Windows) / `/tmp/naturist-sessions` | Directorul fișierelor temporare ale sesiunilor. |
| `MAX_CHAT_CHARS` | `4000` | Lungimea maximă a mesajului utilizatorului. |
| `X_AI_MAX_CONTEXT_CHARS` | `1000000` | Bugetul (în caractere de text al fragmentelor) pentru `AI_PROVIDER=xai`: fragmentele afișate și trimise către AI. Toate fragmentele primesc scor, se ordonează descrescător, iar cele de la coadă care nu încap sunt eliminate întregi, nu trunchiate. Nu există un prag de relevanță separat și nici o limită de candidați per semnal. |
| `MAX_REQUESTS_PER_MINUTE` | `60` | Limita de cereri `POST`/`PUT`/`DELETE` către `/api/` acceptate într-un minut, pe IP. |
| `SESSION_IDLE_SECONDS` | `3600` | Expirarea unei sesiuni inactive. |
| `SESSION_MAX_SECONDS` | `14400` | Durata maximă a unei sesiuni. |
| `MAX_ACTIVE_SESSIONS` | `100` | Numărul maxim de sesiuni în proces. |
| `MAX_SESSIONS_PER_COOKIE` / `MAX_SESSIONS_PER_IP` | `1` / `1` | Limitele sesiunilor simultane per browser, respectiv IP. |
| `MAX_API_BODY_BYTES` | `262144` | Dimensiunea maximă a corpului unei cereri API. |
| `MAX_CONCURRENT_SEARCHES` / `MAX_CONCURRENT_GENERATIONS` | `2` / `1` | Limite de concurență per proces. |
| `OPERATION_TIMEOUT_SECONDS` | `600` | Durata totală acceptată pentru o operație. |
| `DEPLOYMENT_PROFILE` | `local` | `public` validează HTTPS, cookie-uri securizate și dezactivarea logării de conținut; trebuie transmis explicit în Compose. |
| `COOKIE_SECURE` | `false` (direct) / `true` (Compose) | Impune transmiterea cookie-ului numai prin HTTPS. |
| `OWNER_KEY` | _(gol)_ | Cheie secretă lungă, introdusă în formularul `/owner` și trimisă prin `POST /api/owner/login`. Autorizările individuale persistă în PostgreSQL până la logout; rotația cheii le invalidează. Cookie-ul este reînnoit cu Max-Age de 365 de zile la activitate autorizată. |
| `LOG_LEVEL` | `INFO` | Nivelul minim al logurilor. |
| `LOG_FRAGMENT_TEXT` | `false` (direct) / `true` (Compose) | Opțiune de compatibilitate; clientul AI actual loghează numai metadata tehnică, fără textul fragmentelor. Profilul `public` cere `false`. |
| `LOG_FRAGMENT_TEXT_MAX_CHARS` | `4000` | Opțiune de compatibilitate; clientul AI actual nu loghează textul fragmentelor. |
| `LOG_AI_RESPONSE_TEXT` | `false` | Opțiune de compatibilitate; clientul AI actual nu loghează corpul răspunsului nici dacă este activată. Profilul `public` cere `false`. |
| `APP_HOST_PORT` | `8760` (Docker Compose) | Portul de pe host la care Compose publică aplicația. |
| `POSTGRES_PASSWORD` | — (obligatoriu în Docker Compose) | Parola Postgres a serviciului `db`; Compose construiește din ea `DATABASE_URL` pentru aplicație. |
| `POSTGRES_USER` / `POSTGRES_DB` | `medicina` / `medicina` (Docker Compose) | Utilizatorul și baza serviciului `db`. |
| `DB_HOST_PORT` | `5432` (Docker Compose) | Portul de pe host (doar `127.0.0.1`) la care Compose publică Postgres. |
| `APP_DOMAIN` / `CADDY_SITE_SCHEME` | `localhost` / `http` (Docker Compose) | Hostname-ul și schema site-ului servit de Caddy. |
| `PUBLIC_ROOT_PATH` | gol (direct) / `/medicina` (Docker Compose) | Prefixul căii publice, necesar când aplicația este expusă de un reverse proxy sub `/medicina`: intră în linkul de descărcare a PDF-ului și, la build-ul imaginii, devine `PUBLIC_BASE_PATH` pentru frontend. |
| `PUBLIC_ORIGIN` | gol | Originea publică exactă (`https://hostname`, fără `/medicina`), pentru validarea originii când TLS se termină la ngrok/proxy și backendul primește HTTP. Dacă este gol, se compară cu originea cererii ASGI. |
| `FRONTEND_DIST_DIR` | `src/frontend/dist` | Directorul cu build-ul React servit ca fișiere statice de FastAPI. |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Allowlist Uvicorn pentru IP-urile/CIDR-urile proxy-urilor autorizate; aplicația nu interpretează direct `X-Forwarded-For`. |

Creșterea bugetului de context (`*_MAX_CONTEXT_CHARS`) mărește numărul de fragmente afișate, timpul de procesare și dimensiunea requestului trimis către furnizorul AI. În medii în care logurile nu au acces controlat, setați `LOG_FRAGMENT_TEXT=false`.

La pornirea directă, aplicația citește valorile din `.env`; valorile implicite diferă unde este indicat. Docker Compose transmite variabilele enumerate în secțiunea `environment`; `COOKIE_SECURE` este implicit `false` la pornire directă și `true` în Compose. `OWNER_KEY` este opțional, dar fără el generarea raportului este dezactivată; setați o cheie secretă și autorizați browserul prin formularul `/owner`. IP-ul pentru limite este furnizat de serverul ASGI; aplicația nu interpretează `X-Forwarded-For`. În deploymentul cu proxy, configurați allowlistul explicit `FORWARDED_ALLOW_IPS` al Uvicorn pentru proxy-urile autorizate; vechiul `TRUST_PROXY` nu mai acordă încredere antetelor.

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
.\.venv\Scripts\python.exe src\scripts\google_oauth_setup.py
```

Este solicitat numai scope-ul `gmail.send`. Tokenul nu este afișat și nu trebuie publicat. Dacă integrarea nu este complet configurată, raportul rămâne disponibil în aplicație, iar livrarea e-mail este omisă.

## 🔐 Confidențialitate și siguranță

- 🔒 `.env` și cache-ul modelului sunt ignorate de Git; indexul locuiește în Postgres, nu în fișiere din repo.
- 🧭 fiecare fragment rămâne legat de fișierul și liniile sursă;
- 🧹 conversațiile și PDF-urile stau doar în memorie, separate pe tab, și sunt eliminate la închiderea paginii, la expirare sau la repornirea aplicației; nicio informație medicală a pacientului nu se scrie în baza de date;
- 🚫 requesturile xAI folosesc `store=false` (pentru DeepSeek, Hugging Face și Ollama parametrul nu se trimite; se aplică politicile lor de retenție);
- 🩺 răspunsurile sunt informative și trebuie verificate medical înainte de utilizare.

## 🧪 Testare

Comenzile se execută din rădăcina proiectului. Rezultatele validării planului 04 din 11 octombrie 2026 și verificările rămase sunt în [architecture/plan04-implementation.md](architecture/plan04-implementation.md).

Instalați uneltele de dezvoltare în mediul CPU (nu în `.venv-gpu`):

```powershell
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s src/tests/unit -t src -v
.\.venv\Scripts\python.exe -m pytest src/tests/unit/ai/test_report_validation.py src/tests/unit/web/test_report_integrity.py -q
```

Unitarele folosesc dependențe simulate și nu necesită Docker, PostgreSQL, `.env` sau corpusul personal. Testele de integrare folosesc implicit un PostgreSQL/pgvector efemer și corpus sintetic:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s src/tests/integration -t src -v
.\.venv\Scripts\python.exe -m pytest src/tests/integration/test_index_integrity.py -q
```

Docker trebuie să fie disponibil pentru integrare. Alternativ, `TEST_POSTGRES_URL` poate indica **exclusiv o bază de test dispensabilă**: fixture-urile îi modifică schema și datele. Nu folosiți baza aplicației. Testele corpusului și cataloagelor personale necesită separat `RUN_LOCAL_CORPUS_TESTS=1`; nu sunt activate în CI.

Verificările statice și frontend:

```powershell
.\.venv\Scripts\python.exe -m ruff check src
.\.venv\Scripts\python.exe -m ruff format --check src
.\.venv\Scripts\python.exe -m mypy
npm --prefix src/frontend ci
npm --prefix src/frontend run test
npm --prefix src/frontend run typecheck
npm --prefix src/frontend run build
```

Ruff nu rescrie fișiere în CI. Mypy verifică gradual configurația, contractele, modelele, serviciul conversației, bugetul operațiilor și evaluatorul de conținut. Dicționarele third-party din `src/scripts/dictionaires` și scripturile experimentale `icd10_work` sunt excluse din formatarea/lintul aplicației.

### Dependențe și CI

`pyproject.toml` este sursa declarațiilor. Lockurile sunt generate cu pip-tools, includ dependențele tranzitive și hashurile distribuțiilor și păstrează versiunile existente fără upgrade implicit:

| Mediu | Runtime | Dezvoltare |
|---|---|---|
| Windows, Python 3.11 | `requirements-runtime.lock` | `requirements-dev.lock` |
| Linux, Python 3.11 | `requirements-runtime-py311-linux.lock` | `requirements-dev-py311-linux.lock` |

Generați fiecare pereche pe sistemul și versiunea Python corespunzătoare:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m scripts.manage_dependencies --generate
.\.venv\Scripts\python.exe -m scripts.manage_dependencies --check
```

`requirements-locks.json` înregistrează hashul declarațiilor și al fiecărui lock. CI refuză declarații schimbate fără regenerare. `requirements-web.txt` și `requirements-lock.txt` sunt aliasuri pentru lockul Windows/Python 3.11; pe Linux folosiți perechea Linux. Mediul GPU existent și modelul `Qwen/Qwen3-Embedding-0.6B` sunt păstrate.

Workflow-ul `.github/workflows/ci.yml` separă verificările statice, unitarele Python 3.11, integrarea pgvector, frontendul și buildul Docker. Folosește date sintetice și nu publică corpusul personal.

### Evaluarea retrieval-ului la nivel de conținut

Evaluatorul structural existent rămâne disponibil. Noul mod `--content` folosește exact 30 de cazuri din `src/tests/eval/content_cases.json`, acoperind afecțiuni, sinonime, exprimări libere și atenționări. Fiecare fragment este identificat prin cale relativă și SHA-256 al textului, independent de ID-ul PostgreSQL.

Cazurile livrate sunt etichetate pentru corpusul sintetic din `src/tests/eval/synthetic_corpus`. Clasamentele din `synthetic_rankings.json` și baseline-ul analitic ideal verifică mecanismul metricilor; **nu măsoară calitatea modelului pe corpusul personal**:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_retrieval --content --rankings src/tests/eval/synthetic_rankings.json --baseline src/tests/eval/synthetic_baseline.json --output var/output/synthetic-metrics.json
```

Pentru un index real, pregătiți local 30 de cazuri cu hashuri din acel corpus, apoi măsurați baseline-ul înaintea schimbării scoringului. Datele personale și etichetele locale rămân în `var/output`:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_retrieval --content --dotenv --cases var/output/content-cases-local.json --output var/output/retrieval-before.json
.\.venv\Scripts\python.exe -m scripts.evaluate_retrieval --content --dotenv --cases var/output/content-cases-local.json --baseline var/output/retrieval-before.json --output var/output/retrieval-after.json
```

Raportul include Recall@50 din fragmentele relevante etichetate, nDCG@10 cu grade 0–3, numărul rezultatelor etichetate ca irelevante în top 10, fragmentele fără etichetă în top 10 și acoperirea atenționărilor așteptate în top 50. Comparația refuză corpusuri/cazuri/configurații diferite și raportează regresii pe fiecare caz, cu exit code 2. O nouă generație a aceluiași conținut poate fi comparată. Aceste metrici nu validează clinic sursele.

### Operare și limite

`MAX_CONCURRENT_SEARCHES=2` și `MAX_CONCURRENT_GENERATIONS=1` plafonează operațiile per proces (un worker Uvicorn). Excesul primește 429; aceeași căutare deja în generare primește 409. `OPERATION_TIMEOUT_SECONDS=600` limitează durata totală acceptată a operației, inclusiv AI, validare, PDF și publicare. Nu există retry automat. Emailul este o operație separată.

Un apel extern deja trimis poate continua până la timeout/terminare, însă rezultatul tardiv este abandonat; capacitatea rămâne ocupată cât workerul încă rulează. Căutarea rămâne disponibilă pentru reîncercare explicită. Închiderea sesiunii anulează dreptul de publicare.

`DEPLOYMENT_PROFILE=local` este implicit. Profilul `public` cere `PUBLIC_ORIGIN=https://...`, `COOKIE_SECURE=true` și logare de conținut dezactivată. `LOG_FRAGMENT_TEXT` și `LOG_AI_RESPONSE_TEXT` sunt false implicit la pornirea directă, dar Compose setează `LOG_FRAGMENT_TEXT=true` dacă nu este suprascris. `DEPLOYMENT_PROFILE` nu este transmis de actualul fișier Compose: pentru profilul `public`, adăugați-l explicit în `app.environment` și dezactivați ambele opțiuni de logare. `/readyz` verifică deja indexul; configurarea proxy-urilor este descrisă în documentația de operare.

Reindexarea creează baza lipsă și execută migrările înainte de fragmentare; aplicația web nu aplică migrări la startup; rebuildul indexului are lock de mentenanță și păstrează generația anterioară la eșec. Diagnosticul folosește `/readyz` și codurile erorilor, fără ștergeri manuale ale indexului:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m scripts.build_hybrid_index
```

Starea implementării și pașii de verificare manuală sunt în [architecture/plan04-implementation.md](architecture/plan04-implementation.md).

## Extragerea PDF în Markdown

`src/scripts/extract_pdf_markdown.py` extrage textul local și reconstruiește titlurile
din semnele de carte, numerotare, dimensiunea fonturilor și spațiere. Prima pagină
este inclusă; nu există reguli specifice unei anumite cărți. Ordinea de citire se
adaptează la una, două sau trei coloane. Reperele `<!-- Pagina PDF N -->` păstrează
legătura cu sursa.

Instalați dependențele opționale în mediul virtual:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[pdf]"
```

Pentru scanări fără strat de text este necesar și programul Tesseract, cu limbile
`ron` și `eng`. Este detectat din PATH sau din `C:\Program Files\Tesseract-OCR`;
puteți indica altă instalare prin `--tesseract-cmd`.

```powershell
.\.venv\Scripts\python.exe src\scripts\extract_pdf_markdown.py "carte.pdf" -o "carte.md" --report "carte.extraction.json"
```

Implicit, `--ocr auto` citește textul existent și folosește OCR numai pentru pagini
fără text. `--ocr always` recitește toate paginile din imagini, iar `--ocr never`
dezactivează OCR. `--deskew auto` corectează coordonatele textului sau imaginea
scanată pentru înclinări de până la ±30°; `--deskew off` dezactivează corecția.
`--columns auto` poate fi înlocuit cu `1`, `2` sau `3` pentru documente ambigue.
`--start-page` și `--end-page` permit verificarea unui interval înainte de conversia
completă. Raportul JSON include unghiul estimat, numărul de coloane, metoda de
extragere și paginile fără text. Ieșirea Markdown este înlocuită numai după o
extragere reușită.

Ierarhia este euristică: fonturile uniforme din OCR, paginile cu orientări mixte,
tabelele complexe și scanările degradate pot necesita verificare manuală.
Extractorul păstrează grafia sursei și nu corectează semantic erorile OCR.

## 📜 Licență

Codul proiectului este distribuit sub [Business Source License 1.1](LICENSE) ([versiunea în română](LICENSE.ro.md)). Utilizarea în medii non-producție este gratuită; utilizarea în producție necesită un acord comercial separat cu licențiatorul. Apache 2.0 este licența prevăzută după schimbare, conform termenilor din `LICENSE`, nu licența inițială a proiectului.

---

<div align="center">

🌱 **Surse verificabile · retrieval local · recomandări adjuvante**

</div>
