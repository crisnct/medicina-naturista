# Fluxul de generare a indexului hibrid

**Intrare:** fișierele Markdown din `data/documents`.

**Ieșire:** indexul semantic, indexul lexical și fișierele de trasabilitate din `data/hybrid_index`.

## 1. Pornirea procesului — `rebuild_index.ps1`

- **1.1.** Primește parametrul `BatchSize`; valoarea implicită este `64`.
- **1.2.** Configurează PowerShell să se oprească la prima eroare.
- **1.3.** Determină directorul-rădăcină al proiectului.
- **1.4.** Elimină `HF_HUB_OFFLINE`, astfel încât modelul să poată fi descărcat dacă nu există deja în cache.
- **1.5.** Pornește Python din `.venv`.
- **1.6.** Execută `build_hybrid_index.py` cu următoarele argumente:
  - **1.6.1.** `--source data/documents`.
  - **1.6.2.** `--output data`.
  - **1.6.3.** `--batch-size 64` sau valoarea furnizată de utilizator.
- **1.7.** Returnează codul de ieșire primit de la scriptul Python.

## 2. Pregătirea directoarelor — `build_hybrid_index.py`

- **2.1.** Convertește directoarele sursă și destinație în căi absolute.
- **2.2.** Verifică existența directorului `data/documents`.
- **2.3.** Verifică dacă directorul de ieșire nu se află în interiorul directorului-sursă.
- **2.4.** Creează `data/hybrid_index` dacă nu există.
- **2.5.** Creează `data/model_cache` dacă nu există.
- **2.6.** Găsește recursiv toate fișierele cu extensia `.md`.
- **2.7.** Sortează fișierele în mod determinist după calea relativă.
- **2.8.** Oprește procesul dacă nu este găsit niciun fișier Markdown.

## 3. Citirea și împărțirea fiecărui document în fragmente

- **3.1.** Citește dimensiunea și data ultimei modificări pentru fiecare fișier `.md`.
- **3.2.** Citește conținutul brut al fișierului.
- **3.3.** Încearcă succesiv decodificarea `UTF-8 BOM`, `UTF-8`, `UTF-16`, `CP1250` și `CP1252`.
- **3.4.** Normalizează sfârșiturile de linie și elimină caracterele NUL.
- **3.5.** Normalizează Unicode la NFC, păstrând diacriticele românești.
- **3.6.** Calculează suma de control SHA-256 a fișierului-sursă.
- **3.7.** Creează metadatele `SourceFile`: cale, dimensiune, codificare, număr de linii și sumă de control.
- **3.8.** Împarte documentul în blocuri Markdown pe baza titlurilor, paragrafelor, listelor și tabelelor.
- **3.9.** Tratează titlurile obișnuite drept limite stricte de secțiune.
- **3.10.** Tratează marcajele `Pagina N` sau `Page N` drept limite flexibile, fără a le folosi ca titluri semantice.
- **3.11.** Pentru blocurile mai mari decât `MAX_CHARS=1400`, caută un punct de separare în această ordine:
  - **3.11.1.** Sfârșitul unei propoziții.
  - **3.11.2.** Sfârșitul unei linii, în special pentru liste și tabele.
  - **3.11.3.** Un spațiu dintre cuvinte.
  - **3.11.4.** Limita strictă de 1.400 de caractere, dacă nu există un punct de separare mai sigur.
- **3.12.** Combină unități complete până când fragmentul se apropie de `TARGET_CHARS=1200`.
- **3.13.** Transferă cel mult `OVERLAP_CHARS=240` de caractere formate din unități complete.
- **3.14.** La limita dintre pagini, poate transfera ultima propoziție completă în fragmentul următor.
- **3.15.** Nu combină niciodată conținut din secțiuni Markdown diferite.
- **3.16.** Creează câte un obiect `Chunk` pentru fiecare fragment, cu:
  - **3.16.1.** Un `chunk_id` unic.
  - **3.16.2.** Poziția `embedding_row` în matricea vectorială.
  - **3.16.3.** Calea sursei și suma de control a sursei.
  - **3.16.4.** Intervalul de linii din sursă.
  - **3.16.5.** Titlul sau secțiunea semantică.
  - **3.16.6.** Textul, numărul de caractere și suma de control a fragmentului.
- **3.17.** Raportează progresul pregătirii după fiecare 50 de fișiere și după ultimul fișier.
- **3.18.** Oprește procesul dacă nu este produs niciun fragment.

## 4. Încărcarea modelului semantic

- **4.1.** Selectează modelul implicit `intfloat/multilingual-e5-small`.
- **4.2.** Verifică dacă FastEmbed cunoaște deja modelul.
- **4.3.** Înregistrează descrierea modelului dacă aceasta nu este deja disponibilă în FastEmbed.
- **4.4.** Încarcă modelul ONNX din `data/model_cache`.
- **4.5.** Descarcă modelul și tokenizerul numai dacă lipsesc din cache-ul local.
- **4.6.** Configurează ONNX Runtime să folosească maximum `numărul de procesoare - 1` fire de execuție.

## 5. Generarea embedding-urilor

- **5.1.** Construiește fiecare intrare E5 pentru document din:
  - **5.1.1.** Prefixul `passage:`.
  - **5.1.2.** Numele fișierului-sursă.
  - **5.1.3.** Titlul sau secțiunea semantică, atunci când este disponibilă.
  - **5.1.4.** Textul fragmentului.
- **5.2.** Trimite fragmentele către model în loturi de 64 sau cu dimensiunea solicitată.
- **5.3.** Raportează aproximativ la fiecare 10 secunde fragmentele procesate, procentul, timpul scurs, viteza și timpul estimat rămas.
- **5.4.** Colectează câte un vector cu 384 de dimensiuni pentru fiecare fragment.
- **5.5.** Verifică dacă forma matricei este `(fragment_count, 384)`.
- **5.6.** Verifică dacă toți vectorii conțin valori finite și dacă niciunul nu este vector nul.
- **5.7.** Normalizează L2 fiecare vector.
- **5.8.** Afișează rezumatul final al etapei de embedding.

## 6. Verificarea fișierelor-sursă după embedding

- **6.1.** Citește din nou dimensiunea și data ultimei modificări pentru fiecare fișier-sursă.
- **6.2.** Le compară cu valorile înregistrate înainte de embedding.
- **6.3.** Oprește construirea dacă un document-sursă s-a modificat în timpul procesării.

## 7. Construirea artefactelor într-un director temporar

- **7.1.** Creează un director temporar de pregătire `data/hybrid_index/index-build-*`.
- **7.2.** Scrie matricea semantică normalizată în `embeddings.npy`.
- **7.3.** Scrie fragmentele și metadatele lor în `fragments.jsonl`.
- **7.4.** Scrie metadatele și sumele de control ale surselor în `source_manifest.jsonl`.
- **7.5.** Creează `index.sqlite3`.
- **7.6.** Creează tabelele SQLite `metadata`, `files` și `chunks`.
- **7.7.** Creează indexul lexical FTS5 `chunks_fts`.
- **7.8.** Inserează în SQLite metadatele, fișierele-sursă, fragmentele și înregistrările FTS.
- **7.9.** Rulează `PRAGMA integrity_check` și se oprește dacă baza de date este invalidă.
- **7.10.** Scrie în `manifest.json` modelul, dimensiunea vectorilor, strategia de chunking și numărul surselor și fragmentelor.
- **7.11.** Calculează sumele de control pentru artefactele principale.
- **7.12.** Scrie sumele de control în `SHA256SUMS.txt`.

## 8. Publicarea indexului hibrid

- **8.1.** Mută fiecare artefact validat din directorul temporar în `data/hybrid_index` folosind `os.replace`.
- **8.2.** Publică următoarele șase fișiere:
  - **8.2.1.** `embeddings.npy` — vectorii semantici.
  - **8.2.2.** `index.sqlite3` — metadatele, fragmentele și indexul lexical FTS5.
  - **8.2.3.** `fragments.jsonl` — exportul auditabil al fragmentelor.
  - **8.2.4.** `source_manifest.jsonl` — inventarul documentelor-sursă.
  - **8.2.5.** `manifest.json` — configurația construirii.
  - **8.2.6.** `SHA256SUMS.txt` — sumele de control ale artefactelor.
- **8.3.** Elimină directorul temporar după ce acesta devine gol.
- **8.4.** Afișează rezultatul JSON final: starea, numărul surselor, numărul fragmentelor, forma matricei și calea de ieșire.
- **8.5.** Returnează codul de ieșire `0` către `rebuild_index.ps1` atunci când construirea reușește.
- **8.6.** În caz de eroare, afișează tipul și mesajul excepției și returnează un cod de ieșire diferit de zero.

## Rezultatul final

```text
data/hybrid_index/
├── embeddings.npy
├── fragments.jsonl
├── index.sqlite3
├── manifest.json
├── source_manifest.jsonl
└── SHA256SUMS.txt
```

Indexul este consumat la rulare de `src/medicina_naturista/ai/search.py` (`rank()`) și `ai/retrieval.py`; vezi [fluxul de generare a raportului final](final-report-generation.md).
