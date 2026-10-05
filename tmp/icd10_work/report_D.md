# Litera D — raport CIM-10

- coduri CIM-10 cu titlul la litera D: **520**
- eliminate automat (P2): **23**
  - dublura categoriei parinte (nespecificat): 15
  - subzona de organ (D5): 5
  - asterisc (in alte boli): 3
- găsite automat în dicționar (P4.1–P4.3): **82**
- de decis manual (`nou` + `posibil`): **415**
- **afecțiuni adăugate: 46**

## Decizii manuale

- **Din `pending_by_letter.jsonl` (scrise la A):** `Deficit de vitamine B` (E53.9) și `Durere faciala atipica` (G50.1), re-verificate cu `lookup.py` (doar potriviri aproximative cu deficitele de vitamine B anume — B12, folat, piridoxină, niacină, biotină — care sunt alte intrări) și incluse în lot.
- **Potriviri automate absurde (lista `exista`):** `A09 Diareea si gastro-enterita probabil infectioase = Tuberculoza` — potrivire falsă pe un termen de excludere „Tuberculoza (A15-A19)” citit ca includere; boala reală (diareea infecțioasă) există ca `Gastroenterita`. `L20 Dermatita atopica = Eczema` și `L21 Dermatita seboreica = Dermatita` sunt corecte după datele dicționarului (sinonime existente).
- **Existau sub alt nume:** deficitul selectiv de IgA / subclase IgG, deficitul de ADA, deficitul MHC clasa II (`Imunodeficienta cu deficit de HLA clasa II`), dicroceliaza, difteria nazofaringiană (`Difterie nazala`, `Faringita cu Corynebacterium`), sindroamele pluriglandulare autoimune (E31), acatalazia (E80.3), dementa în boala Pick (`Dementa frontotemporala`), în HIV (`Dementa la HIV`), în Creutzfeldt-Jakob, Huntington, delirul (`Delirium`), disfuncția somatoformă autonomă (`Astenie neurocirculatora`), disfuncția orgasmică (`Frigiditate`, prin „anorgasmie”), dispareunia psihogenă (`Dispareunie`), distonia buco-facială (`Sindrom Meige`), distonia idiopatică familială (`Distonie generalizata`), degenerescența striatonigrică și Shy-Drager (`Atrofie multisistemica`), demielinizarea acută diseminată (`Encefalomielita`), Marchiafava-Bignami (G37.1), extrasistolele atriale / joncționale / ventriculare (`Aritmie extrasistolie atriala / supraventriculara / ventriculara`), disecția de aortă, disecția carotidiană (`Disectie de artera cervicala`), dermografismul, reticulohistiocitoza (M14.3), deformările în butonieră / gât de lebădă, discita (`Spondilodiscita`), diastaza musculară (`Diastazis al muschilor drepti`), vezica neurogenă (N31), displazia mamară benignă (`Mastopatie fibrochistica`), displaziile de col / vagin / vulvă (CIN, VAIN, VIN), steatoza (K76.0), deshidratarea / depleția de volum (`Deshidratare`), displazia septo-optică, duplicația ureterală, diverticulul de urac (`Persistenta de urac`), displazia renală (`Displazie renala multichistica`), dislocarea congenitală de șold (`Displazie de sold`), torticolisul congenital, deformarea Sprengel, displazia fronto-nazală, McCune-Albright, displazia ectodermică, situs inversus; din termenii de includere cu D: Devic, Steinert, Dupuytren, algoneurodistrofia, dislexia, dismorfofobia, Alpers, gnatostomoza, methemoglobinemia congenitală, deficitul de carboxilaze (`Deficit de holocarboxilaza sintetaza`), deficitul de galactokinază (`Galactozemie tip II`), deficitul de factor XI (`Hemofilie C`), displazia bronhopulmonară (`Boala pulmonara cronica neonatala`), disproporția cefalo-pelvină (`Bazin strimt`), dipsomania (`Alcoolism`), boala buloasă cronică a copilăriei (`Dermatita IgA liniara`), dermatofitidele (`Reactie id`, în așteptare la R), deficiența femurală focală proximală (`Absenta de femur`, scoasă din lot la verificarea manuală), displazia tanatoforă (`Nanism tanatofor`), sinostoza radio-ulnară, deformarea Madelung, disostoza cleidocraniană.
- **Grupate în categoria lor (D5 / G1):** toate „Diabet mellitus tip 1 / tip 2 / nespecificat / alte forme … cu X” (`E10`–`E14` .0–.9: hiperosmolaritate, acidocetoză, acidoză lactică, comă, complicații renale, oculare, neurologice, circulatorii, periodontale, ulcerații, control slab, fără complicații) → `Diabet zaharat tip 1`, `Diabet zaharat`, `Diabet zaharat tip 1/2 cu complicatii`, `Diabet secundar`; complicațiile au oricum intrări proprii (`Cetoacidoza diabetica`, `Coma hiperosmolara`, `Nefropatie diabetica`, `Retinopatie diabetica`, `Cataracta diabetica`, `Neuropatie autonoma diabetica`, `Cardiomiopatie diabetica`, `Picior diabetic`). Diabetul preexistent în sarcină (O24.0–O24.3) → tipul de diabet, O24.4 → `Diabet gestational`. Variantele demenței Alzheimer și vasculare (F00.x, F01.x), delirul supraadăugat demenței (F05.0–F05.1), disfuncția somatoformă pe organe (F45.30–F45.39), distonia idiopatică nefamilială (G24.2), dermatitele de contact după agent (L23.x, L24.x, L25.x) și dermatita prin alimente ingerate (L27.2), dismenoreea primară / secundară, distociile de obstacol după cauză (O64–O66 → `Distocie`, `Distocie de umar`, `Bazin strimt`), dezlipirea de placentă cu coagulopatie (O45.0), disecția aortei pe segmente (I71.0x), dacriopericistita (→ `Dacriocistita`), herpesul vezicular (B00.1 → `Herpes labial`), deficitul secundar de lactază (→ `Intoleranta la lactoza`), deshidratarea nou-născutului (→ `Deshidratare`), defectele septale post-infarct (I23.1–I23.2, incluse în noul `Defect septal dobandit`), dicefalia (Q89.41 → gemenii uniți, Q89.4, la G), dermatoza papuloasă neagră (→ `Cheratoza seboreica`), degenerescența polipoidă a sinusului / Woakes (J33.1 → `Polipi nazali`; eponimul e termen de includere la S).
- **Nu sunt boli anume (G7 / P2):** durata sarcinii (O09.x), decesele obstetricale (O95–O97), dehiscența suturilor de cezariană / perineu (O90.0–O90.1, complicații de procedură), durerea oculară, dorsalgia și durerea de membru (simptome), dificultățile de alăptare, diminuarea activității cerebrale la nou-născut, dezechilibrul constituenților alimentari (E63.1), deformările dobândite fără nume (M20.6, M21.0–M21.2, M95.x), dorsopatiile nespecificate, disfuncția segmentară și somatică (M99.0), deformarea orbitei, depunerile conjunctivale, degenerescența senilă a creierului, degenerescența miocardului, duplicațiile cromozomiale (Q92.4–Q92.5), deformările congenitale generice (Q66, Q67.5, Q68.1), dismotilitatea esofagiană (Q39.82), duplicațiile digestive NCA, diplegia membrelor superioare (sindrom paralitic, G83.0), diareea neinfecțioasă neonatală (P78.3, simptom), diafragmatita, deviațiile / deplasările de organe și dinți fără nume consacrat.
- **Variante de organ / tip păstrate separat (G4):** dezlipirea de retină seroasă și cea tracțională (față de `Dezlipire de retina`), disecția de arteră cerebrală intracraniană (față de cea cervicală, renală, coronară), diverticulul vezical dobândit și cel congenital (Hutch), diverticulul apendicular și cel caliceal, dermatita seboreică infantilă (față de cea facială), dermatita berloque (față de `Fotodermatita`), dermatita artefacta (față de `Tulburare factice` și `Dermatilomanie`), distonia medicamentoasă (față de `Diskinezie tardiva`), degenerescența cerebeloasă alcoolică (față de `Atrofie cerebeloasa`), delta-beta-talasemia (față de `Beta-talasemie`), deficitul selectiv de IgM (față de IgA), deficitul HLA clasa I (față de clasa II), deficitul congenital de lactază (față de intoleranța la lactoză), dirofilarioza (față de `Pneumonie cu Dirofilaria`).
- **Adăugate din termenii de includere cu D** (coduri cu titlu rezidual „Alte …” sau generic, pe care nicio altă literă nu le prinde): `Dirofilarioza` (B74.8), `Deficit de sulfit oxidaza` (E72.1), `Dacriops` (H04.1), `Druze ale papilei optice` (H47.3), `Disociatie atrioventriculara` (I45.8), `Dilaceratie dentara` (K00.4), `Dentinogeneza imperfecta` (K00.5), `Dinti natali` (K00.6), `Diastema dentara` (K07.3), `Displazie Kniest` (Q77.89).
- **Sinonime insuficiente / lăsate deoparte:** deficitul de lanț kappa ușor (D80.8), deficitul de fosfatază acidă (E83.3), disfuncția glandei pineale, displazia dentinară, dintele Turner (hipoplazie de smalt, la H), diverticulul bronșic congenital, discraniopigofalangia.
- **Lăsate literei titlului / termenului (nu le-am scris, ca să nu apară de două ori):** Sneddon-Wilkinson (termen de includere la B), fluoroza dentară (la F), nevroza de compensație (la N), sindromul Woakes (la S), Hallervorden-Spatz (titlu la B), Wilson-Mikity și sindromul coastei scurte / Jeune (titluri la S), condrodisplazia punctată și cea metafizară (titluri la C), nanismul metatropic (la N), rinichiul dublu (la R), gemenii uniți (la G), malocluzia / distocluzia (K07.4, la M), contracțiile uterine hipertone / inerția uterină (titluri la C și I), tulburarea anxios-depresivă mixtă (la T).
- **Amânate la altă literă (`pending_from_D.jsonl`, 8):** B — `Boala Grover` (L11.1), `Bursita calcificata` (M71.4); P — `Police trifalangian` (Q74.03); S — `Sindrom Hallermann-Streiff` (Q75.5), `Sindrom fetal warfarinic` (Q86.2), `Sindrom Frohlich` (E23.6, distrofia adipozo-genitală); T — `Tartru dentar` (K03.6), `Tulburare dezintegrativa a copilariei` (F84.3, titlul începe cu „Alta …” și a fost eliminat ca rezidual la A; atenție: S sau P ar putea adăuga separat „Sindrom Heller” / „Psihoza dezintegrativa”).
- **Amânate de la alte litere, adăugate la unire (coordonator, 5):** `Deficit de transcobalamina II` (D51.2; de la C); `Depresie recurenta de scurta durata` (F38.1; de la E); `Dislalie` (F80.0; de la T); `Disortografie` (F81.1; de la T); `Duplicatie uretrala` (Q64.73; de la U). Verificate față de dicționarul unit al tuturor literelor (G3, G6).

## Adăugate

| Nume canonic | Coduri | Sinonime |
|---|---|---|
| Dacriops | H04.1 | chist de glanda lacrimala; chist al ductului lacrimal; chist lacrimal; dacryops; lacrimal gland cyst; lacrimal ductal cyst |
| Defect septal dobandit | I51.0, I23.1, I23.2 | defect septal cardiac dobandit; ruptura de sept interventricular; defect septal ventricular postinfarct; acquired cardiac septal defect; ventricular septal rupture; post-infarction ventricular septal defect |
| Deficit congenital de lactaza | E73.0 | deficit congenital in lactaza; alactazie congenitala; intoleranta congenitala la lactoza; congenital lactase deficiency; congenital alactasia; congenital lactose intolerance |
| Deficit de HLA clasa I | D81.6 | deficit in complex major de histocompatibilitate clasa I; sindromul limfocitelor goale tip I; deficit de MHC clasa I; major histocompatibility complex class I deficiency; MHC class I deficiency; bare lymphocyte syndrome type I; HLA class I deficiency |
| Deficit de purin nucleozid fosforilaza | D81.5 | deficit in purine nucleosidfosforilaza; deficit de PNP; imunodeficienta prin deficit de PNP; purine nucleoside phosphorylase deficiency; PNP deficiency; PNP immunodeficiency |
| Deficit de sulfit oxidaza | E72.1 | deficit in sulfit oxidaza; deficit izolat de sulfit oxidaza; sulfocisteinurie; sulfite oxidase deficiency; isolated sulfite oxidase deficiency; sulfocysteinuria |
| Deficit de transcobalamina II | D51.2 | carenta de transcobalamina II; deficit ereditar de transcobalamina; deficienta de transcobalamina; transcobalamin II deficiency; transcobalamin deficiency; TCII deficiency |
| Deficit de vitamine B | E53.9 | avitaminoza B; carenta de vitamine din grupul B; hipovitaminoza B; vitamin B deficiency; B vitamin deficiency; vitamin B complex deficiency |
| Deficit selectiv de IgM | D80.4 | deficit selectiv in imunoglobuline M; deficit selectiv de imunoglobulina M; deficit izolat de IgM; selective deficiency of immunoglobulin M; selective IgM deficiency; isolated IgM deficiency |
| Degenerescenta cerebeloasa alcoolica | G31.2 | degenerescenta sistemului nervos datorita alcoolului; atrofie cerebeloasa alcoolica; ataxie cerebeloasa alcoolica; degeneration of nervous system due to alcohol; alcoholic cerebellar degeneration; alcoholic cerebellar atrophy; alcoholic cerebellar ataxia |
| Degenerescenta pulpara | K04.2 | calcificare pulpara; pulpoliti; denticuli pulpari; pulp degeneration; pulp calcification; pulp stones; denticles |
| Delta-beta-talasemie | D56.2 | delta-beta-thalasemia; talasemie delta-beta; talasemie F; delta-beta thalassemia; F-thalassemia; delta-beta thalassaemia |
| Dentinogeneza imperfecta | K00.5 | dentina opalescenta ereditara; dinti Capdepont; dinte in forma de scoica; dentinogenesis imperfecta; hereditary opalescent dentin; Capdepont teeth; shell teeth |
| Depresie postschizofrenica | F20.4 | depresie post-schizofrenica; depresie postpsihotica schizofrenica; depresie dupa episod schizofrenic; post-schizophrenic depression; postpsychotic depression of schizophrenia; post-schizophrenia depression |
| Depresie recurenta de scurta durata | F38.1 | episoade depresive recurente de scurta durata; depresie scurta recurenta; tulburare depresiva recurenta scurta; recurrent brief depression; recurrent brief depressive disorder; brief recurrent depression |
| Dermatita artefacta | L98.1 | dermatita factice; patomimie cutanata; dermatita autoprovocata; factitial dermatitis; dermatitis artefacta; factitious dermatitis; self-inflicted dermatitis |
| Dermatita berloque | L56.2 | dermita de fotocontact; dermatita de fotocontact; dermatita berlock; photocontact dermatitis; berloque dermatitis; berlock dermatitis |
| Dermatita eczematoida infectioasa | L30.3 | dermatita infectioasa; eczema infectioasa; eczema microbiana; infective dermatitis; infectious eczematoid dermatitis; microbial eczema |
| Dermatita seboreica infantila | L21.1 | crusta de lapte; dermatita seboreica a sugarului; eczema seboreica infantila; seborrheic infantile dermatitis; infantile seborrheic dermatitis; cradle cap |
| Dezlipire de retina seroasa | H33.2 | dezlipirea seroasei retiniene; dezlipire de retina exudativa; decolare exudativa de retina; serous retinal detachment; exudative retinal detachment; secondary exudative retinal detachment |
| Dezlipire de retina tractionala | H33.4 | detasare mecanica a retinei; dezlipire de retina prin tractiune; decolare tractionala de retina; traction detachment of retina; tractional retinal detachment; traction retinal detachment |
| Diastema dentara | K07.3 | diastema unuia sau mai multor dinti; strungareata; diastema interincisiva; diastema; midline diastema; gap teeth |
| Dilaceratie dentara | K00.4 | dilacerarea dintilor; dilaceratie radiculara; dinte dilacerat; tooth dilaceration; dental dilaceration; root dilaceration |
| Dinte inclus | K01, K01.0, K01.1 | dinti inclusi si inclavati; dinte inclavat; dinte retinut; molar de minte inclus; embedded and impacted teeth; impacted tooth; embedded tooth; unerupted tooth |
| Dinti natali | K00.6 | dinte natal; dinte neonatal; dinti congenitali; natal teeth; neonatal teeth; congenital teeth |
| Dinti supranumerari | K00.1 | dinti suplimentari; hiperdontie; meziodens; supernumerary teeth; hyperdontia; supplementary teeth; mesiodens |
| Dirofilarioza | B74.8 | dirofilariaza; infectie cu Dirofilaria; dirofilarioza subcutanata; dirofilariasis; Dirofilaria infection; subcutaneous dirofilariasis; human dirofilariasis |
| Discontinuitate a lantului osicular | H74.2 | disociatia si dislocarea oscioarelor urechii; luxatia oscioarelor urechii; disjunctie osiculara; discontinuity and dislocation of ear ossicles; ossicular discontinuity; ossicular chain disruption; ossicular dislocation |
| Disectie de artera cerebrala | I67.0 | disectia arterelor cerebrale; disectie arteriala intracraniana; disectie intracraniana; dissection of cerebral arteries; cerebral artery dissection; intracranial artery dissection |
| Disfunctie labirintica | H83.2 | hipofunctia labirintului; hipersensibilitatea labirintului; pierderea functiei labirintului; labyrinthine dysfunction; labyrinthine hypofunction; labyrinthine hypersensitivity |
| Dislalie | F80.0 | tulburare specifica de articulare a vorbirii; tulburare fonologica; tulburare de articulare a vorbirii; phonological disorder; speech sound disorder; dyslalia |
| Disociatie atrioventriculara | I45.8 | disociere atrioventriculara; disociatie AV; disociere de interferenta; atrioventricular dissociation; AV dissociation; interference dissociation |
| Disortografie | F81.1 | tulburare specifica de ortografie; disortografie de dezvoltare; tulburare de ortografie; specific spelling disorder; dysorthography; spelling disorder |
| Displazie fibromusculara | I77.3 | displazia fibromusculara arteriala; displazie fibromusculara a arterei renale; fibroplazie mediala; arterial fibromuscular dysplasia; fibromuscular dysplasia; renal artery fibromuscular dysplasia |
| Displazie Kniest | Q77.89 | sindrom Kniest; nanism metatropic tip II; condrodisplazie Kniest; Kniest dysplasia; Kniest syndrome; metatropic dwarfism type II; Swiss cheese cartilage syndrome |
| Distonie medicamentoasa | G24.0 | distonia provocata medicamentos; distonie indusa de medicamente; reactie distonica acuta; drug induced dystonia; acute dystonic reaction; medication-induced dystonia; neuroleptic-induced acute dystonia |
| Diverticul apendicular | K38.2 | diverticulul apendicelui; diverticuloza apendiculara; diverticul al apendicelui vermiform; diverticulum of appendix; appendiceal diverticulum; appendiceal diverticulosis |
| Diverticul caliceal | Q63.81 | diverticul calicial congenital; diverticul pielocaliceal; chist pielogen; calyceal diverticulum; pyelocalyceal diverticulum; pyelogenic cyst |
| Diverticul vezical | N32.3 | diverticulul vezicii urinare; diverticul al vezicii urinare; diverticuloza vezicala; diverticulum of bladder; bladder diverticulum; vesical diverticulum |
| Diverticul vezical congenital | Q64.6 | diverticul congenital al vezicii; diverticul Hutch; diverticul paraureteral congenital; congenital diverticulum of bladder; congenital bladder diverticulum; Hutch diverticulum |
| Dolicocefalie | Q67.2 | dolicocefalia; cap alungit; dolicocefalie pozitionala; dolichocephaly; positional dolichocephaly; dolichocephalic head |
| Dop de cerumen | H61.2 | ceara in ureche; cerumen impactat; dop de ceara; impacted cerumen; cerumen impaction; earwax impaction; earwax blockage |
| Druze ale papilei optice | H47.3 | druse ale papilei optice; druze ale discului optic; druze papilare; optic disc drusen; optic nerve head drusen; drusen of optic disc |
| Duplicatie uretrala | Q64.73 | uretra dubla; meat urinar dublu; uretra accesorie; urethral duplication; double urethra; duplicated urethra; accessory urethra |
| Durere faciala atipica | G50.1 | algie faciala atipica; durere faciala idiopatica persistenta; prosopalgie atipica; atypical facial pain; persistent idiopathic facial pain; atypical facial neuralgia |
| Durere ovulatorie | N94.0 | dureri intermenstruale; sindrom intermenstrual; durere de ovulatie; Mittelschmerz; ovulation pain; midcycle pain; intermenstrual pain |

## Decise manual, neadăugate

Titluri `nou` / `posibil` care nu au devenit afecțiuni noi: există sub alt nume, sunt variante ale unei categorii (D5), categorii generice sau nu sunt boli (G7). Coloana „Apropiat” e sugestia automată.

| Cod | Titlu CIM-10 | Apropiat |
|---|---|---|
| A36.1 | Difteria nazo-faringiana | Faringita cu Corynebacterium |
| B00.1 | Dermita veziculara datorita virusului herpetic |  |
| B66.2 | Dicrocoeliaza | Dicrocelioza |
| B70 | Diphyllobothriaza si sparganoza |  |
| D80.2 | Deficit selectiv de imunoglobuline A [lgA] | Deficit selectiv de IgA |
| D80.3 | Deficit selectiv in subclasele imunoglobulinelor G [lgG] | Deficit de subclase IgG / Deficit selectiv de IgA |
| D80.6 | Deficit in anticorpi cu imunoglobuline aproape normale sau cu hiperimunoglobulinemie | Deficit selectiv de IgA |
| D81.3 | Deficit de adenosin dezaminaza [ADA] | Deficit de adenozin deaminaza / Deficit de mioadenilat deaminaza |
| D81.7 | Deficit in complex major de histocompatibilitate clasa II |  |
| E10 | Diabet mellitus tip 1 | Diabet zaharat tip 1 |
| E10.1 | Diabet mellitus tip 1 cu acidoza | Diabet zaharat tip 1 |
| E10.11 | Diabet mellitus tip 1 cu acidocetoză, fara coma | Diabet zaharat tip 1 |
| E10.12 | Diabet mellitus tip 1 cu acidocetoză, cu coma | Diabet zaharat tip 1 |
| E10.13 | Diabet mellitus tip 1 cu acidoza lactica, fara coma | Acidoza lactica / Diabet zaharat tip 1 |
| E10.14 | Diabet mellitus tip 1 cu acidoza lactica, cu coma | Acidoza lactica / Diabet zaharat tip 1 |
| E10.15 | Diabet mellitus tip 1 cu acidocetoză, cu acidoza lactica, fara coma | Acidoza lactica / Diabet zaharat tip 1 |
| E10.16 | Diabet mellitus tip 1 cu acidocetoză, cu acidoza lactica, cu coma | Acidoza lactica / Diabet zaharat tip 1 |
| E10.2 | Diabet mellitus tip 1 cu complicatii renale | Diabet zaharat tip 1 / Glicozurie renala |
| E10.21 | Diabet mellitus tip 1 cu nefropatie diabetica incipienta | Diabet zaharat tip 1 / Nefropatie diabetica |
| E10.22 | Diabet mellitus tip 1 cu nefropatie diabetica stabilita | Diabet zaharat tip 1 / Nefropatie diabetica |
| E10.29 | Diabet mellitus tip 1 cu alte complicatii renale specificate | Diabet zaharat tip 1 / Glicozurie renala |
| E10.3 | Diabet mellitus tip 1 cu complicatii oculare | Diabet zaharat tip 1 / Retinopatie diabetica / Diabet zaharat tip 1 cu complicatii |
| E10.31 | Diabet mellitus tip 1 cu retinopatie de fond | Diabet zaharat tip 1 |
| E10.32 | Diabet mellitus tip 1 cu retinopatie preproliferativa | Diabet zaharat tip 1 |
| E10.33 | Diabet mellitus tip 1 cu retinopatie proliferativa | Diabet zaharat tip 1 |
| E10.34 | Diabet mellitus tip 1 cu alte retinopatii | Diabet zaharat tip 1 |
| E10.35 | Diabet mellitus tip 1 cu boala oculara avansata | Diabet zaharat tip 1 |
| E10.36 | Diabet mellitus tip 1 cu cataracta diabetica | Cataracta diabetica / Diabet zaharat tip 1 |
| E10.39 | Diabet mellitus tip 1 cu alte complicatii oculare specificate | Diabet zaharat tip 1 / Retinopatie diabetica |
| E10.4 | Diabet mellitus tip 1 cu cataracta cu complicatii neurologi | Diabet zaharat tip 1 |
| E10.41 | Diabet mellitus tip 1 cu mononeuropatie diabetica | Diabet zaharat tip 1 |
| E10.42 | Diabet mellitus tip 1 cu polineuropatie diabetica | Diabet zaharat tip 1 |
| E10.43 | Diabet mellitus tip 1 cu neuropatie diabetica autonoma | Diabet zaharat tip 1 / Neuropatie autonoma / Neuropatie autonoma diabetica / Neuropatie diabetica |
| E10.49 | Diabet mellitus tip 1 cu alte complicatii neurologice specificate | Diabet zaharat tip 1 |
| E10.5 | Diabet mellitus tip 1 cu complicatii circulatorii | Diabet zaharat tip 1 |
| E10.51 | Diabet mellitus tip 1 cu angiopatie periferica, fara gangrena | Diabet zaharat tip 1 |
| E10.52 | Diabet mellitus tip 1 cu angiopatie periferica, cu gangrena | Diabet zaharat tip 1 |
| E10.53 | Diabet mellitus tip 1 cu cardiomiopatie ischemica diabetica | Cardiomiopatie diabetica / Diabet zaharat tip 1 / Miocardiopatie ischemica |
| E10.6 | Diabet mellitus tip 1 cu alte complicatii specificate | Diabet zaharat tip 1 |
| E10.61 | Diabet mellitus tip 1 cu complicatii diabetice musculoscheletale si ale tesutului conjunctiv specificate | Diabet zaharat tip 1 |
| E10.62 | Diabet mellitus tip 1 cu complicatii ale pielii si tesutului subcutanat specificate | Diabet zaharat tip 1 |
| E10.63 | Diabet mellitus tip 1 cu complicatii periodontale specificate | Diabet zaharat tip 1 |
| E10.64 | Diabet mellitus tip 1 cu hipoglicemie | Diabet zaharat tip 1 |
| E10.65 | Diabet mellitus tip 1 cu control slab | Diabet zaharat tip 1 |
| E10.69 | Diabet mellitus tip 1 cu alte complicatii specificate | Diabet zaharat tip 1 |
| E10.7 | Diabet mellitus tip 1 cu complicatii multiple | Diabet zaharat tip 1 |
| E10.71 | Diabet mellitus tip 1 cu complicatii microvasculare multiple | Diabet zaharat tip 1 |
| E10.73 | Diabet mellitus tip 1 cu ulceratia piciorului datorita unor cauze multiple | Diabet zaharat tip 1 |
| E10.8 | Diabet mellitus tip 1 cu complicatii nespecificate | Diabet zaharat tip 1 / Diabet zaharat tip 1 cu complicatii |
| E10.9 | Diabet mellitus tip 1 fara complicatii | Diabet zaharat tip 1 |
| E11 | Diabet mellitus tip 2 ec etiei de insulina | Diabet zaharat |
| E11.0 | Diabet mellitus tip 2 cu hiperosmolaritate | Diabet zaharat |
| E11.01 | Diabet mellitus tip 2 cu hiperosmolaritate fara coma noncetotica hiperglicemica-hiperosmolara [NKHHC] | Coma hiperosmolara / Diabet zaharat |
| E11.02 | Diabet mellitus tip 2 cu hiperosmolaritate cu coma | Diabet zaharat |
| E11.1 | Diabet mellitus tip 2 cu acidoza | Diabet zaharat |
| E11.11 | Diabet mellitus tip 2 cu acidocetoză, fara coma | Diabet zaharat |
| E11.12 | Diabet mellitus tip 2 cu acidocetoză, cu coma | Diabet zaharat |
| E11.13 | Diabet mellitus tip 2 cu acidoza lactica, fara coma | Acidoza lactica / Diabet zaharat |
| E11.14 | Diabet mellitus tip 2 cu acidoza lactica, cu coma | Acidoza lactica / Diabet zaharat |
| E11.15 | Diabet mellitus tip 2 cu acidocetoză, cu acidoza lactica, fara coma | Acidoza lactica / Diabet zaharat |
| E11.16 | Diabet mellitus tip 2 cu acidocetoză, cu acidoza lactica, cu coma | Acidoza lactica / Diabet zaharat |
| E11.2 | Diabet mellitus tip 2 cu complicatii renale | Diabet zaharat / Glicozurie renala |
| E11.21 | Diabet mellitus tip 2 cu nefropatie diabetica incipienta | Diabet zaharat / Nefropatie diabetica |
| E11.22 | Diabet mellitus tip 2 cu nefropatie diabetica stabilita | Diabet zaharat / Nefropatie diabetica |
| E11.29 | Diabet mellitus tip 2 cu alte complicatii renale specificate | Diabet zaharat / Glicozurie renala |
| E11.3 | Diabet mellitus tip 2 cu complicatii oculare | Diabet zaharat / Retinopatie diabetica / Diabet zaharat tip 2 cu complicatii |
| E11.31 | Diabet mellitus tip 2 cu retonopatie de fond | Diabet zaharat |
| E11.32 | Diabet mellitus tip 2 cu retinopatie preproliferativa | Diabet zaharat |
| E11.33 | Diabet mellitus tip 2 cu retinopatie proliferativa | Diabet zaharat |
| E11.34 | Diabet mellitus tip 2 cu alte retinopatii | Diabet zaharat |
| E11.35 | Diabet mellitus tip 2 cu boala oculara avansata | Diabet zaharat |
| E11.36 | Diabet mellitus tip 2 cu cataracta diabetica | Cataracta diabetica / Diabet zaharat |
| E11.39 | Diabet mellitus tip 2 cu alte complicatii oculare specificate | Diabet zaharat / Retinopatie diabetica |
| E11.4 | Diabet mellitus tip 2 cu complicatii neurologice | Diabet zaharat |
| E11.40 | Diabet mellitus tip 2 cu neuropatie nespecificata | Diabet zaharat |
| E11.41 | Diabet mellitus tip 2 cu mononeuropatie diabetica | Diabet zaharat |
| E11.42 | Diabet mellitus tip 2 cu polineuropatie diabetica | Diabet zaharat |
| E11.43 | Diabet mellitus tip 2 cu neuropatie diabetica autonoma | Diabet zaharat / Neuropatie autonoma / Neuropatie autonoma diabetica / Neuropatie diabetica |
| E11.49 | Diabet mellitus tip 2 cu alte complicatii neurologice specificate | Diabet zaharat |
| E11.5 | Diabet mellitus tip 2 cu complicatii circulatorii | Diabet zaharat |
| E11.51 | Diabet mellitus tip 2 cu angiopatie periferica, fara gangrena (E11 | Diabet zaharat |
| E11.52 | Diabet mellitus tip 2 cu angiopatie periferica, cu gangrena | Diabet zaharat |
| E11.53 | Diabet mellitus tip 2 cu cardiomiopatie ischemica diabetica | Cardiomiopatie diabetica / Diabet zaharat / Miocardiopatie ischemica |
| E11.6 | Diabet mellitus tip 2 cu alte complicatii specificate | Diabet zaharat |
| E11.61 | Diabet mellitus tip 2 cu complicatii diabetice musculoscheletale si ale tesutului conjunctiv specificate | Diabet zaharat |
| E11.62 | Diabet mellitus tip 2 cu complicatii ale pielii si tesutului subcutanat specificate | Diabet zaharat |
| E11.63 | Diabet mellitus tip 2 cu complicatii periodontale specificate | Diabet zaharat |
| E11.64 | Diabet mellitus tip 2 cu hipoglicemie | Diabet zaharat |
| E11.65 | Diabet mellitus tip 2 cu control slab | Diabet zaharat |
| E11.69 | Diabet mellitus tip 2 cu alte complicatii specificate | Diabet zaharat |
| E11.71 | Diabet mellitus tip 2 cu complicatii microvasculare multiple | Diabet zaharat |
| E11.72 | Diabet mellitus tip 2 cu caracteristici de rezistenta la insulina | Diabet zaharat / Rezistenta la insulina |
| E11.73 | Diabet mellitus tip 2 cu ulceratia piciorului datorita unor cauze multiple | Diabet zaharat |
| E11.8 | Diabet mellitus tip 2 cu complicatii nespecificate | Diabet zaharat / Diabet zaharat tip 2 cu complicatii |
| E11.9 | Diabet mellitus tip 2 fara complicatii | Diabet zaharat |
| E14 | Diabet mellitus nespecificat | Diabet zaharat |
| E14.0 | Diabet mellitus nespecificat cu hiperosmolaritate |  |
| E14.01 | Diabet mellitus nespecificat cu hiperosmolaritate, fara coma noncetotica hiperglicemica-hiperosmolara [NKHHC] | Coma hiperosmolara |
| E14.02 | Diabet mellitus nespecificat cu hiperosmolaritate, cu coma |  |
| E14.1 | Diabet mellitus nespecificat cu acidoza |  |
| E14.11 | Diabet mellitus nespecificat cu acidocetoză, fara coma |  |
| E14.12 | Diabet mellitus nespecificat cu acidocetoză, cu coma |  |
| E14.13 | Diabet mellitus nespecificat cu acidoza lactica, fara coma | Acidoza lactica |
| E14.14 | Diabet mellitus nespecificat cu acidoza lactica, cu coma | Acidoza lactica |
| E14.15 | Diabet mellitus nespecificat cu acidocetoză, cu acidoza lactica, fara coma | Acidoza lactica |
| E14.16 | Diabet mellitus nespecificat cu acidocetoză, cu acidoza lactica, cu coma | Acidoza lactica |
| E14.2 | Diabet mellitus nespecificat cu complicatii renale | Glicozurie renala |
| E14.21 | Diabet mellitus nespecificat cu nefropatie diabetica incipienta | Nefropatie diabetica |
| E14.22 | Diabet mellitus nespecificat cu nefropatie diabetica stabilita | Nefropatie diabetica |
| E14.29 | Diabet mellitus nespecificat cu alte complicatii renale specificate | Glicozurie renala |
| E14.3 | Diabet mellitus nespecificat cu complicatii oculare | Retinopatie diabetica |
| E14.31 | Diabet mellitus nespecificat cu retinopatie de fond |  |
| E14.32 | Diabet mellitus nespecificat cu retinopatie preproliferativa |  |
| E14.33 | Diabet mellitus nespecificat cu retinopatie proliferativa |  |
| E14.34 | Diabet mellitus nespecificat cu alte retinopatii |  |
| E14.35 | Diabet mellitus nespecificat cu boala oculara avansata |  |
| E14.36 | Diabet mellitus nespecificat cu cataracta diabetica | Cataracta diabetica |
| E14.39 | Diabet mellitus nespecificat cu alte complicatii oculare specificate | Retinopatie diabetica |
| E14.4 | Diabet mellitus nespecificat cu complicatii neurologice |  |
| E14.40 | Diabet mellitus nespecificat cu neuropatie nespecificata |  |
| E14.41 | Diabet mellitus nespecificat cu mononeuropatie diabetica |  |
| E14.42 | Diabet mellitus nespecificat cu polineuropatie diabetica |  |
| E14.43 | Diabet mellitus nespecificat cu neuropatie diabetica autonoma | Neuropatie autonoma / Neuropatie autonoma diabetica / Neuropatie diabetica |
| E14.49 | Diabet mellitus nespecificat cu alte complicatii neurologice specificate |  |
| E14.5 | Diabet mellitus nespecificat cu complicatii circulatorii |  |
| E14.51 | Diabet mellitus nespecificat cu agiopatie periferica, fara gangrena |  |
| E14.52 | Diabet mellitus nespecificat cu agiopatie periferica, cu gangrena |  |
| E14.53 | Diabet mellitus nespecificat cu cardiomiopatie ischemica diabetica | Cardiomiopatie diabetica / Miocardiopatie ischemica |
| E14.6 | Diabet mellitus nespecificat cu alte complicatii specificate |  |
| E14.61 | Diabet mellitus nespecificat cu complicatii diabetice musculoscheletale si ale tesutului conjunctiv specificate |  |
| E14.62 | Diabet mellitus nespecificat cu complicatii ale pielii si tesutului subcutanat specificate |  |
| E14.63 | Diabet mellitus nespecificat cu complicatii periodontale specificate |  |
| E14.64 | Diabet mellitus nespecificat cu hipoglicemie |  |
| E14.65 | Diabet mellitus nespecificat cu control slab |  |
| E14.69 | Diabet mellitus nespecificat cu alte complicatii specifice |  |
| E14.7 | Diabet mellitus nespecificat cu complicatii multiple |  |
| E14.71 | Diabet mellitus nespecificat cu complicatii microvasculare multiple |  |
| E14.72 | Diabet mellitus nespecificat cu caracteristici de rezistenta la insulina | Rezistenta la insulina |
| E14.73 | Diabet mellitus nespecificat cu ulceratia piciorului datorita unor cauze multiple |  |
| E14.8 | Diabet mellitus nespecificat cu complicatii nespecificate |  |
| E14.9 | Diabet mellitus nespecificat fara complicatii |  |
| E28 | Disfunctia ovariana | Hipogonadism feminin |
| E29 | Disfunctia testiculara | Hipogonadism masculin / Orhita |
| E31 | Disfunctiuni pluriglandulare |  |
| E31.9 | Disfunctii poliglandulare, nespecificate |  |
| E63.1 | Dezechilibru constituentilor alimentari ingerati |  |
| E73.1 | Deficit secundar in lactaza | Intoleranta la lactoza |
| E77.0 | Deficit de transformare post-traductionala a enzimelor lisosomale | Boala cu celule I |
| E80.3 | Deficit in catalaza si peroxidaza |  |
| F00 | Dementa in boala Alzheimer (G30.-†) | Alzheimer |
| F00.0 | Dementa in boala Alzheimer, cu debut precoce (G30.0†) | Alzheimer / Schizofrenie |
| F00.1 | Dementa in boala Alzheimer, cu debut tardiv (G30.1†) | Alzheimer / Dementa mixta |
| F00.2 | Dementa in boala Alzheimer, forma atipica sau mixta (G30.8†) | Alzheimer / Dementa mixta |
| F01.0 | Dementa vasculara cu debut acut | Dementa vasculara |
| F01.1 | Dementa vasculara prin infarcte multiple | Dementa vasculara |
| F01.3 | Dementa vasculara mixta, corticala si subcorticala | Boala Binswanger / Dementa mixta / Dementa vasculara |
| F02.0 | Dementa in boala Pick (G31.0†) | Dementa asociata bolii Parkinson |
| F02.1 | Dementa in boala Creutzfeldt-Jakob (A81.0†) | Boala Creutzfeldt-Jakob |
| F02.2 | Dementa in boala Huntington (G10†) |  |
| F02.4 | Dementa in boala cu virusul imunodeficientei umane [HIV] (B22†) | Sida |
| F05 | Delir, neindus de alcool si alte substante psiho-active |  |
| F05.0 | Delir nesupra-adaugat unei demente, descrisa ca atare |  |
| F05.1 | Delir supra-adaugat unei demente |  |
| F05.9 | Delir nespecificat | Delirium |
| F45.30 | Disfunctie autonoma somatoforma, organ sau sistem nespecificate |  |
| F45.31 | Disfunctie autonoma somatoforma, inima si sistem cardiovascular |  |
| F45.32 | Disfunctie autonoma somatoforma, tract gastrointestinal superior |  |
| F45.33 | Disfunctie autonoma somatoforma, tract gastrointestinal inferior |  |
| F45.34 | Disfunctie autonoma somatoforma, sistem respirator |  |
| F45.35 | Disfunctie autonoma somatoforma, sistem genito-urinar |  |
| F45.38 | Disfunctie autonoma somatoforma, alt organ sau sistem |  |
| F45.39 | Disfunctie autonoma somatoforma, organe sau sisteme multiple |  |
| F52 | Disfuntie sexuala, neprovocata de o tulburare sau boala organica |  |
| F52.3 | Disfunctie orgasmica |  |
| F52.6 | Dispareunie neorganica | Disfonie functionala |
| F52.9 | Disfunctie sexuala nespecificata, necauzata de o tulburare sau o boala organica | Disfunctie sexuala |
| F68.0 | Dezvoltare a simptomelor fizice din motive psihologice |  |
| G23.2 | Degenerescenta striato-nigrica [nigrostriate] | Atrofie multisistemica |
| G24.1 | Distonia idiopatica familiala | Distonie generalizata / Rinita vasomotorie |
| G24.2 | Distonia idiopatica nonfamiliala |  |
| G24.4 | Distonia buco-faciala |  |
| G31.1 | Degenerescenta senila a creierului, neclasificata altundeva | Boala Canavan |
| G36.9 | Demielinizari acute diseminate, nespecificate |  |
| G37.1 | Demielinizarea centrala a corpului calos |  |
| G83.0 | Diplegia membrelor superioare |  |
| G90.3 | Degenerescenta multisistemica | Atrofie multisistemica |
| H01.1 | Dermatoza neinfectioasa a pleoapei |  |
| H05.3 | Deformarea orbitei |  |
| H11.1 | Depuneri si afectiuni degenerative ale conjuctivei |  |
| H18.5 | Distrofia corneeana ereditara | Distrofie corneana |
| H31.1 | Degenerescenta choroidiana | Degenerescenta corneana / Atrofie iriana / Atrofie tiroidiana / Distrofie coroidiana |
| H33 | Dezlipiri si rupturi ale retinei | Dezlipire de retina |
| H33.0 | Dezlipirea retinei cu ruptura retiniana | Dezlipire de retina |
| H35.3 | Degenerescenta maculei si polului posterior |  |
| H35.5 | Distrofia retiniana ereditara | Retinita pigmentara / Degenerescenta retiniana periferica / Distrofie corneana |
| H35.7 | Dezlipirea straturilor retinei | Retinoschizis / Retinopatie seroasa centrala |
| H57.1 | Durere oculara |  |
| I49.1 | Depolarizare atriala prematura |  |
| I49.2 | Depolarizare jonctionala prematura |  |
| I49.3 | Depolarizare ventriculara prematura |  |
| I51.5 | Degenerescenta miocardului | Degenerescenta vitreana |
| I71.0 | Disectia aortei | Disectie de aorta / Anevrism aortic |
| I71.00 | Disectia aortei, localizare nespecificata | Disectie de aorta |
| I71.01 | Disectia aortei toracice | Disectie de aorta |
| I71.02 | Disectia aortei abdominale | Disectie de aorta |
| I71.03 | Disectia aortei toraco-abdominale | Disectie de aorta |
| J33.1 | Degenerescenta polipoida a sinusului |  |
| K00.3 | Dinti patati |  |
| K03.6 | Depozite [acumulare] pe dinti | Tulburare de acumulare |
| K22.5 | Diverticul dobandit al esofagului | Diverticul al esofagului |
| K76.0 | Degenerescenta grasoasa a ficatului, neclasificata altundeva | Steatoza hepatica / Steatoza hepatica alcoolica |
| L11.1 | Dermatoza acantolitica tranzitorie [Grover] |  |
| L13.1 | Dermatoza pustuloasa subcorneeana |  |
| L23.0 | Dermatita alergica de contact datorita metalelor | Dermatita / Dermatita de contact alergica |
| L23.1 | Dermatita alergica de contact datorita adezivilor | Dermatita / Dermatita de contact alergica |
| L23.2 | Dermatita alergica de contact datorita cosmeticelor | Dermatita / Dermatita de contact alergica |
| L23.3 | Dermatita alergica de contact datorita medicamentelor in contact cu pielea | Dermatita / Dermatita de contact alergica |
| L23.4 | Dermatita alergica de contact datorita vopselelor | Dermatita / Dermatita de contact alergica |
| L23.5 | Dermatita alergica de contact datorita produselor chimice | Dermatita / Dermatita de contact alergica |
| L23.6 | Dermatita alergica de contact datorita alimentelor in contact cu pielea | Dermatita / Dermatita de contact alergica |
| L23.7 | Dermatita alergica de contact datorita vegetalelor, exceptand alimentele | Dermatita / Dermatita de contact alergica |
| L23.8 | Dermatita alergica de contact datorita altor agenti | Dermatita / Dermatita de contact alergica |
| L23.9 | Dermatita alergica de contact, cauza nespecificata | Dermatita / Dermatita de contact alergica |
| L24.0 | Dermatita iritanta de contact datorita detergentilor | Dermatita / Dermatita de contact iritativa |
| L24.1 | Dermatita iritanta de contact datorita uleiurilor si grasimilor | Dermatita / Dermatita de contact iritativa |
| L24.2 | Dermatita iritanta de contact datorita solventilor | Dermatita / Dermatita de contact iritativa |
| L24.3 | Dermatita iritanta de contact datorita cosmeticelor | Dermatita / Dermatita de contact iritativa |
| L24.4 | Dermatita iritanta de contact datorita medicamentelor in contact cu pielea | Dermatita / Dermatita de contact iritativa |
| L24.5 | Dermatita iritanta de contact datorita altor produse chimice | Dermatita / Dermatita de contact iritativa |
| L24.6 | Dermatita iritanta de contact datorita alimentelor in contact cu pielea | Dermatita / Dermatita de contact iritativa |
| L24.7 | Dermatita iritanta de contact datorita vegetalelor, exceptand alimentele | Dermatita / Dermatita de contact iritativa |
| L24.8 | Dermatita iritanta de contact datorita altor agenti | Dermatita / Dermatita de contact iritativa |
| L24.9 | Dermatita iritanta de contact, cauza nespecificata | Dermatita / Dermatita de contact iritativa |
| L25.0 | Dermatita de contact nespecificata datorita cosmeticelor | Dermatita |
| L25.1 | Dermatita de contact nespecificata datorita medicamentelor in contact cu pielea | Dermatita |
| L25.2 | Dermatita de contact nespecificata datorita vopselelor | Dermatita |
| L25.3 | Dermatita de contact nespecificata datorita altor produse chimice | Dermatita |
| L25.4 | Dermatita de contact nespecificata datorita alimentelor in contact cu pielea | Dermatita |
| L25.5 | Dermatita de contact nespecificata dato-rita vegetalelor, exceptand alimentele | Dermatita |
| L25.8 | Dermatita de contact nespecificata datorita altor agenti | Dermatita |
| L25.9 | Dermatita de contact nespecificata din cauze nespecificate | Dermatita / Edera otravitoare / Dermatita de contact alergica |
| L27 | Dermatita datorita substantelor ingerate |  |
| L27.2 | Dermatita datorita ingestiei de alimente |  |
| L27.8 | Dermatita datorita altor substante ingerate |  |
| L27.9 | Dermatita datorita unei substante ingerate nespecificate |  |
| L50.3 | Dermatografism urticarian |  |
| L98.2 | Dermatoza neutrofila febrila [Sweet] | Sindrom Sweet |
| M14.3 | Dermato-artrita lipoida (E78.8†) |  |
| M20 | Deformatii dobandite ale degetelor de la mana si picior |  |
| M20.0 | Deformatia deget(e) de la mana |  |
| M20.6 | Deformatia dobandita a degetului(lor) de la picior, nespecificata |  |
| M21.0 | Deformatia valgus, neclasificata altundeva |  |
| M21.1 | Deformatia in varus, neclasificata altundeva | Boala Blount |
| M21.2 | Deformatia in flexiune |  |
| M21.9 | Deformatii dobandite ale membrelor, nespecificate |  |
| M25.5 | Durere in articulatie | Sindrom al articulatiei temporo-mandibulare / Luxatie |
| M33 | Dermatopolimiozita | Dermatomiozita |
| M36.0 | Dermato(poli)miozita in boli neoplazice (C00-D48†) | Poliomielita |
| M43.9 | Dorsopatia deformanta, nespecificata | Boala Paget osoasa / Scolioza |
| M46.4 | Discita, nespecificata | Spondilodiscita |
| M53.9 | Dorsopatia, nespecificata |  |
| M54 | Dorsalgia |  |
| M62.0 | Diastaza musculara | Rabdomioliza |
| M71.4 | Depozit de calciu in bursa |  |
| M79.6 | Durere la nivelul unui membru |  |
| M95.0 | Diformitate dobandita a nasului |  |
| M95.3 | Diformitate dobandita a gatului |  |
| M95.4 | Diformitate dobandita a toracelui si coastelor |  |
| M95.5 | Diformitate dobandita a pelvisului |  |
| M95.9 | Diformitate dobandita a sistemului musculo-scheletal, nespecificata |  |
| M99.0 | Disfunctie segmentara si somatica |  |
| N18.91 | Deficienta renala cronica | Insuficienta renala / Boala Addison |
| N31 | Disfunctia neuro-musculara a vezicii urinare |  |
| N31.9 | Disfunctiunea neuro-musculara a vezicii urinare, nespecificata |  |
| N60 | Displazia mamara benigna |  |
| N87 | Displazia colului uterin | Displazie cervicala / Polip cervical |
| N87.0 | Displazia usoara a colului uterin | Displazie cervicala / Neoplazie intraepiteliala cervicala |
| N87.1 | Displazia moderata a colului uterin | Displazie cervicala / Neoplazie intraepiteliala cervicala |
| N87.2 | Displazia severa a colului uterin, neclasificata altundeva | Displazie cervicala |
| N89.0 | Displazia usoara a vaginului | Neoplazie intraepiteliala vaginala |
| N89.1 | Displazia moderata a vaginului | Neoplazie intraepiteliala vaginala |
| N89.2 | Displazia severa a vaginului, neclasificata altundeva |  |
| N89.3 | Displazia vaginului, nespecificata |  |
| N90.0 | Displazia usoara a vulvei | Neoplazie intraepiteliala vulvara |
| N90.1 | Displazia moderata a vulvei | Neoplazie intraepiteliala vulvara |
| N90.2 | Displazia severa a vulvei, neclasificata altundeva |  |
| N90.3 | Displazia vulvei, nespecificata |  |
| N94 | Durere si alte afectiuni asociate cu organele genitale feminine si cu ciclul menstrual | Dismenoree |
| N94.4 | Dismenoree primara | Dismenoree / Amenoree primara / Oligomenoree |
| N94.5 | Dismenoree secundara | Dismenoree / Amenoree secundara |
| O09 | Durata sarcinii |  |
| O09.0 | Durata sarcinii < 5 saptamani complete |  |
| O09.1 | Durata sarcinii 5-13 saptamani complete |  |
| O09.2 | Durata sarcinii 14-19 saptamani complete |  |
| O09.3 | Durata sarcinii 20-25 saptamani complete |  |
| O09.4 | Durata sarcinii 26-33 saptamani complete |  |
| O09.5 | Durata sarcinii 34-36 saptamani complete |  |
| O24 | Diabet mellitus in sarcina | Diabet gestational |
| O24.0 | Diabet mellitus pre-existent, tip 1, in sarcina | Diabet gestational / Diabet zaharat tip 1 |
| O24.1 | Diabetul mellitus pre-existent, tip 2, in sarcina | Diabet gestational / Diabet zaharat |
| O24.2 | Diabetul mellitus pre-existent, alt tip specificat, in sarcina | Diabet gestational |
| O24.3 | Diabetul mellitus pre-existent, nespecificat, in sarcina | Diabet gestational |
| O24.4 | Diabetul mellitus survenit in timpul sarcinii | Diabet gestational |
| O24.9 | Diabetul mellitus in sarcina, cu debut nespecificat | Diabet gestational |
| O45 | Dezlipirea prematura a placentei [hematom retro-placentar] | Decolment prematur de placenta |
| O45.0 | Dezlipirea prematura a placentei cu anomalii de coagulare |  |
| O45.9 | Dezlipirea prematura a placentei, nespecificata | Decolment prematur de placenta |
| O64 | Distocia de obstacol datorita unei pozitii si prezentatii anormale a fatului |  |
| O64.0 | Distocia de obstacol datorita unei rotatii incomplete a capului fatului |  |
| O64.1 | Distocia de obstacol datorita unei prezentatii pelvine |  |
| O64.2 | Distocia de obstacol datorita unei prezentatii faciale |  |
| O64.3 | Distocia de obstacol datorita unei prezentatii frontale |  |
| O64.4 | Distocia de obstacol datorita unei prezentatii umerale |  |
| O64.5 | Distocia de obstacol datorita unei prezentatii complexe |  |
| O64.8 | Distocia de obstacol datorita altor pozitii si prezentatii anormale |  |
| O64.9 | Distocia de obstacol datorita unei pozitii si prezentatii anormale, nespecificate |  |
| O65 | Distocia de obstacol datorita unei anomalii pelviene a mamei |  |
| O65.0 | Distocia de obstacol datorita unei deformari pelviene |  |
| O65.1 | Distocia de obstacol datorita unui bazin ingust in general |  |
| O65.2 | Distocia de obstacol datorita unei ingustari a stramtorii superioare |  |
| O65.3 | Distocia de obstacol datorita unei ingustari a stramtorii inferioare si a cavitatii medii |  |
| O65.4 | Distocia de obstacol datorita unei disproportii feto-pelviene, nespecificata |  |
| O65.5 | Distocia de obstacol datorita unei anomalii a organelor pelviene ale mamei |  |
| O65.8 | Distocia de obstacol datorita altor anomalii pelviene ale mamei |  |
| O66.0 | Distocia de obstacol datorita unei distocii a umarului | Distocie de umar |
| O66.1 | Distocia de obstacol gemelar |  |
| O66.2 | Distocia de obstacol datorita unui fat anormal de mare |  |
| O66.3 | Distocia de obstacol datorita anomaliilor fetale |  |
| O66.9 | Distocia de obstacol, nespecificata |  |
| O90.0 | Desprinderea unei suturi de cezariana |  |
| O90.1 | Desprinderea unei suturi obstetricale la nivelul perineului |  |
| O95 | Deces obstetrical datorita unei cauze nespecificate |  |
| O96 | Deces de origine obstetricala, survenind peste mai mult de 42 zile dar mai putin de un an dupa nastere |  |
| O97 | Deces prin sechele survenind dintr-o cauza obstetricala directa |  |
| P12.3 | Distrugerea scalpului datorita traumatismului la nastere | Traumatism obstetric |
| P74.1 | Deshidratarea nou-nascutului |  |
| P78.3 | Diareea neinfectioasa neonatala | Diabet neonatal / Apnee prematurului / Acnee neonatala |
| P91.4 | Diminuarea activitatii cerebrale la nou-nascut |  |
| P92.5 | Dificultati in alaptarea nou-nascutului |  |
| Q04.4 | Displazia septului si cailor optice |  |
| Q39.5 | Dilatatia congenitala a esofagului | Duplicatie esofagiana / Megaureter |
| Q39.81 | Duplicare congenitala a esofagului | Duplicatie esofagiana |
| Q39.82 | Dismotilitate esofagiana |  |
| Q43.4 | Duplicatia intestinului | Dublura intestinala / Neuropatie viscerala intestinala / Miopatie viscerala intestinala |
| Q45.82 | Duplicatia organelor digestive, neclasificate altundeva |  |
| Q61.4 | Displazia renala | Displazie renala multichistica / Displazie de rect |
| Q61.40 | Displazia renala, nespecificata | Displazie renala multichistica / Displazie de rect |
| Q61.41 | Displazia renala chistica, unilaterala | Displazie renala multichistica |
| Q61.42 | Displazia renala chistica, bilaterala | Displazie renala multichistica |
| Q62 | Defecte obstructive congenitale ale pelvisului renal si malformatiile congenitale ale ureterului |  |
| Q62.5 | Dublarea ureterului |  |
| Q64.43 | Diverticul al uracei |  |
| Q64.71 | Diverticul uretral anterior congenital | Diverticul uretral |
| Q65 | Deformatii congenitale ale soldului |  |
| Q65.0 | Dislocarea congenitala a soldului, unilaterala |  |
| Q65.1 | Dislocarea congenitala a soldului, bilaterala |  |
| Q65.2 | Dislocarea congenitala a soldului, nespecificata | Luxatie congenitala de cap radial |
| Q65.9 | Deformatia congenitala a soldului, nespecificata | Coxa vara congenitala |
| Q66 | Deformatii congenitale ale piciorului |  |
| Q66.9 | Deformatia congenitala a piciorului, nespecificata |  |
| Q67 | Deformatii congenitale musculo-scheletale ale capului, fetei, coloanei vertebrale si pieptului |  |
| Q67.42 | Deviatia septului nasal, congenitala |  |
| Q67.5 | Deformatii congenitale ale coloanei vertebrale |  |
| Q68.0 | Deformatii congenitale ale muschiului sternocleidomastoidian | Torticolis congenital |
| Q68.1 | Deformatii congenitale ale mainii |  |
| Q68.2 | Deformatii congenitale ale genunchiului |  |
| Q69.2 | Deget(e) de la picioare supranumerar(e) | Polidactilie |
| Q70.0 | Degete fuzionate |  |
| Q70.2 | Degetele de la picioare fuzionate |  |
| Q70.3 | Degetele de la picioare unite |  |
| Q74.03 | Deget mare de la mana trifalangian |  |
| Q74.07 | Deget(e) bifid(e) al membrului superior |  |
| Q74.08 | Deformatia Sprengel | Sindrom Sprengel |
| Q75.5 | Disostoza oculo-mandibulara |  |
| Q75.81 | Displazia fronto-nasala | Displazie frontonazala |
| Q78.1 | Displazia fibroasa poliostotica | Displazie fibroasa |
| Q82.4 | Displazia ectodermala (anhidrotica) | Sindrom Ellis-van Creveld / Displazie ectodermica / Anhidroza |
| Q86.2 | Dismorfism datorita warfarinei |  |
| Q89.31 | Dextrocardia cu situs inversus | Situs inversus |
| Q89.41 | Dicefalia |  |
| Q92.4 | Dublarea observata numai in prometafaza |  |
| Q92.5 | Dublarea cu alte rearanjamente complexe |  |

## Existente (potrivire automată)

Candidații pentru sinonime adăugate ulterior (D6).

| Cod | Titlu CIM-10 | Afecțiune | Potrivire |
|---|---|---|---|
| A06.0 | Dizenteria amibiana acuta | Dizenterie amibiana | temporal (G1) |
| A09 | Diareea si gastro-enterita probabil infectioase | Tuberculoza | exact |
| A36 | Difteria | Difterie | terminatii |
| A36.0 | Difteria faringiana | Faringita cu Corynebacterium | terminatii |
| A36.2 | Difteria laringiana | Difterie laringiana | terminatii |
| A36.3 | Difteria cutanata | Difterie cutanata | terminatii |
| A90 | Denga (denga clasica) | Denga | exact |
| B35 | Dermatofitoze | Dermatofitoza | terminatii |
| B65.3 | Dermatita cercariara | Dermatita schistosomica | terminatii |
| B70.0 | Diphyllobothriaza | Difilobotrioza | exact |
| B72 | Dracunculoza | Dracunculoza | exact |
| D50.1 | Disfagia sideropenica | Sindrom Plummer-Vinson | terminatii |
| D69.1 | Defecte calitative ale trombocitelor | Boala Glanzmann | exact |
| E10.23 | Diabet mellitus tip 1 cu boala renala stadiu final [ESRD] | Insuficienta renala cronica terminala | exact |
| E11.23 | Diabet mellitus tip 2 cu boala renala stadiu final [ESRD] | Insuficienta renala cronica terminala | exact |
| E14.23 | Diabet mellitus nespecificat cu boala renala stadiu final [ESRD] | Insuficienta renala cronica terminala | exact |
| E23.2 | Diabetul insipid | Diabet insipid | terminatii |
| E77.1 | Deficit de degradare a glicoproteinelor | Fucozidoza | exact |
| E78.6 | Deficit in lipoproteine | Abetalipoproteinemie | exact |
| F01 | Dementa vasculara | Dementa vasculara | exact |
| F01.2 | Dementa vasculara subcorticala | Boala Binswanger | exact |
| F02.3 | Dementa in boala Parkinson (G20†) | Dementa asociata bolii Parkinson | exact |
| F03 | Dementa nespecificata | Dementa | exact |
| F34.1 | Distimie | Distimie | exact |
| F45.3 | Disfunctia somatoforma autonoma | Astenie neurocirculatora | exact |
| G24 | Distonia | Distonie | terminatii |
| G71.0 | Distrofia musculara | Distrofie musculara | terminatii |
| G90.1 | Disautonomia familiala [Riley-Day] | Sindrom Riley-Day | terminatii |
| H04.0 | Dacrioadenita | Dacrioadenita | exact |
| H18.4 | Degenerescenta corneei | Arcul senil | terminatii |
| H31.2 | Distrofia ereditara a choroidei | Distrofie coroidiana | exact |
| H31.4 | Dezlipirea choroidei | Detasament coroidian | exact |
| H35.4 | Degenerescenta retiniana periferica | Degenerescenta retiniana periferica | exact |
| H53.2 | Diplopia | Diplopie | exact |
| H69.0 | Distensiunea trompei Eustache | Trompa Eustachio deschisa | exact |
| K22.4 | Dischinezia esofagului | Spasme esofagiene difuze | exact |
| K29.8 | Duodenita | Duodenita | exact |
| K30 | Dispepsia | Dispepsie | terminatii |
| K31.0 | Dilatatia acuta a stomacului | Dilatatie gastrica acuta | terminatii |
| K31.4 | Diverticul gastric | Diverticul gastric | exact |
| K59.1 | Diareea functionala | Diaree functionala | exact |
| L13.0 | Dermatita herpetiforma | Dermatita herpetiforma | exact |
| L20 | Dermatita atopica | Eczema | exact |
| L21 | Dermatita seboreica | Dermatita | exact |
| L22 | Dermita (iritatie de scutec) | Dermatita de scutec | exact |
| L23 | Dermatita alergica de contact | Dermatita de contact alergica | exact |
| L24 | Dermatita iritanta de contact | Dermatita de contact iritativa | exact |
| L25 | Dermatita de contact nespecificata | Dermatita | exact |
| L26 | Dermatita exfoliativa | Dermatita exfoliativa | exact |
| L30.0 | Dermita numulara | Dermatita numulara | exact |
| L30.1 | Dishidroza [pompholyx] | Dermatita disidrozica | exact |
| L30.9 | Dermatita, nespecificata | Dermatita | exact |
| L60.3 | Distrofia unghiilor | Onicodistrofie | exact |
| L71.0 | Dermatita periorala | Dermatita periorala | exact |
| L81.7 | Dermatoza purpurica pigmentata | Capilarita | exact |
| M33.0 | Dermatomiozita juvenila | Dermatomiozita juvenila | exact |
| M54.5 | Dorsalgie joasa | Lombalgie | exact |
| M65.3 | Deget "in resort" | Deget in resort | exact |
| M85.0 | Displazia fibroasa (localizata) | Displazie fibroasa | terminatii |
| N25.1 | Diabet insipid nefrogen | Diabet insipid nefrogenic | exact |
| N36.1 | Diverticul uretral | Diverticul uretral | exact |
| N94.1 | Dispareunie | Dispareunie | exact |
| N94.6 | Dismenoree, nespecificata | Dismenoree | exact |
| P70.2 | Diabet mellitus neonatal | Diabet neonatal | exact |
| Q06.2 | Diastematomielia | Diastematomielie | exact |
| Q21.0 | Defect septal ventricular | Comunicare interventriculara | exact |
| Q21.1 | Defect septal atrial | Comunicare interatriala | exact |
| Q21.2 | Defect septal atrio-ventricular | Defect de sept atrioventricular | exact |
| Q21.4 | Defect septal aorto-pulmonar | Fereastra aortopulmonara | exact |
| Q24.0 | Dextrocardia | Dextrocardia | exact |
| Q39.6 | Diverticul al esofagului | Diverticul al esofagului | exact |
| Q43.0 | Diverticul Meckel | Diverticul Meckel | exact |
| Q69.0 | Deget(e) supranumerar(e) | Polidactilie | terminatii |
| Q70.1 | Degete lipite | Sindactilie | exact |
| Q75.1 | Disostoza cranio-faciala | Sindrom Crouzon | exact |
| Q75.4 | Disostoza mandibulo-faciala | Sindrom Treacher Collins | exact |
| Q77.5 | Displazia distrofica | Nanism diastrofic | exact |
| Q77.6 | Displazia condroectodermala | Sindrom Ellis-van Creveld | terminatii |
| Q77.7 | Displazia spondiloepifizara | Displazie spondiloepifizara | terminatii |
| Q78.3 | Displazia progresiva diafizala | Sindrom Camurati-Engelmann | terminatii |
| Q78.5 | Displazia metafizei | Displazie metaphizara | exact |
| Q82.3 | Deficienta pigmentara | Incontinentia pigmenti | exact |
