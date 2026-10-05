# Litera A — raport CIM-10

- coduri CIM-10 cu titlul la litera A: **2207**
- eliminate automat (P2): **1615**
  - rezidual: 1364
  - categorie generica (nu o boala anume): 145
  - asterisc (in alte boli): 43
  - dublura categoriei parinte (nespecificat): 26
  - subzona de organ (D5): 23
  - procedura: 13
  - agent cauzal, nu boala: 1
- găsite automat în dicționar (P4.1–P4.3): **111**
- de decis manual (`nou` + `posibil`): **481**
- **afecțiuni adăugate: 79**

## Decizii manuale

- **Existau sub alt nume** (prinse la validarea G6, scoase din lot): `Afachie` (H27.0), `Amaurosis fugax` (G45.3), `Amigdalita cu Aspergillus` (B44.2), `Artrita infectioasa cu stafilococ` (M00.0), `Oul oprit in evolutie` (O02.1, avort ratat), `Distocie` (O62), `Aplazie biliara` (Q44.2, atrezie biliară). De aici înainte potrivirea automată verifică și titlul englezesc CIM-10.
- **Existau, găsite la căutarea manuală:** amibiază (colită/dizenterie amibiană, amebom, abcesele amibiene), aspergiloză invazivă/diseminată, anemiile megaloblastice B12/folat, anemia Fanconi, deficitul de piruvat-kinază, aplazia eritrocitară pură, anemia prematurității (`Anemie neonatala`), abcesul epidural/subdural (`Empiem subdural`), astmul nonalergic, angina Prinzmetal, sindromul Baastrup, CRPS/algoneurodistrofie, anomaliile congenitale deja prezente (focomelie, amelie, ectrodactilie, atrezii digestive, agenezii renale/ovariene/uterine, lisencefalie, holoprozencefalie).
- **Grupate în categoria lor (D5 / G1):** variantele „cu complicații” (ascaridioză, avitaminoza A cu xeroză/pete Bitot, anevrismele aortice cu/fără ruptură, apendicita cu peritonită), formele acute/cronice/tranzitorii (aplazia eritrocitară pură), lateralitățile și duratele (amnezia post-traumatică < 24 h etc., agenezia renală uni/bilaterală), subzonele (abcesul cutanat al feței/gâtului/trunchiului, atreziile anorectale după tipul de fistulă).
- **Nu sunt boli anume (G7):** categoriile „Afecțiuni ale …”, „Anomalii ale …”, „Atrofii sistemice … în mixedem” (asterisc), abuzul de antiacide/laxative (F55, titluri stricate în PDF), asfixia la naștere „ușoară/severă” (grupată în `Asfixie perinatala`), alimentația lentă a nou-născutului, asimetria facială, urechea jos implantată.
- **Variante de organ / tip păstrate separat (G4):** actinomicoza cervicofacială și abdominală, angiosarcomul hepatic, abcesele de organ (timic, uretral, vulvar, anorectal, ischiorectal, glandă salivară), alopecia universală/totală/cicatricială/congenitală.
- **Reîmpărțire după numele afecțiunii (D4 revizuit, 2026-10-05):** pasul A conține doar afecțiunile al căror **nume canonic** începe cu A. Cele 22 de afecțiuni găsite la A dar cu nume la altă literă (`Coagulopatie`, `Reactie id`, `Sindrom Gianotti-Crosti`, `Macroftalmie` etc.) au fost scoase din dicționar și așteaptă în `tmp/icd10_work/pending_by_letter.jsonl`, fiecare la litera ei. Invers, sub coduri cu titlul la altă literă am găsit 7 afecțiuni noi cu nume la A: `Acatalazie` (E80.3), `Abces palpebral` (H00.0), `Abces submandibular` (K12.2), `Atrofie renala` (N26), `Aplazie de glande salivare` (Q38.4), `Aplazie ulnara` (Q71.5), `Amputatie congenitala` (Q71.9, Q72.9). Restul termenilor cu A din alte coduri existau deja (`Artropatie neuropatica`, `Agammaglobulinemie`, `Corioamnionita`, `Granulomatoza eozinofilica cu poliangeita`, `Exostoza multipla ereditara`, `Displazie ectodermica` etc.) sau nu sunt boli (localizări, titluri de bloc).

## Adăugate

| Nume canonic | Coduri | Sinonime |
|---|---|---|
| Abces anorectal | K61, K61.2, K61.4 | abces al regiunii anorectale; abces anal; abces rectal; anorectal abscess; anal abscess; rectal abscess |
| Abces de glanda salivara | K11.3 | abcesul glandelor salivare; abces parotidian; abces al glandei submandibulare; salivary gland abscess; abscess of salivary gland; parotid abscess |
| Abces ischiorectal | K61.3 | abces al fosei ischiorectale; abces ischioanal; abces pararectal; ischiorectal abscess; ischioanal abscess; abscess of ischiorectal fossa |
| Abces palpebral | H00.0 | abces al pleoapei; furuncul palpebral; colectie purulenta palpebrala; eyelid abscess; abscess of eyelid; palpebral abscess |
| Abces submandibular | K12.2 | abces al spatiului submandibular; abces submaxilar; colectie purulenta submandibulara; submandibular abscess; submandibular space abscess; submaxillary abscess |
| Abces timic | E32.1 | abcesul timusului; abces al timusului; colectie purulenta timica; thymic abscess; abscess of thymus; thymus abscess |
| Abces uretral | N34.0 | abces periuretral; abcesul uretrei; colectie purulenta uretrala; urethral abscess; periurethral abscess; abscess of urethra |
| Abces vulvar | N76.4 | abces al vulvei; furuncul vulvar; colectie purulenta vulvara; vulvar abscess; abscess of vulva; vulvar furuncle |
| Abraziune dentara | K03.1 | abraziunea dintilor; uzura dentara prin abraziune; abraziune cervicala dentara; dental abrasion; tooth abrasion; abrasion of teeth |
| Absenta congenitala a trompei lui Eustache | Q16.2 | agenezie a trompei lui Eustache; absenta congenitala a trompei auditive; aplazie de trompa Eustache; absence of eustachian tube; congenital absence of eustachian tube; eustachian tube agenesis |
| Acantamebioza | B60.1 | infectie cu Acanthamoeba; acantamoebioza; amebioza cu Acanthamoeba; acanthamoebiasis; acanthamebiasis; Acanthamoeba infection |
| Acatalazie | E80.3 | acatalasemie; boala Takahara; deficit ereditar de catalaza; acatalasia; acatalasemia; Takahara disease |
| Acidoza metabolica neonatala | P74.0 | acidoza metabolica tardiva a nou-nascutului; acidoza metabolica a nou-nascutului; acidoza neonatala tardiva; late metabolic acidosis of newborn; neonatal metabolic acidosis; metabolic acidosis of prematurity |
| Acnee excoriata | L70.5 | acnee excoriee; acnee excoriata a tinerelor fete; acnee prin ciupire; acne excoriee; excoriated acne; picker's acne |
| Acnee tropicala | L70.3 | acnee tropica; acnee din climat tropical; acnee de caldura; acne tropica; tropical acne; acne tropicalis |
| Acnee varioliforma | L70.2 | acnee necrotica miliara; acnee frontala necrotica; acnee varioliforma a fruntii; acne varioliformis; acne necrotica; acne necrotica miliaris |
| Acrodermatita continua Hallopeau | L40.2 | acrodermatita continua; acrodermatita supurativa continua; boala Hallopeau; acrodermatitis continua of Hallopeau; acrodermatitis continua; acrodermatitis perstans |
| Actinomicetom | B47.1 | micetom actinomicotic; micetom bacterian; micetom cu Nocardia; actinomycetoma; actinomycotic mycetoma; bacterial mycetoma |
| Actinomicoza abdominala | A42.1 | actinomicoza abdominopelvina; actinomicoza intestinala; actinomicoza ileocecala; abdominal actinomycosis; abdominopelvic actinomycosis; intestinal actinomycosis |
| Actinomicoza cervicofaciala | A42.2 | actinomicoza cervico-faciala; actinomicoza oro-cervico-faciala; actinomicoza mandibulara; cervicofacial actinomycosis; orocervicofacial actinomycosis; lumpy jaw |
| Adipozitate localizata | E65 | depozit adipos localizat; burelet adipos; sort abdominal adipos; localized adiposity; fat pad; localized fat deposit |
| Afakie congenitala | Q12.3 | afachie congenitala; absenta congenitala a cristalinului; aplazie de cristalin; congenital aphakia; congenital absence of lens; primary aphakia |
| Agalactie | O92.3 | absenta secretiei lactate; agalactie primara; esecul lactatiei; agalactia; absence of lactation; lactation failure |
| Agenezie de aparat lacrimal | Q10.4 | absenta congenitala a aparatului lacrimal; aplazie de aparat lacrimal; agenezie a glandei lacrimale; agenesis of lacrimal apparatus; congenital absence of lacrimal apparatus; lacrimal gland agenesis |
| Agenezie de col uterin | Q51.5 | aplazie cervicala; absenta congenitala a colului uterin; agenezie cervicala; cervical agenesis; congenital absence of cervix; agenesis of cervix |
| Agenezie de vezica urinara | Q64.5 | absenta congenitala a vezicii urinare; agenezie vezicala; agenezie de vezica si uretra; bladder agenesis; congenital absence of bladder; agenesis of urinary bladder |
| Agenezie suprarenala | Q89.11 | absenta congenitala a glandei suprarenale; aplazie suprarenala; agenezie adrenala; adrenal agenesis; congenital absence of adrenal gland; adrenal aplasia |
| Agenezie tubara | Q50.61 | absenta trompei uterine; absenta congenitala a trompei Fallope; aplazie tubara; fallopian tube agenesis; congenital absence of fallopian tube; absent fallopian tube |
| Agenezie ureterala | Q62.4 | agenezia ureterului; absenta ureterului; ureter absent congenital; ureteral agenesis; agenesis of ureter; absent ureter |
| Ainhum | L94.6 | dactiloliza spontana; ainhum idiopatic; constrictie spontana a degetului mic de la picior; dactylolysis spontanea; spontaneous dactylolysis; ainhum disease |
| Alopecie cicatriciala | L66 | alopecie cicatriceala; pierdere de par cicatriciala; alopecie cicatriciala primara; cicatricial alopecia; scarring alopecia; scarring hair loss |
| Alopecie congenitala | Q84.0 | atricoza congenitala; atrichie congenitala; absenta congenitala a parului; congenital alopecia; congenital atrichia; atrichia congenita |
| Alopecie totala | L63.0 | alopecia totala a scalpului; pierderea totala a parului de pe scalp; chelie totala; alopecia totalis; alopecia areata totalis; total scalp hair loss |
| Alopecie universala | L63.1 | pierderea parului de pe tot corpul; alopecie areata universala; chelie universala; alopecia universalis; alopecia areata universalis; universal alopecia |
| Alungire hipertrofica a colului uterin | N88.4 | hipertrofie a colului uterin; elongatie hipertrofica cervicala; alungirea colului uterin; hypertrophic elongation of cervix; cervical elongation; hypertrophy of cervix uteri |
| Amastie | Q83.0 | absenta congenitala a sanului; agenezie mamara; aplazie mamara; amastia; congenital absence of breast; breast agenesis |
| Amenoree primara | N91.0 | absenta menstruatiei la pubertate; amenoree primitiva; lipsa instalarii menstruatiei; primary amenorrhea; primary amenorrhoea; failure to menstruate at puberty |
| Amenoree secundara | N91.1 | absenta menstruatiei dupa menstruatii anterioare; amenoree secundara dobandita; oprirea menstruatiei; secondary amenorrhea; secondary amenorrhoea; cessation of menses |
| Amielie | Q06.0 | absenta congenitala a maduvei spinarii; agenezie medulara; aplazie a maduvei spinarii; amyelia; congenital absence of spinal cord; spinal cord agenesis |
| Amnezie posttraumatica | F04.0 | amnezie post-traumatica; amnezie dupa traumatism cranian; pierdere de memorie posttraumatica; post-traumatic amnesia; posttraumatic amnesia; amnesia after head injury |
| Amputatie congenitala | Q71.9, Q72.9 | amputatie congenitala a membrului; absenta congenitala transversala a membrului; deficienta transversala congenitala a membrului; congenital amputation; congenital transverse limb deficiency; transverse reduction defect of limb |
| Anchiloza dentara | K03.5 | anchiloza dintelui; dinte anchilozat; anchiloza dento-alveolara; ankylosis of teeth; dental ankylosis; dentoalveolar ankylosis |
| Anemie aplastica medicamentoasa | D61.1 | anemie aplastica indusa de medicamente; anemie aplazica medicamentoasa; aplazie medulara medicamentoasa; drug-induced aplastic anemia; medication-induced aplastic anemia; drug-induced bone marrow aplasia |
| Anemie asociata cancerului | D63.0 | anemie in bolile neoplazice; anemie din cancer; anemie neoplazica; anemia in neoplastic disease; cancer-related anemia; anemia of cancer |
| Anemie hemolitica medicamentoasa | D59.0, D59.2 | anemie hemolitica indusa de medicamente; hemoliza medicamentoasa; anemie hemolitica autoimuna medicamentoasa; drug-induced hemolytic anemia; drug-induced immune hemolytic anemia; medication-induced hemolysis |
| Anemie prin deficit de proteine | D53.0 | anemie prin carenta proteica; anemie prin carenta de proteine; anemie prin deficit de aminoacizi; protein deficiency anemia; protein malnutrition anemia; amino acid deficiency anemia |
| Anemie scorbutica | D53.2 | anemie prin deficit de vitamina C; anemie din scorbut; anemie prin carenta de acid ascorbic; scorbutic anemia; vitamin C deficiency anemia; anemia of scurvy |
| Anetodermie | L90.1, L90.2 | atrofie maculara cutanata; anetodermie Schweninger-Buzzi; anetodermie Jadassohn-Pellizzari; anetoderma; macular atrophy of skin; anetoderma of Jadassohn-Pellizzari |
| Anevrism de artera pulmonara | I28.1 | anevrismul arterei pulmonare; dilatatie anevrismala a arterei pulmonare; anevrism pulmonar arterial; pulmonary artery aneurysm; aneurysm of pulmonary artery; pulmonary arterial aneurysm |
| Angiodisplazie colonica | K55.2 | angiodisplazia colonului; ectazie vasculara colonica; malformatie vasculara colonica; colonic angiodysplasia; angiodysplasia of colon; colonic vascular ectasia |
| Angiodisplazie gastrica | K31.81 | angiodisplazia stomacului; angiodisplazie gastroduodenala; angiodisplazie a stomacului si duodenului; gastric angiodysplasia; angiodysplasia of stomach and duodenum; gastroduodenal angiodysplasia |
| Angiosarcom hepatic | C22.3 | hemangiosarcom hepatic; sarcom cu celule Kupffer; angiosarcomul ficatului; hepatic angiosarcoma; liver angiosarcoma; Kupffer cell sarcoma |
| Aniseiconie | H52.3 | anizeiconie; inegalitatea imaginilor retiniene; aniseiconie optica; aniseikonia; unequal retinal image size; aniseiconia |
| Anodontie | K00.0 | absenta congenitala a dintilor; anodontie totala; agenezie dentara totala; anodontia; congenital absence of teeth; total tooth agenesis |
| Anonichie | Q84.3 | absenta congenitala a unghiei; anonichie congenitala; agenezie unghiala; anonychia; congenital absence of nail; anonychia congenita |
| Aplazie de glande salivare | Q38.4 | absenta congenitala a glandelor salivare; agenezie de glande salivare; atrezie de canale salivare; salivary gland aplasia; congenital absence of salivary glands; salivary gland agenesis |
| Aplazie ulnara | Q71.5 | hemimelie ulnara; absenta congenitala a cubitusului; deficienta longitudinala ulnara; ulnar hemimelia; congenital absence of ulna; longitudinal ulnar deficiency |
| Apnee obstructiva neonatala | P28.42 | apnee obstructiva la nou-nascut; apnee neonatala obstructiva; apnee obstructiva a nou-nascutului; obstructive apnea of newborn; neonatal obstructive apnea; obstructive apnoea of the newborn |
| Arinencefalie | Q04.1 | arhinencefalie; agenezie olfactiva; absenta congenitala a lobilor olfactivi; arhinencephaly; arrhinencephaly; olfactory agenesis |
| Artera ombilicala unica | Q27.0 | absenta unei artere ombilicale; cordon ombilical cu doua vase; hipoplazie de artera ombilicala; single umbilical artery; two-vessel umbilical cord; absence of umbilical artery |
| Articulatii Clutton | M03.1 | sinovita Clutton; hidrartroza sifilitica bilaterala a genunchilor; artropatie sifilitica congenitala; Clutton joints; Clutton's joints; syphilitic synovitis of knees |
| Artropatie cristalina | M11.9 | artropatie prin microcristale; artrita indusa de cristale; artropatie microcristalina; crystal arthropathy; crystal-induced arthritis; microcrystalline arthropathy |
| Artropatie dupa bypass intestinal | M02.0 | artrita dupa bypass intestinal; artropatie dupa derivatie intestinala; sindrom artrita-dermatita dupa bypass; bowel bypass arthritis; arthropathy following intestinal bypass; bowel-associated dermatosis-arthritis syndrome |
| Artropatie Jaccoud | M12.0 | artropatie cronica postreumatismala; artropatie Jaccoud postreumatica; sindrom Jaccoud; Jaccoud arthropathy; chronic postrheumatic arthropathy; Jaccoud syndrome |
| Artropatie postvaccinala | M02.2 | artrita postvaccinala; artropatie dupa vaccinare; artrita dupa vaccin; postimmunization arthropathy; post-vaccination arthritis; vaccine-associated arthritis |
| Ataxie cerebeloasa cu debut tardiv | G11.2 | ataxie cerebeloasa tardiva; ataxie cerebeloasa cu debut la adult; ataxie cerebeloasa ereditara tardiva; late-onset cerebellar ataxia; adult-onset cerebellar ataxia; late onset hereditary ataxia |
| Ataxie congenitala neprogresiva | G11.0 | ataxie cerebeloasa congenitala; ataxie congenitala; ataxie cerebeloasa neprogresiva congenitala; congenital nonprogressive ataxia; congenital cerebellar ataxia; nonprogressive congenital ataxia |
| Ataxie ereditara | G11 | ataxie cerebeloasa ereditara; ataxii ereditare; ataxie familiala; hereditary ataxia; inherited ataxia; familial ataxia |
| Atelie | Q83.2 | absenta mamelonului; agenezie de mamelon; aplazie de mamelon; athelia; absent nipple; congenital absence of nipple |
| Atrezie aortica | Q25.2 | atrezie de valva aortica; atrezia aortei; atrezie valvulara aortica; aortic atresia; aortic valve atresia; atresia of aorta |
| Atrofie a crestei alveolare | K08.2 | resorbtie a crestei alveolare; atrofia crestei alveolare edentate; resorbtie osoasa alveolara; alveolar ridge atrophy; atrophy of edentulous alveolar ridge; alveolar ridge resorption |
| Atrofie de glanda salivara | K11.0 | atrofia glandelor salivare; atrofie salivara; atrofie glandulara salivara; salivary gland atrophy; atrophy of salivary gland; salivary atrophy |
| Atrofie de prostata | N42.2 | atrofia prostatei; atrofie prostatica; prostata atrofica; prostatic atrophy; atrophy of prostate; prostate atrophy |
| Atrofie mamara | N64.2 | atrofia sanului; atrofie a glandei mamare; involutie mamara atrofica; breast atrophy; atrophy of breast; mammary atrophy |
| Atrofie musculara | M62.5 | emaciere musculara; pierdere de masa musculara; atrofia muschilor; muscle atrophy; muscle wasting; muscular atrophy |
| Atrofie ovariana | N83.3 | atrofia dobandita a ovarului; atrofie de ovar; atrofie ovariana dobandita; ovarian atrophy; acquired atrophy of ovary; atrophic ovary |
| Atrofie renala | N26 | rinichi mic scleros; rinichi contractat; atrofia rinichiului; renal atrophy; contracted kidney; atrophic kidney |
| Atrofie tiroidiana | E03.4 | atrofia tiroidei; atrofie tiroidiana dobandita; tiroida atrofica; thyroid atrophy; acquired atrophy of thyroid; atrophic thyroid |
| Autism atipic | F84.1 | psihoza infantila atipica; tulburare pervaziva de dezvoltare atipica; autism cu debut atipic; atypical autism; atypical childhood psychosis; pervasive developmental disorder not otherwise specified |

## Decise manual, neadăugate

Titluri `nou` / `posibil` care nu au devenit afecțiuni noi: există sub alt nume, sunt variante ale unei categorii (D5), categorii generice sau nu sunt boli (G7). Coloana „Apropiat” e sugestia automată.

| Cod | Titlu CIM-10 | Apropiat |
|---|---|---|
| A06 | Amibiaza | Amebiaza / Miiaza / Giardiaza |
| A06.1 | Amibiaza intestinala cronica |  |
| A06.3 | Amiliaza (intestinala) | Miiaza / Giardiaza / Meteorism / Paralizie intestinala / Gastroenterita |
| A06.4 | Abcesul amibian al ficatului | Amiloidoza hepatica / Micoza hepatica |
| A06.5 | Abcesul amibian al plamanului |  |
| A06.6 | Abcesul amibian al creierului |  |
| A06.7 | Amibiaza cutanata | Amebiaza cutanata / Miiaza / Amiloidoza cutanata |
| A22.2 | Antrax gastro-intestinal | Antrax gastrointestinal |
| A28.9 | Antropo-zoonoze bacteriene, nespecificate | Infectii bacteriene |
| B43.1 | Abcesul phaeomycotic al creierului |  |
| B43.2 | Abcesul si chistul phaeomycotic subcutanat | Abces subcutanat |
| B44 | Aspergilloza | Aspergiloza / Aspergilom pulmonar |
| B44.0 | Aspergilloza pulmonara invaziva | Aspergiloza pulmonara cronica / Aspergiloza invaziva |
| B44.2 | Aspergilloza amigdaliana |  |
| B44.7 | Aspergilloza diseminata | Aspergiloza invaziva / Listerioza / Scleroza multipla / Hipertricoza / Artroza generalizata |
| B48.2 | Allescheriaza |  |
| B76.0 | Ankylostomiaza | Ancilostomiaza |
| B77.0 | Ascariaza cu complicatii intestinale prin Ascaris |  |
| B77.8 | Ascariaza cu alte complicatii |  |
| B81.0 | Anisakiaza | Anisakidoza |
| B81.3 | Angiostrongyloza intestinala | Tricostrongiloidoza / Strongiloidoza |
| B83.2 | Angiostrongyliaza datorita Parastrongylus cantonensis | Angiostrongiloidoza |
| D50 | Anemia prin carenta de fier | Deficit de fier |
| D51 | Anemia prin carenta in vitamina B12 | Deficit de vitamina A / Deficit de vitamina B12 |
| D51.0 | Anemia prin carenta de vitamina B12, datorita carentei unui factor intrinsec | Deficit de vitamina A / Deficit de vitamina B12 |
| D51.9 | Anemii prin carenta de vitamina B12, nespecificate | Deficit de vitamina A / Deficit de vitamina B12 / Boala hemoragica a nou-nascutului |
| D52 | Anemia prin carenta de acid folic |  |
| D52.0 | Anemia prin carenta alimentara de acid folic | Anemie megaloblastica |
| D52.1 | Anemia prin carenta de acid folic provocata de medicamente |  |
| D53.8 | Anemia asociata cu alte carente nutritionale specificate |  |
| D55 | Anemia datorita tulburarilor enzimatice |  |
| D55.1 | Anemia datorita altor tulburari ale metabolismului glutationului |  |
| D55.2 | Anemia datorita tulburarilor enzimelor glicolitice |  |
| D55.3 | Anemia datorita tulburarilor de metabolism al nucleotidelor |  |
| D56.0 | Alfa-thalasemia | Alfa-talasemie |
| D57.1 | Anemia cu hematii falciforme fara crize | Anemie falciforma |
| D60 | Aplazia pura de celule rosii dobandita [eritroblastopenia] | Aplasia eritrocitara pura / Anemie eritroblastopenica |
| D60.0 | Aplazia pura de celule rosii dobandita cronica |  |
| D60.1 | Aplazia pura de celule rosii dobandita tranzitorie |  |
| D60.9 | Aplazii pure de celule rosii dobandite, nespecificate |  |
| D61.0 | Anemia aplazica constitutionala |  |
| D61.2 | Anemia aplazica datorita altor agenti externi |  |
| D61.3 | Anemia aplazica idiopatica | Anemie aplastica idiopatica |
| D61.9 | Anemia aplazica, nespecificata | Anemie aplastica / Anemie hipoplastica |
| D62 | Anemia post-hemoragica acuta | Anemie posthemoragica |
| D63 | Anemia in bolile cronice clasificate altundeva |  |
| D63.8 | Anemia in cursul altor boli cronice clasificate altundeva |  |
| D64.1 | Anemia sideroblastica secundara datorita unei boli | Anemie sideroblastica |
| D64.2 | Anemia sideroblastica secundara, provocata de medicamente si toxine | Anemie sideroblastica |
| D68.9 | Anomalia de coagulare, nespecificata |  |
| D72.0 | Anomaliile genetice ale leucocitelor |  |
| D72.9 | Anomalia celulelor albe, nespecificata |  |
| D73.3 | Abcesul splinei |  |
| D84.0 | Anomalia functiunii limfocitare antigen I [LFA-1] |  |
| E07.9 | Afectiunea tiroidei, nespecificata | Intoleranta la glucoza |
| E22.0 | Acromegalia si gigantismul pituitar | Artrita asociata acromegaliei |
| E50 | Avitaminoza A | Avitaminoza / Scorbut / Deficit de vitamina A |
| E50.0 | Avitaminoza A cu xeroza conjunctivei |  |
| E50.1 | Avitaminoza A cu pete Bitot si xeroza conjunctivei |  |
| E50.2 | Avitaminoza A cu xeroza corneei |  |
| E50.3 | Avitaminoza A cu ulceratia corneei si xeroza | Ulcer cornean |
| E50.4 | Avitaminoza A cu cheratomalacie | Keratomalacie |
| E50.5 | Avitaminoza A cu hemeralopie vesperala |  |
| E50.6 | Avitaminoza A cu cicatrice xeroftalmica a corneei |  |
| E53.9 | Avitaminoze din grupa B, nespecificate |  |
| E85.1 | Amiloidoza heredofamiliala neuropatica | Neuropatie amiloida |
| E85.2 | Amiloidoza heredofamiliara, nespecificata | Amiloidoza familiala |
| E85.3 | Amiloidoza sistemica secundara | Amiloidoza / Amiloidoza ATTR / Amiloidoza AA / Amiloidoza asociata dializei |
| E85.4 | Amiloidoza la unul sau mai multe organe | Amiloidoza cutanata / Amiloidoza asociata dializei |
| F04.00 | Amnezia post-traumatica, nespecificata | Artroza posttraumatica |
| F04.01 | Amnezia post-traumatica, durata de < 24 de ore |  |
| F04.02 | Amnezia post-traumatica, durata de ≥ 24 de ore si < 14 zile |  |
| F04.03 | Amnezia post-traumatica, durata de ≥ 14 zile |  |
| F40.00 | Agorafobie fara mentionarea tulburarii de panica |  |
| F40.01 | Agorafobie cu tulburare de panica |  |
| F42.1 | Acte predominant compulsive [ritualuri obsedante] |  |
| F44.6 | Anestezie disociativa si pierdere sensoriala | Presbiacuzie |
| F50.1 | Anorexie nervoasa atipica | Anorexie nervoasa |
| F50.4 | Apetit excesiv asociat cu alte tulburari psihologice |  |
| F52.1 | Aversiunea sexuala si lipsa de placere sexuala |  |
| F55.0 | Antidepresive |  |
| F55.2 | Analgezice |  |
| F55.3 | Antiacide |  |
| F80.3 | Afazie dobindita cu epilepsie [Landau-Kleffner] | Sindrom Landau-Kleffner |
| G06 | Abces si granulom intracranian si intrarahidian |  |
| G06.0 | Abces si granulom intracranian |  |
| G06.1 | Abces si granulom intrarahidian |  |
| G06.2 | Abces extradural si subdural, nespecificat |  |
| G11.1 | Ataxia cerebeloasa cu debut precoce | Ataxie |
| G11.3 | Ataxia cerebeloasa cu defect de reparatie a AND | Ataxie / Ataxie telangiectatica |
| G12 | Atrofia musculara spinala si sindroame inrudite | Amiotrofie spinala |
| G12.0 | Atrofia musculara spinala infantila, tip I (Werdning-Hoffman) | Amiotrofie spinala / Amiotrofie spinala infantila / Amiotrofie spinala tip II |
| G13.2 | Atrofii sistemice afectand in principal sistemul nervos central in mixedem (E00.1†; E03.-†) |  |
| G40.6 | Atacuri de "grand mal", nespecificate (cu sau fara petit mal) | Epilepsie absenta / Epilepsie absenta a copilariei |
| G45 | Atacuri cerebrale ischemice tranzitorii si sindroame inrudite |  |
| G45.2 | Atac ischemic tranzitoriu al teritoriilor arteriale precerebrale multiple si bilaterale | Accident ischemic tranzitoriu |
| G45.3 | Amauroza fugace |  |
| G47.30 | Apneea de somn, nespecificata | Apnee in somn |
| G50 | Afectiunile nervului trigemen |  |
| G50.1 | Algia faciala atipica |  |
| G51.1 | Afectiunea ganglionului geniculat |  |
| G52.0 | Afectiunile nervului olfactiv |  |
| G52.1 | Afectiunile nervului gloso-faringian | Nevralgia glosofaringiana |
| G52.2 | Afectiunile nervului vag |  |
| G52.3 | Afectiunile nervului hipoglos |  |
| G52.7 | Afectiunile mai multor nervi cranieni |  |
| G52.8 | Afectiunile altor nervi cranieni specificati |  |
| G54.0 | Afectiunile plexului brahial | Plexopatie brahiala |
| G54.1 | Afectiunile plexului lombosacral | Plexopatie lombosacrala |
| G54.2 | Afectiunile radiculare cervicale, neclasificate altundeva |  |
| G54.3 | Afectiunile radiculare toracice, neclasificate altundeva |  |
| G54.4 | Afectiunile radiculare lombo-sacrale, neclasificate altundeva |  |
| G96.1 | Afectiunile meningelui, neclasificate altundeva |  |
| H03.1 | Atingerea pleoapei in alte boli infectiose clasificate altundeva |  |
| H05.9 | Afectiunea orbitei, nespecificata | Celulita orbitala |
| H18.3 | Alteratia membranelor corneene |  |
| H21.9 | Afectiunea irisului si corpilor ciliari, nespecificata |  |
| H27.0 | Afakia |  |
| H51.9 | Anomaliile miscarilor binoculare, nespecificate |  |
| H53.0 | Ambliopia si anopsia |  |
| H53.4 | Anomalia campului vizual |  |
| H60.0 | Abces al urechii externe | Otita externa circumscrisa |
| H69.9 | Afectiunea trompei Eustache, nespecificata |  |
| H70.2 | Apexita [petrosita] | Boala inflamatorie pelvina / Petrozita / Periostita |
| H74.9 | Afectiunea urechii medii si a apofizei mastoide, nespecificata |  |
| H81.9 | Afectiunea functiei vestibulare, nespecificata | Vertij |
| H93.3 | Afectiunile nervului auditiv | Neuropatie auditiva |
| H93.9 | Afectiunea urechii, nespecificata | Otita |
| I20.1 | Angina pectorala cu spasm inregistrat | Angina pectorala / Angina stabila |
| I25.3 | Anevrismul inimii |  |
| I25.4 | Anevrismul arterei coronare | Anevrism de artera coronara / Spasm coronarian / Anevrism de artera carotidiana / Fistula arteriovenoasa / Fistula coronariana |
| I34 | Afectiunile nereumatice ale valvei mitrale |  |
| I34.9 | Afectiunea nereumatismala a valvulei mitrale, nespecificata |  |
| I35 | Afectiunile nereumatismale ale valvei aortice |  |
| I35.9 | Afectiunea valvei aortice, nespecificata |  |
| I36.9 | Afectiunea nereumatica a valvei tricuspide, nespecificata |  |
| I37 | Afectiunile valvei pulmonare | Boala valvulara pulmonara |
| I37.9 | Afectiunea valvei pulmonare, nespecificata | Boala valvulara pulmonara / Atrezie pulmonara |
| I47.0 | Aritmia ventriculara de reintrare | Aritmie ventriculara |
| I67.1 | Anevrism cerebral, fara ruptura | Anevrism cerebral / Hemoragie subarahnoidiana |
| I68.0 | Angiopatia cerebrala amiloida (E85.-†) | Angiopatie amiloida cerebrala |
| I68.1 | Arterita cerebrala in bolile infectioase si parazitare clasificate altundeva | Vasculita cerebrala |
| I70.1 | Ateroscleroza arterei renale |  |
| I70.2 | Ateroscleroza arterelor extremitatilor | Ateroscleroza |
| I70.20 | Ateroscleroza arterelor extremitatilor, nespecificata |  |
| I70.21 | Ateroscleroza arterelor extremitatilor cu claudicatie intermitenta | Circulatie periferica deficitara |
| I70.22 | Ateroscleroza arterelor extremitatilor cu durere la repaos |  |
| I70.23 | Ateroscleroza arterelor extremitatilor cu ulceratie |  |
| I70.24 | Ateroscleroza arterelor extremitatilor cu gangrena |  |
| I70.8 | Ateroscleroza altor artere | Ateroscleroza aortei |
| I70.9 | Ateroscleroza generalizata si nespecificata |  |
| I71 | Anevrismul si disectia aortica | Anevrism aortic |
| I71.1 | Anevrismul toracic, cu ruptura | Anevrism de aorta toracica |
| I71.2 | Anevrismul toracic, fara mentiunea rupturii | Anevrism de aorta toracica |
| I71.3 | Anevrismul abdominal, cu ruptura | Anevrism de aorta abdominala |
| I71.4 | Anevrismul abdominal, fara mentiunea rupturii | Anevrism de aorta abdominala |
| I71.5 | Anevrismul toraco-abdominal, cu ruptura | Anevrism de aorta abdominala |
| I71.6 | Anevrismul toraco-abdominal, fara mentiunea rupturii | Anevrism de aorta abdominala |
| I71.8 | Anevrismul aortic cu localizare nespecificata, cu ruptura | Anevrism aortic / Ruptura coroidiana |
| I71.9 | Anevrismul aortic, cu localizare nespecificata, fara mentiunea rupturii | Anevrism aortic / Anevrism aortic toracic familial / Anevrism de aorta abdominala / Anevrism de aorta ascendenta / Anevrism de aorta toracica / Disectie de aorta |
| I72.0 | Anevrismul arterei carodite | Anevrism de artera carotidiana / Anevrism popliteu |
| I72.1 | Anevrismul arterei extremitatilor superioare |  |
| I72.2 | Anevrismul arterei renale | Anevrism de artera renala / Anevrism cerebral / Anevrism de artera femurala |
| I72.3 | Anevrismul arterei iliace | Anevrism iliac / Anevrism de artera splenica |
| I72.4 | Anevrismul arterei extremitatilor inferioare |  |
| I72.8 | Anevrismul altor artere specificate |  |
| I72.9 | Anevrismul cu localizari nespecificate |  |
| I84.6 | Apendice hemoroidal rezidual |  |
| J03.0 | Amigdalita streptococica | Amigdalita acuta cu streptococ / Angina streptococica / Amigdalita stafilococica |
| J03.8 | Amigdalita acuta datorita altor microorganisme specificate |  |
| J34.0 | Abces, furuncul si antraxul nasului |  |
| J39.0 | Abces parafaringian si retrofaringian | Abces parafaringian / Abces retrofaringian / Abces periamigdalian |
| J45.0 | Astmul cu predominenta alergica | Astmul bronsic |
| J45.1 | Astmul nonalergic | Astmul bronsic |
| J45.8 | Astmul asociat |  |
| J85 | Abcesul pulmonar si al mediastinului | Abces pulmonar / Abces pulmonar primar / Abces pulmonar secundar |
| J85.1 | Abcesul pulmonar cu pneumopatie | Abces pulmonar / Abces pulmonar primar / Abces pulmonar secundar / Abces pulmonar cu Pseudomonas |
| J85.3 | Abcesul mediastinului | Abces mediastinal |
| K04.6 | Abces periapical cu fistula | Abces dentar |
| K06.9 | Afectiunea gingiei si a crestei alveolare edentate, nespecificata |  |
| K07.6 | Afectiunea articulatiei temporo-mandibulare | Sindrom al articulatiei temporo-mandibulare / Artroza temporomandibulara |
| K07.9 | Anomalia dento-faciala, nespecificata |  |
| K08.9 | Afectiunea interesand dintii si parodontiul, nespecificata |  |
| K31.82 | Angiodisplazia stomacului si duodenului cu hemoragie |  |
| K35.0 | Apendicita acuta cu peritonita generalizata | Peritonita / Peritonita acuta generalizata |
| K35.1 | Apendicita acuta cu abces peritoneal | Abces peritoneal |
| K55.21 | Angiodisplazia colonului fara mentionarea hemoragiei | Hemoragie digestiva inferioara |
| K55.22 | Angiodisplazia colonului cu hemoragie | Hemoragie digestiva inferioara |
| K56.5 | Aderente intestinale [bride] cu obstructie | Ocluzie intestinala |
| K63.0 | Abces al intestinului | Abces intestinal / Abces perineal |
| K75.0 | Abces al ficatului | Abces amibian hepatic |
| L02 | Abces cutanat, furuncul si furuncul antracoid | Abces cutanat |
| L02.0 | Abces cutanat, furuncul si furuncul antracoid al fetei | Abces cutanat |
| L02.1 | Abces cutanat, furuncul si furuncul antracoid al gatului | Abces cutanat |
| L02.2 | Abces cutanat, furuncul si furuncul antracoid al trunchiului | Abces cutanat / Dehiscence de perete abdominal / Hernie inghinala / Hernie lombara / Hernie Richter |
| L02.3 | Abces cutanat, furuncul si furuncul antracoid al fesei | Abces cutanat |
| L02.4 | Abces cutanat, furuncul si carbuncul al membrului | Abces cutanat / Carbuncul cutanat |
| L02.8 | Abces cutanat, furuncul si furuncul antracoid cu alte localizari | Abces cutanat |
| L30.2 | Autosensibilizarea cutanata |  |
| L44.4 | Acrodermatita eritemato-papuloasa infantila [Giannotti-Crosti] |  |
| L55 | Arsura de soare | Arsura solara |
| L55.0 | Arsura de soare, eritem | Arsura solara |
| L55.1 | Arsura de soare, profunzime partiala | Arsura solara |
| L55.2 | Arsura de soare, profunzime adanca | Arsura solara |
| L57.1 | Actino-reticuloza |  |
| L64 | Alopecia androgena | Alopecie androgenetica |
| L64.0 | Alopecia androgenica datorita medicamentelor | Alopecie androgenetica |
| L64.9 | Alopecia androgenica, nespecificata | Alopecie androgenetica |
| L65.1 | Anagen |  |
| L65.2 | Alopecia flucinoasa Pinkus |  |
| L66.9 | Alopecia cicatriciala, nespecificata | Acnee cheloida / Pseudopelada / Atelectazie cicatriciala |
| L70 | Acneea | Acnee |
| L70.0 | Acneea vulgaris | Acnee |
| L70.1 | Acneea conglobata | Acnee conglobata / Rosacea fulminans |
| L70.4 | Acneea infantila | Acnee neonatala |
| L71 | Acneea rozacee | Acnee rozacee |
| L71.9 | Acneea rosacee, nespecificata | Acnee rozacee |
| L73.0 | Acneea cheloida | Acnee cheloida |
| L87.9 | Anomalia eliminarii transepidermice, nespecificata |  |
| L90 | Afectiunile atrofice ale pielii |  |
| L90.3 | Atrofodermia Pasini si Pierini | Atrofodermie |
| M00 | Artrita piogenica | Sindrom PAPA |
| M00.0 | Artrita si poliartrita stafilococica |  |
| M00.1 | Artrita si poliartrita pneumococica | Artrita pneumococica |
| M00.8 | Artrita si poliartrita datorita altor agenti bacterieni specificati |  |
| M01.2 | Artrita in cursul bolii Lyme (A69.2†) | Boala Lyme tardiva |
| M01.3 | Atrita in alte boli bacteriene clasificate altundeva |  |
| M01.4 | Artrita in rubeola (B06.8†) | Artrita brucelozica |
| M01.5 | Artrita in alte boli virale clasificate altundeva | Artrita virala |
| M01.6 | Artrita in micoze (B35-B49†) |  |
| M01.8 | Artrita in alte boli infectioase si parazitare clasificate altundeva | Artrita septica |
| M02 | Artropatii de reactie |  |
| M02.1 | Artropatia postdizenterica |  |
| M03.0 | Atrita postmeningococica (A39.8†) | Artrita meningococica |
| M05.3 | Artrita reumatoida cu implicarea altor organe sau sisteme | Artrita reumatoida |
| M07 | Artropatii psoriazice si enteropatice | Artrita enteropatica / Artrita psoriazica |
| M07.0 | Artropatia psoriazica interfalangiana distala (L40.5†) | Artrita interfalangiana / Artrita psoriazica / Artroza interfalangiana distala |
| M07.1 | Artrita mutilanta (L40.5†) | Artrita psoriazica mutilanta |
| M07.5 | Atropatia in colita ulceroasa (K51.-†) |  |
| M08 | Artrita juvenila | Artrita idiopatica juvenila / Artrita juvenila asociata entezitei / Artrita juvenila nediferentiata / Artrita juvenila oligoarticulara / Artrita juvenila poliarticulara / Artrita juvenila psoriazica |
| M08.4 | Artrita juvenila pauciarticulara | Artrita juvenila poliarticulara / Artrita juvenila oligoarticulara |
| M09.0 | Artrita juvenila in psoriazis (L40.5†) | Artrita juvenila psoriazica |
| M09.2 | Artrita juvenila in colita ulceroasa (K51.†) |  |
| M12.5 | Artropatia traumatica |  |
| M14.0 | Artropatia gutoasa datorita unui deficit enzimatic si altor tulburari ereditare | Artrita gutoasa |
| M14.1 | Artropatia cu microcristale in alte tulburari metabolice |  |
| M14.4 | Artropatia in amiloidoza (E85.-†) | Artrita asociata amiloidozei |
| M14.5 | Artropatia in alte boli endocrine, de nutritie si metabolism |  |
| M14.8 | Artropatia in alte boli specificate clasificate altundeva |  |
| M15.3 | Artroza secundara multipla | Artroza posttraumatica |
| M18 | Artroza primei articulatii carpo-metacarpiene | Rizartroza |
| M18.0 | Artroza primara a primei articulatii carpo-metacarpiene, bilaterala |  |
| M18.2 | Artroza post-traumatica a primelor articulatii carpo-metacarpiene, bilaterala |  |
| M19.0 | Artroza primara a altor articulatii | Artroza / Artroza secundara / Artroza generalizata / Hiperoxalurie primara tip 1 |
| M22 | Afectiunile rotulei |  |
| M22.9 | Afectiunea rotulei, nespecificata |  |
| M23 | Afectiunea interna a genunchiului |  |
| M24.6 | Anchiloza articulatiei | Ankiloza articulatiei |
| M31.5 | Arterita cu celule gigante cu polimialgie reumatismala | Arterita cu celule gigante |
| M35.9 | Atingeri sistemice ale tesutului conjuctiv, nespecificate | Mastocitoza sistemica |
| M36.1 | Artropatia in boli neoplazice, clasificate altundeva (C00-D48†) |  |
| M36.3 | Artropatia in alte tulburari sangvine (D50-D76†) |  |
| M36.4 | Artropatia in reactiile de hipersensibilitate clasificate altundeva | Purpura Henoch-Schonlein / Nefropatia purpurica |
| M48.2 | Artroza interspinoasa |  |
| M50.9 | Afectiunea unui disc cervical, nespecificata |  |
| M51.9 | Afectiunea unui disc intervertebral, nespecificat |  |
| M65.0 | Abcesul tecii tendonului |  |
| M71.0 | Abcesul bursei |  |
| M89.0 | Algoneurodistrofia | Sindrom Marfan |
| M94.9 | Afectiunea cartilagiului, nespecificata |  |
| N15.1 | Abces renal si perirenal | Abces perirenal / Abces renal |
| N41.2 | Abcesul prostatei | Abces prostatic |
| N49.0 | Afectiunile inflamatorii ale veziculelor seminale |  |
| N49.1 | Afectiunile inflamatorii ale cordonului spermatic, tunicii vaginale si canalului deferent | Ascita |
| N50.0 | Atrofia testiculului | Atrofie testiculara |
| N50.9 | Afectiunea organelor genitale masculine, nespecificata |  |
| N60.2 | Adenofibroza sanului |  |
| N73.6 | Aderente peritoneale pelviene | Aderente pelvine / Adeziviune peritoneala |
| N75.1 | Abcesul glandei Bartholin | Abces de glanda Bartholin / Chist de glanda Bartholin |
| N90.5 | Atrofia vulvei | Atrofie vulvara |
| N91 | Amenoree, oligomenoree si hipomenoree |  |
| N96 | Avort obisnuit |  |
| O02.1 | Avort fals |  |
| O04 | Avort medical |  |
| O43 | Anomaliile placentei |  |
| O43.2 | Aderare anormala a placentei |  |
| O62 | Anormalitati de contractie uterina si de dilatare a colului |  |
| O62.9 | Anomalia contractiei uterine si dilatatia de col, nespecificata |  |
| O72.3 | Anomalia de coagulare postpartum |  |
| O91.1 | Abcesul sanului asociat nasterii | Abces mamar |
| O99.0 | Anemia complicand sarcina, nasterea si lauzia | Anemie de sarcina |
| P15.6 | Adipo-necroza subcutanata datorita traumatismului la nastere | Traumatism obstetric |
| P21 | Asfixia la nastere |  |
| P21.0 | Asfixia la nastere severa |  |
| P21.1 | Asfixia la nastere usoara sau moderata |  |
| P21.9 | Astixia la nastere, nespecificata | Anorexie nervoasa / Anotie |
| P24.0 | Aspiratia de meconiu in perioada neonatala | Sindrom de aspiratie de meconiu / Sindrom de aspiratie neonatala |
| P24.2 | Aspiratia de sange in perioada neonatala | Sindrom de aspiratie neonatala |
| P24.3 | Aspiratia de lapte si alimente regurgitate in perioada neonatala | Sindrom de aspiratie neonatala |
| P28.0 | Atelectazia primara a nou-nascutului | Atelectazie neonatala |
| P28.40 | Apneea nou-nascutului, nespecificata | Acnee neonatala / Anemie neonatala / Pneumonie congenitala |
| P28.41 | Apneea prematuritatii | Apnee prematurului |
| P56 | Anasarca feto-placentara datorita bolii hemolitice |  |
| P56.0 | Anasarca feto-placentara datorita izoimunizarii |  |
| P56.9 | Anasarca feto-placentara datorita altor boli hemolitice nespecificate |  |
| P61.2 | Anemia prematuritatii | Anemie neonatala |
| P61.3 | Anemia congenitala prin pierderi de sange fetal | Hemoragie |
| P83.2 | Anasarca feto-placentara nedatorita unei boli hemolitice |  |
| P92.2 | Alimentatia lenta a nou-nascutului | Meningita neonatala |
| Q00 | Anencefalia si malformatii similare |  |
| Q00.01 | Anencefalia incompleta | Hidranencefalie / Anencefalie / Iniencefalie |
| Q00.2 | Acefalia | Anencefalie / Raceala |
| Q00.20 | Acefalia, nespecificata | Anencefalie / Raceala |
| Q00.21 | Acefalia, deschisa |  |
| Q00.22 | Acefalia, inchisa |  |
| Q04.01 | Agenezia corpului calos | Agenezie de corp calos / Boala Marchiafava-Bignami |
| Q04.34 | Agiria si lissencefalia |  |
| Q11 | Anoftalmia, microftalmia si macroftalmia |  |
| Q16.0 | Absenta congenitala a pavilionului urechii | Anotie |
| Q16.1 | Absenta, atrezia sau strictura conductului auditiv (extern) |  |
| Q17.4 | Anomalia de pozitie a urechii |  |
| Q25.5 | Atrezia arterei pulmonare | Atrezie pulmonara |
| Q30.0 | Atrezia choanelor |  |
| Q30.1 | Agenezia si hipoplazia nasului | Arhinie / Agengezie pancreatica / Aniridie / Atrezie vaginala |
| Q33.3 | Agenezia pulmonara | Agengezie pulmonara / Stenoza pulmonara / Gangrena pulmonara |
| Q39.1 | Atrezia esofagului cu fistula traheo-esofagiana | Atrezie esofagiana / Atrezie esofagiana cu fistula / Fistula traheoesofagiana / Fistula bronhoesofagiana |
| Q39.11 | Atrezia esofagului cu fistula intre trahee si punga esofagiana superioara | Atrezie esofagiana / Atrezie esofagiana cu fistula / Fistula traheoesofagiana |
| Q39.12 | Atrezia esofagului cu fistula intre trahee si punga esofagiana inferioara | Atrezie esofagiana / Atrezie esofagiana cu fistula / Fistula traheoesofagiana |
| Q39.19 | Atrezia esofagului cu fistula traheo-esofagiana | Atrezie esofagiana / Atrezie esofagiana cu fistula / Fistula traheoesofagiana |
| Q41 | Absenta congenitala, atrezia si stenoza intestinului subtire | Estenoza intestinala congenitala |
| Q41.0 | Absenta, atrezia si stenoza congenitala a duodenului |  |
| Q41.1 | Absenta, atrezia si stenoza congenitala a jejunului |  |
| Q41.2 | Absenta, atrezia si stenoza congenitala a ileonului |  |
| Q41.8 | Absenta, atrezia si stenoza congenitala a altor parti specificate ale intestinului subtire | Estenoza intestinala congenitala |
| Q41.9 | Absenta, atrezia si stenoza congenitala a intestinului subtire, parte nespecificata | Estenoza intestinala congenitala |
| Q42 | Absenta, atrezia si stenoza congenitala a intestinului gros | Estenoza intestinala congenitala |
| Q42.0 | Absenta, atrezia si stenoza congenitala a rectului cu fistula | Atrezie rectala |
| Q42.00 | Absenta, atrezia si stenoza congenitala a rectului cu fistula nespecificata | Atrezie rectala |
| Q42.01 | Absenta, atrezia si stenoza congenitala a rectului cu fistula recto-uretrala | Atrezie rectala / Fistula rectouretrala / Strictura uretrala |
| Q42.02 | Absenta, atrezia si stenoza congenitala a rectului cu fistula recto-vezicala | Atrezie rectala |
| Q42.03 | Absenta, atrezia si stenoza congenitala a rectului cu fistula recto-vulvara | Atrezie rectala |
| Q42.04 | Absenta, atrezia si stenoza congenitala a rectului cu fistula recto-cutanata | Atrezie rectala |
| Q42.05 | Absenta, atrezia si stenoza congenitala a rectului cu fistula recto-cloacala | Atrezie rectala |
| Q42.09 | Absenta, atrezia si stenoza congenitala a rectului cu alta fistula | Atrezie rectala |
| Q42.1 | Absenta, atrezia si stenoza congenitala a rectului, fara fistula | Atrezie rectala |
| Q42.2 | Absenta, atrezia si stenoza congenitala a anusului cu fistula |  |
| Q42.20 | Absenta, atrezia si stenoza congenitala a anusului cu fistula nespecificata |  |
| Q42.21 | Absenta, atrezia si stenoza congenitala a anusului cu fistula ano-cutanata | Fistula anala |
| Q42.22 | Absenta, atrezia si stenoza congenitala a anusului cu fistula ano-vestibulara | Fistula anala |
| Q42.29 | Absenta, atrezia si stenoza congenitala a anusului cu alta fistula |  |
| Q42.8 | Absenta, atrezia si stenoza congenitala a altor parti ale intestinului gros | Estenoza intestinala congenitala |
| Q42.9 | Absenta, atrezia si stenoza congenitala a intestinului gros, parte nespecificata | Estenoza intestinala congenitala / Atrezie pilorica |
| Q43.32 | Aderente intraabdominale [bride] congenitale | Adeziviune peritoneala |
| Q44.0 | Agenezia, aplazia si hipoplazia vezicii biliare | Aplazie biliara |
| Q44.2 | Atrezia cailor biliare | Atrezie biliara intrahepatica / Aplazie biliara / Colangita |
| Q45.81 | Absenta (completa) (partiala) a cailor digestive, neclasificate altundeva |  |
| Q50.01 | Absenta congenitala a ovarului, unilaterala | Agenezie ovariana |
| Q50.02 | Absenta congenitala a ovarului, bilaterala | Agenezie ovariana |
| Q51.0 | Agenezia si aplazia uterului | Agenezie uterina / Absenta de perone / Aniridie / Anosmie congenitala |
| Q55.0 | Absenta si aplazia testiculului | Anorhidie |
| Q55.00 | Absenta si aplazia testiculului, nespecificat |  |
| Q55.01 | Absenta si aplazia testiculului, unilateral |  |
| Q55.02 | Absenta si aplazia testiculului, bilateral |  |
| Q55.3 | Atrezia vasului deferent |  |
| Q55.5 | Absenta congenitala si aplazia penisului | Agenezie de penis / Absenta de perone / Aniridie |
| Q60 | Agenezia renala si alte defecte de reducere a rinichiului | Agenezie renala |
| Q60.0 | Agenezia renala unilaterala | Agenezie renala |
| Q60.1 | Agenezia renala bilaterala | Agenezie renala / Secventa Potter |
| Q62.1 | Atrezia si stenoza ureterului |  |
| Q62.11 | Atrezia si stenoza jonctiunii uterero-pelviene, unilaterala |  |
| Q62.12 | Atrezia si stenoza jonctiunii uterero-pelviene, bilaterala |  |
| Q62.13 | Atrezia si stenoza jonctiunii uterero-vezicale, unilaterala |  |
| Q62.14 | Atrezia si stenoza jonctiunii uterero-vezicale, bilaterala |  |
| Q62.18 | Atrezia si stenoza altor parti si nespecificate ale ureterului, unilaterala |  |
| Q62.19 | Atrezia si stenoza altor parti si nespecificate ale ureterului, bilaterala |  |
| Q67.0 | Asimetria faciala |  |
| Q71.0 | Absenta completa congenitala a membrului(lor) superior(e) | Amelie |
| Q71.1 | Absenta congenitala a bratului si antebratului cu prezenta mainii |  |
| Q71.2 | Absenta congenitala atat a antebratului cat si a mainii |  |
| Q71.3 | Absenta congenitala a mainii si degetului(lor) | Aniridie / Agenezie renala / Atrezie vaginala |
| Q71.31 | Absenta congenitala a degetului(lor) cu mana ramasa intacta |  |
| Q71.32 | Absenta congenitala a degetului mare cu toate celelalte degete intacte |  |
| Q71.33 | Absenta congenitala a mainii si degetului(lor) | Aniridie / Agenezie renala / Atrezie vaginala |
| Q72.0 | Absenta completa congenitala a membrului(lor) inferior(e) | Amelie |
| Q72.1 | Absenta congenitala a coapsei si a gambei cu prezenta labei piciorului |  |
| Q72.2 | Absenta congenitala atat a gambei cat si a labei piciorului |  |
| Q72.3 | Absenta congenitala a labei piciorului si a degetului(lor) |  |
| Q72.31 | Absenta congenitala a degetului(lor) cu laba piciorului ramasa intacta |  |
| Q72.32 | Absenta congenitala a degetului mare cu celelalte degete intacte |  |
| Q72.33 | Absenta congenitala a labei piciorului si a degetului(lor) |  |
| Q74.3 | Artrogripoza congenitala multipla | Artrogripoza |
| Q74.84 | Asimetria congenitala a membrelor | Amelie |
| Q76.41 | Absenta congenitala a unei(or) vertebre |  |
| Q76.42 | Anomalia congenitala a vertebrei(lor) sacrale | Agenezie renala |
| Q76.61 | Absenta congenitala a coastelor | Agenezie ovariana / Amelie / Anorhidie |
| Q76.71 | Absenta congenitala a sternului | Absenta de perone / Aniridie / Agenezie renala |
| Q77.01 | Acondrogeneza, tip I | Acondrogeneza |
| Q77.02 | Acondrogeneza, tip II | Acondrogeneza |
| Q87.01 | Acrocefalopolisindactilia | Sindrom Apert |
| Q87.27 | Asocierea VATER | Sindrom VACTERL |
| Q89.32 | Aranjament atrial imagine in oglinda cu pozitie inversa |  |
| Q93.3 | Absenta ramurii scurte a cromozomului 4 | Sindrom Wolf-Hirschhorn |
| Q93.6 | Absenta observata numai in prometafaza |  |
| Q93.7 | Absenta cu alte rearanjamente complexe |  |
| Q93.9 | Absenta de autosomi, nespecificata |  |

## Existente (potrivire automată)

Candidații pentru sinonime adăugate ulterior (D6).

| Cod | Titlu CIM-10 | Afecțiune | Potrivire |
|---|---|---|---|
| A22 | Antrax | Antrax | exact |
| A22.0 | Antrax cutanat | Antrax cutanat | exact |
| A22.1 | Antrax pulmonar | Antrax pulmonar | exact |
| A42 | Actinomicoza | Actinomicoza | exact |
| A42.0 | Actinomicoza pulmonara | Pneumonie cu Actinomyces | exact |
| B76.9 | Ankylostomiaza, nespecificata | Larva migrans cutanata | terminatii |
| B77 | Ascariaza | Ascaridioza | exact |
| D50.0 | Anemia prin carenta de fier secundara unei pierderi de sange (cronica) | Anemie posthemoragica | terminatii |
| D51.1 | Anemia prin carenta de vitamina B12, datorita unei malabsorbtii selective a vitaminei B12, cu proteinurie | Sindrom Imerslund-Grasbeck | terminatii |
| D53.9 | Anemia nutritionala, nespecificata | Anemie hemolitica | terminatii |
| D55.0 | Anemia datorita unei carente de glucozo-6-fosfat dehidrogenaza [G-6-PD] | Deficit de glucozo-6-fosfat dehidrogenaza | exact |
| D57.0 | Anemia cu hematii falciforme (anemie drepanocitara) cu crize | Anemie falciforma | exact |
| D58.9 | Anemie hemolitica ereditara, nespecificata | Anemie hemolitica ereditara | exact |
| D59 | Anemia hemolitica dobandita | Anemie hemolitica dobandita | terminatii |
| D64.0 | Anemia sideroblastica ereditara | Anemie sideroblastica legata de X | terminatii |
| D64.4 | Anemia diseritropoietica congenitala | Anemie diseritropoietica congenitala | terminatii |
| D64.9 | Anemia, nespecificata | Anemie | exact |
| D70 | Agranulocitoza | Agranulocitoza | exact |
| E56.9 | Avitaminoza, nespecificata | Avitaminoza | exact |
| E70.3 | Albinism | Albinism | exact |
| E85 | Amiloidoza | Amiloidoza | exact |
| E85.0 | Amiloidoza heredofamiliala non-neuropatica | Amiloidoza renala ereditara | terminatii |
| E87.2 | Acidoza | Acidoza | exact |
| E87.3 | Alcaloza | Alcaloza | exact |
| F40.0 | Agorafobie | Agorafobie | exact |
| F44.0 | Amnezie disociativa | Amnezie disociativa | exact |
| F50.0 | Anorexie nervoasa | Anorexie nervoasa | exact |
| F52.0 | Absenta sau pierdere a dorintei sexuale | Frigiditate | exact |
| F84.0 | Autism infantil | Autism | exact |
| G12.9 | Atrofia musculara spinala, nespecificata | Amiotrofie spinala | terminatii |
| G31.0 | Atrofia cerebrala circumscrisa | Dementa frontotemporala | exact |
| G45.4 | Amnezia globala tranzitorie | Amnezie globala tranzitorie | terminatii |
| G45.9 | Atac ischemic cerebral tranzitoriu, nespecificat | Accident ischemic tranzitoriu | terminatii |
| G47.3 | Apnee de somn | Apnee in somn | exact |
| H47.2 | Atrofia optica | Atrofie optica | terminatii |
| H52.2 | Astigmatism | Astigmatism | exact |
| H93.1 | Acufene (tinnitus) | Tinitus | exact |
| I20 | Angina pectorala | Angina pectorala | exact |
| I20.0 | Angina instabila | Angina instabila | exact |
| I49.9 | Aritmia cardiaca, nespecificata | Aritmie cardiaca | terminatii |
| I67.2 | Ateroscleroza cerebrala | Ateroscleroza cerebrala | exact |
| I67.7 | Arterita cerebrala, neclasificata altundeva | Vasculita cerebrala | exact |
| I70 | Ateroscleroza | Ateroscleroza | exact |
| I70.0 | Ateroscleroza aortei | Ateroscleroza aortei | exact |
| I77.6 | Arterita, nespecificata | Arterita | exact |
| J03 | Amigdalita acuta | Amigdalita | exact |
| J35.0 | Amigdalita cronica | Amigdalita | exact |
| J36 | Angina flegmonoasa | Abces periamigdalian | exact |
| J45 | Astm | Astmul bronsic | exact |
| J63.0 | Aluminoza (pulmonara) | Intoxicatie cu aluminiu | exact |
| J85.2 | Abcesul pulmonar fara pneumopatie | Abces pulmonar | terminatii |
| K04.7 | Abces periapical fara fistula | Abces dentar | exact |
| K10.3 | Alveolita maxilarelor | Alveolita | exact |
| K12.0 | Afte bucale recidivante | Afte bucale | temporal (G1) |
| K14.4 | Atrofia papilelor limbii | Glosita atrofica | exact |
| K22.0 | Acalazia cardiei | Acalazie | terminatii |
| K35 | Apendicita acuta | Apendicita | exact |
| K37 | Apendicita, nespecificata | Apendicita | exact |
| K61.0 | Abces anal | Abces perianal | exact |
| K61.1 | Abces rectal | Abces perirectal | exact |
| K66.0 | Aderente peritoneale | Adeziviune peritoneala | exact |
| K83.0 | Angiocolita [colangita] | Colangita | exact |
| L02.9 | Abces cutanat, furuncul si carbuncul, nespecificat | Furuncul | exact |
| L40.5 | Artropatia psoriazica (M07.0-M07.3*, M09.0*) | Artrita psoriazica | terminatii |
| L63 | Alopecia areata | Alopecie areata | exact |
| L74.4 | Anhidroza | Anhidroza | exact |
| L83 | Acanthosis nigricans | Acantosis nigricans | exact |
| L90.4 | Acrodermatita cronica atrofianta | Acrodermatita cronica atrofianta | exact |
| L99.0 | Amiloidoza cutanata (E85.-†) | Amiloidoza cutanata | exact |
| M01.0 | Artrita meningococica (A39.8†) | Artrita meningococica | exact |
| M01.1 | Artrita tuberculoasa (A18.0†) | Artrita tuberculoasa | exact |
| M05 | Artrita reumatoida seropozitiva | Artrita reumatoida seropozitiva | exact |
| M06.0 | Artrita reumatoida seronegativa | Artrita reumatoida seronegativa | exact |
| M06.9 | Artrita reumatoida, nespecificata | Artrita reumatoida | exact |
| M07.4 | Artropatia in boala Crohn [enterita regionala] (K50.-†) | Boala Crohn | exact |
| M08.0 | Artrita reumatoida juvenila | Artrita idiopatica juvenila | exact |
| M08.2 | Artrita juvenila cu debut sistemic | Artrita idiopatica juvenila | exact |
| M09.1 | Artrita juvenila in boala Crohn [enterita regionala] (K50.- †) | Boala Crohn | exact |
| M13.9 | Artrita, nespecificata | Artrita | exact |
| M14.6 | Artropatia neuropatica | Artropatie neuropatica | terminatii |
| M19.1 | Artroza post-traumatica a altor articulatii | Artroza posttraumatica | exact |
| M19.9 | Artroza, nespecificata | Artroza | exact |
| M31.0 | Angeita de hipersensibilitate | Sindrom Goodpasture | terminatii |
| M36.2 | Artropatia hemofilica (D66-D68†) | Artropatia hemofilica | exact |
| N91.2 | Amenoree, nespecificata | Amenoree | exact |
| O03 | Avort spontan | Avort spontan | exact |
| O06 | Avort nespecificat | Avort spontan | exact |
| P24.1 | Aspiratia lichidului amniotic si a mucusului in perioada neonatala | Sindrom de aspiratie neonatala | terminatii |
| P28.3 | Apneea primitiva de somn a nou-nascutului | Sindrom de hipoventilatie centrala congenitala | terminatii |
| Q00.0 | Anencefalia | Anencefalie | exact |
| Q00.00 | Anencefalia, nespecificata | Anencefalie | exact |
| Q03.1 | Atrezia fisurii Luschka si a foramenului | Sindrom Dandy-Walker | terminatii |
| Q13.1 | Absenta irisului | Aniridie | exact |
| Q22.0 | Atrezia valvei pulmonarei | Atrezie pulmonara | terminatii |
| Q38.1 | Anchiloglosia | Ankyloglosie | exact |
| Q39.0 | Atrezia esofagului, fara fistula | Atrezie esofagiana | exact |
| Q42.3 | Absenta, atrezia si stenoza congenitala a anusului, fara fistula | Anus imperforat | exact |
| Q45.0 | Agenezia, aplazia si hipoplazia pancreasului | Agengezie pancreatica | exact |
| Q50.0 | Absenta congenitala a ovarului | Agenezie ovariana | terminatii |
| Q50.00 | Absenta congenitala a ovarului, nespecificata | Agenezie ovariana | terminatii |
| Q52.0 | Absenta congenitala a vaginului | Atrezie vaginala | exact |
| Q60.2 | Agenezia renala, nespecificata | Agenezie renala | terminatii |
| Q63.10 | Anomalia de contopire a rinichiului, nespecificata | Rinichi in potcoava | terminatii |
| Q73.0 | Absenta congenitala a unui membru(e) nespecificat(e) | Amelie | exact |
| Q77.0 | Acondrogeneza | Acondrogeneza | exact |
| Q77.00 | Acondrogeneza, nespecificata | Acondrogeneza | exact |
| Q77.4 | Acondroplazia | Acondroplazie | terminatii |
| Q84.81 | Aplazia cutanata congenitala | Aplazie cutis congenita | terminatii |
| Q87.02 | Acrocefalosindactilia | Sindrom Apert | terminatii |
| Q89.01 | Asplenia congenitala | Asplenie | terminatii |
| Q93.4 | Absenta ramurii scurte a cromozomului 5 | Sindrom Cri du chat | terminatii |
