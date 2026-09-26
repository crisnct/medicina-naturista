<div align="center">

# 🌿 Recomandări Naturiste Adjuvante

### Chatbot medical informativ bazat pe o arhivă locală și căutare hibridă

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Gradio](https://img.shields.io/badge/Gradio-6.x-FF7C00?logo=gradio&logoColor=white)](https://www.gradio.app/)
[![Hybrid retrieval](https://img.shields.io/badge/Retrieval-Semantic%20%2B%20FTS5-6A5ACD)](#-cum-funcționează)
[![License](https://img.shields.io/badge/License-Apache%202.0-D22128)](LICENSE)

🟢 **surse locale** · 🔵 **căutare semantică** · 🟠 **căutare lexicală** · 🟣 **raport PDF**

</div>

> [!IMPORTANT]
> Aplicația oferă informații orientative și recomandări adjuvante. Nu înlocuiește diagnosticul, consultația, tratamentul prescris sau îngrijirea medicală de urgență.

## ✨ Despre proiect

Proiectul transformă o colecție locală de documente Markdown despre medicină naturistă și terapii complementare într-un index hibrid interogabil. Interfața web primește problema descrisă de utilizator, caută dovezi în arhiva locală, solicită xAI să redacteze un răspuns structurat exclusiv pe baza fragmentelor selectate și generează un raport PDF cu trimiteri la surse.

| 🧩 Componentă | Rol |
|---|---|
| **Index semantic** | Identifică fragmente apropiate ca sens cu vectori E5 de 384 dimensiuni. |
| **Index lexical** | Găsește termeni exacți prin SQLite FTS5 și ordonare BM25. |
| **Fuziune RRF** | Combină clasamentele semantic și lexical prin Reciprocal Rank Fusion. |
| **Retriever medical** | Prioritizează expresia exactă, documentele dedicate și atenționările. |
| **Chat web** | Oferă sesiuni izolate pe tab și afișează recomandările structurate. |
| **Raport PDF** | Include recomandări, atenționări, citări și bibliografie navigabilă. |
| **Livrare e-mail** | Poate trimite raportul prin Gmail API cu OAuth2, dacă este configurat. |

## 🎨 Cum funcționează

```text
📚 documente Markdown
        ↓
✂️ fragmente coerente, cu sursă și interval de linii
        ↓
🧠 embeddings E5  +  🔎 SQLite FTS5
        ↓
⚖️ fuziune RRF și prioritizarea dovezilor
        ↓
🤖 un singur request structurat către xAI
        ↓
💬 recomandări în chat  +  📄 raport PDF  +  ✉️ e-mail opțional
```

> **Local vs. extern:** documentele, fragmentarea, indexarea și retrieval-ul rulează local. Fragmentele selectate sunt trimise către API-ul xAI pentru redactarea raportului. Livrarea prin Gmail este opțională.

## 🛠️ Tehnologii folosite

| Zonă | Tehnologii |
|---|---|
| **Limbaj și runtime** | Python 3.11, PowerShell |
| **Interfață și API** | Gradio 6, FastAPI, Uvicorn |
| **Embeddings locale** | FastEmbed, ONNX Runtime, `intfloat/multilingual-e5-small` |
| **Calcul vectorial** | NumPy, cosine similarity pe vectori normalizați L2 |
| **Căutare lexicală** | SQLite, FTS5, BM25 |
| **Fuziunea rezultatelor** | Reciprocal Rank Fusion — RRF (`k=60`) |
| **Generare AI** | xAI Responses API, răspuns JSON structurat |
| **Documente** | ReportLab pentru PDF, pypdf pentru procesare și verificare |
| **E-mail** | Gmail API, OAuth2 cu refresh token |
| **Configurare** | python-dotenv, variabile de mediu |
| **Rulare și publicare** | Docker, Docker Compose, Caddy |
| **Testare** | `unittest`, teste unitare și de integrare |

## 🗺️ Documentație de arhitectură

| Document | Ce explică |
|---|---|
| 🧠 [Fluxul de generare a indexului hibrid](architecture/hybrid-index-generation.md) | Fluxul complet: documente → fragmente → embeddings → FTS5 → publicarea atomică a indexului. |
| 📄 [Fluxul de generare a raportului final](architecture/final-report-generation.md) | Fluxul complet: mesaj → retrieval hibrid → xAI → PDF → download și e-mail opțional. |

## 📁 Structura proiectului

```text
medicina-naturista/
├── architecture/                 # documentația fluxurilor principale
├── data/
│   ├── documents/                # corpusul Markdown local
│   ├── hybrid_index/             # indexul generat; ignorat de Git
│   └── model_cache/              # modelul ONNX local; ignorat de Git
├── scripts/
│   ├── build_hybrid_index.py     # construirea indexului
│   ├── rebuild_index.ps1         # lansator PowerShell pentru rebuild
│   ├── search_index.ps1          # căutare locală din terminal
│   └── google_oauth_setup.py     # autorizare Gmail OAuth2
├── src/medicina_naturista/
│   ├── ai/                       # căutare, retrieval, client xAI și prompturi
│   ├── core/                     # modele și sesiuni izolate
│   ├── integrations/             # integrarea Gmail
│   ├── reporting/                # generarea raportului PDF
│   └── web/                      # FastAPI, Gradio și resursele UI
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

### 2. Construirea indexului

```powershell
.\scripts\rebuild_index.ps1
```

Batch size-ul implicit este `64`; poate fi schimbat astfel:

```powershell
.\scripts\rebuild_index.ps1 -BatchSize 32
```

Prima construire descarcă modelul în `data/model_cache/` și poate dura câteva zeci de minute. Următoarele căutări folosesc modelul din cache și rulează offline. În timpul embedding-ului sunt afișate progresul, timpul scurs, viteza și ETA.

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
GROK_API_KEY_MED=...
COOKIE_SECURE=false
```

Apoi porniți aplicația:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn medicina_naturista.web.main:app --host 127.0.0.1 --port 7860
```

Deschideți `http://127.0.0.1:7860`. Endpointul de stare este `http://127.0.0.1:7860/healthz`.

## 📦 Artefactele indexului hibrid

Construirea reușită publică atomic șase fișiere în `data/hybrid_index/`:

| Fișier | Conținut |
|---|---|
| `embeddings.npy` | Matricea semantică `float32`, normalizată L2. |
| `index.sqlite3` | Metadate, fragmente și indexul lexical FTS5. |
| `fragments.jsonl` | Export auditabil al fragmentelor și al intervalelor de linii. |
| `source_manifest.jsonl` | Inventarul surselor, metadatele și SHA-256. |
| `manifest.json` | Modelul, dimensiunea vectorilor și strategia de chunking. |
| `SHA256SUMS.txt` | Sumele de control ale artefactelor principale. |

Configurația curentă de chunking este:

```text
TARGET_CHARS  = 1200
MAX_CHARS     = 1400
OVERLAP_CHARS = 240
```

Titlurile Markdown sunt limite stricte de secțiune, diacriticele sunt păstrate prin normalizare Unicode NFC, iar blocurile prea mari sunt separate preferențial la final de propoziție, linie sau cuvânt.

## 🐳 Rulare cu Docker Compose

Înainte de pornire, trebuie să existe `data/documents/`, `data/hybrid_index/`, `data/model_cache/` și fișierul local `.env` cu cheia xAI.

```powershell
docker compose build
docker compose up -d
docker compose ps
Invoke-WebRequest http://localhost:7860/healthz
```

Aplicația rulează într-un container read-only, fără capabilități Linux suplimentare, ca utilizator non-root. Documentele și indexul sunt montate read-only, iar fișierele temporare folosesc `tmpfs`.

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
| `GROK_API_KEY_MED` | — | Cheia necesară pentru generarea raportului. |
| `XAI_MODEL` | `grok-4.3` | Modelul xAI folosit pentru redactare. |
| `XAI_REASONING_EFFORT` | `low` | Nivelul de reasoning solicitat. |
| `DOCUMENTS_DIR` | `data/documents` | Directorul documentelor locale. |
| `INDEX_DIR` | `data/hybrid_index` | Directorul indexului hibrid. |
| `MAX_CHAT_CHARS` | `4000` | Lungimea maximă a mesajului utilizatorului. |
| `MAX_REQUESTS_PER_MINUTE` | `60` | Limita de cereri acceptate într-un minut. |
| `SESSION_IDLE_SECONDS` | `3600` | Expirarea unei sesiuni inactive. |
| `SESSION_MAX_SECONDS` | `14400` | Durata maximă a unei sesiuni. |
| `COOKIE_SECURE` | `false` | Impune transmiterea cookie-ului numai prin HTTPS. |
| `LOG_LEVEL` | `INFO` | Nivelul minim al logurilor. |
| `LOG_FRAGMENT_TEXT` | `true` | Include textul fragmentelor în loguri. |
| `LOG_FRAGMENT_TEXT_MAX_CHARS` | `4000` | Limita textului logat per fragment. |

Creșterea limitelor de retrieval și evidence poate mări timpul de procesare și dimensiunea requestului trimis către xAI. În medii în care logurile nu au acces controlat, setați `LOG_FRAGMENT_TEXT=false`.

La pornirea directă, aplicația citește aceste valori din `.env`. În Docker, `docker-compose.yaml` transmite numai variabilele enumerate în secțiunea `environment`; pentru un override suplimentar, adăugați explicit variabila respectivă în acea secțiune.

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

- 🔒 `.env`, cache-ul modelului și indexurile generate sunt ignorate de Git.
- 🧭 fiecare fragment rămâne legat de fișierul și liniile sursă;
- 🧹 conversațiile și PDF-urile sunt temporare, separate pe sesiune și eliminate la închiderea tabului, la expirare sau la repornirea aplicației;
- 🚫 requesturile xAI folosesc `store=false`;
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
