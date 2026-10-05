# Litera Y — raport CIM-10

- coduri CIM-10 cu titlul la litera Y: **1**
- eliminate automat (P2): **0**
- găsite automat în dicționar (P4.1–P4.3): **0**
- de decis manual (`nou` + `posibil`): **1**
- **afecțiuni adăugate: 0**

## Decizii manuale

- **Nicio afecțiune nouă la Y.** Litera are un singur cod CIM-10 cu titlul la Y (`A28.2`), niciun termen de includere cu Y sub coduri de la alte litere (`cross_Y.txt` gol) și nicio afecțiune în așteptare din pașii anteriori (`pending_by_letter.jsonl`).
- **Grupate în categoria lor (D5 / G8):** `Yersinioza extra-intestinala` (A28.2) → `Yersinioza`. Formele extraintestinale (septicemie, abcese, adenită, artrită) sunt localizări ale aceleiași infecții cu *Yersinia enterocolitica*, nu o entitate clinică distinctă; în plus, în afară de titlu (`extraintestinal yersiniosis`) nu există 3 + 3 denumiri reale proprii (sinonime insuficiente, 2.4). Formele cu entitate proprie sunt deja în dicționar: `Yersinioza pseudotuberculoasa`, `Faringita cu Yersinia`, `Artrita reactiva postenterica`, iar ciuma (*Y. pestis*) are `Ciuma bubonica` / `pneumonica` / `septicemica`.
- **Există sub alt nume (G3):** pianul / yaws (`A66`, cu toate grafiile: „Pian”, „Pianul”, „Yaws”, „Framboesia”, „frambesia tropica”) → `Framboesia`; enterita prin *Yersinia enterocolitica* (`A04.6`, titlu la E) → `Yersinioza` (sinonimul „enterocolita cu Yersinia”).
- **Amânate la altă literă:** niciuna (titlurile subcategoriilor `A66.x` încep cu L, P, H, G, A și se tratează la literele lor; ex. `Gangosa` la G).

## Adăugate

| Nume canonic | Coduri | Sinonime |
|---|---|---|

## Decise manual, neadăugate

Titluri `nou` / `posibil` care nu au devenit afecțiuni noi: există sub alt nume, sunt variante ale unei categorii (D5), categorii generice sau nu sunt boli (G7). Coloana „Apropiat” e sugestia automată.

| Cod | Titlu CIM-10 | Apropiat |
|---|---|---|
| A28.2 | Yersinioza extra-intestinala | Yersinioza |

## Existente (potrivire automată)

Candidații pentru sinonime adăugate ulterior (D6).

| Cod | Titlu CIM-10 | Afecțiune | Potrivire |
|---|---|---|---|
