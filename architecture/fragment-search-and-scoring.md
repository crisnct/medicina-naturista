# Fluxul de căutare și scoring al fragmentelor

**Intrare:** problema de sănătate din profilul sesiunii și indexul din Postgres.

**Ieșire:** inventarul de dovezi (`evidence`): fragmente ordonate descrescător după scor, limitate la bugetul de context al furnizorului AI (`max_chars`), gata de afișat pacientului și de trimis către AI.

Documentul are două părți: **[Partea I — Rezumat](#partea-i--rezumat)** (cele 6 etape pe scurt) și **[Partea II — Detalii](#partea-ii--detalii)** (aceleași 6 etape, pas cu pas).

----------------------------------------------------------------------------------------------------

## Partea I — Rezumat

1. **Recunoașterea afecțiunii** (`resolve_query()`) — mesajul se împarte la virgulă, iar în fiecare parte se caută afecțiunile din `data/medical_conditions.txt` (cu sinonime și toleranță la greșeli de scriere). Pacientul vede în chat ce afecțiune s-a identificat.
2. **Scorul** — pacientul alege din panoul „Căutare avansată” ce semnale intră în scor: **A** (afecțiuni), **B** (lexical), **C** (semantic). Implicit sunt toate trei: `score = 4·P1 + 2·P2 + L + V` (maximum 8):
   - **P1** — afecțiunea este în titlul fragmentului (semnalul A);
   - **P2** — afecțiunea este în textul fragmentului (semnalul A);
   - **L** — fracțiunea de expresii (separate prin virgulă) pe care fragmentul le conține (căutare lexicală, semnalul B);
   - **V** — fragmentul are un sens apropiat de întrebare (căutare semantică, semnalul C).
   Pentru celelalte combinații formula se schimbă (tabelul de la 2) și semnalele nebifate nu se calculează.
3. **Căutarea** (`rank()`) — o singură interogare SQL notează toate fragmentele din sursele alese; se păstrează cele mai bune, cât încap în limita de text a furnizorului AI (fragmente întregi, tăiate de la coadă).
4. **Dovezile** (`Retriever.collect()`) — fiecare fragment păstrat devine o dovadă `C<id>`, cu sursa, scorul și procentul de relevanță (față de maximul combinației de semnale alese).
5. **Afișarea** (`FragmentsPanel`) — pacientul vede fragmentele ordonate după scor și le poate filtra (scor, afecțiune, găsire lexicală, document); componentele și filtrele semnalelor nebifate sunt ascunse.
6. **Setări** — limita de text per furnizor (`*_MAX_CONTEXT_CHARS`), dicționarul (`CONDITIONS_FILE`), modelul (`MODEL_CACHE_DIR`) și baza de date (`DATABASE_URL`).

```text
problema pacientului → afecțiuni recunoscute → score = Σ greutate·semnal, pe semnalele alese (implicit 4·P1 + 2·P2 + L + V)
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
- **1.5.** Mesaj în chat: `POST /api/messages` adaugă, înaintea notificării „🔍 Caut rapid în cele N documente…”, un mesaj `✅ Am identificat afecțiunea: **Nume**. O caut și după denumirile: <sinonimele>.` (`_condition_identified_message()` în `web/main.py`), în funcție de semnalele alese (secțiunea 2.7):
  - **cu A bifat** apare câte o linie pentru fiecare afecțiune recunoscută în orice expresie;
  - partea „O caut și după denumirile: …” apare **doar cu B bifat** și **doar** pentru afecțiunile care sunt o expresie întreagă (2.2.3), pentru că numai acolo căutarea lexicală folosește sinonimele; lipsește și când afecțiunea nu are sinonime;
  - **cu B fără A** mesajul apare doar pentru acele afecțiuni (nume + sinonime); **fără A și fără B** (doar C) nu apare niciun mesaj;
  - dacă nu se recunoaște nimic, nu apare niciun mesaj. Căutarea propriu-zisă rulează apoi separat, prin `POST /api/search`.
- **1.6.** Pentru fiecare expresie se reține și dacă ea **este** afecțiunea (`QuerySegment.whole_condition`): adevărat doar la potrivirea 1.2.1 (termen exact) și 1.2.2 (scriere aproape identică); fals la 1.2.3 și 1.2.4. Doar o astfel de expresie primește sinonimele în căutarea lexicală (2.2.3).

### 2. Formula scorului

Pacientul alege, în panoul „Căutare avansată”, ce **tipuri de căutare** intră în scor (cel puțin unul; implicit toate trei, alegerea se păstrează în `localStorage`, cheia `naturist.searchSignals`). Alegerea se trimite cu fiecare mesaj (`signals` în `POST /api/messages`) și se aplică acelei căutări; serverul respinge cu 422 o cerere fără niciun semnal.

| Bifat | Formula | Scor maxim | `relevance_percent` |
|---|---|---|---|
| **A**+**B**+**C** (implicit) | `4·P1 + 2·P2 + L + V` | 8 | `score / 8 × 100` |
| A+B | `3·P1 + 2·P2 + L` | 6 | `score / 6 × 100` |
| A+C | `3·P1 + 2·P2 + V` | 6 | `score / 6 × 100` |
| B+C | `L + V` | 2 | `score / 2 × 100` |
| A | `2·P1 + P2` | 3 | `score / 3 × 100` |
| B | `L` | 1 | `score × 100` |
| C | `V` | 1 | `score × 100` |

**A** = căutare afecțiuni (P1, P2), **B** = căutare lexicală (L), **C** = căutare semantică (V). Greutățile sunt un tabel explicit în `ai/search.py` (`_WEIGHTS`, citit prin `weights(signals)` și `max_score(signals)`); procentul se calculează **o singură dată**, în `Retriever.collect()`, cu maximul combinației alese, iar UI-ul nu îl recalculează.

| Termen | Tip | Definiție |
|---|---|---|
| **P1** | {0, 1} | 1 dacă `primary_medical_conditions` (afecțiunile din **titlul** fragmentului) conține una dintre afecțiunile din mesaj |
| **P2** | {0, 1} | 1 dacă `secondary_medical_conditions` (afecțiunile din **textul** fragmentului) conține una dintre ele |
| **L** | {0, 1/N, …, 1} | fracțiunea din cele `N` expresii ale mesajului pe care fragmentul le conține (2.2) |
| **V** | [0, 1] | similaritatea semantică, rescalată între mediana și maximul căutării; 0 sub mediană sau când toate similaritățile sunt egale |

- **2.1. Prioritățile.** Greutățile păstrează ordinea priorităților: cu toate semnalele, P1 valorează cât toate semnalele inferioare la maximum (4 = 2 + 1 + 1), iar P2 cât L plus V (2 = 1 + 1); fără L sau fără V, P1 valorează cât P2 plus ce a rămas (3 = 2 + 1); doar cu A, afecțiunea din titlu bate pe cea din text (2 > 1). Egalitatea apare doar când fragmentul de rang inferior are potrivire perfectă la tot ce urmează; în acest caz, ca la orice egalitate, ordinea o decide `chunk_id` (2.6), deci `priority_order_violations` din evaluare nu mai este 0 prin construcție, ci rămâne foarte mic. L și V cântăresc la fel: o potrivire semantică foarte bună poate depăși una lexicală slabă și invers. Inegalitățile sunt păzite de teste (`tests/unit/ai/test_search.py`, `WeightTests`).
- **2.2. Semnalul lexical (L).** `ts_rank_cd` nu mai este folosit. L este fracțiunea de **expresii** regăsite în fragment, în toate combinațiile în care B este bifat.
  - **2.2.1.** Mesajul se împarte la virgulă în expresii; cele goale se ignoră, iar cele identice după normalizare (`gripa, Gripa`) se numără o singură dată. Fie `N` numărul de expresii rămase (`lexical_queries()` întoarce câte o interogare `tsquery` pe expresie).
  - **2.2.2.** Fiecare expresie devine o **frază**: toate cuvintele ei (cel mult 32), **inclusiv** cele generice și cele scurte (`de`, `la`, `pentru`, `ce`, `sa` …), în ordinea scrisă și alăturate (operatorul `<->` din `tsquery`). Fiecare cuvânt se potrivește cu flexiuni, prin prefix: stemul este cuvântul fără ultimele 2 litere pentru cuvintele de cel puțin 6 caractere (minimum 4 litere păstrate); cuvintele sub 3 litere (`de`, `la`, `cu`) se potrivesc exact, ca `de` să nu prindă și „deja” sau „despre”. Indexul folosește configurația `simple` (fără stemming românesc) și `unaccent`, deci diacriticele și majusculele se ignoră. Coloana `text_search` conține textul, titlul și calea fișierului. Exemplu: `dureri de picioare` → `(dure:* <-> de <-> picioa:*)`.
  - **2.2.3.** Excepția: dacă expresia **este** o afecțiune (`whole_condition`: termen exact din dicționar sau scriere aproape identică, 1.2.1–1.2.2), ea se caută sub **toate denumirile** afecțiunii — nume canonic și sinonime — ca un **SAU** între frazele lor: `gripa` → `((gripa:*) | (influen:*) | (season:* <-> flu:*) | …)`. Altfel (`gripa la copii`) expresia se caută **ca atare**, ca frază exactă, fără sinonime și fără căutarea unei afecțiuni în interiorul ei; recunoașterea din 1.2 rămâne neschimbată pentru P1/P2.
  - **2.2.4.** `L_brut(f)` = câte dintre cele `N` interogări se potrivesc fragmentului `f`; o expresie contează **o singură dată**, oricâte denumiri ale ei sau apariții are fragmentul. `L = L_brut / N`, față de numărul de expresii, **nu** față de cel mai bun fragment din căutare și fără normalizare după lungimea fragmentului: `gripa, raceala, guta` cu un fragment care are gripa și guta dă L = 2/3 chiar dacă niciun fragment nu le are pe toate trei. Cu o singură expresie L este 0 sau 1, deci cu doar B toate fragmentele găsite au 100%, iar ordinea între ele o dă `chunk_id`. Expresii echivalente (`gripa, influenza`) rămân două expresii distincte.
  - **2.2.5.** Textul utilizatorului nu ajunge niciodată ca sintaxă `tsquery`: operanzii conțin doar litere și cifre. Dacă mesajul nu are niciun cuvânt utilizabil, nu se face potrivire lexicală.
  - **2.2.6.** Consecință asumată: o întrebare scrisă ca propoziție (`ce sa iau pentru gripa`) caută fraza exactă și va găsi rar ceva, deci L va fi des 0; în schimb o expresie scurtă sau o afecțiune se regăsește exact. Pozițiile din `tsvector` sunt limitate la 16.383, deci o frază aflată după acea poziție într-un fragment foarte lung nu se potrivește.
- **2.3. Semnalul semantic (V).** Vectorul Qwen3 al mesajului (instrucțiunea din profilul modelului, `Instruct: … Query:`, urmată de mesajul așa cum a fost scris; normalizat L2), calculat pe CPU cu modelul înregistrat în `sync_metadata` (eroare dacă indexul nu a fost încă sincronizat), încărcat offline din `data/model_cache` și păstrat în memorie între căutări. Fiind vectori de lungime 1, produsul scalar este chiar similaritatea cosinus, calculată **exact** pentru toate fragmentele (`-(embedding <#> vector)`); `V = clamp((cos − mediană) / (max − mediană), 0, 1)`. Rescalarea este necesară pentru că similaritățile se adună într-o bandă îngustă, care se mută de la o interogare la alta, deci un prag fix nu ar funcționa. Cu doar C, ordinea este ordinea cosinusului (peste mediană).
- **2.4. Statistici relative la căutare.** Mediana și maximul cosinusului se calculează peste fragmentele categoriilor alese de pacient (filtrul se aplică înainte, și în partea lexicală). Procentul de relevanță arată cât de bun este un fragment **în această căutare** și nu se compară între căutări diferite sau cu alte combinații de semnale.
- **2.5. Categoriile.** `Retriever.collect()` păstrează doar categoriile selectate care există încă în index; dacă nu rămâne niciuna sau sunt selectate toate, căutarea rulează fără filtru. O selecție goală este respinsă înainte de căutare, cu un mesaj către pacient.
- **2.6. Ordinea.** `ORDER BY score DESC, chunk_id ASC`: la scor egal decide doar `chunk_id` (ordine deterministă, dar arbitrară), în toate combinațiile; nu există departajare ascunsă după un semnal nebifat.
- **2.7. Semnalele nebifate nu se calculează.** Fără C nu se calculează embeddingul întrebării, nu se citesc vectorii și nu se cere nici metadatele modelului (căutare mai rapidă); fără B nu rulează partea lexicală; fără A, P1 și P2 sunt constante 0 în SQL. Câmpurile semnalelor nebifate din rezultat (`condition_in_title`, `condition_in_text`, `lexical_score`, `semantic_score`, `semantic_similarity`) sunt `None`. Fragmentele cu scor 0 sunt excluse în toate combinațiile: doar A fără nicio afecțiune recunoscută nu găsește nimic (mesajul generic „Nu am găsit fragmente relevante în sursele locale.”), iar doar C păstrează doar fragmentele cu cosinusul peste mediană.

### 3. Interogarea SQL unică — `search.rank()`

`rank(query, category_ids=None, max_chars=None, signals=ALL_SIGNALS)` execută **o singură interogare** care face toți pașii lângă date (`_RANK_SQL`); părțile semnalelor nebifate sunt scrise ca CTE-uri goale sau constante, deci nu costă nimic:

- **3.1.** `pool`: fragmentele categoriilor selectate, cu P1 și P2 (operatorul `&&` pe array-urile indexate GIN; constante 0 fără A) și cosinusul exact (fără C nu apare `embedding <#> …`).
- **3.2.** `lq` / `lex`: cele `N` expresii ca `tsquery` (`lq`, evaluate o singură dată) și, pentru fragmentele care satisfac **SAU**-ul lor (indexul GIN `idx_chunks_text_search`), câte expresii conține fiecare (`hits`); `L = hits / N`. Interogările se trimit ca array, deci textul SQL nu crește cu numărul de expresii. Gol fără B sau când mesajul nu are cuvinte utilizabile.
- **3.3.** Statisticile căutării (`cosine_stats`, doar cu C), apoi `score` pentru fiecare fragment; fragmentele cu scor 0 (nicio afecțiune, nicio potrivire lexicală, similaritate semantică sub mediană) nu intră în rezultat.
- **3.4.** **Bugetul de context:** suma cumulată a caracterelor de dovadă în ordinea scorului (`char_count` plus prefixul `Secțiune: <titlu>` + linie goală când titlul există, ca în `Retriever._context()`). Se păstrează doar prefixul care încape în `max_chars` (bugetul furnizorului AI, `ai.context_budget()`; fără `max_chars`, adică în scripturi și teste, nu se taie nimic), deci fragmentele de la coadă se elimină **întregi**, niciodată trunchiate; primul fragment care nu încape le elimină și pe toate cele de după el.
- **3.5.** Textul fragmentelor păstrate se citește printr-un `JOIN LATERAL` pe cheia primară, ca să fie atinse doar acele rânduri (un `JOIN` obișnuit face Postgres să parcurgă întreaga tabelă, text inclus, și era de 3–5 ori mai lent).
- **3.6.** Nu există nicio limită de candidați per semnal: nimic nu se elimină înainte de scor.
- **3.7.** Rezultatul fiecărui fragment: `chunk_id`, `score`, `condition_in_title` (P1), `condition_in_text` (P2), `lexical_score` (L, `None` dacă nu s-a potrivit), `semantic_score` (V), `semantic_similarity` (cosinusul brut), `found_by_lexical`, calea relativă și absolută a sursei, `line_start`, `line_end`, `heading`, `text`, `source_sha256`, `business_category`, `primary_medical_conditions`, `secondary_medical_conditions` și `signals` (semnalele cu care s-a calculat scorul). Câmpurile unui semnal nebifat sunt `None`.
- **3.8.** `warm_up()` rulează o căutare de probă (`gripa`, cu toate semnalele, deci încarcă și modelul) la pornirea aplicației (`web/main.py`, `lifespan`), ca modelul, dicționarul și indexul să fie încărcate înainte de prima căutare a unui pacient; un eșec aici produce doar un avertisment în log.
- **3.9.** `ai/search.py` poate fi rulat și ca script (`python -m backend.ai.search "<întrebare>" [--json] [--signals ABC]`), afișând rezultatele cu componentele scorului; `--signals` ia orice combinație de `A`, `B`, `C` (implicit toate).

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
  | `relevance_percent` | `score / max_score(signals) × 100`, cu maximul combinației alese |
  | `lexical_score`, `semantic_score`, `semantic_similarity` | componentele scorului (informative) |
  | `condition_in_title`, `condition_in_text` | P1 și P2 |
  | `business_category`, `primary_medical_conditions`, `secondary_medical_conditions` | metadatele fragmentului |
  | `found_by_lexical` | adevărat dacă a fost găsit lexical |

- **4.4.** Semnalele căutării vin din `session.search_signals` (setate de `POST /api/messages`; implicit toate) și se înregistrează în log (`signals=ABC`) împreună cu numărul de fragmente, caracterele și sursele unice.
- **4.5.** Bugetul furnizorului este aplicat o singură dată, de `rank()`: pacientul vede exact fragmentele pe care le va primi AI-ul, iar cererea le trimite pe toate nemodificate (vezi [final-report-generation.md](final-report-generation.md)).
- **4.6.** Dacă nu rezultă nicio dovadă, pacientul primește mesajul „Nu am găsit fragmente relevante în sursele locale.”

### 5. Afișarea în interfață — `_fragments_message()` și `FragmentsPanel`

- **5.1.** Lista plată se sortează descrescător după `score`, indiferent de document.
- **5.2.** Pentru fiecare fragment: textul complet (spații normalizate) și o linie cu `Scor relevanță: N%` (rotunjit), `Scor semantic` (V, 2 zecimale), `Scor lexical` (L, 2 zecimale, doar când există), `Afecțiune în titlu` / `Afecțiune în text` (`conditionMatch`), eticheta `Găsire Lexicală` și calea documentului. Nu se afișează ID-uri sau intervale de linii. Componentele semnalelor nebifate lipsesc.
- **5.3.** Filtrele din panou: scor minim (≥ 25 / 50 / 75 / 90 %), scor semantic minim (pe V, > 0,05 … 0,95), afecțiune (în titlu / în text / lipsește), găsire lexicală (da / nu) și document (după numele fișierului). Mesajul `fragments` poartă `signals` (semnalele căutării lui), iar panoul ascunde „Scor semantic” și filtrul lui fără C, „Scor lexical”, eticheta „Găsire Lexicală” și filtrul „Găsire lexicală” fără B, „Afecțiune în titlu / în text” și filtrul de afecțiune fără A; „Scor relevanță” și filtrul de document rămân mereu. Un mesaj fără `signals` (mai vechi) se tratează ca A+B+C, iar fragmentele deja afișate își păstrează scorul chiar dacă pacientul schimbă ulterior alegerea.
- **5.4.** Panoul arată și lista documentelor fragmentelor vizibile, plus un sumar cu numărul de fragmente, documente și caractere (cu „din N” când filtrele sunt active).
- **5.5.** Procentul este cel calculat de `Retriever.collect()`; UI-ul nu îl recalculează.

### 6. Parametri de configurare

| Variabilă | Implicit | Rol |
|---|---|---|
| `X_AI_MAX_CONTEXT_CHARS` / `DEEPSEEK_MAX_CONTEXT_CHARS` / `OLLAMA_MAX_CONTEXT_CHARS` / `HF_MAX_CONTEXT_CHARS` | 1.000.000 (HF: 120.000) | Bugetul textului dovezilor (caractere) pentru furnizorul activ; fragmente întregi eliminate de la coadă |
| `CONDITIONS_FILE` | `data/medical_conditions.txt` | Dicționarul de afecțiuni și sinonime |
| `MODEL_CACHE_DIR` | `data/model_cache` | Locul modelului de embeddings folosit pentru întrebare |
| `DATABASE_URL` | `postgresql://medicina:medicina@127.0.0.1:5432/medicina` | Conexiunea Postgres a indexului |

Comutatorul de experiment `SEARCH_SEMANTIC_ONLY` a fost eliminat: doar C bifat face același lucru. Constantele din cod (`ai/search.py`): tabelul `_WEIGHTS` cu greutățile fiecărei combinații (secțiunea 2), `ALL_SIGNALS` (toate semnalele), `PREFIX_MATCH_MIN_CHARS = 3`. Din `ai/conditions.py`: `TYPO_CUTOFF = 0.9`, `FUZZY_CUTOFF = 0.84`, `MAX_MATCHED_CONDITIONS = 2`.

Postgres rulează în `docker-compose.yaml` cu `shared_buffers=512MB`: tabela `chunks` (~150 MB) depășește valoarea implicită de 128 MB, iar atunci prima căutare după o repornire citește de pe disc.

### Măsurarea calității

`src/scripts/evaluate_retrieval.py` rulează `rank()` pe interogările din `src/tests/eval/retrieval_queries.json` (etichetate prin reguli de cale și titlu, deci stabile la reindexare) și raportează Precision@10, MRR, nDCG@10, Recall@50, latența p50/p95 și `priority_order_violations` (fragmente cu afecțiunea în titlu aflate sub unul fără ea; 0 sau foarte aproape de 0, vezi 2.1; raportat doar când A este bifat). Scriptul doar citește din baza de date. `--signals ABC|AB|AC|BC|A|B|C` (implicit ABC) alege semnalele scorului, pentru a compara combinațiile; `--no-conditions` dezactivează recunoașterea afecțiunilor (fără P1/P2 și sinonime), pentru comparație; `--cases` alege alt fișier de interogări.

```bash
python src/scripts/evaluate_retrieval.py --output after.json
```

---

Fluxul complet al raportului este descris în [final-report-generation.md](final-report-generation.md), iar generarea indexului în [hybrid-index-generation.md](hybrid-index-generation.md).
