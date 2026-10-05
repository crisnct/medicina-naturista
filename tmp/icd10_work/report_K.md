# Litera K — raport CIM-10

- coduri CIM-10 cu titlul la litera K: **22**
- eliminate automat (P2): **3**
  - asterisc (in alte boli): 2
  - dublura categoriei parinte (nespecificat): 1
- găsite automat în dicționar (P4.1–P4.3): **6**
- de decis manual (`nou` + `posibil`): **13**
- **afecțiuni adăugate: 7**

## Decizii manuale

- **Grafia „Kerat…” / „Cherat…” (G3):** fiecare candidat „Kerat…” a fost căutat în ambele grafii (și „Chera…”/„Kera…” ca sinonim). Existau deja: `Keratita` (H16, cu „cheratita”), `Keratoconus` (H18.6), `Cheratoza actinica` (L57.0, cu „keratoza actinica”), `Cheratoderma` (L85.1 și „Keratoza ereditara palmara si plantara” din Q82.8), `Cheratoza foliculara`, `Keratoglob`. Fiecare afecțiune nouă are și grafia cu „Cher…” ca sinonim.
- **Existau sub alt nume:** `Keratoconjunctivita cu adenovirus` (B30.0) = `Keratoconjunctivita epidemica` („shipyard eye”); keratita/keratoconjunctivita herpetică (H19.1†) = `Keratita herpetica`; `Keratita interstitiala sifilitica congenitala tardiva` (A50.3) = `Sifilis congenital tardiv`; `Keratomicoza nigricans a palmei` (B36.1) = `Tinea nigra`; `Keratoza foliculara [Darier-White]` (Q82.8) = `Boala Darier`; `Keratoglob congenital cu glaucom` (Q15.0) = `Glaucom congenital`; `Kraurosis a vulvei` (N90.4) = `Lichen sclerosus vulvar`; `Kraurosisul penisului` (N48.0) = `Leucoplazie de penis` (balanita xerotica obliterans); `Kariotip 47, XXX` (Q97.0) = `Sindrom triplu X`; `Kariotip 47, XYY` (Q98.5) = `Sindrom XYY`; `Kawasaki` (M30.3) = `Boala Kawasaki`; `Klein` (Q87.04) = `Sindrom Treacher Collins`; `Kuru`, `Kala-azar` (= `Leishmanioza viscerala`), `kernicterus`, `Kwashiorkor`, `Kwashiorkor marasmic`.
- **Grupate în categoria lor (D5 / G8):** `Kariotip 45, X`, `46, X iso (Xq)`, `46, X cu cromozom sexual anormal` (Q96.0–Q96.2) → `Sindrom Turner` (variante de cariotip, nu boli diferite); `Keratoza foliculara datorita avitaminozei A` (E50.8, manifestare †) → `Deficit de vitamina A`; `Keratocon in sindromul Down` (H19.8*) → `Keratoconus` / sindrom Down.
- **Nu sunt boli anume (G7 / P2):** `Klebsiella pneumoniae, cauza unor boli clasate la alte capitole` (B96.1, agent cauzal) și `Klebsiella pneumoniae` în pneumonia congenitală (P23.6, agent; pneumoniile cu Klebsiella există deja pe organ); `Keratita, nespecificata` (H16.9); codurile-asterisc H19.2, H19.3, L86.
- **Variante de tip păstrate separat (G4):** `Keratita interstitiala` (H16.3) — dicționarul deja separă keratitele după tip (herpetică, aspergilară, cu Acanthamoeba); `Keratoconjunctivita` (H16.2) ca intrare de bază, alături de tipurile existente (uscată, epidemică, herpetică), cum e `Keratita` față de `Keratita herpetica`; `Keratoza punctata palmoplantara` (L85.2, Buschke-Fischer-Brauer), tip distinct față de `Cheratoderma`; `Keratopatie in banda` (H18.4, incluziune), entitate distinctă de `Degenerescenta corneana` generală; `Kerion` (B35.0, incluziune) — forma inflamatorie supurată a tinea capitis, entitate clinică consacrată (cf. `Scabie norvegiana` separat de scabie); `Keratoza obturanta` (H60.4, incluziune) — clinic distinctă de colesteatomul conductului auditiv extern, cu care CIM-10 o grupează.
- **Amânate la altă literă:** `Boala Kyrle` (L87.0, „Keratoza foliculara si parafoliculara penetrand in piele [Kyrle]”) → B, în `pending_from_K.jsonl` (numele eponimic urmează stilul `Boala Darier`). Titlul englezesc CIM-10 (62 de caractere) depășește limita de 60, deci nu e sinonim; s-a folosit forma scurtă „hyperkeratosis follicularis et parafollicularis”.
- **Lăsate literei titlului:** `Kleeblattschadel` (Q75.06) e incluziune sub „Craniu sub forma de frunza de trifoi” — apare în `candidates_C.txt`, deci decide pasul C (nu există în dicționar: „cloverleaf skull” lipsește).
- **De urmărit la integrare (G6):** `Keratoza obturanta` are ca sinonim „keratoza obturativa a urechii externe”, care e și incluziune la H60.4 (titlu la C, `Colesteatomul urechii externe`); `Kerion` e incluziune la B35.0 (titlu la T, `Tinea barbii si partii paroase a capului`). Dacă pașii C/T au pus acești termeni ca sinonime la alte afecțiuni, la reunire trebuie păstrați aici.
- **Sinonime insuficiente:** niciuna. Candidați posibili care nu apar în sursa românească (incluziuni OMS la H16.1/H16.2: keratoconjunctivita flictenulară, keratita neurotrofică, keratita punctată superficială Thygeson) nu au fost adăugați — nu sunt în lista RoDRG.
- **Amânate de la alte litere, adăugate la unire (coordonator, 1):** `Keratochist odontogen` (K09.0; de la C). Verificate față de dicționarul unit al tuturor literelor (G3, G6).

## Adăugate

| Nume canonic | Coduri | Sinonime |
|---|---|---|
| Keratita interstitiala | H16.3 | keratita interstitiala si profunda; cheratita interstitiala; keratita parenchimatoasa; keratita profunda; interstitial and deep keratitis; interstitial keratitis; parenchymatous keratitis; deep keratitis |
| Keratochist odontogen | K09.0 | cheratochist odontogen; tumora keratochistica odontogena; chist primordial; odontogenic keratocyst; keratocystic odontogenic tumor; primordial cyst |
| Keratoconjunctivita | H16.2 | cheratoconjunctivita; keratita superficiala cu conjunctivita; inflamatia corneei si conjunctivei; keratoconjunctivitis; superficial keratitis with conjunctivitis; inflammation of the cornea and conjunctiva |
| Keratopatie in banda | H18.4 | keratopatia in bandelete; cheratopatie in banda; keratopatie calcara in banda; degenerescenta corneana in banda; band keratopathy; calcific band keratopathy; band-shaped keratopathy; calcific band-shaped keratopathy |
| Keratoza obturanta | H60.4 | keratoza obturativa a urechii externe; keratoza obturanta a conductului auditiv extern; cheratoza obturanta; keratosis obturans; keratosis obturans of the external auditory canal; keratosis obturans of the ear |
| Keratoza punctata palmoplantara | L85.2 | keratoza punctata palmara si plantara; keratodermie palmoplantara punctata; cheratoza punctata palmoplantara; boala Buschke-Fischer-Brauer; keratosis punctata palmaris et plantaris; punctate palmoplantar keratoderma; Buschke-Fischer-Brauer disease; keratoderma punctatum |
| Kerion | B35.0 | kerion Celsi; tricofitie supurata; tinea capitis inflamatorie; tinea capitis supurativa; inflammatory tinea capitis; suppurative tinea capitis; kerion of Celsus; inflammatory ringworm of the scalp |

## Decise manual, neadăugate

Titluri `nou` / `posibil` care nu au devenit afecțiuni noi: există sub alt nume, sunt variante ale unei categorii (D5), categorii generice sau nu sunt boli (G7). Coloana „Apropiat” e sugestia automată.

| Cod | Titlu CIM-10 | Apropiat |
|---|---|---|
| B30.0 | Keratoconjunctivita cu adenovirus | Conjunctivita virala / Keratoconjunctivita epidemica |
| B96.1 | Klebsiella pneumoniae [K. pneumoniae], cauza unor boli clasate la alte capitole | Pneumonie / Pneumonita |
| H19.1 | Keratita si kerato-conjunctivita datorita virusului herpetic (B00.5†) | Keratita herpetica |
| H19.2 | Keratita si kerato-conjunctivita in alte boli infectioase si parazitare clasificate altundeva |  |
| L87.0 | Keratoza foliculara si parafoliculara penetrand in piele [Kyrle] | Cheratoza foliculara |
| Q96.0 | Kariotip 45, X |  |
| Q96.1 | Kariotip 46, X iso (Xq) |  |
| Q96.2 | Kariotip 46, X cu cromozom sexual anormal, cu exceptia iso (Xq) |  |
| Q97.0 | Kariotip 47, XXX | Sindrom triplu X / Triploidie |
| Q98.5 | Kariotip 47, XYY | Sindrom XYY |

## Existente (potrivire automată)

Candidații pentru sinonime adăugate ulterior (D6).

| Cod | Titlu CIM-10 | Afecțiune | Potrivire |
|---|---|---|---|
| E40 | Kwashiorkor | Kwashiorkor | exact |
| E42 | Kwashiorkor de marasm | Kwashiorkor marasmic | exact |
| H16 | Keratita | Keratita | exact |
| H18.6 | Keratocon | Keratoconus | exact |
| L57.0 | Keratoza actinica | Cheratoza actinica | exact |
| L85.1 | Keratoza [keratodermia] palmara si plantara dobandita | Cheratoderma | exact |
