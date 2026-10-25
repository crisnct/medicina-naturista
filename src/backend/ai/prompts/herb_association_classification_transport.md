# Clasificarea fragmentului integral

Returneaza numai `{"relations":{"r0":{"local_condition":"...","recommendation":false,"prohibition":false}}}` si include fiecare ID din `candidates` exact o data.

`units[].text` este fragmentul indexat integral, intr-un singur camp. Citeste-l de la inceput pana la sfarsit. Nu presupune ca este impartit in parti sau ca unele parti lipsesc.

Pentru fiecare relatie:
- `local_condition`: denumirea afectiunii asa cum apare in contextul afirmatiei despre produs; sir gol daca nu o poti identifica.
- `recommendation`: `true` daca sursa recomanda candidatul pentru afectiunea locala.
- `prohibition`: `true` daca sursa cere explicit evitarea candidatului pentru afectiunea locala.

Foloseste textul integral, titlurile si contextul candidatului. Nu transfera afirmatii intre produse sau afectiuni. Nu returna citate, ID-uri de citat, etichete finale, explicatii sau alte campuri.
