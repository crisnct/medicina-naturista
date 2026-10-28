# Clasificare si atentionari in acelasi raspuns

Returneaza numai obiectul JSON cu doua sectiuni: `relations` si `warnings`.
Foloseste JSON compact, fara Markdown, comentarii sau text in afara obiectului.
In `relations`, include fiecare ID din `candidates` exact o data, cu aceleasi trei campuri:
`local_condition` (forma locala a afectiunii), `recommendation` si `prohibition` (booleeni).
Pastreaza regulile clasificarii produs-afectiune, inclusiv prioritatea aplicatiei pentru recomandari.
In `warnings`, include fiecare ID din `safety_targets` exact o data, cu `status` si `items`.
Fiecare element din items contine exact `kind`, `focus_id`, `summary`, `passage_ids` si `partners`.
`focus_id` apartine listei tintei `warning_statement_ids`; `summary` este formularea scurta afisata.
`passage_ids` selecteaza ID-uri din catalogul unitatii tintei; nu returna textul citatelor.
`units[].text` contine fragmentul indexat integral, intr-un singur camp. Citeste-l integral.
Atentionarile se refera la produs, independent de afectiunea unei relatii. Nu le repeta
pentru fiecare afectiune si nu schimba clasificarea relatiei doar pentru a returna atentionari.
