# Litera Z — raport CIM-10

- coduri CIM-10 cu titlul la litera Z: **9**
- eliminate automat (P2): **2**
  - dublura categoriei parinte (nespecificat): 1
  - subzona de organ (D5): 1
- găsite automat în dicționar (P4.1–P4.3): **4**
- de decis manual (`nou` + `posibil`): **3**
- **afecțiuni adăugate: 0**

## Decizii manuale

- **Nicio afecțiune nouă la Z.** Toate entitățile CIM-10 cu nume la Z existau deja; dicționarul nu a fost modificat.
- **Existau (G3):** `Zona zoster [herpes zoster]` (B02) → `Zona zoster`; `Zona zoster oftalmică` (B02.3) → `Zona zoster oftalmica`; `Zona zoster diseminată` (B02.7) → `Zona zoster diseminata`; `Zygomicoză` (B46, zigomicoza/zygomycosis) → `Mucormikoza` (are deja `zigomikoza`, `zygomycosis`, `ficomikoza` ca sinonime). Subcategoriile B46 au nume la M (`Mucormikoza pulmonara`, `Mucormikoza rino-orbito-cerebrala`, `Mucormikoza cutanata` există), iar `Entomophthoromicoza` (B46.8) există ca `Entomophthoromikoza` (cu `zigomikoza subtropicala`).
- **Grupate în categoria lor (D5):** `Zona zoster însoțită de alte manifestări neurologice` (B02.2), `Zona zoster cu alte complicații` (B02.8), `Zona zoster fără complicații` (B02.9) → `Zona zoster`. Manifestările neurologice cu nume propriu există separat: `Neuralgie postherpetica` (G53.0, B02.2†), `Sindrom Ramsay Hunt` (zona zoster otică); encefalita și meningita zosteriană (B02.0, B02.1) au nume la E și M.
- **Nu sunt boli (P2/G7):** `Zona retro-cricoidiană` (C13.0) și `Zona de joncțiune a orofaringelui` (C10.8, termen de includere din cross_Z) — subzone anatomice ale cancerului hipofaringian/orofaringian (D5); `Zygomicoză, nespecificată` (B46.9) — dublura categoriei.
- **Verificate în plus, existente:** `Diverticul Zenker`, `Infectie cu virusul Zika` / `Sindrom congenital Zika` (Zika nu e în capitolele incluse ale CIM-10-AM), sindromul Zollinger-Ellison (E16.4, termen de includere la S; sinonim al `Gastrinom`).
- **Sinonime insuficiente / amânate la altă literă:** niciuna. `pending_by_letter.jsonl` nu are linii pentru Z; nu există `pending_from_Z.jsonl`.

## Adăugate

| Nume canonic | Coduri | Sinonime |
|---|---|---|

## Decise manual, neadăugate

Titluri `nou` / `posibil` care nu au devenit afecțiuni noi: există sub alt nume, sunt variante ale unei categorii (D5), categorii generice sau nu sunt boli (G7). Coloana „Apropiat” e sugestia automată.

| Cod | Titlu CIM-10 | Apropiat |
|---|---|---|
| B02.2 | Zona zoster insotita de alte manifestari neurologice | Zona zoster |
| B02.8 | Zona zoster cu alte complicatii | Zona zoster |
| B02.9 | Zona zoster, fara complicatii | Zona zoster |

## Existente (potrivire automată)

Candidații pentru sinonime adăugate ulterior (D6).

| Cod | Titlu CIM-10 | Afecțiune | Potrivire |
|---|---|---|---|
| B02 | Zona zoster [herpes zoster] | Zona zoster | exact |
| B02.3 | Zona zoster oftalmica | Zona zoster oftalmica | exact |
| B02.7 | Zona zoster diseminata | Zona zoster diseminata | exact |
| B46 | Zygomicoza | Mucormikoza | exact |
