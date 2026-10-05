# Plan: dicționarul de afecțiuni în JSONL și catalogul de plante medicinale `herbs.jsonl`

**Stare:** E1 implementat (2026-10-05): conversia a trecut round-trip-ul (5469 de afecțiuni, 39.804 termeni), cele 8789 de fragmente sunt identice înainte și după, .txt-ul și `conditions_work/` sunt șterse. E2 implementat (2026-10-05): `backend/ai/herbs.py`, `HERBS_FILE`, `test_herbs.py`; copierea în `Dockerfile` s-a mutat în E4 (6.1). E3 aprobat (2026-10-05): lista revizuită are 1210 specii (125 adăugate de proprietar). E4 implementat (2026-10-05): `data/herbs.jsonl` cu 1188 de specii (22 de dubluri unite), generat de `src/scripts/herbs_work/build_herbs.py`; 118 specii fără nume românesc au `ro` = numele latin (decizie), 79 au `en` gol (D10); raportul `tmp/herbs_review.md` e generat de `src/scripts/audit_herbs.py`. Catalogul a fost acceptat; denumirile regionale din cunoștințe (D14) sunt marcate `cunostinte` în raport (36), iar zgomotul din denumirile regionale a fost curățat. Scripturile one-off au fost scoase din `src/` (păstrate local în `tmp/herbs_work/scripts/`, fiindcă nu au fost comise niciodată); în repo rămâne `src/scripts/audit_herbs.py`. Planul este complet (E1–E4).

**Scop:**

1. `data/medical_conditions.txt` se mută în **`data/medical_conditions.jsonl`**: o afecțiune pe linie, ca obiect JSON. Fișierul .txt dispare, împreună cu uneltele one-off care îl rescriau (`src/scripts/conditions_work/`). Aplicația citește JSONL-ul exact cum citește azi .txt-ul, deci afecțiunile, fragmentele și scorurile rămân **identice** și **nu e nevoie de reindexare**.
2. Apare **`data/herbs.jsonl`**, un catalog de plante medicinale, plus un loader (`backend/ai/herbs.py`) și teste de integritate. În etapa asta catalogul **nu e legat** de căutare, de fragmentare sau de PDF.
3. `herbs.jsonl` primește **toate speciile medicinale** din Farmacopeea Română și din corpus, completate apoi din monografiile EMA și din literatura românească de floră medicinală — plante vasculare, ciuperci, licheni, mușchi și alge — fără un număr fix (D4, D8).

Planul are trei părți: **[Partea I — Decizii](#partea-i--decizii)**, **[Partea II — Implementare](#partea-ii--implementare)** și **[Partea III — Verificare și riscuri](#partea-iii--verificare-și-riscuri)**.

----------------------------------------------------------------------------------------------------

## Partea I — Decizii

### 1. Decizii confirmate

| # | Decizie |
|---|---|
| D1 | O linie din `medical_conditions.jsonl` = `{"name": ..., "synonyms": [...]}`, cu numele canonic **doar** în `name` |
| D2 | `data/medical_conditions.jsonl` **înlocuiește** .txt-ul și e citit la runtime de `load_dictionary()`, cu reîncărcare pe `mtime` ca azi. Planul Postgres ([plan-postgres-conditions-and-index-api-deepseek.md](plan-postgres-conditions-and-index-api-deepseek.md)) rămâne separat |
| D3 | `herbs.jsonl` = fișier de date + loader + teste; nimic din căutare sau fragmentare nu se schimbă |
| D4 | **Originea speciei:** speciile din Farmacopeea Română și din corpus intră **indiferent unde cresc** (inclusiv senna, arborele de chinină, scorțișoara, ghimbirul, turmericul). Speciile adăugate din EMA și din literatura românească intră doar dacă sunt **spontane** în România (indigene sau naturalizate) sau **cultivate** în România, inclusiv în ghiveci sau în casă (ginkgo, aloe, lămâi) |
| D5 | Denumirile românești din `herbs.jsonl` se scriu **fără diacritice** („Musetel”), ca în `medical_conditions.jsonl` |
| D6 | Câmpuri în plus față de cerința inițială: `id`, `latin_synonyms`, `en_alt`, `family` |
| D7 | **Numele latin acceptat e identificatorul botanic**: o intrare = o specie, `latin` și `id` unice în tot fișierul. **`ro` nu e unic**: când un nume popular acoperă mai multe specii, fiecare specie are intrarea ei cu același `ro` („Paducel” pentru *Crataegus monogyna* și pentru *C. laevigata*); speciile se deosebesc prin `id` / `latin`. Și `ro_regional` poate fi comun mai multor specii |
| D8 | **Surse, în ordinea priorității:** (1) **Farmacopeea Română** (ed. X și suplimentele ei) — toate speciile cu monografie; (2) **corpusul** (orice document din `data/documents`); (3) completări din **monografiile EMA/HMPC** și din **literatura românească de floră medicinală**, supuse filtrului de origine din D4. Sursa fiecărei specii apare în raportul de verificare. Fără număr fix |
| D9 | Grupuri incluse: plante vasculare (inclusiv ferigi și coada-calului), **ciuperci**, **licheni**, **mușchi**, **alge** (inclusiv cele din Marea Neagră) |
| D10 | Dacă o specie **nu are nume englezesc uzual**, `en` este șirul gol `""`, iar `en_alt` este `[]` |
| D11 | `src/scripts/conditions_work/` se **șterge în acest plan** (etapa E1) |
| D12 | Fără câmpuri `group` și `cultivated`: structura rămâne cea din §3. Grupul și originea (spontan/cultivat/importat) apar doar în lista de review (7.6) și în raportul de verificare (8.6) |
| D13 | **Plantele alimentare** (legume, fructe, cereale) intră doar dacă au o **utilizare medicinală explicită** în sursă — o simplă pomenire într-o rețetă culinară nu ajunge |
| D14 | Denumirile din `ro_regional`, `en` și `en_alt` care nu apar în corpus se completează **din cunoștințele mele**, doar cele de care sunt sigur; raportul marchează pentru fiecare specie care denumiri vin din corpus |
| D15 | Lista de aprobat (7.6) se livrează ca **JSONL**, nu ca Excel |
| D16 | **Nu fac niciun commit.** Toate modificările rămân în arborele de lucru; commit-ul îl faci tu la final |

### 2. Structura `medical_conditions.jsonl`

```json
{"name": "Abces", "synonyms": ["buboi", "colectie de puroi", "acumulare purulenta", "supuratie localizata", "abscess", "pus collection", "localized pus"]}
```

- **2.1.** O linie = o afecțiune, în **aceeași ordine** ca în .txt (ordinea contează la egalitățile din potrivirea fuzzy, `get_close_matches` / `_pick()`).
- **2.2.** `name` = primul câmp din linia .txt; `synonyms` = restul câmpurilor, în ordinea lor, **deja deduplicate** (cum le deduplică azi `parse_conditions()` după `_normalize()`).
- **2.3.** Scriere: UTF-8, sfârșit de linie LF, `json.dumps(obj, ensure_ascii=False)` cu separatorii impliciți (`", "`, `": "`), un `\n` la final. Un diff de o linie = o afecțiune schimbată, ca azi.
- **2.4.** JSONL nu are comentarii. Liniile goale se ignoră; azi nu există nicio linie goală sau comentată (5469 de afecțiuni pe 5469 de linii), deci nu se pierde nimic.
- **2.5.** Termenii nu pot conține **virgulă**. În .txt asta era imposibil prin construcție; în JSONL devine posibil, dar un termen cu virgulă n-ar putea fi niciodată recunoscut, pentru că `resolve()` taie mesajul la virgulă. Regula intră în teste.

### 3. Structura `herbs.jsonl`

```json
{"id": "matricaria-chamomilla", "ro": "Musetel", "ro_regional": ["romanita", "matricea", "musetel de camp"], "latin": "Matricaria chamomilla", "latin_synonyms": ["Matricaria recutita", "Chamomilla recutita"], "en": "German chamomile", "en_alt": ["wild chamomile", "scented mayweed"], "family": "Asteraceae"}
{"id": "crataegus-monogyna", "ro": "Paducel", "ro_regional": ["gherghinar"], "latin": "Crataegus monogyna", "latin_synonyms": [], "en": "Common hawthorn", "en_alt": ["single-seeded hawthorn"], "family": "Rosaceae"}
{"id": "crataegus-laevigata", "ro": "Paducel", "ro_regional": ["gherghinar"], "latin": "Crataegus laevigata", "latin_synonyms": ["Crataegus oxyacantha"], "en": "Midland hawthorn", "en_alt": ["English hawthorn"], "family": "Rosaceae"}
{"id": "fomitopsis-betulina", "ro": "Iasca de mesteacan", "ro_regional": [], "latin": "Fomitopsis betulina", "latin_synonyms": ["Piptoporus betulinus"], "en": "Birch polypore", "en_alt": ["birch bracket"], "family": "Fomitopsidaceae"}
```

| Câmp | Tip | Obligatoriu | Reguli |
|---|---|---|---|
| `id` | string | da | slug ASCII din numele latin la creare (`^[a-z]+(-[a-z]+)+$`), unic. **Nu se schimbă** dacă taxonomia se schimbă mai târziu (vezi 3.3) |
| `ro` | string | da | numele românesc uzual, fără diacritice, cu majusculă inițială și cratimele din DOOM („Coada-soricelului”); **poate fi comun mai multor specii** (D7) |
| `ro_regional` | listă de string | da (poate fi `[]`) | celelalte denumiri românești: populare, regionale, arhaice; fără diacritice, litere mici (în afară de nume proprii); fără `ro` și fără duplicate în listă |
| `latin` | string | da | numele acceptat al speciei, **fără autor** (`Matricaria chamomilla`, nu `Matricaria chamomilla L.`); unic; hibrizii cu `x` (`Mentha x piperita`); subspecie doar când e relevantă medicinal (`Genus species subsp. x`) |
| `latin_synonyms` | listă de string | da (poate fi `[]`) | nume latine vechi sau sinonime, în special cele folosite de Farmacopee, de literatura românească și de corpus (`Aloe vulgaris`, `Ribes grossularia`); niciun element nu poate fi `latin` al altei intrări |
| `en` | string | da (poate fi `""`, D10) | numele englezesc uzual principal |
| `en_alt` | listă de string | da (poate fi `[]`) | alte nume englezești uzuale, fără `en`; obligatoriu `[]` când `en` e gol |
| `family` | string | da | familia, terminată în `-aceae`: pentru plante după APG (`Asteraceae`, nu `Compositae`), pentru ciuperci și licheni după Index Fungorum / MycoBank (`Parmeliaceae`), pentru alge după AlgaeBase |

- **3.1.** Ordinea cheilor e fixă (cea din tabel), iar liniile sunt sortate după `ro` normalizat, apoi după `latin` (pentru speciile cu același `ro`), ca review-ul și diff-urile să fie ușoare.
- **3.2.** Tot fișierul e **ASCII pur** (ca `medical_conditions.jsonl`). Un hibrid se scrie cu `x`, nu cu `×`.
- **3.3.** De ce `id` separat de `latin`: `latin` e identificatorul botanic (D7), dar numele acceptate se mai schimbă (*Piptoporus betulinus* → *Fomitopsis betulina*). La o astfel de schimbare, `latin` primește noul nume, vechiul trece în `latin_synonyms`, iar `id` rămâne, deci orice referință viitoare la plantă (din fragmente, din DB) nu se rupe.
- **3.4.** `ro_regional` conține **toate** celelalte denumiri românești, nu doar cele strict regionale: regiunea unei denumiri nu se poate stabili sigur pentru sute de specii, iar pentru o recunoaștere viitoare în text contează doar că denumirea există.
- **3.5.** Pentru plantele cultivate, intrarea e la nivel de **specie**, nu de soi (fără „busuioc cu frunza mare”, „usturoi de toamnă”).
- **3.6.** Farmacopeea numește **produsul vegetal**, nu specia („Chamomillae flos”, „Crataegi folium cum flore”). Fiecare monografie se traduce în specia sau speciile-sursă pe care le admite (*Crataegi folium cum flore* → *C. monogyna* și *C. laevigata*, deci două intrări); numele produsului nu intră în `herbs.jsonl`.

### 4. Ce nu intră în acest plan

- recunoașterea plantelor în mesaje sau în fragmente, semnale de scor noi, coloane noi în `chunks`;
- indicații terapeutice, părți folosite, toxicitate (au fost discutate, nu au fost alese);
- mutarea dicționarului în Postgres (rămâne planul separat);
- commit-urile (D16).

----------------------------------------------------------------------------------------------------

## Partea II — Implementare

### 5. Etapa E1 — `medical_conditions.jsonl`

- **5.1. Conversia (o singură dată).** Script nou `src/scripts/convert_conditions_to_jsonl.py`:
  - citește `data/medical_conditions.txt` cu parserul .txt de azi (copiat în script, pentru că `parse_conditions()` se rescrie la 5.2);
  - scrie `data/medical_conditions.jsonl` după regulile din §2;
  - verifică **round-trip-ul**: lista de `Condition` obținută din JSONL (cu noul `parse_conditions()`) e egală element cu element cu cea din .txt — aceleași nume, aceiași termeni, aceeași ordine; la orice diferență iese cu cod nenul și nu scrie nimic.
  - Scriptul se șterge după ce JSONL-ul e verificat.
- **5.2. `src/backend/ai/conditions.py`:**
  - `parse_conditions(text)` își păstrează numele și semnătura, dar parsează JSONL: pentru fiecare linie nevidă, `json.loads`, apoi `terms = [name, *synonyms]` deduplicate după `_normalize()` (aceeași regulă ca azi, păstrată defensiv).
  - O linie invalidă (JSON stricat, `name` lipsă, `synonyms` care nu e listă de string) aruncă `ValueError` cu numărul liniei. Azi nu există niciun caz de „linie stricată”; un dicționar gol tăcut ar strica toate căutările fără niciun semn, deci eroarea e preferabilă. Un fișier **lipsă** dă în continuare dicționar gol (comportamentul de azi).
  - docstring-ul modulului și comentariile se actualizează (`.txt` → `.jsonl`, structura nouă).
  - `ConditionDictionary`, `_load()`, `load_dictionary()`, `find_conditions()`, `resolve_query()` **nu se schimbă**.
- **5.3. Configurare și imagine:**
  - `src/backend/config.py:83`: implicitul lui `CONDITIONS_FILE` devine `data/medical_conditions.jsonl`;
  - `Dockerfile:30`: `COPY data/medical_conditions.jsonl ./data/medical_conditions.jsonl`;
  - dacă cineva are `CONDITIONS_FILE` setat explicit spre .txt într-un `.env` local, trebuie actualizat (notă în README).
- **5.4. Teste:**
  - helper nou `src/tests/support/conditions.py` cu `conditions_jsonl(*rows)`, care transformă rânduri scurte în stilul vechi (`"Gripa,gripe"`) în text JSONL. Apelurile `parse_conditions("...")` cu text inline (25 de apeluri în total, inclusiv cele pe fișierul livrat) din `test_conditions.py`, `test_condition_ai.py`, `test_build_hybrid_index.py`, `test_fragmenter.py`, `test_search.py` și `test_web.py` trec prin helper, ca testele să rămână lizibile;
  - `FileLoadingTests` (fișier lipsă, reîncărcare pe `mtime`) scriu fișiere `.jsonl`;
  - testele „shipped dictionary” (`test_conditions.py:151-211`) se rescriu pe JSONL: fiecare linie e un obiect cu exact cheile `name` și `synonyms`; cel puțin 6 sinonime (azi: nume + 3 RO + 3 EN); niciun termen gol, cu spații la capete, cu diacritice, non-ASCII sau **cu virgulă** (2.5); nume canonice unice; niciun termen comun la două afecțiuni;
  - test nou: o linie invalidă aruncă `ValueError` cu numărul liniei.
- **5.5. Scripturi care citesc .txt-ul:**
  - `src/scripts/audit_conditions.py` și `src/scripts/audit_near_dupes.py` se adaptează la JSONL (citesc prin `parse_conditions()` în loc să despartă singure liniile);
  - **`src/scripts/conditions_work/` se șterge integral** (D11): ~90 de fișiere — loturile `01_…15_*.txt`, specificațiile `SPEC*.md` / `TASK_*.md`, `archive_folk/` și scripturile Python care citesc sau rescriu .txt-ul (inclusiv `coverage_probe.py` și `gaps_from_corpus.py`, care foloseau `load_dictionary()`). Rămân în istoria git.
- **5.6. Documentație:** `README.md:296`, `architecture/fragment-search-and-scoring.md` (rândurile 13, 23, 40, 143), `architecture/hybrid-index-generation.md` (16, 49): calea nouă și structura JSONL. Planurile vechi din `architecture/` rămân cum sunt (descriu istoric).
- **5.7. Ștergere:** `data/medical_conditions.txt` se șterge după ce JSONL-ul trece round-trip-ul și testele.

### 6. Etapa E2 — loader-ul `herbs.py`

- **6.1.** `src/backend/config.py`: `herbs_file: Path` din `HERBS_FILE`, implicit `data/herbs.jsonl`. `Dockerfile`: `COPY data/herbs.jsonl ./data/herbs.jsonl`, ca loader-ul să funcționeze și în container — adăugat abia în **E4**, când fișierul există (un `COPY` spre un fișier lipsă ar opri build-ul imaginii).
- **6.2.** Modul nou `src/backend/ai/herbs.py`, după modelul lui `conditions.py`:

  ```python
  @dataclass(frozen=True)
  class Herb:
      id: str
      ro: str
      ro_regional: tuple[str, ...]
      latin: str
      latin_synonyms: tuple[str, ...]
      en: str                      # "" when the species has no common English name
      en_alt: tuple[str, ...]
      family: str

      # Every non-empty name of the plant: ro, regional, latin, latin synonyms, en, en_alt.
      @property
      def names(self) -> tuple[str, ...]: ...

  def parse_herbs(text: str) -> list[Herb]: ...          # ValueError cu numărul liniei la orice abatere de schemă

  class HerbCatalog:
      def __init__(self, herbs: list[Herb]) -> None: ...
      def by_id(self, herb_id: str) -> Herb | None: ...
      def by_latin(self, latin: str) -> Herb | None: ...  # caută și în latin_synonyms
      def lookup(self, name: str) -> list[Herb]: ...       # orice denumire, după _normalize(); listă, pentru că ro și ro_regional pot fi comune mai multor specii

  def load_herbs(path: Path | None = None) -> HerbCatalog: ...  # lru_cache pe (cale, mtime); fișier lipsă -> catalog gol
  ```

  `_normalize()` se importă din `conditions.py`, ca plantele și afecțiunile să se compare după aceeași regulă.
- **6.3.** `parse_herbs()` validează **schema** (chei exacte, tipuri, câmpurile obligatorii nevide, cu excepția lui `en`, care poate fi `""`). Regulile de **conținut** pe fișierul livrat stau în teste (6.4), ca un fixture mic de test să nu trebuiască să le respecte pe toate.
- **6.4.** Teste noi `src/tests/unit/ai/test_herbs.py`. Regulile de conținut stau în funcția `content_problems()` din test, verificată pe fixture-uri bune și greșite; testul pe `data/herbs.jsonl` e sărit cât timp fișierul lipsește și devine obligatoriu în E4, când i se adaugă și numărul minim de specii:
  - parser: linie validă, chei lipsă/în plus, tipuri greșite, `en` gol acceptat, linie goală ignorată, JSON stricat → `ValueError` cu numărul liniei;
  - catalog: `by_id`, `by_latin` (și prin sinonim), `lookup` fără diacritice și fără majuscule, `lookup("paducel")` → ambele specii de *Crataegus*, `lookup` pe o denumire regională comună → mai multe specii, `lookup("")` → nimic (un `en` gol nu e denumire); fișier lipsă → catalog gol; reîncărcare pe `mtime`;
  - fișierul livrat: **fără număr fix** de intrări — testul cere doar cel puțin numărul livrat la E4, ca o trunchiere accidentală să fie prinsă; ASCII pur; ordinea cheilor din §3; sortat după `ro`, apoi `latin`; `id` unic și cu formatul slug; `latin` unic și de forma `Genus species` / `Genus x species` (opțional `subsp.`/`var.`), fără autor; niciun `latin_synonyms` egal cu `latin`-ul altei specii sau repetat la două specii; `ro` absent din propriul `ro_regional`; `en` absent din `en_alt`; `en_alt == []` când `en == ""`; fără duplicate în liste; `family` terminată în `-aceae`; niciun termen cu virgulă. (`ro` **nu** trebuie să fie unic, D7.)

### 7. Etapa E3 — lista speciilor

- **7.1. Farmacopeea Română** (sursa 1, D8). Lista monografiilor de produse vegetale din FR X și din suplimentele ei, fiecare tradusă în specia sau speciile-sursă (3.6). Farmacopeea nu e în corpus, deci lista se face **din cunoștințele mele**; în raport sursa apare ca „FR X”, iar dacă adaugi ulterior textul Farmacopeei în corpus, lista se poate verifica automat față de el. Toate speciile intră, indiferent de origine (D4).
- **7.2. „Dicționarul plantelor de leac”** (sursa 2). Script one-off `src/scripts/herbs_work/extract_dictionary_candidates.py` citește `data/documents/Surse sigure/Dictionarul plantelor de leac/Dictionarul-Plantelor-de-Leac.pdf.md` (380 de titluri `###`, 369 cu „Denumire științifică”, 225 cu „Denumiri populare”) și scrie titlul, numele latin și denumirile populare din carte.
- **7.3. Restul corpusului** (sursa 2). Script one-off `src/scripts/herbs_work/scan_corpus_names.py` caută în toate documentele din `data/documents`:
  - binoame latine (`Genus species`), validate prin GBIF species match (numele există în regnurile Plantae, Fungi sau Chromista — algele brune sunt în Chromista, lichenii în Fungi), ca să nu intre fals pozitive precum „Homo sapiens” sau fraze în latină;
  - denumiri românești de plante: după ce lista din 7.1–7.2 există, toate denumirile ei (`ro`, `ro_regional`) se caută în corpus, ca să apară și documentele care numesc o plantă doar românește; titlurile de documente și secțiuni care nu se potrivesc cu nicio specie cunoscută intră într-o listă de verificat (de ex. `Plante si remedii/Coada-soricelului.md`);
  - pentru fiecare specie: documentele în care apare și un fragment de context, ca să se poată verifica **utilizarea medicinală explicită** (D13). Speciile pomenite doar culinar sau în treacăt nu intră.
  - Toate speciile din corpus cu utilizare medicinală intră, indiferent de origine (D4).
- **7.4. Completări** (sursa 3): speciile din monografiile EMA/HMPC (listă publică) și din literatura românească de floră medicinală, care nu sunt deja în listă. Aici se aplică **filtrul de origine** din D4: intră doar cele spontane sau cultivate în România (inclusiv în ghiveci).
- **7.5.** Toate listele se unesc într-un singur fișier, deduplicat după numele latin acceptat (după 8.1, ca un sinonim vechi din carte și numele acceptat din EMA să devină aceeași specie).
- **7.6. Punct de control (D15):** înainte de completarea câmpurilor, primești lista completă în **`tmp/herbs_candidates.jsonl`**, o specie pe linie:

  ```json
  {"latin": "Crataegus monogyna", "ro": "Paducel", "group": "planta", "origin": "spontan", "sources": ["FR X", "corpus:3", "EMA"], "corpus_documents": ["Surse sigure/Dictionarul plantelor de leac/Dictionarul-Plantelor-de-Leac.pdf.md"]}
  ```

  `group` și `origin` există **doar** în lista de review (D12), nu și în `herbs.jsonl`. Scoți liniile cu speciile pe care nu le vrei (sau îmi spui care) și adaugi ce lipsește. Ordinul de mărime estimat: câteva sute de specii, posibil peste o mie.

### 8. Etapa E4 — popularea câmpurilor și verificarea taxonomică

- **8.1. Taxonomie.** Script `src/scripts/herbs_work/verify_taxonomy.py`; răspunsurile se păstrează în `tmp/herbs_work/gbif_cache.json`, ca rulările repetate să nu mai facă cereri. Se trimit doar numele speciilor. *La implementare (E3):* API-ul POWO e protejat de o verificare anti-bot Cloudflare, deci nu se folosește; numele acceptat vine din GBIF Backbone, iar prezența în România din setul **WCVP** (World Checklist of Vascular Plants, Kew), publicat în GBIF (`species/{key}/distributions`, `TDWG:ROM`), plus numărul de observații GBIF din România. Surse, toate API-uri publice gratuite, fără cheie:
  - **plante vasculare:** Plants of the World Online (Kew, POWO) — nume acceptat, familie, distribuție;
  - **ciuperci, licheni, mușchi, alge:** GBIF Backbone (care integrează Index Fungorum / MycoBank / AlgaeBase) — nume acceptat, familie;
  - dacă numele e sinonim, `latin` devine numele acceptat, iar cel vechi trece în `latin_synonyms`.
- **8.2. Originea** (pentru raport și pentru filtrul D4 al completărilor din 7.4):
  - plante vasculare spontane: distribuția POWO pentru România (`native` sau `introduced`);
  - ciuperci, licheni, mușchi, alge: înregistrări GBIF cu `country=RO` (pentru alge: și Marea Neagră, litoralul românesc);
  - plante cultivate (inclusiv în ghiveci): POWO nu acoperă culturile, deci se marchează „cultivat”;
  - speciile din FR X și din corpus care nu cresc în România se marchează „importat” și **rămân** în catalog (D4).
- **8.3. Denumiri românești.** `ro` = numele uzual din Farmacopee, din corpus sau din literatura românească de specialitate; mai multe specii pot avea același `ro` (D7). `ro_regional` = denumirile populare din corpus plus cele pe care le știu sigur (D14). Fără diacritice (D5); cratimele se păstrează după DOOM. Pentru speciile importate fără nume românesc consacrat, `ro` = numele folosit în comerțul și literatura românească (de ex. „Scortisoara”, „Ghimbir”).
- **8.4. Denumiri englezești.** `en` = numele englezesc uzual cel mai răspândit, `en_alt` = alte nume uzuale, din cunoștințele mele (D14), verificate unde se poate cu POWO / BSBI / PFAF pentru plante și cu listele British Mycological Society / British Lichen Society pentru ciuperci și licheni. **Dacă nu există un nume uzual, `en = ""` și `en_alt = []`** (D10) — nu se inventează traduceri și nu se pune numele latin.
- **8.5. Completarea pe loturi.** Lista aprobată la 7.6 se completează pe loturi (de ex. ~100 de specii, pe grupuri: plante vasculare A–F, G–M…, apoi ciuperci, licheni, mușchi, alge); fiecare lot trece testele din 6.4 înainte să fie adăugat în `herbs.jsonl`.
- **8.6. Raport de verificare** `tmp/herbs_review.md`, generat de `src/scripts/herbs_work/audit_herbs.py` (scriptul rămâne în repo, ca `audit_conditions.py`; scripturile one-off din `herbs_work/` se șterg la final):
  - totaluri pe grup (plante vasculare, ciuperci, licheni, mușchi, alge) și pe origine (spontan, cultivat, importat);
  - sursa fiecărei specii (FR X, corpus — cu numărul de documente —, EMA/HMPC, literatură românească);
  - pentru fiecare specie, care denumiri vin din corpus și care din cunoștințele mele (D14);
  - speciile cu nume latin schimbat de verificarea taxonomică (vechi → nou);
  - completările din 7.4 fără origine confirmată în România;
  - speciile cu `en` gol;
  - grupurile de specii cu același `ro` și denumirile din `ro_regional` comune mai multor specii (D7).
- **8.7.** `herbs.jsonl` se scrie sortat (3.1) și trece testele din 6.4.

### 9. Ordinea etapelor

Nu fac commit-uri (D16); la sfârșitul fiecărei etape îți spun ce s-a schimbat și ce verificări au trecut.

| Etapă | Conținut | Gata când |
|---|---|---|
| **E1** | conversie + `parse_conditions()` JSONL + config + Dockerfile + teste + scripturi audit + documentație; .txt și `conditions_work/` șterse | A1, A2, A3 |
| **E2** | `herbs.py`, `HERBS_FILE`, teste pe fixture | testele unitare trec |
| **E3** | lista speciilor (`tmp/herbs_candidates.jsonl`), aprobată de tine (7.6) | aprobare |
| **E4** | `herbs.jsonl` complet (pe loturi) + `COPY` în Dockerfile + testul pe fișierul livrat fără `skip` + `audit_herbs.py` + raport | A4, A5 |

----------------------------------------------------------------------------------------------------

## Partea III — Verificare și riscuri

### 10. Criterii de acceptare

| # | Criteriu | Cum se dovedește |
|---|---|---|
| A1 | Dicționarul din JSONL e **identic** cu cel din .txt (aceleași nume, aceiași termeni, aceeași ordine) | round-trip-ul din 5.1 |
| A2 | Fragmentele sunt identice, deci **nu e nevoie de reindexare** | `src/scripts/fragment_report.py` rulat înainte și după dă ieșire identică |
| A3 | `grep -rn "medical_conditions.txt"` nu mai găsește nimic în cod, configurare, Docker, teste sau documentația curentă; `src/scripts/conditions_work/` nu mai există | căutare în repo (planurile vechi din `architecture/` pot pomeni fișierul) |
| A4 | `herbs.jsonl` conține toate speciile aprobate la 7.6 și trece toate regulile din 6.4 | `pytest src/tests/unit/ai/test_herbs.py` + comparație cu lista aprobată |
| A5 | Fiecare `latin` e acceptat în POWO / GBIF; fiecare completare din 7.4 are origine confirmată în România sau e aprobată explicit în raport | raportul din 8.6 |

### 11. Riscuri

- **R1. Diferențe ascunse la conversie** (spații, termeni deduplicați diferit). Acoperit de round-trip-ul pe obiecte `Condition`, nu pe text, și de A2.
- **R2. Fișier JSONL editat manual greșit** (o virgulă lipsă strică o linie). `ValueError` cu numărul liniei la încărcare, plus testele pe fișierul livrat.
- **R3. Lista Farmacopeei fără document.** FR X nu e în corpus, deci lista din 7.1 nu se poate verifica automat. Atenuare: sursa e marcată separat în raport; dacă textul Farmacopeei ajunge în corpus, scanarea din 7.3 o confirmă sau o corectează.
- **R4. Volum.** Catalogul poate depăși o mie de specii. Atenuare: sursele sunt închise (D8), lista se aprobă înainte de completare (7.6), iar completarea merge pe loturi verificate (8.5).
- **R5. Denumiri din cunoștințele mele** (D14). Denumirile regionale sunt partea cea mai greu de verificat, iar riscul crește cu volumul. Atenuare: adaug doar ce știu sigur, iar raportul separă denumirile din corpus de celelalte, pentru verificare prin sondaj.
- **R6. Nume latine învechite în corpus și în Farmacopee.** Ambele folosesc nomenclatură veche (`Aloe vulgaris`, `Ribes grossularia`, `Crataegus oxyacantha`); verificarea taxonomică le mută în `latin_synonyms`, deci rămân căutabile.
- **R7. Utilizarea medicinală în corpus** (D13) se judecă pe context. Atenuare: lista de review are documentele fiecărei specii, deci poți verifica orice caz îndoielnic.
- **R8. Fals pozitive la scanarea corpusului** (7.3): binoame care nu sunt specii sau titluri care nu sunt plante. Atenuare: validarea GBIF pe regn și aprobarea listei la 7.6.
- **R9. Prezența ciupercilor, lichenilor și algelor în România** e mai slab documentată decât la plantele vasculare. Contează doar pentru completările din 7.4; speciile neconfirmate nu se elimină automat, ci intră în raport.
- **R10. API-uri externe indisponibile.** Verificarea taxonomică e o unealtă de dezvoltare, nu rulează în aplicație; cache-ul permite reluarea fără cereri noi.
