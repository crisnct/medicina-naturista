# Plan: compactarea surselor pentru payload-ul AI (`scripts/clean_documents.py`) — deepseek

**Obiectiv:** sursele din `data/documents/` (recursiv) să aibă semnificativ mai puține caractere, fără să se piardă informație medicală, ca fragmentele trimise la AI să coste mai puțini tokeni.

**Rezultat măsurat pe corpusul real** (prototip rulat pe toate cele 387 de fișiere, tokenizer `intfloat/multilingual-e5-small` ca proxy local):

| Metrică | Înainte | După | Diferență |
|---|---|---|---|
| Caractere | 17.657.659 | 17.431.608 | **−1,28%** |
| Bytes UTF-8 | 18.420.650 | 17.479.195 | **−5,11%** |
| Tokeni (proxy) | 4.856.078 | 4.617.234 | **−238.844 (−4,92%)** |
| Fișiere modificate | — | 283 din 387 | — |
| Cifre pierdute | — | **0** | invariantă verificată |
| Titluri pierdute | — | **0** | structura de fragmentare intactă |
| Fișiere ne-idempotente | — | **0** | a doua rulare nu mai schimbă nimic |

Diferența dintre −1,28% caractere și −5,11% bytes este efectul folding-ului de diacritice: `ă/â/î/ș/ț` sunt 2 bytes în UTF-8, iar `a/i/s/t` este 1 byte. Tokenii scad mai mult decât caracterele pentru că textul ASCII se tokenizează mai eficient.

---

## 1. Ce am măsurat pe corpus (și ce a infirmat analiza)

387 fișiere, 17,7M caractere, ~2,8M cuvinte, ~4,86M tokeni. Distribuția e extrem de concentrată: **5 fișiere = 50%** din volum, 24 = 80%, 65 = 90%. Cel mai mare fișier (Balch — *Vindecare prin nutriție*, 4,34M caractere) e text OCR cu rânduri rupte la ~60 de caractere.

**Ce NU ajută** (măsurat, ca să nu pierdem timp cu ele):

| Idee intuitivă | Măsurat | Concluzie |
|---|---|---|
| Refacerea paragrafelor rupte (hard-wrap → paragraf) | 157.314 rânduri, **0 tokeni** economisiți | tokenizer-ul absoarbe `\n` în tokenul următor; nu merită riscul |
| Deduplicare de paragrafe între fișiere | 39 paragrafe, 18.261 caractere (**0,10%**) | neglijabil |
| Tabele / liste | 3,9% din caractere | nu merită reformatare |
| Eliminarea liniilor de tip „Sursa:” | 564 caractere | neglijabil |

**Ce ajută** (și e în plan): headerele repetate (185.451 caractere), Cuprinsul (30.650), liniile cu număr de pagină (6.506), colofonul (2.806) și folding-ul diacriticelor (−176.312 tokeni singur).

---

## 2. Decizii (din răspunsurile tale)

| Decizie | Alegere | Consecință |
|---|---|---|
| Nivel de agresivitate | Reguli deterministe + eliminarea secțiunilor ne-informative | fără condensare AI, fără rescriere de text |
| Cărți marginale (Hawkins, Vaccinarea, Lipton, Cristaloterapie) | **rămân în index** | se renunță la cea mai mare economie (estimat 35–50%) |
| Fragmente R1/R2 uriașe (max 75.478 caractere ≈ 20k tokeni) | **nu se modifică `ai/fragmenter.py`** | planul se limitează la `clean_documents.py` |
| Diacritice | **se convertesc la ASCII în tot corpusul** | text „sanatate” în loc de „sănătate” |
| Aplicare | **in-place, cu git ca backup** | distructiv, dar cu diff complet în git |
| Verificări | invariantă de cifre + evaluare retrieval înainte/după | nu se adaugă rapoarte per fișier sau eșantion uman |
| Protejat obligatoriu | cifre/doze/unități, denumiri, contraindicații, pași de preparare, titluri | nicio regulă nu are voie să atingă aceste elemente |

**Regulile pe care le-ai aprobat și care, în acest corpus, nu găsesc nimic de eliminat** (rămân în cod, pentru fișiere viitoare): secțiuni de tip `Index`/`Glosar` și `Bibliografie`/`Referințe`. Motivul, dovedit pe fișiere reale:

- `Diverse/Cristaloterapie/Cristale-M-Z.md` → `## REFERINȚE ȘI ANEXE` (85.522 caractere) conține **conținut** („Semnificația pietrelor prețioase…”), nu o bibliografie;
- `Marele dicționar al bolilor…` → `## INDEX` (2.367 caractere) este chiar **articolul de dicționar** pentru termenul „Index” („Stomacul este locul în care corpul meu fizic asimilează mâncarea…”), nu indexul cărții;
- `Vindecare prin nutritie.md` → `## Surse` (14.309 caractere în 4 secțiuni) listează **sursele alimentare de fier/minerale** — informație medicală valoroasă, care ar fi fost distrusă de un tipar naiv de „bibliografie”.

Aceste trei cazuri sunt motivul pentru care planul folosește teste de **formă și poziție**, nu potriviri de cuvinte-cheie.

---

## 3. Ordinea de aplicare (contează)

```
_read()                          # decodare + normalizare LF (neschimbat)
  → regulile existente           # metadata extracție, markere pagină, linkuri/email/„Vezi și”
  → FOLDING DIACRITICE           # ÎNTÂI, înaintea numărării liniilor repetate
  → secțiuni de mobilier         # Cuprins / Index / Glosar / Bibliografie
  → colofon / front-matter
  → linii doar cu număr de pagină
  → headere repetate (≥5 apariții)
  → colaps linii goale
  → verificarea invarianței cifrelor → scriere
```

**De ce folding-ul e primul:** prototipul care îl aplica la final nu era idempotent pe 3 fișiere (`Sanatate-Din-Farmacia-Domnului`, `Vindecare prin nutritie`, `bruce_lipton_biologia_credintei`) — după folding, linii care diferă doar prin diacritice deveneau identice și abia a doua rulare le număra ca headere repetate. Cu folding-ul primul, o singură rulare ajunge la punct fix (verificat: 0 fișiere ne-idempotente).

---

## 4. Regulile noi, cu condițiile exacte

### 4.1. Headere/running titles repetate — **cel mai mare câștig: 185.451 caractere**

Titlul cărții sau al capitolului, repetat pe fiecare pagină de conversia PDF, este cea mai mare sursă de redundanță (126.827 caractere doar în cartea Balch).

Se elimină toate aparițiile unei linii **cu excepția primei**, dacă:
- linia are ≥ 20 de caractere după `strip()`;
- apare de **≥ 5 ori** în același fișier (prag care nu poate fi atins întâmplător de conținut);
- **nu conține o doză strictă** (`\b\d+([.,]\d+)?\s*(mg|mcg|µg|ml|kg|picături|lingură/lingurițe|capsule|comprimate)\b`) — o linie cu dozaj nu este niciodată mobilier;
- nu conține cuvinte de avertizare (`atenție`, `contraindic`, `avertisment`, `toxicit`).

### 4.2. Secțiuni de mobilier: Cuprins, Index/Glosar, Bibliografie — **30.650 caractere (doar Cuprins, în acest corpus)**

O secțiune e eliminată **numai dacă toate condițiile sunt adevărate**:

1. titlul e potrivit de tiparul de mobilier, la început de linie: `cuprins|cuprinsul|sumar|table of contents|conținut|con[țt]inut`, `index|index alfabetic|glosar|glossary|abrevieri`, `bibliografie|bibliography|referințe|references|note bibliografice|surse bibliografice|lecturi recomandate`;
2. titlul e **neambiguu**: nu conține `și`, `and`, `&`, `+`, `anex`, `plus`, `cuprinde` (astfel `REFERINȚE ȘI ANEXE` rămâne conținut);
3. pentru `Index`/`Glosar`/`Bibliografie`: titlul e în **ultimele 20%** din fișier (un index real e la sfârșit; `## INDEX` din dicționar e la mijloc → păstrat);
4. blocul are > 120 caractere și **nu conține nicio doză strictă**;
5. **densitatea de intrări ≥ 30%**: cel puțin 30% dintre liniile ne-goale se termină cu un număr de pagină sau cu puncte de umplere (`.......`).

Secțiunea se întinde de la titlu până la primul titlu de nivel egal sau superior (funcția `section_end()`).

### 4.3. Colofon / front-matter — **2.806 caractere**

Se elimină liniile de credit editorial, doar dacă au < 200 caractere și se află în **primele 300 de linii** ale fișierului sau încep cu un tipar puternic (`©`, `(c) 2014`, `ISBN`, `ISSN`, `Descrierea CIP`, `Toate drepturile`, `All rights reserved`, `Tehnoredactare`, `Corector`, `Copertă`, `Redactor`, `Traducere`, `Tipărit`, `Ediția a`).

Restricția de poziție e intenționată: fără ea, orice linie de conținut care pomenește „editura” ar fi dispărut. Varianta agresivă ar fi tăiat 42.884 caractere, dar cu risc de a pierde text medical — am ales varianta sigură, cu câștig mic.

### 4.4. Linii care conțin doar numărul paginii — **6.506 caractere**

Se elimină liniile care, după `strip()`, conțin exclusiv: un număr (eventual cu liniuțe), `pagina N`/`pag. N`, sau un numeral roman. Testul existent `test_keeps_headings_that_merely_mention_pagina` rămâne valid: `### Pagina de start` nu e o linie de număr.

### 4.5. Folding diacritice → ASCII — **−176.312 tokeni (−3,63%) singur**

`ă â î ș ț Ă Â Î Ș Ț ş ţ Ş Ţ ã Ã → a a i s t A A I S T s t S T a A`.

Argumente de siguranță:
- căutarea lexicală folosește deja `to_tsvector('simple', unaccent(...))`, iar dicționarul de afecțiuni e scris fără diacritice — potrivirea afecțiunilor trece prin `plain()` (NFKD + eliminare de semne diacritice), deci **nu se schimbă**;
- structura (titluri, niveluri) nu se atinge;
- cifrele, unitățile și denumirile latine nu conțin diacritice românești, deci rămân identice.

Se adaugă steagul `--keep-diacritics` ca supapă de revenire rapidă.

### 4.6. Regulile existente rămân neatinse

`strip_extraction_metadata()`, `strip_page_markers()`, `clean_text()` (linkuri, emailuri, „Vezi și”, caractere invizibile, cedile), `collapse_blank_lines()` și logica de scriere cu păstrarea codării originale. Nimic din ce funcționează azi nu se rescrie; regulile noi se adaugă în aceeași conductă.

---

## 5. Garanția de siguranță: invarianta cifrelor

Cerința ta: „nicio doză/cantitate nu dispare”. Implementată ca **invariantă verificată înainte de scriere**, nu ca raport:

```
numere(text_înainte)  ==  numere(text_după)  ⊎  numere(spans_eliminate)
```

- `numere(x)` = multisetul de potriviri `\d+(?:[.,]\d+)?` din text;
- `spans_eliminate` = textul exact scos de fiecare regulă whitelistată (secțiune, linie de colofon, linie de pagină, header repetat, link/email).

Dacă un număr lipsește din textul final **și** nu apare în spans-urile eliminate, fișierul **nu se scrie**, se afișează numărul și numele fișierului, iar scriptul iese cu cod ≠ 0. Astfel, o regulă viitoare care ar tăia din greșeală „500 mg” din textul rămas nu poate trece neobservată.

Verificat pe corpus: **0 violări** (387 de fișiere).

---

## 6. Interfața scriptului

| Steag | Efect |
|---|---|
| `--source PATH` | rădăcina (implicit `data/documents`) — neschimbat |
| `--dry-run` | listează fișierele care s-ar schimba, fără să scrie — neschimbat |
| `--keep-diacritics` | **nou**: dezactivează 4.5 (pentru revenire sau comparații) |
| `--stats` | **nou**: la final, un sumar unic (nu per fișier): fișiere modificate, caractere și bytes eliminate, caractere eliminate pe fiecare regulă, violări |

Ieșirea rămâne o linie per fișier modificat (`Cleaning: <cale>`), plus sumarul. Cod de ieșire: `0` normal, `1` dacă există violări ale invarianței cifrelor sau erori.

---

## 7. Modificări în cod

Toate în `scripts/clean_documents.py` (singurul fișier de producție atins), plus `scripts/clean_documents.ps1` pentru pass-through-ul steagurilor noi.

Funcții noi:

| Funcție | Rol |
|---|---|
| `fold_diacritics(text) -> str` | 4.5 |
| `section_end(lines, start, level) -> int` | sfârșitul unei secțiuni, după nivelul titlului |
| `entry_density(lines) -> float` | proporția de linii de tip „intrare în cuprins” |
| `is_furniture_section(lines, position_ratio, kind) -> bool` | condițiile 1–5 din 4.2 |
| `strip_furniture_sections(text) -> tuple[str, list[Removed]]` | 4.2 |
| `strip_colophon_lines(lines) -> tuple[list[str], list[Removed]]` | 4.3 |
| `strip_page_number_lines(lines) -> tuple[list[str], list[Removed]]` | 4.4 |
| `strip_repeated_lines(text) -> tuple[str, list[Removed]]` | 4.1 |
| `numbers(text) -> Counter[str]` | invarianta din §5 |
| `check_digit_invariant(before, after, removed) -> list[str]` | §5 |

`Removed` = `(rule: str, text: str)` — folosit și pentru invariantă, și pentru sumarul `--stats`.

`clean_documents()` devine: `_read` → regulile existente → `fold_diacritics` → cele patru reguli noi → `collapse_blank_lines` → `check_digit_invariant` → scriere, cu acumularea statisticilor.

---

## 8. Teste

Extindere în `tests/unit/ai/test_clean_documents.py` (testele existente rămân valide; `test_never_changes_line_count` continuă să treacă, fiindcă fișierul lui de test nu atinge nicio regulă nouă):

1. `## Cuprins` cu puncte de umplere și numere de pagină → secțiunea dispare, iar textul de după următorul titlu de nivel 2 rămâne;
2. `## INDEX` aflat la mijlocul fișierului, cu text de proză → **păstrat**;
3. `## REFERINȚE ȘI ANEXE` → **păstrat** (titlu ambiguu);
4. `## Bibliografie` la sfârșit, cu ≥30% linii terminate în număr → eliminat;
5. linie repetată de 5 ori → eliminate toate copiile în afară de prima; linie repetată de 4 ori → neatinsă;
6. linie repetată care conține „500 mg” → **niciodată** eliminată;
7. `### Pagina 8` → eliminată; `### Pagina de start` → păstrată (deja existent);
8. linii de colofon în primele 300 de linii → eliminate; aceeași linie la mijlocul fișierului → păstrată;
9. diacritice: `Coadă, șoricel, țuică` → `Coada, soricel, tuica`; cu `--keep-diacritics` → neschimbat;
10. invarianta cifrelor: caz sintetic construit manual (`before`, `after`, `removed`) în care un număr dispare fără să fie în spans → `check_digit_invariant()` îl raportează;
11. idempotență: `clean_documents()` rulat de două ori → al doilea apel raportează 0 fișiere modificate și nu atinge `mtime`;
12. titlurile rămân intacte: pentru un fișier cu titluri pe mai multe niveluri, multisetul de titluri (foldat) e identic înainte/după.

---

## 9. Cum se rulează (rollout)

1. **Backup:** commit git curat înainte de orice (`git status` fără modificări în `data/documents/`); opțional `git stash` nu e necesar — diff-ul e dovada.
2. **Baseline retrieval:** `python scripts/evaluate_retrieval.py --output tmp/eval-before-doc-clean.json` (pe indexul actual).
3. **Proba:** `.\scripts\clean_documents.ps1 -DryRun` → se verifică lista de fișiere și sumarul (fără scriere).
4. **Aplicare:** `.\scripts\clean_documents.ps1` → 283 fișiere modificate, sumar cu caractere/bytes eliminate și **0 violări**.
5. **Verificare spot:** 10–15 fișiere din listă (`git diff --stat data/documents` și `git diff` pe 2–3 fișiere mari: se vede exact ce linii au dispărut).
6. **Reindexare:** `.\scripts\rebuild_index.ps1` — 283 de fișiere au SHA-256 nou, deci se re-fragmentează și se re-embeduiesc; `TEXT_REPR_VERSION` **nu** necesită bump.
7. **Poarta de calitate:** `python scripts/evaluate_retrieval.py --output tmp/eval-after-doc-clean.json` și comparație cu pasul 2 (Precision@10, MRR, nDCG@10, Recall@50). Dacă scăderea e semnificativă → `git checkout -- data/documents` și se reia cu `--keep-diacritics`.
8. **Commit** cu două mesaje separate: unul pentru script, unul pentru conținutul din `data/documents/`.

---

## 10. Ce se schimbă în experiența utilizatorului

- **PDF-ul și panoul de fragmente** vor afișa text fără diacritice în citatele din surse (`sanatate`), în timp ce textul generat de AI rămâne cu diacritice. Este consecința directă a deciziei „diacritice → ASCII”, acceptată explicit.
- **Răspunsurile AI**: ~5% mai puțini tokeni pentru aceleași fragmente; la buget plin (1.000.000 caractere pentru DeepSeek/xAI) încap ~5% mai multe fragmente în același payload.
- **Căutarea nu se schimbă funcțional**: potrivirea lexicală normalizează deja diacriticele, iar dicționarul de afecțiuni e scris fără diacritice.

---

## 11. Riscuri și limite (toate măsurate, nu presupuse)

| Risc | Măsură / dovadă |
|---|---|
| Se pierde informație medicală | invariantă de cifre (0 violări) + teste 2, 3, 6, 7 + condiția „fără doze” pe fiecare regulă + titluri intacte (0 pierdute) |
| O secțiune de conținut e confundată cu mobilier | testul de formă (≥30% intrări) + poziția (ultimele 20% pentru index/bibliografie) + titluri ambigue excluse; dovedit pe cele 3 capcane reale din corpus |
| Folding-ul strică potrivirea afecțiunilor | potrivirea trece prin `plain()` și dicționarul e deja fără diacritice; poarta de evaluare retrieval la pasul 7 |
| Folding-ul scade calitatea embedding-urilor | evaluare retrieval înainte/după; supapă `--keep-diacritics` |
| Rularea repetată produce modificări în cascadă | idempotență verificată pe toate cele 387 de fișiere (0 ne-idempotente) |
| Se strică numerotarea liniilor din fragmente | reindexare completă la pasul 6; `chunks.line_start/line_end` se recalculează |
| Câștigul e mai mic decât așteptarea | cifra reală e **−4,92%**, nu 30%; vezi §12 pentru ce ar aduce restul |

---

## 12. În afara scopului (cu cifrele disponibile, dacă se revine)

| Optimizare refuzată acum | Câștig estimat | De ce ar merita reluată |
|---|---|---|
| Scoaterea din index a 5–24 de cărți marginale (Hawkins, Vaccinarea, Lipton, Cristaloterapie, liste de linkuri) | **35–50%** din tokeni | singura optimizare de ordin mare rămasă |
| Limitarea fragmentelor R1/R2 (azi max 75.478 caractere ≈ 20k tokeni într-un fragment) | payload previzibil, mai multe fragmente în același buget | necesită `ai/fragmenter.py` + reindexare |
| Eliminarea markup-ului (`**bold**`, list markers) | 15.343 tokeni (0,3%) | refuzat: accentul din „**nu** se administrează” are valoare de siguranță |
| Lowercase pe liniile ALL-CAPS | 12.052 tokeni (0,2%) | neutru ca informație; se poate activa ulterior |
| Deduplicare de paragrafe între fișiere | 18.261 caractere (0,10%) | efort mare, câștig neglijabil |
| Condensare cu AI (rescriere) | necunoscut, potențial mare | singura variantă care poate reduce *conținutul* fără a șterge documente |

---

## 13. Anexă — cum se remăsoară

Prototipurile de măsurare (nu fac parte din livrare, se pot șterge după implementare):

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe tmp\prototype_compaction_v5.py   # caractere, bytes, tokeni, invariantă, idempotență, titluri
.\.venv\Scripts\python.exe tmp\verify_digit_invariant.py    # verificare per fișier a cifrelor
```

Tokenizerul de referință este `data/model_cache/models--intfloat--multilingual-e5-small/snapshots/*/tokenizer.json` (biblioteca `tokenizers`, deja instalată). Este un **proxy**: vocabularul DeepSeek diferă, deci cifrele absolute diferă, dar comparația relativă înainte/după este validă. Estimarea brută `caractere / 4` dă 4,42M tokeni față de 4,86M cât dă tokenizer-ul real — suficient de aproape pentru decizii, insuficient pentru facturare.
