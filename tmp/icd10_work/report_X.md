# Litera X — raport CIM-10

- coduri CIM-10 cu titlul la litera X: **4**
- eliminate automat (P2): **0**
- găsite automat în dicționar (P4.1–P4.3): **3**
- de decis manual (`nou` + `posibil`): **1**
- **afecțiuni adăugate: 1**

## Decizii manuale

- **Adăugată (1):** `Xantom veruciform` (K13.4, termen de includere „Xantom verucos al mucoasei bucale”): leziune benignă a mucoasei bucale, fără legătură cu dislipidemia, entitate distinctă de `Xantom` (G4, cum sunt deja separate `Xantelasma` și `Xantogranulom juvenil`). Auditul de aproape-duplicate semnalează perechea `Xantom` ⊂ `Xantom veruciform`, așteptată (tip distinct).
- **Existau (G3):** `Xantelasma pleoapei` (H02.6) → `Xantelasma`; `Xeroza cutanata` (L85.3) → `Piele uscata`; `Xeroderma pigmentara` (Q82.1) → `Xeroderma pigmentosum`; `Xantogranulom` (D76.3) → `Xantogranulom juvenil`; `Xerostomia` (K11.7) → `Xerostomie`; `Xantinuria ereditara` (E79.8) → `Xantinurie` (are deja „xantinurie familiala”); `Xeroftalmia` (E50.7) → `Ochi uscat` („xeroftalmie”/„xerophthalmia” sunt sinonime ale ei).
- **Grupate (D5 / G8):** `Xifopagus` (Q89.44) e un tip de gemeni uniți după locul de unire, ca dicefalia, craniopagus, toracopagus și pigopagus. Se grupează în categoria Q89.4 „Gemeni uniti”, al cărei titlu e la G și se tratează la pasul G, deci nu am trecut nimic în pending. `Xantom tuberos` și `Xantom tubero-eruptiv` (termeni de includere la E78.2, hiperlipidemia mixtă) sunt forme clinice ale xantomului din dislipidemie. Dicționarul nu separă tipurile clinice de xantom, deci se grupează în `Xantom` / hiperlipidemie.
- **Nu sunt boli anume (P2):** `Xerodermia datorita avitaminozei A` (E50.8†, L86*) e o manifestare-asterisc a carenței de vitamina A (`Deficit de vitamina A`).
- **Îndoială rămasă (D6, neatinsă):** în CIM-10, xeroftalmia (E50.7) înseamnă afectarea oculară din carența de vitamina A, nu sindromul de ochi uscat. Dicționarul o are ca sinonim la `Ochi uscat`, deci nu poate primi intrare proprie (G6). O eventuală mutare a sinonimului ține de pasul ulterior de corectare a sinonimelor.
- Litera X nu are nimic de amânat la alte litere (`pending_from_X.jsonl` nu există) și nicio linie cu `"letter": "X"` în `pending_by_letter.jsonl`.

## Adăugate

| Nume canonic | Coduri | Sinonime |
|---|---|---|
| Xantom veruciform | K13.4 | xantom verucos al mucoasei bucale; xantom verucos; xantom veruciform oral; verruciform xanthoma; oral verruciform xanthoma; verrucous xanthoma |

## Decise manual, neadăugate

Titluri `nou` / `posibil` care nu au devenit afecțiuni noi: există sub alt nume, sunt variante ale unei categorii (D5), categorii generice sau nu sunt boli (G7). Coloana „Apropiat” e sugestia automată.

| Cod | Titlu CIM-10 | Apropiat |
|---|---|---|
| Q89.44 | Xifopagus |  |

## Existente (potrivire automată)

Candidații pentru sinonime adăugate ulterior (D6).

| Cod | Titlu CIM-10 | Afecțiune | Potrivire |
|---|---|---|---|
| H02.6 | Xantelasma pleoapei | Xantelasma | terminatii |
| L85.3 | Xeroza cutanata | Piele uscata | exact |
| Q82.1 | Xeroderma pigmentara | Xeroderma pigmentosum | exact |
