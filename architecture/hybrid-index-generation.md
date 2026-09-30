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
- **4.6.** Împarte documentul în fragmente cu `fragment_document()` (`ai/fragmenter.py`), aplicând pe rând criteriile de mai jos. Fiecare fragment primește lista afecțiunilor din `data/medical_conditions.txt` despre care este vorba. Afecțiunile se caută pe cuvinte întregi, fără diacritice și fără diferență între majuscule și minuscule, cu toleranță la terminațiile românești (`gripa`/`gripei`), indiferent de lungimea termenului (nu există prag minim), iar la aceeași poziție câștigă termenul cel mai lung.
- **4.7.** **Document întreg.** Dacă numele fișierului sau al oricărui folder din cale conține o afecțiune, tot documentul devine un fragment, iar calea (`heading`) este titlul documentului (numele fișierului fără `.md` și fără extensia originală), ca semnalul „titlu" din căutare să vadă numele afecțiunii.
- **4.8.** **Text simplu.** Un document fără titluri Markdown (marcajele `Pagina N` nu contează ca titluri) sau textul rămas nefolosit devine un fragment dacă are cel mult 3000 de caractere. Altfel este tăiat în bucăți de ~3000 de caractere, prelungite până la sfârșitul propoziției care depășește limita (`.`, `!`, `?`, `…`); un text fără punctuație este tăiat la un sfârșit de linie înainte de 4000 de caractere.
- **4.9.** **Titlu.** Într-un document Markdown, primul titlu (parcurgere de sus în jos) care conține o afecțiune ia tot subarborele lui, titlurile mai adânci incluse. Calea (`heading`) este lanțul de titluri până la el, inclusiv (`Carte > Gripa`). Liniile luate astfel nu mai participă la pașii următori.
- **4.10.** **Mențiune.** În liniile rămase, fiecare secțiune al cărei text propriu (până la următorul titlu de orice nivel) menționează o afecțiune devine un fragment format din titlurile tuturor strămoșilor, titlul secțiunii și textul ei. Introducerile strămoșilor nu sunt incluse niciodată. Mai multe afecțiuni în aceeași secțiune dau un singur fragment cu toate afecțiunile în `conditions`.
- **4.11.** **Rest.** Textul secțiunilor rămase, fără nicio afecțiune, este tăiat ca la 4.8, secțiune cu secțiune, cu titlurile strămoșilor în față.
- **4.12.** Orice fragment mai lung de `MAX_FRAGMENT_CHARS=8000` este împărțit la granițe de paragraf, propoziție sau rând; părțile păstrează afecțiunile și calea, iar la fragmentele de secțiune repetă titlurile.
- **4.13.** Marcajele `Pagina N` sunt scoase din text și din cale.
- **4.14.** Creează câte un obiect `Chunk` pentru fiecare fragment, cu calea sursei, suma de control a sursei, intervalul de linii, calea titlurilor (`heading`), textul, numărul de caractere, categoria, `priority` și `conditions` — fără un id sau o poziție în matrice: rândul din `chunks` este alocat de Postgres (`BIGSERIAL`) la inserare.
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
- **6.3.** Inserează fragmentele noi în `chunks`, fiecare cu `conditions`, vectorul lui semantic (`embedding`) și coloana lexicală `text_search` calculată la inserare (`to_tsvector('simple', unaccent(text || heading || cale))`, echivalentul indexării pe cele trei coloane pe care FTS5 o făcea înainte).

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
