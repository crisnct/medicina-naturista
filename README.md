# Index local pentru arhiva medicală

Proiectul construiește un index hibrid din fișierele Markdown aflate recursiv în folderul `data/documents`. Cele șase artefacte ale indexului sunt păstrate în `data/hybrid_index`, iar modelul descărcat în `data/model_cache`. Folderele cu artefacte generate local nu sunt păstrate în Git.

## Structura proiectului

- `src/medicina_naturista/core/` — modelele aplicației și sesiunile izolate pe tab.
- `src/medicina_naturista/ai/` — clientul xAI, retrieval, căutarea locală, prompturile și resursele AI.
- `src/medicina_naturista/reporting/` — generarea PDF și resursele raportului.
- `src/medicina_naturista/integrations/` — integrările cu servicii externe, inclusiv Gmail.
- `src/medicina_naturista/web/` — aplicația FastAPI/Gradio, handler-ele UI și fișierele statice.
- `scripts/` — operațiile administrative și utilitarele proiectului.
- `tests/` — teste unitare organizate pe componente și teste de integrare.
- `data/` — documentele, indexul și cache-ul modelului.
- `var/` — rapoarte, sesiuni și fișiere temporare generate la rulare.

## Conținut

- `data/hybrid_index/manifest.json` — configurația, numărul de surse și fragmente, modelul și avertismentele.
- `data/hybrid_index/source_manifest.jsonl` — câte o înregistrare pentru fiecare fișier, cu SHA-256 și metadate.
- `data/hybrid_index/fragments.jsonl` — fragmentele indexate, cu calea-sursă, titlul/secțiunea și liniile.
- `data/hybrid_index/embeddings.npy` — matricea semantică `float32`, normalizată; rândul este indicat de `embedding_row`.
- `data/hybrid_index/index.sqlite3` — metadate, fragmente și index lexical FTS5.
- `data/hybrid_index/SHA256SUMS.txt` — sume de control pentru artefactele principale.
- `src/medicina_naturista/ai/search.py` — căutare hibridă semantică + lexicală.
- `scripts/search_index.ps1` — lansator PowerShell offline.
- `scripts/rebuild_index.ps1` — reconstruiește indexul după modificarea surselor.

## Căutare

La prima utilizare, instalează Python 3.11 și reconstruiește indexul:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\scripts\rebuild_index.ps1
```

Prima reconstruire descarcă modelul în `data/model_cache` și poate dura câteva zeci de minute. După aceea, căutarea funcționează offline.

```powershell
& 'D:\Workspace\medicina-naturista\scripts\search_index.ps1' "plante și măsuri pentru tuse"
```

Pentru rezultate JSON:

```powershell
& 'D:\Workspace\medicina-naturista\scripts\search_index.ps1' "plante și măsuri pentru tuse" -Json
```

Rezultatele indică fișierul absolut și intervalul de linii. Aceste referințe trebuie păstrate în orice document creat ulterior.

## Reconstruire

După adăugarea sau modificarea fișierelor-sursă:

```powershell
& 'D:\Workspace\medicina-naturista\scripts\rebuild_index.ps1'
```

`scripts/rebuild_index.ps1` găsește `data/documents` relativ la rădăcina proiectului, inclusiv dacă este lansat din alt director. Pentru rularea directă a scriptului Python, `--source` folosește implicit același folder; opțiunea poate fi specificată pentru o altă sursă. Modelul este descărcat o singură dată în `data/model_cache`; inferența și interogările rulează local. `scripts/search_index.ps1` activează modul offline.

## Aplicația web

Interfața este Gradio, montată în FastAPI. Nu are conturi. Refolosește modelul local, indexul hibrid și fișierele din `data/documents/`. Conversațiile și PDF-urile sunt temporare și separate pe sesiune/tab. După descrierea problemei, căutarea rulează local, iar raportul este redactat printr-un singur request xAI.

### Docker Compose

Necesare: Docker cu Compose, folderele existente `data/documents/`, `data/hybrid_index/` și `data/model_cache/`, plus o cheie xAI. Configurați `APP_DOMAIN` și limitele în fișierul `.env` existent. Pentru rularea în Docker, setați `GROK_API_KEY_MED` în fișierul `.env` existent.

Rapoartele generate sunt trimise automat la `nelucristian2005@gmail.com` prin Gmail API OAuth2. Configurați în `.env`:

```dotenv
GMAIL_USERNAME=adresa-ta@gmail.com
MAIL_FROM=adresa-ta@gmail.com
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
```

Autorizarea inițială se face o singură dată de proprietarul contului Gmail, cu:

```powershell
.\.venv\Scripts\python.exe scripts\google_oauth_setup.py
```

Scriptul folosește scope-ul `https://www.googleapis.com/auth/gmail.send` și salvează automat `GOOGLE_REFRESH_TOKEN` în `.env`, înlocuind valoarea existentă dacă este prezentă. Tokenul nu este afișat și nu trebuie publicat sau inclus în loguri. Dacă `MAIL_FROM` este gol, aplicația folosește `GMAIL_USERNAME`. Fără configurația OAuth2 completă, generarea raportului continuă, iar trimiterea este omisă (`email_skipped`).

Parametrii de căutare ai arhivei medicale sunt configurați prin variabilele:

- `RETRIEVAL_LIMIT=120` — numărul maxim de rezultate păstrate pentru fiecare interogare;
- `RETRIEVAL_CANDIDATES=720` — numărul de candidați analizați de căutarea hibridă înainte de limitare;
- `EVIDENCE_CONTEXT_CHARS=3000` — numărul maxim de caractere păstrate din fiecare fragment trimis generatorului de raport;
- `MAX_EVIDENCE=2000` — numărul maxim de fragmente distincte reunite în contextul raportului.
- `LOG_LEVEL=INFO` — nivelul minim pentru logurile aplicației.
- `LOG_FRAGMENT_TEXT=true` — include textul fragmentelor în loguri; setați `false` dacă logurile sunt colectate într-un sistem fără control de acces.
- `LOG_FRAGMENT_TEXT_MAX_CHARS=4000` — limita textului unui fragment inclus într-o singură linie de log.

Valorile controlează volumul de dovezi. Creșterea lor poate mări timpul și dimensiunea requestului către AI:

```powershell
docker compose build
docker compose up -d
docker compose ps
Invoke-WebRequest http://localhost:7860/healthz
```

Logurile pentru generarea raportului includ statisticile de căutare, numărul și dimensiunea fragmentelor, sursele unice și inventarul fragmentelor trimise efectiv către AI (`fragments_sent_to_ai`). Dacă este necesară compactarea contextului, sunt logate separat fragmentele înainte de compactare (`fragments_before_compaction`) și fragmentele după compactare, cu `original_text_chars` și `compaction_removed_chars` pentru fiecare fragment. Textul logat este JSON cu newline-urile escapate, pentru a putea fi analizat automat.

Fișierul `.env` este ignorat de Git. Compose transmite variabila `GROK_API_KEY_MED` aplicației la pornire; cheia nu este inclusă în imagine. Indexul și `data/documents/` sunt montate doar pentru citire. `data/model_cache/` este persistat separat. Fișierele temporare sunt în `tmpfs`.

`APP_DOMAIN` trebuie să conțină doar hostname-ul, fără `https://` și fără calea aplicației. Pentru tunel ngrok, folosiți `CADDY_SITE_SCHEME=http`: ngrok termină HTTPS, iar tunelul trebuie să trimită către portul local `80` (`ngrok http 80`). URL-ul public al aplicației rămâne `https://APP_DOMAIN/medicina`, deoarece `GRADIO_ROOT_PATH` este `/medicina`. Pentru un domeniu controlat direct de server, setați `CADDY_SITE_SCHEME=https`, configurați DNS-ul și permiteți accesul public pe porturile 80/443 pentru validarea certificatului Caddy. Portul 7860 este expus doar pe localhost pentru diagnostic; nu îl publicați direct pe internet.

Oprire:

```powershell
docker compose down
```

`docker compose down -v` șterge și certificatele/starea Caddy. Repornirea aplicației elimină conversațiile active. Închiderea sesiunii din UI șterge imediat datele ei, iar sesiunile inactive sunt curățate periodic.

### Pornire directă pentru dezvoltare

Instalați `requirements-web.txt`, configurați `GROK_API_KEY_MED` și `COOKIE_SECURE=false` în fișierul `.env` pentru HTTP local și asigurați existența fonturilor Unicode. Lansați:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn medicina_naturista.web.main:app --host 127.0.0.1 --port 7860
```

PDF-urile se descarcă prin endpointul FastAPI asociat cookie-ului și tabului curent. Modelul configurat implicit este `grok-4.3`, cu `XAI_REASONING_EFFORT=low`. Recomandările sunt informative, adjuvante și trebuie susținute de sursele locale. Fontul interfeței este Inter, cu fallback Arial și sans-serif; PDF-ul folosește Arial pe Windows și Liberation Sans în Docker.

### Dacă mesajele nu sunt procesate

Dacă apare „Lipsește GROK_API_KEY_MED”, verificați variabila în `.env`, apoi recreați containerul cu `docker compose up -d --force-recreate app`.
