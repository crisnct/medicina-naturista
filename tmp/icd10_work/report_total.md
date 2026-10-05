# Raport total — completarea dicționarului din CIM-10 (pașii 2–26)

Pasul 1 (A, +79) e deja în `main`. Pașii 2–26 au rulat în paralel, fiecare literă pe branch-ul ei; la final, coordonatorul a unit branch-urile, a scos dublurile dintre litere și a distribuit afecțiunile amânate (`pending_from_<L>.jsonl`).

| Literă | Branch | Afecțiuni adăugate | Raport |
|---|---|---|---|
| B | `claude/elegant-allen-thlr5k` | 26 | `report_B.md` |
| C | `claude/icd10-litera-C` | 67 | `report_C.md` |
| D | `claude/icd10-litera-D` | 46 | `report_D.md` |
| E | `claude/icd10-litera-E` | 37 | `report_E.md` |
| F | `claude/icd10-litera-F` | 39 | `report_F.md` |
| G | `claude/icd10-litera-G` | 24 | `report_G.md` |
| H | `claude/icd10-litera-H` | 66 | `report_H.md` |
| I | `claude/icd10-litera-I` | 18 | `report_I.md` |
| J | `claude/icd10-litera-J` | 0 | `report_J.md` |
| K | `claude/icd10-litera-K` | 7 | `report_K.md` |
| L | `claude/icd10-litera-L` | 37 | `report_L.md` |
| M | `claude/icd10-litera-M` | 47 | `report_M.md` |
| N | `claude/icd10-litera-N` | 19 | `report_N.md` |
| O | `claude/icd10-litera-O` | 19 | `report_O.md` |
| P | `claude/icd10-litera-P` | 105 | `report_P.md` |
| Q | `claude/icd10-litera-Q` | 0 | `report_Q.md` |
| R | `claude/icd10-litera-R` | 13 | `report_R.md` |
| S | `claude/icd10-litera-S` | 85 | `report_S.md` |
| T | `claude/icd10-litera-T` | 48 | `report_T.md` |
| U | `claude/icd10-litera-U` | 11 | `report_U.md` |
| V | `claude/icd10-litera-V` | 11 | `report_V.md` |
| W | `claude/icd10-litera-W` | 1 | `report_W.md` |
| X | `claude/icd10-litera-X` | 1 | `report_X.md` |
| Y | `claude/icd10-litera-Y` | 0 | `report_Y.md` |
| Z | `claude/icd10-litera-Z` | 0 | `report_Z.md` |
| A (completare) | `claude/icd10-finalizare` | 9 | `notes_A2.md` |
| **Total** | | **736** | |

Dicționarul: 5548 afecțiuni după pasul A → **6284** după unirea tuturor branch-urilor (+736). Toate liniile existente sunt neschimbate și în aceeași ordine (D6); `test_conditions.py` trece pe dicționarul unit (29 de teste, 6291 de subteste).

## Unirea branch-urilor

- **Dubluri între litere, scoase:** `Boala Brill-Zinsser` (B) = `Tifos recrudescent` (T, A75.1); `Boala Ollier` (B) = `Encondromatoza` (E, Q78.4); `Leziune limfoepiteliala benigna` (L) = `Boala Mikulicz` (B, K11.8); `Litiaza uretrala` (L) = `Calcul uretral` (C, N21.1); `Hernie cerebrala` (H) = `Compresie cerebrala` (C, G93.5); `Granulom periferic cu celule gigante` (G) = `Epulis gigantocelular` (E). Se păstrează intrarea cu titlul CIM-10 sau cu sinonimele mai complete; cealaltă formulare e deja sinonim.
- **Termeni comuni (G6), corectați:** `Hipodontie` (H) a pierdut „oligodontie” (acum afecțiunea `Oligodontie`, O) și a primit „anodontie partiala”; `Hiperplazie gingivala` (H) a pierdut „fibromatoza gingivala” (afecțiunea `Fibromatoza gingivala`, F).
- **Redenumire:** `Voyeurism` → `Voaiorism` (forma din DEX).
- **Afecțiuni amânate:** 125 de linii unice în `pending_from_*`. 31 fuseseră deja adăugate de litera-țintă (eliminate); 94 au fost verificate pe dicționarul unit și adăugate pe branch-ul literei lor (A → `claude/icd10-finalizare`). Două sinonime corectate: „fizionomia bolii hematiilor falciforme” → „siclemie heterozigota”, „pelticie” → „vorbire peltica”.

## Greșeli găsite în liniile existente (nemodificate, D6)

Propuneri pentru un pas separat de corectare a sinonimelor:

| Afecțiune existentă | Termenul greșit | Unde îi e locul |
|---|---|---|
| Sindrom de iesire toracica | umar blocat | Capsulita adeziva |
| Ochi uscat | xeroftalmie / xerophthalmia | xeroftalmia din carența de vitamina A (E50.7) |
| Preeclampsie | eclampsie | intrare separată `Eclampsie` |
| Mola hidatiforma | ou clar | Sarcina anembrionara |
| Dismenoree | titlul N92.0 (menstruație excesivă și frecventă) | Menoragie |
| Spina bifida | sindrom mielodisplazic / myelodysplastic syndrome / mielodisplazie / myelodysplasia | `Neoplasm mielodisplazic` (D46) |
| Hernie inghinala | hernie ombilicala / umbilical hernia | intrare separată `Hernie ombilicala` |
| Greturi matinale | hiperemeza gravidica | intrare separată `Hiperemeza gravidica` |
| Prurigo de sarcina | pemphigoid gestationis | pemfigoid gestațional (O26.4) |
| Pericardita reumatoida | pericardita reumatismala cronica | cardita reumatismală |
| Papuloza limfomatoida | pitiriazis lichenoid si varioliform acut | PLEVA (L41.0) |
| Nanism tanatofor | distrofie toracica asfixianta | `Sindrom Jeune` |
| Paragangliom | tumora glomica / glomus tumor | tumoră glomică (nu e paragangliom) |
| Decubit de cornet | deviația de sept nazal | intrare separată |
| Sindrom Laurence-Moon | Sindromul William | sindromul Williams |
| — | lipsesc „revarsat pleural” / „pleural effusion” | `Pleurita` |

## De decis

- **Parafilii (F65):** dicționarul nu avea niciuna; acum are `Fetisism`, `Froteurism`, `Voaiorism`, `Exhibitionism`, `Pedofilie`, `Sadomasochism`, `Travestism fetisist`, `Travestism bivalent` și umbrela `Parafilie`. Sunt diagnostice CIM-10 din capitolul V (inclus după D3); se pot scoate dacă nu le vrei în proiect.
- **La limita G7 (stări, semne, leziuni):** `Cecitate`, `Dop de cerumen`, `Tartru dentar`, `Durere ovulatorie`, `Paraplegie`, `Tetraplegie`, `Hemiplegie`, `Proteinurie ortostatica`, `Linii Beau`, `Ruptura perineala obstetricala`.
- **Reindexare (D9):** `TEXT_REPR_VERSION` 5 → 6 în `src/scripts/build_hybrid_index.py` (branch-ul `claude/icd10-finalizare`). Comanda: `python src/scripts/build_hybrid_index.py` (sau `.\.venv-gpu\Scripts\python src\scripts\build_hybrid_index.py`), apoi `src/scripts/evaluate_retrieval.py` față de ultima evaluare.
