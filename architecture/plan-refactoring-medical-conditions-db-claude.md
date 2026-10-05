# Plan de refactoring — dicționarul de afecțiuni în Postgres, prin migrări versionate

**Scop:**

1. Fișierul `data/medical_conditions.txt` dispare ca fișier citit de aplicație. Afecțiunile și sinonimele lor stau în Postgres.
2. Schema bazei de date și datele dicționarului sunt create și modificate **numai prin migrări versionate** (Alembic), rulate automat la pornire. Nu se mai creează tabele din cod (`ensure_schema()`) și nu se mai scriu date de referință de mână.

**Ce nu se schimbă:**

- **Indexarea (sincronizarea și reindexarea completă) rămâne exact ca azi:** se pornește manual, de pe host, cu `python src/scripts/build_hybrid_index.py` (sau `.venv-gpu\Scripts\python` pentru GPU), cu aceleași argumente, aceeași ieșire în consolă și aceleași declanșatoare de reindexare completă (`TEXT_REPR_VERSION` schimbat, model de embedding schimbat). **Nu există API de indexare**, nici tabelă de joburi, nici endpoint-uri de admin.
- Regulile de fragmentare R1/R2/D1, potrivirea afecțiunilor (`ConditionDictionary.find()` / `resolve()`), formula de scor `8·P1 + 4·P2 + 2·L + V` și coloanele `primary_medical_conditions` / `secondary_medical_conditions` din `chunks`.
- Dacă dicționarul din DB este identic cu fișierul, fragmentele sunt identice, deci **migrarea nu cere reindexare**.

Documentul are două părți: **[Partea I — Rezumat](#partea-i--rezumat)** și **[Partea II — Detalii](#partea-ii--detalii)**.

----------------------------------------------------------------------------------------------------

## Partea I — Rezumat

**Azi:**

```text
ai/db.py: SCHEMA_SQL + ensure_schema()  ──► tabele create din cod, la prima conexiune
data/medical_conditions.txt ──(cache pe mtime)──► load_dictionary() ──► fragmenter / căutare / PDF
python src/scripts/build_hybrid_index.py ──► Postgres
```

**După refactoring:**

```text
migrations/ (Alembic, versionat în git)
  0001_extensions          extensiile vector și unaccent
  0002_documents           tabela documents (cu category_id generat)
  0003_chunks              tabela chunks + toți indecșii ei (GIN, B-tree)
  0004_sync_metadata       tabela sync_metadata
  0005_medical_conditions  tabelele dicționarului + revizia
  0006_seed_conditions     încarcă migrations/data/0006_medical_conditions.csv
  00NN_...                 orice modificare ulterioară de schemă sau de dicționar = o migrare nouă
        │
        ▼  alembic upgrade head pe o bază goală = toată baza, de la zero
           (la pornirea containerului, în teste, local)
Postgres ──(cache pe revizie)──► load_dictionary() ──► aceiași consumatori
python src/scripts/build_hybrid_index.py ──► Postgres          (neschimbat; doar verifică schema în loc s-o creeze)
```

**Fazele:**

| # | Fază | Rezultat |
|---|---|---|
| 0 | Linia de bază | Instantanee ale comportamentului actual, ca să dovedim echivalența |
| 1 | Introducerea Alembic și schema completă | `migrations/` + `0001`–`0004`: extensiile, `documents`, `chunks`, `sync_metadata`, cu toți indecșii; `ensure_schema()` dispare |
| 2 | Schema dicționarului | `0005_medical_conditions`: tabele, constrângeri, trigger de revizie |
| 3 | Datele dicționarului | `0006_seed_conditions`: încărcarea celor 5468 de afecțiuni dintr-un CSV imuabil al migrării |
| 4 | Citirea din DB | `load_dictionary()` citește din Postgres; consumatorii nu se schimbă |
| 5 | Adaptarea minimă a scriptului de indexare | `build_hybrid_index.py` nu mai creează schema; restul comportamentului rămâne identic |
| 6 | Curățenia | Ștergerea fișierului, a `CONDITIONS_FILE`, a scripturilor `conditions_work/`; documentația |

Fiecare fază e un commit (sau PR) separat; aplicația funcționează după fiecare.

----------------------------------------------------------------------------------------------------

## Partea II — Detalii

### Inventarul dependențelor actuale

| Loc | Cum folosește fișierul sau schema | Ce devine |
|---|---|---|
| `src/backend/ai/db.py` | `SCHEMA_SQL` + `ensure_schema()` creează tabelele la prima conexiune; `ensure_schema(dimension)` recreează coloana `embedding` la schimbarea lățimii modelului | Schema trece în migrările `0001`–`0004`; `SCHEMA_SQL` și `ensure_schema()` se șterg; logica de lățime rămâne, separat, pentru script (faza 1, 5) |
| `src/scripts/build_hybrid_index.py:307`, `src/tests/support/postgres.py:38`, `src/tests/unit/ai/test_build_hybrid_index.py:396,482,525` | apelează `ensure_schema()` | Scriptul: verificare de schemă + `ensure_embedding_dimension()` (faza 5); testele: `alembic upgrade head` (faza 1) |
| `src/backend/config.py:83` | `conditions_file` (`CONDITIONS_FILE`) | Se șterge (faza 6) |
| `src/backend/ai/conditions.py` | `parse_conditions()`, cache pe `mtime`, `load_dictionary()` | Încărcare din DB, cache pe revizie (faza 4) |
| `ai/fragmenter.py`, `ai/search.py`, `web/main.py`, `reporting/pdf.py`, `src/scripts/fragment_report.py`, `src/scripts/evaluate_retrieval.py` | `load_dictionary()` / `resolve_query()` / `find_conditions()` | Neschimbat |
| `src/scripts/audit_conditions.py`, `src/scripts/audit_near_dupes.py`, `src/scripts/conditions_work/*` | citesc / rescriu fișierul | Se șterg (rămân în istoria git) |
| `src/tests/unit/ai/test_conditions.py` | `parse_conditions(SAMPLE)`; testele „shipped dictionary” citesc fișierul | Rescrise (fazele 3–4) |
| `Dockerfile:30` | `COPY data/medical_conditions.txt` | Se înlocuiește cu `COPY migrations` + `alembic.ini` |
| `README.md`, `architecture/hybrid-index-generation.md`, `architecture/fragment-search-and-scoring.md` | descriu fișierul, `CONDITIONS_FILE`, `ensure_schema()` | Actualizate (faza 6) |

### Decizii de design

- **D1. Unealta de migrare: Alembic.** Proiectul este Python, iar Alembic rulează în același mediu (`.venv`, imaginea Docker), fără JVM. Migrările se scriu cu SQL explicit (`op.execute(...)`), fără modele SQLAlchemy ORM: codul rămâne pe `psycopg`, ca acum. Alembic ține versiunea aplicată în `alembic_version` și face `upgrade` / `downgrade` ordonat. *Alternativa echivalentă* este Liquibase (changeset-uri SQL/YAML, `loadData` din CSV), rulată ca imagine Docker separată (`liquibase/liquibase`) în `docker-compose`; e potrivită dacă vrei unealta folosită în proiectele Java. Restul planului e același cu oricare dintre ele.
- **D2. Migrările sunt singura sursă a schemei și a datelor de referință.** Nicio tabelă nu mai este creată din cod. Orice schimbare a dicționarului (afecțiune nouă, sinonim nou, redenumire, ștergere) este o **migrare nouă**, revizuită și versionată în git. Asta înlocuiește istoricul pe care îl avea fișierul în git și face ca orice bază (locală, producție, teste) să ajungă în aceeași stare cu `alembic upgrade head`. **Singura excepție, păstrată intenționat ca azi:** scriptul de indexare recreează coloana `chunks.embedding` când modelul ales are altă lățime de vector (D9).
- **D3. O migrare aplicată nu se mai modifică.** CSV-ul din `0006` este imuabil după aplicare. O corectură înseamnă o migrare nouă, nu editarea celei vechi — altfel bazele deja migrate ar diverge de cele noi.
- **D4. Coloanele din `chunks` rămân cu nume canonice (`TEXT[]`).** Căutarea compară deja nume (`primary_medical_conditions && %(conditions)s::text[]`), indecșii GIN rămân valabili, iar `retrieval.py`, `handlers.py` și frontend-ul nu se schimbă. Consecință (aceeași ca azi): o redenumire sau ștergere de afecțiune cere re-fragmentarea documentelor, care se face ca azi — reindexare completă prin scriptul de indexare (de exemplu prin creșterea `TEXT_REPR_VERSION`).
- **D5. Ordinea afecțiunilor se păstrează prin `condition_id`.** Seed-ul inserează în ordinea din fișier; dicționarul se încarcă `ORDER BY condition_id`. Ordinea contează doar la egalități (`_pick()`), dar așa rezultatul după migrare e identic.
- **D6. Unicitatea termenilor e garantată de DB.** Fiecare termen are cheia normalizată `term_key` cu `UNIQUE`; invariantul „niciun termen la două afecțiuni”, verificat azi de `test_shipped_dictionary_has_no_shared_terms`, devine constrângere. O migrare care l-ar încălca eșuează și se anulează integral (Postgres rulează DDL și DML tranzacțional).
- **D7. Revizia dicționarului.** Un trigger crește `sync_metadata.conditions_revision` la orice scriere în tabelele dicționarului (deci și la fiecare migrare de date). `load_dictionary()` reconstruiește dicționarul doar când revizia s-a schimbat.
- **D8. Scriptul reține revizia folosită** (`indexed_conditions_revision`, scrisă în `sync_metadata` odată cu celelalte chei de la final). La pornire, dacă diferă de `conditions_revision`, scriptul doar **afișează un avertisment** („dicționarul s-a schimbat de la ultima sincronizare; fragmentele existente pot avea afecțiunile vechi”). Nu forțează nimic: reindexarea completă rămâne decizia ta, declanșată ca azi.
- **D9. Lățimea vectorului rămâne gestionată de script.** Comportamentul de azi din `ensure_schema(dimension)` (coloană de altă lățime → `DELETE` din `documents` / `sync_metadata`, recrearea coloanei `embedding`, într-o tranzacție) se păstrează neschimbat, mutat într-o funcție dedicată `ensure_embedding_dimension(width)` din `ai/db.py`, apelată **doar** de script. Aplicația web nu o apelează niciodată.
- **D10. Nu există API de scriere sau de indexare.** Scrierile în dicționar trec doar prin migrări (D2); indexarea trece doar prin script.

### Faza 0 — Linia de bază

- **0.1.** Instantaneu al dicționarului: `[(name, terms)]` din `parse_conditions()` pe fișierul actual → `tmp/conditions-baseline.json`.
- **0.2.** Instantaneu al fragmentării: `src/scripts/fragment_report.py` pe tot corpusul → `tmp/fragments-baseline.*`.
- **0.3.** Evaluarea căutării: `src/scripts/evaluate_retrieval.py` → `tmp/eval-before-db.json`.
- **0.4.** Suita de teste trece pe `main`.

### Faza 1 — Introducerea Alembic și crearea întregii scheme

Scop: pe o bază **goală**, `alembic upgrade head` creează toată structura de care are nevoie aplicația — extensiile, `documents`, `chunks`, `sync_metadata`, toți indecșii — fără niciun cod de creare în aplicație. Baza de date propriu-zisă și rolul ei rămân create de containerul `pgvector/pgvector:pg16` din `POSTGRES_DB` / `POSTGRES_USER` (rolul este proprietarul bazei și superuser în imagine, deci poate crea extensiile); tot ce e **în** bază vine din migrări.

- **1.1.** Dependență nouă `alembic` (în `pyproject.toml`, `requirements-lock.txt`, `requirements-web.txt`). `sqlalchemy` vine ca dependență a lui Alembic, folosit doar pentru conexiunea de migrare (driver `postgresql+psycopg`).
- **1.2.** Structura:

  ```text
  alembic.ini                      # script_location = migrations
  migrations/
    env.py                         # URL-ul din settings.database_url (nu din alembic.ini), mod online
    script.py.mako
    versions/
      0001_extensions.py
      0002_documents.py
      0003_chunks.py
      0004_sync_metadata.py
      0005_medical_conditions.py
      0006_seed_conditions.py
    data/                          # fișierele de date ale migrărilor, imuabile
      0006_medical_conditions.csv
  ```

  Revizii cu id-uri lizibile și ordonate (`--rev-id 0001`), nu hash-uri aleatoare. O migrare per obiect logic, ca istoria să fie ușor de citit și fiecare `downgrade()` să fie simplu.

- **1.3.** `0001_extensions`

  ```sql
  CREATE EXTENSION IF NOT EXISTS vector;     -- pgvector: tipul vector(N) pentru embeddings
  CREATE EXTENSION IF NOT EXISTS unaccent;   -- folosit la calculul chunks.text_search
  ```

  `downgrade()`: `DROP EXTENSION unaccent; DROP EXTENSION vector;`

- **1.4.** `0002_documents` — un rând per fișier Markdown sincronizat.

  ```sql
  CREATE TABLE documents (
      relative_path   TEXT PRIMARY KEY,
      absolute_path   TEXT NOT NULL,
      size_bytes      BIGINT NOT NULL,
      modified_utc    TIMESTAMPTZ NOT NULL,
      sha256          TEXT NOT NULL,
      encoding        TEXT NOT NULL,
      line_count      INTEGER NOT NULL,
      char_count      INTEGER NOT NULL,
      -- folderul care conține fișierul; generat, ca să nu poată diverge de relative_path
      category_id     TEXT GENERATED ALWAYS AS (
          CASE WHEN relative_path LIKE '%/%'
               THEN regexp_replace(relative_path, '/[^/]*$', '')
               ELSE ''
          END
      ) STORED
  );
  ```

  `downgrade()`: `DROP TABLE documents;`

- **1.5.** `0003_chunks` — un rând per fragment, cu indexul semantic și cel lexical.

  ```sql
  CREATE TABLE chunks (
      chunk_id              BIGSERIAL PRIMARY KEY,
      source_relative_path  TEXT NOT NULL REFERENCES documents(relative_path) ON DELETE CASCADE,
      source_absolute_path  TEXT NOT NULL,
      source_sha256         TEXT NOT NULL,
      line_start            INTEGER NOT NULL,
      line_end              INTEGER NOT NULL,
      heading               TEXT NOT NULL,
      text                  TEXT NOT NULL,
      text_sha256           TEXT NOT NULL,
      char_count            INTEGER NOT NULL,
      category_id           TEXT GENERATED ALWAYS AS (
          CASE WHEN source_relative_path LIKE '%/%'
               THEN regexp_replace(source_relative_path, '/[^/]*$', '')
               ELSE ''
          END
      ) STORED,
      embedding             vector(1024) NOT NULL,   -- lățimea modelului implicit (Qwen3-Embedding-0.6B)
      text_search           tsvector NOT NULL,
      business_category     TEXT CHECK (business_category IN ('R1', 'R2', 'D1')),
      primary_medical_conditions   TEXT[] NOT NULL DEFAULT '{}',
      secondary_medical_conditions TEXT[] NOT NULL DEFAULT '{}'
  );

  CREATE INDEX idx_chunks_source               ON chunks (source_relative_path, line_start);
  CREATE INDEX idx_chunks_category             ON chunks (category_id);
  CREATE INDEX idx_chunks_business_category    ON chunks (business_category);
  CREATE INDEX idx_chunks_text_search          ON chunks USING GIN (text_search);
  CREATE INDEX idx_chunks_primary_conditions   ON chunks USING GIN (primary_medical_conditions);
  CREATE INDEX idx_chunks_secondary_conditions ON chunks USING GIN (secondary_medical_conditions);
  ```

  `downgrade()`: `DROP TABLE chunks;` (indecșii dispar odată cu tabela).

  Diferențe față de `SCHEMA_SQL` de azi, intenționate:
  - instrucțiunile de compatibilitate cu baze vechi (`ALTER TABLE chunks DROP COLUMN IF EXISTS priority / conditions`, `ADD COLUMN IF NOT EXISTS ...`) **nu** intră în migrări: o bază nouă primește direct forma finală, iar bazele existente au fost deja aduse la ea de `ensure_schema()`;
  - `business_category` rămâne nullable, exact ca în producție, ca schema creată de migrări să fie identică cu cea existentă. Trecerea la `NOT NULL` poate veni ulterior, ca migrare separată, după ce o interogare confirmă că nu există rânduri cu `NULL`;
  - lățimea `vector(1024)` este cea a modelului implicit; dacă scriptul este rulat cu alt model, o ajustează singur, ca azi (D9).

- **1.6.** `0004_sync_metadata` — perechi cheie/valoare despre ultima sincronizare (`model_name`, `model_dimension`, `last_synced_utc`, `text_repr_version`) și, din faza 2, `conditions_revision` / `indexed_conditions_revision`.

  ```sql
  CREATE TABLE sync_metadata (
      key   TEXT PRIMARY KEY,
      value TEXT NOT NULL
  );
  ```

  `downgrade()`: `DROP TABLE sync_metadata;`

- **1.7.** **Bazele existente** (locală și producție) au deja aceste obiecte, create de `ensure_schema()`. Pe ele nu se rulează `0001`–`0004`, ci se marchează ca aplicate, după o verificare:
  1. backup (`pg_dump`) al bazei;
  2. se creează o bază goală temporară, se rulează `alembic upgrade 0004` pe ea și se compară schema ei cu cea existentă (`pg_dump --schema-only` pe ambele, sau o interogare pe `information_schema.columns` + `pg_indexes` + `pg_constraint`), ignorând ordinea coloanelor — pe bazele vechi coloanele adăugate prin `ALTER` sunt la sfârșitul tabelei;
  3. dacă nu există diferențe: `alembic stamp 0004`; apoi `alembic upgrade head` rulează normal migrările `0005`+;
  4. dacă există diferențe: o migrare de aliniere scrisă explicit, nu o modificare a migrărilor `0001`–`0004`.

  Pașii se repetă întâi pe o copie `pg_restore` a bazei de producție. Comparația de schemă devine și script (`src/scripts/compare_schema.py`), refolosibil la orice migrare viitoare.
- **1.8.** `ai/db.py`: se șterg `SCHEMA_SQL` și `ensure_schema()`; `get_pool()` doar deschide pool-ul. Dacă schema lipsește sau e la o versiune veche, aplicația nu încearcă s-o repare: la pornire verifică `alembic_version` față de `head` și refuză să pornească cu un mesaj clar. Logica de lățime a vectorului se mută în `ensure_embedding_dimension(width)` (D9).
- **1.9.** Rularea migrărilor:
  - **container:** un `docker-entrypoint.sh` rulează `alembic upgrade head` și apoi `exec uvicorn ...` (o singură instanță, `--workers 1`, deci fără concurență între migrări). `Dockerfile` copiază `alembic.ini` și `migrations/`.
  - **local:** `alembic upgrade head` din `.venv`, menționat în README.
  - **teste:** `src/tests/support/postgres.py` rulează `alembic upgrade head` programatic (`alembic.command.upgrade`) pe containerul efemer, în locul `ensure_schema()`.
- **1.10.** Teste noi:
  - pe o bază goală, `upgrade head` → `downgrade base` → `upgrade head` reușește (migrările sunt reversibile și repetabile);
  - după `upgrade head`, toate tabelele, coloanele generate, constrângerile și indecșii de mai sus există (interogare pe catalog);
  - testele existente de indexare și căutare (`test_build_hybrid_index.py`, `test_search.py`) rulează pe o bază creată exclusiv din migrări.

### Faza 2 — Migrarea `0005_medical_conditions` (schema dicționarului)

```sql
CREATE TABLE medical_conditions (
    condition_id  BIGSERIAL PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE           -- numele canonic, scris în chunks.*_medical_conditions
);

CREATE TABLE medical_condition_terms (
    condition_id  BIGINT NOT NULL REFERENCES medical_conditions(condition_id) ON DELETE CASCADE,
    position      INTEGER NOT NULL,              -- 0 = numele canonic, apoi sinonimele în ordine
    term          TEXT NOT NULL,                 -- scrierea originală
    term_key      TEXT NOT NULL UNIQUE,          -- forma normalizată (fără diacritice, majuscule, punctuație)
    PRIMARY KEY (condition_id, position)
);

CREATE FUNCTION bump_conditions_revision() RETURNS trigger AS $$
BEGIN
    INSERT INTO sync_metadata (key, value) VALUES ('conditions_revision', '1')
    ON CONFLICT (key) DO UPDATE SET value = (sync_metadata.value::bigint + 1)::text;
    RETURN NULL;
END $$ LANGUAGE plpgsql;
-- câte un trigger AFTER INSERT OR UPDATE OR DELETE ... FOR EACH STATEMENT pe fiecare tabelă
```

- **2.1.** `term_key` se calculează în Python, cu aceeași funcție `_normalize()` din `ai/conditions.py`, ca să coincidă exact cu cheile folosite la potrivire. De aceea migrările de date (faza 3 și următoarele) importă funcția din pachet, nu o reimplementează în SQL. Ca să nu depindă o migrare veche de o normalizare schimbată ulterior, `_normalize()` se mută într-un modul mic, stabil (`ai/normalization.py`); orice schimbare a ei vine cu o migrare care recalculează `term_key` (vezi Riscuri).
- **2.2.** `downgrade()` șterge triggerele, funcția și tabelele.
- **2.3.** Teste: un termen cu același `term_key` la două afecțiuni e respins; ștergerea unei afecțiuni îi șterge termenii; orice scriere crește `conditions_revision`.

### Faza 3 — Migrarea `0006_seed_conditions` (datele dicționarului)

- **3.1.** Fișierul de date `migrations/data/0006_medical_conditions.csv`, generat **o singură dată** din `data/medical_conditions.txt` (prin `parse_conditions()`, deci cu aceeași deduplicare din interiorul liniei). Format lung, cu antet, UTF-8:

  ```csv
  condition_order,position,term
  1,0,Abces
  1,1,buboi
  1,2,colectie de puroi
  2,0,Abces abdominal
  ...
  ```

  Formatul lung (un termen pe rând) evită ambiguitatea virgulelor din termeni și dă diff-uri curate în git.
- **3.2.** `upgrade()`: citește CSV-ul, verifică înainte de orice scriere că nu există nume canonice duplicate sau termeni comuni între afecțiuni (mesaj clar cu conflictele), apoi inserează afecțiunile în ordinea `condition_order` și termenii cu `term_key`. Inserarea se face în loturi (`executemany` / `COPY`), nu rând cu rând.
- **3.3.** `downgrade()`: șterge exact afecțiunile introduse de această migrare (după numele din CSV).
- **3.4.** Verificare: dicționarul încărcat din DB (faza 4) produce exact `tmp/conditions-baseline.json`.
- **3.5.** Testele „shipped dictionary” din `test_conditions.py` (fără duplicate, fără termeni comuni, linii complete) devin teste pe CSV-ul de seed și, după `upgrade head`, pe conținutul bazei.

**Cum se modifică dicționarul de aici înainte:** o migrare nouă, de exemplu `0007_add_conditions_respirator.py` cu `migrations/data/0007_add_conditions_respirator.csv` (același format) pentru adăugări, sau cu instrucțiuni explicite pentru redenumiri / sinonime noi / ștergeri, fiecare cu `downgrade()` corespunzător. Un helper comun (`migrations/helpers/conditions.py`: `add_conditions(csv)`, `add_synonyms(name, terms)`, `rename_condition(old, new)`, `remove_conditions(names)`) face validarea și normalizarea identic în toate migrările, ca migrările concrete să rămână scurte. Loturile pe care le generai până acum pentru fișier devin CSV-uri ale unor migrări noi. După o astfel de migrare, dacă vrei ca fragmentele existente să reflecte dicționarul nou, rulezi o reindexare completă ca azi (D4, D8).

### Faza 4 — Citirea dicționarului din DB (`ai/conditions.py`)

Interfața publică rămâne: `Condition`, `ConditionDictionary`, `load_dictionary()`, `find_conditions()`, `resolve_query()`.

- **4.1.** `_fetch_conditions(connection)`: un `SELECT` cu `JOIN`, `ORDER BY c.condition_id, t.position`, grupat în Python.
- **4.2.** `load_dictionary()`: citește `conditions_revision`; aceeași revizie → dicționarul din cache; altfel îl reconstruiește. Cache protejat de `threading.Lock` (aplicația web servește cereri pe mai multe fire).
- **4.3.** Tabelă goală → dicționar gol + `logger.warning("conditions_empty")`. DB indisponibil → ultimul dicționar din cache, altfel gol; fără excepție.
- **4.4.** Teste: potrivirile (`MatchTests`, `resolve`, `remainder`) construiesc dicționarul dintr-o listă de `Condition`, fără text; reîncărcarea pe revizie se testează pe Postgres-ul efemer.
- **4.5.** Verificare: fragmentarea (0.2) și evaluarea (0.3) dau rezultate identice → `TEXT_REPR_VERSION` nu se schimbă, nu e nevoie de reindexare.

### Faza 5 — Adaptarea minimă a scriptului de indexare

`src/scripts/build_hybrid_index.py` rămâne locul și modul în care pornești indexarea; algoritmul, argumentele (`--source`, `--model`), ieșirea în consolă, rezumatul JSON de la final și declanșatoarele de reindexare completă (`TEXT_REPR_VERSION`, schimbarea modelului) **nu se schimbă**. Se schimbă doar trei lucruri:

- **5.1.** În locul `ensure_schema(profile.dimension)`:
  1. verificarea că baza este la `alembic head` (aceeași funcție ca la pornirea aplicației, 1.8); altfel scriptul se oprește cu mesajul „baza nu e migrată — rulează `alembic upgrade head` sau pornește containerul”;
  2. `ensure_embedding_dimension(profile.dimension)` (D9), cu exact comportamentul de azi la schimbarea lățimii.
- **5.2.** Dicționarul vine din DB prin același `load_dictionary()` (faza 4); scriptul nu are cod nou pentru asta.
- **5.3.** `indexed_conditions_revision` se adaugă la cheile scrise în `sync_metadata` la final; la pornire, avertismentul din D8 când revizia diferă.
- **5.4.** Teste (`test_build_hybrid_index.py`): baza de test vine din migrări; testele de schimbare a lățimii (`:482`) rămân, pe `ensure_embedding_dimension()`; testul „`ensure_schema()` fără dimensiune nu atinge indexul” (`:521`) se înlocuiește cu „aplicația web nu modifică niciodată coloana `embedding`”; test nou: bază nemigrată → scriptul se oprește cu mesajul de la 5.1; test nou: avertismentul D8.

### Faza 6 — Curățenia

- **6.1.** Se șterg `data/medical_conditions.txt`, `parse_conditions()` (după ce CSV-ul de seed a fost generat și verificat), `src/scripts/audit_conditions.py`, `src/scripts/audit_near_dupes.py` și `src/scripts/conditions_work/` (rămân în istoria git). Datele trăiesc de acum în `migrations/data/`.
- **6.2.** `config.py`: se șterge `conditions_file`.
- **6.3.** `Dockerfile`: fără `COPY data/medical_conditions.txt`; cu `alembic.ini`, `migrations/` și entrypoint-ul de la 1.9.
- **6.4.** `reporting/pdf.py:522`: comentariul nu mai numește fișierul.
- **6.5.** Documentație:
  - `README.md`: dicționarul e în `medical_conditions` / `medical_condition_terms`, populat de migrări; secțiune nouă „Migrări” (`alembic upgrade head`, cum se adaugă afecțiuni printr-o migrare nouă, că după o migrare de dicționar reindexarea completă se face cu scriptul, ca până acum); `CONDITIONS_FILE` dispare. Secțiunea despre `build_hybrid_index.py` rămâne, cu o singură precizare: baza trebuie să fie migrată înainte.
  - `architecture/hybrid-index-generation.md` — pasul 2 / 2.2 (schema creată de migrări, nu de `ensure_schema()`; scriptul doar o verifică și ajustează lățimea vectorului), 2.8 (dicționarul din DB), pasul 8 (`indexed_conditions_revision`).
  - `architecture/fragment-search-and-scoring.md` — 1.1 (sursa dicționarului, reîncărcarea pe revizie) și tabelul de setări.
- **6.6.** Verificare finală: `grep -r medical_conditions.txt` găsește doar acest plan; suita de teste trece; `alembic upgrade head` pe o bază goală + `python src/scripts/build_hybrid_index.py` reproduc indexul; pe baza existentă, o rulare a scriptului nu raportează niciun fișier schimbat.

### Riscuri și măsuri

| Risc | Măsură |
|---|---|
| Schema creată de migrări diferă de cea a bazei de producție existente | Comparație de schemă înainte de `alembic stamp 0004` (1.7), întâi pe o copie `pg_restore`; diferențele se rezolvă cu o migrare de aliniere, nu editând `0001`–`0004`; backup înainte de deploy |
| O migrare de date eșuată la pornirea containerului | DDL + DML tranzacționale în Postgres → rollback complet; containerul nu pornește, iar versiunea anterioară a imaginii rulează în continuare pe baza neschimbată |
| Scriptul rulat pe o bază încă nemigrată (de pe host, înainte de pornirea containerului nou) | Verificarea `alembic head` din 5.1 oprește scriptul înainte de orice scriere |
| `term_key` depinde de normalizare; o schimbare a ei invalidează cheile | Normalizarea într-un modul stabil (2.1); orice schimbare vine cu o migrare care recalculează `term_key` și verifică noile coliziuni |
| Editarea unei migrări deja aplicate | Regula D3; test care compară checksum-urile CSV-urilor deja livrate |
| Fragmentele rămân cu afecțiunile vechi după o migrare de dicționar | Avertismentul din D8 la următoarea rulare a scriptului; reindexare completă, pornită de tine, ca azi |
| Coloana `embedding` ajustată de script diferă de lățimea din `0003` | Intenționat (D9), exact ca azi; comparația de schemă (1.7) ignoră lățimea vectorului |
| Ordinea afecțiunilor schimbă rezultatele la egalități | Seed în ordinea din fișier + `ORDER BY condition_id`; verificările 3.4 / 4.5 |

### Rularea

Migrările rulează singure la pornirea containerului; local:

```bash
alembic upgrade head
```

Dacă verificarea 4.5 confirmă fragmente identice, migrarea nu cere reindexare. Orice sincronizare sau reindexare completă se pornește manual, de către tine, ca azi:

```bash
python src/scripts/build_hybrid_index.py
```
