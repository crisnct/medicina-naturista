# Litera W — raport CIM-10

- coduri CIM-10 cu titlul la litera W: **0**
- eliminate automat (P2): **0**
- găsite automat în dicționar (P4.1–P4.3): **0**
- de decis manual (`nou` + `posibil`): **0**
- **afecțiuni adăugate: 1**

## Decizii manuale

- **Niciun cod cu titlul la W:** CIM-10 românesc nu are niciun titlu de cod care să înceapă cu W (`candidates_W.txt` gol). Eponimele cu W (Waldenström, Whipple, Wilson, Wegener, Wernicke, Wolff-Parkinson-White etc.) apar sub „Boala …”, „Sindrom …”, „Macroglobulinemie …” și aparțin literelor B/S/M; nu au fost adăugate aici.
- **Termeni cu W sub coduri de la altă literă (`cross_W.txt`, 4 linii `?`):**
  - **Existau sub alt nume:** `Werdning-Hoffman` (G12.0, scris greșit în CIM-10 românesc) = `Amiotrofie spinala infantila` (sinonimul `boala Werdnig-Hoffmann`); `Weber-Christian` (M35.6, paniculita recidivantă) = `Boala Weber-Christian`.
  - **Adăugată (G4):** `Watsoniaza` (B66.8) — trematodoză intestinală cu *Watsonius watsoni*, termen de includere al categoriei reziduale „Alte infecții specificate cu paraziți”; dicționarul face deja distincția după agent pentru vecinii ei din B66.8 (`Heterofioza`, `Metagonimoza`), deci intră separat, cu sinonimele în același stil.
  - **Amânată la altă literă:** `Wells` (L98.3, „Celulita eozinofilă [Wells]”) — afecțiune nouă (lipsește din dicționar), dar numele canonic firesc este `Celulita eozinofilica` (C), după modelul `Fascita eozinofilica`/`Colita eozinofilica`; scrisă în `pending_from_W.jsonl` cu sinonimele `sindrom Wells`, `eosinophilic cellulitis`, `Wells syndrome` etc.
- **Nicio linie W în `pending_by_letter.jsonl`.**

## Adăugate

| Nume canonic | Coduri | Sinonime |
|---|---|---|
| Watsoniaza | B66.8 | infestare cu Watsonius watsoni; distomatoza intestinala cu Watsonius; trematodoza intestinala cu Watsonius; watsoniasis; Watsonius watsoni infection; Watsonius infection |

## Decise manual, neadăugate

Titluri `nou` / `posibil` care nu au devenit afecțiuni noi: există sub alt nume, sunt variante ale unei categorii (D5), categorii generice sau nu sunt boli (G7). Coloana „Apropiat” e sugestia automată.

| Cod | Titlu CIM-10 | Apropiat |
|---|---|---|

## Existente (potrivire automată)

Candidații pentru sinonime adăugate ulterior (D6).

| Cod | Titlu CIM-10 | Afecțiune | Potrivire |
|---|---|---|---|
