# Fluxul de căutare, unire și scoring al fragmentelor

**Intrare:** problema de sănătate din profilul sesiunii și indexul hibrid din `data/hybrid_index`.

**Ieșire:** inventarul de dovezi (`evidence`): fragmente unite, filtrate după relevanță și ordonate descrescător, gata de afișat pacientului și de trimis către AI.

Codul implicat: `ai/retrieval.py` (`Retriever.collect()`), `ai/search.py` (`rank()`), `ai/client.py` (`fit_evidence_to_context()`), `web/handlers.py` (afișarea).

## 1. Construirea interogărilor — `consultation_queries()` și `Retriever.collect()`

Problema pacientului este căutată cu **una sau două formulări**. Fiecare formulare se numește interogare, iar numărul lor final se notează `N` (1 sau 2).

**Exemplu** folosit în această secțiune: `durere de genunchi la efort`.

- **1.1.** **Interogarea de bază** este întreaga problemă de sănătate, cu spațiile normalizate: `durere de genunchi la efort`. Istoricul conversației nu este folosit, pentru a nu devia căutarea de la subiect. Dacă problema este goală, căutarea se oprește și returnează un inventar gol.
- **1.2.** **Cuvintele relevante** se extrag din problemă. Un cuvânt este relevant dacă are minimum 4 caractere și nu apare în `generic_query_words.txt`. Compararea se face fără diacritice și fără diferențe de majuscule. În exemplu: `durere`, `genunchi`, `efort`; cuvintele „de” și „la” sunt prea scurte.
- **1.3.** Dacă nu există niciun cuvânt relevant, se folosește doar interogarea de bază: `N = 1`.
- **1.4.** Dacă există, se construiește o **a doua interogare** din cuvintele relevante, sortate alfabetic și unite printr-un spațiu: `durere efort genunchi`. Ea elimină cuvintele de umplutură, astfel încât modelul semantic să se concentreze pe termenii importanți.
- **1.5.** **Deduplicarea:** `collect()` inserează în față textul problemei și interogarea din 1.4, deci lista devine `[problemă, cuvinte sortate, problemă]`. Interogările se compară după forma normalizată (spații și majuscule), iar duplicatele dispar.

| Situația | Interogări rezultate | `N` |
|---|---|---|
| Problemă cu mai multe cuvinte relevante | problema întreagă + cuvintele sortate | 2 |
| Un singur cuvânt relevant (ex. `migrene`) | cele două coincid, rămâne una | 1 |
| Niciun cuvânt relevant | doar problema întreagă | 1 |

- **1.6.** **Ce se întâmplă cu ele:** fiecare interogare trece prin `rank()` (secțiunea 2), deci prin ambele semnale, semantic și lexical. Interogarea cu cuvinte sortate este căutată lexical ca frază exactă, care aproape niciodată nu apare așa în documente. În practică ea contribuie mai ales prin rangul semantic.
- **1.7.** Scorurile fiecărui fragment din cele `N` interogări se adună, apoi se împart la `N` (secțiunile 3 și 4). Astfel scorul rămâne comparabil, indiferent dacă s-a folosit una sau două interogări.

## 2. Ranking hibrid pentru o interogare — `search.rank()`

Se rulează pentru fiecare dintre cele `N` interogări și întoarce **toate** fragmentele indexului, nu doar un top.

### 2.1. Semnalul semantic

- **2.1.1.** Citește modelul și dimensiunea vectorilor din `manifest.json` și încarcă `embeddings.npy` prin mapare în memorie; validează forma `(fragmente, dimensiune)`.
- **2.1.2.** Încarcă modelul FastEmbed (ONNX) din `data/model_cache`, offline, păstrat în cache pe proces.
- **2.1.3.** Generează vectorul E5 al interogării cu prefixul `query: ` și îl normalizează L2.
- **2.1.4.** Calculează similaritatea (produs scalar) față de toți vectorii documentelor.
- **2.1.5.** Ordonează toate fragmentele descrescător după similaritate. Fiecare primește un **rang semantic** de la 1 (cel mai similar) la `F` (cel mai puțin similar); nu există limită top-N.

### 2.2. Semnalul lexical

- **2.2.1.** Convertește interogarea într-o expresie SQLite FTS5. Un text fără virgulă devine o **frază exactă** (cuvinte adiacente, în ordine, maximum 32). Segmentele separate prin virgulă devin fraze exacte combinate cu `OR`.
- **2.2.2.** Nu există revenire la potrivirea pe cuvinte individuale: dacă fraza nu apare identic, fragmentul nu primește niciun scor lexical.
- **2.2.3.** Preia din `chunks_fts` toate fragmentele potrivite, ordonate prin BM25, fără `LIMIT`. Ele primesc un **rang lexical** de la 1 în sus; celelalte nu au rang lexical.

### 2.3. Fuziunea — Reciprocal Rank Fusion

- **2.3.1.** Constanta este `RRF_K = 60`.
- **2.3.2.** Pentru fiecare fragment: `hybrid_score = 1 / (60 + rang_semantic)`.
- **2.3.3.** Dacă are rang lexical, se adaugă `1 / (60 + rang_lexical)`.
- **2.3.4.** Ambele semnale rulează întotdeauna; nu există comutator care să dezactiveze unul dintre ele.
- **2.3.5.** Rezultatul fiecărui fragment conține: `chunk_id`, `hybrid_score`, `semantic_similarity`, `lexical_rank`, `found_by_lexical`, calea sursei, `line_start`, `line_end`, `heading`, `text`, `source_sha256`.
- **2.3.6.** Lista se sortează descrescător după `hybrid_score`.

### 2.4. Scorul maxim

- **2.4.1.** `RRF_MAX_SCORE = 2 / (RRF_K + 1) = 2/61 ≈ 0,0328`: un fragment clasat pe primul loc de ambele semnale.
- **2.4.2.** Este plafonul fix pe baza căruia se calculează procentul de relevanță; nicio altă componentă nu duplică constanta.

## 3. Agregarea scorurilor între interogări — `Retriever.collect()`

- **3.1.** Pentru fiecare fragment se însumează `hybrid_score` din toate cele `N` interogări (`score_sums`).
- **3.2.** Se rețin o singură dată datele fragmentului (prima apariție) și `found_by_lexical`, care devine adevărat dacă **oricare** interogare l-a găsit lexical.
- **3.3.** Se înregistrează în log numărul de candidați pentru fiecare interogare.

## 4. Scorul de relevanță și pragul

- **4.1.** Formula:

  ```text
  relevance_percent = suma_scorurilor / N / RRF_MAX_SCORE × 100
  ```

  Împărțirea la `N` menține plafonul la `RRF_MAX_SCORE`, indiferent de numărul de interogări.
- **4.2.** Se păstrează doar fragmentele cu `relevance_percent >= MIN_RELEVANCE_PERCENT` (implicit `10`, interval 0–100).
- **4.3.** Aceasta este **singura regulă de selecție**, comună panoului din UI și cererii către AI.
- **4.4.** Repere pentru o singură interogare, fără potrivire lexicală: rangul semantic 1 dă ≈ 50%, iar pragul de 10% este atins până la rangul semantic ≈ 245 (`30,5 / (60 + rang) ≥ 0,10`). O potrivire lexicală exactă adaugă un al doilea termen, deci ridică scorul.

## 5. Unirea fragmentelor vecine — `Retriever._merge_adjacent()`

Se aplică doar fragmentelor păstrate la pasul 4.

- **5.1.** Grupează fragmentele după fișierul sursă.
- **5.2.** În fiecare fișier le ordonează după `(line_start, line_end)`.
- **5.3.** Parcurge fragmentele în ordine, cu un grup curent. Un fragment se alătură grupului curent dacă îndeplinește **ambele** condiții:
  - **5.3.1.** Începe cel mult la `NEIGHBOR_LINE_GAP = 5` linii după sfârșitul grupului (deci intervalele se suprapun sau sunt apropiate).
  - **5.3.2.** Diferența dintre cel mai mare și cel mai mic `relevance_percent` din grup, cu fragmentul candidat inclus, rămâne **strict sub** `MERGE_MAX_PERCENT_DIFF` (implicit `9`, interval 0–100).
- **5.4.** Altfel începe un grup nou. Un fragment fără vecini rămâne un grup cu un singur membru.
- **5.5.** Fiecare grup păstrează: calea, intervalul de linii unit (minimul startului, maximul sfârșitului), membrii în ordinea din fișier și procentele minim și maxim.
- **5.6.** Condiția de scor împiedică unirea unui fragment foarte relevant cu unul marginal doar pentru că sunt alăturate în document.

## 6. Scorul și textul unei dovezi unite

- **6.1.** **Fragmentul reprezentant** al grupului este membrul cu suma de scoruri cea mai mare (`best_id`). Se folosește maximul, nu suma membrilor, ca un document împărțit în multe bucăți să nu depășească un singur fragment puternic.
- **6.2.** Dovezile se ordonează descrescător după suma de scoruri a reprezentantului.
- **6.3.** Textul unei dovezi:
  - **6.3.1.** Grup cu un singur membru — `_context()`: textul fragmentului; dacă are sub 600 de caractere și fișierul sursă există, este extins cu liniile din jur (5 înainte, 4 după, maximum 1800 de caractere). Dacă fragmentul are titlu, se prefixează `Secțiune: <titlu>`.
  - **6.3.2.** Grup cu mai mulți membri — `_group_context()`: liniile sursă ale întregului interval unit, prefixate cu titlul reprezentantului. Dacă fișierul nu poate fi citit sau se află în afara directorului de documente, se folosesc textele membrilor în ordinea din fișier, separate printr-o linie goală.
  - **6.3.3.** Căile sunt validate să rămână în `documents_dir`.
- **6.4.** Fiecare dovadă este stocată sub cheia `C<chunk_id reprezentant>` cu câmpurile:

  | Câmp | Conținut |
  |---|---|
  | `source` | `documents/<cale>:<linie_start>-<linie_end>` (intervalul unit) |
  | `text` | contextul construit la 6.3 |
  | `score` | `suma_scorurilor_reprezentant / N` |
  | `relevance_percent` | procentul reprezentantului (maximul din grup) |
  | `found_by_lexical` | adevărat dacă oricare membru a fost găsit lexical |

- **6.5.** Se înregistrează în log numărul de interogări, candidați, fragmente peste prag, dovezi, caractere și surse unice.

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
| `MIN_RELEVANCE_PERCENT` | 10 | Pragul minim al procentului de relevanță |
| `MERGE_MAX_PERCENT_DIFF` | 9 | Diferența maximă de procent într-un grup unit |
| `MAX_CONTEXT_CHARS` | 2.400.000 | Bugetul serializat al dovezilor |
| `INDEX_DIR` | `data/hybrid_index` | Directorul indexului |
| `DOCUMENTS_DIR` | `data/documents` | Documentele sursă pentru extinderea contextului |

Constantele din cod: `RRF_K = 60`, `NEIGHBOR_LINE_GAP = 5`, lungimea minimă a unui cuvânt relevant 4, pragul de extindere a contextului 600 de caractere.

## Rezultatul final

```text
Problema de sănătate
    -> N interogări distincte (problema întreagă și cuvintele-cheie sortate)
    -> pentru fiecare: rang semantic (E5) + rang lexical (FTS5, frază exactă)
    -> hybrid_score = RRF pe cele două rangări, pentru toate fragmentele
    -> suma scorurilor pe interogări, împărțită la N
    -> relevance_percent = scor / RRF_MAX_SCORE × 100
    -> filtrare: relevance_percent >= MIN_RELEVANCE_PERCENT
    -> unirea vecinilor (≤ 5 linii, diferență de procent < MERGE_MAX_PERCENT_DIFF)
    -> dovadă = interval unit, scor și procent ale celui mai bun membru
    -> ordonare descrescătoare și limitare la MAX_CONTEXT_CHARS
    -> panou cu fragmente pentru pacient și, la cerere, payload către AI
```

Fluxul complet al raportului este descris în [final-report-generation.md](final-report-generation.md), iar generarea indexului în [hybrid-index-generation.md](hybrid-index-generation.md).
