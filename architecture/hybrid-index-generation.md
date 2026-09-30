# Fluxul de sincronizare a indexului hibrid

**Intrare:** fișierele Markdown din `data/documents`.

**Ieșire:** indexul semantic (`pgvector`) și indexul lexical (`tsvector`) din Postgres, actualizate incremental.

## 1. Pornirea procesului — `rebuild_index.ps1`

- **1.1.** Primește parametrul `BatchSize`; valoarea implicită este `64`.
- **1.2.** Configurează PowerShell să se oprească la prima eroare.
- **1.3.** Determină directorul-rădăcină al proiectului.
- **1.4.** Elimină `HF_HUB_OFFLINE`, astfel încât modelul să poată fi descărcat dacă nu există deja în cache.
- **1.5.** Pornește Python din `.venv`.
- **1.6.** Execută `build_hybrid_index.py` cu următoarele argumente:
  - **1.6.1.** `--source data/documents`.
  - **1.6.2.** `--batch-size 64` sau valoarea furnizată de utilizator.
- **1.7.** Returnează codul de ieșire primit de la scriptul Python.

Conexiunea Postgres vine din `.env` (`DATABASE_URL`), citită de `medicina_naturista.config.settings` — nu e un argument al scriptului.

## 2. Pregătirea — `build_hybrid_index.py`

- **2.1.** Convertește directorul sursă într-o cale absolută și verifică existența `data/documents`.
- **2.2.** Creează extensiile și tabelele Postgres dacă nu există deja (`ensure_schema()` — `vector`, `unaccent`, tabelele `documents`, `chunks`, `sync_metadata`).
- **2.3.** Găsește recursiv toate fișierele cu extensia `.md` și le sortează determinist după calea relativă.
- **2.4.** Oprește procesul dacă nu este găsit niciun fișier Markdown.
- **2.5.** Interoghează `documents` pentru harta `cale_relativă → sha256` deja sincronizată.

## 3. Decizia „sar peste” vs. „re-procesez”, per fișier

- **3.1.** Pentru fiecare fișier, calculează SHA-256 direct din bytes (fără a decodifica sau fragmenta conținutul).
- **3.2.** Dacă acest SHA-256 este identic cu cel deja stocat pentru aceeași cale relativă → fișierul este **sărit complet**: nu este citit, fragmentat sau trimis către modelul de embeddings, și nu se face niciun apel către baza de date pentru el.
- **3.3.** Altfel, fișierul intră în lista „de procesat”: se citește, se fragmentează (secțiunea 4) și fragmentele sale se adaugă la lotul care va fi trimis modelului de embeddings (secțiunea 5).

Acesta este mecanismul de sincronizare incrementală: adăugarea sau modificarea unui singur document nu regenerează embeddings pentru restul corpusului.

## 4. Citirea și împărțirea fiecărui document „de procesat” în fragmente

- **4.1.** Citește conținutul brut al fișierului.
- **4.2.** Încearcă succesiv decodificarea `UTF-8 BOM`, `UTF-8`, `UTF-16`, `CP1250` și `CP1252`.
- **4.3.** Normalizează sfârșiturile de linie și elimină caracterele NUL.
- **4.4.** Normalizează Unicode la NFC, păstrând diacriticele românești.
- **4.5.** Creează metadatele `SourceFile`: cale, dimensiune, codificare, număr de linii și suma de control SHA-256.
- **4.6.** Împarte documentul în fragmente cu `fragment_document()` (`ai/fragmenter.py`). Fiecare fragment primește o categorie de business (`business_category`: `R1`, `R2` sau `D1`) și, pentru R1 și R2, afecțiunile din `data/medical_conditions.txt` despre care este vorba. Un capitol este un titlu Markdown (marcajele `Pagina N` nu sunt titluri). Afecțiunile se caută pe cuvinte întregi, fără diacritice și fără diferență între majuscule și minuscule, cu toleranță la terminațiile românești (`gripa`/`gripei`), indiferent de lungimea termenului (nu există prag minim), iar la aceeași poziție câștigă termenul cel mai lung. O afecțiune se potrivește prin denumirea ei sau prin oricare dintre sinonimele de pe același rând (SAU). **Numele fișierului și folderele nu se compară cu afecțiunile**; nu există fragment „document întreg”. Pașii de mai jos se aplică în ordine.
- **4.7.** **R1 — titlul capitolului conține o afecțiune.** Titlurile sunt parcurse de jos în sus (cele mai adânci primele), deci un subcapitol cu afecțiune în titlu este mereu fragment separat, iar părintele păstrează doar ce a rămas din subarborele lui. Fragmentul începe cu propriul titlu, fără titlurile strămoșilor. Un titlu rămas fără text nu produce fragment. Liniile luate sunt excluse din pașii următori.
- **4.8.** **R2 — textul propriu al capitolului menționează o afecțiune.** Între titlurile rămase, cele al căror text propriu (până la următorul titlu de orice nivel) conține o afecțiune devin fragmente formate din propriul titlu și acel text, fără titlurile strămoșilor; mai multe afecțiuni în aceeași secțiune dau un singur fragment. Liniile luate sunt excluse din pasul următor.
- **4.9.** **Afecțiunile fragmentelor R1 și R2.** `primary_medical_conditions` = afecțiunile din propriul titlu (la R2 este mereu gol, altfel fragmentul ar fi R1). `secondary_medical_conditions` = afecțiunile din textul fragmentului, fără linia titlului. Cele două liste se pot suprapune. Se rețin denumirile canonice.
- **4.10.** **D1 — restul textului.** Fiecare porțiune continuă de linii rămase (inclusiv textul de sub niciun titlu și documentele fără titluri) este tăiată în bucăți de ~1800 de caractere (`D1_TARGET_CHARS`), la cea mai bună limită din intervalul 1500–2100: sfârșit de paragraf, apoi de propoziție, apoi de rând, apoi spațiu. Bucata următoare începe la un început de propoziție (altfel de rând, altfel de cuvânt) din ultimele cel mult 270 de caractere ale bucății anterioare (`D1_MAX_OVERLAP_CHARS`). O bucată nu trece peste un fragment R1/R2, iar tăietura nu lasă mai puțin de 300 de caractere pentru bucata următoare. O porțiune formată doar din titluri și linii albe nu produce fragment. Fragmentele D1 nu au afecțiuni.
- **4.11.** Fragmentele R1 și R2 nu au limită de lungime.
- **4.12.** `heading` = lanțul de titluri până la titlul propriu al fragmentului (`Carte > Plante > Mușețel`); pentru D1, lanțul secțiunii în care începe bucata, sau gol. Este doar metadată (afișare, semnalul „titlu" din căutare, contextul raportului); nu intră în textul fragmentului și nu este folosit la determinarea afecțiunilor.
- **4.13.** Marcajele `Pagina N` sunt scoase din text și din cale.
- **4.14.** Creează câte un obiect `Chunk` pentru fiecare fragment, cu calea sursei, suma de control a sursei, intervalul de linii (primul și ultimul rând al fragmentului), calea titlurilor (`heading`), textul, numărul de caractere, categoria documentului, `business_category`, `primary_medical_conditions` și `secondary_medical_conditions` — fără un id sau o poziție în matrice: rândul din `chunks` este alocat de Postgres (`BIGSERIAL`) la inserare.
- **4.15.** Raportează progresul scanării după fiecare 50 de fișiere și după ultimul fișier, cu numărul de fișiere schimbate față de cele nemodificate.
- **4.16.** Un document fără text indexabil produce doar un avertisment.

## 5. Generarea embedding-urilor

Rulează o singură dată, peste **toate** fragmentele tuturor documentelor „de procesat” adunate la pasul 3 — nu per document — pentru eficiență la loturi (`batch_size`). Dacă niciun document nu s-a schimbat, acest pas este sărit complet: modelul nici măcar nu este încărcat.

- **5.1.** Încarcă modelul ONNX din `data/model_cache` (implicit `intfloat/multilingual-e5-small`), offline, descărcându-l doar dacă lipsește din cache.
- **5.2.** Construiește fiecare intrare E5 din: prefixul `passage:`, categoria, numele fișierului-sursă, titlul sau secțiunea semantică (când există) și textul fragmentului.
- **5.3.** Un fragment mai lung de `MAX_CHARS=1400` este împărțit în ferestre care se suprapun cu `OVERLAP_CHARS=240`; toate ferestrele tuturor fragmentelor sunt trimise modelului în loturi de 64 sau cu dimensiunea solicitată, iar vectorul unui fragment este media normalizată a ferestrelor lui.
- **5.4.** Raportează aproximativ la fiecare 10 secunde ferestrele procesate, procentul, timpul scurs, viteza și timpul estimat rămas.
- **5.5.** Colectează câte un vector cu 384 de dimensiuni pentru fiecare fragment.
- **5.6.** Verifică dacă forma matricei este `(fragment_count, 384)`.
- **5.7.** Verifică dacă toți vectorii conțin valori finite și dacă niciunul nu este vector nul.
- **5.8.** Normalizează L2 fiecare vector.
- **5.9.** După finalizare, verifică din nou dimensiunea și data ultimei modificări a fiecărui fișier „de procesat”; oprește sincronizarea dacă vreunul s-a schimbat în timpul embedding-ului.

## 6. Scrierea fiecărui document „de procesat” — o tranzacție per document

Pentru fiecare document din lista „de procesat” (secțiunea 3), într-o singură conexiune/tranzacție:

- **6.1.** Șterge din `chunks` toate fragmentele vechi ale acelui `source_relative_path`.
- **6.2.** Face `INSERT ... ON CONFLICT (relative_path) DO UPDATE` în `documents` cu metadatele noi (dimensiune, dată, SHA-256, categorie).
- **6.3.** Inserează fragmentele noi în `chunks`, fiecare cu `business_category`, `primary_medical_conditions`, `secondary_medical_conditions`, vectorul lui semantic (`embedding`) și coloana lexicală `text_search` calculată la inserare (`to_tsvector('simple', unaccent(text || heading || cale))`, echivalentul indexării pe cele trei coloane pe care FTS5 o făcea înainte).

Niciun cititor nu vede vreodată un document cu doar o parte din fragmentele lui noi scrise, iar eșecul scrierii unui document nu afectează documentele deja scrise cu succes în aceeași rulare.

## 7. Documente eliminate din sursă

- **7.1.** Orice cale relativă prezentă în `documents` dar absentă din listarea curentă a `data/documents` este ștearsă din `documents` (`DELETE ... WHERE relative_path = ANY(...)`).
- **7.2.** Ștergerea cascadează automat la `chunks`, prin cheia străină `ON DELETE CASCADE`.

## 8. Metadate și rezumat

- **8.1.** Scrie în `sync_metadata` numele modelului, dimensiunea vectorilor și data/ora ultimei sincronizări.
- **8.2.** Afișează un rezumat JSON: numărul de fișiere scanate, nemodificate, sincronizate și eliminate, numărul de fragmente scrise și numărul de avertismente.
- **8.3.** Returnează codul de ieșire `0` către `rebuild_index.ps1` atunci când sincronizarea reușește.
- **8.4.** În caz de eroare, afișează tipul și mesajul excepției și returnează un cod de ieșire diferit de zero.

## Rezultatul final

```text
data/documents/*.md
        ↓ (SHA-256 neschimbat?) ── da ──→ sărit, neatins
        ↓ nu
   fragmentare + embeddings (doar fișierele schimbate)
        ↓
   Postgres: documents, chunks (embedding + text_search), sync_metadata
```

Indexul este consumat la rulare de `src/medicina_naturista/ai/search.py` (`rank()`) și `ai/retrieval.py`; vezi [fluxul de generare a raportului final](final-report-generation.md) și [căutarea, unirea și scoringul fragmentelor](fragment-search-and-scoring.md).
