# Plan de refactorizare — scorul unui fragment (P1 → P4)

**Stare:** implementat; rezultatele măsurate sunt în secțiunea 11 · **Data:** 2026-09-30

**Înlocuiește:** secțiunile 2–4, 7 și 9 din fluxul de căutare și scoring de dinainte de refactorizare (rescris acum în [fragment-search-and-scoring.md](fragment-search-and-scoring.md)): fuziunea RRF, semnalul de titlu/cale, prioritatea calculată în Python, candidații `SEARCH_CANDIDATE_LIMIT` per semnal și `fit_evidence_to_context()`.

**Nu se schimbă:** fragmentarea R1/R2/D1 ([plan](fragmentation-refactoring-plan.md)), schema tabelei `chunks`, modelul de embedding, dicționarul `data/medical_conditions.txt`. **Nu este nevoie de reindexare.**

---

## 1. De ce refactorizăm

### 1.1. Probleme de design

| # | Problemă | Consecință |
|---|---|---|
| A1 | Fiecare semnal (semantic, lexical, titlu/cale) își păstrează doar top `SEARCH_CANDIDATE_LIMIT` (100–200) înainte de fuziune. | Un fragment care e al 201-lea la toate semnalele nu este evaluat deloc, chiar dacă are afecțiunea în titlu. Tăierea e arbitrară și se face **înainte** de scor, nu după. |
| A2 | RRF folosește doar **poziția** în fiecare listă, nu mărimea scorului. | Locul 1 și locul 2 diferă la fel, fie că scorurile sunt aproape egale, fie foarte diferite. Prioritățile nu pot fi exprimate explicit. |
| A3 | Prioritatea (1/3/10) se recalculează în Python la fiecare căutare, scanând din nou textul fiecărui candidat (`name_matcher()`). | Dublează munca făcută deja la indexare în `primary_medical_conditions` / `secondary_medical_conditions` și este cea mai lentă etapă a căutării. |
| A4 | Semnalul de titlu construiește `to_tsvector(heading ‖ cale)` la fiecare interogare, pe toate rândurile. | ~90 ms per căutare, fără index. Pune și numele fișierului în scor, deși decizia Q3 din planul de fragmentare spune că numele fișierului nu contează. |
| A5 | `ConditionDictionary.match()` se aplică pe tot mesajul, nu pe fiecare expresie dintre virgule, și păstrează doar termenii cei mai lungi. | `gripa, tuse` recunoaște doar **Gripa**; Tuse se pierde (verificat). |
| A6 | Sinonimele (`expansions`) intră în interogarea lexicală ca grupuri `SAU` separate, alături de expresia utilizatorului. | Regula „ȘI în interiorul expresiei” este ocolită: la `tratament pentru gripa la copii`, grupul de sinonime `(gripa:*)` potrivește orice fragment care conține „gripa”, chiar dacă nu conține nici „tratament”, nici „copii” (verificat). |
| A7 | Scriptul de evaluare apelează `rank()` fără `condition_names`, deci nu măsoară deloc prioritatea. | Rezultatele evaluării nu reflectă ce rulează în aplicație. |

### 1.2. Latența măsurată (2026-09-30, index de 9.601 fragmente, 151 MB, model încărcat)

| Etapă — `rank("gripa")` actual | Timp |
|---|---|
| Embedding interogare (model deja încărcat; primul apel ~50 ms) | ~5 ms |
| Semantic, top-100 exact | 80–150 ms |
| Lexical (strict + eventual lax) | ~80 ms |
| Titlu/cale, `to_tsvector` la interogare | ~90 ms |
| Prioritate în Python pe ~350 de texte | ~280 ms |
| **Total `rank()`** | **1.040–1.090 ms** |

Restul până la total vine din aducerea textelor, din calculul similarității pentru uniunea candidaților și din drumurile separate până la baza de date.

**Prototipul formulei noi** (o singură interogare SQL, secțiunea 4), pe aceleași date: **49 ms execuție în Postgres** (`EXPLAIN ANALYZE`, „gripa”). Măsurat din client, inclusiv transferul a 300–600 de fragmente cu text: 110–350 ms la cald. Prima rulare a unei interogări noi urcă până la ~570 ms, pentru că tabela (151 MB) nu încape în `shared_buffers` implicit (128 MB) — vezi 5.2.

---

## 2. Decizii

### 2.1. Confirmate de utilizator

| # | Întrebare | Decizie |
|---|---|---|
| D0 | Ordinea priorităților | **P1** afecțiunea în `primary_medical_conditions` › **P2** afecțiunea în `secondary_medical_conditions` › **P3** scor lexical › **P4** potrivire semantică. |
| D1 | Cât de strict domină P3 peste P4 | **Soft:** lexicalul contează de 2 ori mai mult decât semanticul. O potrivire semantică foarte bună poate depăși o potrivire lexicală slabă. P1 și P2 domină **strict** (secțiunea 3.3). |
| D2 | Ce intră în rezultat | Fără limită per semnal. **Toate** fragmentele primesc scor; lista se sortează descrescător după scorul total; apoi se elimină **fragmente întregi din coadă** până când suma caracterelor este ≤ `MAX_CONTEXT_CHARS`. |
| D3 | `MAX_CONTEXT_CHARS` | **1.000.000** (implicit în cod, `.env`, `docker-compose.yaml`, README). |
| D4 | Potriviri lexicale parțiale | **Scor lexical zero.** Mesajul se împarte la virgulă în **expresii**. Între expresii se aplică **SAU**, iar între cuvintele unei expresii se aplică **ȘI**. Un fragment primește scor lexical doar dacă îndeplinește toate cuvintele a cel puțin unei expresii. Pragul `MIN_STRICT_LEXICAL_HITS` și interogarea laxă dispar. |
| D5 | Sinonimele afecțiunii în semnalul lexical | **Da**, se păstrează. |

**Exemplul de referință pentru D4:** mesajul `durere de genunchi la efort, artroza`. Fragmentul B conține „genunchi” și „artroza”, dar nu și „durere” sau „efort”. B potrivește expresia `artroza`, deci primește scor lexical (și, cel mai probabil, P2, dacă Artroza este în `secondary_medical_conditions`). Un fragment care conține doar „durere” nu îndeplinește nicio expresie, deci primește L = 0.

### 2.2. Interpretări derivate (de confirmat la review)

- **I1. „Afecțiunea dată de utilizator”** = afecțiunile din dicționar recunoscute în **fiecare expresie** a mesajului (separată prin virgulă), cu regulile actuale din `match()`, reunite și fără duplicate. Se compară **numele canonic** (primul termen de pe rând), exact ce scrie fragmenterul în coloanele `primary_` / `secondary_medical_conditions`. Sinonimele sunt deja rezolvate la indexare. Corectează A5.
- **I2. Mai multe afecțiuni în mesaj:** P1 = 1 dacă fragmentul are în titlu **oricare** dintre ele (la fel pentru P2). Nu se folosește o fracție, ca să rămână garanțiile de dominanță de la 3.3.
- **I3. Mesaj fără nicio afecțiune recunoscută** (ex. `durere de genunchi la efort`): P1 = P2 = 0 pentru toate fragmentele, iar ordinea este dată doar de L și V. Nu apare niciun mesaj „Am identificat afecțiunea”.
- **I4. Sinonimele respectă regula ȘI (corectează A6).** În fiecare expresie, cuvintele care numesc afecțiunea sunt înlocuite cu un **SAU** între denumirile ei, iar restul cuvintelor rămân legate prin **ȘI**:
  `tratament pentru gripa la copii` → `tratame:* & copii:* & (gripa:* | influen:* | (season:* & flu:*) | grip:* | …)`.
  Când expresia este doar afecțiunea (`gripa`), rezultatul este SAU-ul denumirilor ei.
- **I5. Semnalul separat de titlu/cale dispare** (confirmat). Rolul lui este preluat de P1, care folosește coloana precalculată `primary_medical_conditions` (afecțiunea din titlul propriu al fragmentului; titlurile părinte și numele fișierului nu contează, consecvent cu Q3 din planul de fragmentare). **Precizare descoperită la implementare:** coloana `text_search` indexează `text ‖ heading ‖ cale`, deci un cuvânt din titlu sau din numele fișierului se potrivește în continuare **lexical** (L), doar că nu mai există un semnal și un termen RRF separat pentru el. Categoriile alese de pacient rămân un **filtru**, nu un scor.
- **I6. Bugetul numără caracterele textului de dovadă** — exact textul trimis către AI (`Secțiune: <heading>\n\n` + text, vezi `Retriever._context()`), nu lungimea JSON serializată. Se aplică **o singură dată, în SQL**. `fit_evidence_to_context()` se elimină.
- **I7. Fragmentele cu scor 0** (nicio afecțiune, niciun cuvânt, similaritate semantică sub mediană) nu intră în rezultat. În practică bugetul de 1.000.000 de caractere (~480 de fragmente, cu media de 2.083 de caractere) se umple mult înainte să ajungem la ele. Regula contează doar când filtrul de categorii lasă foarte puține fragmente.
- **I8. L și V sunt relative la căutare** (normalizate pe fragmentele din căutarea curentă, secțiunea 3.2). Procentul de relevanță arată cât de bun e un fragment **în această căutare**. Nu se compară între căutări diferite.

---

## 3. Formula

### 3.1. Formula

```text
score = 8·P1 + 4·P2 + 2·L + 1·V          score ∈ [0, 15]

relevance_percent = score / 15 × 100
```

| Termen | Tip | Definiție |
|---|---|---|
| **P1** | {0, 1} | 1 dacă `primary_medical_conditions` conține cel puțin o afecțiune din mesaj (I1, I2) |
| **P2** | {0, 1} | 1 dacă `secondary_medical_conditions` conține cel puțin o afecțiune din mesaj |
| **L** | [0, 1] | scorul lexical al fragmentului, raportat la cel mai bun scor lexical din căutare |
| **V** | [0, 1] | similaritatea semantică, rescalată între mediana și maximul căutării |

### 3.2. Normalizarea L și V

**L — lexical.**

```text
raw(f) = ts_rank_cd(text_search, Q, 1)     dacă text_search @@ Q, altfel fragmentul are L = 0
L(f)   = raw(f) / max(raw)                  maximul se ia peste fragmentele potrivite în căutarea curentă
```

- `Q` este tsquery-ul construit după D4 și I4: expresiile sunt legate prin `|`, cuvintele unei expresii prin `&`, iar cuvintele afecțiunii sunt înlocuite cu `(sinonim₁ | sinonim₂ | …)`.
- Cuvintele relevante și stemurile pe prefix rămân cele de acum (`_content_stems()`, `_stem()`): fără cuvintele din `generic_query_words.txt`, iar cuvintele de cel puțin 6 litere pierd ultimele 2 litere și se caută ca prefix (`stem:*`).
- Normalizarea `1` a `ts_rank_cd` împarte la `1 + log(lungimea documentului)`. Astfel un fragment scurt, concentrat pe subiect, bate același cuvânt pomenit într-un capitol de 400.000 de caractere.
- Cel mai bun fragment lexical are L = 1. Cele care nu se potrivesc au L = 0.

**V — semantic.**

```text
cos(f) = −(embedding <#> q)                                     vectorii sunt normalizați L2, deci produsul scalar = cosinus
V(f)   = clamp( (cos(f) − mediana_cos) / (max_cos − mediana_cos), 0, 1 )
```

Mediana și maximul se calculează peste **toate** fragmentele din categoriile selectate. Motivul este măsurat: E5 comprimă similaritățile într-o bandă îngustă care se mută de la o interogare la alta, deci un prag fix nu funcționează.

| Interogare | mediană cos | p99 | max |
|---|---|---|---|
| gripa | 0,791 | 0,828 | 0,873 |
| gută | 0,816 | 0,850 | 0,889 |
| hipertensiune | 0,816 | 0,855 | 0,912 |
| durere de genunchi la efort | 0,821 | 0,857 | 0,889 |

Rescalarea face ca fragmentul cel mai apropiat semantic să aibă V = 1. Jumătatea mai puțin similară din corpus are V = 0.

### 3.3. Garanțiile de prioritate

Greutățile sunt puteri ale lui 2, alese astfel încât fiecare prioritate să fie mai mare decât suma maximă a tuturor celor de sub ea:

| Garanție | Verificare |
|---|---|
| P1 domină **strict** P2 + P3 + P4 | 8 > 4 + 2 + 1 = 7 |
| P2 domină **strict** P3 + P4 | 4 > 2 + 1 = 3 |
| P3 față de P4: **soft**, lexicalul contează dublu (D1) | 2·L față de 1·V |

Deci **orice** fragment cu afecțiunea în titlu (scor ≥ 8) stă deasupra **oricărui** fragment fără ea (scor ≤ 7). Orice fragment cu afecțiunea în text (≥ 4) stă deasupra oricărui fragment care are doar potrivire lexicală și semantică (≤ 3). Un fragment cu afecțiunea în titlu **și** în text (≥ 12) stă deasupra celui care o are doar în titlu (≤ 11).

### 3.4. Exemplu pentru „gripa”

| Fragment | P1 | P2 | L | V | score | relevanță |
|---|---|---|---|---|---|---|
| R1 `### Gripa – tratament`, textul pomenește gripa | 1 | 1 | 0,80 | 0,90 | 8 + 4 + 1,60 + 0,90 = **14,50** | 97% |
| R1 `### Gripa`, text fără cuvântul „gripa” | 1 | 0 | 0,30 | 0,70 | 8 + 0,60 + 0,70 = **9,30** | 62% |
| R2 `### Echinaceea`, textul pomenește gripa (cel mai bun posibil) | 0 | 1 | 1,00 | 1,00 | 4 + 2 + 1 = **7,00** | 47% |
| D1 care spune „influenza” | 0 | 0 | 0,50 | 0,60 | 1,00 + 0,60 = **1,60** | 11% |
| D1 doar semantic, foarte apropiat | 0 | 0 | 0 | 0,90 | **0,90** | 6% |
| D1 care pomenește „gripei” o dată, într-un text lung | 0 | 0 | 0,10 | 0,20 | 0,20 + 0,20 = **0,40** | 3% |

Ultimele două rânduri arată decizia D1: o potrivire lexicală slabă poate fi depășită de o potrivire semantică foarte bună.

### 3.5. Ordinea finală și departajarea

`ORDER BY score DESC, chunk_id ASC`. Departajarea după `chunk_id` face ordinea (și deci tăierea din coadă) deterministă, necesară pentru teste și pentru ca pacientul să vadă aceleași fragmente la o căutare repetată.

---

## 4. Arhitectura noii căutări

### 4.1. Fluxul

```text
mesaj utilizator
  ├─ Python  (≤ 25 ms)
  │    1. normalizare spații; mesaj gol → rezultat gol
  │    2. împărțire în expresii la virgulă
  │    3. dicționar: afecțiunile fiecărei expresii → nume canonice (P1/P2) + sinonime (lexical)
  │    4. tsquery Q după D4 + I4
  │    5. vectorul E5 al mesajului ("query: …", normalizat L2)
  └─ Postgres — O SINGURĂ interogare (~50 ms în server)
       6. pool   = fragmentele din categoriile selectate: P1, P2 (GIN pe array), cos (scanare exactă)
       7. lex    = fragmentele cu text_search @@ Q (GIN) și raw = ts_rank_cd
       8. stats  = mediana și maximul cos; maximul raw
       9. scored = 8·P1 + 4·P2 + 2·L + V; se păstrează doar score > 0
      10. kept   = SUM(evidence_chars) OVER (ORDER BY score DESC, chunk_id) ≤ MAX_CONTEXT_CHARS
      11. join cu chunks → text + metadate DOAR pentru fragmentele păstrate
```

Nu mai există: top-N per semnal, uniune de candidați, al doilea drum pentru texte, bucle Python pe fiecare fragment, `to_tsvector` calculat la interogare.

### 4.2. Interogarea SQL (schiță)

```sql
WITH
q AS (SELECT to_tsquery('simple', unaccent(%(tsquery)s)) AS tq),
pool AS (
    SELECT chunk_id, char_count, heading,
           (primary_medical_conditions   && %(conditions)s::text[])::int AS p1,
           (secondary_medical_conditions && %(conditions)s::text[])::int AS p2,
           -(embedding <#> %(qvec)s) AS cos
    FROM chunks
    WHERE {category_filter}                       -- "TRUE" sau category_id = ANY(%(categories)s)
),
lex AS (
    SELECT chunk_id, ts_rank_cd(text_search, q.tq, 1) AS raw
    FROM chunks, q
    WHERE text_search @@ q.tq AND {category_filter}   -- folosește idx_chunks_text_search (GIN)
),
cos_stats AS (
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY cos) AS p50, max(cos) AS mx FROM pool
),
lex_stats AS (SELECT max(raw) AS mx FROM lex),
scored AS (
    SELECT p.chunk_id, p.p1, p.p2, p.cos, l.raw,
           coalesce(l.raw / nullif(ls.mx, 0), 0)                                   AS lexical,
           greatest(0, least(1, coalesce((p.cos - cs.p50) / nullif(cs.mx - cs.p50, 0), 0))) AS semantic,
           p.char_count + CASE WHEN p.heading <> '' THEN char_length(p.heading) + 12 ELSE 0 END
                                                                                   AS evidence_chars
    FROM pool p
    CROSS JOIN cos_stats cs CROSS JOIN lex_stats ls
    LEFT JOIN lex l USING (chunk_id)
),
ranked AS (
    SELECT *, 8*p1 + 4*p2 + 2*lexical + semantic AS score FROM scored
),
kept AS (
    SELECT *, sum(evidence_chars) OVER (ORDER BY score DESC, chunk_id
                                        ROWS UNBOUNDED PRECEDING) AS running_chars
    FROM ranked
    WHERE score > 0
)
SELECT k.chunk_id, k.score, k.p1, k.p2, k.lexical, k.semantic, k.cos, k.raw,
       c.source_relative_path, c.source_absolute_path, c.line_start, c.line_end,
       c.heading, c.text, c.source_sha256, c.business_category,
       c.primary_medical_conditions, c.secondary_medical_conditions
FROM kept k JOIN LATERAL (SELECT * FROM chunks WHERE chunk_id = k.chunk_id) c ON TRUE
WHERE k.running_chars <= %(max_chars)s
ORDER BY k.score DESC, k.chunk_id;
```

Note:

- **Tăierea din coadă (D2)** este exact prefixul sortat: suma cumulată crește monoton, deci primul fragment care depășește bugetul le scoate și pe toate cele de după. Fragmentele sunt eliminate întregi, niciodată trunchiate.
- `12` = lungimea prefixului `Secțiune: ` (10) + `\n\n` (2), identic cu `Retriever._context()`. Formula stă într-o singură constantă Python, `EVIDENCE_PREFIX`, folosită și de `_context()`, ca să nu se desincronizeze.
- Fără tsquery (mesaj fără niciun cuvânt folosibil), CTE-ul `lex` nu se generează și L = 0 peste tot. Fără afecțiuni, `conditions = '{}'`, iar `&&` cu un array gol este fals.
- Filtrul de categorii se aplică **înainte** de statistici. Mediana și maximul se calculează doar pe subsetul ales, deci V rămâne corect relativ la ce caută pacientul.
- Textul pleacă din Postgres doar pentru fragmentele păstrate (≤ 1.000.000 de caractere).

### 4.3. Contractul rezultatului `rank()`

| Câmp | Conținut |
|---|---|
| `chunk_id`, `source_relative_path`, `source_absolute_path`, `line_start`, `line_end`, `heading`, `text`, `source_sha256`, `business_category`, `primary_medical_conditions`, `secondary_medical_conditions` | ca acum |
| `score` | 0–15, formula 3.1 (înlocuiește `hybrid_score`) |
| `condition_in_title` | P1 (bool) — înlocuiește `priority` 1 |
| `condition_in_text` | P2 (bool) — înlocuiește `priority` 3 |
| `lexical_score` | L (0–1), `None` când nu s-a potrivit lexical |
| `semantic_score` | V (0–1) |
| `semantic_similarity` | cosinusul brut (pentru log și evaluare) |
| `found_by_lexical` | L > 0 |

Se elimină: `hybrid_score`, `priority`, `lexical_rank`, `found_by_heading`.

---

## 5. Performanță

### 5.1. Ținte

| Măsură | Țintă | Cum se verifică |
|---|---|---|
| `rank()` p50 | ≤ 150 ms | `scripts/evaluate_retrieval.py` (57 de interogări) |
| `rank()` p95 | ≤ 300 ms | idem |
| Execuție SQL în server | ≤ 80 ms | `EXPLAIN (ANALYZE, BUFFERS)` pe „gripa” |
| Capăt la capăt, „gripa” în chat → fragmente afișate | **< 1 s** | log-urile `retrieval_started` / `retrieval_completed` + măsurare în browser |

### 5.2. Măsuri

1. **O singură interogare SQL** (secțiunea 4.2), un singur drum la baza de date.
2. **P1/P2 din coloane precalculate** cu index GIN (`idx_chunks_primary_conditions`, `idx_chunks_secondary_conditions` există deja): ~0,1 ms în loc de ~280 ms de Python.
3. **Lexical prin GIN** (`idx_chunks_text_search`): `ts_rank_cd` se calculează doar pe fragmentele potrivite (sute), nu pe tot indexul.
4. **Semantic: scanare exactă a tuturor vectorilor** (~30 ms la 9.601 fragmente). Este necesară, pentru că formula dă scor fiecărui fragment și V are nevoie de mediana căutării. Un index aproximativ (HNSW/ivfflat) nu ajută aici.
5. **`shared_buffers = 512MB`** pentru containerul Postgres (`command: postgres -c shared_buffers=512MB` în `docker-compose.yaml`). Tabela are 151 MB și depășește valoarea implicită de 128 MB. Asta produce vârfurile de ~500 ms la prima rulare a unei interogări noi. Pe mașina locală de dezvoltare se setează la fel în `postgresql.conf`.
6. **Încălzirea modelului la pornire:** `web/main.py` încarcă modelul E5 și face un embedding de probă la startup. Primul apel costă ~50 ms plus încărcarea ONNX; acum îl plătește primul pacient.
7. **Dicționarul** rămâne în cache pe proces (`lru_cache` + `mtime`). Potrivirea costă 0,2–20 ms. Aceeași rezolvare (`resolve_query()`, 6.1) servește și mesajul „Am identificat afecțiunea”, și căutarea, și evaluarea. Nu se mai calculează de trei ori.

### 5.3. Scalabilitate

Costul dominant este scanarea exactă a vectorilor, liniară în numărul de fragmente: ~30 ms la 10 mii, ~300 ms estimat la 100 de mii. Până la ~50 de mii de fragmente nu e nevoie de nimic în plus. Peste acest volum, în ordinea preferinței:

1. `halfvec(384)`, care înjumătățește datele citite;
2. matricea de embeddings ținută în memorie (numpy, 15 MB la 10 mii de fragmente), cu `cos` calculat în Python și trimis ca parametru.

Nu se implementează acum.

---

## 6. Modificări pe fișiere

### 6.1. `ai/conditions.py`

- **Nou:** `resolve_query(query) -> ResolvedQuery`, un dataclass înghețat cu:
  - `segments`: lista de expresii (la virgulă, cu spațiile normalizate);
  - pentru fiecare expresie, afecțiunile ei și **poziția cuvintelor** care le numesc (necesar la I4);
  - `condition_names`: numele canonice, unice, în ordinea apariției (pentru P1/P2);
  - `synonyms`: denumirile fiecărei afecțiuni (pentru lexical).
- `find()` primește o variantă care întoarce și intervalele de cuvinte potrivite (există deja intern, în bucla din `find()`).
- `match()` rămâne regula de potrivire pe **o expresie**. `resolve_query()` o aplică pe fiecare expresie (corectează A5). `MAX_MATCHED_CONDITIONS` se aplică per expresie.
- Se elimină `names()`, `expansions()`, `condition_names_for()`, `expansions_for()`, înlocuite de `resolve_query()`.

### 6.2. `ai/search.py`

- `lexical_query(resolved) -> str | None` înlocuiește `lexical_queries()`: o singură interogare, după D4 + I4. Dispare interogarea laxă.
- `rank(query, category_ids=None) -> list[dict]` rezolvă singur interogarea (`resolve_query()`), construiește Q și vectorul și rulează SQL-ul din 4.2. Apelanții (aplicația, evaluarea, CLI-ul) nu mai pot trimite parametri diferiți (corectează A7).
- Constante noi, documentate cu garanția de la 3.3:
  `WEIGHT_PRIMARY = 8`, `WEIGHT_SECONDARY = 4`, `WEIGHT_LEXICAL = 2`, `WEIGHT_SEMANTIC = 1`, `MAX_SCORE = 15`.
  Un test verifică `WEIGHT_PRIMARY > WEIGHT_SECONDARY + WEIGHT_LEXICAL + WEIGHT_SEMANTIC` și `WEIGHT_SECONDARY > WEIGHT_LEXICAL + WEIGHT_SEMANTIC`, ca să nu se strice garanția la o ajustare ulterioară.
- Se elimină: `RRF_K`, `RRF_SIGNAL_COUNT`, `RRF_MAX_SCORE`, `PRIORITY_WEIGHT`, `NOT_FOUND_PRIORITY`, `MIN_STRICT_LEXICAL_HITS`, `_lexical_hits()`, `_heading_ids()`, `name_matcher()`, `query_priority()`.
- `main()` (CLI) afișează `score`, P1, P2, L, V.

### 6.3. `ai/retrieval.py`

- `collect()` nu mai calculează sinonime sau nume: apelează `rank(query, category_ids)` și transformă rândurile în dovezi.
- `relevance_percent = score / MAX_SCORE × 100`.
- Câmpurile dovezii: cele de acum, cu `priority` înlocuit de `condition_in_title` / `condition_in_text`, `semantic_similarity` înlocuit de `semantic_score` (V) și `lexical_score` = L.
- `_context()` folosește constanta `EVIDENCE_PREFIX` (4.2).

### 6.4. `ai/client.py` și `web/main.py`

- Se elimină `fit_evidence_to_context()`, `_entries_within_budget()`, `_ordered_entries()` (dacă nu mai are alt apelant) și constanta `MAX_CONTEXT_CHARS` din `client.py`. Bugetul este aplicat de `rank()` (I6).
- `on_find_fragments()` folosește direct `retriever.collect(session)`.
- `_condition_identified_message()` folosește `resolve_query()` și afișează toate afecțiunile din toate expresiile.
- Comentariul despre timeout-ul de 5 minute (care pomenește 2,4 milioane de caractere) se actualizează.

### 6.5. Interfața

- `web/handlers.py`: câmpul `priority` devine `conditionMatch: "title" | "text" | null`. `semanticScore` = V, `lexicalScore` = L (ambele 0–1).
- `frontend/src/api/types.ts`, `FragmentsPanel.tsx`: filtrul „Prioritate 1/3/10” devine „Afecțiune: în titlu / în text / oricare”. Eticheta scorului devine `Afecțiune în titlu` / `Afecțiune în text` în loc de `Prioritate N`. Filtrul semantic (0,05–0,95) rămâne și se aplică acum pe V, care are o scară mai utilă decât cosinusul brut.
- `reporting/pdf.py`: nu se modifică. Ordonează secțiunile raportului după `relevance_percent`, care rămâne în dovezi cu aceeași semnificație (0–100, mai mare = mai relevant).

### 6.6. Configurare și documentație

- `config.py`: se elimină `search_candidate_limit` (`SEARCH_CANDIDATE_LIMIT`). `max_context_chars` rămâne 1.000.000.
- `docker-compose.yaml`: `MAX_CONTEXT_CHARS: ${MAX_CONTEXT_CHARS:-1000000}`, plus `shared_buffers` pentru `db` (5.2).
- `README.md`: rândul pentru `MAX_CONTEXT_CHARS` (1.000.000, caractere de text al dovezilor, nu JSON); se elimină `SEARCH_CANDIDATE_LIMIT`.
- `architecture/fragment-search-and-scoring.md`: secțiunile 2–4, 7 și 9 se rescriu după formula nouă. Acest plan rămâne ca istoric, cu starea „implementat”.

### 6.7. `scripts/evaluate_retrieval.py`

- Apelează `rank(query)`, care include acum automat afecțiunile (corectează A7).
- `--no-conditions` rămâne, ca `resolve_query()` fără dicționar, pentru comparație.
- Raportează suplimentar p50/p95 pentru execuția SQL separat de embedding.

---

## 7. Teste

Unitare, fără bază de date:

| Test | Verifică |
|---|---|
| `test_weights_keep_priority_order` | inegalitățile de la 3.3 |
| `test_lexical_query_segments_or_words_and` | `a b, c` → `(a:* & b:*) \| (c:*)` |
| `test_lexical_query_substitutes_condition_synonyms` | I4: `tratament pentru gripa la copii` → `tratame:* & copii:* & (gripa:* \| influen:* \| …)`, fără grup `gripa:*` de sine stătător |
| `test_resolve_query_per_segment` | `gripa, tuse` → Gripa **și** Tuse |
| `test_resolve_query_without_condition` | `durere de genunchi la efort` → fără afecțiuni, doar lexical |
| `test_resolve_query_empty` | mesaj gol → `rank()` întoarce `[]` fără să atingă baza de date |

Integrare (Postgres efemer, `tests/support/postgres.py`, corpus sintetic mic):

| Test | Verifică |
|---|---|
| `test_primary_beats_everything` | un fragment P1 fără potrivire lexicală și semantic slab stă deasupra unui fragment P2 perfect lexical și semantic |
| `test_secondary_beats_lexical_and_semantic` | analog pentru P2 față de L + V |
| `test_lexical_counts_double` | D1: L = 1, V = 0 (scor 2) bate L = 0, V = 1 (scor 1); L = 0,1, V = 0,2 pierde în fața lui V = 0,9 |
| `test_partial_expression_scores_zero_lexical` | exemplul D4: „durere” singur → L = 0; „genunchi + artroza” → L > 0 |
| `test_budget_cuts_whole_fragments_from_tail` | cu `MAX_CONTEXT_CHARS` mic: prefix sortat, fragmente întregi, suma ≤ buget, primul care nu încape le scoate pe toate cele de după |
| `test_category_filter_before_stats` | V și L se normalizează pe subsetul filtrat |
| `test_no_candidate_limit` | un fragment P1 aflat pe locul 500 semantic și în afara oricărui top lexical apare totuși primul |
| `test_deterministic_tie_break` | la scoruri egale, ordinea după `chunk_id` |

Testele existente din `tests/unit/ai/test_search.py` și `tests/unit/web/test_web.py` care verifică RRF, prioritatea 1/3/10, `found_by_heading`, `fit_evidence_to_context` și `MAX_CONTEXT_CHARS` din `client` se rescriu sau se elimină odată cu codul lor.

---

## 8. Evaluare și acceptare

1. **Înainte de orice modificare**, pe indexul actual:
   ```bash
   python scripts/evaluate_retrieval.py --output tmp/eval-scoring-before.json
   ```
2. După implementare, **fără reindexare** (schema și datele nu se schimbă):
   ```bash
   python scripts/evaluate_retrieval.py --output tmp/eval-scoring-after.json
   ```
3. Criterii de acceptare:
   - latența `rank()`: p50 ≤ 150 ms, p95 ≤ 300 ms; „gripa” capăt la capăt < 1 s;
   - pentru fiecare interogare care numește o afecțiune, **toate** fragmentele cu afecțiunea în `primary_medical_conditions` apar înaintea oricărui alt fragment (verificat automat de script, ca metrică nouă: `priority_order_violations = 0`);
   - nDCG@10 și P@10 nu scad față de `tmp/eval-scoring-before.json`. Dacă scad, se analizează interogările afectate înainte de a ajusta ceva. Etichetele setului de evaluare se bazează pe titlu și cale, deci eliminarea semnalului de cale (I5) poate penaliza artificial fișierele dedicate fără titluri Markdown (vezi riscul R1).

**Ajustări permise după evaluare**, fără a strica garanțiile de la 3.3: raportul L:V (2:1) și modul de normalizare a lui V (mediană → alt percentil). Orice ajustare trece prin testul `test_weights_keep_priority_order`.

---

## 9. Ordinea implementării

| Pas | Conținut | Depinde de |
|---|---|---|
| 1 | Evaluarea „înainte” (8.1) | — |
| 2 | `resolve_query()` + teste (6.1) | — |
| 3 | `lexical_query()` cu I4 + teste (6.2) | 2 |
| 4 | SQL-ul nou în `rank()` + testele de integrare (4.2, 7) | 2, 3 |
| 5 | `retrieval.py`, eliminarea `fit_evidence_to_context()`, `web/main.py` (6.3, 6.4) | 4 |
| 6 | Interfața: handlers + frontend (6.5) | 5 |
| 7 | Config, `docker-compose.yaml`, `shared_buffers`, încălzirea modelului, README (5.2, 6.6) | — |
| 8 | `evaluate_retrieval.py` + evaluarea „după” (6.7, 8) | 4 |
| 9 | Rescrierea `fragment-search-and-scoring.md`; starea acestui plan → „implementat” | 8 |

---

## 10. Riscuri

| # | Risc | Atenuare |
|---|---|---|
| R1 | 88% dintre fragmente (8.478 din 9.601) sunt D1 și au coloanele de afecțiuni goale. Fișierele dedicate unei afecțiuni, dar fără titluri Markdown (ex. `Hemoroizi .md`), nu primesc P1/P2 și concurează doar prin L (numele fișierului rămâne în `text_search`) și V. | Consecvent cu decizia Q3 din planul de fragmentare. Restructurarea planificată a surselor în Markdown le transformă în R1. Până atunci, efectul se vede în evaluare (8.3). |
| R2 | Dicționarul se modifică după ultima indexare → coloanele P1/P2 rămân vechi până la resincronizare. | Documentat: orice modificare a `medical_conditions.txt` cere o sincronizare a indexului, rulată de utilizator. Opțional: `sync_metadata` păstrează hash-ul dicționarului, iar la pornire se emite un avertisment dacă diferă de fișierul curent. |
| R3 | L și V sunt relative la căutare (I8): cel mai bun fragment lexical are mereu L = 1, chiar dacă e slab în absolut. | Acceptat: P1/P2 nu depind de normalizare, iar fragmentele P3/P4 sunt ordonate relativ unele la altele, exact ce cere prioritatea. |
| R4 | O căutare frecventă („gripa”: 5 P1 + 69 P2 + ~735 lexicale) umple bugetul cu ~480 de fragmente → panoul din UI este lung. | Filtrele existente din panou (scor, afecțiune, lexical, document) rămân. Dacă randarea devine lentă, se paginează panoul în frontend. Scorul și selecția nu se schimbă. |
| R5 | Prima interogare după pornirea Postgres citește de pe disc. | `shared_buffers` (5.2); opțional `pg_prewarm('chunks')` la pornirea aplicației. |

---

## 11. Implementare și rezultate (2026-09-30)

Implementat conform planului; diferențele față de schița de mai sus:

- **`JOIN LATERAL` pe cheia primară** pentru textul fragmentelor păstrate (schița avea un `JOIN` obișnuit): planificatorul alegea un hash join peste toată tabela, text inclus, iar interogarea făcea 300–600 ms în loc de ~100 ms.
- **`V = 0` când toate similaritățile sunt egale** (`coalesce(…, 0)`): fără el, `greatest`/`least` ignoră `NULL` și un subset cu un singur fragment (sau cu similarități identice) ar fi primit V = 1. Acoperit de test.
- **Un mesaj fără niciun cuvânt** (`?!`) întoarce lista goală, fără interogare.
- **`SEARCH_CANDIDATE_LIMIT`** a fost eliminat din `config.py`; `fit_evidence_to_context()` a fost eliminată din `ai/client.py`.
- **`evaluate_retrieval.py`** măsoară acum `priority_order_violations`, iar `--no-conditions` dezactivează recunoașterea afecțiunilor.
- **Test pe indexul real:** `test_flu_query_retrieves_reflection_fragment_from_internal_dictionary` a fost înlocuit cu `test_flu_query_ranks_titled_sections_first_from_the_real_index`. Fragmentul „Marele dicționar” pe care îl verifica este D1 și, cu bugetul de 1.000.000 de caractere, nu mai încape pentru „gripa” (vezi mai jos).

### Evaluare (57 de interogări, același index, fără reindexare)

| Metrică | Înainte | După |
|---|---|---|
| Precision@10 | 0,323 | 0,326 |
| MRR | 0,790 | 0,846 |
| nDCG@10 | 0,598 | 0,636 |
| Recall@50 | 0,716 | 0,710 |
| `rank()` p50 | 985 ms | 467 ms |
| `rank()` p95 | 3.261 ms | 834 ms |
| `priority_order_violations` | — | 0 |

### Latență măsurată (mașina de dezvoltare, Postgres în Docker Desktop)

- **Execuția SQL în Postgres: 60–105 ms**; de la client, cu transferul textelor, 90–200 ms.
- Un mesaj nou costă în plus: **embedding 50–100 ms** (ONNX este lent pe forme noi de intrare; același mesaj repetat costă ~5 ms) și **recunoașterea afecțiunilor 1–100 ms** (`difflib` peste ~5.500 de termeni când mesajul nu e o potrivire exactă).
- Rezultat: `rank()` ia **150–230 ms pentru o interogare repetată** și **~470 ms la mediană pentru interogări noi**. Ținta din 5.1 (p50 ≤ 150 ms) nu este atinsă pentru interogări noi, dar ținta funcțională (< 1 s capăt la capăt pentru „gripa”) este atinsă cu marjă.
- Măsurători care au exclus multi-threading-ul ca soluție: paralelismul din Postgres scade timpul serverului de la 53 la 32 ms, dar nu se vede în timpul măsurat de aplicație; două fire Python pentru embedding și dicționar sunt mai lente decât execuția secvențială (37 ms față de 21 ms).
- `shared_buffers = 512MB` a fost adăugat în `docker-compose.yaml`, dar **nu a fost verificat** pe containerul local (necesită recrearea containerului `medicina-db`, pe care nu l-am repornit).

### Observație de calitate, pentru decizie

Cu bugetul de 1.000.000 de caractere aplicat exact pe scor, câteva fragmente foarte mari cu afecțiunea în text (P2) consumă bugetul înaintea fragmentelor mici și precise: pentru „gripa” intră doar ~50 de fragmente, între care unele de 196.579 și 399.530 de caractere (secțiuni de carte cu un singur cuvânt „gripa” în treacăt). Fragmentele D1 scurte, dar relevante (de exemplu cele din „Marele dicționar”), rămân dincolo de tăietură. Nu s-a schimbat nimic, pentru că regula (tăiere de la coadă a fragmentelor întregi) este cea confirmată; opțiuni dacă se dorește altfel: un plafon pe lungimea unui fragment, sau un număr maxim de fragmente. Restructurarea surselor în Markdown va reduce dimensiunea acestor fragmente.
