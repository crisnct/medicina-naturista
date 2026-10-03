# Plan de migrare: `intfloat/multilingual-e5-small` → `Qwen/Qwen3-Embedding-0.6B`

## 1. Context și starea actuală

Modelul de embedding influențează **doar semnalul V** din scorul de căutare
`8·P1 + 4·P2 + 2·L + V` (`src/medicina_naturista/ai/search.py`). P1, P2 și L nu
depind de model. Consecință practică: câștigul se va vedea în principal la
întrebările **fără o afecțiune recunoscută** și la departajarea fragmentelor cu
același P1/P2/L. Evaluarea trebuie deci raportată separat pe aceste grupe
(vezi §6), altfel o îmbunătățire reală poate fi ascunsă în medie.

Punctele din cod legate de model:

| Loc | Ce e hardcodat azi |
|---|---|
| `ai/embedding_model.py` | `DEFAULT_MODEL`, `MODEL_DIMENSION = 384`, `MODEL_FILE`, înregistrarea ca model custom cu pooling MEAN |
| `scripts/build_hybrid_index.py` | prefixul `passage: `, `MAX_CHARS = 1400` / `OVERLAP_CHARS = 240` (aleși pentru limita de 512 tokeni a e5) |
| `ai/search.py` | prefixul `query: ` la `query_embed` |
| `ai/db.py` | coloana `embedding vector(384)` în `CREATE TABLE IF NOT EXISTS` |
| `sync_metadata` | `model_name`, `model_dimension` — search-ul citește modelul de aici |
| teste | `builder.MODEL_DIMENSION`, `builder.DEFAULT_MODEL` |

Ce e deja bine pentru migrare:
- **FastEmbed 0.8.1 suportă nativ** `Qwen/Qwen3-Embedding-0.6B` (fp32, 2,38 GB, ONNX
  din `Qdrant/Qwen3-Embedding-0.6B-onnx`) și `Qwen/Qwen3-Embedding-0.6B-Q`
  (int8, 1,12 GB). Folosește pooling `LAST_TOKEN` + normalizare. Varianta `-Q`
  cere onnxruntime ≥ 1.23; instalat: 1.30. `create_embedding_model()` nu mai
  trebuie să-l înregistreze ca model custom (ramura `add_custom_model` este
  sărită automat).
- Scorul V este **relativ la căutare** (rescalat din [mediană, max]), deci
  distribuția diferită a cosinusurilor lui Qwen nu cere recalibrarea ponderilor.
- Etichetele de evaluare (`tests/eval/retrieval_queries.json`) sunt pe
  cale/titlu, nu pe `chunk_id`, deci rămân valabile după reindexare.
- Căutarea este o scanare exactă (fără HNSW/IVF), deci nu există index vectorial
  de reconstruit.

## 2. Diferențele tehnice care contează

| | e5-small | Qwen3-Embedding-0.6B |
|---|---|---|
| Parametri | 118M | 596M (~5× mai lent pe token) |
| Dimensiune | 384 | 1024 (MRL: poate fi trunchiat la 512/768 + renormalizare) |
| Context | 512 tokeni | 32k tokeni |
| Pooling | MEAN | LAST_TOKEN (EOS) |
| Prefix query | `query: ` | `Instruct: {sarcină}\nQuery:{întrebare}` |
| Prefix document | `passage: ` | **niciunul** |

**Atenție:** FastEmbed **nu** adaugă singur instrucțiunea Qwen: `query_embed()`
trimite textul neschimbat. Fără instrucțiune la query și fără să scoți
`passage: ` la documente, calitatea scade vizibil. Asta este cea mai probabilă
cauză de „migrare care nu aduce nimic”.

## 3. Decizii de arhitectură

### D1. Profil de model în loc de constante împrăștiate
În `ai/embedding_model.py` se adaugă un profil imutabil, căutat după numele
modelului stocat în `sync_metadata`:

```python
@dataclass(frozen=True)
class EmbeddingProfile:
    name: str
    dimension: int
    query_template: str      # "query: {text}" / "Instruct: ...\nQuery:{text}"
    passage_template: str    # "passage: {text}" / "{text}"
    max_chars: int           # fereastra de embedding
    overlap_chars: int

PROFILES = {
    "intfloat/multilingual-e5-small": EmbeddingProfile(..., 384, "query: {text}", "passage: {text}", 1400, 240),
    "Qwen/Qwen3-Embedding-0.6B":      EmbeddingProfile(..., 1024, QWEN_QUERY, "{text}", 1400, 240),
    "Qwen/Qwen3-Embedding-0.6B-Q":    EmbeddingProfile(..., 1024, QWEN_QUERY, "{text}", 1400, 240),
}
```

- `build_hybrid_index.py` și `search.py` iau prefixele, dimensiunea și ferestrele
  **din profil**, nu din constante. Search-ul ia deja numele modelului din
  `sync_metadata`, deci query-ul folosește automat profilul cu care a fost
  construit indexul. Un index e5 vechi rămâne interogabil corect până la
  reindexare.
- Instrucțiunea Qwen se fixează o singură dată, în engleză (așa a fost antrenat
  modelul; textul query-ului rămâne în română):
  `Instruct: Given a question about natural medicine in Romanian, retrieve passages from herbal and naturopathic texts that answer it\nQuery:{text}`.
  Instrucțiunea face parte din „reprezentarea” query-ului: dacă se schimbă, nu e
  nevoie de reindexare, dar trebuie remăsurată evaluarea.

### D2. Schimbarea modelului forțează resync complet
`TEXT_REPR_VERSION` acoperă deja schimbarea regulilor de text. Se extinde
aceeași logică: dacă `sync_metadata.model_name` ≠ modelul cerut, `build()`
tratează toate documentele ca noi. Fără asta, un `--model` nou ar reembeda doar
fișierele modificate și ar amesteca vectori din două spații diferite (iar cu
dimensiuni diferite, INSERT-ul ar eșua oricum).

### D3. Dimensiunea coloanei: migrare explicită, nu `CREATE IF NOT EXISTS`
`CREATE TABLE IF NOT EXISTS ... vector(384)` nu modifică o tabelă existentă.
`ensure_schema()` primește dimensiunea profilului și, dacă diferă de cea din
catalog (`atttypmod` al coloanei `embedding`), rulează în aceeași tranzacție:

```sql
ALTER TABLE chunks DROP COLUMN embedding;
ALTER TABLE chunks ADD COLUMN embedding vector(1024);
DELETE FROM documents;   -- forțează resync; chunks se șterg prin CASCADE
```

(`NOT NULL` nu poate fi pus pe o coloană nouă într-o tabelă cu rânduri, iar
golirea tabelei e oricum necesară. Se poate adăuga `NOT NULL` după golire, în
același pas.) Operația e distructivă pentru index, dar indexul se poate
reconstrui integral din `data/documents`. De aceea pasul se face doar din
scriptul de build, niciodată din aplicația web.

### D4. Blue/green: indexul nou se construiește într-o bază separată
Pentru o comparație cinstită și rollback instant, indexul Qwen se construiește
într-o **a doua bază Postgres** (de ex. `medicina_qwen` pe același server),
selectată prin `DATABASE_URL`. Baza e5 rămâne neatinsă până la decizie.
Rollback = revenire la vechiul `DATABASE_URL`. Nu e nevoie de cod nou pentru
asta, doar de o variabilă de mediu.

### D5. Precizia și dispozitivul: indexare GPU fp16, întrebări CPU fp32 (DECIS)
Decis pe baza măsurătorilor din §8; varianta `-Q` (int8) este **exclusă**.

| Rol | Dispozitiv și precizie | Motiv |
|---|---|---|
| **Indexare** (build) | GPU, PyTorch fp16, `--batch-size 8` | ~19 ferestre/s, ~17 min pe tot corpusul (vs ~8 ore pe CPU cu `-Q`) |
| **Întrebare** (chat) | CPU, FastEmbed fp32 (`Qwen/Qwen3-Embedding-0.6B`), `EMBEDDING_THREADS` fire | p50 111 ms; `-Q` avea 866 ms, deci int8 e lent pe acest CPU |

- **Consistența vectorilor:** GPU fp16 vs CPU fp32 dau cosinus per text
  **≥ 0,99978** (măsurat), deci indexul făcut pe GPU se interoghează corect cu
  vectori de întrebare calculați pe CPU. Regula „același artefact” din planul
  inițial nu mai e necesară, dar verificarea de cosinus (≥ 0,99) rămâne
  obligatorie ca test de acceptare la orice schimbare de versiune a
  `torch`/`transformers`/`fastembed` (`tmp/gpu_check.py`).
- Profilul de model (D1) are un singur nume de model, `Qwen/Qwen3-Embedding-0.6B`;
  alegerea GPU/CPU nu ține de profil, ci de `EMBEDDING_DEVICE` (D8).

### D6. Dimensiunea 1024 rămâne, deocamdată
Corpusul este mic (387 de fișiere), iar scanarea exactă pe 1024 de dimensiuni
costă câteva ms în plus. Trunchierea MRL la 512 (+ renormalizare) rămâne o
optimizare ulterioară, de făcut doar dacă latența sau spațiul o cer. Nu se
folosește `halfvec` acum.

### D7. Fereastra de embedding: o singură variabilă pe rând
`MAX_CHARS = 1400` exista din cauza limitei de 512 tokeni a e5. Qwen poate citi
fragmente întregi, dar primul build Qwen păstrează **1400/240**, ca diferența
măsurată să vină doar din model. Abia după aceea se testează ferestre mai mari
(de ex. 4000/400 sau „fragment întreg”) ca experiment separat, prin profil.

### D8. Indexare pe GPU: adaptor opțional, mediu separat
- **Adaptor** în `ai/embedding_model.py`: o clasă cu aceeași interfață ca
  `TextEmbedding` pentru ce folosește build-ul (`embed(texts, batch_size, parallel)`,
  care returnează vectori numpy), construită peste `sentence-transformers`
  (`torch_dtype=float16`, `padding_side="left"`). `create_embedding_model()` îl
  alege când `EMBEDDING_DEVICE=cuda`; implicit (`cpu`) rămâne FastEmbed.
  `embed_chunks()` nu se schimbă, pentru că vectorii sunt oricum renormalizați.
- **`torch` se importă leneș**, doar pe ramura `cuda`. Aplicația web, imaginea
  Docker, `pyproject.toml` și `requirements-lock.txt` **nu primesc** `torch`.
- **Mediu separat `.venv-gpu`** (adăugat în `.gitignore`), folosit doar pentru
  build. Conține `torch 2.11.0+cu128`, `sentence-transformers`, `fastembed`.
  Instalare (măsurată pe PC-ul dezvoltatorului):
  1. `python -m venv .venv-gpu`
  2. `pip install torch --no-deps --index-url https://download.pytorch.org/whl/cu128`
     (cu `--index-url` fără `--no-deps` pip încearcă să compileze dependențele
     mărunte din surse)
  3. `pip install --no-cache-dir --only-binary=:all: filelock typing-extensions sympy networkx jinja2 fsspec`
  4. `pip install --no-cache-dir --only-binary=:all: sentence-transformers fastembed`
  5. dependențele build-ului (importate de `scripts/build_hybrid_index.py`; fără ele
     scriptul pică la `import dotenv`):
     `pip install --no-cache-dir --only-binary=:all: numpy python-dotenv "psycopg[binary]" psycopg-pool pgvector`
     și `pip install --no-deps -e .` pentru pachetul `medicina_naturista`
- **Cache-ul modelului în `data/model_cache`**: build-ul setează
  `HF_HUB_CACHE` la `settings.model_cache_dir` înainte de a importa `torch`.
  Pe PC-ul dezvoltatorului, *Controlled folder access* (Windows Defender) blochează
  scrierea Python-ului din venv în `~/.cache` și în cache-ul pip; de aceea
  `--no-cache-dir` la pip și `HF_HUB_CACHE` în proiect. Setarea de securitate nu
  se modifică. `HF_HUB_DISABLE_SYMLINKS_WARNING=1` taie avertismentele de symlink.
- **VRAM:** lotul de 8 ferestre folosește ~1,9 GB, loturile mai mari nu sunt mai
  rapide (17–18/s la 16–32), deci `--batch-size 8` pentru build pe GPU.
- Dacă GPU-ul lipsește sau `torch.cuda.is_available()` e `False`, build-ul **se
  oprește cu o eroare clară**, nu cade tăcut pe CPU (ar fi ~8 ore fără să-și dea
  seama cineva).

### D9. `EMBEDDING_THREADS` rămâne
Se aplică doar căii CPU: embedding-ul întrebărilor în aplicație (și în
containerul de producție, care nu are GPU) și build-ul cu `EMBEDDING_DEVICE=cpu`.
Valoarea implicită rămâne 8, plafonată la numărul de nuclee. La ramura GPU este
ignorată.

## 4. Riscuri

| Risc | Impact | Măsură |
|---|---|---|
| Instrucțiune lipsă / `passage:` rămas | calitate mult mai slabă | D1 + test unitar pe șabloane |
| Tokenizerul nu adaugă EOS (`<\|endoftext\|>`) | pooling LAST_TOKEN greșit, vectori proști | verificare în E1: comparație cu `sentence-transformers` de referință, cosinus ≥ 0,99 |
| FastEmbed trunchiază sub 32k (limită din `tokenizer_config`) | coada textelor lungi ignorată | verificare în E1; ferestrele de 1400 caractere evită oricum problema |
| Latență query pe serverul de producție | răspuns chat mai lent | PC dezvoltator: p50 111 ms (fp32, 8 fire). De remăsurat în containerul Docker (alt CPU, alte nuclee) înainte de comutare |
| RAM în container (fp32 ~2,5–3 GB rezident) | OOM pe un host mic | limită de memorie verificată în `docker-compose.yaml`; **int8 nu e alternativă** (866 ms/întrebare pe CPU) |
| Timp de indexare | ~8 ore pe CPU | rezolvat prin GPU fp16: ~17 min (D5, D8) |
| Build fără GPU (alt PC, CI) | build de ore sau eșec | eroare explicită dacă `EMBEDDING_DEVICE=cuda` și CUDA lipsește (D8); indexul se construiește o dată pe PC-ul cu GPU |
| Deriva GPU fp16 vs CPU fp32 la actualizarea bibliotecilor | vectori din spații ușor diferite | `tmp/gpu_check.py` (cosinus ≥ 0,99) rulat la orice upgrade `torch`/`transformers`/`fastembed` |
| Câștig mascat de P1/P2 | concluzie greșită („nu ajută”) | evaluare pe grupe (§6) |
| Cache Windows → Linux | modelul nu se încarcă în container | `_normalize_fastembed_metadata` acoperă deja; verificat în E3 |

## 5. Pași de implementare

**Stare:** migrarea la Qwen este decisă și codul trecut complet pe Qwen (`DEFAULT_MODEL`,
fără profil e5). Evaluarea pe 120 de întrebări a arătat un câștig la Recall@50 (+5,3) și,
cu ponderea V dublată, la nDCG@10 pe întrebările fără afecțiune (+3,8). Formula scorului a
devenit `4·P1 + 2·P2 + L + V` (echivalentă cu `8·P1 + 4·P2 + 2·L + 2·V`). Indexul oficial
(`medicina`) se reconstruiește cu Qwen din `.venv-gpu`; baza `medicina_qwen` era doar pentru
comparație și se poate șterge.

**Pas 0. Baseline (fără cod nou)**
Rulezi `scripts/evaluate_retrieval.py --output tmp/eval-e5-baseline.json` pe
indexul e5 actual. Fără acest fișier nu avem cu ce compara.

**Pas 1. Spike de validare a modelului (`tmp/`, aruncabil) — FĂCUT pe PC-ul dezvoltatorului**
- E1. Corectitudine: GPU fp16 (`sentence-transformers`) vs FastEmbed fp32 pe CPU,
  8 întrebări cu instrucțiune + 8 ferestre → cosinus min **0,99978**. ✔
  (Rămâne de verificat în E1' că tokenizerul pune EOS pentru pooling pe ultimul token;
  cosinusul ridicat față de referință indică că e corect.)
- E2. int8 vs fp32: **închis**, `-Q` exclus (D5): 866 ms/întrebare și 0,7 ferestre/s pe CPU.
- E3. Latență: `tmp/bench_threads.py` și `tmp/gpu_check.py`. Pe PC: fp32 p50 111 ms
  (p95 135 ms). **Rămâne de făcut în containerul Docker**; țintă orientativă
  p95 < 150–300 ms pe întrebare.

**Pas 2. Refactor fără schimbare de comportament**
- `EmbeddingProfile` + `PROFILES` în `ai/embedding_model.py`; `get_profile(name)`
  aruncă eroare clară pentru un model necunoscut.
- `build_hybrid_index.py`: `_embedding_windows()` și `embed_chunks()` primesc
  profilul (șablon passage, ferestre, dimensiune) în loc de `MAX_CHARS`,
  `OVERLAP_CHARS`, `MODEL_DIMENSION`.
- `search.py`: `profile.query_template.format(text=query)` în loc de `f"query: {query}"`.
- Testele existente trec neschimbate cu profilul e5 → dovada că refactorul nu
  schimbă nimic.

**Pas 3. Suport pentru schimbarea modelului**
- `ensure_schema(dimension)` cu migrarea de dimensiune (D3).
- `build()`: resync complet când `model_name` diferă (D2).
- `--model` documentat în `README.md` și `architecture/hybrid-index-generation.md`.

**Pas 4. Teste noi**
- șabloanele Qwen: query cu instrucțiune, passage fără prefix;
- schimbare de model → toate documentele reembeddate, `sync_metadata` actualizat;
- schimbare de dimensiune → coloana recreată (test pe Postgres-ul din testcontainers);
- `search.rank()` folosește profilul modelului din `sync_metadata`, nu `DEFAULT_MODEL`;
- testele care folosesc `builder.MODEL_DIMENSION` trec pe `profile.dimension`.

**Pas 5. Build Qwen în baza separată (îl rulezi tu)**
Creezi baza `medicina_qwen`, apoi rulezi build-ul din `.venv-gpu`, cu
`DATABASE_URL` spre ea, `EMBEDDING_DEVICE=cuda`, `--batch-size 8` și
`--model Qwen/Qwen3-Embedding-0.6B` (fp32 ca nume; pe GPU se încarcă în fp16).
Durată estimată ~17 minute (~19.850 de ferestre, 8.861 de fragmente). Îți dau
comanda exactă când ajungem aici.

**Pas 6. Evaluare comparativă** (vezi §6).

**Pas 7. Comutare**
- `DEFAULT_MODEL` → modelul ales; `DATABASE_URL` de producție → baza nouă
  (sau reconstrucție în baza principală, cu baza e5 păstrată ca backup).
- `docker-compose.yaml`: limita de memorie verificată; cache-ul modelului
  pre-populat în `data/model_cache` (montat deja), pentru că rularea e offline
  (`HF_HUB_OFFLINE=1`).
- `README.md` și `architecture/hybrid-index-generation.md` actualizate.

**Pas 8. Curățenie (după 1–2 săptămâni fără probleme)**
Ștergerea bazei e5 și eventual a profilului e5 din `PROFILES`.

## 6. Criterii de acceptare

Comparație `tmp/eval-e5-baseline.json` vs `tmp/eval-qwen.json`, pe trei grupe:
**toate**, **cu afecțiune recunoscută**, **fără afecțiune recunoscută**.

Se adoptă Qwen dacă:
1. nDCG@10 pe grupa „fără afecțiune” crește clar (orientativ ≥ +3 puncte), și
2. nicio grupă nu scade cu mai mult de 1 punct la nDCG@10 sau Recall@50, și
3. `priority_order_violations` rămâne 0, și
4. latența p95 a `rank()` în container rămâne acceptabilă (orientativ < 300 ms).

Dacă (1) nu e îndeplinit, Qwen nu se adoptă: modelul nu aduce nimic pentru
felul în care e construit scorul, iar costul (RAM, latență, timp de build) nu
se justifică. Următorul experiment ar fi atunci ferestre mai mari (D7) sau o
pondere mai mare pentru V. Ponderea e însă o decizie de scoring, separată de
această migrare.

## 7. Rollback

Până la Pasul 8: se schimbă `DATABASE_URL` înapoi pe baza e5. Codul suportă
ambele profiluri, iar search-ul alege profilul după `sync_metadata`, deci nu e
nevoie de revert de cod.

## 8. Măsurători (PC dezvoltator: 24 nuclee fizice / 32 fire, RTX 3500 Ada 11,5 GB, 32 GB RAM)

Corpus: 8.861 de fragmente, 18,06 M caractere, ~19.850 de ferestre de embedding
(1400 de caractere, suprapunere 240).

| Configurație | Întrebare p50 / p95 | Ferestre/s | Indexare corpus |
|---|---|---|---|
| CPU, Qwen `-Q` (int8), 4 fire | 3.505 / 3.754 ms | 0,5 | – |
| CPU, Qwen `-Q` (int8), 8 fire | 866 / 904 ms | 0,7 | ~8 h |
| CPU, Qwen fp32, 8 fire | **111 / 135 ms** | n/m | n/m |
| **GPU fp16, lot 8** | n/m | **19,7** (1,9 GB VRAM) | **~17 min** |
| GPU fp16, lot 16 | n/m | 18,3 (2,7 GB) | – |
| GPU fp16, lot 32 | n/m | 17,3 (4,3 GB) | – |

- n/m = nemăsurat. Pentru e5-small nu există încă o măsurătoare de fire în acest
  document; valoarea implicită 8 din `EMBEDDING_THREADS` este un punct de plecare.
- Fidelitate GPU fp16 vs CPU fp32: cosinus per text min 0,99978.
- Cu `--index-url` fără `--no-deps` și cu cache-ul pip activ, instalarea se bloca
  (compilare din surse; *Controlled folder access*). Vezi D8.
