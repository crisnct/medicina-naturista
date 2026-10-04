# Plan: dicționarul de afecțiuni în Postgres și crearea fragmentelor printr-un endpoint API

Scop, în două propoziții:

1. `data/medical_conditions.txt` dispare din aplicație; afecțiunile și sinonimele lor ajung în Postgres, iar la runtime nimeni nu mai citește niciun fișier de dicționar.
2. Crearea fragmentelor (ce face azi `scripts/rebuild_index.ps1` pe host, cu `scripts/build_hybrid_index.py`) devine un apel HTTP: `POST /api/index/sync`, urmărit prin `GET /api/index/runs/{run_id}`.

Documentul e împărțit în: constatări în cod (§2), decizii (§3), model de date (§4), seeding (§5), citire (§6), mutarea indexerului (§7), API (§8), curățenie (§9), teste (§10), etape de livrare (§11), riscuri (§12), operare (§13), ce rămâne în afara scopului (§14).

---

## 1. Criterii de acceptare

| # | Criteriu | Cum se dovedește |
|---|---|---|
| A1 | Dicționarul încărcat din Postgres este **identic** cu cel încărcat azi din fișier (aceleași nume canonice, aceleași sinonime, aceeași ordine) | diff gol între `tmp/conditions-baseline.json` și dump-ul din DB |
| A2 | Fragmentele rezultate sunt identice, deci **nu e nevoie de reindexare** la deploy | `scripts/fragment_report.py` rulat înainte/după dă rezultat identic; `TEXT_REPR_VERSION` rămâne `"4"` |
| A3 | `grep -rn "medical_conditions.txt"` nu mai găsește nimic în cod, configurare, Docker, teste sau documentație operațională | căutare în repo (planurile din `architecture/` pot pomeni fișierul istoric) |
| A4 | `POST /api/index/sync` pe o bază cu `documents`/`chunks` goale populează indexul, iar statusul rulează până la `state="done"` cu contoare | test de integrare + rulare manuală |
| A5 | Un al doilea `POST` cât timp primul rulează răspunde `409`; un al doilea sync incremental după primul raportează `files_changed = 0` | teste + rulare manuală |
| A6 | Endpointul nu e accesibil din domeniul public și cere token | regulă în `Caddyfile` + teste `401`/`503` |

---

## 2. Ce există azi în cod (harta dependențelor)

Fapte verificate în arborele curent:

| Loc | Rol acum | Devine |
|---|---|---|
| `data/medical_conditions.txt` (985.313 B, 5468 linii) | 5468 afecțiuni, 39.792 termeni, 0 linii goale/comentate, max 23 termeni/afecțiune, nume canonice unice | șters (E5); sursa devine `conditions.jsonl` (D2, §5) |
| `src/backend/ai/conditions.py` | `parse_conditions()` (:70), `_normalize()` (:65), `_load()` cu `lru_cache` pe `mtime` (:227), `load_dictionary()` (:236), `find_conditions()` (:246), `resolve_query()` (:252) | citește din DB (§6); `_normalize()` se mută în `ai/normalization.py` |
| `src/backend/config.py:52` | `conditions_file` / `CONDITIONS_FILE` | se șterge (E5) |
| Consumatori care nu se schimbă | `ai/fragmenter.py:218`, `ai/search.py:223`, `reporting/pdf.py:899`, `web/main.py:99`, `scripts/fragment_report.py:43`, `scripts/evaluate_retrieval.py:74` | aceleași semnături |
| `scripts/build_hybrid_index.py` | `build()` (:294), `ensure_schema()` (:299), `TEXT_REPR_VERSION="4"` (:44), `embed_chunks()` cu `print()` (:167–231), progres pe scanare (:346), model încărcat la :411 | se mută în `src/backend/indexing/` (E3) |
| `scripts/rebuild_index.ps1` | pornește scriptul Python local, scoate `HF_HUB_OFFLINE` ca să poată descărca modelul | client HTTP subțire (E4); rămâne și un CLI local pentru prima descărcare a modelului |
| `Dockerfile:30` | `COPY data/medical_conditions.txt` | se șterge; `scripts/` **nu** e copiat în imagine, deci indexerul trebuie mutat în `src/` ca să poată rula în container (E3) |
| `src/backend/ai/db.py` | `SCHEMA_SQL` idempotent (`CREATE ... IF NOT EXISTS`) + `ensure_schema()` (:106), apelat de `get_pool()` (:118) | primește cele 3 tabele noi + `bootstrap_database()` (§4, §5) |
| `docker-compose.yaml` | `app`: `read_only`, user `10001`, `mem_limit: 2g`, `HF_HUB_OFFLINE=1`, `data/documents` montat read-only, `data/model_cache` montat citire-scriere, `APP_HOST_PORT` (implicit 8760) → 7860 | + `INDEX_TOKEN`; documentat că modelul trebuie să fie deja în cache |
| `Caddyfile` | doar `reverse_proxy app:7860`, fără reguli de cale | + blocarea `/api/index/*` pe site-ul public (E4) |
| `src/backend/ai/retrieval.py:32-46` | `Retriever` citește `document_count` și `category_tree` **o singură dată**, în `__init__` | + `Retriever.refresh()` apelat după un sync reușit (E4) |
| `src/backend/ai/search.py:235`, `web/main.py:148` | `cached_query_model()` (lru_cache) și `warm_up_search()` la pornire | reutilizate de indexer, ca să nu existe două copii ale modelului în proces (§7) |
| `tests/support/postgres.py:38,51` | `ensure_schema()` la start, `TRUNCATE chunks, documents, sync_metadata` între teste | `bootstrap_database()` + re-seed după truncate (§10) |
| `tests/unit/ai/test_conditions.py:105-174` | `FileLoadingTests` (fișier lipsă, reîncărcare pe `mtime`) + 4 teste „shipped dictionary” care citesc fișierul | rescrise pe DB, respectiv pe resursa `conditions.jsonl` (§10) |
| `README.md` (liniile 29, 86, 89-90, 132-144, 207-233, 285), `architecture/hybrid-index-generation.md` (16, 49-54, 120), `architecture/fragment-search-and-scoring.md` (13, 39, 126) | descriu fișierul, `CONDITIONS_FILE`, `ensure_schema()` și lansarea din PowerShell | actualizate (E5) |
| `scripts/audit_conditions.py`, `scripts/audit_near_dupes.py`, `scripts/conditions_work/` (96 de fișiere) | unelte one-off care citesc/reescriu fișierul | șterse (E5), rămân în istoria git |

---

## 3. Decizii de arhitectură

- **D1. Nu introduc Alembic în acest pas.** Deploymentul e o singură instanță (`--workers 1`), schema se creează deja idempotent în `SCHEMA_SQL`, iar schimbarea de aici e strict aditivă (3 tabele noi + 1 funcție/2 triggere). Versionarea schemei e o decizie separată, care se poate adăuga ulterior peste aceleași tabele. *Amăruntul care contează:* dacă mai târziu se adoptă o unealtă de migrare, tabelele din acest plan intră într-o migrare inițială marcată ca aplicată pe bazele existente.
- **D2. Un singur artefact sursă al dicționarului, în pachet:** `src/backend/ai/resources/conditions.jsonl`, în format JSON Lines, o linie per afecțiune: `{"name": "Abces", "terms": ["Abces", "buboi", ...]}`. Aplicația **nu îl citește niciodată la runtime**; îl folosește doar seeding-ul. Am ales JSONL în loc de CSV pentru că termenii conțin virgule și caractere care ar cere escaping, iar în loc de SQL pentru că un diff de o linie = o afecțiune schimbată, exact ca la fișierul de azi.
- **D3. `name` (numele canonic) este cheia primară** a afecțiunilor, pentru că exact aceste șiruri sunt scrise în `chunks.primary_medical_conditions` / `secondary_medical_conditions`; nu e nevoie de un id surrogate. `sort_order` păstrează ordinea din fișier, pentru că ordinea dicționarului poate influența egalitățile din potrivirea fuzzy (`get_close_matches` / `_pick()`), iar A1/A2 cer rezultate identice bit cu bit.
- **D4. `condition_terms.term_key` este cheie primară**, deci invariantul „un termen aparține unei singure afecțiuni” — azi doar testat (`test_shipped_dictionary_has_no_shared_terms`) — devine constrângere de bază de date: un seed care l-ar încălca eșuează și se anulează integral.
- **D5. Seed idempotent, condus de hash.** `sha256(conditions.jsonl)` se păstrează în `sync_metadata['conditions_source_sha256']`; dacă hash-ul diferă (sau lipsește), dicționarul se rescrie complet într-o singură tranzacție. Restarturile nu produc scrieri, iar o bază nu poate rămâne în urmă față de resursa livrată.
- **D6. Cache invalidat pe revizie.** Un trigger pe cele două tabele incrementează `sync_metadata['conditions_revision']`; `load_dictionary()` citește revizia (o căutare pe cheie primară) și reconstruiește obiectul Python doar când s-a schimbat. Fără cache pe `mtime`, fără TTL, fără reîncărcare la fiecare cerere.
- **D7. Crearea fragmentelor = un job HTTP asincron.** `POST /api/index/sync` creează un rând în `index_runs` și pornește sincronizarea pe un **fir separat în procesul web**; progresul se scrie în rând (cel mult o dată la ~2 s), deci clientul îl citește prin polling. Un singur job activ e garantat de `pg_try_advisory_lock`. Fir, nu subproces, pentru că indexerul poate refolosi modelul de embedding deja încărcat de `warm_up_search()` — important sub `mem_limit: 2g`. *Plan B*, dacă măsurătorile arată că embedding-ul în proces afectează latența căutărilor: `python -m backend.indexing` ca subproces, cu aceleași endpointuri și aceeași tabelă de stare.
- **D8. Endpointurile de indexare sunt de operare, nu de utilizator.** Token bearer `INDEX_TOKEN` comparat cu `hmac.compare_digest`; dacă variabila nu e configurată, răspund `503` cu mesaj explicit (fail-closed, dar diagnosticabil — nu `404` mut). În plus, `Caddyfile` răspunde `404` pe `/api/index/*` pentru domeniul public, deci calea de acces rămâne `127.0.0.1:${APP_HOST_PORT}`.
- **D9. Nu există endpoint de scriere a dicționarului.** Dicționarul se schimbă prin resursă + redeploy/restart, adică printr-o modificare revizuită în git; endpointurile HTTP doar citesc și declanșează indexarea.
- **D10. Polling, nu SSE/WebSocket.** Un sync durează minute-zeci de minute, clientul e un script de operare, iar un endpoint de status simplu e mai ușor de testat și de urmărit din orice unealtă.

---

## 4. Modelul de date

Adăugat în `SCHEMA_SQL` (`ai/db.py`), idempotent, deci se aplică singur la prima conexiune, inclusiv pe bazele existente:

```sql
CREATE TABLE IF NOT EXISTS conditions (
    name       TEXT PRIMARY KEY,          -- numele canonic, exact cel din chunks.*_medical_conditions
    sort_order INTEGER NOT NULL           -- ordinea din resursă (contează la egalitățile fuzzy)
);

CREATE TABLE IF NOT EXISTS condition_terms (
    term_key       TEXT PRIMARY KEY,      -- forma normalizată (fără diacritice/majuscule/punctuație)
    condition_name TEXT NOT NULL REFERENCES conditions(name) ON DELETE CASCADE,
    position       INTEGER NOT NULL,      -- 0 = numele canonic, apoi sinonimele, în ordine
    term           TEXT NOT NULL,         -- scrierea originală
    UNIQUE (condition_name, position)
);
CREATE INDEX IF NOT EXISTS idx_condition_terms_name ON condition_terms(condition_name, position);

CREATE TABLE IF NOT EXISTS index_runs (
    run_id        BIGSERIAL PRIMARY KEY,
    state         TEXT NOT NULL CHECK (state IN ('queued', 'running', 'done', 'error')),
    full_resync   BOOLEAN NOT NULL,
    requested_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_utc   TIMESTAMPTZ,
    heartbeat_utc TIMESTAMPTZ,
    finished_utc  TIMESTAMPTZ,
    phase         TEXT,                   -- 'scan' | 'embed' | 'write' | 'done'
    counters      JSONB NOT NULL DEFAULT '{}'::jsonb,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS idx_index_runs_requested ON index_runs(requested_utc DESC);

CREATE OR REPLACE FUNCTION bump_conditions_revision() RETURNS trigger AS $$
BEGIN
    INSERT INTO sync_metadata (key, value) VALUES ('conditions_revision', '1')
    ON CONFLICT (key) DO UPDATE SET value = (sync_metadata.value::bigint + 1)::text;
    RETURN NULL;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS conditions_revision_conditions ON conditions;
CREATE TRIGGER conditions_revision_conditions
    AFTER INSERT OR UPDATE OR DELETE ON conditions
    FOR EACH STATEMENT EXECUTE FUNCTION bump_conditions_revision();

DROP TRIGGER IF EXISTS conditions_revision_terms ON condition_terms;
CREATE TRIGGER conditions_revision_terms
    AFTER INSERT OR UPDATE OR DELETE ON condition_terms
    FOR EACH STATEMENT EXECUTE FUNCTION bump_conditions_revision();
```

Chei noi în `sync_metadata` (tabel existent, perechi cheie/valoare):

| Cheie | Scrisă de | Semnificație |
|---|---|---|
| `conditions_source_sha256` | seeding | hash-ul resursei deja aplicată |
| `conditions_revision` | trigger | se schimbă la orice scriere în dicționar |
| `indexed_conditions_revision` | indexare | revizia folosită la ultima fragmentare |
| `model_name`, `model_dimension`, `last_synced_utc`, `text_repr_version` | indexare (existente) | neschimbate |

`conditions_revision` vs `indexed_conditions_revision` dau `conditions_stale` în status: dicționarul s-a schimbat, fragmentele încă poartă numele vechi.

---

## 5. Seeding-ul dicționarului

Fișier nou `src/backend/ai/conditions_store.py`:

```python
CONDITIONS_RESOURCE = Path(__file__).resolve().parent / "resources" / "conditions.jsonl"
SEED_LOCK_KEY = 0x636F6E64  # "cond" — advisory lock pentru bootstrap concurent

def read_resource() -> list[tuple[str, tuple[str, ...]]]:
    """[(nume, termeni)] citit din conditions.jsonl, în ordinea din fișier."""

def seed_conditions(force: bool = False) -> bool:
    """Scrie dicționarul în DB dacă hash-ul resursei diferă (sau force=True).
    Într-o singură tranzacție: advisory lock, DELETE din ambele tabele,
    INSERT în loturi, apoi conditions_source_sha256. Returnează True dacă a scris."""
```

Reguli de execuție:

- **E1.** Validare *înainte* de orice scriere: nume canonice duplicate, termeni comuni între afecțiuni, linii fără termeni. Eșecul dă un mesaj cu conflictele concrete și nu modifică baza.
- **E2.** `term_key` se calculează în Python cu funcția mutată în `ai/normalization.py` (`normalize_term()`, fosta `_normalize()`), ca să fie identic cu cheile folosite la potrivire. `conditions.py` și `conditions_store.py` importă din același modul; nicio migrare viitoare nu are voie să reimplementeze normalizarea în SQL.
- **E3.** `INSERT` în loturi (`executemany`), nu rând cu rând; 5468 afecțiuni / 39.792 termeni se scriu în sub o secundă.
- **E4.** `bootstrap_database()` în `ai/db.py` = `ensure_schema()` + `seed_conditions()` (import local al lui `conditions_store`, ca să nu apară ciclu `db → conditions → db`). E apelat o singură dată per proces, lazy, din `get_pool()` și din `lifespan`.
- **E5.** Prima `load_dictionary()` dintr-un proces se asigură că bootstrap-ul a rulat, ca uneltele care încarcă dicționarul direct (`scripts/fragment_report.py`, `scripts/evaluate_retrieval.py`) să nu vadă un dicționar gol.
- **E6.** Generatorul resursei, folosit o singură dată: `scripts/export_conditions_jsonl.py` citește `data/medical_conditions.txt` cu `parse_conditions()`, scrie JSONL ordonat, verifică round-trip-ul (parse(JSONL) == parse(txt)) și iese cu cod diferit de zero la orice diferență. Se șterge în etapa E5, după ce resursa e verificată și fișierul dispare.

---

## 6. Citirea dicționarului din Postgres (`ai/conditions.py`)

Interfața publică rămâne neschimbată: `Condition`, `ConditionDictionary`, `find_conditions()`, `resolve_query()`, `load_dictionary()`.

- **E1.** `_fetch_conditions(connection)` — un `SELECT c.name, c.sort_order, t.position, t.term FROM conditions c JOIN condition_terms t USING (condition_name) ORDER BY c.sort_order, t.position`, grupat în Python în `[Condition(name, terms)]`.
- **E2.** `load_dictionary(conditions: list[Condition] | None = None)`:
  - dacă primește o listă, construiește direct dicționarul (utilitar pentru teste și pentru codul care vrea un dicționar izolat);
  - altfel: bootstrap (o dată per proces) → citește `conditions_revision` → dacă revizia e cea din cache, întoarce obiectul din cache; altfel reconstruiește și actualizează cache-ul sub `threading.Lock` (indexarea rulează pe alt fir).
- **E3.** Moduri de eșec, identice ca spirit cu azi:
  - bază indisponibilă → ultimul dicționar din cache; dacă nu există, dicționar gol + `logger.warning("conditions_unavailable")`, fără excepție (azi: fișier lipsă → dicționar gol);
  - tabele goale → dicționar gol + `logger.warning("conditions_empty")`;
  - succes → `logger.info("conditions_loaded source=db conditions=%s terms=%s revision=%s")`.
- **E4.** Se șterg `parse_conditions()`, `_load()` cu `lru_cache` pe `mtime`, `settings.conditions_file`. `_normalize()` devine `normalization.normalize_term()`, iar `_fold_word()` rămâne în `conditions.py` (doar potrivirea îl folosește).
- **E5. Poarta de echivalență:** `tmp/conditions-baseline.json` (generat în E0) vs dump-ul din DB trebuie să fie identice, altfel etapa nu se închide.

---

## 7. Indexerul devine modul al aplicației

Mutare din `scripts/build_hybrid_index.py` în `src/backend/indexing/` (obligatoriu: imaginea nu copiază `scripts/`):

```text
src/backend/indexing/__init__.py
src/backend/indexing/pipeline.py   # sync_index(), embed_chunks(), _write_document(), TEXT_REPR_VERSION
src/backend/indexing/jobs.py       # pornire job, progres, recuperare după restart
src/backend/indexing/__main__.py   # CLI local (python -m backend.indexing)
```

- **E1.** `build(source, model_name, batch_size)` → `sync_index(source, *, model_name, batch_size, full=False, on_progress=None) -> dict`. `full=True` golește harta `existing` (aceeași cale pe care `TEXT_REPR_VERSION` schimbat o forțează azi) și reindexează tot.
- **E2.** `print()` de progres devine `on_progress(event)` cu date structurate:

  ```python
  {"phase": "scan",  "files_total": 812, "files_scanned": 300, "files_changed": 12, "files_unchanged": 288}
  {"phase": "embed", "windows_done": 540, "windows_total": 2100, "eta_seconds": 340}
  {"phase": "write", "documents_written": 7, "documents_total": 12}
  ```

  `embed_chunks()` primește callback-ul; CLI-ul local pasează un callback care scrie exact liniile de consolă de azi, deci comportamentul din terminal nu se schimbă.
- **E3.** Modelul de embedding: `sync_index()` primește modelul de la apelant, iar apelantul din web folosește `cached_query_model(...)` — aceeași instanță pe care `warm_up_search()` a încărcat-o deja. CLI-ul local păstrează `create_embedding_model()` (cu posibilitatea de descărcare), pentru prima populare a cache-ului.
- **E4.** La începutul rulării se citește `conditions_revision` (instantaneu al dicționarului folosit), la final se scrie `indexed_conditions_revision` — baza pentru `conditions_stale`.
- **E5.** `scripts/build_hybrid_index.py` rămâne o coajă de 5 linii care apelează `backend.indexing.__main__`, ca să nu se rupă obiceiul local; `rebuild_index.ps1` devine client HTTP (E4, §8), cu păstrarea variantei CLI pentru prima descărcare a modelului.
- **E6.** Testele existente din `tests/unit/ai/test_build_hybrid_index.py` își schimbă doar importurile; `builder.TEXT_REPR_VERSION` și restul numelor publice rămân.

---

## 8. API-ul de indexare

Router nou `src/backend/web/index_api.py`, montat în `web/main.py` (care nu are azi niciun router de admin).

| Metodă | Rută | Corp | Răspuns |
|---|---|---|---|
| `POST` | `/api/index/sync` | `{"full": false, "batch_size": 64}` | `202 {"run_id": 12, "state": "queued"}`; `409` dacă există un run `queued`/`running`; `401` token greșit; `503` token neconfigurat |
| `GET` | `/api/index/runs/{run_id}` | — | `200` cu `state`, `phase`, `counters`, `started_utc`, `heartbeat_utc`, `finished_utc`, `error` |
| `GET` | `/api/index/runs?limit=20` | — | ultimele rulări (fără `counters` complet) |
| `GET` | `/api/index/status` | — | documente, fragmente, `model_name`, `last_synced_utc`, `text_repr_version` stocată, `conditions_revision`, `indexed_conditions_revision`, `conditions_stale`, run activ |

- **E1.** Execuție: handler-ul ia `pg_try_advisory_lock`, inserează rândul `queued`, pornește `threading.Thread(daemon=True)` și răspunde imediat. Firul: `state='running'`, `started_utc=now()`, apoi `sync_index()` cu un callback care scrie `phase`, `counters` și `heartbeat_utc` cel mult o dată la 2 secunde; la final `done` + contoare sau `error` + `type: message` (fără traceback în răspuns; traceback-ul în log). Lacătul se eliberează în `finally`.
- **E2.** La pornire (`lifespan`), rândurile rămase `queued`/`running` se marchează `error` cu `error='interrupted by restart'`, înainte de a servi cereri. Scrierea per document e tranzacțională (azi la fel), deci un sync întrerupt se reia incremental fără pierdere.
- **E3.** După un run reușit: `retriever.refresh()` (metodă nouă care recitește `document_count`, `category_tree`, `_known_category_ids`), ca `/api/categories` și mesajul „Caut rapid în cele N documente” să vadă documentele noi fără restart.
- **E4.** `scripts/rebuild_index.ps1`:

  ```powershell
  param([switch]$Full, [int]$BatchSize = 64)
  # citește INDEX_TOKEN din .env, POST /api/index/sync, apoi polling la 3 s pe
  # /api/index/runs/{id} cu afișarea fazei, contoarelor și ETA; exit code != 0 la state='error'
  ```

- **E5.** `Caddyfile`: `handle /api/index/* { respond 404 }` înaintea `reverse_proxy`. `docker-compose.yaml`: `INDEX_TOKEN: ${INDEX_TOKEN:-}`; README primește variabila în tabelul de setări.
- **E6.** Configurare: `settings.index_token()` în `config.py` (citit la cerere, ca `api_key()`), nu în `Settings` (testele pot rula fără el).
- **E7.** *(opțional)* `POST /api/index/documents` cu `{"relative_path": "..."}` — re-fragmentează un singur document (util după editarea unui fișier), prin același `sync_index()` limitat la o cale.
- **E8.** Teste în `tests/unit/web/test_index_api.py`: token lipsă → `503`; token greșit → `401`; primul `POST` → `202` + rând `queued`; al doilea cât rulează → `409`; excepție în pipeline → `state='error'` cu mesaj; rând lăsat `running` → marcat `error` la pornire.

---

## 9. Curățenie

- **E1.** Se șterg: `data/medical_conditions.txt`, `scripts/audit_conditions.py`, `scripts/audit_near_dupes.py`, `scripts/conditions_work/` (96 de fișiere one-off), `scripts/export_conditions_jsonl.py` (după ce resursa e verificată), `Dockerfile:30`.
- **E2.** `config.py`: dispare `conditions_file`; apare `index_token()`. `README.md`: dispare `CONDITIONS_FILE`, apar `INDEX_TOKEN` și secțiunea de reindexare prin API.
- **E3.** `pyproject.toml`: lista `package-data` primește `ai/resources/*.jsonl`, lângă `ai/resources/*.txt` care e deja acolo (resursa dicționarului ajunge astfel în wheel, nu doar în imagine).
- **E4.** `reporting/pdf.py:522`: comentariul nu mai pomenește fișierul.
- **E5.** Documentație: `architecture/hybrid-index-generation.md` (pornirea prin API și jobul, schema din DB în locul fișierului, `index_runs`/`indexed_conditions_revision`), `architecture/fragment-search-and-scoring.md` (sursa dicționarului, reîncărcarea pe revizie, tabelul de setări).
- **E6.** Verificare finală: A1–A6 din §1, plus `grep -rn "medical_conditions"` care nu mai găsește decât planurile din `architecture/`.

---

## 10. Teste

| Test | Ce apără |
|---|---|
| `tests/unit/ai/test_conditions_store.py` (nou, Postgres efemer) | seed din resursă; idempotență (al doilea apel nu scrie, revizia rămâne); `force=True` rescrie; `term_key` duplicat e respins de constrângere; revizia crește la scriere manuală și `load_dictionary()` o vede |
| `tests/unit/ai/test_conditions.py` (rescris) | testele pure de potrivire rămân (construiesc `ConditionDictionary` direct); cele 4 teste „shipped dictionary” validează **resursa JSONL** (nume unice, termeni unici, linii complete) și, după bootstrap, conținutul tabelelor; `FileLoadingTests` (fișier lipsă / `mtime`) dispar |
| `tests/unit/ai/test_conditions_equivalence.py` (nou, temporar) | dicționarul din DB == `tmp/conditions-baseline.json`; se șterge după ce etapa 2 e închisă |
| `tests/unit/ai/test_build_hybrid_index.py` (adaptat) | importuri din `backend.indexing`; `full=True` forțează reindexarea; `TEXT_REPR_VERSION` schimbat forțează reindexarea (test existent) |
| `tests/unit/web/test_index_api.py` (nou) | contractul API din §8/E8 |
| `tests/support/postgres.py` (adaptat) | `bootstrap_database()` la start; `reset()` trunchiază și `conditions`, `condition_terms`, `index_runs`, apoi re-seed (`seed_conditions(force=True)`) ca testele următoare să aibă dicționar |
| `scripts/evaluate_retrieval.py` (rulare manuală, nu test) | A2: aceleași rezultate de ranking înainte/după |

---

## 11. Etape de livrare

Fiecare etapă e un commit care lasă aplicația funcțională; E0 și E2 au porți de echivalență care blochează continuarea.

| Etapă | Conținut | Poartă de ieșire |
|---|---|---|
| **E0. Linie de bază** | dump dicționar → `tmp/conditions-baseline.json`; `scripts/fragment_report.py` → `tmp/fragments-baseline.json`; `scripts/evaluate_retrieval.py` → `tmp/eval-before.json`; suita de teste verde | fișierele există și suita trece |
| **E1. Date în DB** | `ai/normalization.py`; `conditions.jsonl` + `scripts/export_conditions_jsonl.py`; tabelele + triggerul în `SCHEMA_SQL`; `ai/conditions_store.py`; `bootstrap_database()`; teste store | resursa round-trip-ează identic cu `.txt`; seed-ul e idempotent |
| **E2. Citire din DB** | `ai/conditions.py` citește din DB, pe revizie; consumatorii nu se ating | **A1** (diff gol) și **A2** (fragmente identice) |
| **E3. Indexer în pachet** | mutare în `backend/indexing/`; progres pe callback; CLI local; teste adaptate | teste verzi; `python -m backend.indexing` dă aceeași ieșire ca azi |
| **E4. API** | `web/index_api.py`; `index_runs`; `Retriever.refresh()`; `INDEX_TOKEN`; `Caddyfile`; `rebuild_index.ps1` client | **A4, A5, A6**; un sync incremental după primul raportează `files_changed=0` |
| **E5. Curățenie** | ștergerea fișierului și a uneltelor one-off; `config.py`; `Dockerfile`; README + cele două documente de arhitectură | **A3**; `docker compose up` pe o bază existentă pornește fără reindexare |
| **E6.** *(opțional)* | `POST /api/index/documents` (un singur document); reutilizarea embedding-urilor (hash al intrării de embedding, ca un `full` după o schimbare de dicționar să nu re-embeduiască tot) | măsurători înainte de adoptare |

---

## 12. Riscuri și măsuri

| Risc | Măsură |
|---|---|
| Dicționarul din DB diferă de fișier → fragmente diferite, căutări schimbate | A1 (diff pe dump) și A2 (raport de fragmentare identic) sunt porți de etapă, nu verificări finale |
| O bază rămâne cu un dicționar vechi după deploy | seed condus de hash la fiecare pornire (D5); `conditions_source_sha256` arată ce resursă a fost aplicată |
| Normalizarea se schimbă și `term_key` devine inconsistent | `normalize_term()` într-un modul unic; orice schimbare a ei cere re-seed (se face singur, prin hash) și o verificare de coliziuni; test care fixează câteva `term_key` cunoscute |
| Sync în procesul web consumă CPU/memorie și încetinește căutările | model reutilizat (`cached_query_model`), progres + heartbeat, `batch_size` reglabil; măsurare în timpul unui sync mare; plan B: subproces (`python -m backend.indexing`) |
| Modelul de embedding lipsește în container (rulează offline) | `data/model_cache` e bind mount, iar prima descărcare rămâne un pas pe host, prin CLI-ul local (`python -m backend.indexing`); la lipsă, jobul eșuează cu mesaj clar, nu blochează aplicația |
| Restart al containerului în timpul unui sync | scriere per document, tranzacțională → re-rulare incrementală; rândurile `running` se marchează `error` la pornire (E2 din §8) |
| Endpoint accesibil public → reindexare declanșată de oricine | token fail-closed + `respond 404` în Caddy pe `/api/index/*` |
| Fragmente cu afecțiuni vechi după o schimbare de dicționar | `conditions_stale` în `/api/index/status`; reindexare `full` explicită; E6 opțional o face ieftină |
| `index_runs` crește nelimitat | index pe `requested_utc DESC`; curățare oportunistă (păstrează ultimele 100) la pornire sau după fiecare run |

---

## 13. Operare

```bash
# token (o singură dată, în .env)
INDEX_TOKEN=<secret>

# indexare incrementală, prin API (endpointul e blocat pe domeniul public)
curl -X POST http://127.0.0.1:8760/api/index/sync \
  -H "Authorization: Bearer $INDEX_TOKEN" -H "Content-Type: application/json" \
  -d '{"full": false}'
# → {"run_id": 12, "state": "queued"}

curl -H "Authorization: Bearer $INDEX_TOKEN" http://127.0.0.1:8760/api/index/runs/12
curl -H "Authorization: Bearer $INDEX_TOKEN" http://127.0.0.1:8760/api/index/status
```

```powershell
# echivalentul din Windows, folosit zilnic
.\scripts\rebuild_index.ps1            # incremental, cu progres în consolă
.\scripts\rebuild_index.ps1 -Full      # reindexare completă (după o schimbare de dicționar sau de reguli)
```

Modificarea dicționarului: se editează `src/backend/ai/resources/conditions.jsonl` (o linie = o afecțiune), se rulează testele, se face deploy. La pornire, seed-ul vede hash-ul nou, rescrie tabelele și crește revizia; `/api/index/status` raportează `conditions_stale: true` până la un sync (recomandat `full`, pentru că numele canonice scrise în fragmente se pot schimba).

---

## 14. În afara scopului (explicit)

- **Fără unealtă de migrare** (Alembic/Liquibase) în acest pas — vezi D1; se poate adăuga ulterior peste aceleași tabele.
- **Fără API de scriere a dicționarului** (D9) și fără interfață în frontend pentru dicționar.
- **Fără schimbarea regulilor de fragmentare** (R1/R2/D1), a formulei de scor `8·P1 + 4·P2 + 2·L + V` sau a coloanelor din `chunks`; `TEXT_REPR_VERSION` rămâne `"4"`.
- **Fără re-embedding**: A2 trebuie să arate fragmente identice, deci deployul nu cere reindexare; singura reindexare necesară apare dacă dicționarul chiar se schimbă.
