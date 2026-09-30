# Plan de refactorizare — fragmentarea pe categorii de business (R1 / R2 / D1)

**Stare:** plan aprobat, neimplementat · **Data:** 2026-09-30

**Înlocuiește:** criteriile de fragmentare 4.6–4.14 din [fluxul de sincronizare a indexului hibrid](hybrid-index-generation.md) (implementate în `src/medicina_naturista/ai/fragmenter.py`).

## 1. Convenții

| Notație | Semnificație |
|---|---|
| **BC** | `business_category` — coloană nouă în `chunks` |
| **R1** | remedii naturiste de categoria 1 — capitol/subcapitol al cărui **titlu** conține o afecțiune |
| **R2** | remedii naturiste de categoria 2 — capitol/subcapitol al cărui **text propriu** menționează o afecțiune |
| **D1** | diverse — tot restul textului |

- **Afecțiune** = un rând din `data/medical_conditions.txt`: prima expresie (până la virgulă) este denumirea canonică, expresiile următoare de pe același rând sunt sinonimele ei.
- **Regulă obligatorie:** oriunde algoritmul caută o afecțiune, caută denumirea canonică **SAU** oricare dintre sinonime. Acest lucru îl face deja `ConditionDictionary.find()` (`ai/conditions.py`): cuvinte întregi, fără diacritice, fără diferență de majuscule, cu terminațiile românești pliate (`gripa`/`gripei`), iar la aceeași poziție câștigă termenul cel mai lung. Dicționarul nu se modifică.
- **Capitol/subcapitol** = un titlu Markdown (`#`…`######`); marcajele `Pagina N` nu sunt titluri. **Subarborele** unui titlu = titlul și tot ce urmează până la următorul titlu de nivel mai mic sau egal. **Textul propriu** = liniile de sub titlu până la următorul titlu de orice nivel.
- Numele fișierului și calea lui (folderele) **nu** se compară niciodată cu afecțiunile. Nu mai există fragment „document întreg”.

## 2. Decizii confirmate

| # | Întrebare | Decizie |
|---|---|---|
| Q1 | Text care nu stă sub niciun titlu Markdown (documente fără titluri, preambulul dinaintea primului titlu) | Nu este capitol → se fragmentează direct la **pasul 6 (D1)**. |
| Q2 | Capitole imbricate care conțin afecțiuni în titlu | Parcurgere **de jos în sus**: subcapitolul cel mai adânc se procesează primul; părintele primește doar ce a rămas neluat din subarborele lui. |
| Q3 | Numele fișierului/folderelor conține o afecțiune | Nu se ia în considerare. Categoria „R1 document întreg” dispare. |
| Q4 | Granularitatea D1 | Segmente continue de linii libere, care pot traversa titluri; se taie obligatoriu la golurile lăsate de R1/R2 și la capătul documentului. |
| Q5 | `primary` ∩ `secondary` | Se pot suprapune: o afecțiune din titlu care apare și în text este în ambele coloane. |
| I1 | Titlurile capitolelor părinte în textul fragmentului | Nu se pun. Textul unui fragment R1/R2 începe cu **propriul titlu**, fără titlurile strămoșilor în față. |
| — | Valorile BC | `R1`, `R2`, `D1` (cerința inițială spunea „R3” — greșeală de redactare). |
| — | Numele coloanei | `secondary_medical_conditions` (cerința inițială spunea „seconday”). |

### Exemplul de referință pentru Q2

```markdown
# Vindecare prin nutritie
## Gripa si raceala
### Gripa - tratament naturiste
Ceai de musetel: de doua ori pe zi.
```

Rezultă **un singur fragment** (R1):

```markdown
### Gripa - tratament naturiste
Ceai de musetel: de doua ori pe zi.
```

`## Gripa si raceala` nu mai are niciun text propriu rămas după ce subcapitolul a fost luat, deci nu produce fragment. `# Vindecare prin nutritie` nu are text → nu produce nici fragment D1.

### Decizia I1 în detaliu (confirmată)

Pentru R2, aceasta schimbă comportamentul actual, care pune titlurile tuturor strămoșilor ca prefix (`fragmenter.py`, criteriul 4). Exemplu:

```markdown
# Vindecare prin nutritie
## Plante utile
### Musetel
Ceaiul de musetel ajuta in gripa si in insomnie.
```

Fragmentul R2 este doar:

```markdown
### Musetel
Ceaiul de musetel ajuta in gripa si in insomnie.
```

Consecințe:

- Titlurile părinte nu mai pot ajunge în `secondary_medical_conditions` (consecvent cu Q5).
- Contextul părinților rămâne disponibil prin coloana `heading` (vezi I2), pe care embedding-ul o primește deja în contextul fiecărui fragment (`_embedding_context()` din `build_hybrid_index.py`) și pe care căutarea lexicală și semnalul „titlu” o indexează deja. Contextul trimis LLM-ului pentru raportul final o include și el deja: `_context()` din `ai/retrieval.py` pune `Secțiune: <heading>` înaintea textului fiecărui fragment. Nicio informație nu se pierde, deci nu e nevoie de modificări suplimentare.

### Interpretări derivate din decizii (de confirmat la review)

- **I2.** Coloana `heading` păstrează lanțul complet de titluri (`Vindecare prin nutritie > Gripa si raceala > Gripa - tratament naturiste`), ca metadată pentru afișare, pentru semnalul „titlu” din căutare și pentru etichetele de evaluare. **Nu** este folosit la determinarea afecțiunilor.
- **I3.** `primary_medical_conditions` = afecțiunile din **propriul titlu** al fragmentului (nu din titlurile strămoșilor, nu din numele documentului).
- **I4.** **Consecință logică a lui I3:** un fragment R2 are întotdeauna `primary_medical_conditions` gol — dacă titlul lui ar conține o afecțiune, ar fi fost R1. Coloana `primary` este deci informativă doar pentru R1.
- **I5.** Un titlu R1 care, după parcurgerea de jos în sus, nu mai are niciun rând de text (doar titluri goale sau linii albe) nu produce fragment; linia lui de titlu este consumată și nu ajunge în D1.
- **I6.** Un segment D1 format numai din linii de titlu și linii albe nu produce fragment.
## 3. Algoritmul țintă

```text
fragment_document(text, dictionary) -> list[Fragment]

  headings = titlurile documentului (fără marcajele "Pagina N")
  consumed = [False] * număr_linii

  # Pasul 1 — R1, de jos în sus (cei mai adânci întâi; post-ordine)
  pentru h în headings, ordonate descrescător după adâncime:
      dacă dictionary.find(h.title) e gol: continuă
      linii = liniile din subarborele lui h care NU sunt consumate
      marchează linii ca consumate
      dacă linii (fără titluri și linii albe) conțin text:
          R1(text = linii, heading = lanț_titluri(h))

  # Pasul 2 — liniile R1 sunt excluse (consumed)

  # Pasul 3 — R2
  pentru h în headings, cu linia titlului neconsumată:
      corp = textul propriu al lui h
      dacă dictionary.find(corp) nu e gol:
          R2(text = h.raw + corp, heading = lanț_titluri(h)); marchează consumat
      # o secțiune cu mai multe afecțiuni → un singur fragment

  # Pasul 4 — etichetare (doar R1 și R2)
  primary   = nume_canonice(dictionary.find(titlul propriu))
  secondary = nume_canonice(dictionary.find(textul fragmentului fără linia propriului titlu))

  # Pasul 5 — liniile R2 sunt excluse (consumed)

  # Pasul 6 — D1
  pentru fiecare segment maximal de linii neconsumate (inclusiv preambulul și
  documentele fără titluri):
      dacă segmentul are doar titluri/linii albe: sari
      bucăți = split_with_overlap(segment, țintă=1800, suprapunere_max=270)
      D1(text = bucată, heading = lanț_titluri al secțiunii în care începe bucata sau "")
      primary = secondary = []

  sortează fragmentele după (line_start, line_end)
```

### 3.1 Detalii

- **Pasul 1:** ordinea „cei mai adânci întâi” garantează că un subcapitol cu afecțiune în titlu este mereu fragment separat, iar părintele primește doar restul: titlul propriu, textul lui propriu și subcapitolele fără afecțiune în titlu. Titlurile de aceeași adâncime au subarbori disjuncți, deci ordinea dintre ele nu contează.
- **Pasul 3:** cerința „se iterează `medical_conditions.txt` și pentru fiecare afecțiune se caută în document” se implementează ca o singură trecere prin secțiuni cu `find()`. Mulțimea de secțiuni rezultate este identică (reuniunea peste afecțiuni), dar costul este O(lungimea textului) în loc de O(809 afecțiuni × lungimea textului), iar deduplicarea (o secțiune → un fragment) este implicită.
- **Pasul 4:** subtitlurile rămase în interiorul unui R1 fac parte din text, deci contribuie la `secondary`. După pasul 1 ele nu pot conține afecțiuni, deci regula rămâne consecventă.
- **Fără limită de caractere pentru R1 și R2:** `MAX_FRAGMENT_CHARS` dispare; nu se mai împarte niciun fragment R1/R2.
- **Pasul 6 — `split_with_overlap`:**
  - tăietura se face la cea mai bună limită din intervalul **[1500, 2100]** caractere, în ordinea: final de paragraf → final de propoziție (`.`, `!`, `?`, `…`) → final de rând → spațiu; în lipsa tuturor, tăietură forțată la 2100;
  - bucata următoare începe la un început de propoziție (altfel de cuvânt) aflat în ultimele **≤ 270** caractere ale bucății anterioare; suprapunerea poate fi 0 dacă nu există o astfel de limită;
  - o bucată finală sub 300 de caractere se lipește de cea anterioară;
  - liniile de titlu din segment rămân în text, ca și context;
  - o bucată nu traversează niciodată un gol lăsat de R1/R2.
- **Intervalul de linii** al unui R1 din care s-a decupat un subcapitol are un gol; `line_start`/`line_end` sunt primul și ultimul rând al fragmentului.
- Marcajele `Pagina N` sunt scoase din text și din `heading`, ca acum.

## 4. Impact măsurat pe corpus

Simulare pe `data/documents` (fără bază de date, fără embeddings), cu regulile de mai sus:

| Categorie | Număr | Caractere | Mediană | p95 | Max | > 8 000 | > 50 000 |
|---|---|---|---|---|---|---|---|
| R1 | 559 | 3,30M | 3 299 | 16 318 | 399 531 | 139 | 1 |
| R2 | 564 | 1,82M | 1 859 | 8 979 | 196 580 | 48 | 1 |
| D1 | ≈ 8 700 bucăți (din 559 segmente) | 13,32M | ≈ 1 800 | ≈ 2 100 | ≈ 2 100 | 0 | 0 |

Referință: fragmenterul actual produce 6 246 de fragmente.

Observații:

- **~72% din text devine D1**, în mare parte cărți convertite din PDF fără titluri Markdown (de ex. *Jacques Martel – Marele dicționar al bolilor*, 1,6M caractere; *Walter Last – Heal Yourself*, 1,4M). Sunt cărți de sănătate, deci eticheta D1 e corectă tehnic, dar săracă semantic. Remedierea ține de date, nu de algoritm: adăugarea titlurilor la conversie (vezi §8).
- **Două fragmente depășesc 50 000 de caractere:**
  - R1, 399 531 caractere — `Cărți/Phyllis A. Balch - Vindecare prin nutritie/Vindecare prin nutritie.md`, titlul `# Reducerea riscului de sindrom de tunel carpian`. E un H1 cu nivel greșit, care înghite capitolele următoare. Remediere: retrogradarea titlului în sursă.
  - R2, 196 580 caractere — `Diverse/Cristaloterapie/Cristale-M-Z.md`: o secțiune foarte lungă fără subtitluri.

## 5. Modificări pe fișiere

### 5.1 `src/medicina_naturista/ai/fragmenter.py` — rescriere

- Se păstrează: `_parse_headings`, `_span`, `_cut_before`, `_is_page_marker`.
- Se elimină: `MAX_FRAGMENT_CHARS`, `PLAIN_CHUNK_CHARS`, `PLAIN_HARD_CAP_CHARS`, `_cut_after`, `plain_mode`, `_document_title`, `_SOURCE_EXTENSIONS` și criteriul „nume de fișier”.
- Parametrul `relative_path` al lui `fragment_document()` nu mai este necesar; se elimină odată cu apelantul.
- Se adaugă:
  - `D1_TARGET_CHARS = 1800`, `D1_MIN_CHARS = 1500`, `D1_MAX_CHARS = 2100`, `D1_MAX_OVERLAP_CHARS = 270`, `D1_MIN_TAIL_CHARS = 300`;
  - `class BusinessCategory(StrEnum): R1 = "R1"; R2 = "R2"; D1 = "D1"`;
  - `Fragment(text, line_start, line_end, path, business_category, primary_conditions, secondary_conditions)`.
- Structură în funcții pure, testabile separat: `_select_r1()`, `_select_r2()`, `_split_rest()`, `_tag()`.

### 5.2 `src/medicina_naturista/ai/db.py` — schemă

```sql
-- în CREATE TABLE chunks: coloanele noi, fără conditions
ALTER TABLE chunks DROP COLUMN IF EXISTS conditions;          -- idx_chunks_conditions dispare odată cu ea
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS business_category TEXT
    CHECK (business_category IN ('R1', 'R2', 'D1'));
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS primary_medical_conditions   TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS secondary_medical_conditions TEXT[] NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS idx_chunks_business_category ON chunks(business_category);
CREATE INDEX IF NOT EXISTS idx_chunks_primary_conditions   ON chunks USING GIN(primary_medical_conditions);
CREATE INDEX IF NOT EXISTS idx_chunks_secondary_conditions ON chunks USING GIN(secondary_medical_conditions);
```

`business_category` rămâne nullable la migrare: un `ADD COLUMN ... NOT NULL` fără valoare implicită ar eșua pe un tabel cu date, iar o valoare implicită ar eticheta greșit rândurile vechi. Indexatorul setează mereu coloana. După ce toate mediile au fost resincronizate, se trece la `NOT NULL` într-o modificare separată.

### 5.3 `scripts/build_hybrid_index.py`

- `Chunk`: `conditions` se înlocuiește cu `business_category`, `primary_medical_conditions` și `secondary_medical_conditions`; se elimină comentariul învechit despre „priority 1..5”.
- `_write_document()`: coloanele noi în `INSERT`.
- `build()`: maparea din `Fragment`; apelul `fragment_document(normalized, dictionary)`.
- `TEXT_REPR_VERSION`: `"3"` → `"4"`, ca să forțeze resincronizarea completă.
- Embedding-ul rămâne neschimbat (ferestre de 1 400 de caractere cu suprapunere de 240, mediate).

### 5.4 Consumatori

- `src/medicina_naturista/ai/search.py`: în `SELECT`-ul din `rank()` și în dicționarul rezultat, `conditions` se înlocuiește cu cele trei câmpuri noi.
- `src/medicina_naturista/ai/retrieval.py`: câmpurile din dovezi (`evidence`).
- Frontend-ul nu citește `conditions`, deci nu are nevoie de modificări.

### 5.5 Documentație

- `architecture/hybrid-index-generation.md`: §4.6–4.14 (criteriile noi), §6.3 (coloanele noi).
- `architecture/fragment-search-and-scoring.md`: §2.4.4 și tabelul de câmpuri.

## 6. Teste

`tests/unit/ai/test_fragmenter.py` (rescriere):

1. Exemplul de referință din §2 produce exact un fragment R1, cu textul `### Gripa - tratament naturiste\nCeai de musetel: de doua ori pe zi.`.
2. R1 detectat după denumirea canonică, după un sinonim (`gout`) și după o formă flexionată (`Gripei`).
3. Părinte R1 cu text propriu și copil R1 → două fragmente disjuncte; părintele păstrează subcapitolele fără afecțiune în titlu.
4. O afecțiune menționată în textul unui R1 nu produce R2.
5. R2: textul începe cu propriul titlu, fără strămoși; trei afecțiuni în aceeași secțiune dau un singur fragment.
6. Un document fără titluri și un preambul care menționează afecțiuni devin D1.
7. Numele fișierului care conține o afecțiune nu influențează nimic.
8. D1:
   - bucăți între 1 500 și 2 100 de caractere (cu excepția ultimei);
   - suprapunere ≤ 270;
   - reuniunea bucăților acoperă tot segmentul;
   - nicio bucată nu traversează un gol R1/R2;
   - `primary` și `secondary` sunt goale;
   - un segment format doar din titluri nu produce fragment.
9. Etichetarea:
   - R1 `### Gripa` cu „febră” în text → `primary = (Gripa,)`, `secondary = (Febra,)`;
   - dacă „gripa” apare și în text → `secondary` conține și `Gripa` (Q5);
   - R2 → `primary` gol (I4).
10. Un R1 de 20 000 de caractere rămâne un singur fragment.
11. Marcajele `Pagina N` sunt eliminate din text și din `heading`.

`tests/unit/ai/test_build_hybrid_index.py`:

- Migrarea din schema veche este idempotentă (rulată de două ori): `conditions` dispare, coloanele noi există.
- Sincronizarea scrie `business_category`, `primary_medical_conditions` și `secondary_medical_conditions` (se adaptează `test_sync_stores_conditions_and_heading_per_fragment`).
- Constrângerea `CHECK` respinge o valoare invalidă (de ex. `R3`).

`tests/unit/ai/test_search.py`: `test_results_carry_the_indexed_conditions` verifică noile câmpuri.

## 7. Riscuri

- **Fragmente R1/R2 foarte mari** (cele două de la §4 și cele 187 peste 8 000 de caractere):
  - vectorul semantic devine media multor ferestre, deci e mai puțin precis;
  - un fragment mare aflat sus în clasament consumă o parte mare din `MAX_CONTEXT_CHARS`, iar `fit_evidence_to_context()` (`ai/client.py`) păstrează fragmentele în ordinea scorului până la epuizarea bugetului, deci îi elimină pe cei de după el;
  - `tsvector` limitează pozițiile la 16 383, deci ordonarea după proximitate slăbește la textele lungi.
  - Atenuări fără a încălca regula „fără limită”: corectarea surselor (§8) și, dacă evaluarea arată regresie, mai mulți vectori per fragment (vezi §8).
- **Clasamentul se schimbă peste tot:** se măsoară înainte și după (§9), nu se presupune.

## 8. În afara acestui refactor (pași următori propuși)

- **Date:**
  - adăugarea titlurilor Markdown la cărțile mari fără structură, prin `scripts/extract_pdf_markdown.py`;
  - corectarea nivelului titlului din Balch (§4);
  - împărțirea secțiunii din `Cristale-M-Z.md`.
- **Căutare:**
  - `query_priority()` (`ai/search.py`) poate citi `primary_medical_conditions` și `secondary_medical_conditions` în loc să recalculeze potrivirea la fiecare căutare;
  - `business_category` poate deveni filtru sau pondere în scor. De măsurat separat.
- **Embedding multi-vector:** un tabel `chunk_windows` cu câte un vector per fereastră, iar la căutare contează fereastra cea mai apropiată. Doar dacă evaluarea arată regresie pe fragmentele mari.
- **Schemă:** `business_category` trece la `NOT NULL` după resincronizarea tuturor mediilor.

## 9. Ordinea de lucru

1. **Baseline**, pe indexul actual, înainte de orice modificare. Etichetele de relevanță se bazează pe cale și titlu, deci rămân comparabile după reindexare:
   `.venv/Scripts/python.exe scripts/evaluate_retrieval.py --output tmp/eval-baseline.json`
2. Pe un branch separat: fragmenter și testele lui → schemă → indexator → căutare și regăsire → documentație.
3. `scripts/fragment_report.py`: raport fără bază de date, cu distribuția pe categorii și fragmentele cele mai mari, verificat înainte de reindexare.
4. Reindexarea completă se rulează de utilizator: `scripts/rebuild_index.ps1`.
5. Evaluare după reindexare și comparație cu baseline-ul: nDCG@10, R@50, latență.
