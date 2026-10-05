# Plan: completarea `medical_conditions.jsonl` din CIM-10 (ICD-10), pe litere

**Stare:** aprobat (2026-10-05: Î1 da, Î2 da, Î3 da). Pasul 0 făcut. Pasul 1 (A) făcut și refăcut după D4 revizuit: **79 de afecțiuni cu nume la A** adăugate (5469 → 5548), raport în `tmp/icd10_work/report_A.md`. **Pașii 2–26 făcuți** (2026-10-05), la cererea ta în paralel, fiecare literă pe branch-ul ei, cu câte un PR (§10): **+736 de afecțiuni** după unire (5548 → 6284), raport general în `tmp/icd10_work/report_total.md`. Cele 22 de afecțiuni din `pending_by_letter.jsonl` au intrat la literele lor. Rămân: deciziile din §10.4 și reindexarea (7.5).

**Scop:** pentru fiecare literă din alfabetul englez (A–Z, 26 de pași) se caută în CIM-10, în limba română, toate bolile și afecțiunile care încep cu acea literă și **nu** există în `data/medical_conditions.jsonl`. Ce se găsește se adaugă în fișier, cu sinonime în română și în engleză. Regulile actuale ale proiectului despre gruparea mai multor afecțiuni într-una singură rămân valabile (§3).

Planul are trei părți: **[Partea I — Decizii și reguli](#partea-i--decizii-și-reguli)**, **[Partea II — Cei 26 de pași](#partea-ii--cei-26-de-pași)** și **[Partea III — Verificare și riscuri](#partea-iii--verificare-și-riscuri)**.

----------------------------------------------------------------------------------------------------

## Partea I — Decizii și reguli

### 1. Decizii

| # | Decizie |
|---|---|
| D1 | **Sursa românească:** *Lista tabelară a diagnosticelor RoDRG v1* (CIM-10-AM, ediția a treia, traducerea Centrului de Statistică Sanitară și Documentare Medicală), PDF de ~22,5 MB publicat pe `hosptm.ro`. E clasificarea folosită oficial în spitalele din România. Descărcarea se face doar după acordul tău (pasul 0) |
| D2 | **Sursa englezească, pe cod:** pentru fiecare cod CIM-10 se ia titlul englezesc al aceluiași cod din ICD-10-CM (CMS, domeniu public). Codurile de 3 și 4 caractere coincid în mare parte între CIM-10-AM, ICD-10 OMS și ICD-10-CM, deci titlul englezesc vine din cod, nu dintr-o traducere. Unde codul nu există în ICD-10-CM, titlul englezesc se scrie din cunoștințele mele |
| D3 | **Capitole incluse:** I–XVII (`A00`–`Q99`): infecții, neoplasme, sânge și imunitate, endocrine și metabolice, psihice, nervos, ochi, ureche, circulator, respirator, digestiv, piele, osteoarticular, genitourinar, sarcină (doar patologia ei), perinatal, malformații congenitale. **Excluse:** XVIII (`R`, simptome și semne), XIX (`S`–`T`, leziuni, traumatisme, intoxicații), XX (`V`–`Y`, cauze externe), XXI (`Z`, factori și contacte cu serviciile de sănătate), XXII (`U`, coduri speciale). Aceasta e regula din `SPEC.md`: fără simptome izolate, stări fiziologice, leziuni, proceduri. Intrările vechi de aceste tipuri (`Febra`, `Fractura`, `Intoxicatie cu arsenic`) rămân neatinse |
| D4 | **Litera unui pas = prima literă a numelui canonic al afecțiunii** (cerut de tine la 2026-10-05), după scoaterea diacriticelor (`Ă`, `Â` → A; `Î` → I; `Ș` → S; `Ț` → T). Candidații unei litere vin din codurile al căror titlu CIM-10 **sau** termen de includere începe cu litera; o afecțiune găsită la o literă, dar cu nume la alta, trece în `tmp/icd10_work/pending_by_letter.jsonl` și se adaugă la pasul literei ei („Tumora maligna a colonului” → `Cancer de ...`, deci la C) |
| D5 | **Unitatea de lucru = categoria de 3 caractere.** O subcategorie de 4 caractere devine intrare separată **doar** când numește o entitate clinică distinctă (alt tip, altă etiologie, eponim, alt organ). Nu devine intrare separată când precizează doar: o subzonă a aceluiași organ (`C18.0` cec, `C18.2` colon ascendent → „Cancer de colon”), o complicație sau o manifestare („cu comă”, „fără complicații”), lateralitatea, un episod, sau e reziduală („alte”, „nespecificată”). **De confirmat** (întrebarea Î2) |
| D6 | **Nu se modifică intrările existente:** nu li se adaugă sinonime, nu se redenumesc, nu se șterg. Un titlu CIM-10 care corespunde unei afecțiuni deja prezente sub altă formulare intră doar în raport (§5), ca posibilă completare ulterioară |
| D7 | **Fără punct de aprobare pe fiecare literă:** ce se găsește se adaugă direct, cum ai cerut. Excepție: după pasul 1 (litera A) mă opresc o dată, ca să verifici calitatea pe un lot real înainte de restul de 25 de pași. **De confirmat** (întrebarea Î3) |
| D8 | **Nu fac niciun commit.** Toate modificările rămân în arborele de lucru |
| D9 | **Nu pornesc reindexarea.** La final cresc `TEXT_REPR_VERSION` în `build_hybrid_index.py` (5 → 6), ca rularea ta să refragmenteze tot corpusul cu noile afecțiuni, și îți dau comanda |

### 2. Regulile de conținut (din `SPEC.md`, păstrate)

- **2.1.** O afecțiune = `{"name": ..., "synonyms": [...]}`, cu numele canonic în română, majusculă inițială, **fără diacritice**, **fără virgulă** în niciun termen, ASCII pur, un termen ≤ ~60 de caractere.
- **2.2.** Minimum **3 sinonime românești + 3 englezești** (testul „lines are complete” cere cel puțin 6). Termenii dintr-o linie sunt distincți după `_normalize()`.
- **2.3.** Sinonimele sunt reale: denumiri alternative, eponime, termeni vechi, traduceri consacrate, denumiri populare consacrate (`SPEC_POPULAR.md`). Sunt acceptate formulările descriptive echivalente, în stilul intrărilor existente („colectie purulenta abdominala”); **nu** se inventează nume. Titlul CIM-10 românesc (fără diacritice, dacă diferă de numele canonic) e primul sinonim românesc; titlul englezesc al codului (D2) e primul sinonim englezesc.
- **2.4.** Dacă o entitate reală nu poate primi 3 + 3 termeni reali, **nu se adaugă**; apare în raport la „sinonime insuficiente”.
- **2.5.** Numele canonic urmează stilul existent al fișierului, nu formularea administrativă CIM-10: `Cancer de X` / `Cancer X` (cu „tumora maligna a X” ca sinonim), `Boala X`, `Sindrom X`, singular, ordinea firească a cuvintelor. Calificativele CIM-10 („nespecificat”, „neclasificat altundeva”, „NCA”, „fără altă specificație”) nu intră niciodată în nume.

### 3. Regulile de grupare (din `conditions_work/`, păstrate)

Regulile vin din scripturile care au construit dicționarul (`collapse_variants.py`, `consolidate.py`, `consolidate_duplicates.py`, `merge_logic.py`, `drop_non_diseases.py`, acum în istoria git) și din testele „shipped dictionary”:

| # | Regulă | Exemplu |
|---|---|---|
| G1 | **Variantele temporale se grupează în boala de bază.** Un titlu care diferă de o afecțiune existentă doar prin `acut(a)`, `subacut(a)`, `cronic(a)`, `recurent(a)`, `recidivant(a)` la final **nu** e afecțiune nouă | `Amigdalita` conține deja `Amigdalita acuta` și `Amigdalita cronica` ca sinonime |
| G2 | **Excepția de la G1:** dacă nu există boala de bază și modalitatea face parte din numele consacrat, titlul rămâne afecțiune separată | `Leucemie limfoblastica acuta`, `Panencefalita sclerozanta subacuta` |
| G3 | **Aceeași boală sub alt nume = o singură intrare.** Un titlu care e numele canonic sau sinonimul unei afecțiuni existente (după `_normalize()`) există deja | `Influenza` → `Gripa`; `Sarcina ectopica` → `Sarcina extrauterina` |
| G4 | **Variantele de organ, localizare sau tip rămân separate** | `Abces renal` ≠ `Abces hepatic`; `Colita amibiana` ≠ `Colita ulcerativa` |
| G5 | **Asemănarea de nume singură nu grupează.** Două titluri se consideră aceeași boală doar dacă datele o dovedesc (termen comun, nume = sinonim) sau dacă sunt aceeași entitate medicală, nu doar pentru că seamănă | `Scleroza multipla primar progresiva` ≠ `... secundar progresiva` |
| G6 | **Un termen aparține unei singure afecțiuni.** Niciun sinonim nou nu poate fi deja termenul altei afecțiuni (testul `has_no_shared_terms`); dacă singurul termen disponibil e ocupat, se alege altul sau se renunță la el | `gusa` aparține doar de `Gusa` |
| G7 | **Numai boli.** Nu se adaugă simptome izolate, stări fiziologice, leziuni, proceduri, investigații (D3 și lista din `drop_non_diseases.py`) | fără „Diplopie”, „Hemoroidectomie” |
| G8 | **Granularitatea CIM-10** (D5): subcategoriile care doar detaliază o categorie se grupează în ea | `C18.0`–`C18.9` → o singură intrare |

### 4. Procedura comună a fiecărui pas (P1–P8)

Fiecare dintre cei 26 de pași aplică aceeași procedură pe litera lui:

- **P1. Extragere.** Din `tmp/icd10_work/icd10_ro.jsonl` (pasul 0) se iau codurile din capitolele incluse (D3) al căror titlu normalizat începe cu litera pasului, plus codurile cu titlul la altă literă care au un termen de includere la litera pasului; se adaugă și afecțiunile din `pending_by_letter.jsonl` cu litera pasului (D4).
- **P2. Filtrare.** Se elimină: titlurile de bloc și de capitol („Boli ale ...”, „Afectiuni ale ...”), categoriile reziduale („Alte ...”, „... nespecificat(a)”, „... neclasificat(a) altundeva”), codurile-asterisc de manifestare („X in boli clasificate altundeva”), sechelele („Sechele ale ...”) și tot ce încalcă G7. Fiecare eliminare are motivul ei în raport.
- **P3. Grupare CIM-10.** Subcategoriile de 4 caractere se grupează în categoria de 3 caractere sau rămân separate după D5 / G8. Rezultatul: lista de **entități candidate** ale literei.
- **P4. Potrivire cu dicționarul**, în ordine:
  1. **exactă:** numele candidat sau titlul CIM-10, după `_normalize()`, e numele sau sinonimul unei afecțiuni → **există** (G3);
  2. **temporală:** fără modalitatea finală, e o afecțiune existentă → **există** (G1);
  3. **echivalențe de formulare:** se rescrie formularea CIM-10 în formulările proiectului și se caută din nou (`tumora maligna a X` ↔ `cancer de X` / `cancer X` / `carcinom X` / `neoplasm X`; `boala X` ↔ `X`; genitiv ↔ adjectiv: „ale ficatului” ↔ „hepatic(a)”, „a rinichiului” ↔ „renal(a)”; singular ↔ plural);
  4. **aproximativă:** aceleași cuvinte-cheie fără cuvintele generice (`boala`, `sindrom`, `tulburare`, `tip`, `forma` ..., lista `GENERIC` din `merge_logic.py`), incluziune de cuvinte-cheie sau asemănare ≥ 0,75 → **posibil existent**. Aici decid manual, după G4 și G5, iar decizia și motivul ei intră în raport.
  
  Tot ce nu se potrivește e **nou**.
- **P5. Grupare între candidați.** Candidații noi ai literei se compară și între ei, și cu cei adăugați la literele anterioare, după G1–G5, ca aceeași boală să nu intre de două ori.
- **P6. Scrierea liniilor** după §2: nume canonic în stilul proiectului, ≥ 3 + 3 sinonime reale, G6 verificat pe tot fișierul. Numele canonic începe cu litera pasului; altfel linia merge în `pending_by_letter.jsonl` (D4).
- **P7. Inserare.** Liniile noi se inserează la locul lor, cu cheia de sortare existentă `(_normalize(name), name)` (cea din `consolidate.py`); restul fișierului rămâne identic octet cu octet. Formatul: `json.dumps(obj, ensure_ascii=False)`, LF, `\n` final.
- **P8. Verificare și raport.** Trec testele dicționarului (`src/tests/unit/ai/test_conditions.py`) și rulează `src/scripts/audit_near_dupes.py`; perechile noi semnalate de audit se verifică manual. Raportul literei se scrie în `tmp/icd10_work/report_<litera>.md` (§5). Dacă o literă nu are nimic nou, raportul spune asta și pasul se încheie fără modificări.

### 5. Raportul fiecărei litere

`tmp/icd10_work/report_<litera>.md` conține:

- numărul de coduri extrase, eliminate (pe motiv), entități candidate, existente, adăugate;
- **adăugate:** numele canonic, codul / codurile CIM-10 acoperite, sinonimele;
- **existente:** titlul CIM-10 → afecțiunea din dicționar și tipul potrivirii (exactă, temporală, echivalență, manuală) — aceasta e lista din care se pot adăuga ulterior sinonime noi (D6);
- **decizii manuale** la potrivirea aproximativă, cu motivul;
- **eliminate** (G7, reziduale, asterisc, sechele) și **sinonime insuficiente** (2.4).

### 6. Ce nu intră în acest plan

- adăugarea de sinonime la afecțiunile existente (D6; rapoartele pregătesc un pas ulterior);
- capitolele R, S–T, V–Y, Z, U (D3);
- codurile CIM-10 ca date în fișier (structura liniei rămâne `{"name", "synonyms"}`);
- reindexarea (D9) și commit-urile (D8).

----------------------------------------------------------------------------------------------------

## Partea II — Cei 26 de pași

### Pasul 0 — Pregătire (înainte de A)

- **0.1.** Cu acordul tău: descarc *Lista tabelară a diagnosticelor RoDRG v1* (D1) și fișierul de coduri ICD-10-CM de la CMS (D2) în `tmp/icd10_work/` (nu intră în repo).
- **0.2.** Script one-off `src/scripts/icd10_work/extract_icd10.py`: transformă PDF-ul în `tmp/icd10_work/icd10_ro.jsonl`, un cod pe linie: `{"code": "J10.1", "chapter": "X", "title_ro": "...", "title_en": "..."}` (`title_en` din ICD-10-CM, după cod). Verificări: fiecare capitol inclus are codurile de 3 caractere complete față de lista OMS; nu există coduri duplicate; titlurile rupte pe mai multe rânduri în PDF sunt reunite.
- **0.3.** Script `src/scripts/icd10_work/match_letter.py <litera>`: face P1–P5 automat (extragere, filtrare, grupare, potrivire în 4 niveluri) și scrie `tmp/icd10_work/candidates_<litera>.jsonl` cu verdictul fiecărei entități (`exista` / `posibil` / `nou` / `eliminat` + motiv). Deciziile manuale și scrierea liniilor (P4.4, P6) le fac eu, pe baza acestui fișier.
- **0.4.** Instantaneu al dicționarului înainte de pasul 1: `tmp/icd10_work/conditions-before.jsonl` (5469 de afecțiuni).
- **0.5.** Numărul de coduri pe literă (după D3 și D4), cu verdictul automat inițial al `match_letter.py`. *La implementare:* extragerea are 8191 de coduri, din care 1291 de categorii de 3 caractere — toate categoriile CIM-10-AM din `A00`–`Q99` (cele 43 de categorii ICD-10-CM fără corespondent sunt coduri doar americane). Titlurile din PDF au pierdut uneori literele cu diacritice („datorit”); numele canonice le scriu oricum manual.

  | Literă | Coduri | Eliminate | Există | De decis | | Literă | Coduri | Eliminate | Există | De decis |
  |---|---|---|---|---|---|---|---|---|---|---|
  | A | 2207 | 1615 | 111 | 481 | | N | 104 | 26 | 15 | 63 |
  | B | 317 | 30 | 62 | 225 | | O | 218 | 63 | 31 | 124 |
  | C | 509 | 107 | 95 | 307 | | P | 534 | 115 | 102 | 317 |
  | D | 520 | 23 | 64 | 433 | | Q | 0 | 0 | 0 | 0 |
  | E | 262 | 36 | 65 | 161 | | R | 157 | 17 | 19 | 121 |
  | F | 258 | 79 | 38 | 141 | | S | 647 | 96 | 172 | 379 |
  | G | 125 | 36 | 26 | 63 | | T | 729 | 119 | 92 | 518 |
  | H | 397 | 39 | 91 | 267 | | U | 58 | 19 | 14 | 25 |
  | I | 361 | 84 | 55 | 222 | | V | 77 | 18 | 18 | 41 |
  | J | 3 | 3 | 0 | 0 | | W | 0 | 0 | 0 | 0 |
  | K | 22 | 3 | 4 | 15 | | X | 4 | 0 | 2 | 2 |
  | L | 274 | 84 | 56 | 134 | | Y | 1 | 0 | 0 | 1 |
  | M | 397 | 53 | 77 | 267 | | Z | 9 | 2 | 3 | 4 |

  Literele B–Z se recalculează înaintea pasului lor (după filtrele rafinate la A și cu afecțiunile adăugate între timp), deci cifrele lor se vor schimba.
- **0.6.** *Adăugat la implementare:* `src/scripts/icd10_work/lookup.py` (verifică rapid dacă o listă de nume există, exact sau aproximativ), `apply_additions.py` (P7: validează G6, ≥ 3 + 3 sinonime, ASCII, fără virgulă și inserează sortat; nu scrie nimic dacă există o problemă) și `report_letter.py` (P8). Potrivirea automată verifică și **titlul englezesc** CIM-10 față de sinonimele englezești existente (la A, 7 boli existente sub alt nume românesc au fost prinse abia la validare: `Afachie`, `Amaurosis fugax` etc.).

### Pașii 1–26

Fiecare pas aplică P1–P8 pe litera lui. Coloana „Ce conține CIM-10” arată familiile tipice ale literei, iar „Atenție la” capcanele specifice. „Azi în fișier” = numărul de afecțiuni existente care încep cu litera.

| Pas | Literă | Azi în fișier | Ce conține CIM-10 (tipic) | Atenție la |
|---|---|---|---|---|
| 1 | **A** | 773 | Abces, Adenom, Alergie, Amiloidoza, Anemie, Anevrism, Angina, Anomalie (cap. XVII), Artrita, Artroza, Ateroscleroza, Atrofie | multe titluri „Alte ...” și „Afectiuni ale ...” (P2); „Anomalii ale X” vs „Malformatie X” existent (P4.3). **Punct de control** după acest pas (D7) |
| 2 | **B** | 356 | Boala X (eponime și boli de organ), Bronsita, Bronsiectazie, Bruceloza, Botulism | „Boli ale ...” sunt titluri de bloc; „Boala HIV care determina X” (`B20`–`B23`) se grupează în HIV (D5); „Boala X” ↔ „X” (P4.3) |
| 3 | **C** | 473 | Carcinom in situ, Cardiomiopatie, Cataracta, Ciroza, Colecistita, Colita, Conjunctivita, Coxartroza, Criptorhidie | majoritatea cancerelor apar la T („Tumora maligna”), nu la C; `Carcinom in situ al X` (`D00`–`D09`) e altă entitate decât cancerul invaziv (G4) |
| 4 | **D** | 364 | Dementa, Depresie, Dermatita, Diabet, Diaree, Discopatie, Displazie, Distrofie, Diverticuloza | „Diabet zaharat ... cu complicatii X” (`E10`–`E14` .0–.9) se grupează în tipul de diabet (D5); `Diaree` e simptom (G7) dacă nu e infecțioasă |
| 5 | **E** | 230 | Eclampsie, Eczema, Edem, Embolie, Emfizem, Encefalita, Endocardita, Endometrioza, Enterita, Epilepsie, Erizipel | „Encefalita/mielita/encefalomielita” în aceeași categorie (`G04`) — se separă doar entitățile distincte; `Edem` simplu e semn (G7) |
| 6 | **F** | 181 | Faringita, Febra (infecțioase: tifoida, Q, butonoasa), Fibroza, Fistula, Flebita, Foliculita | „Febra X” infecțioasă e boală, „Febra” simplă e simptom (G7); `Fistula` congenitală vs dobândită (G4) |
| 7 | **G** | 111 | Gastrita, Glaucom, Glomerulonefrita, Gonartroza, Gonoree, Guta, Gusa | subtipurile `N00`–`N08` sunt după aspect histologic, combinate cu sindromul — se grupează conform D5 |
| 8 | **H** | 335 | Hemofilie, Hemoroizi, Hepatita, Hernie, Hidronefroza, Hiperplazie, Hipertensiune, Hipertiroidie, Hipotiroidie | „Hepatita virala acuta B cu agent delta ...” — combinații grupate (D5); „Hernie ... cu ocluzie / cu gangrena” se grupează în hernie |
| 9 | **I** | 176 | Icter (neonatal), Ileus, Infarct, Infectie, Insuficienta (cardiaca, renala, respiratorie), Intoleranta | „Infectie cu X cu localizare nespecificata” e reziduală (P2); `Î` (Întârziere, Îngustare) intră aici (D4) |
| 10 | **J** | 2 | puține titluri | se așteaptă 0–2 candidați |
| 11 | **K** | 13 | Keratita, Keratoconjunctivita, Keratoconus, Kwashiorkor | „Keratita” vs „Cheratita” — aceeași boală, două grafii (G3) |
| 12 | **L** | 170 | Laringita, Leishmanioza, Lepra, Leucemie, Limfom, Lupus, Luxatie congenitala | `Luxatie` traumatică e exclusă (cap. XIX), cea congenitală rămâne; subtipurile de limfom/leucemie sunt entități distincte (G4) |
| 13 | **M** | 250 | Malaria, Melanom, Meningita, Miastenie, Miocardita, Mielom, Miopatie, Mononucleoza | `Malaria cu P. X` = entități distincte (G4); „Meningita in boli clasificate altundeva” = asterisc (P2) |
| 14 | **N** | 143 | Nefrita, Nefropatie, Neoplasm (benign/in situ), Neuropatie, Nevralgie, Nevrita | `Nevralgie` simplă poate fi simptom (G7); „Neoplasm cu evolutie incerta” (`D37`–`D48`) — entitate separată doar unde e uzuală |
| 15 | **O** | 109 | Obezitate, Ocluzie, Osteoartrita, Osteomielita, Osteoporoza, Otita, Otoscleroza | `Osteoporoza cu fractura patologica` se grupează în osteoporoză (D5); `Otita` / `Otita medie` sunt deja grupate (G3) |
| 16 | **P** | 489 | Pancreatita, Paralizie, Pneumonie, Poliartrita, Polip, Psoriazis, Purpura, Pielonefrita | „Pneumonie cu X” după agent = entități distincte (G4); `Paralizie` după cauză vs localizare (D5) |
| 17 | **Q** | 0 | aproape niciun titlu românesc | se așteaptă 0 candidați (codurile `Q` încep cu „Anomalie”, „Malformatie” etc.) |
| 18 | **R** | 104 | Rahitism, Retinopatie, Reumatism, Rinita, Rubeola, Rujeola | „Reumatism articular acut” = febra reumatică (G3); capitolul `R` (simptome) e exclus (D3), litera R nu |
| 19 | **S** | 760 | Sarcom, Scarlatina, Schizofrenie, Scleroza, Septicemie, Sifilis, Sindrom X, Spondiloza, Stenoza, Strabism | „Sindrom X” e cea mai mare familie — G5 strict; `Ș` (Șancru) intră aici (D4); „Sifilis ... secundar / tardiv / congenital” = stadii, se decide după D5 |
| 20 | **T** | 327 | Tumora maligna/benigna a X, Tetanos, Tiroidita, Tromboza, Tuberculoza, Tulburare (psihice) | **pasul cel mai mare probabil:** toate „Tumora maligna a X” (`C00`–`C97`) se mapează pe `Cancer de X` existent (P4.3) sau devin `Cancer de X` nou (2.5); „Tulburare X” din cap. V; `Ț` intră aici |
| 21 | **U** | 34 | Ulcer, Uretrita, Urticarie, Uveita | „Ulcer gastric acut/cronic cu hemoragie/perforatie” (`K25.0`–`K25.9`) se grupează în `Ulcer gastric` (G1, D5) |
| 22 | **V** | 49 | Varice, Varicela, Vasculita, Vitiligo, Vulvita, Volvulus | „Varice ale membrelor inferioare cu ulcer / cu inflamatie” se grupează (D5) |
| 23 | **W** | 0 | aproape niciun titlu românesc | se așteaptă 0 candidați; eponimele cu W (Waldenström, Whipple, Wilson) apar sub „Boala”/„Macroglobulinemie” |
| 24 | **X** | 15 | Xantom, Xeroderma pigmentosum, Xeroftalmie | puține, majoritatea probabil existente |
| 25 | **Y** | 2 | Yersinioza, Yaws (framboesia) | „Pian” / „Framboesia” = aceeași boală (G3) |
| 26 | **Z** | 3 | Zona zoster, Zigomicoza | `Zona zoster` ↔ `Herpes zoster` (G3) |

----------------------------------------------------------------------------------------------------

## Partea III — Verificare și riscuri

### 7. Verificarea finală (după pasul 26)

- **7.1.** Toată suita de teste trece (`pytest src/tests`), în special testele „shipped dictionary”.
- **7.2.** `src/scripts/audit_conditions.py` și `src/scripts/audit_near_dupes.py` pe fișierul final; perechile noi față de instantaneul 0.4 se verifică manual.
- **7.3.** Diff-ul față de `conditions-before.jsonl` conține **numai linii adăugate** (D6): nicio linie existentă modificată sau ștearsă.
- **7.4.** Raport general `tmp/icd10_work/report_total.md`: totaluri pe literă și pe capitol CIM-10, numărul de titluri CIM-10 găsite ca existente (candidații pentru sinonime ulterioare).
- **7.5.** `TEXT_REPR_VERSION` 5 → 6 în `src/scripts/build_hybrid_index.py` (D9) și îți dau comanda de reindexare. După rularea ta: `src/scripts/evaluate_retrieval.py` comparat cu ultima evaluare, ca să se vadă efectul afecțiunilor noi asupra căutării.
- **7.6.** Scripturile one-off din `src/scripts/icd10_work/` se șterg după ce confirmi rezultatul; `tmp/icd10_work/` rămâne local.

### 8. Riscuri

| Risc | Măsură |
|---|---|
| Extragerea din PDF rupe sau lipește titluri | Verificarea 0.2 (codurile de 3 caractere complete, fără duplicate); titlurile suspecte (prea lungi, fără literă mare) intră în raport |
| Formularea administrativă CIM-10 nu se potrivește exact cu dicționarul (`Tumora maligna a colonului` vs `Cancer de colon`) → duplicate | Potrivirea în 4 niveluri (P4), cu echivalențele de formulare și decizia manuală pe „posibil existent”; `audit_near_dupes.py` la fiecare literă |
| Explozie de intrări prea fine (subzone, complicații) | D5 / G8: categoria de 3 caractere e unitatea implicită |
| Sinonime inventate ca să ajungă la 3 + 3 | 2.3–2.4: fără sinonime reale, afecțiunea nu se adaugă și apare în raport |
| Un sinonim nou e deja termenul altei afecțiuni | G6, verificat la P6 și de testul `has_no_shared_terms` |
| Afecțiunile noi schimbă etichetarea fragmentelor și scorurile | Reindexarea o pornești tu (D9); evaluarea 7.5 arată efectul |
| Codurile CIM-10-AM pot diferi ușor de ICD-10 OMS la unele coduri | Titlul englezesc se ia pe cod (D2); unde codul lipsește din ICD-10-CM, se scrie manual și se marchează în raport |

### 9. Întrebări deschise

- **Î1.** Accepți descărcarea celor două surse (D1: PDF RoDRG v1, ~22,5 MB, `hosptm.ro`; D2: codurile ICD-10-CM, CMS)?
- **Î2.** Granularitatea D5 (categoria de 3 caractere implicit, subcategoriile doar când sunt entități distincte) e cea dorită?
- **Î3.** Punctul de control după litera A (D7) — da sau nu?

### 10. Execuția pașilor 2–26 (adăugat la implementare)

- **10.1. În paralel.** Ai cerut (2026-10-05) ca pașii rămași să ruleze în paralel, pe branch-uri diferite, cu câte un PR pe branch: B pe `claude/elegant-allen-thlr5k`, C–Z pe `claude/icd10-litera-<L>`, plus `claude/icd10-finalizare` (completarea literei A, acest plan, `TEXT_REPR_VERSION` 5 → 6, `report_total.md`). D8 (fără commit) e înlocuit de această cerere.
- **10.2. Amânatele, fără `pending_by_letter.jsonl` comun.** Fiecare literă a scris afecțiunile cu nume la altă literă în `tmp/icd10_work/pending_from_<L>.jsonl` (D4). La unire, cele deja adăugate de litera-țintă au fost eliminate (31), restul (94) au fost verificate pe dicționarul unit și adăugate cu un commit în plus pe branch-ul literei lor.
- **10.3. Unirea.** Dublurile apărute între litere (aceeași boală sub două nume, pe branch-uri diferite: 6) și termenii comuni (G6: 2) au fost corectați pe branch-ul care nu avea titlul CIM-10; detaliile în `report_total.md` și în `notes_<L>.md`. Dicționarul unit trece `test_conditions.py`, iar perechile noi din `audit_near_dupes.py` sunt toate de tip bază ⊂ subtip (G4).
- **10.4. De decis:** parafiliile (F65), intrările la limita G7 și corecturile propuse pentru liniile existente (D6) — listele în `report_total.md`.
- **10.5. Ordinea de integrare a PR-urilor.** Toate modifică `data/medical_conditions.jsonl` în zone diferite; două litere vecine care inserează la aceeași graniță (ultima linie a uneia, prima a celeilalte) dau conflict la al doilea PR integrat. Se rezolvă păstrând ambele linii în ordinea sortată. `claude/icd10-finalizare` se integrează ultimul (reindexarea forțată).
