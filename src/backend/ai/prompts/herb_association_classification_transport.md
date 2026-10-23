# Protocol JSON strict

Returneaza numai `{"relations":{...}}`, cu exact ID-urile candidatilor primiti, fiecare
o singura data. Nu adauga Markdown, explicatii sau chei. Fiecare valoare este o lista:

| Cod | Eticheta | Continut |
| --- | --- | --- |
| 0 | unclear | [0] |
| 1 | positive | [1, ID_citat] |
| 2 | caution | [2, ID_citat] |
| 3 | mixed | [3, ID_citat] sau [3, ID_favorabil, ID_nefavorabil] |

## Provenienta si acoperire

- Foloseste exclusiv ID-uri din `segments[].parts` ale unitatii candidatului: `c` este doar
  un exemplu de identificator. Nu inventa ID-uri si nu cita alta unitate.
- Un citat trebuie sa aiba text original neblank. Pentru mixed, un singur citat poate
  sustine ambele sensuri; altfel foloseste doua citate distincte, favorabil apoi nefavorabil.
- `start` si `mentions` sunt pozitii in textul original al aceleiasi unitati.
- Citeste toate partile tuturor segmentelor in ordine: concatenarea lor pastreaza integral unitatea.
  Un avertisment se poate afla in alt segment. Ruperile OCR nu incheie afirmatia.
- Fiecare segment are maximum 1000 caractere. Cererile obisnuite au maximum sase segmente;
  o unitate prea mare se trimite integral, singura in cerere, cu mai multe segmente.
- Partile sunt citate mai scurte din acelasi pasaj, nu pasaje suplimentare. Alege afirmatia
  proprie a produsului; un beneficiu din randul altui produs nu sustine relatia candidata.
- Titlurile, introducerile si antetele sunt context, nu ID-uri de citat.
- Pentru unclear nu furniza citate. Pastreaza si candidatii neclari in raspuns.

## Verificare finala

Set exact de candidati, cod valid, numar valid de citate, toate citatele din unitatea proprie.
