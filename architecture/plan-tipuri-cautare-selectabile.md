# Plan: tipuri de căutare selectabile de utilizator (A / B / C)

**Stare:** implementat (2026-10-03). Deciziile D1–D3 au fost aplicate așa cum sunt propuse; la implementare, CTE-ul `lex` (9.1.5) trimite expresiile ca array de interogări (`unnest(...)` evaluat o singură dată, `MATERIALIZED`), nu ca sumă literală de `@@`, ca textul SQL să nu crească cu numărul de expresii (rezultatul este același). Descrierea curentă a comportamentului este în [fragment-search-and-scoring.md](fragment-search-and-scoring.md).

**Scop:** pacientul alege din panoul „Căutare avansată” care semnale intră în scorul unui fragment. Azi formula este fixă: `score = 4·P1 + 2·P2 + L + V` (vezi [fragment-search-and-scoring.md](fragment-search-and-scoring.md)). Pe lângă alegerea semnalelor, planul **redefinește semnalul lexical L** în toate combinațiile, conform deciziilor de mai jos.

Planul are trei părți: **[Partea I — Ce se schimbă](#partea-i--ce-se-schimbă)** (comportamentul văzut de pacient și formulele), **[Partea II — Implementare](#partea-ii--implementare)** (fișier cu fișier) și **[Partea III — Riscuri și verificare](#partea-iii--riscuri-și-verificare)**.

----------------------------------------------------------------------------------------------------

## Partea I — Ce se schimbă

### 1. Interfața

În panoul „Căutare avansată” (`AdvancedSearchPanel`), deasupra arborelui de categorii, apare:

```text
[x] Căutare afecțiuni      (A)
[x] Căutare lexicală       (B)
[x] Căutare semantică      (C)
```

- **1.1. Implicit:** toate trei bifate (formula de azi, cu noul L).
- **1.2. Memorare:** ultima alegere se păstrează în `localStorage` (cheie `naturist.searchSignals`). Citirea și scrierea sunt în `try/catch`; o valoare lipsă, coruptă sau cu toate trei debifate revine la implicit.
- **1.3. Cel puțin unul bifat:** ultimul checkbox bifat devine `disabled` (nu se poate debifa), deci UI-ul nu ajunge niciodată la zero semnale. Serverul validează oricum (vezi 6.2).
- **1.4.** Alegerea se trimite cu fiecare mesaj (ca `categories`) și se aplică acelei căutări. Fragmentele afișate deja în chat își păstrează scorul și procentul de la căutarea lor.

### 2. Formulele

| Bifat | Formulă | Scor maxim | `relevance_percent` |
|---|---|---|---|
| A+B+C | `4·P1 + 2·P2 + L + V` | 8 | `score / 8 × 100` |
| A+B | `3·P1 + 2·P2 + L` | 6 | `score / 6 × 100` |
| A+C | `3·P1 + 2·P2 + V` | 6 | `score / 6 × 100` |
| B+C | `L + V` | 2 | `score / 2 × 100` |
| A | `2·P1 + P2` | 3 | `score / 3 × 100` |
| B | `L` | 1 | `score × 100` |
| C | `V` | 1 | `score × 100` |

- **2.1.** Procentul se calculează **o singură dată**, în `Retriever.collect()`, cu scorul maxim al combinației alese (`max_score(signals)`); UI-ul nu îl recalculează (ca azi).
- **2.2. Doar A:** scorul are trei valori: 3 (afecțiunea în titlu și în text), 2 (doar în titlu), 1 (doar în text). Fragmentele cu 0 nu intră în rezultat.
- **2.3. Egalități:** în toate combinațiile, la scor egal decide `chunk_id` (ordine deterministă, dar arbitrară). Nu există departajare ascunsă după un semnal nebifat.
- **2.4.** Fragmentele cu scor 0 sunt excluse în toate combinațiile (ca azi). Consecințe: doar A fără nicio afecțiune recunoscută → niciun fragment → mesajul generic „Nu am găsit fragmente relevante în sursele locale.” (fără mesaj special); doar C → rămân doar fragmentele cu cosinusul peste mediană (ca azi în modul `SEARCH_SEMANTIC_ONLY`).

### 3. Semnalul A (P1, P2) — neschimbat

Recunoașterea afecțiunilor rămâne exact ca azi (`resolve_query()`, regulile 1.2.1–1.2.4 din documentul de scoring), inclusiv **în interiorul** unei expresii: `gripa la copii` → Gripa → P1/P2.

### 4. Semnalul B (L) — redefinit, în toate combinațiile

`ts_rank_cd` dispare. L devine **fracțiunea de expresii regăsite în fragment**.

- **4.1. Expresiile:** mesajul se împarte la virgulă; expresiile goale se ignoră. Fie `N` numărul de expresii rămase.
- **4.2. Interogarea unei expresii `qᵢ`:**
  - **4.2.1. Expresia întreagă este o afecțiune** — este exact un termen din dicționar (regula 1.2.1) sau o scriere aproape identică a unui termen întreg (regula 1.2.2, raport `difflib` ≥ 0,9; ex. `grippa`). Atunci `qᵢ` = **SAU** între frazele tuturor denumirilor afecțiunii (numele canonic și sinonimele), **nu** textul scris de utilizator.
  - **4.2.2. Altfel** — `qᵢ` = expresia **ca atare**, ca frază exactă: toate cuvintele (cel mult 32), **inclusiv** cuvintele generice și cele scurte (`de`, `la`, `pentru`, `ce`, `sa` …), în ordinea scrisă, alăturate. **Fără sinonime și fără căutarea unei afecțiuni în interiorul expresiei** (`gripa la copii` caută literal fraza „gripa la copii”, chiar dacă A recunoaște Gripa pentru P1/P2).
  - **4.2.3. Fraza** `w₁ <-> w₂ <-> … <-> wₖ` (operatorul `<->` din `tsquery`: cuvinte alăturate, în ordine). Fiecare cuvânt se potrivește cu flexiuni, prin prefix-stem ca azi (`_stem()`: cuvintele de cel puțin 6 litere pierd ultimele 2, minimum 4 păstrate). Diacriticele și majusculele se ignoră (`unaccent`, configurația `simple`). Un sinonim din mai multe cuvinte devine și el frază (`seasonal flu` → `season:* <-> flu:*`).
- **4.3. Numărarea:** `L_brut(f)` = câte dintre `q₁ … q_N` se potrivesc fragmentului `f`. O expresie contează **o singură dată**, oricâte denumiri ale ei sau oricâte apariții ar avea fragmentul (`gripa` și `influenza` în același fragment = 1).
- **4.4. Normalizarea:** `L = L_brut / N` (față de numărul de expresii, **nu** față de cel mai bun fragment din căutare și **fără** normalizare după lungimea fragmentului). Exemplu `gripa, raceala, guta`: un fragment cu gripa și guta are L = 2/3, chiar dacă niciun fragment nu le are pe toate trei.
- **4.5. O singură expresie** (fără virgulă): L ∈ {0, 1}. Cu doar B, toate fragmentele găsite au 100%, iar ordinea între ele o dă `chunk_id` (acceptat explicit).
- **4.6.** `found_by_lexical` = `L_brut > 0`. `lexical_score` = L (sau `None` când `L_brut = 0`, ca azi).

### 5. Semnalul C (V) — neschimbat

`V = clamp((cos − mediană) / (max − mediană), 0, 1)` peste fragmentele categoriilor alese. Cu doar C, ordinea este ordinea cosinusului (peste mediană).

### 6. Semnalele nebifate nu se calculează

- **6.1.** Fără C nu se calculează embeddingul întrebării și nu se citesc vectorii (căutare mai rapidă). Fără B nu rulează partea lexicală. Fără A, P1/P2 nu se calculează în SQL.
- **6.2.** Serverul respinge (HTTP 422) o cerere fără niciun semnal; nu se ajunge aici din UI (1.3).
- **6.3.** Panoul de fragmente ascunde componentele semnalelor nebifate: „Scor semantic” și filtrul lui (fără C), „Scor lexical”, eticheta „Găsire Lexicală” și filtrul „Găsire lexicală” (fără B), „Afecțiune în titlu / în text” și filtrul de afecțiune (fără A). „Scor relevanță” și filtrul de document rămân mereu.

### 7. Mesajul „Am identificat afecțiunea”

- **7.1. Cu A bifat:** `✅ Am identificat afecțiunea: **X**.` pentru fiecare afecțiune recunoscută de A (regulile de azi).
- **7.2. Partea „O caut și după denumirile: …”** apare **doar cu B bifat** și **doar** pentru afecțiunile care sunt o expresie întreagă (4.2.1), deoarece numai acolo se folosesc sinonimele.
- **7.3. Cu B fără A:** mesajul apare doar pentru afecțiunile de la 4.2.1 (nume + sinonime).
- **7.4. Fără A și fără B** (doar C): niciun mesaj de afecțiune.

### 8. `SEARCH_SEMANTIC_ONLY` se elimină

Comutatorul de experiment devine redundant (doar C bifat face același lucru). Se scoate din `config.py`, `docker-compose.yaml`, `.env` (azi `true` local — după eliminare, căutarea locală revine la implicitul A+B+C din UI) și din teste.

----------------------------------------------------------------------------------------------------

## Partea II — Implementare

### 9. Backend

- **9.1. `ai/search.py`**
  - **9.1.1.** Tip nou `SearchSignals(conditions: bool, lexical: bool, semantic: bool)` (dataclass frozen), cu `ALL_SIGNALS` = toate `True` și validare „cel puțin unul”.
  - **9.1.2.** Tabelul ponderilor ca dicționar explicit pe combinație, `(w_primary, w_secondary, w_lexical, w_semantic)`: ABC `(4,2,1,1)`, AB `(3,2,1,0)`, AC `(3,2,0,1)`, BC `(0,0,1,1)`, A `(2,1,0,0)`, B `(0,0,1,0)`, C `(0,0,0,1)`. Înlocuiește `WEIGHT_*`, `MAX_SCORE`, `active_weights()` și `current_max_score()` cu `weights(signals)` și `max_score(signals)`.
  - **9.1.3.** `lexical_query()` → `lexical_queries(resolved) -> list[str]`: câte un `tsquery` pe expresie, după 4.2. Funcțiile `_content_stems()` / `_and_group()` nu mai sunt folosite de lexical (rămân doar dacă le mai folosește altceva). Stemurile conțin doar litere și cifre, deci textul utilizatorului tot nu poate injecta sintaxă `tsquery`.
  - **9.1.4.** `ai/conditions.py` expune, pe fiecare segment, afecțiunea „expresie întreagă” (potrivire 1.2.1 sau 1.2.2) separat de afecțiunile găsite în interior (1.2.3, 1.2.4). Azi informația există implicit (restul gol) — devine un câmp explicit, ex. `Segment.whole_condition`.
  - **9.1.5.** CTE-ul `lex` devine: `SELECT chunk_id, (text_search @@ q₁)::int + … + (text_search @@ q_N)::int AS hits FROM chunks WHERE text_search @@ (q₁ || … || q_N)` (filtrul SAU folosește indexul GIN, suma numără expresiile), iar `L = hits / N`. `lexical_stats` dispare.
  - **9.1.6.** Părțile semnalelor nebifate se generează ca CTE-uri goale sau constante 0 (ca `_NO_LEXICAL_CTE` azi): fără C, `pool` nu conține `embedding <#> …`, `cosine_stats` dispare și `vector` nu se calculează (modelul nu se apelează). Interogarea rămâne una singură.
  - **9.1.7.** `rank(query, category_ids=None, max_chars=None, signals=ALL_SIGNALS)`; rezultatul conține și `signals` aplicate. `warm_up()` rulează cu `ALL_SIGNALS` (încarcă modelul). CLI-ul primește `--signals ABC` (implicit toate).
- **9.2. `ai/retrieval.py`** — `collect(session, max_chars)` citește `session.search_signals` și trimite `signals` la `rank()`; `relevance_percent = score / max_score(signals) × 100`; câmpurile semnalelor nebifate (`semantic_score`, `semantic_similarity`, `lexical_score`, `condition_in_*`) sunt `None`.
- **9.3. `core/models.py`** — `SessionData.search_signals: SearchSignals = ALL_SIGNALS`. `PendingSearch` păstrează și semnalele căutării (pentru afișare/generare).
- **9.4. `web/main.py`**
  - **9.4.1.** `MessageRequest.signals: SignalsPayload = {conditions: true, lexical: true, semantic: true}` (pydantic); niciunul `true` → 422.
  - **9.4.2.** `post_message` salvează `session.search_signals`; logul `user_message_accepted` include semnalele.
  - **9.4.3.** `_condition_identified_message(health_problem, signals)` după secțiunea 7.
  - **9.4.4.** `_fragments_message()` (în `web/handlers.py`) include `signals` în payload, ca panoul să știe ce să ascundă.
- **9.5. `config.py`, `docker-compose.yaml`, `.env`** — eliminarea `SEARCH_SEMANTIC_ONLY` (secțiunea 8).

### 10. Frontend

- **10.1. `hooks/useSearchSignals.ts`** (nou) — starea `{conditions, lexical, semantic}`, inițializată din `localStorage` (1.2), salvată la fiecare schimbare.
- **10.2. `components/CategoryFilterPanel.tsx`** — grupul de trei checkboxuri (secțiunea 1) deasupra barei „Selectează tot / Deselectează tot”; butoanele de categorii nu ating semnalele. Ultimul checkbox bifat primește `disabled` și un `title` explicativ.
- **10.3. `App.tsx`, `hooks/useConversation.ts`, `api/client.ts`, `api/types.ts`** — `sendMessage(message, categories, signals)`; tipul mesajului de fragmente primește `signals`.
- **10.4. `components/FragmentsPanel.tsx`** — ascunde liniile și filtrele semnalelor nebifate (6.3), pe baza `message.signals`; mesajele vechi fără `signals` se tratează ca A+B+C.

### 11. Teste

- **11.1. `tests/unit/ai/test_search.py`**
  - ponderile pentru toate cele 7 combinații și `max_score` corespunzător; inegalitățile de prioritate acolo unde există (ABC: 4 = 2+1+1, 2 = 1+1; AB/AC: 3 = 2+1; A: 2 > 1);
  - `lexical_queries()`: expresie = afecțiune exactă / cu greșeală mică → SAU de fraze din denumiri; expresie cu afecțiune în interior (`gripa la copii`) → frază literală, fără sinonime; cuvinte generice păstrate (`dureri de picioare` → `dure:* <-> de <-> picioa:*`, cu D2); sinonim din mai multe cuvinte → frază; protecția la sintaxă `tsquery`;
  - pe baza de date de test: `L = hits / N` (`gripa, raceala, guta`: 2 din 3 → 0,667); o expresie contează o dată chiar cu mai multe sinonime prezente; doar A → scoruri 3/2/1; doar C fără apel la model (mock care eșuează dacă e apelat); fragmentele cu scor 0 excluse.
  - testul `test_semantic_only_switch_zeroes_every_weight_but_v` și `test_lexical_counts_double_…` se rescriu/elimină.
- **11.2. `tests/unit/web/test_web.py`** — `signals` în `POST /api/messages` (implicit, valid, toate false → 422); mesajul de afecțiune pentru combinațiile din secțiunea 7; `relevance_percent` cu maximul combinației.
- **11.3. Frontend (vitest)** — `useSearchSignals` (localStorage lipsă/corupt/toate false → implicit), ultimul checkbox `disabled`, panoul ascunde filtrele semnalelor nebifate.

### 12. Evaluare

- **12.1.** `scripts/evaluate_retrieval.py` primește `--signals ABC|AB|…` (implicit ABC) și îl trimite la `rank()`; `priority_order_violations` se raportează doar când A este bifat.
- **12.2.** Redefinirea lui L schimbă și formula implicită (ABC), deci: o rulare **înainte** de modificare (`--output before.json`), una **după** cu ABC, plus B singur și C singur pentru comparație. Scriptul doar citește din baza de date; nu e nevoie de reindexare.

### 13. Documentație

`architecture/fragment-search-and-scoring.md` se actualizează: secțiunea 2 (tabelul combinațiilor, noul L), 2.2 rescrisă (fraze, expresie întreagă, numărare), 1.5 (mesajul de afecțiune), 5 (filtrele ascunse), 6 (fără `SEARCH_SEMANTIC_ONLY`, constantele noi).

### 14. Ordinea implementării

1. `conditions.py`: câmpul „afecțiune = expresie întreagă” + teste.
2. `search.py`: `SearchSignals`, tabelul ponderilor, `lexical_queries()`, SQL-ul nou + teste; rularea evaluării înainte/după.
3. `retrieval.py`, `models.py`, `web/main.py`, `handlers.py` + teste.
4. Frontend + teste.
5. Eliminarea `SEARCH_SEMANTIC_ONLY`; documentația.

Nu este nevoie de reindexare: `text_search` păstrează deja toate cuvintele și pozițiile lor (configurația `simple`), deci frazele `<->` funcționează pe indexul existent.

----------------------------------------------------------------------------------------------------

## Partea III — Riscuri și verificare

- **R1. Recall lexical mai mic.** Fraza exactă cu cuvinte generice păstrate (`ce sa iau pentru gripa`) va găsi rar ceva; L va fi des 0 pentru întrebări scrise ca propoziții. Acceptat explicit; evaluarea de la 12.2 arată cât contează în ABC.
- **R2. Multe egalități** cu doar A sau doar B (o expresie): ordinea după `chunk_id` și tăierea la bugetul de 1M caractere sunt arbitrare în cadrul egalității. Acceptat explicit.
- **R3. Pozițiile din `tsvector`** sunt limitate la 16.383: într-un fragment foarte lung, o frază aflată după acea poziție nu se potrivește. Fragmentele sunt secțiuni, deci cazul este rar; de verificat câte fragmente depășesc limita.
- **R4. Latența.** Frazele cu cuvinte foarte frecvente (`de`, `la`) cer verificarea pozițiilor pe multe rânduri. Ținta rămâne < 1 s pentru o întrebare ca „gripa”; se măsoară cu `evaluate_retrieval.py` (p50/p95).
- **R5. Expresii echivalente** (`gripa, influenza`) contează ca două expresii distincte, deci un fragment cu „gripa” are L = 2/2. Comportament acceptat ca urmare directă a regulii 4.3; de semnalat dacă deranjează.

### Decizii de implementare propuse (de confirmat la review)

- **D1.** Expresii identice după normalizare (`gripa, Gripa`) se numără o singură dată în `N`.
- **D2.** Cuvintele sub 3 litere din frază (`de`, `la`, `cu`) se potrivesc exact, fără `:*`, ca `de` să nu prindă și „deja”/„despre”; restul cuvintelor rămân pe prefix-stem ca azi.
- **D3.** Cheia `localStorage` este `naturist.searchSignals`; nu se sincronizează între dispozitive.
