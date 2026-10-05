# Litera F — raport CIM-10

- coduri CIM-10 cu titlul la litera F: **258**
- eliminate automat (P2): **79**
  - fat afectat de mama: 57
  - subzona de organ (D5): 14
  - dublura categoriei parinte (nespecificat): 8
- găsite automat în dicționar (P4.1–P4.3): **57**
- de decis manual (`nou` + `posibil`): **122**
- **afecțiuni adăugate: 39**

## Decizii manuale

- **Existau sub alt nume** (G3): febra purpurie prin *R. rickettsii* / febra Sao Paulo (`Febra pustoaselor stancoase`), prin *R. conorii* (`Febra butonoasa`), febra ecvină de Venezuela (`Encefalita ecvina venezuelana`), febra de Oroya (`Bartoneloza`), febra Kew Garden (`Rickettsioza variceliforma`), febra pădurii Barmah (`Infectie cu virusul Barmah Forest`), filarioza cu *Brugia timori* (sinonim la `Filarioza cu Brugia malayi`), fibroza prin bauxită și grafit (`Pneumoconioza de bauxita`, `Pneumoconioza de grafit`), fibroza pulmonară după iradiere (`Pneumopatia de iradiere`), fibroza miocardică (`Cardioscleroza`), flebita intracraniană (`Tromboza de sinus venos cerebral`), flebita superficială (`Tromboflebita`), fistula vezico-intestinală (`Fistula colovesicala`), fistula rectală/anorectală (`Fistula anala`), fisura mamelonului, inclusiv cea puerperală (`Sfarcuri dureroase`), fibroscleroza sânului (`Mastopatie fibrochistica`), flebotromboza profundă în sarcină și lăuzie (`Tromboza venoasa profunda`, `Tromboza puerperala`), fătul născut mort (`Moarte fetala in utero`), furunculul pleoapei/urechii/vulvei (`Abces palpebral`, `Otita externa circumscrisa`, `Abces vulvar`), fogo selvagem (formă endemică de `Pemfigus foliaceu`), Franceschetti (`Sindrom Treacher Collins`), fibroplazia retrolentală (`Retinopatie de prematuritate`).
- **Potriviri automate greșite, dar boala există:** „Febre recurente” (A68) = `Febra` [G1] — de fapt ambele febre recurente (prin păduchi, prin căpușe) există ca intrări proprii; „Fibromatoza fasciala plantara” (M72.2) = `Pinten calcanean` — boala Ledderhose există ca `Fibromatoza plantara`.
- **Grupate în categoria lor (D5 / G1):** febra galbenă silvestră/citadină, fibroza chistică cu manifestări pulmonare/alte, flebita venei femurale și a venelor profunde (în `Flebita` / `Tromboza venoasa profunda`), fibroza alcoolică a ficatului (boala hepatică alcoolică), fibroza hepatică cu scleroză, fenilcetonuria clasică, fisurile palatului (moale, boltă, combinate) și fisurile labio-palatine uni/bilaterale (`Fisura palatina`, `Fisura labiopalatina`), fistulele traheo-/bronho-esofagiene congenitale, fistula congenitală a rectului și anusului, fistula mastoidei (mastoidita cronică), formele combinate de cataractă senilă, faza activă a trahomului, stadiile pianului (framboesia), focomelia brațului/membrului inferior, fistula congenitală a glandelor salivare (în `Fistula salivara`).
- **Nu sunt boli anume (G7 / P2):** „Febra” simplă și febra nou-născutului (simptom), febrele virale „nespecificate” (A92.9, A94, A99, A96, A77 și A77.9 generice), factorii psihologici (F54), abuzul de substanțe nepsihoactive (F55), fobia nespecificată, flashback-urile, furtul în grup (tulburare de conduită), funcționarea defectuoasă a traheostomiei/stomiei urinare (complicații de procedură), fracturile (de oboseală, patologice, metastatice, după implant, obstetricale — leziuni, rămân sub `Fractura` / `Traumatism obstetric`), fasciculul Krukenberg (semn), fragilitatea părului, fecalomul apendicelui, „Fat si nou-nascut afectati de…” (P00–P04), categoriile „Fistule implicand tractul genital feminin” și „Fasciita”/„Fistula arteriala” generice, facomatozele (categorie generică; bolile ei — neurofibromatoza, scleroza tuberoasă etc. — există separat), titlurile stricate sau cu `title_en` nepotrivit (K08.81, P28.81, Q64.75).
- **Variante păstrate separat (G4):** fistulele după organ (salivară, apendiculară, biliară, articulară, uretrală, enterovaginală, arterioportală) — dicționarul are deja fistule separate pe organ; fluoroza dentară ≠ fluoroza scheletală; fibroza endomiocardică tropicală (Davies) ≠ boala endomiocardică eozinofilică Löffler (`Sindrom hipereozinofilic cardiac`); fibromatoza gingivală (ereditară) ≠ hiperplazia gingivală (titlul K06.1, rămâne pentru H); fasciita nodulară ≠ celelalte fasciite; febra Pontiac (legioneloză fără pneumonie) ≠ `Boala legionarilor`; furunculul nazal ≠ `Vestibulita nazala`; feohifomicoza cerebrală ≠ subcutanată ≠ `Cromoblastomikoza`. Parafiliile (`Fetisism`, `Froteurism`) lipseau complet din dicționar; le-am adăugat ca tulburări F65 reale.
- **Din pending_by_letter (pasul A), re-verificate și adăugate:** `Feohifomicoza cerebrala` (B43.1), `Feohifomicoza subcutanata` (B43.2), `Furuncul nazal` (J34.0), `Funiculita` (N49.1).
- **Sinonime insuficiente (2.4):** fibroza splinei (D73.8), fibroza uterului (N85.8), fibroza pulmonară congenitală (P27.8), fragilitatea capilară ereditară (D69.8), fistula uretro-scrotală (N50.8), fistula intestino-uterină (N82.4), fistulele genito-cutanate la femeie (N82.5), fistula congenitală uter–tract digestiv/urinar (Q51.7), formațiunea de țesut dentar dur în pulpă (K04.3).
- **Amânate la altă literă** (`pending_from_F.jsonl`, 11): T — `Tifos siberian de capuse` (A77.2), `Tifos de capuse Queensland` (A77.3), `Travestism fetisist` (F65.1), `Trasatura drepanocitara` (D57.3); E — `Exantem Boston` (A88.0); P — `Pileflebita` (K75.1), `Pseudartroza` (M84.1); C — `Calus vicios` (M84.0); A — `Atritie dentara` (K03.0), `Atrofodermie vermiculata` (L66.4); U — `Uvula bifida` (Q35.7).
- **Amânate de la alte litere, adăugate la unire (coordonator, 6):** `Feohifomicoza` (B43.1, B43.2; de la C); `Fistula de lichid cefalorahidian` (G96.0; de la P); `Febra Sennetsu` (A79.8; de la R); `Fetopatie diabetica` (P70.0, P70.1; de la S); `Fibroelastom papilar` (D15.1; de la T); `Fibroadenom mamar` (D24; de la T). Verificate față de dicționarul unit al tuturor literelor (G3, G6).

## Adăugate

| Nume canonic | Coduri | Sinonime |
|---|---|---|
| Fascita nodulara | M72.4 | fibromatoza pseudosarcomatoasa; fasciita nodulara; fasciita pseudosarcomatoasa; pseudosarcomatous fibromatosis; nodular fasciitis; pseudosarcomatous fasciitis; infiltrative fasciitis |
| Fat papiraceu | O31.0 | fat presat; fetus papiraceus; fat comprimat; papyraceous fetus; fetus papyraceus; fetus compressus |
| Febra pappataci | A93.1 | febra tantarului de nisip; febra flebotomilor; febra Phlebotomus; sandfly fever; pappataci fever; phlebotomus fever |
| Febra Pontiac | A48.2 | boala legionarilor fara semne pulmonare; legioneloza nepneumonica; forma nepneumonica a legionelozei; nonpneumonic Legionnaires' disease; Pontiac fever; non-pneumonic legionellosis |
| Febra purpurica braziliana | A48.4 | febra purpurica din Brazilia; infectie sistemica cu Haemophilus aegyptius; sepsis cu Haemophilus aegyptius; Brazilian purpuric fever; systemic Haemophilus aegyptius infection; Haemophilus aegyptius sepsis |
| Febra Sennetsu | A79.8 | rickettsioza datorita Ehrlichia sennetsu; ehrlichioza Sennetsu; neorickettsioza Sennetsu; infectie cu Neorickettsia sennetsu; Sennetsu fever; Sennetsu ehrlichiosis; Sennetsu neorickettsiosis; Neorickettsia sennetsu infection |
| Femur curbat congenital | Q68.3 | curbura congenitala a femurului; femur arcuat congenital; incurbare congenitala a femurului; congenital bowing of femur; congenital femoral bowing; congenital curvature of femur |
| Feohifomicoza | B43.1, B43.2 | abces feomicotic; infectie cu fungi dematiacei; micoza cu fungi pigmentati; phaeohyphomycosis; phaeomycotic abscess; dematiaceous fungal infection |
| Feohifomicoza cerebrala | B43.1 | abces feomicotic cerebral; abces cerebral feohifomicotic; cromomicoza cerebrala; cerebral phaeohyphomycosis; phaeomycotic brain abscess; cerebral chromomycosis |
| Feohifomicoza subcutanata | B43.2 | abces feomicotic subcutanat; chist feomicotic subcutanat; feohifomicoza cutanata; subcutaneous phaeohyphomycosis; subcutaneous phaeomycotic abscess; phaeomycotic cyst |
| Fetisism | F65.0 | fetisism sexual; tulburare fetisista; parafilie fetisista; fetishism; fetishistic disorder; sexual fetishism |
| Fetopatie diabetica | P70.0, P70.1 | sindromul copilului cu mama diabetica; embriofetopatie diabetica; nou-nascut din mama diabetica; syndrome of infant of a diabetic mother; diabetic fetopathy; infant of diabetic mother |
| Fibroadenom mamar | D24 | fibroadenom; adenofibrom mamar; fibroadenom al sanului; fibroadenoma; breast fibroadenoma; fibroadenoma of breast |
| Fibroelastom papilar | D15.1 | fibroelastom papilar cardiac; fibroelastom valvular; tumora papilara valvulara; papillary fibroelastoma; cardiac papillary fibroelastoma; valvular papillary fibroelastoma |
| Fibromatoza gingivala | K06.1 | fibromatoza gingivala ereditara; elefantiazis gingival; hiperplazie gingivala fibromatoasa; gingival fibromatosis; hereditary gingival fibromatosis; elephantiasis gingivae |
| Fibroscleroza multifocala | M35.5 | fibroscleroza multifocala idiopatica; fibroscleroza sistemica idiopatica; fibroza sistemica idiopatica; multifocal fibrosclerosis; idiopathic multifocal fibrosclerosis; systemic idiopathic fibrosclerosis |
| Fibroza endomiocardica | I42.3 | fibroza endomiocardica tropicala; boala Davies; fibroza endomiocardica africana; endomyocardial fibrosis; tropical endomyocardial fibrosis; Davies disease |
| Fibroza submucoasa orala | K13.5 | fibroza submucoasa a gurii; fibroza submucoasa a limbii; fibroza submucoasa bucala; oral submucous fibrosis; submucous fibrosis of mouth; oral submucosal fibrosis |
| Ficat accesoriu | Q44.7 | lob hepatic accesoriu; ficat ectopic; tesut hepatic ectopic; accessory liver; accessory hepatic lobe; ectopic liver |
| Fistula apendiculara | K38.3 | fistula apendicelui; fistula apendiculo-cutanata; fistula a apendicelui vermiform; fistula of appendix; appendiceal fistula; appendicocutaneous fistula |
| Fistula arterioportala | Q26.6 | fistula intre vena porta si artera hepatica; fistula arterioportala congenitala; fistula arteriovenoasa hepatoportala; portal vein-hepatic artery fistula; arterioportal fistula; hepatoportal arteriovenous fistula |
| Fistula articulara | M25.1 | fistula articulatiei; fistula sinoviala; fistula sinoviocutanata; fistula of joint; joint fistula; synovial fistula |
| Fistula biliara | K83.3 | fistula cailor biliare; fistula coledocoduodenala; fistula a canalului biliar; fistula of bile duct; biliary fistula; bile duct fistula |
| Fistula de lichid cefalorahidian | G96.0 | pierdere de lichid cefalorahidian; scurgere de lichid cefalorahidian; fistula de LCR; cerebrospinal fluid leak; CSF leak; cerebrospinal fluid fistula |
| Fistula enterovaginala | N82.2 | fistula vaginului cu intestinul subtire; fistula intestino-vaginala; fistula ileovaginala; fistula of vagina to small intestine; enterovaginal fistula; ileovaginal fistula |
| Fistula salivara | K11.4, Q38.4 | fistula glandelor salivare; fistula parotidiana; fistula salivara cutanata; fistula of salivary gland; salivary fistula; parotid fistula |
| Fistula uretrala | N36.0 | fistula a uretrei; fistula uretrocutanata; fistula uretroperineala; urethral fistula; urethrocutaneous fistula; fistula of urethra |
| Fisura laringiana | Q31.8 | fisura laringotraheala; fisura posterioara a cartilagiului cricoid; fisura laringiana posterioara; laryngeal cleft; laryngotracheal cleft; posterior laryngeal cleft |
| Flebectazie congenitala | Q27.4 | flebectazia congenitala; ectazie venoasa congenitala; dilatatie venoasa congenitala; congenital phlebectasia; congenital venous ectasia; congenital venous dilatation |
| Fluoroza dentara | K00.3 | dinti patati; smalt patat; fluoroza smaltului; mottled teeth; dental fluorosis; mottled enamel |
| Fluoroza scheletala | M85.1 | fluoroza osoasa; osteofluoroza; fluoroza endemica a scheletului; skeletal fluorosis; osteofluorosis; bone fluorosis |
| Foliculita decalvanta | L66.2 | foliculita decalvans; boala Quinquaud; foliculita decalvanta Quinquaud; folliculitis decalvans; Quinquaud disease; tufted folliculitis |
| Froteurism | F65.8 | froterism; tulburare froteurista; frotaj; frotteurism; frotteuristic disorder; frottage |
| Fungemie | B49 | septicemie fungica; sepsis fungic; infectie fungica a sangelui; fungemia; fungal sepsis; fungal bloodstream infection |
| Funiculita | N49.1 | inflamatia cordonului spermatic; deferentita; vasita; funiculitis; inflammation of spermatic cord; vasitis |
| Furuncul nazal | J34.0 | abces al nasului; furuncul al vestibulului nazal; furunculoza nazala; nasal furuncle; abscess of nose; nasal vestibular furunculosis |
| Fuziune costala congenitala | Q76.62 | fuziunea congenitala a coastelor; sinostoza costala congenitala; coaste fuzionate congenital; congenital fusion of ribs; rib fusion; fused ribs |
| Fuziune dentara | K00.2 | fuziunea dintilor; dinti fuzionati; sinodontie; dental fusion; fused teeth; synodontia |
| Fuziune testiculara | Q55.1 | fuzionarea testiculelor; sinorhidie; testicule fuzionate; testicular fusion; synorchidism; fused testes |

## Decise manual, neadăugate

Titluri `nou` / `posibil` care nu au devenit afecțiuni noi: există sub alt nume, sunt variante ale unei categorii (D5), categorii generice sau nu sunt boli (G7). Coloana „Apropiat” e sugestia automată.

| Cod | Titlu CIM-10 | Apropiat |
|---|---|---|
| A01 | Febre tifoide si paratifoide | Febra paratifoida A / Febra tifoida |
| A25 | Febre datorite muscaturii de sobolan | Febra muscaturii de sobolan |
| A25.9 | Febra cauzata de muscatura de sobolan, nespecificata | Febra muscaturii de sobolan |
| A71.1 | Faza activa a trahomului | Trahom |
| A77 | Febra purpurie (Rickettsia de capuse) |  |
| A77.0 | Febra purpurie prin Rickettsia rickettsii |  |
| A77.1 | Febra purpurie prin Rickettsia conorii |  |
| A77.2 | Febra purpurie prin Rickettsia siberica |  |
| A77.3 | Febra purpurie prin Rickettsia australis |  |
| A77.9 | Febra purpurie, nespecificata | Febra pustoaselor stancoase |
| A88.0 | Febra exantematoasa cu enterovirus [exantemul de Boston] |  |
| A92.0 | Febra de Chikcungunya | Febra chikungunya / Febra hemoragica denga |
| A92.2 | Febra ecvina de Venezuela |  |
| A92.9 | Febra virala transmisa de tantari, nespecificata |  |
| A94 | Febra virala transmisa de artropode, nespecificata |  |
| A95.0 | Febra galbena silvestra | Febra galbena |
| A95.1 | Febra galbena citadina | Febra galbena |
| A96 | Febra hemoragica cu Arenavirus | Febra hemoragica brasiliana / Febra hemoragica argentina |
| A99 | Febra virala hemoragica, nespecificata | Leptospiroza |
| B30.2 | Faringo-conjunctivita virala | Conjunctivita virala / Faringoconjunctivita |
| B74.1 | Filarioza datorita Brugia malay | Filarioza cu Brugia malayi |
| B74.2 | Filarioza datorita Brugia timori | Filarioza cu Brugia malayi |
| D57.3 | Fizionomia bolii hematiilor falciforme [drepanocitare] | Anemie falciforma |
| E70.0 | Fenilcetonuria clasica | Fenilcetonurie atipica |
| E84.0 | Fibroza chistica cu manifestari pulmonare | Fibroza chistica / Pneumopatie fibrozanta |
| E84.8 | Fibroza chistica cu alte manifestari | Fibroza chistica |
| F54 | Factori psihologici si comportamentali asociati bolilor sau tulburarilor clasificate altundeva |  |
| F55 | Folosire daunatoare de substante nedeterminand dependenta |  |
| G08 | Flebita si tromboflebita intracraniana si intrarahidiana |  |
| I28.0 | Fistula arteriovenoasa a vaselor pulmonare | Fistula arteriovenoasa / Fistula arteriovenoasa pulmonara |
| I48 | Fibrilatia atriala si flutter | Fibrilatie atriala permanenta |
| I49.0 | Fibrilatia ventriculara si flutter | Flutter ventricular |
| I77.0 | Fistula arterio-venoasa, dobindita | Malformatie arteriovenoasa spinala / Fistula arteriovenoasa durala / Fistula arteriovenoasa pulmonara |
| I80 | Flebita si tromboflebita |  |
| I80.0 | Flebita si tromboflebita vaselor superficiale ale extremitatilor inferioare | Flebita / Tromboflebita |
| I80.1 | Flebita si tromboflebita venei femurale |  |
| I80.2 | Flebita si tromboflebita altor vase profunde ale extremitatilor inferioare |  |
| I80.3 | Flebita si tromboflebita extremitatilor inferioare, nespecificata |  |
| I80.8 | Flebita si tromboflebita cu alte localizari |  |
| I80.9 | Flebita si tromboflebita cu localizare nespecificata |  |
| J02.8 | Faringita acuta datorita altor organisme specificate |  |
| J63.1 | Fibroza (pulmonara) datorita bauxitei |  |
| J63.3 | Fibroza (pulmonara) datorita grafitului |  |
| J95.0 | Functionarea defectuoasa a unei traheostomii |  |
| K03.0 | Frecarea excesiva a dintilor |  |
| K04.3 | Formatiune anormala de tesut dentar dur in pulpa |  |
| K08.81 | Fractura patologica a dintelui |  |
| K60 | Fisura si fistula regiunilor anale si rectale | Fistula anala / Fisura anala |
| K60.4 | Fistula rectala | Fistula anala / Persistenta de urac / Fistula rectovaginala |
| K60.5 | Fistula anorectala | Fistula rectouretrala / Fistula rectovaginala / Fistula anala / Fisura anala |
| K63.2 | Fistula intestinului | Fistula gastrojejunala / Fistula rectouretrala / Fistula rectovaginala / Fistula intestinala |
| K70.2 | Fibroza si scleroza alcoolica a ficatului | Fibroza hepatica |
| K74 | Fibroza si ciroza ficatului | Ciroza hepatica / Fibroza hepatica |
| K74.2 | Fibroza hepatica cu scleroza hepatica | Fibroza hepatica |
| K75.1 | Flebita venei porte |  |
| L66.4 | Foliculita uleritematoasa reticulara |  |
| M48.4 | Fractura vertebrala de oboseala |  |
| M72.0 | Fibromatoza fasciala palmara [Dupuytren] | Boala Dupuytren |
| M84.0 | Fractura rau consolidata |  |
| M84.1 | Fractura neconsolidata [pseudoartroza] |  |
| M84.3 | Fractura prin solicitare excesiva, neclasificata altundeva |  |
| M84.4 | Fractura patologica, neclasificata altundeva |  |
| M90.7 | Fractura osoasa in bolile neoplazice (C00-D48†) | Fractura |
| M96.6 | Fractura osoasa dupa insertia unui implant ortopedic, a unei prosteze articulare sau a unei placi osoase | Fractura |
| N32.1 | Fistula vezico-intestinala | Fistula intestinala / Fistula aortointestinala / Fistula vezicovaginala |
| N32.2 | Fistula vezicala urinara, neclasificata altundeva | Fistula colovesicala |
| N60.3 | Fibroscleroza sanului |  |
| N64.0 | Fisura si fistula mamelonului | Sfarcuri dureroase |
| N82 | Fistule implicand tractul genital feminin |  |
| N82.5 | Fistule genito-cutanate la femeie |  |
| N82.9 | Fistula tractului genital feminin, nespecificata |  |
| N99.5 | Functionarea proasta a unei stomii externe a tractului urinar |  |
| O22.3 | Flebotromboza profunda in sarcina | Flebotromboza / Tromboza venoasa profunda / Tromboza venoasa a membrelor superioare |
| O87.1 | Flebotromboza profunda in timpul lauziei | Flebotromboza / Tromboza puerperala / Tromboza venoasa profunda / Tromboza venoasa a membrelor superioare |
| O92.1 | Fisura mamelonului asociata nasterii | Sfarcuri dureroase |
| P00.9 | Fat si nou-nascuti afectat de o tulburare materna nespecificata |  |
| P03 | Fat si nou-nascuti afectati de alte complicatii ale travaliului si nasterii |  |
| P13.0 | Fractura craniului datorita traumatismului la nastere | Traumatism obstetric |
| P13.4 | Fractura claviculei datorita traumatismului la nastere | Traumatism obstetric |
| P28.81 | Fornaitul la nou-nascut |  |
| Q35.1 | Fisura boltii palatului | Fisura palatina submucoasa |
| Q35.3 | Fisura partii moi a palatului |  |
| Q35.5 | Fisura boltii si partii moi a palatului |  |
| Q35.7 | Fisura luetei |  |
| Q36.0 | Fisura labiala bilaterala | Fisura labiala / Fisura labiala mediana |
| Q37 | Fisura palatului cu fisura labiala | Fisura labiala |
| Q37.0 | Fisura boltii palatului cu fisura labilala bilaterala |  |
| Q37.1 | Fisura boltii palatului cu fisura labilala unilaterala |  |
| Q37.2 | Fisura partii moi a palatului cu fisura labiala bilaterala | Fisura labiala |
| Q37.3 | Fisura partii moi a palatului cu fisura labiala unilaterala | Fisura labiala |
| Q37.4 | Fisura boltii si a partii moi a palatului cu fisura labiala bilaterala | Fisura labiala |
| Q37.5 | Fisura boltii si a partii moi a palatului cu fisura labiala unilaterala | Fisura labiala |
| Q37.8 | Fisura palatului nespecificata cu fisura labiala bilaterala | Fisura labiala |
| Q37.9 | Fisura palatului nespecificata cu fisura labiala unilaterala | Fisura labiala |
| Q39.2 | Fistula traheo-esofagiana congenitala fara atrezie | Atrezie esofagiana / Atrezie esofagiana cu fistula / Fistula traheoesofagiana |
| Q39.21 | Fistula traheo-esofagiana congenitala fara atrezie | Atrezie esofagiana / Atrezie esofagiana cu fistula / Fistula traheoesofagiana / Fistula traheoesofagiana postintubatie |
| Q39.22 | Fistula bronho-esofagiana congenitala fara atrezie | Atrezie esofagiana / Atrezie esofagiana cu fistula / Fistula bronhoesofagiana |
| Q43.6 | Fistula congenitala a rectului si anusului |  |
| Q51.7 | Fistula congenitala intre uter si tractul digestiv si urinar | Fistula intestinala |
| Q52.2 | Fistula recto-vaginala congenitala | Fistula rectovaginala / Fistula branhiala / Fistula rectovestibulara |
| Q52.5 | Fuziunea vulvei |  |
| Q64.75 | Fistula tractului gastro-intestinal-urinar congenitala | Fistula intestinala / Fistula anala |
| Q85 | Facomatoze, neclasificate altundeva |  |

## Existente (potrivire automată)

Candidații pentru sinonime adăugate ulterior (D6).

| Cod | Titlu CIM-10 | Afecțiune | Potrivire |
|---|---|---|---|
| A01.0 | Febra tifoida | Febra tifoida | exact |
| A54.5 | Faringita gonococica | Faringita gonococica | exact |
| A68 | Febre recurente | Febra | temporal (G1) |
| A68.0 | Febra recurenta prin paduche | Febra recurenta transmisa de paduchi | exact |
| A68.1 | Febra recurenta prin capuse | Febra recurenta transmisa de capuse | exact |
| A78 | Febra Q | Febra Q | exact |
| A79.0 | Febra de transee | Febra de transee | exact |
| A91 | Febra hemoragica datorita virusului de denga | Febra hemoragica denga | exact |
| A92.1 | Febra O'nyong-nyong | Febra O'nyong-nyong | exact |
| A92.3 | Febra cu virus West Nile | Encefalita West Nile | exact |
| A92.4 | Febra de Rift Valley | Febra de Valea Riftului | exact |
| A93.2 | Febra de capuse Colorado | Febra de Colorado | exact |
| A95 | Febra galbena | Febra galbena | exact |
| A96.0 | Febra hemoragica Junin | Febra hemoragica argentina | exact |
| A96.1 | Febra hemoragica de Machupo | Febra hemoragica boliviana | exact |
| A96.2 | Febra de Lassa | Febra Lassa | exact |
| A98.0 | Febra hemoragica de Crimeia [de Congo] | Febra hemoragica Crimeea-Congo | exact |
| A98.1 | Febra hemoragica de Omsk | Febra hemoragica Omsk | exact |
| A98.5 | Febra hemoragica cu sindrom renal | Infectie cu hantavirus | exact |
| B08.5 | Faringita veziculara prin enterovirus | Herpangina | exact |
| B66.3 | Fasciolaza | Fascioloza | exact |
| B66.5 | Fasciolopsiaza | Fasciolopsidoza | exact |
| B74 | Filarioza | Filarioza | exact |
| B74.0 | Filarioza cu Wuchereria bancrofti | Filarioza limfatica | exact |
| B85.3 | Ftiriaza | Phtiriaza | exact |
| D56.3 | Fizionomia thalasemica | Talasemie minor | exact |
| E84 | Fibroza chistica | Fibroza chistica | exact |
| E84.1 | Fibroza chistica cu manifestari intestinale | Ileus meconial | exact |
| F40.1 | Fobii sociale | Fobie sociala | terminatii |
| F40.2 | Fobii specifice (izolate) | Fobie specifica | terminatii |
| F44.1 | Fuga disociativa | Fuga disociativa | exact |
| F63.2 | Furt patologic [cleptomanie] | Cleptomanie | exact |
| H83.1 | Fistula labirintica | Fistula perilimfatica | exact |
| I42.4 | Fibroelastoza endocardica | Fibroelastoza endocardica | exact |
| J02 | Faringita acuta | Faringita | exact |
| J02.0 | Faringita streptococica | Angina streptococica | exact |
| J31.2 | Faringita cronica | Faringita | exact |
| J94.1 | Fibrotorax | Fibrotorax | exact |
| K12.2 | Flegmonul si abcesul gurii | Abces submandibular | exact |
| K31.6 | Fistula stomacului si duodenului | Fistula gastrocolica | exact |
| K60.0 | Fisura anala acuta | Fisura anala | temporal (G1) |
| K60.1 | Fisura anala cronica | Fisura anala | exact |
| K60.2 | Fisura anala, nespecificata | Fisura anala | exact |
| K60.3 | Fistula anala | Fistula anala | exact |
| K74.0 | Fibroza hepatica | Fibroza hepatica | exact |
| K82.3 | Fistula vezicii biliare | Fistula colecistoduodenala | exact |
| M35.4 | Fasciita difuza (eosinofilica) | Fascita eozinofilica | exact |
| M72.2 | Fibromatoza fasciala plantara | Pinten calcanean | exact |
| M72.6 | Fasciita necrozanta | Fascita necrozanta | exact |
| N82.0 | Fistula vezico-vaginala | Fistula vezicovaginala | exact |
| N82.3 | Fistula vaginului cu intestinul gros | Fistula rectovaginala | exact |
| Q35 | Fisura palatului | Fisura palatina | exact |
| Q36 | Fisura labiala | Fisura labiala | exact |
| Q36.1 | Fisura labiala mediana | Fisura labiala mediana | exact |
| Q36.9 | Fisura labiala unilaterala | Fisura labiala | exact |
| Q73.1 | Focomelia, membru nespecificat | Focomelie | exact |
| Q80.4 | Fat arlechin | Ihtioza harlequin | exact |
