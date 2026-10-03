# Fluxul de sincronizare a indexului hibrid

**Intrare:** fișierele Markdown din `data/documents`.

**Ieșire:** indexul semantic (`pgvector`) și indexul lexical (`tsvector`) din Postgres, actualizate incremental.

Documentul are două părți: **[Partea I — Rezumat](#partea-i--rezumat)** (cele 8 etape pe scurt) și **[Partea II — Detalii](#partea-ii--detalii)** (aceleași 8 etape, pas cu pas).

----------------------------------------------------------------------------------------------------

## Partea I — Rezumat

1. **Pornire** — `rebuild_index.ps1` rulează `build_hybrid_index.py` peste `data/documents` (loturi de 64); baza de date vine din `DATABASE_URL`.
2. **Pregătire** — creează tabelele dacă lipsesc (`documents`, `chunks`, `sync_metadata`) și citește ce documente sunt deja indexate. Dacă regulile de fragmentare s-au schimbat (`TEXT_REPR_VERSION`), totul se reindexează.
3. **Ce s-a schimbat** — un document cu același SHA-256 ca în bază este sărit complet; doar cele noi sau modificate merg mai departe.
4. **Împărțirea în fragmente** (`fragment_document()`) — capitolul cu afecțiunea în titlu devine fragment **R1**, cel cu afecțiunea doar în text devine **R2**, iar restul se taie în bucăți **D1** de ~1800 de caractere. Afecțiunile vin din `data/medical_conditions.txt`. Fragmentele R1 și R2 primesc două liste de afecțiuni: `primary_medical_conditions` (cele din titlul fragmentului; la R2 mereu goală) și `secondary_medical_conditions` (cele din textul fragmentului, fără titlu). Fragmentele D1 nu au afecțiuni. Căutarea le folosește la scor (P1 și P2).
5. **Vectorii de sens** — modelul local `multilingual-e5-small` calculează pentru fiecare fragment un vector de 384 de valori (fragmentele lungi sunt citite în ferestre de 1400 de caractere).
6. **Salvarea** — o tranzacție per document: fragmentele vechi sunt înlocuite cu cele noi, cu vectorul (`embedding`) și indexul de cuvinte (`text_search`).
7. **Curățenia** — documentele șterse din folder sunt șterse și din bază, împreună cu fragmentele lor.
8. **Final** — se notează în `sync_metadata` modelul și data sincronizării și se afișează un rezumat JSON.

```text
data/documents/*.md → SHA-256 neschimbat? → da: sărit
                                           → nu: fragmente R1/R2/D1 → vectori E5 → Postgres
```

----------------------------------------------------------------------------------------------------

## Partea II — Detalii

### 1. Pornirea procesului — `rebuild_index.ps1`

- **1.1.** Primește parametrul `BatchSize`; valoarea implicită este `64`.
- **1.2.** Configurează PowerShell să se oprească la prima eroare.
- **1.3.** Determină directorul-rădăcină al proiectului.
- **1.4.** Elimină `HF_HUB_OFFLINE`, astfel încât modelul să poată fi descărcat dacă nu există deja în cache.
- **1.5.** Pornește Python din `.venv`.
- **1.6.** Execută `build_hybrid_index.py` cu următoarele argumente:
  - **1.6.1.** `--source data/documents`.
  - **1.6.2.** `--batch-size 64` sau valoarea furnizată de utilizator.
  - Argumentul `--model` nu este transmis, deci se folosește valoarea implicită `intfloat/multilingual-e5-small`.
- **1.7.** Returnează codul de ieșire primit de la scriptul Python.

Conexiunea Postgres vine din `.env` (`DATABASE_URL`), citită de `medicina_naturista.config.settings` — nu e un argument al scriptului.

### 2. Pregătirea — `build_hybrid_index.py`

- **2.1.** Convertește directorul sursă într-o cale absolută și verifică existența lui.
- **2.2.** Creează extensiile, tabelele și indecșii Postgres dacă nu există deja (`ensure_schema()` din `ai/db.py` — extensiile `vector` și `unaccent`, tabelele `documents`, `chunks`, `sync_metadata`), printr-o conexiune separată, înainte de deschiderea pool-ului de conexiuni.
- **2.3.** Creează directorul cache al modelului (`data/model_cache`, configurabil prin `MODEL_CACHE_DIR`) dacă lipsește.
- **2.4.** Găsește recursiv toate fișierele cu extensia `.md` și le sortează determinist după calea relativă (fără diferență între majuscule și minuscule).
- **2.5.** Oprește procesul dacă nu este găsit niciun fișier Markdown.
- **2.6.** Interoghează `documents` pentru harta `cale_relativă → sha256` deja sincronizată și citește `text_repr_version` din `sync_metadata`.
- **2.7.** Dacă versiunea stocată diferă de `TEXT_REPR_VERSION` (în prezent `"4"`, mărită la fiecare schimbare a regulilor de fragmentare/curățare a textului), harta de la 2.6 este golită: toate documentele vor fi re-procesate, deși niciunul nu s-a schimbat pe disc. La o bază existentă se afișează „Text representation changed (… -> …); forcing a full resync”.
- **2.8.** Încarcă dicționarul de afecțiuni din `data/medical_conditions.txt` (configurabil prin `CONDITIONS_FILE`); un fișier lipsă produce un dicționar gol, nu o eroare.

### 3. Decizia „sar peste” vs. „re-procesez”, per fișier

- **3.1.** Pentru fiecare fișier, determină categoria documentului (`category_id`) = folderul care îl conține, relativ la sursă (gol pentru fișierele din rădăcină).
- **3.2.** Calculează SHA-256 direct din bytes, citind fișierul în blocuri de 1 MB (fără a decodifica sau fragmenta conținutul).
- **3.3.** Dacă acest SHA-256 este identic cu cel deja stocat pentru aceeași cale relativă → fișierul este **sărit complet**: nu este citit, fragmentat sau trimis către modelul de embeddings, și nu se face niciun apel către baza de date pentru el.
- **3.4.** Altfel, fișierul intră în lista „de procesat”: i se reține dimensiunea și data modificării (pentru verificarea de la 5.10), se citește, se fragmentează (secțiunea 4) și fragmentele sale se adaugă la lotul care va fi trimis modelului de embeddings (secțiunea 5).

Acesta este mecanismul de sincronizare incrementală: adăugarea sau modificarea unui singur document nu regenerează embeddings pentru restul corpusului.

### 4. Citirea și împărțirea fiecărui document „de procesat” în fragmente

- **4.1.** Citește conținutul brut al fișierului.
- **4.2.** Încearcă succesiv decodificarea `UTF-8 BOM`, `UTF-8`, `UTF-16`, `CP1250` și `CP1252`; dacă toate eșuează, decodifică `UTF-8` cu caractere de înlocuire și adaugă un avertisment.
- **4.3.** Recalculează SHA-256 din bytes-urile citite; dacă diferă de cel de la 3.2, oprește sincronizarea (fișierul s-a schimbat în timpul rulării).
- **4.4.** Normalizează sfârșiturile de linie și elimină caracterele NUL. Sursele trebuie să fie deja curate (`scripts/clean_documents.py`); aici nu se mai elimină linkuri sau trimiteri.
- **4.5.** Normalizează Unicode la NFC, păstrând diacriticele românești.
- **4.6.** Creează metadatele `SourceFile`: cale relativă și absolută, dimensiune, data modificării (UTC), SHA-256, codificare, număr de linii, număr de caractere și categoria documentului.
- **4.7.** Împarte documentul în fragmente cu `fragment_document()` (`ai/fragmenter.py`). Fiecare fragment primește o categorie de business (`business_category`: `R1`, `R2` sau `D1`) și, pentru R1 și R2, afecțiunile din dicționar despre care este vorba. Un capitol este un titlu Markdown (`#` … `######`); marcajele de pagină (`Pagina N`, `Pagina N din M`, `Page N`) nu sunt titluri. **Numele fișierului și folderele nu se compară cu afecțiunile**; nu există fragment „document întreg”. Pașii 4.9–4.12 se aplică în ordine.
- **4.8.** **Potrivirea afecțiunilor** (`ConditionDictionary.find()` din `ai/conditions.py`): fiecare rând din dicționar este o afecțiune — denumirea canonică urmată de sinonime, separate prin virgulă; o afecțiune se potrivește prin oricare dintre ele (SAU). Termenii se caută pe cuvinte întregi, fără diacritice și fără diferență între majuscule și minuscule, indiferent de lungimea termenului (nu există prag minim). Terminațiile românești uzuale (`-ului`, `-ilor`, `-elor`, `-ile`, `-ele`, `-ei`, `-ii`, `-ul`, `-a`, `-e`, `-i`) sunt ignorate la cuvintele de cel puțin 4 litere, dacă rămân cel puțin 3 (`gripa`/`gripei`/`gripe`). La aceeași poziție câștigă termenul cu cele mai multe cuvinte (`adenom colonic` ascunde `adenom`), iar cuvintele potrivite nu mai sunt scanate din nou. Se rețin denumirile canonice, fără duplicate, în ordinea apariției.
- **4.9.** **R1 — titlul capitolului conține o afecțiune.** Titlurile sunt parcurse de jos în sus (cele mai adânci primele), deci un subcapitol cu afecțiune în titlu este mereu fragment separat, iar părintele păstrează doar ce a rămas din subarborele lui. Fragmentul începe cu propriul titlu, fără titlurile strămoșilor. Liniile subarborelui sunt marcate ca luate și excluse din pașii următori chiar dacă titlul a rămas fără text și deci nu produce fragment.
- **4.10.** **R2 — textul propriu al capitolului menționează o afecțiune.** Între titlurile rămase, cele al căror text propriu (până la următorul titlu de orice nivel) conține o afecțiune devin fragmente formate din propriul titlu și acel text, fără titlurile strămoșilor; mai multe afecțiuni în aceeași secțiune dau un singur fragment. Liniile luate sunt excluse din pasul următor.
- **4.11.** **Afecțiunile fragmentelor R1 și R2.** `primary_medical_conditions` = afecțiunile din propriul titlu (la R2 este mereu gol, altfel fragmentul ar fi R1). `secondary_medical_conditions` = afecțiunile din textul fragmentului, fără linia titlului. Cele două liste se pot suprapune.
- **4.12.** **D1 — restul textului.** Fiecare porțiune continuă de linii rămase (inclusiv textul de sub niciun titlu și documentele fără titluri) care conține text real este tăiată în bucăți. O porțiune de cel mult 2100 de caractere rămâne o singură bucată; altfel tăietura se face la ~1800 de caractere (`D1_TARGET_CHARS`), la limita cea mai apropiată de țintă din intervalul 1500–2100 (`D1_MIN_CHARS`–`D1_MAX_CHARS`), preferând sfârșit de paragraf, apoi de propoziție, apoi de rând, apoi spațiu (fără niciuna, tăietură fixă). Tăietura nu lasă mai puțin de 300 de caractere pentru restul (`D1_MIN_TAIL_CHARS`). Bucata următoare începe la primul început de propoziție (altfel de rând, altfel de cuvânt) din ultimele cel mult 270 de caractere ale bucății anterioare (`D1_MAX_OVERLAP_CHARS`). O bucată nu trece peste un fragment R1/R2, pentru că porțiunile se opresc la liniile luate. O porțiune formată doar din titluri, marcaje de pagină și linii albe nu produce fragment. Fragmentele D1 nu au afecțiuni.
- **4.13.** Fragmentele R1 și R2 nu au limită de lungime. Liniile albe de la începutul și sfârșitul fiecărui fragment sunt eliminate.
- **4.14.** `heading` = lanțul de titluri până la titlul propriu al fragmentului (`Carte > Plante > Mușețel`); pentru D1, lanțul ultimului titlu aflat înainte de prima linie a bucății, sau gol. Este doar metadată (afișare, contextul embedding-ului, indexul lexical, contextul raportului); nu intră în textul fragmentului și nu este folosit la determinarea afecțiunilor.
- **4.15.** Marcajele de pagină sunt scoase din textul fragmentelor și nu apar în `heading`.
- **4.16.** Fragmentele sunt ordonate după poziția din document (prima, apoi ultima linie).
- **4.17.** Creează câte un obiect `Chunk` pentru fiecare fragment, cu calea relativă și absolută a sursei, SHA-256 al sursei, intervalul de linii (primul și ultimul rând al fragmentului), `heading`, textul, SHA-256 al textului, numărul de caractere, categoria documentului, `business_category`, `primary_medical_conditions` și `secondary_medical_conditions` — fără un id sau o poziție în matrice: rândul din `chunks` este alocat de Postgres (`BIGSERIAL`) la inserare.
- **4.18.** Un document fără text indexabil produce doar un avertisment („No indexable text”); rândul lui din `documents` este totuși scris la pasul 6.
- **4.19.** Afișează progresul scanării („Scanned N/total files; X changed, Y unchanged”) când numărul de ordine al fișierului este multiplu de 50 sau este ultimul, indiferent dacă fișierul este procesat sau sărit.

### 5. Generarea embedding-urilor

Rulează o singură dată, peste **toate** fragmentele tuturor documentelor „de procesat” adunate la pasul 3 — nu per document — pentru eficiență la loturi (`batch_size`). Dacă nu există niciun fragment nou, acest pas este sărit complet: modelul nici măcar nu este încărcat.

- **5.1.** Încarcă modelul FastEmbed/ONNX (implicit `intfloat/multilingual-e5-small`) din `data/model_cache`, descărcându-l de pe Hugging Face doar dacă lipsește din cache. Dacă FastEmbed nu îl cunoaște, îl înregistrează ca model propriu (`onnx/model.onnx`, pooling mediu, normalizat, 384 de dimensiuni). Numărul de fire vine din `EMBEDDING_THREADS` (implicit 8, cel mult numărul de nuclee).
- **5.2.** Construiește fiecare intrare E5 din: prefixul `passage:`, categoria documentului (folderele separate prin ` > `, omisă la rădăcină), numele fișierului-sursă fără extensie, `heading` (când există) — câte unul pe linie — urmate de textul fragmentului.
- **5.3.** Un fragment mai lung de `MAX_CHARS=1400` este împărțit în ferestre de 1400 de caractere care se suprapun cu `OVERLAP_CHARS=240`; fiecare fereastră primește același context de la 5.2. Toate ferestrele tuturor fragmentelor sunt trimise modelului în loturi de 64 sau cu dimensiunea solicitată.
- **5.4.** Raportează la cel puțin 10 secunde distanță ferestrele procesate, procentul, timpul scurs, viteza (ferestre/s) și timpul estimat rămas; la final afișează totalul de fragmente și ferestre.
- **5.5.** Verifică dacă matricea ferestrelor are forma `(număr_ferestre, 384)`.
- **5.6.** Verifică dacă toți vectorii ferestrelor conțin valori finite și dacă niciunul nu este vector nul.
- **5.7.** Normalizează L2 fiecare vector de fereastră.
- **5.8.** Vectorul unui fragment = suma vectorilor ferestrelor lui, verificată (finită, nenulă) și normalizată L2 din nou.
- **5.9.** Rezultă câte un vector cu 384 de dimensiuni pentru fiecare fragment.
- **5.10.** După finalizare, verifică din nou dimensiunea și data ultimei modificări a fiecărui fișier „de procesat”; oprește sincronizarea dacă vreunul s-a schimbat în timpul embedding-ului (nimic nu a fost încă scris în baza de date).

### 6. Scrierea fiecărui document „de procesat” — o tranzacție per document

Pentru fiecare document din lista „de procesat” (secțiunea 3), cu o conexiune luată din pool doar pentru el (commit la final, rollback la eroare):

- **6.1.** Șterge din `chunks` toate fragmentele vechi ale acelui `source_relative_path`.
- **6.2.** Face `INSERT ... ON CONFLICT (relative_path) DO UPDATE` în `documents` cu metadatele noi (cale absolută, dimensiune, dată, SHA-256, codificare, număr de linii și de caractere). `category_id` nu este scris: este o coloană generată de Postgres din cale.
- **6.3.** Inserează fragmentele noi în `chunks`, fiecare cu metadatele de la 4.17, `business_category`, `primary_medical_conditions`, `secondary_medical_conditions`, vectorul lui semantic (`embedding`) și coloana lexicală `text_search` calculată la inserare (`to_tsvector('simple', unaccent(text || ' ' || heading || ' ' || cale))`, echivalentul indexării pe cele trei coloane pe care FTS5 o făcea înainte). Și aici `category_id` este coloană generată.

Niciun cititor nu vede vreodată un document cu doar o parte din fragmentele lui noi scrise, iar eșecul scrierii unui document nu afectează documentele deja scrise cu succes în aceeași rulare.

### 7. Documente eliminate din sursă

- **7.1.** Orice cale relativă prezentă în `documents` (citită la 2.6, înainte de eventuala golire de la 2.7) dar absentă din listarea curentă a `data/documents` este ștearsă din `documents` (`DELETE ... WHERE relative_path = ANY(...)`).
- **7.2.** Ștergerea cascadează automat la `chunks`, prin cheia străină `ON DELETE CASCADE`.

### 8. Metadate și rezumat

- **8.1.** Scrie în `sync_metadata` numele modelului, dimensiunea vectorilor, data/ora ultimei sincronizări și `text_repr_version`.
- **8.2.** Afișează un rezumat JSON: `status`, numărul de fișiere scanate, nemodificate, sincronizate și eliminate, numărul de fragmente scrise și numărul de avertismente.
- **8.3.** Returnează codul de ieșire `0` către `rebuild_index.ps1` atunci când sincronizarea reușește.
- **8.4.** În caz de eroare, afișează `ERROR: <tip>: <mesaj>` pe stderr, apoi propagă excepția (traceback Python și cod de ieșire diferit de zero).

---

Indexul este consumat la rulare de `src/medicina_naturista/ai/search.py` (`rank()`) și `ai/retrieval.py`; vezi [fluxul de generare a raportului final](final-report-generation.md) și [căutarea, unirea și scoringul fragmentelor](fragment-search-and-scoring.md).
