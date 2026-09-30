# Fluxul de căutare, unire și scoring al fragmentelor

**Intrare:** problema de sănătate din profilul sesiunii și indexul hibrid din Postgres.

**Ieșire:** inventarul de dovezi (`evidence`): fragmente unite, filtrate după relevanță și ordonate descrescător, gata de afișat pacientului și de trimis către AI.

Codul implicat: `ai/retrieval.py` (`Retriever.collect()`), `ai/search.py` (`rank()`), `ai/client.py` (`fit_evidence_to_context()`), `web/handlers.py` (afișarea).

## 1. Construirea interogării — `consultation_query()` și `Retriever.collect()`

Problema pacientului este căutată cu **o singură interogare**; scorul unui fragment nu se combină cu alte interogări.

- **1.1.** Interogarea este întreaga problemă de sănătate, cu spațiile normalizate: `durere de genunchi la efort`. Istoricul conversației nu este folosit, pentru a nu devia căutarea de la subiect. Dacă problema este goală, căutarea se oprește și returnează un inventar gol.
- **1.2.** Nu se mai construiește o a doua interogare din cuvintele sortate alfabetic: era căutată lexical ca frază exactă (care nu apare aproape niciodată așa în documente) și dubla costul unei căutări fără să aducă fragmente noi.
- **1.3.** **Dicționarul de afecțiuni** (`ai/conditions.py`, fișierul `data/medical_conditions.txt`, calea din `CONDITIONS_FILE`): o afecțiune pe linie, separată prin virgulă, cu numele canonic primul, urmat de sinonimele în română și engleză. `collect()` află ce afecțiune numește interogarea și o extinde cu celelalte denumiri ale ei (`expansions`), pe care `rank()` le folosește la semnalele lexical și de titlu. Potrivirea, în ordine:
  - **1.3.1.** interogarea este exact un termen din dicționar (fără diacritice și majuscule): `gout` găsește `Artrita gutoasa`;
  - **1.3.2.** interogarea este o scriere aproape identică a unui termen întreg (raport `difflib` ≥ 0,9), pentru greșeli de scriere: `artrita gutosa`;
  - **1.3.3.** termeni din dicționar apar ca cuvinte întregi în interogare; câștigă cei mai lungi: `tratament pentru adenom de prostata` găsește `Adenom de prostata`, nu `Adenom`;
  - **1.3.4.** ultima variantă: cel mai apropiat termen după scriere (raport ≥ 0,84).
  - **1.3.5.** Se folosesc cel mult 2 afecțiuni și 12 denumiri de extindere. Dacă nu se potrivește nimic sau fișierul lipsește, căutarea rulează exact ca înainte. Fișierul se reîncarcă automat când se modifică.
  - **1.3.6.** Extinderea nu modifică interogarea semantică (rămâne textul utilizatorului) și nu intră în interogarea laxă a semnalului lexical.
- **1.3.7.** Mesaj în chat: dacă interogarea se potrivește cu o afecțiune, `POST /api/messages` adaugă, imediat înaintea notificării „Caut rapid…”, un mesaj `✅ Am identificat afecțiunea: **Nume**. O caut și după denumirile: <toate sinonimele, în română și engleză>.` Dacă se potrivesc două afecțiuni, mesajul are câte o linie pentru fiecare. Dacă nu se potrivește nimic, nu apare niciun mesaj. Potrivirea este aceeași cu cea din `collect()` (`_condition_identified_message()` în `web/main.py`).

## 2. Ranking hibrid — `search.rank()`

Se rulează o dată pe interogare și întoarce doar **candidații** semnalelor, nu tot indexul.

### 2.1. Semnalul semantic

- **2.1.1.** Citește modelul și dimensiunea vectorilor din `sync_metadata` (Postgres) — scrise acolo de `build_hybrid_index.py` la fiecare sincronizare.
- **2.1.2.** Încarcă modelul FastEmbed (ONNX) din `data/model_cache`, offline, păstrat în cache pe proces.
- **2.1.3.** Generează vectorul E5 al interogării cu prefixul `query: ` și îl normalizează L2.
- **2.1.4.** Interoghează Postgres: `ORDER BY embedding <#> vector_interogare LIMIT SEARCH_CANDIDATE_LIMIT` (implicit 100), peste subsetul filtrat pe categorie. Se citesc doar id-urile; scanarea este exactă (fără HNSW/ivfflat), deci cei 100 sunt cu adevărat cei mai similari.
- **2.1.5.** Rangul semantic este poziția în acea listă, de la 1.

### 2.2. Semnalul lexical

- **2.2.1.** Din interogare se păstrează cuvintele relevante: fără cuvintele din `generic_query_words.txt` și fără cele sub 3 caractere (dacă nu rămâne niciunul, se păstrează toate). Fiecare devine o potrivire pe prefix `stem:*`, unde stemul este cuvântul fără ultimele 2 litere pentru cuvintele de cel puțin 6 caractere. Indexul folosește configurația `simple` (fără stemming românesc), iar prefixul acoperă flexiunile: `genunchi` găsește `genunchiului`, `gripa` găsește `gripei`. Nu e nevoie de reindexare.
- **2.2.2.** Interogarea **strictă** cere toate cuvintele relevante (`ȘI`, în orice ordine și la orice distanță). Segmentele separate prin virgulă se combină prin `SAU`. Textul utilizatorului nu ajunge niciodată ca sintaxă tsquery: stemurile conțin doar litere și cifre.
- **2.2.2a.** Fiecare denumire de extindere devine un grup suplimentar `ȘI`, legat prin `SAU` de interogarea strictă (și, prin ea, de semnalul de titlu).
- **2.2.3.** Dacă interogarea strictă găsește sub `MIN_STRICT_LEXICAL_HITS = 10` fragmente, se rulează și interogarea **laxă** (oricare dintre cuvinte); potrivirile stricte rămân primele, iar cele laxe se adaugă după ele.
- **2.2.4.** Ordonare prin `ts_rank_cd` cu normalizarea 1, cel mult `SEARCH_CANDIDATE_LIMIT` rezultate. Rangul lexical este poziția în listă.

### 2.3. Semnalul de titlu

- **2.3.1.** Fragmentele al căror titlu sau a căror cale de fișier se potrivește interogării stricte (`to_tsvector('simple', unaccent(titlu || ' ' || cale))`), ordonate după similaritatea semantică, cel mult `SEARCH_CANDIDATE_LIMIT`.
- **2.3.2.** Un fragment aflat sub un titlu care numește afecțiunea (`GUTĂ`, `Constipație`) este cel mai bun indiciu că e despre acea afecțiune; textul poate menționa cuvântul o singură dată, în treacăt. Se calculează la interogare, pe șiruri scurte (zeci de milisecunde), fără index suplimentar.

### 2.4. Fuziunea — Reciprocal Rank Fusion

- **2.4.1.** Constanta este `RRF_K = 60`.
- **2.4.2.** `hybrid_score` este suma termenilor `1 / (60 + rang)` pentru fiecare dintre cele trei semnale care a găsit fragmentul (semantic, lexical, titlu).
- **2.4.2.1.** Suma se înmulțește apoi cu greutatea `PRIORITY` a fragmentului (`PRIORITY_WEIGHT`: `1 → 1,0`, `3 → 0,7`, `10 → 0,2`). Prioritatea se stabilește **pentru fiecare căutare**, din afecțiunea numită de utilizator (`condition_names`: numele ei canonic și toate sinonimele din dicționar, plus `expansions`): 1 dacă un nume apare în `heading` (calea titlurilor; la documentele întregi, folderele și numele fișierului), 3 dacă apare în textul fragmentului, 10 altfel. Dacă afecțiunea nu e în dicționar, nu se folosesc sinonime: interogarea se ia ca atare și un fragment se potrivește când conține toate cuvintele ei importante (pe segmente separate prin virgulă). Prioritatea nu se stochează în DB. Toate greutățile sunt ≤ 1, deci `RRF_MAX_SCORE` rămâne plafonul.
- **2.4.3.** Se întoarce uniunea candidaților, cu textele aduse dintr-o singură interogare `WHERE chunk_id = ANY(...)`. Un fragment găsit de un singur semnal primește doar termenul lui, dar `semantic_similarity` este raportată oricum.
- **2.4.4.** Rezultatul fiecărui fragment conține: `chunk_id`, `hybrid_score`, `semantic_similarity`, `lexical_rank`, `found_by_lexical`, `found_by_heading`, calea sursei, `line_start`, `line_end`, `heading`, `text`, `source_sha256`, `priority` (calculată la căutare), `business_category`, `primary_medical_conditions`, `secondary_medical_conditions`.
- **2.4.5.** Lista se sortează descrescător după `hybrid_score`.

### 2.5. Scorul maxim

- **2.5.1.** `RRF_MAX_SCORE = 3 / (RRF_K + 1) = 3/61 ≈ 0,0492`: un fragment clasat pe primul loc de toate cele trei semnale.
- **2.5.2.** Este plafonul fix pe baza căruia se calculează procentul de relevanță; nicio altă componentă nu duplică constanta.

## 3. Scorul unui fragment

- **3.1.** Scorul unui fragment (`score`) este chiar `hybrid_score` din secțiunea 2: suma celor trei termeni RRF (semantic, lexical, titlu/cale) înmulțită cu greutatea priorității. Nu se adună și nu se mediază cu nicio altă interogare, pentru că există una singură.
- **3.2.** `found_by_lexical` arată dacă interogarea a găsit fragmentul lexical.

## 4. Scorul de relevanță

- **4.1.** Formula:

  ```text
  relevance_percent = hybrid_score / RRF_MAX_SCORE × 100
  ```

  `RRF_MAX_SCORE` este plafonul fix al scorului, deci procentul este între 0 și 100.
- **4.2.** Nu există un prag minim de relevanță: **fiecare** candidat întors de `rank()` (cel mult `SEARCH_CANDIDATE_LIMIT` per semnal) devine dovadă. Singurul loc unde un fragment poate fi eliminat mai târziu este bugetul `MAX_CONTEXT_CHARS`, aplicat o singură dată de `fit_evidence_to_context()` (vezi [final-report-generation.md](final-report-generation.md)), nu aici.
- **4.3.** `relevance_percent` rămâne calculat și afișat (scorul din panoul UI), doar că nu mai e folosit ca regulă de selecție — e pur informativ pentru pacient.

## 5. Dovezile — `Retriever.collect()`

Fragmentele nu se mai unesc: fiecare este o secțiune întreagă (vezi `ai/fragmenter.py`) și rămâne dovadă separată, exact cum a fost indexată.

- **5.1.** Dovezile se ordonează descrescător după suma de scoruri.
- **5.2.** Textul unei dovezi este textul fragmentului, prefixat cu `Secțiune: <cale titluri>` când există. Nu se citesc linii din jur din fișierul sursă.
- **5.3.** Fiecare dovadă este stocată sub cheia `C<chunk_id>` cu câmpurile:

  | Câmp | Conținut |
  |---|---|
  | `source` | `documents/<cale>:<linie_start>-<linie_end>` |
  | `text` | contextul de la 5.2 |
  | `score` | `suma_scorurilor / N` |
  | `relevance_percent` | procentul fragmentului |
  | `priority`, `business_category`, `primary_medical_conditions`, `secondary_medical_conditions` | metadatele fragmentului |
  | `found_by_lexical` | adevărat dacă a fost găsit lexical |

- **5.4.** Se înregistrează în log numărul de interogări, candidați, dovezi, caractere și surse unice.

## 7. Limitarea la bugetul de context — `fit_evidence_to_context()`

Se apelează în `on_find_fragments()`, imediat după `collect()`.

- **7.1.** Ordonează dovezile descrescător după `score`.
- **7.2.** Calculează lungimea serializată JSON a fiecărei intrări `{id, source, text}`, inclusiv separatorii `, ` și parantezele listei.
- **7.3.** Păstrează cel mai bine punctat **prefix** care încape în `MAX_CONTEXT_CHARS` (implicit 2.400.000); nicio intrare nu este trunchiată, cele de la coadă sunt eliminate integral.
- **7.4.** Dacă s-au eliminat dovezi, se emite un avertisment cu numărul lor.
- **7.5.** Este singurul loc unde se aplică limita: pacientul vede exact fragmentele pe care le va primi AI-ul, iar cererea le trimite pe toate nemodificate.

## 8. Afișarea în interfață — `_fragments_panel_html()`

- **8.1.** Sortează lista plată descrescător după `score`, indiferent de document sau interogare.
- **8.2.** Pentru fiecare fragment afișează textul complet (spații normalizate) și o linie cu `Scor relevanță: <relevance_percent rotunjit>%`, eticheta `Găsire Lexicală` dacă `found_by_lexical`, și numele documentului.
- **8.3.** Nu afișează ID-uri, intervale de linii sau alte metadate interne.
- **8.4.** Procentul este cel calculat de `Retriever.collect()`; UI-ul nu îl recalculează.
- **8.5.** Eticheta lexicală poate fi extinsă cu alte semnale selective prin adăugarea unei perechi în `_MATCH_TYPE_SIGNALS`. Nu există etichetă semantică, deoarece toate fragmentele sunt ordonate semantic.

## 9. Parametri de configurare

| Variabilă | Implicit | Rol |
|---|---|---|
| `SEARCH_CANDIDATE_LIMIT` | 100 | Candidați per semnal (semantic, lexical, titlu) |
| `CONDITIONS_FILE` | `data/medical_conditions.txt` | Dicționarul de afecțiuni și sinonime |
| `MAX_CONTEXT_CHARS` | 2.400.000 | Bugetul serializat al dovezilor |
| `DATABASE_URL` | `postgresql://medicina:medicina@127.0.0.1:5432/medicina` | Conexiunea Postgres a indexului |
| `DOCUMENTS_DIR` | `data/documents` | Documentele sursă pentru extinderea contextului |

Constantele din cod: `RRF_K = 60`, `MIN_STRICT_LEXICAL_HITS = 10`, lungimea minimă a unui cuvânt relevant 4.

## Rezultatul final

```text
Problema de sănătate
    -> o singură interogare (problema întreagă)
    -> dicționar de afecțiuni: dacă numește o afecțiune, o extinde cu sinonimele ei
    -> semnal semantic (E5, top-100 exact) + lexical (prefixe, ȘI apoi SAU) + titlu/cale
    -> hybrid_score = RRF pe cele trei rangări, doar pentru uniunea candidaților
    -> relevance_percent = scor / RRF_MAX_SCORE × 100 (afișat, dar nu filtrează)
    -> dovadă = fragmentul însuși, cu scorul și procentul lui
    -> ordonare descrescătoare și limitare la MAX_CONTEXT_CHARS
    -> panou cu fragmente pentru pacient și, la cerere, payload către AI
```

Fluxul complet al raportului este descris în [final-report-generation.md](final-report-generation.md), iar generarea indexului în [hybrid-index-generation.md](hybrid-index-generation.md).

## Măsurarea calității

`scripts/evaluate_retrieval.py` rulează `rank()` pe interogările din `tests/eval/retrieval_queries.json` (etichetate prin reguli de cale și titlu, deci stabile la reindexare) și raportează Precision@10, MRR, nDCG@10, Recall@50 și latența p50/p95. Scriptul doar citește din baza de date. Rulează-l înainte și după orice schimbare de scoring; `--no-conditions` dezactivează extinderea cu dicționarul, pentru comparație.

```bash
python scripts/evaluate_retrieval.py --output before.json
```
