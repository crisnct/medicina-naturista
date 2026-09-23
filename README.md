# Index local pentru arhiva medicală

Proiectul construiește un index hibrid din fișierele Markdown aflate recursiv în folderul `documents`. Cele șase artefacte ale indexului sunt păstrate în `embedings`, iar modelul descărcat în `model_cache`. Ambele foldere sunt generate local și nu sunt păstrate în Git.

## Conținut

- `embedings/manifest.json` — configurația, numărul de surse și fragmente, modelul și avertismentele.
- `embedings/source_manifest.jsonl` — câte o înregistrare pentru fiecare fișier, cu SHA-256 și metadate.
- `embedings/chunks.jsonl` — fragmentele indexate, cu calea-sursă, titlul/secțiunea și liniile.
- `embedings/embeddings.npy` — matricea semantică `float32`, normalizată; rândul este indicat de `embedding_row`.
- `embedings/index.sqlite3` — metadate, fragmente și index lexical FTS5.
- `embedings/SHA256SUMS.txt` — sume de control pentru artefactele principale.
- `search_medical_embeddings.py` — căutare hibridă semantică + lexicală.
- `search.ps1` — lansator PowerShell offline.
- `rebuild.ps1` — reconstruiește indexul după modificarea surselor.

## Căutare

La prima utilizare, instalează Python 3.11 și reconstruiește indexul:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\rebuild.ps1
```

Prima reconstruire descarcă modelul în `model_cache` și poate dura câteva zeci de minute. După aceea, căutarea funcționează offline.

```powershell
& 'D:\Workspace\medicina-naturista\search.ps1' "plante și măsuri pentru tuse"
```

Pentru rezultate JSON:

```powershell
& 'D:\Workspace\medicina-naturista\search.ps1' "plante și măsuri pentru tuse" -Json
```

Rezultatele indică fișierul absolut și intervalul de linii. Aceste referințe trebuie păstrate în orice document creat ulterior.

## Reconstruire

După adăugarea sau modificarea fișierelor-sursă:

```powershell
& 'D:\Workspace\medicina-naturista\rebuild.ps1'
```

`rebuild.ps1` găsește `documents` relativ la propria locație, inclusiv dacă este lansat din alt director. Pentru rularea directă a scriptului Python, `--source` folosește implicit același folder; opțiunea poate fi specificată pentru o altă sursă. Modelul este descărcat o singură dată în `model_cache`; inferența și interogările rulează local. `search.ps1` activează modul offline.

## Aplicația web

Interfața este Gradio, montată în FastAPI. Nu are conturi. Refolosește modelul local, indexul hibrid și fișierele din `documents/`. Conversațiile, fișierele încărcate și PDF-urile sunt temporare și separate pe sesiune/tab. Modelul xAI este folosit numai după o verificare Zero Data Retention; fără confirmarea ZDR, informațiile medicale nu sunt trimise.

### Docker Compose

Necesare: Docker cu Compose, folderele existente `documents/`, `embedings/` și `model_cache/`, plus o cheie xAI cu ZDR activ. Configurați `APP_DOMAIN` și limitele în fișierul `.env` existent. Pentru rularea în Docker, setați `GROK_API_KEY_MED` în fișierul `.env` existent:

```powershell
docker compose build
docker compose up -d
docker compose ps
Invoke-WebRequest http://localhost:7860/healthz
```

Fișierul `.env` este ignorat de Git. Compose transmite variabila `GROK_API_KEY_MED` aplicației la pornire; cheia nu este inclusă în imagine. Indexul și `documents/` sunt montate doar pentru citire. `model_cache/` este persistat separat. Uploadurile și fișierele temporare sunt în `tmpfs`.

Interfața este disponibilă prin Caddy la `https://APP_DOMAIN`. Pentru un domeniu public, configurați DNS-ul către server și permiteți intrarea pe porturile 80/443. Cu `APP_DOMAIN=localhost`, certificatul local Caddy poate necesita încredere explicită în browser. Portul 7860 este expus doar pe localhost pentru diagnostic; nu îl publicați direct pe internet.

Oprire:

```powershell
docker compose down
```

`docker compose down -v` șterge și certificatele/starea Caddy. Repornirea aplicației elimină conversațiile active. Închiderea sesiunii din UI șterge imediat datele ei, iar sesiunile inactive sunt curățate periodic.

### Pornire directă pentru dezvoltare

Instalați `requirements-web.txt`, configurați `GROK_API_KEY_MED` și `COOKIE_SECURE=false` în fișierul `.env` pentru HTTP local și asigurați instalarea locală a Antiword, Tesseract (`ron` și `eng`), Poppler și fonturilor Unicode. Lansați:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
.\.venv\Scripts\python.exe -m uvicorn web_app.main:app --host 127.0.0.1 --port 7860
```

PDF-urile se descarcă prin endpointul FastAPI asociat cookie-ului și tabului curent. Gradio nu servește cache-ul de uploaduri. Modelul configurat implicit este `grok-4.3`, cu `XAI_REASONING_EFFORT=low`. Recomandările sunt informative, adjuvante și trebuie susținute de sursele locale sau de documentele încărcate în sesiunea curentă. Fontul interfeței este Arial; PDF-ul folosește Arial pe Windows și Liberation Sans, compatibil metric, în Docker.

### Dacă mesajele nu sunt procesate

Dacă apare „Lipsește GROK_API_KEY_MED”, verificați variabila în `.env`, apoi recreați containerul cu `docker compose up -d --force-recreate app`.

Dacă apare „Zero Data Retention nu este confirmat”, cheia funcționează, dar echipa xAI răspunde cu `x-zero-data-retention: false`. Un administrator al echipei trebuie să activeze ZDR în xAI Console, la Team Settings. Până atunci, aplicația refuză apelurile care ar conține date medicale. După activare, încercați din nou în chat.
