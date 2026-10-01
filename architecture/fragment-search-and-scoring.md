# Fluxul de căutare și scoring al fragmentelor

**Intrare:** problema de sănătate din profilul sesiunii și indexul din Postgres.

**Ieșire:** inventarul de dovezi (`evidence`): fragmente ordonate descrescător după scor, limitate la bugetul de context al furnizorului AI (`max_chars`), gata de afișat pacientului și de trimis către AI.

Documentul are două părți: **[Partea I — Rezumat](#partea-i--rezumat)** (cele 6 etape pe scurt) și **[Partea II — Detalii](#partea-ii--detalii)** (aceleași 6 etape, pas cu pas).

----------------------------------------------------------------------------------------------------

## Partea I — Rezumat

1. **Recunoașterea afecțiunii** (`resolve_query()`) — mesajul se împarte la virgulă, iar în fiecare parte se caută afecțiunile din `data/medical_conditions.txt` (cu sinonime și toleranță la greșeli de scriere). Pacientul vede în chat ce afecțiune s-a identificat.
2. **Scorul** — `score = 8·P1 + 4·P2 + 2·L + V` (maximum 15):
   - **P1** — afecțiunea este în titlul fragmentului;
   - **P2** — afecțiunea este în textul fragmentului;
   - **L** — fragmentul conține toate cuvintele căutate (căutare lexicală);
   - **V** — fragmentul are un sens apropiat de întrebare (căutare semantică).
3. **Căutarea** (`rank()`) — o singură interogare SQL notează toate fragmentele din sursele alese; se păstrează cele mai bune, cât încap în limita de text a furnizorului AI (fragmente întregi, tăiate de la coadă).
4. **Dovezile** (`Retriever.collect()`) — fiecare fragment păstrat devine o dovadă `C<id>`, cu sursa, scorul și procentul de relevanță.
5. **Afișarea** (`FragmentsPanel`) — pacientul vede fragmentele ordonate după scor și le poate filtra (scor, afecțiune, găsire lexicală, document).
6. **Setări** — limita de text per furnizor (`*_MAX_CONTEXT_CHARS`), dicționarul (`CONDITIONS_FILE`), modelul (`MODEL_CACHE_DIR`) și baza de date (`DATABASE_URL`).

```text
problema pacientului → afecțiuni recunoscute → score = 8·P1 + 4·P2 + 2·L + V
    → cele mai bune fragmente, cât încap în limita AI → afișate pacientului → trimise la AI
```

----------------------------------------------------------------------------------------------------

## Partea II — Detalii

Codul implicat: `ai/conditions.py` (`resolve_query()`), `ai/search.py` (`rank()`), `ai/retrieval.py` (`Retriever.collect()`), `web/main.py` (mesajele din chat), `web/handlers.py` și `frontend/src/components/FragmentsPanel.tsx` (afișarea).

### 1. Interogarea și afecțiunile recunoscute — `resolve_query()`

Problema pacientului este căutată cu **o singură interogare** (`consultation_query()`: problema de sănătate, cu spațiile normalizate). Istoricul conversației nu este folosit. Dacă problema este goală sau nu conține niciun cuvânt, căutarea se oprește și returnează un inventar gol.

- **1.1.** **Dicționarul de afecțiuni** (`data/medical_conditions.txt`, calea din `CONDITIONS_FILE`): o afecțiune pe linie, separată prin virgulă, cu numele canonic primul, urmat de sinonimele în română și engleză; liniile goale și cele care încep cu `#` sunt ignorate. Fișierul se reîncarcă automat când se modifică; un fișier lipsă înseamnă că nu se recunoaște nicio afecțiune.
- **1.2.** Mesajul se împarte la virgulă în **expresii**, iar afecțiunile se recunosc **în fiecare expresie separat** (`gripa, tuse` → Gripa și Tuse). Comparația ignoră diacriticele, majusculele și punctuația. Potrivirea în cadrul unei expresii, în ordine:
  - **1.2.1.** expresia este exact un termen din dicționar;
  - **1.2.2.** este o scriere aproape identică a unui termen întreg (raport `difflib` ≥ 0,9);
  - **1.2.3.** termeni din dicționar apar ca cuvinte întregi în expresie; câștigă cei mai lungi (`adenom de prostata`, nu `adenom`);
  - **1.2.4.** ultima variantă: cel mai apropiat termen după scriere (raport ≥ 0,84).
  - Se recunosc cel mult 2 afecțiuni pe expresie.
- **1.3.** Pentru fiecare expresie se reține și **restul** ei: cuvintele care nu fac parte din numele afecțiunii (`copii` în `gripa la copii`). Dacă expresia este chiar afecțiunea (sau o scriere aproape identică), restul este gol.
- **1.4.** Numele **canonice** ale afecțiunilor recunoscute (unice, în ordinea apariției) sunt exact valorile scrise la indexare în `primary_medical_conditions` / `secondary_medical_conditions`; ele decid P1 și P2 (secțiunea 2). Un mesaj fără nicio afecțiune recunoscută are P1 = P2 = 0 pentru toate fragmentele.
- **1.5.** Mesaj în chat: `POST /api/messages` adaugă, înaintea notificării „🔍 Caut rapid în cele N documente…”, un mesaj `✅ Am identificat afecțiunea: **Nume**. O caut și după denumirile: <sinonimele>.` pentru fiecare afecțiune recunoscută în orice expresie (`_condition_identified_message()` în `web/main.py`); partea cu sinonimele lipsește când afecțiunea nu are sinonime. Dacă nu se recunoaște nimic, nu apare niciun mesaj. Căutarea propriu-zisă rulează apoi separat, prin `POST /api/search`.

### 2. Formula scorului

```text
score = 8·P1 + 4·P2 + 2·L + 1·V          score ∈ [0, 15]
relevance_percent = score / 15 × 100
```

| Termen | Tip | Definiție |
|---|---|---|
| **P1** | {0, 1} | 1 dacă `primary_medical_conditions` (afecțiunile din **titlul** fragmentului) conține una dintre afecțiunile din mesaj |
| **P2** | {0, 1} | 1 dacă `secondary_medical_conditions` (afecțiunile din **textul** fragmentului) conține una dintre ele |
| **L** | [0, 1] | scorul lexical al fragmentului, raportat la cel mai bun scor lexical din căutare; 0 dacă nu se potrivește |
| **V** | [0, 1] | similaritatea semantică, rescalată între mediana și maximul căutării; 0 sub mediană sau când toate similaritățile sunt egale |

- **2.1. Prioritățile.** Greutățile sunt alese astfel încât P1 să bată orice combinație de semnale inferioare (8 > 4 + 2 + 1) și P2 să bată lexicalul și semanticul împreună (4 > 2 + 1). P3 față de P4 este intenționat **moale**: lexicalul contează dublu, dar o potrivire semantică foarte bună poate depăși una lexicală slabă. Constantele `WEIGHT_*` din `ai/search.py` sunt păzite de un test (`tests/unit/ai/test_search.py`) care verifică inegalitățile.
- **2.2. Semnalul lexical (L).**
  - **2.2.1.** Din fiecare expresie se iau cel mult 32 de cuvinte și se păstrează cele relevante: fără cuvintele din `ai/resources/generic_query_words.txt` și fără cele sub 3 caractere (într-o expresie fără afecțiune, dacă nu rămâne niciunul, se păstrează toate). Fiecare cuvânt, fără diacritice și cu litere mici, devine o potrivire pe prefix `stem:*`, unde stemul este cuvântul fără ultimele 2 litere pentru cuvintele de cel puțin 6 caractere (minimum 4 litere păstrate). Indexul folosește configurația `simple` (fără stemming românesc), iar prefixul acoperă flexiunile (`genunchi` găsește `genunchiului`). Coloana `text_search` conține textul, titlul și calea fișierului, deci un cuvânt din titlu sau din numele fișierului se potrivește lexical.
  - **2.2.2.** Între cuvintele unei expresii se aplică **ȘI** (în orice ordine și la orice distanță), între expresii **SAU**. Un fragment primește scor lexical numai dacă îndeplinește toate cuvintele a cel puțin unei expresii; o potrivire parțială are L = 0. Nu există interogare „laxă”.
  - **2.2.3.** Cuvintele care numesc o afecțiune sunt înlocuite cu un **SAU** între toate denumirile ei (nume canonic și sinonime), iar restul expresiei rămâne legat prin **ȘI**: `tratament pentru gripa la copii` → `tratame:* & copii:* & ((gripa:*) | (influen:*) | (season:* & flu:*) | …)`. Un sinonim nu lasă deci fragmentul să ignore celelalte cuvinte scrise de utilizator.
  - **2.2.4.** Textul utilizatorului nu ajunge niciodată ca sintaxă `tsquery`: stemurile conțin doar litere și cifre. Dacă mesajul nu are niciun cuvânt utilizabil, nu se face potrivire lexicală (L = 0 peste tot).
  - **2.2.5.** `ts_rank_cd` cu normalizarea 1 împarte la `1 + log(lungimea)`, deci un fragment scurt și concentrat pe subiect bate același cuvânt pomenit într-un capitol foarte lung. L = `ts_rank_cd / max(ts_rank_cd)` peste fragmentele potrivite.
- **2.3. Semnalul semantic (V).** Vectorul E5 al mesajului (prefix `query: `, mesajul așa cum a fost scris, normalizat L2), calculat cu modelul înregistrat în `sync_metadata` (eroare dacă indexul nu a fost încă sincronizat), încărcat offline din `data/model_cache` și păstrat în memorie între căutări. Fiind vectori de lungime 1, produsul scalar este chiar similaritatea cosinus, calculată **exact** pentru toate fragmentele (`-(embedding <#> vector)`); `V = clamp((cos − mediană) / (max − mediană), 0, 1)`. Rescalarea este necesară pentru că E5 comprimă similaritățile într-o bandă îngustă (mediana este ≈ 0,79–0,82, maximul ≈ 0,87–0,91) care se mută de la o interogare la alta, deci un prag fix nu ar funcționa.
- **2.4. Statistici relative la căutare.** Mediana, maximul cosinusului și cel mai bun scor lexical se calculează peste fragmentele categoriilor alese de pacient (filtrul se aplică înainte, și în partea lexicală). Procentul de relevanță arată cât de bun este un fragment **în această căutare** și nu se compară între căutări diferite.
- **2.5. Categoriile.** `Retriever.collect()` păstrează doar categoriile selectate care există încă în index; dacă nu rămâne niciuna sau sunt selectate toate, căutarea rulează fără filtru. O selecție goală este respinsă înainte de căutare, cu un mesaj către pacient.
- **2.6. Ordinea.** `ORDER BY score DESC, chunk_id ASC`: departajarea după `chunk_id` face ordinea deterministă.

### 3. Interogarea SQL unică — `search.rank()`

`rank(query, category_ids=None, max_chars=None)` execută **o singură interogare** care face toți pașii lângă date (`_RANK_SQL`):

- **3.1.** `pool`: fragmentele categoriilor selectate, cu P1 și P2 (operatorul `&&` pe array-urile indexate GIN) și cosinusul exact.
- **3.2.** `lex`: fragmentele care satisfac `tsquery` (indexul GIN `idx_chunks_text_search`), cu `ts_rank_cd`; gol când mesajul nu are cuvinte utilizabile.
- **3.3.** Statisticile căutării (`cosine_stats`, `lexical_stats`), apoi `score` pentru fiecare fragment; fragmentele cu scor 0 (nicio afecțiune, nicio potrivire lexicală, similaritate semantică sub mediană) nu intră în rezultat.
- **3.4.** **Bugetul de context:** suma cumulată a caracterelor de dovadă în ordinea scorului (`char_count` plus prefixul `Secțiune: <titlu>` + linie goală când titlul există, ca în `Retriever._context()`). Se păstrează doar prefixul care încape în `max_chars` (bugetul furnizorului AI, `ai.context_budget()`; fără `max_chars`, adică în scripturi și teste, nu se taie nimic), deci fragmentele de la coadă se elimină **întregi**, niciodată trunchiate; primul fragment care nu încape le elimină și pe toate cele de după el.
- **3.5.** Textul fragmentelor păstrate se citește printr-un `JOIN LATERAL` pe cheia primară, ca să fie atinse doar acele rânduri (un `JOIN` obișnuit face Postgres să parcurgă întreaga tabelă, text inclus, și era de 3–5 ori mai lent).
- **3.6.** Nu există nicio limită de candidați per semnal: nimic nu se elimină înainte de scor.
- **3.7.** Rezultatul fiecărui fragment: `chunk_id`, `score`, `condition_in_title` (P1), `condition_in_text` (P2), `lexical_score` (L, `None` dacă nu s-a potrivit), `semantic_score` (V), `semantic_similarity` (cosinusul brut), `found_by_lexical`, calea relativă și absolută a sursei, `line_start`, `line_end`, `heading`, `text`, `source_sha256`, `business_category`, `primary_medical_conditions`, `secondary_medical_conditions`.
- **3.8.** `warm_up()` rulează o căutare de probă (`gripa`) la pornirea aplicației (`web/main.py`, `lifespan`), ca modelul, dicționarul și indexul să fie încărcate înainte de prima căutare a unui pacient; un eșec aici produce doar un avertisment în log.
- **3.9.** `ai/search.py` poate fi rulat și ca script (`python -m medicina_naturista.ai.search "<întrebare>" [--json]`), afișând rezultatele cu componentele scorului.

### 4. Dovezile — `Retriever.collect()`

Fragmentele nu se unesc: fiecare este o secțiune întreagă (vezi `ai/fragmenter.py`) și rămâne dovadă separată, exact cum a fost indexată.

- **4.1.** Dovezile păstrează ordinea din `rank()`.
- **4.2.** Textul unei dovezi este textul fragmentului, prefixat cu `Secțiune: <cale titluri>` și o linie goală când există. Nu se citesc linii din jur din fișierul sursă.
- **4.3.** Fiecare dovadă este stocată sub cheia `C<chunk_id>`:

  | Câmp | Conținut |
  |---|---|
  | `source` | `documents/<cale>:<linie_start>-<linie_end>` |
  | `text` | contextul de la 4.2 |
  | `score` | scorul de la secțiunea 2 |
  | `relevance_percent` | `score / MAX_SCORE × 100` |
  | `lexical_score`, `semantic_score`, `semantic_similarity` | componentele scorului (informative) |
  | `condition_in_title`, `condition_in_text` | P1 și P2 |
  | `business_category`, `primary_medical_conditions`, `secondary_medical_conditions` | metadatele fragmentului |
  | `found_by_lexical` | adevărat dacă a fost găsit lexical |

- **4.4.** Se înregistrează în log numărul de fragmente, caracterele și sursele unice.
- **4.5.** Bugetul furnizorului este aplicat o singură dată, de `rank()`: pacientul vede exact fragmentele pe care le va primi AI-ul, iar cererea le trimite pe toate nemodificate (vezi [final-report-generation.md](final-report-generation.md)).
- **4.6.** Dacă nu rezultă nicio dovadă, pacientul primește mesajul „Nu am găsit fragmente relevante în sursele locale.”

### 5. Afișarea în interfață — `_fragments_message()` și `FragmentsPanel`

- **5.1.** Lista plată se sortează descrescător după `score`, indiferent de document.
- **5.2.** Pentru fiecare fragment: textul complet (spații normalizate) și o linie cu `Scor relevanță: N%` (rotunjit), `Scor semantic` (V, 2 zecimale), `Scor lexical` (L, 2 zecimale, doar când există), `Afecțiune în titlu` / `Afecțiune în text` (`conditionMatch`), eticheta `Găsire Lexicală` și calea documentului. Nu se afișează ID-uri sau intervale de linii.
- **5.3.** Filtrele din panou: scor minim (≥ 25 / 50 / 75 / 90 %), scor semantic minim (pe V, > 0,05 … 0,95), afecțiune (în titlu / în text / lipsește), găsire lexicală (da / nu) și document (după numele fișierului).
- **5.4.** Panoul arată și lista documentelor fragmentelor vizibile, plus un sumar cu numărul de fragmente, documente și caractere (cu „din N” când filtrele sunt active).
- **5.5.** Procentul este cel calculat de `Retriever.collect()`; UI-ul nu îl recalculează.

### 6. Parametri de configurare

| Variabilă | Implicit | Rol |
|---|---|---|
| `X_AI_MAX_CONTEXT_CHARS` / `DEEPSEEK_MAX_CONTEXT_CHARS` / `OLLAMA_MAX_CONTEXT_CHARS` / `HF_MAX_CONTEXT_CHARS` | 1.000.000 (HF: 120.000) | Bugetul textului dovezilor (caractere) pentru furnizorul activ; fragmente întregi eliminate de la coadă |
| `CONDITIONS_FILE` | `data/medical_conditions.txt` | Dicționarul de afecțiuni și sinonime |
| `MODEL_CACHE_DIR` | `data/model_cache` | Locul modelului de embeddings folosit pentru întrebare |
| `DATABASE_URL` | `postgresql://medicina:medicina@127.0.0.1:5432/medicina` | Conexiunea Postgres a indexului |

Constantele din cod (`ai/search.py`): `WEIGHT_PRIMARY = 8`, `WEIGHT_SECONDARY = 4`, `WEIGHT_LEXICAL = 2`, `WEIGHT_SEMANTIC = 1`, `MAX_SCORE = 15`. Din `ai/conditions.py`: `TYPO_CUTOFF = 0.9`, `FUZZY_CUTOFF = 0.84`, `MAX_MATCHED_CONDITIONS = 2`.

Postgres rulează în `docker-compose.yaml` cu `shared_buffers=512MB`: tabela `chunks` (~150 MB) depășește valoarea implicită de 128 MB, iar atunci prima căutare după o repornire citește de pe disc.

### Măsurarea calității

`scripts/evaluate_retrieval.py` rulează `rank()` pe interogările din `tests/eval/retrieval_queries.json` (etichetate prin reguli de cale și titlu, deci stabile la reindexare) și raportează Precision@10, MRR, nDCG@10, Recall@50, latența p50/p95 și `priority_order_violations` (fragmente cu afecțiunea în titlu aflate sub unul fără ea; 0 prin construcția scorului). Scriptul doar citește din baza de date. `--no-conditions` dezactivează recunoașterea afecțiunilor (fără P1/P2 și sinonime), pentru comparație; `--cases` alege alt fișier de interogări.

```bash
python scripts/evaluate_retrieval.py --output after.json
```

---

Fluxul complet al raportului este descris în [final-report-generation.md](final-report-generation.md), iar generarea indexului în [hybrid-index-generation.md](hybrid-index-generation.md).
