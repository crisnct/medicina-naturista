# Plan: compactarea surselor pentru payload-ul AI (`scripts/clean_documents.py`) — deepseek

**Obiectiv:** sursele din `data/documents/` (recursiv) să aibă semnificativ mai puține caractere, fără să se piardă informație medicală, ca fragmentele trimise la AI să coste mai puțini tokeni.

**Rezultat măsurat pe corpusul real** (regulile finale rulate pe toate cele 387 de fișiere, tokenizer `intfloat/multilingual-e5-small` ca proxy local):

| Metrică | Înainte | După | Diferență |
|---|---|---|---|
| Caractere | 17.657.661 | 17.598.699 | **−0,33%** |
| Bytes UTF-8 | 18.420.652 | 17.646.304 | **−4,20%** |
| Tokeni (proxy) | 4.856.461 | 4.660.035 | **−196.426 (−4,04%)** |
| Cifre pierdute | — | **0** | invariantă verificată |
| Titluri pierdute | — | **0** | structura de fragmentare intactă |

Diferența dintre −0,33% caractere și −4,20% bytes este efectul folding-ului de diacritice: `ă/â/î/ș/ț` sunt 2 bytes în UTF-8, iar `a/i/s/t` este 1 byte. Tokenii scad mai mult decât caracterele pentru că textul ASCII se tokenizează mai eficient. Defalcare pe reguli: `furniture:toc` 30.650 caractere, `running_header` 18.083, `page_number_line` 7.292, `colofon` 1.731, `inline_cleanup` 1.421, `phone_number` 488, `phone_label` 72, `email` 23.

> **Notă:** folding-ul de diacritice e **pornit** din 2 octombrie 2026 (`FOLD_DIACRITICS_BY_DEFAULT = True`) și se aplică fără niciun steag. Se oprește pe o singură rulare cu `--no-fold-diacritics` (sau `.\scripts\clean_documents.ps1 -KeepDiacritics`). Steagul `--fold-diacritics` rămâne acceptat, dar e redundant.

> **Corecție după un incident real.** Prima versiune a regulii de headere elimina *orice* linie repetată de ≥5 ori. Pe corpusul acesta asta a șters conținut: în `Herbal Antibiotics` au dispărut 20 din 23 de apariții ale subtitlului „Side Effects and Contraindications" (capul secțiunii de siguranță al fiecărei plante), în Balch au dispărut 132 de apariții ale unui antet de tabel („SUPLIMENT DOZĂ RECOMANDATĂ OBSERVAȚII") și 74 de propoziții de conținut repetate. Regula a fost restrânsă: se elimină **doar linia care repetă titlul documentului**, niciodată un titlu Markdown, niciodată o linie cu dozaj. Efectul corectat este 18.083 caractere în **4 fișiere** (ex. „Heal Yourself - The Natural Way", de 461 de ori), iar numărul de tokeni economisiți a scăzut de la −4,92% (care includea ștergeri dăunătoare) la **−4,04%**. Trei teste de regresie păzesc cazurile: subtitlu de șablon, antet de tabel, titlu Markdown repetat.

**Stare: implementat.** Regulile sunt în `scripts/clean_documents.py` (60 de teste trec în `tests/unit/ai/test_clean_documents.py` și `test_text_cleaning.py`). **Sursele nu sunt modificate de mine**: scriptul se rulează manual, de tine — în proiect nimic nu îl apelează automat (nici `rebuild_index.ps1`, nici aplicația), deci `data/documents/` se schimbă doar când execuți `.\scripts\clean_documents.ps1`.

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

**Ce ajută** (și e în plan): Cuprinsul (30.650 caractere), antetul de pagină care repetă titlul cărții (18.083), liniile cu număr de pagină (7.292), colofonul (1.731), datele de contact (583) și folding-ul diacriticelor (−176.312 tokeni singur, acum pornit).

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

### 4.1. Antetul de pagină care repetă titlul cărții — **18.083 caractere, doar 4 fișiere**

Conversia PDF tipărește titlul cărții în capul fiecărei pagini. Se elimină toate aparițiile **cu excepția primei**, dar numai dacă toate condițiile sunt adevărate:

- linia apare de **≥ 5 ori** în fișier;
- linia **repetă titlul documentului** — comparată normalizat (fără extensie, punctuație, diacritice, majuscule) cu numele fișierului și cu titlurile `#` din text; se acceptă și varianta „Titlu - Autor" sau titlul urmat de un număr de pagină;
- linia **nu este un titlu Markdown** (`#`, `##`, …) — titlurile sunt structura documentului, pe care se sprijină fragmentarea;
- linia **nu conține o doză** (`\b\d+([.,]\d+)?\s*(mg|mcg|µg|ml|kg|picături|lingurițe|capsule|comprimate)\b`).

**De ce nu e suficientă repetiția** (lecție plătită): corpusul repetă masiv și conținut. `Herbal Antibiotics` are subtitlul „Side Effects and Contraindications" la fiecare plantă (23 de apariții), Balch are un antet de tabel de 132 de ori și propoziții de dozaj repetate în fiecare fișă de supliment. O regulă bazată doar pe „linia apare de ≥5 ori" a șters exact acele linii — de aceea condiția de titlu e obligatorie, iar cele patru condiții de mai sus sunt acoperite de teste de regresie.

Efectul măsurat: 4 fișiere, cel mai mare „Heal Yourself - The Natural Way" (461 de apariții, 14.752 caractere).

### 4.2. Secțiuni de mobilier: Cuprins, Index/Glosar, Bibliografie — **30.650 caractere (doar Cuprins, în acest corpus)**

O secțiune e eliminată **numai dacă toate condițiile sunt adevărate**:

1. titlul e potrivit de tiparul de mobilier, la început de linie: `cuprins|cuprinsul|sumar|table of contents|conținut|con[țt]inut`, `index|index alfabetic|glosar|glossary|abrevieri`, `bibliografie|bibliography|referințe|references|note bibliografice|surse bibliografice|lecturi recomandate`;
2. titlul e **neambiguu**: nu conține `și`, `and`, `&`, `+`, `anex`, `plus`, `cuprinde` (astfel `REFERINȚE ȘI ANEXE` rămâne conținut);
3. pentru `Index`/`Glosar`/`Bibliografie`: titlul e în **ultimele 20%** din fișier (un index real e la sfârșit; `## INDEX` din dicționar e la mijloc → păstrat);
4. blocul are > 120 caractere și **nu conține nicio doză strictă**;
5. **densitatea de intrări ≥ 30%**: cel puțin 30% dintre liniile ne-goale se termină cu un număr de pagină sau cu puncte de umplere (`.......`).

Secțiunea se întinde de la titlu până la primul titlu de nivel egal sau superior (funcția `section_end()`).

### 4.3. Colofon / front-matter — **1.731 caractere**

Se elimină liniile de credit editorial, doar dacă au < 200 caractere și **încep** cu un marcaj de credit: fie tiparul puternic (`©`, `(c) 2014`, `ISBN`, `ISSN`, `Descrierea CIP`, `Toate drepturile`, `All rights reserved`, `Tehnoredactare`, `Corector`, `Copertă`, `Redactor`, `Traducere`, `Tipărit`, `Ediția a`), fie, doar în **primele 300 de linii**, tiparul de front-matter (`Editura`, `Publicat de/la/prin`, `Distribuit`, `www.`, `http…`, adresă de e-mail, `Copyright`, „orice reproducere”, `Editor:`, `prepress`).

**Ambele tipare sunt ancorate la începutul liniei**, iar cuvintele care pot apărea în interiorul altora au graniță de cuvânt. Lecția a venit din corpus: cu potrivire liberă în linie, regula a șters conținut — linia „-mentinerea unei diete sanatoase in care carbohidratii sa fie **distribuit**i pe parcursul unei zile…” a fost citită ca un credit de distribuție, două intrări bibliografice („1. Banu C. …, **Editura** Tehnică”) și două note de sursă („articol **publicat la**: 25 Aprilie 2002…”). Toate cele șapte linii de conținut sunt acum păstrate, iar regula a scăzut de la 2.806 la 1.731 de caractere; toate cele 49 de eliminări rămase sunt credite reale (copyright, ISBN, traducători, editură).

Restricția de poziție rămâne un al doilea gard: varianta agresivă (fără poziție și fără ancorare) ar fi tăiat 42.884 caractere, cu risc mare de a pierde text medical.

### 4.4. Linii care conțin doar numărul paginii — **7.296 caractere, 42 de fișiere**

Se elimină liniile care, după `strip()`, conțin exclusiv: un număr (eventual cu liniuțe), `pagina N`/`pag. N`, `page N` (`Page 104`, `Page 104 of 350`, `Page: 12`, `page viii.`) sau un numeral roman valid.

Formele englezești lipseau: `strip_page_markers()` știa doar `### Page 104` și `<!-- Page 104 -->`, iar regula de linii-număr-de-pagină doar `pagina 104`. În corpus rămăseseră astfel **105 linii „Page N"** (toate în `Herbal Antibiotics`) plus `Page i` … `Page viii`; acum sunt eliminate.

Numeralul roman e validat (`x{0,3}(?:ix|iv|v?i{0,3})`, adică până la XXXIX) în loc de clasa `[ivxlcdm]{1,7}`: altfel o linie care e doar cuvântul „civil" sau „Mix" ar fi fost ștearsă ca numeral. Testul existent `test_keeps_headings_that_merely_mention_pagina` rămâne valid (`### Pagina de start` nu e o linie de număr), iar liniile care doar *încep* cu o referință de pagină rămân neatinse — în corpus: `p.m. At 8 p.m. a full glass…`, `P.M.H. Atwater, LH.D.`, `p. cm. (A medicinal herb guide)` și 13 trimiteri rupte de tipul `p. 358.)`, care sunt conținut, nu mobilier.

### 4.5. Folding diacritice → ASCII — **−176.312 tokeni (−3,63%) singur**

`ă â î ș ț Ă Â Î Ș Ț ş ţ Ş Ţ ã Ã → a a i s t A A I S T s t S T a A`.

Argumente de siguranță:
- căutarea lexicală folosește deja `to_tsvector('simple', unaccent(...))`, iar dicționarul de afecțiuni e scris fără diacritice — potrivirea afecțiunilor trece prin `plain()` (NFKD + eliminare de semne diacritice), deci **nu se schimbă**;
- structura (titluri, niveluri) nu se atinge;
- cifrele, unitățile și denumirile latine nu conțin diacritice românești, deci rămân identice.

Se adaugă steagul `--keep-diacritics` ca supapă de revenire rapidă.

### 4.6. Date de contact: e-mailuri și numere de telefon

Adresele de e-mail erau deja eliminate de `clean_text()`; regula acceptă acum și forma escapată de extractor (`dspivak\@post-trib.com`), iar eliminările apar în sumar sub regula `email`.

Numerele de telefon sunt noi. Un șir de cifre cu separatoare de telefon este eliminat numai dacă trece testele de formă:

- pe o linie care anunță date de contact (`\b(?:tel|telefon|fax|mobil|mobile|gsm|whatsapp|viber|contact|contactați|sună|sunați|apel)\b`), orice număr de 7–15 cifre care nu e respins mai jos;
- în rest, doar formele naționale (`0` plus grupuri de 2–4 cifre, 9–11 cifre), cele internaționale (`+`/`00`, 9–15 cifre) sau numerele verzi americane (`1-800-…`);
- se acceptă și citirea OCR `o` pentru zero inițial (`Tel o21 242 14 46`).

Sunt respinse, ca să nu dispară informație medicală sau bibliografică: cifrele lipite de o unitate (`500 mg`, `10 ani`), cantitățile cu separatori de mii (`4.200.000`, `150.000-300.000`), datele (`11.11.2009`), ISBN-urile, șirurile cu o singură cifră distinctă (`000000000000`, cozi de DOI) și referințele de revistă (`100/1998`, `0079.1-0079.14`). Eticheta rămasă după număr (`tel.`, `mobil:`) se șterge și ea, iar o linie care nu mai conține nimic altceva dispare complet.

Măsurat pe corpus: **39 de numere de telefon și 17 etichete, în 14 fișiere**, plus o adresă de e-mail escapată — 488 + 95 + 23 de caractere. Eliminările sunt înregistrate ca spans whitelistate, deci invarianta cifrelor rămâne la **0 violări**.

### 4.7. Regulile existente rămân neatinse

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

Ieșirea: o linie per fișier modificat (`Cleaning: <cale>` / `Would clean: <cale>`), apoi **întotdeauna** un sumar de trei linii — fișiere modificate, caractere înainte → după, caractere eliminate pe fiecare regulă și starea diacriticelor + numărul de violări ale invarianței. Sumarul nu e opțional: dacă o regulă ar pierde o cifră, informația trebuie să apară oricum în consolă. Cod de ieșire: `0` normal, `1` dacă există violări ale invarianței cifrelor sau erori.

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

`Removed` = `(rule: str, text: str)` — folosit și pentru invariantă, și pentru sumarul de la final.

`clean_documents()` devine: `_read` → regulile existente → `fold_diacritics` → cele patru reguli noi → `collapse_blank_lines` → `check_digit_invariant` → scriere, cu acumularea statisticilor.

---

## 8. Teste

Extindere în `tests/unit/ai/test_clean_documents.py` (testele existente rămân valide; `test_never_changes_line_count` continuă să treacă, fiindcă fișierul lui de test nu atinge nicio regulă nouă):

1. `## Cuprins` cu puncte de umplere și numere de pagină → secțiunea dispare, iar textul de după următorul titlu de nivel 2 rămâne;
2. `## INDEX` aflat la mijlocul fișierului, cu text de proză → **păstrat**;
3. `## REFERINȚE ȘI ANEXE` → **păstrat** (titlu ambiguu);
4. `## Bibliografie` la sfârșit, cu ≥30% linii terminate în număr → eliminat;
5. linia care repetă titlul documentului, de 5 ori → eliminate toate copiile în afară de prima; de 4 ori → neatinsă;
6. linia cu dozaj repetată → **niciodată** eliminată, chiar dacă repetă titlul;
6b. subtitlu de șablon repetat la fiecare intrare („Side Effects and Contraindications") → **păstrat**;
6c. antet de tabel repetat („SUPLIMENT DOZĂ RECOMANDATĂ OBSERVAȚII") → **păstrat**;
6d. titlu Markdown (`# Carte`) repetat → **păstrat** (structura documentului);
7. `### Pagina 8` → eliminată; `### Pagina de start` → păstrată (deja existent);
8. linii de colofon în primele 300 de linii → eliminate; aceeași linie la mijlocul fișierului → păstrată;
8b. linie de conținut care doar *conține* un cuvânt de credit („…carbohidratii sa fie distribuiti…”, „1. Banu C. …, Editura Tehnică”, „articol publicat la: …”) → **păstrată**;
9. diacritice: `Coadă, șoricel, țuică` → `Coada, soricel, tuica`; cu `--keep-diacritics` → neschimbat;
10. invarianta cifrelor: caz sintetic construit manual (`before`, `after`, `removed`) în care un număr dispare fără să fie în spans → `check_digit_invariant()` îl raportează;
11. idempotență: `clean_documents()` rulat de două ori → al doilea apel raportează 0 fișiere modificate și nu atinge `mtime`;
12. titlurile rămân intacte: pentru un fișier cu titluri pe mai multe niveluri, multisetul de titluri (foldat) e identic înainte/după.

---

## 9. Cum se rulează (rollout)

**Aplicarea pe surse e o decizie a ta, luată manual.** Nimic din proiect nu apelează `clean_documents.py` automat (nici `rebuild_index.ps1`, nici aplicația, nici testele — testele lucrează doar în directoare temporare), deci `data/documents/` se schimbă doar când execuți tu scriptul. Pașii de mai jos se rulează în ordine, când vrei să aplici compactarea.

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

```powershell
# proba pe surse, fără nicio scriere (listează fișierele și sumarul per regulă)
.\scripts\clean_documents.ps1 -DryRun

# regulile, invarianta cifrelor, idempotența și păstrarea titlurilor
.\.venv\Scripts\python.exe -m pytest tests\unit\ai\test_clean_documents.py -q

# poarta de calitate a căutării, după o reindexare
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py --output tmp\eval-doc-clean.json
```

Măsurătoarea de tokeni din tabelul de la început s-a făcut cu tokenizerul local al modelului `intfloat/multilingual-e5-small` (biblioteca `tokenizers`, deja instalată, fișierul din `data/model_cache/`), pe toate cele 387 de fișiere, înainte și după. Este un **proxy**: vocabularul DeepSeek diferă, deci cifrele absolute diferă, dar comparația relativă înainte/după este validă. Estimarea brută `caractere / 4` dă 4,42M tokeni față de 4,86M cât dă tokenizer-ul real — suficient de aproape pentru decizii, insuficient pentru facturare.
