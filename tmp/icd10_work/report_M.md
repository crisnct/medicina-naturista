# Litera M — raport CIM-10

- coduri CIM-10 cu titlul la litera M: **397**
- eliminate automat (P2): **53**
  - subzona de organ (D5): 32
  - dublura categoriei parinte (nespecificat): 14
  - asterisc (in alte boli): 6
  - procedura: 1
- găsite automat în dicționar (P4.1–P4.3): **90**
- de decis manual (`nou` + `posibil`): **254**
- **afecțiuni adăugate: 41**

## Decizii manuale

- **Din `pending_by_letter.jsonl` (pasul A):** `Mariska anala` (I84.6), `Mucinoza foliculara` (L65.2) și `Macroftalmie` re-verificate (nu există, G6 curat) și adăugate. La `Macroftalmie` codul corectat Q11 → Q11.3 (Q11 e categoria „anoftalmie, microftalmie, macroftalmie”); la `Mucinoza foliculara` titlul englezesc CIM-10 („alopecia mucinosa”) trecut primul.
- **Mucormicoza (cerut de la pasul Z):** dicționarul ține subtipurile de organ separate (`Mucormicoza pulmonara`, `Mucormikoza cutanata`, `Mucormikoza rino-orbito-cerebrala`, `Mediastinita cu Mucor`), deci după G4 am adăugat `Mucormicoza gastrointestinala` (B46.2) și `Mucormicoza diseminata` (B46.4), cu grafia CIM-10 (c). B46.5 nespecificată = `Mucormikoza`.
- **Variante de tip / agent / organ păstrate separat (G4):** meningitele după agent (`Meningita cu virus varicela-zoster` = B01.0 + B02.1, același virus, după modelul `Encefalita cu virus varicela-zoster`; `Meningita cu adenovirus`; `Meningita streptococica`), miiaza după localizare, fiecare cu codul ei (oculară, nazofaringiană, auriculară, a plăgilor; miaza intestinală/urogenitală din codul rezidual B87.8 rămâne în `Miiaza`), `Miopatie medicamentoasa` și `Miopatie toxica` (lângă `Miopatia steroidica`, `Miopatia alcoolica`), `Miliaria cristalina` (lângă `Miliaria rubra`), `Mastita neonatala`, `Miastenie neonatala tranzitorie` (≠ `Sindrom miastenic congenital`), `Mola hidatiforma completa` / `partiala` (lângă `Mola hidatiforma invaziva`), `Miopie degenerativa`, `Manie fara simptome psihotice` (pereche cu `Manie cu simptome psihotice`), `Migrena oftalmoplegica` și `Microtropie` (din termenii de includere G43.8, H50.4), `Malformatie arteriovenoasa periferica` / `precerebrala` (lângă cea cerebrală și spinală), `Melanom in situ` (D03, toate subzonele grupate; ≠ melanomul invaziv), `Mezoteliom malign` (C45 generic; subtipurile pleural/peritoneal/pericardic existau).
- **Excepția G2:** `Mielofibroza acuta` (C94.5, panmieloză acută cu mielofibroză) e o leucemie acută, nu forma acută a `Mielofibroza primara` (neoplasm mieloproliferativ cronic), deși potrivirea automată o leagă temporal (G1). Scriptul o eliminase greșit ca „subzonă”.
- **Existau sub alt nume:** meningita listeriană (`Meningita cu Listeria`), Mollaret și meningita cronică (`Meningita`), nonpiogenă (`Meningita aseptica`), coccidioidomicotică (`Coccidioidomikoza diseminata`), carbunoasă (`Antrax meningeal`), cu criptococ, cu Toxoplasma (`Toxoplasmoza cerebrala`); mononucleoza CMV (`Mononucleoza cu citomegalovirus`); maduromicoza (`Micetom`); mastocitomul (`Mastocitoza cutanata`); miozita osificantă traumatică; menopauza prematură (`Insuficienta ovariana prematura`); mediastinopericardita adezivă (`Pericardita constrictiva`); metatarsalgia Morton (`Sindrom Morton`); membranele pupilare (`Persistenta membranei pupilare`); mucocelul salivar (`Chist salivar`); mastopatia chistică difuză (`Mastopatie fibrochistica`); malnutriția fetală (`Restrictie de crestere intrauterina`); malformațiile apeductului Magendie (`Sindrom Dandy-Walker`), corpului calos, vitrosului, urechii interne/medii, colobomul papilei/coroidei, microgiria/pahigiria, malrotația intestinală, ectopia ureterului, uraca, mâna în cleşte de rac (`Ectrodactilie`), mâna în bâtă radială (`Aplazie radiala`), măduva fixată (`Sindrom de colada medulara`), megacolonul congenital (`Boala Hirschsprung`), mozaicismele Turner (`Sindrom Turner in mozaic`), mielomul solitar (`Medulom`, sinonim „plasmocitom solitar”).
- **Potriviri absurde ale scriptului, verificate:** `Mielodisplazia` (D46.9) → `Spina bifida` (sens spinal; sindromul mielodisplazic propriu-zis e D46, titlul la S), `Menstruatie excesiva ... ciclu regulat` (N92.0) → `Dismenoree` (de fapt `Menoragie`, există), `Mastocitoza` Q82.2 → `Mastocitoza sistemica` (e cea cutanată, există și ea), `Mielomul solitar` → `Medulom` (corect prin sinonim).
- **Grupate în categoria lor (D5 / G1):** melioidoza acută/cronică, melanomul malign pe subzone (C43.x), mezoteliomul pe subzone, malnutriția proteino-energetică după grad (E43, E44.x) și în sarcină (O25), migrena complicată, meningoencefalita bacteriană (G04.2), miocardita infecțioasă/izolată, mastita asociată nașterii (O91.x), menoragia pubertară, macrocefalia familială benignă (în `Macrocefalie`), miozita osificantă paralitică/după arsuri, monorhismul (lateralitate, în `Anorhidie`), meningita postmorbiloasă (complicație a rujeolei).
- **Nu sunt boli anume (G7 / P2):** toate „Meningita / Miocardita / Miopatia / Miozita / Mielopatia / Mastoidita în boli clasificate altundeva” (asterisc), megaesofagul și megacolonul din boala Chagas (†/asterisc), categoriile „Malformații congenitale ale X” și „Mononeuropatii ale membrului”, monosomiile autosomale fără cromozom precizat, monoplegia (deficit neurologic; nici `Hemiplegie` nu e în dicționar), mialgia, metatarsalgia, mastodinia, metamorfopsia, monoartrita NCA, mâna/piciorul în gheară dobândite, malpoziția uterului (retroversie), malformația placentei (generică), modificările de culoare ale dinților, modificările pielii prin radiații neionizante, monitorizarea scalpului nou-născutului, suflul cardiac funcțional, malnutriția maternă, menisc detașat/blocat, agenții cauzali (Mycoplasma, Proteus), localizările tumorale (mediastin, mandibulă, meninge).
- **Sinonime insuficiente (2.4):** `Miliaria profunda` (L74.2; „miliaria tropicala” e singura alternativă sigură), `Miozita interstitiala` (M60.1), `Mucinoza orala focala` (K13.7), `Metastrongiloza` (B83.8), malformațiile prin metilmercur / citotoxice / radiații (Q86.84–Q86.87).
- **Amânate la altă literă (`pending_from_M.jsonl`):** `Politelie` (Q83.3, P; pereche cu `Atelie`), `Stenoza de apeduct Sylvius` (Q03.0, S), `Sindrom fetal valproic` (Q86.81, S; după modelul `Sindrom fetal alcoolic`), `Embriopatie cu talidomida` (Q86.83, E), `Embriopatie retinoica` (Q86.82, E). Termenii cu M ai unor coduri cu titlul la altă literă rămân la litera titlului: meziodinții (K00.1, `Dinti supranumerari`, D), odontoclazia (K02.4, O), masochismul (F65.5, S), pili/perlat (Q84.1, P), proteinoza alveolară (J84.0, P).
- **Nume la M din coduri cu titlul la altă literă, adăugate aici:** `Malocluzie` (K07.2, K07.4; lipsea cu totul), `Morsicatio buccarum` (K13.1), `Miochimie faciala` (G51.4), `Menarha prematura` (E30.8), `Moniletrix` (Q84.1), `Microlitiaza alveolara pulmonara` (J84.0), `Malrotatie renala` (Q63.29; ≠ `Rinichi ectopic`), `Megauretra` (Q64.76), `Macrotie`, `Macrocheilie`, `Microcheilie`, `Macrocefalie` (≠ `Megalencefalie`), `Menisc discoid`.

## Adăugate

| Nume canonic | Coduri | Sinonime |
|---|---|---|
| Macrocefalie | Q75.3, Q75.31, Q75.39 | macrocranie; macrocefalie familiala benigna; perimetru cranian crescut; macrocephaly; macrocrania; benign familial macrocephaly |
| Macrocheilie | Q18.6 | hipertrofia congenitala a buzei; buze mari congenitale; macrocheilie congenitala; macrocheilia; macrochilia; macrocheily |
| Macroftalmie | Q11.3 | macroftalmia; megaloftalmie; glob ocular marit congenital; macrophthalmos; megalophthalmos; congenital macrophthalmia |
| Macrotie | Q17.1 | megalotie; urechi mari congenitale; pavilion auricular marit congenital; macrotia; megalotia; congenital large ears |
| Malformatie arteriovenoasa periferica | Q27.3 | malformatia arterio-venoasa periferica; MAV periferica; anevrism arteriovenos periferic; peripheral arteriovenous malformation; peripheral AVM; arteriovenous malformation of the limbs |
| Malformatie arteriovenoasa precerebrala | Q28.0 | malformatia arterio-venoasa a vaselor precerebrale; anevrism arteriovenos precerebral congenital; MAV precerebrala; arteriovenous malformation of precerebral vessels; precerebral arteriovenous malformation; congenital precerebral arteriovenous aneurysm |
| Malocluzie | K07.2, K07.4 | malocluzie dentara; ocluzie dentara anormala; anomalie de ocluzie; malocclusion; dental malocclusion; bad bite |
| Malrotatie renala | Q63.29 | malrotatia rinichiului; rotatie anormala a rinichiului; rinichi malrotat; renal malrotation; malrotation of kidney; malrotated kidney |
| Manie fara simptome psihotice | F30.1 | episod maniacal fara simptome psihotice; manie fara elemente psihotice; manie nepsihotica; manic episode without psychotic symptoms; mania without psychotic symptoms; nonpsychotic mania |
| Mariska anala | I84.6 | apendice hemoroidal rezidual; mariska; pliu cutanat anal; anal skin tag; residual hemorrhoidal skin tag; perianal skin tag |
| Mastita neonatala | P39.0 | mastita infectioasa neonatala; mastita nou-nascutului; abces mamar neonatal; neonatal infective mastitis; neonatal mastitis; mastitis neonatorum |
| Megauretra | Q64.76 | megauretra congenitala; megalouretra; dilatatie congenitala a uretrei; megalourethra; congenital megalourethra; megaurethra |
| Melanom in situ | D03, D03.0, D03.1, D03.2, D03.3, D03.4, D03.5, D03.6, D03.7, D03.8, D03.9 | melanom malign in situ; melanom intraepidermic; melanom stadiul 0; melanoma in situ; in situ melanoma; stage 0 melanoma |
| Menarha prematura | E30.8 | menarha precoce; menarha prematura izolata; sangerare vaginala prepubertara izolata; premature menarche; isolated premature menarche; precocious menarche |
| Meningita cu adenovirus | A87.1 | meningita adenovirala; meningita prin adenovirus; meningita virala cu adenovirus; adenoviral meningitis; adenovirus meningitis; meningitis due to adenovirus |
| Meningita cu virus varicela-zoster | B01.0, B02.1 | meningita variceloasa; meningita zosteriana; meningita cu VZV; varicella meningitis; zoster meningitis; varicella-zoster virus meningitis; VZV meningitis |
| Meningita streptococica | G00.2 | meningita cu streptococi; meningita prin streptococ; meningita cu Streptococcus; streptococcal meningitis; Streptococcus meningitis; meningitis due to streptococci |
| Menisc discoid | M23.1 | menisc discoid congenital; menisc in forma de disc; menisc discoidal; discoid meniscus; discoid lateral meniscus; congenital discoid meniscus |
| Mezoteliom malign | C45, C45.7, C45.9 | mesoteliom; mezoteliom; mezoteliom difuz malign; mesothelioma; malignant mesothelioma; diffuse malignant mesothelioma |
| Miastenie neonatala tranzitorie | P94.0 | miastenia gravis tranzitorie neonatala; miastenie gravis neonatala; miastenie neonatala; transient neonatal myasthenia gravis; neonatal myasthenia gravis; transient neonatal myasthenia |
| Microcheilie | Q18.7 | buze mici congenitale; hipoplazie labiala congenitala; microcheilie congenitala; microcheilia; microchilia; microcheily |
| Microlitiaza alveolara pulmonara | J84.0 | microlitiaza alveolara a plamanului; microlitiaza alveolara; microlitiaza pulmonara; pulmonary alveolar microlithiasis; alveolar microlithiasis; microlithiasis alveolaris pulmonum |
| Microtropie | H50.4 | microstrabism; sindrom de monofixare; strabism cu unghi mic; microtropia; microstrabismus; monofixation syndrome |
| Mielofibroza acuta | C94.5 | panmieloza acuta cu mielofibroza; mieloscleroza acuta; mieloscleroza maligna; acute myelofibrosis; acute panmyelosis with myelofibrosis; malignant myelosclerosis |
| Migrena oftalmoplegica | G43.8 | migrena cu oftalmoplegie; neuropatie oftalmoplegica dureroasa recurenta; oftalmoplegie migrenoasa; ophthalmoplegic migraine; recurrent painful ophthalmoplegic neuropathy; migraine with ophthalmoplegia |
| Miiaza auriculara | B87.4 | miaza urechii; otomiaza; miaza otica; aural myiasis; otomyiasis; ear myiasis |
| Miiaza nazofaringiana | B87.3 | miaza nazo-faringiana; miaza nazala; miaza laringiana; nasopharyngeal myiasis; nasal myiasis; rhinomyiasis |
| Miiaza oculara | B87.2, H06.1 | miaza oculara; oftalmomiaza; miaza orbitei; ocular myiasis; ophthalmomyiasis; oculomyiasis |
| Miiaza plagilor | B87.1 | miaza plagilor cutanate; miaza traumatica; infestarea plagilor cu larve de muste; wound myiasis; traumatic myiasis; wound maggot infestation |
| Miliaria cristalina | L74.1 | sudamine; miliarie cristalina; vezicule sudorale cristaline; miliaria crystallina; sudamina; crystalline miliaria |
| Miochimie faciala | G51.4 | miochimia faciala; miokimie faciala; clonii musculare segmentare faciale; facial myokymia; myokymia of the face; continuous facial myokymia |
| Miopatie medicamentoasa | G72.0 | miopatia provocata medicamentos; miopatie indusa de medicamente; miopatie iatrogena medicamentoasa; drug-induced myopathy; medication-induced myopathy; drug-related myopathy |
| Miopatie toxica | G72.2 | miopatia datorita altor agenti toxici; miopatie prin agenti toxici; miopatie indusa de toxine; myopathy due to other toxic agents; toxic myopathy; toxin-induced myopathy |
| Miopie degenerativa | H44.2 | miopie patologica; miopie maligna; miopie forte degenerativa; degenerative myopia; pathologic myopia; malignant myopia |
| Mola hidatiforma completa | O01.0 | mola hidatiforma clasica; mola completa; sarcina molara completa; classical hydatidiform mole; complete hydatidiform mole; complete molar pregnancy |
| Mola hidatiforma partiala | O01.1 | mola hidatiforma incompleta; mola partiala; sarcina molara partiala; incomplete and partial hydatidiform mole; partial hydatidiform mole; partial molar pregnancy |
| Moniletrix | Q84.1 | par moniliform; par in matanii; aplazie moniliforma a parului; monilethrix; beaded hair; moniliform hair |
| Morsicatio buccarum | K13.1 | muscarea partii mucoase a obrazului si buzei; muscarea cronica a obrazului; muscarea obrajilor si buzelor; cheek and lip biting; chronic cheek biting; cheek chewing |
| Mucinoza foliculara | L65.2 | alopecie mucinoasa; alopecia mucinoasa Pinkus; mucinoza foliculara Pinkus; alopecia mucinosa; follicular mucinosis; Pinkus follicular mucinosis |
| Mucormicoza diseminata | B46.4 | mucormicoza generalizata; zigomicoza diseminata; mucormicoza sistemica; disseminated mucormycosis; disseminated zygomycosis; generalized mucormycosis |
| Mucormicoza gastrointestinala | B46.2 | mucormicoza gastro-intestinala; zigomicoza gastrointestinala; mucormicoza digestiva; gastrointestinal mucormycosis; gastrointestinal zygomycosis; intestinal mucormycosis |

## Decise manual, neadăugate

Titluri `nou` / `posibil` care nu au devenit afecțiuni noi: există sub alt nume, sunt variante ale unei categorii (D5), categorii generice sau nu sunt boli (G7). Coloana „Apropiat” e sugestia automată.

| Cod | Titlu CIM-10 | Apropiat |
|---|---|---|
| A24 | Morva si melioidoza |  |
| A24.1 | Melioidoza acuta sau galopanta |  |
| A24.2 | Melioidoza subacuta si cronica |  |
| A32.1 | Meningita si meningoencefalita listeriana | Meningita cu Listeria |
| B00.3 | Meningita cu virusul herpetic | Meningita herpetica / Meningita urliana / Meningita enterovirala |
| B27.1 | Mononucleoza cu cytomegalovirus | Mononucleoza cu citomegalovirus |
| B36.9 | Micoze superficiale nespecificate |  |
| B38.4 | Meningita prin coccidioidomicoza | Coccidioidomikoza diseminata |
| B46.5 | Mucormicoza, nespecificata | Mucormikoza |
| B48.7 | Micoze oportuniste |  |
| B58.2 | Meningoencefalita cu Toxoplasma (G05.2*) | Meningoencefalita / Meningita cu Listeria |
| B87.8 | Miaza, alte localizari |  |
| B96.0 | Mycoplasma pneumoniae [M. pneumoniae], cauza unor boli clasate la alte capitole | Pneumonie cu citomegalovirus / Pneumonie |
| C43 | Melanomul malign al pielii | Melanom |
| C43.0 | Melanomul malign al buzei | Melanom |
| C43.1 | Melanomul malign al pleoapei, inclusiv cantusul | Melanom |
| C43.2 | Melanomul malign al urechii si canalului auditiv extern | Melanom |
| C43.3 | Melanomul malign al fetei, alte localizari si nespecificate | Melanom |
| C43.4 | Melanomul malign al scalpului si gatului | Melanom |
| C43.5 | Melanomul malign al trunchiului | Melanom |
| C43.6 | Melanomul malign al membrelor superioare, inclusiv umarul | Melanom |
| C43.7 | Melanom malign al membrelor inferioare, inclusiv soldul | Melanom |
| C43.8 | Melanomul malign depasind pielea | Melanom |
| C90 | Mielom multiplu si tumori maligne cu plasmocite | Cancer / Mielom multiplu |
| E43 | Malnutritia proteino-energetica grava, nespecificata | Malnutritie proteino-energetica / Kwashiorkor marasmic |
| E44 | Malnutritia proteino-energetica usoara sau moderata | Malnutritie proteino-energetica |
| E44.0 | Malnutritia proteino-energetica moderata | Malnutritie proteino-energetica / Kwashiorkor marasmic |
| E44.1 | Malnutritia proteino-energetica usoara | Malnutritie proteino-energetica / Kwashiorkor marasmic |
| G01 | Meningita in boli bacteriene clasificate altundeva |  |
| G02 | Meningita in alte boli infectioase si parazitare clasificate altundeva |  |
| G02.0 | Meningita in boli virale clasate la alte locuri | Meningita |
| G02.1 | Meningita in micoze | Meningita criptocococica |
| G02.8 | Meningita in alte boli infectioase si parazitare specificate clasificate altundeva |  |
| G03 | Meningita datorita altor cauze si nespecificate |  |
| G03.0 | Meningita cu nonpiogenica | Meningita / Meningita neonatala |
| G03.2 | Meningita benigna recurenta [Mollaret] | Meningita |
| G03.8 | Meningita datorita altor cauze specificate |  |
| G04.2 | Meningoencefalita si meningomielita bacteriana, neclasificate altundeva |  |
| G37.3 | Mielita transversa acuta in bolile demielinizante ale sistemului nervos central | Mielita transversa / Mielita longitudinala extinsa |
| G37.4 | Mielita necrozanta subacuta | Sindrom Leigh |
| G43.3 | Migrena complicata |  |
| G56 | Mononeuropatii ale membrului superior |  |
| G56.9 | Mononeuropatia membrului superior, nespecificata |  |
| G57 | Mononeuropatii ale membrului inferior |  |
| G57.9 | Mononeuropatia membrului inferior, nespecificata |  |
| G70 | Miastenia gravis si alte afectiuni neuromusculare | Miastenie |
| G70.2 | Miastenia congenitala si evolutiva | Sindrom miastenic congenital |
| G72.4 | Miopatia inflamatorie, neclasificata altundeva | Dermatomiozita / Colita / Aortita / Nefrita |
| G73.4 | Miopatia in bolile infectioase si parazitare clasificate altundeva |  |
| G73.5 | Miopatia in bolile endrocrine |  |
| G73.6 | Miopatia in bolile metabolice | Miopatia metabolica |
| G83.1 | Monoplegia membrelor inferioare | Sirenomelie |
| G83.2 | Monoplegia membrelor superioare |  |
| G83.3 | Monoplegia, nespecificata |  |
| H21.4 | Membrane pupilare | Persistenta membranei pupilare |
| H70 | Mastoidita si afectiuni asociate |  |
| I40.0 | Miocardita infectioasa | Miocardita / Endocardita infectioasa / Miozita infectioasa / Miocardita reumatica |
| I40.1 | Miocardita izolata | Miocardita |
| I41.0 | Miocardita in bolile bacteriene clasificate altundeva |  |
| I41.1 | Miocardita in bolile virale, clasificate altundeva | Miocardita |
| I41.2 | Miocardita in alte boli infectioase si parazitare clasificate altundeva | Miocardita |
| I46.1 | Moarte cardiaca subita, astfel descrisa | Moarte subita cardiaca |
| K03.7 | Modificari ale culorii tesutului dentar dur dupa eruptie |  |
| K11.6 | Mucocelul glandelor salivare | Chist salivar / Abces de glanda salivara |
| K23.1 | Megaesofag in cursul bolii Chagas (B57.3†) |  |
| K90.4 | Malabsorbtia datorita unei intolerante, neclasificata altundeva |  |
| K93.1 | Megacolon in boala Chagas (B57.3†) |  |
| L56.9 | Modificari acute ale pielii datorite radiatiilor ultraviolete, nespecificate |  |
| L57 | Modificari ale pielii datorite expunerii cronice la radiatii neionizante |  |
| L57.9 | Modificari ale pielii datorite expunerii cronice la raze neionizate, nespecificate |  |
| L74.2 | Miliaria profunda |  |
| L74.3 | Miliaria, nespecificata | Malarie |
| M13.1 | Monoartrita, neclasificata altundeva |  |
| M21.5 | Mana si picior sub forma de maciuca sau in gheara (dobandit) |  |
| M60.1 | Miozita interstitiala | Cistita interstitiala / Micoza intestinala / Nefrita interstitiala |
| M61.0 | Miozita osificanta traumatica | Miozita osificanta |
| M63.0 | Miozita in boli bacteriene clasificate altundeva |  |
| M63.1 | Miozita in infectii parazitare si cu protozoare clasificate altundeva |  |
| M63.2 | Miozita in alte boli infectioase clasificate altundeva | Miozita infectioasa / Miozita virala |
| M63.3 | Miozita in sarcoidoza (D86.8†) |  |
| M77.4 | Metatarsalgia |  |
| M79.1 | Mialgia | Milium |
| N60.1 | Mastopatia chistica difuza |  |
| N64.4 | Mastodinie |  |
| N85.4 | Malpozitia uterului |  |
| N92 | Menoragie, polimenoree si metroragie |  |
| N92.2 | Menstruatie excesiva la pubertate | Menoragie |
| O25 | Malnutritia in sarcina |  |
| O43.1 | Malformatia placentei |  |
| O91.2 | Mastita nepurulenta asociata nasterii |  |
| P05.2 | Malnutritia fatului, fara mentionarea de usor sau mic pentru varsta gestationala |  |
| P12.4 | Monitorizarea traumatismului scalpului la nou-nascut |  |
| P29.82 | Murmur cardiac beningn si fara semnificatie patologica la nou-nascut |  |
| Q03.0 | Malformatii ale apeductului Sylvius |  |
| Q04.0 | Malformatii congenitale ale corpului calos |  |
| Q04.00 | Malformatii congenitale ale corpului calos, nespecificate |  |
| Q04.35 | Microgiria si pahigiria |  |
| Q04.9 | Malformatia congenitala a encefalului, nespecificata |  |
| Q06.9 | Malformatia congenitala a maduvei spinarii, nespecificata | Amielie |
| Q07.9 | Malformatia congenitala a sistemului nervos, nespecificata |  |
| Q10 | Malformatii congenitale ale pleoapei, aparatului lacrimal si orbitei |  |
| Q10.7 | Malformatia congenitala a orbitei |  |
| Q12 | Malformatii congenitale ale cristalinului |  |
| Q12.9 | Malformatia congenitala a cristalinului, nespecificata | Afakie congenitala |
| Q13 | Malformatii congenitale ale camerei anterioare a ochiului |  |
| Q13.9 | Malformatia congenitala a camerei anterioare a ochiului, nespecificata |  |
| Q14 | Malformatii congenitale ale camerei posterioare a ochiului |  |
| Q14.0 | Malformatii congenitale ale corpului vitros | Malformatie de vitros |
| Q14.1 | Malformatii congenitale ale retinei | Malformatie intestinala congenitala / Anevrism cerebral congenital |
| Q14.2 | Malformatii congenitale ale papilei optice |  |
| Q14.3 | Malformatii congenitale ale coroidei |  |
| Q14.9 | Malformatia congenitala a camerei posterioare a ochiului, nespecificata |  |
| Q15.9 | Malformatia congenitala a ochiului, nespecificata | Anoftalmie |
| Q16 | Malformatii congenitale ale urechii cauzand alterarea auzului |  |
| Q16.3 | Malformatia congenitala a oscioarelor urechii |  |
| Q16.5 | Malformatia congenitala a urechii interne | Microtie |
| Q17.9 | Malformatia congenitala a urechii, nespecificata | Microtie / Anotie / Malformatie de ureche medie |
| Q18.9 | Malformatia congenitala a fetei si gatului, nespecificata |  |
| Q20 | Malformatii congenitale ale cavitatilor si orificiilor cardiace | Comunicare interventriculara |
| Q20.9 | Malformatia congenitala a cavitatilor si orificiilor cardiace, nespecificata | Comunicare interventriculara |
| Q21 | Malformatii congenitale ale septului cardiac | Comunicare interventriculara |
| Q21.9 | Malformatia congenitala a unui sept cardiac, nespecificata | Comunicare interventriculara |
| Q22 | Malformatii congenitale ale valvelor tricuspida si pulmonara | Boala valvulara pulmonara |
| Q22.9 | Malformatia congenitala a valvei tricuspide, nespecificata |  |
| Q23 | Malformatii congenitale ale valvei aortice si valvei mitrale |  |
| Q23.9 | Malformatii congenitale ale valvelor aortice si mitrale, nespecificate |  |
| Q24.5 | Malformatia vaselor coronariene | Anevrism de artera coronara |
| Q24.9 | Malformatia congenitala cardiaca, nespecificata | Comunicare interventriculara |
| Q25 | Malformatii congenitale ale arterelor mari |  |
| Q25.9 | Malformatia congenitala a arterelor mari, nespecificata |  |
| Q26 | Malformatii congenitale ale venelor mari |  |
| Q26.9 | Malformatia congenitala a unei vene mari, nespecificata |  |
| Q27.9 | Malformatia congenitala a sistemului vascular periferic, nespecificata | Malformatie vasculara |
| Q28.2 | Malformatia arterio-venoasa a vaselor cerebrale | Malformatie venoasa cerebrala / Malformatie arteriovenoasa cerebrala / Fistula arteriovenoasa cerebrala |
| Q28.9 | Malformatia congenitala a sistemului circulator, nespecificata |  |
| Q30 | Malformatii congenitale ale nasului |  |
| Q30.9 | Malformatia congenitala a nasului, nespecificata | Arhinie |
| Q31 | Malformatii congenitale ale laringelui |  |
| Q31.9 | Malformatia congenitala a laringelui, nespecificata |  |
| Q32 | Malformatii congenitale ale traheei si bronhiilor |  |
| Q33 | Malformatii congenitale ale plamanului |  |
| Q33.9 | Malformatia congenitala a pulmonului, nespecificata |  |
| Q34.9 | Malformatia congenitala a sistemului respirator, nespecificata | Fisura labiala / Fisura palatina |
| Q38.0 | Malformatii congenitale ale buzelor, neclasificate altundeva |  |
| Q38.4 | Malformatii congenitale ale glandelor si canalelor salivare |  |
| Q38.5 | Malformatii congenitale ale palatului, neclasificate altundeva | Agenezie ureterala / Agenezie uterina |
| Q39 | Malformatiile congenitale ale esofagului |  |
| Q39.9 | Malformatia congenitala a esofagului, nespecificata | Duplicatie esofagiana |
| Q40.3 | Malformatia congenitala a stomacului, nespecificata |  |
| Q40.9 | Malformatia congenitala a tractului digestiv superior, nespecificata |  |
| Q43.3 | Malformatii congenitale de fixare a intestinului |  |
| Q43.9 | Malformatia congenitala a intestinului, nespecificata | Malformatie intestinala congenitala |
| Q44 | Malformatii congenitale ale vezicii biliare, cailor biliare si ficatului |  |
| Q45.83 | Malformatii congenitale ale organelor digestive, neclasificate altundeva |  |
| Q45.9 | Malformatia sistemului digestiv, nespecificata |  |
| Q50 | Malformatii congenitale ale ovarelor, trompelor Fallope si ale ligamentelor largi |  |
| Q51 | Malformatii congenitale ale uterului si cervixului |  |
| Q52.6 | Malformatia congenitala a clitorisului |  |
| Q52.9 | Malformatii congenitale ale organelor genitale feminine, nespecificate |  |
| Q55.9 | Malformatii congenitale ale organului genital masculin, nespecificate |  |
| Q62.6 | Malpozitia ureterului |  |
| Q62.60 | Malpozitia ureterului, locul drenajului ureterului nespecificat |  |
| Q62.61 | Malpozitia ureterului, drenajul ureterului via capatul vezicii |  |
| Q62.62 | Malpozitia ureterului, drenajul ureterului via uretra |  |
| Q62.63 | Malpozitia ureterului, drenajul ureterului via vagin |  |
| Q62.64 | Malpozitia ureterului, drenajul ureterului via vulva |  |
| Q62.65 | Malpozitia ureterului, drenajul ureterului via vase deferente |  |
| Q62.66 | Malpozitia ureterului, drenajul ureterului via vezicule seminale |  |
| Q62.69 | Malpozitia ureterului, drenajul ureterului via alte localizari |  |
| Q63.9 | Malformatia congenitala a rinichiului, nespecificata | Agenezie renala |
| Q64.4 | Malformatia uracei |  |
| Q64.9 | Malformatia congenitala a sistemului urinar, nespecificata |  |
| Q71.6 | Mana in forma de cleste de rac |  |
| Q74.9 | Malformatia congenitala nespecificata a membrului(lor) | Amputatie congenitala |
| Q75.9 | Malformatia congenitala a craniului si oaselor fetei, nespecificata |  |
| Q76 | Malformatii cogenitale ale coloanei vertebrale si oaselor toracelui |  |
| Q76.43 | Malformatii congenitale ale altei(or) vertebre |  |
| Q76.7 | Malformatii congenitale ale sternului |  |
| Q76.9 | Malformatii congenitale ale oaselor toracelui, nespecificate |  |
| Q79 | Malformatii congenitale ale sistemului musculo-scheletal, neclasificate altundeva |  |
| Q79.9 | Malformatia congenitala a sistemului musculo-scheletal, nespecificata | Comunicare interventriculara / Malformatie anorectala / Malformatie intestinala congenitala / Microtie |
| Q82.9 | Malformatii congenitale ale pielii, nespecificate |  |
| Q83 | Malformatii congenitale ale sanului |  |
| Q83.3 | Mamelon accesoriu |  |
| Q83.9 | Malformatia congenitala a sanului, nespecificata | Amastie |
| Q84.9 | Malformatii congenitale ale tegumentului, nespecificate |  |
| Q86.81 | Malformatii congenitale datorite esterilor sau sarurilor acidului valproic |  |
| Q86.82 | Malformatii congenitale datorite vitaminei A |  |
| Q86.83 | Malformatii congenitale datorite talidomidei |  |
| Q86.84 | Malformatii congenitale datorite agentilor citotoxici |  |
| Q86.85 | Malformatii congenitale datorite altor medicamente |  |
| Q86.86 | Malformatii congenitale datorite radiatiilor ionizante | Expunere la radiatii |
| Q86.87 | Malformatii congenitale datorite metililor mercurului |  |
| Q86.89 | Malformatii congenitale datorite cauzelor exogene specificate |  |
| Q89.0 | Malformatii congenitale ale splinei |  |
| Q89.1 | Malformatii congenitale ale glandei suprarenale |  |
| Q89.2 | Malformatii congenitale ale altor glande endocrine |  |
| Q89.21 | Malformatii congenitale ale glandei pituitare |  |
| Q89.22 | Malformatii congenitale ale glandei tiroide |  |
| Q89.25 | Malformatii congenitale ale glandei paratiroide |  |
| Q89.26 | Malformatii congenitale ale timusului |  |
| Q89.29 | Malformatii congenitale ale altor glande endocrine specificate |  |
| Q89.7 | Malformatii congenitale multiple, neclasificate altundeva | Malformatie intestinala congenitala |
| Q89.79 | Malformatii congenitale multiple, neclasificate altundeva | Malformatie intestinala congenitala |
| Q89.9 | Malformatia congenitala, nespecificata | Comunicare interventriculara / Malformatie anorectala / Malformatie intestinala congenitala / Microtie / Miopatia congenitala / Malarie congenitala |
| Q93 | Monosomia si absenta autosomilor, neclasificate altundeva |  |
| Q93.0 | Monosomia totala a cromozomilor, fara disjunctia meiotica |  |
| Q93.1 | Monosomia totala a cromozomilor, mozaicism (fara disjunctie mitotica) |  |
| Q96.3 | Mozaicism, 45; X/46; XX sau XY |  |
| Q96.4 | Mozaicism, 45 X/alta linie celulara, cu cromozom sexual anormal |  |
| Q97.2 | Mozaicism, linii cu numere variabile de cromozomi X |  |

## Existente (potrivire automată)

Candidații pentru sinonime adăugate ulterior (D6).

| Cod | Titlu CIM-10 | Afecțiune | Potrivire |
|---|---|---|---|
| A17.0 | Meningita tuberculoasa | Tuberculoza meningeana | exact |
| A24.0 | Morva | Morva | exact |
| A24.4 | Melioidoza, nespecificata | Melioidoza | exact |
| A39.0 | Meningita meningococica | Meningita meningococica | exact |
| A39.2 | Meningococemia acuta | Meningococemie | temporal (G1) |
| A39.3 | Meningococemia cronica | Meningococemie | temporal (G1) |
| A39.4 | Meningococemia, nespecificata | Meningococemie | terminatii |
| A87 | Meningita virala | Meningita | exact |
| A87.0 | Meningita cu enterovirus | Meningita enterovirala | exact |
| B08.1 | Molluscum contagiosum | Negi perlati | exact |
| B26.1 | Meningita urliana | Meningita urliana | exact |
| B27 | Mononucleoza infectioasa | Mononucleoza infectioasa | exact |
| B33.0 | Mialgia epidemica | Pleurodinia | exact |
| B37.5 | Meningita prin Candida | Candidoza meningeana | exact |
| B46.0 | Mucormicoza pulmonara | Mucormicoza pulmonara | exact |
| B46.1 | Mucormicoza rino-cerebrala | Mucormikoza rino-orbito-cerebrala | exact |
| B46.3 | Mucormicoza cutanata | Mucormikoza cutanata | exact |
| B47 | Micetomul | Micetom | terminatii |
| B49 | Micoze nespecificate | Micoze | exact |
| B74.4 | Mansonellioza | Mansoneloza | exact |
| B87 | Miaza | Miiaza | exact |
| B87.0 | Miaza cutanata | Miiaza | exact |
| C90.0 | Mielom multiplu | Mielom multiplu | exact |
| D74 | Methemoglobinemia | Methemoglobinemie | exact |
| D74.0 | Methemoglobinemia congenitala | Methemoglobinemie | terminatii |
| E41 | Marasm nutritional | Marasm | exact |
| E46 | Malnutritia proteino-energetica nespecificata | Malnutritie proteino-energetica | terminatii |
| E76.0 | Mucopolizaharidoze, tip I | Sindrom Hurler | terminatii |
| E76.1 | Mucopolizaharidoza, tip II | Sindrom Hunter | exact |
| E76.3 | Mucopolizaharidoza, nespecificata | Mucopolizaharidoza | exact |
| F30.2 | Manie cu simptome psihotice | Manie cu simptome psihotice | exact |
| F94.0 | Mutism electiv | Mutism selectiv | exact |
| G00 | Meningita bacteriana, neclasificata altundeva | Meningita | exact |
| G00.0 | Meningita cu Haemophilus | Meningita cu Haemophilus influenzae | exact |
| G00.1 | Meningita cu pneumococi | Meningita pneumococica | terminatii |
| G00.3 | Meningita cu stafilococi | Meningita stafilococica | exact |
| G03.1 | Meningita cronica | Meningita | temporal (G1) |
| G03.9 | Meningita, nespecificata | Meningita | exact |
| G25.3 | Mioclonia | Mioclonii | terminatii |
| G37.2 | Mielinoliza centrala pontina | Mielinoliza pontina centrala | exact |
| G43 | Migrena | Migrena | exact |
| G43.0 | Migrena fara aura [migrena comuna] | Migrena fara aura | exact |
| G43.1 | Migrena cu aura [migrena clasica] | Migrena cu aura | exact |
| G57.1 | Meralgia parestezica | Meralgie parestezica | terminatii |
| G58.7 | Mononevrita cu localizari multiple | Mononeuritis multiplex | exact |
| G58.9 | Mononeuropatia, nespecificata | Mononeuropatie | terminatii |
| G70.0 | Miastenia gravis | Miastenie | exact |
| G71.2 | Miopatii congenitale | Miopatia congenitala | terminatii |
| G71.3 | Miopatia mitocondriala, neclasificata altundeva | Miopatia mitocondriala | exact |
| G72.1 | Miopatia alcoolica | Miopatia alcoolica | exact |
| G72.9 | Miopatia, nespecificata | Miopatie | terminatii |
| G95.1 | Mielopatii vasculare | Hematomielie | terminatii |
| H52.1 | Miopia | Miopie | terminatii |
| H70.0 | Mastoidita acuta | Mastoidita | exact |
| H70.1 | Mastoidita cronica | Mastoidita | temporal (G1) |
| H70.9 | Mastoidita, nespecificata | Mastoidita | exact |
| H73.0 | Miringita acuta | Miringita | exact |
| H73.1 | Miringita cronica | Miringita | temporal (G1) |
| I01.2 | Miocardita reumatismala acuta | Miocardita reumatica | temporal (G1) |
| I09.0 | Miocardita reumatismala | Miocardita reumatica | exact |
| I40 | Miocardita acuta | Miocardita | exact |
| I51.4 | Miocardita, nespecificata | Miocardita | exact |
| K59.3 | Megacolon, neclasificat altundeva | Megacolon | exact |
| K90 | Malabsorbtia intestinala | Sindrom de malabsorbtie | terminatii |
| K92.1 | Melena | Melena | exact |
| L74.0 | Miliaria rosie | Miliaria rubra | exact |
| L75.2 | Miliaria apocrina | Boala Fox-Fordyce | exact |
| L98.5 | Mucinoza cutanata | Mucinoza cutanata | exact |
| M31.1 | Microangiopatia trombotica | Microangiopatie trombotica | terminatii |
| M60 | Miozita | Miozita | exact |
| M60.0 | Miozita infectioasa | Miozita infectioasa | exact |
| M61.1 | Miozita osificanta progresiva | Fibrodisplazie osificanta progresiva | exact |
| N92.0 | Menstruatie excesiva si frecventa cu ciclu menstrual regulat | Dismenoree | exact |
| N92.1 | Menstruatie excesiva si frecventa cu ciclu menstrual neregulat | Metroragie | exact |
| N92.6 | Menstruatie neregulata, nespecificata | Menstruatii neregulate | terminatii |
| O01 | Mola hidatiforma | Mola hidatiforma | exact |
| O90.3 | Miocardiopatia in timpul lauziei | Cardiomiopatie peripartum | exact |
| P54.1 | Melena neonatala | Boala hemoragica a nou-nascutului | exact |
| P95 | Moarte fetala de cauza nespecificata | Moarte fetala in utero | exact |
| Q02 | Microcefalia | Microcefalie | terminatii |
| Q04.5 | Megalencefalia | Megalencefalie | exact |
| Q11.2 | Microftalmia | Microftalmie | exact |
| Q16.9 | Malformatia congenitala a urechii cauzand alterarea auzului, nespecificata | Anotie | exact |
| Q17.2 | Microtia | Microtie | exact |
| Q18.4 | Macrostomia | Macrostomie | exact |
| Q18.5 | Microstomia | Microstomie | exact |
| Q38.2 | Macroglosia | Macroglosie | terminatii |
| Q62.2 | Megaloureter congenital | Megaureter | exact |
| Q74.02 | Macrodactilia (degetele de la mana) | Macrodactilie | terminatii |
| Q82.2 | Mastocitoza | Mastocitoza sistemica | exact |
