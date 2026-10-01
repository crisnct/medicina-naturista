# Sarcina 20-25 — Sinonim popular (limbaj popular) pentru fiecare boala

Utilizatorul vrea ca la fiecare boala sa existe, pe langa sinonimele medicale, si
**sinonimul din limbajul popular romanesc**, atunci cand exista unul consacrat.

## Ce scrii

Un fisier cu linii de forma:

```
NumeCanonic|sinonim popular
```

- `NumeCanonic` = exact numele din lista primita (primul camp), scris **identic**, fara modificari.
- `sinonim popular` = denumirea pe care o foloseste lumea obisnuita in romana vorbita.
- **Fara diacritice** (`galbeaza`, nu `gălbează`; `bube dulci`, nu `bube dulci` cu diacritice).
- Un singur sinonim popular per linie, cel mai cunoscut.
- Daca pentru o boala **nu exista** un nume popular consacrat, **nu scrie linia deloc**.
  Mai bine 40 de linii reale decat 134 cu inventii.

## Reguli de substanta

1. Numai denumiri pe care romanii le folosesc efectiv: `boala sarutului`, `piciorul atletului`,
   `gusa`, `buba coapta`, `galbeaza`, `jinduitul`, `frigurile`, `boala galbena`, `chelia`,
   `piatra la fiere`, `pietre la rinichi`, `lesinul`, `jupuitul`, `furnicaturile`, `sughitul`.
2. Nu pune termeni medicali ca sinonim popular (`miocardita` nu este popular pentru infarct).
3. Nu pune descriptii inventate (`boala care apare la copii`) si nu repeta numele canonic.
4. Daca singurul termen popular cunoscut este deja numele canonic al altei boli din dictionar,
   foloseste o alta varianta populara; daca nu exista, sari peste linie.
5. Atentie la boli diferite care impart acelasi nume popular (`gusa` = gușa tiroidiană,
   `chelia` = alopecia). Alege boala cea mai reprezentativa pentru termenul popular.

## Unde scrii

In fisierul indicat in sarcina ta. Doar liniile de date, fara titluri, fara linii goale, fara ``` .
