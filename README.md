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
