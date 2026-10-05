# Litera C — raport CIM-10

- coduri CIM-10 cu titlul la litera C: **509**
- eliminate automat (P2): **107**
  - subzona de organ (D5): 78
  - dublura categoriei parinte (nespecificat): 19
  - asterisc (in alte boli): 9
  - agent cauzal, nu boala: 1
- găsite automat în dicționar (P4.1–P4.3): **121**
- de decis manual (`nou` + `posibil`): **281**
- **afecțiuni adăugate: 67**

## Decizii manuale

- **Cancere (C00–C97, titluri „Tumora maligna …” de la T):** am rulat `match_letter.py T` (fișierele `candidates_T.*` nu intră în commit) și am trecut prin toate categoriile „Tumora maligna a X” / „Tumora maligna secundara …”. **Existau** (sub `Cancer X` / `Carcinom X` / alt nume): limbă, planșeu bucal, cavitate orală, obraz, parotidă și glande salivare, amigdală, orofaringe, nazofaringe, sinus piriform, hipofaringe, esofag, stomac, intestin subțire, colon (cu joncțiunea rectosigmoidiană, `C19`, grupată în `Cancer de colon` = „cancer colorectal”), rect, canal anal, ficat (`C22.0` hepatocarcinom = `Cancer de ficat`), vezică biliară, căi biliare (`Colangiocarcinom`), pancreas, cavitate nazală, sinusuri, laringe, plămân, timus (`Timom malign` = „carcinom timic”), inimă (`Sarcom cardiac`), pleură, nervi periferici (MPNST), retroperitoneu (`Sarcom retroperitoneal`), piele, sân, vulvă, vagin, col uterin, endometru, ovar, trompă, placentă (`Coriocarcinom`), penis, prostată, testicul, rinichi, bazinet, ureter, vezică urinară, uretră, meninge (`Meningiom malign`), creier (`Tumora cerebrala` = „cancer cerebral”), măduva spinării (`Tumora medulara`), tiroidă, paratiroidă, hipofiză. **Adăugate** ca `Cancer X`: buză, gingie, palat, ureche medie (`C30.1`, organ distinct de fosele nazale), trahee, mediastin, os (`C40`–`C41`), peritoneu primar, uter (corp uterin, umbrelă peste `Carcinom endometrial` / sarcoame, ca `Cancer ovarian`), scrot, ochi și anexe, suprarenală (umbrelă peste corticosuprarenală și feocromocitom malign), cancer cu sediu primar necunoscut (`C80`). **Grupate (D5):** subzonele fiecărui organ (cadranele sânului, porțiunile colonului, glanda lacrimală/orbita în `Cancer ocular`, epididimul/cordonul spermatic rar). **Metastazele** (`C77`–`C79`) există ca `Metastaze X` pentru localizările relevante (ganglionare, pulmonare, hepatice, pleurale, peritoneale, cerebrale, osoase, cutanate, ovariene, suprarenale); celelalte (intestin, rinichi, vezică, sân, organe genitale, mediastin) sunt rare ca entitate separată și nu le-am adăugat. `C14`, `C26`, `C39`, `C76`, `C97` sunt reziduale (P2).
- **Carcinom in situ (D00–D09), G4:** există `Carcinom in situ` (generic), `Carcinom in situ mamar`, ductal și lobular in situ, `Boala Bowen` (piele), neoplaziile intraepiteliale cervicală (CIN 3 = `D06`), vulvară, anală, peniană. Am adăugat doar `Carcinom urotelial in situ` (`D09.0`, entitate clinică proprie). CIS fără nume consacrat (cavitate bucală, esofag, stomac, urechea medie, căi respiratorii, alte organe genitale) rămân în `Carcinom in situ`.
- **Existau sub alt nume:** candidozele (cutanată, unghială, vulvovaginală, neonatală), cromomicoza (`Cromoblastomikoza`), criptococoza cerebrală (`Meningita criptococica`), cisticercoza oculară, hemofilia A (`D66`), CID, crioglobulinemia, cardita virală (`Miocardita`), coreea reumatică (`Coreea Sydenham`), cardiopatia aterosclerotică (`Boala coronariana`), congestia pasivă a ficatului (`Ciroza cardiaca`), coledocolitiaza, chistul epidermic (`Chist sebaceu`), condrocalcinoza familială (`Pseudoguta`), capsulita retractilă (`Capsulita adeziva`; potrivirea automată cu „Sindrom de iesire toracica” e greșită), cistita radică (`Cistita de radiatii`), chistul renal dobândit (`Chist renal simplu`), lordoza (`Hiperlordoza`), cefaleea medicamentoasă (`Cefalee prin abuz de medicamente`), canabinoza (`Plaman de canepa`), ciclita posterioară / pars planita (`Ciclita`), condiloma lata (sifilis secundar), condroplazia metafizară (`Displazie metaphizara`), chistul tireoglos, curbura congenitală a penisului (`Cordon penian`), chistul de urac (`Persistenta de urac`), ciclopia, cefalhematomul, convulsiile neonatale, colobomurile (irian, de cristalin, papilar → `Colobom ocular` / `Colobom de nerv optic`), sindromul Sly, xantomatoza cerebrotendinoasă, hermafroditismul (chimera 46,XX/46,XY), cromozomul X fragil.
- **Grupate (D5 / G1):** formele cataractei senile, coxartrozei, carii dentare (smalț, dentină, cement), celulitei (degete, membre, față, trunchi), conjunctivitei (mucopurulentă, atopică, cronică), colesteatomului recidivant postmastoidectomie, calculilor biliari cu/fără colecistită sau angiocolită, cifozei (posturală, postiradiere, postlaminectomie), cardiopatiei hipertensive cu/fără insuficiență, calcificării musculare (`Miozita osificanta`), chistului ovarian de dezvoltare, chistului pancreatic congenital, coreei reumatice cu cardită, CID la nou-născut, cardiomiopatiei hipertrofice neobstructive, defectelor de reducere a membrelor (există `Aplazie radiala`, `Aplazie ulnara`, `Absenta de perone`, `Displazie tibiala`, `Amputatie congenitala`), inerției și hipertoniei uterine (`Distocie`).
- **Nu sunt boli anume (G7 / P2):** carențele „alte”/„multiple”/vanadiu, complicațiile anesteziei și ale lăuziei, câștigul ponderal în sarcină, crizele de cianoză, congestia sânului la nou-născut, corpul străin rezidual, compresiunile radiculare asterisc (`G55`), cervicalgia, coma nou-născutului, comprimarea feței, cavitățile craniene, cromozomii markeri, *Clostridium perfringens* ca agent (`B96.7`), localizările tumorale din termenii de includere (cornete, coarda vocală, calicele renal etc.).
- **Variante păstrate separat (G4):** cataracta juvenilă, traumatică, complicată, medicamentoasă și secundară (dicționarul are deja `Cataracta diabetica`), criptococoza diseminată și coccidioidomicoza cutanată (există formele pulmonare/cutanate/diseminate surori), capilarioza hepatică (diferită de cea intestinală), cardiomiopatia toxică (există `Cardiomiopatie alcoolica`), cardiopatia cifoscoliotică (cauză distinctă de `Cord pulmonar`), cardionefropatia hipertensivă (`I13`, distinctă de cardiopatia și nefropatia hipertensivă izolate), ciroza biliară secundară (≠ primitivă), chisturile odontogene (radicular, dentiger, Stafne).
- **Sinonime insuficiente:** criptococoza osoasă, condroliza, chistul vulvar, concrescența dinților, craniul în frunză de trifoi, calcoza oculară, conjunctivita Newcastle.
- **Amânate la altă literă** (`pending_from_C.jsonl`): `Sarcom de parti moi` (`C49`), `Sarcom mastocitar` (`C96.2`), `Stenoza ureterala` (`N13.5`) → S; `Tumora phyllodes` (`D48.6`, „cistosarcom phyllodes”) → T; `Macrosomie fetala` (`P08.0`) → M; `Hipoacuzie indusa de zgomot` (`H83.3`) → H; `Keratochist odontogen` (`K09.0`) → K; `Deficit de transcobalamina II` (`D51.2`) → D; `Feohifomicoza` (`B43.1`–`B43.2`) → F; `Boala Fahr` (`G23.8`) → B. Tetraplegia (`G82`) și gemenii uniți (`Q89.4`) au titlul la T, respectiv G, și rămân pașilor acelor litere.
- **Din `pending_by_letter.jsonl`:** `Coagulopatie` (`D68.9`, generică, distinctă de `Coagulopatie dobandita`) și `Coagulopatie postpartum` (`O72.3`) — re-verificate (G6), adăugate.
- **Amânate de la alte litere, adăugate la unire (coordonator, 8):** `Cardita meningococica` (A39.5; de la B); `Campilobacterioza` (A04.5; de la E); `Calus vicios` (M84.0; de la F); `Ciuma meningeala` (A20.3; de la P); `Ciuma cutanata` (A20.1; de la P); `Circulara de cordon ombilical` (O69.1; de la T); `Chistadenom seros ovarian` (D27; de la T); `Chistadenom mucinos ovarian` (D27; de la T). Verificate față de dicționarul unit al tuturor literelor (G3, G6).

## Adăugate

| Nume canonic | Coduri | Sinonime |
|---|---|---|
| Calcinoza cutanata | L94.2 | calcinosis cutis; calcificare cutanata; calcinoza tegumentara; cutaneous calcinosis; cutaneous calcification; skin calcinosis |
| Calcul uretral | N21.1 | calcul in uretra; litiaza uretrala; uretrolitiaza; urethral calculus; urethral stone; calculus in urethra |
| Calus vicios | M84.0 | fractura rau consolidata; consolidare vicioasa a fracturii; consolidare vicioasa; malunion of fracture; fracture malunion; malunited fracture |
| Campilobacterioza | A04.5 | enterita prin Campylobacter; infectie intestinala cu Campylobacter; enterocolita cu Campylobacter; campylobacteriosis; Campylobacter enteritis; Campylobacter infection |
| Cancer cu sediu primar necunoscut | C80 | cancer cu punct de plecare necunoscut; carcinom cu sediu primar necunoscut; cancer de origine primara necunoscuta; cancer of unknown primary; carcinoma of unknown primary; malignant neoplasm of unknown primary site; occult primary cancer |
| Cancer de buza | C00 | tumora maligna a buzei; cancer labial; carcinom labial; carcinom al buzei; malignant neoplasm of lip; lip cancer; carcinoma of lip |
| Cancer de palat | C05 | tumora maligna a palatului; cancer palatin; carcinom de palat; malignant neoplasm of palate; palate cancer; palatal carcinoma |
| Cancer de ureche medie | C30.1 | tumora maligna a urechii medii; carcinom de ureche medie; carcinom al urechii medii; malignant neoplasm of middle ear; middle ear cancer; middle ear carcinoma |
| Cancer gingival | C03 | tumora maligna a gingiei; cancer de gingie; carcinom gingival; malignant neoplasm of gum; gingival cancer; gingival carcinoma; gum cancer |
| Cancer mediastinal | C38.1, C38.2, C38.3 | tumora maligna a mediastinului; tumora mediastinala maligna; neoplasm mediastinal malign; malignant neoplasm of mediastinum; mediastinal cancer; malignant mediastinal tumor |
| Cancer ocular | C69 | tumora maligna a ochiului si anexelor sale; cancer al ochiului; tumora maligna oculara; malignant neoplasm of eye and adnexa; eye cancer; ocular cancer; ocular malignancy |
| Cancer osos | C40, C41 | tumora maligna a oaselor si cartilagiilor articulare; cancer al oaselor; cancer osos primar; neoplasm osos malign; malignant neoplasm of bone and articular cartilage; bone cancer; primary bone cancer; malignant bone tumor |
| Cancer peritoneal primar | C48.1, C48.2 | tumora maligna a peritoneului; carcinom peritoneal primar; carcinom seros peritoneal primar; malignant neoplasm of peritoneum; primary peritoneal carcinoma; primary peritoneal cancer |
| Cancer scrotal | C63.2 | tumora maligna a scrotului; carcinom scrotal; cancerul cosarilor; malignant neoplasm of scrotum; scrotal cancer; scrotal carcinoma; chimney sweeps' cancer |
| Cancer suprarenal | C74 | tumora maligna a glandei suprarenale; cancer de glanda suprarenala; neoplasm suprarenal malign; malignant neoplasm of adrenal gland; adrenal cancer; adrenal gland cancer; malignant adrenal tumor |
| Cancer traheal | C33 | tumora maligna a traheei; cancer de trahee; carcinom traheal; malignant neoplasm of trachea; tracheal cancer; tracheal carcinoma |
| Cancer uterin | C54, C55 | tumora maligna a corpului uterin; cancer de corp uterin; cancer de uter; neoplasm uterin malign; malignant neoplasm of corpus uteri; uterine cancer; cancer of the uterus; uterine corpus cancer |
| Canitie prematura | L67.1 | incaruntire prematura; albirea prematura a parului; par gri prematur; premature canities; premature graying of hair; early graying of hair |
| Capilarioza hepatica | B83.8 | capillariaza hepatica; infectie cu Capillaria hepatica; infectie cu Calodium hepaticum; hepatic capillariasis; Capillaria hepatica infection; Calodium hepaticum infection |
| Carcinom urotelial in situ | D09.0 | carcinom in situ al vezicii urinare; carcinom in situ vezical; carcinom urotelial plan in situ; carcinoma in situ of bladder; urothelial carcinoma in situ; bladder carcinoma in situ |
| Cardiomiopatie toxica | I42.7 | cardiomiopatie medicamentoasa; cardiomiopatie indusa medicamentos; cardiomiopatie la antracicline; toxic cardiomyopathy; drug-induced cardiomyopathy; cardiomyopathy due to drug and external agent |
| Cardionefropatie hipertensiva | I13 | cardio-nefropatie hipertensiva; boala cardiaca si renala hipertensiva; boala hipertensiva cardiorenala; hypertensive heart and chronic kidney disease; hypertensive heart and kidney disease; hypertensive cardiorenal disease |
| Cardiopatie cifoscoliotica | I27.1 | cord pulmonar cifoscoliotic; boala cardiaca cifoscoliotica; cord pulmonar cronic in cifoscolioza; kyphoscoliotic heart disease; kyphoscoliotic cor pulmonale; cor pulmonale due to kyphoscoliosis |
| Cardita meningococica | A39.5 | boala de inima meningococica; afectare cardiaca meningococica; miocardita meningococica; pericardita meningococica; meningococcal heart disease; meningococcal carditis; meningococcal myocarditis; meningococcal pericarditis |
| Caruncul uretral | N36.2 | caruncula uretrala; carunculul uretrei; caruncul meatal; urethral caruncle; caruncle of urethra; meatal caruncle |
| Cataracta complicata | H26.2 | cataracta secundara afectiunilor oculare; cataracta in iridociclita cronica; cataracta uveitica; complicated cataract; cataract secondary to ocular disease; uveitic cataract |
| Cataracta juvenila | H26.0 | cataracta infantila juvenila si presenila; cataracta infantila; cataracta presenila; infantile and juvenile cataract; juvenile cataract; infantile cataract; presenile cataract |
| Cataracta medicamentoasa | H26.3 | cataracta provocata de medicamente; cataracta cortizonica; cataracta indusa de corticosteroizi; drug-induced cataract; steroid-induced cataract; corticosteroid-induced cataract |
| Cataracta secundara | H26.4 | opacifierea capsulei posterioare; cataracta secundara postoperatorie; inel Soemmerring; secondary cataract; posterior capsule opacification; after-cataract |
| Cataracta traumatica | H26.1 | cataracta posttraumatica; cataracta prin traumatism ocular; cataracta contuziva; traumatic cataract; post-traumatic cataract; contusion cataract |
| Cecitate | H54 | orbire; pierderea vederii; amauroza; blindness; vision loss; amaurosis |
| Cefalee posttraumatica | G44.3 | cefalee cronica post-traumatica; cefalee dupa traumatism cranian; durere de cap posttraumatica; post-traumatic headache; chronic post-traumatic headache; headache attributed to traumatic injury to the head |
| Celulita eozinofila | L98.3 | sindrom Wells; celulita eozinofilica; dermatita granulomatoasa eozinofilica recidivanta; eosinophilic cellulitis; Wells syndrome; recurrent granulomatous dermatitis with eosinophilia |
| Cenuroza | B71.8 | coenuroza; infectie cu Taenia multiceps; infestare cu Coenurus cerebralis; coenurosis; coenuriasis; Taenia multiceps infection |
| Cheratopatie buloasa | H18.1 | keratopatie buloasa; cheratopatie buloasa pseudofaca; edem cornean bulos; bullous keratopathy; pseudophakic bullous keratopathy; bullous corneal edema |
| Chilocel | I89.8, N50.8 | chilocel al tunicii vaginale; hidrocel chilos; colectie chiloasa scrotala; chylocele; chylous hydrocele; chylocele of tunica vaginalis |
| Chist dentiger | K09.0 | chist dentigen; chist folicular dentar; chist pericoronar; dentigerous cyst; follicular odontogenic cyst; dentigerous follicular cyst |
| Chist mamar | N60.0 | chist solitar al sanului; chist al sanului; chist mamar simplu; solitary cyst of breast; breast cyst; simple breast cyst |
| Chist mezenteric | Q45.84 | chist al mezenterului; chist mezenteric congenital; chist chilos mezenteric; mesenteric cyst; cyst of mesentery; chylous mesenteric cyst |
| Chist radicular | K04.8 | chist periapical; chist radiculodentar; chist apical; radicular cyst; periapical cyst; apical periodontal cyst |
| Chist Stafne | K10.0 | chist latent osos al maxilarului; defect osos Stafne; cavitate osoasa statica a mandibulei; Stafne bone cyst; Stafne defect; static bone cavity; lingual mandibular bone depression |
| Chistadenom mucinos ovarian | D27 | chistadenom mucinos; cistadenom mucinos ovarian; tumora mucinoasa benigna ovariana; mucinous cystadenoma; ovarian mucinous cystadenoma; benign mucinous ovarian tumor |
| Chistadenom seros ovarian | D27 | chistadenom seros; cistadenom seros ovarian; tumora seroasa benigna ovariana; serous cystadenoma; ovarian serous cystadenoma; benign serous ovarian tumor |
| Circulara de cordon ombilical | O69.1 | circulara de cordon; cordon ombilical in jurul gatului; circulara cervicala de cordon; nuchal cord; cord around neck; nuchal umbilical cord |
| Ciroza biliara secundara | K74.4 | ciroza biliara obstructiva; ciroza colestatica secundara; ciroza prin obstructie biliara cronica; secondary biliary cirrhosis; obstructive biliary cirrhosis; biliary cirrhosis due to bile duct obstruction |
| Ciuma cutanata | A20.1 | pesta cutanata; ciuma celulocutanata; pesta celulocutanata; cellulocutaneous plague; cutaneous plague; skin plague |
| Ciuma meningeala | A20.3 | pesta meningeala; meningita pestoasa; meningita cu Yersinia pestis; plague meningitis; meningeal plague; Yersinia pestis meningitis |
| Coagulopatie | D68.9 | defect de coagulare; tulburare a coagularii sangelui; anomalie de coagulare; coagulopathy; coagulation defect; blood clotting disorder |
| Coagulopatie postpartum | O72.3 | tulburare de coagulare postpartum; afibrinogenemie postpartum; coagulopatie obstetricala; postpartum coagulation defect; postpartum coagulopathy; obstetric coagulopathy |
| Coccidioidomicoza cutanata | B38.3 | coccidioidomikoza cutanata; coccidioidomicoza pielii; coccidioidomicoza cutanata primara; cutaneous coccidioidomycosis; primary cutaneous coccidioidomycosis; coccidioidomycosis of skin |
| Coccigodinie | M53.3 | coccidinie; durere coccigiana; sindrom coccigian dureros; coccygodynia; coccydynia; tailbone pain |
| Colagenoza perforanta reactiva | L87.1 | colagenoza perforanta reactiva dobandita; dermatoza perforanta reactiva; dermatoza perforanta dobandita; reactive perforating collagenosis; acquired reactive perforating collagenosis; acquired perforating dermatosis |
| Colesteatom de conduct auditiv extern | H60.4 | colesteatomul urechii externe; colesteatom al conductului auditiv extern; colesteatom de canal auditiv extern; cholesteatoma of external ear; external auditory canal cholesteatoma; external ear canal cholesteatoma |
| Colesteroloza veziculara | K82.4 | colesteroloza vezicii biliare; vezica biliara in forma de fraga; colesteroza veziculara; cholesterolosis of gallbladder; strawberry gallbladder; gallbladder cholesterolosis |
| Compresie cerebrala | G93.5 | compresiunea creierului; hernie cerebrala; angajare cerebrala; compression of brain; brain herniation; cerebral herniation; brain compression |
| Condrodermatita nodulara a helixului | H61.0 | condrodermatita nodulara cronica a helixului; boala Winkler; nodul dureros al helixului; chondrodermatitis nodularis helicis; chondrodermatitis nodularis chronica helicis; Winkler disease |
| Condrodisplazie punctata | Q77.3 | condrodistrofie calcifianta congenitala; sindrom Conradi-Hunermann; boala Conradi; chondrodysplasia punctata; Conradi-Hunermann syndrome; chondrodystrophia calcificans congenita; stippled epiphyses |
| Conjunctivita hemoragica acuta | B30.3 | conjunctivita hemoragica acuta epidemica; conjunctivita hemoragica epidemica; conjunctivita enterovirala; acute hemorrhagic conjunctivitis; acute epidemic hemorrhagic conjunctivitis; epidemic hemorrhagic conjunctivitis; Apollo disease |
| Convulsii disociative | F44.5 | crize psihogene neepileptice; crize disociative; pseudocrize epileptice; dissociative convulsions; psychogenic nonepileptic seizures; conversion disorder with seizures; pseudoseizures |
| Cord triatrial | Q24.2 | cor triatriatum; cord triatriat; inima triatriala; triatrial heart; cor triatriatum sinister; divided left atrium |
| Coreea medicamentoasa | G25.4 | coreea provocata medicamentos; coree indusa medicamentos; coree iatrogena; drug-induced chorea; medication-induced chorea; iatrogenic chorea |
| Corn cutanat | L85.8 | cornu cutaneum; excrescenta cornoasa cutanata; proliferare cornoasa a pielii; cutaneous horn; keratin horn; cutaneous keratin horn |
| Coroideremie | H31.2 | choroideremie; distrofie tapetocoroidiana progresiva; degenerescenta tapetocoroidiana; choroideremia; progressive tapetochoroidal dystrophy; tapetochoroidal dystrophy |
| Corp liber intraarticular | M24.0, M23.4 | corp liber in articulatie; corp liber articular; soarece articular; loose body in joint; intra-articular loose body; joint mouse |
| Craniofaringiom | D44.4, D35.3 | tumora de punga Rathke; tumora a canalului craniofaringian; adamantinom hipofizar; tumora Erdheim; craniopharyngioma; Rathke pouch tumor; craniopharyngeal duct tumor; Erdheim tumor |
| Craniorahischisis | Q00.1 | cranio-rahischisis; craniorahischisis totala; disrafism craniospinal total; craniorachischisis; craniorachischisis totalis; total craniospinal dysraphism |
| Criptococoza diseminata | B45.7 | criptococcoza diseminata; criptococoza generalizata; criptococoza sistemica; disseminated cryptococcosis; generalized cryptococcosis; systemic cryptococcosis |

## Decise manual, neadăugate

Titluri `nou` / `posibil` care nu au devenit afecțiuni noi: există sub alt nume, sunt variante ale unei categorii (D5), categorii generice sau nu sunt boli (G7). Coloana „Apropiat” e sugestia automată.

| Cod | Titlu CIM-10 | Apropiat |
|---|---|---|
| A06.2 | Colita amibiana nedizenterica | Colita amibiana / Dizenterie amibiana |
| B30.1 | Conjunctivita prin adenovirus | Conjunctivita virala / Febra faringoconjunctivala / Conjunctivita foliculara |
| B33.2 | Cardita virala | Miocardita / Artrita virala / Faringita virala |
| B37.2 | Candidiaza pielii si unghiilor |  |
| B37.3 | Candidiaza vulvei si vaginului(M77.1*) |  |
| B37.4 | Candidiaza altor localizari uro-genitale |  |
| B37.8 | Candidiaza cu alte localizari |  |
| B37.88 | Candidiaza cu alte localizari |  |
| B43 | Chromomicoza si abcesul phaeomicotic |  |
| B43.0 | Chromomicoza cutanata | Cromoblastomikoza / Dermatita de staza |
| B43.9 | Chromomicoza, nespecificata | Cromoblastomikoza |
| B45.1 | Criptococcoza cerebrala | Chist hidatic cerebral / Neurocisticercoza / Meningita criptocococica |
| B45.3 | Criptococcoza osoasa |  |
| B69.1 | Cysticercoza ochiului |  |
| B69.8 | Cysticercoza, alte localizari |  |
| B96.7 | Clostridium perfringens [C. perfringens], cauza unor boli clasate la alte capitole |  |
| C22.0 | Carcinomul celulei hepatice | Cancer de ficat / Carcinom bazocelular / Adenom hepatic |
| D00 | Carcinom in situ al cavitatii bucale, esofagului si stomacului | Carcinom in situ |
| D01 | Carcinom in situ al altor organe digestive si nespecificate | Carcinom in situ |
| D02 | Carcinom in situ al urechii mijlocii si sistemului respirator | Carcinom in situ |
| D04 | Carcinom in situ al pielii | Carcinom in situ / Carcinom in situ mamar |
| D05.0 | Carcinom lobular in situ al sanului | Carcinom in situ / Carcinom in situ mamar / Carcinom mamar lobular in situ |
| D05.1 | Carcinom intracanalicular in situ al sanului | Carcinom in situ / Carcinom in situ mamar |
| D06 | Carcinom in situ al colului uterin | Cancer de col uterin / Carcinom in situ |
| D07 | Carcinom in situ al altor organe genitale si nespecificate | Carcinom in situ |
| D09 | Carcinom in situ cu alte localizari si nespecificate | Carcinom in situ |
| D09.7 | Carcinom in situ cu alte localizari specificate | Carcinom in situ |
| D51.2 | Carenta de transcobalamina II |  |
| D66 | Carenta ereditara prin lipsa factorului VIII |  |
| D68.4 | Carenta dobandita a factorului de coagulare | Coagulopatie dobandita |
| D73.4 | Chistul splinei | Chist splenic |
| E05.5 | Criza acuta tireotoxica | Furtuna tiroidiana |
| E53.8 | Carenta de alte vitamine din grupa B | Deficit de vitamina A |
| E56.8 | Carenta de alte vitamine | Deficit de vitamina A / Boala hemoragica a nou-nascutului / Deficit de acid folic / Deficit de niacina / Deficit de piridoxina / Deficit de riboflavina |
| E58 | Carenta alimentara de calciu | Deficit de calciu |
| E61 | Carenta de alte elemente nutritionale |  |
| E61.6 | Carenta de vanadiu | Deficit de sodiu / Deficit de vitamina D / Deficit de magneziu |
| E61.7 | Carenta mai multor elemente nutritionale |  |
| E61.8 | Carenta de alte elemente nutritionale specificate |  |
| E61.9 | Carenta de element nutritional, nespecificata |  |
| E63.9 | Carenta nutritionala, nespecificata | Malnutritie |
| G44.1 | Cefalee vasculara, neclasificata altundeva |  |
| G44.4 | Cefalee provocata medicamentos, neclasificata altundeva |  |
| G55.0 | Compresiunea radacinilor si plexurilor nervoase in bolile tumorale (C00-D48†) |  |
| G55.1 | Compresiunea radacinilor si plexurilor nervoase in leziunile discurilor intevertebrale (M50-M51†) |  |
| G55.2 | Compresiunea radacinilor si plexurilor nervoase in spondiloza (M47.- †) |  |
| G55.3 | Compresiunea radacinilor si plexurilor nervoase in alte dorsopatii (M45-M46†; |  |
| G93.0 | Chist cerebral | Chist hidatic cerebral |
| G95.2 | Compresiune maduvei, nespecificata | Compresie medulara |
| H10.0 | Conjuctivita muco-purulenta | Conjunctivita bacteriana |
| H10.1 | Conjuctivita atopica acuta | Conjunctivita virala |
| H10.3 | Conjuctivite acute, nespecificate |  |
| H10.4 | Conjuctivita cronica | Conjunctivita gonococica / Blefaroconjunctivita |
| H10.9 | Conjuctivita, nespecificata | Conjunctivita |
| H17 | Cicatrice si opacitati corneene |  |
| H17.9 | Cicatrice si opacitate corneeana, nespecificate |  |
| H21.3 | Chistul irisului, corpilor ciliari si a camerei anterioare a ochiului | Chist irian |
| H25.0 | Cataracta senila incipienta | Cataracta |
| H25.1 | Cataracta senila nucleara | Cataracta |
| H25.2 | Cataracta senila de tip Morgagnian | Cataracta |
| H28.1 | Cataracta in bolile endocrine, de nutritie si metabolism | Artropatia hiperparatiroidiana |
| H30.1 | Chorioretinita diseminata |  |
| H30.2 | Ciclita posterioara |  |
| H31.0 | Cicatrice chorioretiniana | Cicatrice corioretiniana / Atrofie corioretiniana |
| H54.0 | Cetitatea ambilor ochi |  |
| H54.1 | Cecitatea unui ochi, scaderea vederii celuilalt ochi |  |
| H54.4 | Cecitatea unui ochi |  |
| H60.1 | Celulita flegmonoasa a urechii externe |  |
| H71 | Colesteatomul urechii medii | Colesteatom |
| H83.3 | Consecintele zgomotului asupra urechii interne |  |
| H95.0 | Colesteatom recidivant dupa mastoidectomie |  |
| I02.0 | Coreea reumatismala cu complicatie cardiaca |  |
| I02.9 | Coreea reumatismala fara complicatie cardiaca | Coreea Sydenham |
| I09.9 | Cardiopatia reumatismala, nespecificata | Miocardita reumatica / Cardiopatie reumatica / Pericardita reumatica |
| I11.0 | Cardiopatia hipertensiva cu insuficienta (congestiva) a inimii | Cardiopatie hipertensiva |
| I11.9 | Cardiopatia hipertensiva fara insuficienta (congestiva) a inimii | Cardiopatie hipertensiva |
| I13.0 | Cardio-nefropatia hipertensiva cu insuficienta (congestiva) a inimii | Nefropatie hipertensiva |
| I13.1 | Cardio-nefropatia hipertensiva cu insuficienta renala | Insuficienta renala / Nefropatie hipertensiva |
| I13.2 | Cardio-nefropatia hipertensiva cu insuficienta cardiaca (congestiva) si renala | Cardiopatie hipertensiva / Insuficienta cardiaca / Insuficienta renala / Nefropatie hipertensiva |
| I25.1 | Cardiopatie aterosclerotica |  |
| I25.10 | Cardiopatia aterosclerotica a unor vase nespecificate |  |
| I25.11 | Cardiopatia aterosclerotica a arterei coronariene native |  |
| I25.12 | Cardiopatia aterosclerotica a unei grefe de bypass autolog |  |
| I25.13 | Cardiopatia aterosclerotica a unei grefe de bypass nonautolog |  |
| I43.0 | Cardiomiopatia in boli infectioase si parazitare clasificata altundeva |  |
| I43.2 | Cardiomiopatia in boli de nutritie |  |
| I51 | Complicatii si cardiopatii incorect descrise |  |
| I87.1 | Compresiunea venei |  |
| J34.1 | Chist si mucocel al nasului si sinusului nazal | Mucocel sinusal |
| J66.2 | Cannabinoza |  |
| K02.0 | Caria limitata la smalt | Vitiligo |
| K02.1 | Caria dentinei |  |
| K02.2 | Caria cimentului |  |
| K02.3 | Caria dentara stabilizata | Carie dentara |
| K09 | Chisturile regiunii bucale, neclasificate altundeva |  |
| K09.1 | Chist al regiunii bucale nelegat de dezvoltarea dentara |  |
| K09.9 | Chist al regiunii bucale, nespecificat |  |
| K38.1 | Concretiuni apendiculare |  |
| K74.5 | Ciroza biliara, nespecificata | Ciroza biliara primitiva |
| K76.1 | Congestia pasiva cronica a ficatului |  |
| K80.0 | Calcul al vezicii biliare cu colecistita acuta |  |
| K80.1 | Calcul al vezicii biliare cu o alta forma de colecistita | Colecistita acuta calculoasa / Colecistita acuta alitiazica |
| K80.2 | Calcul al vezicii biliare fara colecistita |  |
| K80.3 | Calculul canalelor biliare cu angiocolita | Litiaza biliara |
| K80.4 | Calculul canalelor biliare cu colecistita | Colecistita acuta alitiazica / Colecistita acuta calculoasa / Litiaza biliara |
| K80.5 | Calculul canalelor biliare fara angiocolita si colecistita | Colecistita acuta alitiazica / Colecistita acuta calculoasa / Litiaza biliara |
| K83.5 | Chistul biliar | Chist coledocian / Chist de coledoc / Chist hepatic / Milium / Chist trichilemal |
| K86.2 | Chistul pancreasului | Chist pancreatic |
| L03.01 | Celulita degetului mainii |  |
| L03.02 | Celulita degetului piciorului |  |
| L03.1 | Celulita altor parti ale membrelor |  |
| L03.10 | Celulita membrului superior |  |
| L03.11 | Celulita membrului inferior |  |
| L03.2 | Celulita fetei |  |
| L03.3 | Celulita trunchiului | Dehiscence de perete abdominal / Hernie inghinala / Hernie lombara / Hernie Richter |
| L03.8 | Celulita cu alte localizari |  |
| L05.0 | Chist pilonidal cu abces | Abces pilonidal / Sinus pilonidal |
| L11.0 | Cheratoza foliculara dobandita | Cheratoza foliculara |
| L72 | Chisturi foliculare ale pielii si tesutului celular subcutanat |  |
| L72.0 | Chist epidermic | Chist sebaceu / Spermatocel |
| L72.9 | Chist folicular al pielii si tesutului celular subcutanat, nespecificat | Chist trichilemal |
| L90.5 | Cicatrice si fibroze cutanate | Fibroza cutanata |
| M11.1 | Condrocalcinoza familiala |  |
| M16.0 | Coxartroza primara, bilaterala |  |
| M16.2 | Coxartroza de origine displazica, bilaterala | Coxartroza pe displazie |
| M16.4 | Coxartroza post-traumatica bilaterala |  |
| M24.5 | Contractura articulatiei | Contractura articulara |
| M40 | Cifoza si lordoza |  |
| M40.0 | Cifoza posturala | Cifoza |
| M54.2 | Cervicalgia | Eroziune de col uterin |
| M61 | Calcificarea si osificarea muschilor |  |
| M61.2 | Calcificare si osificare paralitica a unui muschi | Miozita osificanta |
| M61.3 | Calcificare si osificare a muschilor asociata cu arsuri | Miozita osificanta |
| M61.9 | Calcificari si osificari ale unui muschi, nespecificat |  |
| M71.2 | Chist sinovial al spatiului popliteu [Baker] | Chist popliteu / Chist sinovial |
| M79.5 | Corp strain rezidual in tesutul moale |  |
| M94.3 | Condroliza | Pseudoguta |
| M96.2 | Cifoza dupa iradiere |  |
| M96.3 | Cifoza dupa laminectomie |  |
| N13.5 | Cudura si strictura ureterala fara hidronefroza |  |
| N20 | Calculii rinichiului si ureterului |  |
| N23 | Colica nefritica nespecificata | Colica renala |
| N28.1 | Chistul rinichiului, dobandit |  |
| N30.4 | Cistita datorita iradierii |  |
| N33.0 | Cistita tuberculoasa (A18.1†) | Rinita tuberculoasa / Peritonita tuberculoasa / Tuberculoza epididimara |
| N42.0 | Calculul prostatei | Calculi prostatici / Atrofie de prostata |
| N42.1 | Congestia si hemoragia prostatei |  |
| N75.0 | Chistul glandei Bartholin | Chist de glanda Bartholin / Abces de glanda Bartholin |
| N83.0 | Chist folicular al ovarului | Chist trichilemal / Chist folicular ovarian |
| N90.7 | Chistul vulvei |  |
| N98 | Complicatii asociate cu fertilizarea artificiala |  |
| N98.2 | Complicatii privind incercarea de implantare a unui ou fecundat in urma fertilizarii in vitro |  |
| N98.3 | Complicatii ale incercarii de implantare a unui embrion in transferul de embrion |  |
| O08 | Complicatii urmand avortului si sarcinii ectopice si molare |  |
| O10.1 | Cardiopatie hipertensiva pre-existenta complicand sarcina, nasterea si lauzia | Cardiopatie hipertensiva |
| O10.3 | Cardio-nefropatia hipertensiva pre-existenta complicand sarcina, nasterea si lauzia | Nefropatie hipertensiva |
| O22 | Complicatii venoase in sarcina |  |
| O26.0 | Castig excesiv in greutate dobandit in sarcina |  |
| O26.1 | Castig scazut in greutate dobandit in sarcina |  |
| O29 | Complicatii ale anesteziei in timpul sarcinii |  |
| O29.0 | Complicatiile pulmonare ale unei anestezii in timpul sarcinii | Pneumonie prin aspiratie |
| O29.1 | Complicatiile cardiace ale unei anestezii in timpul sarcinii |  |
| O29.2 | Complicatii ale sistemului nervos central datorite anesteziei in timpul sarcinii |  |
| O29.4 | Cefalee provocata de o rahianestezie si o anestezie epidurala in timpul sarcinii |  |
| O29.9 | Complicatiile anesteziei in timpul sarcinii, nespecificate |  |
| O31 | Complicatii specifice sarcinii multiple |  |
| O31.1 | Continuarea sarcinii dupa avortul unuia sau mai multor feti |  |
| O31.2 | Continuarea sarcinii dupa decesul intrauterin al unuia sau mai multor feti |  |
| O62.0 | Contractia initiala insuficienta |  |
| O62.4 | Contractii uterine hipertonice, neacordate si prelungite |  |
| O74 | Complicatiile anesteziei in timpul travaliului si nasterii |  |
| O74.2 | Complicatii cardiace datorite unei anestezii in timpul travaliului si nasterii |  |
| O74.3 | Complicatii ale sistemului nervos central datorita unei anesteziei in timpul travaliului si nasterii |  |
| O74.5 | Cefalee provocata de rahianestezie si o anestezie epidurala in timpul travaliului si nasterii |  |
| O74.9 | Complicatii ale unei anestezii in timpul travaliului si nasterii, nespecificate |  |
| O75.9 | Complicatiile travaliului si nasterii, nespecificate |  |
| O87 | Complicatii venoase in timpul lauziei |  |
| O89 | Complicatii ale anesteziei in timpul lauziei |  |
| O89.0 | Complicatii pulmonare ale anesteziei in timpul lauziei |  |
| O89.1 | Complicatiile cardiace datorita unei anestezii in timpul lauziei |  |
| O89.2 | Complicatiile sistemului nervos central datorita unei anestezii in timpul lauziei |  |
| O89.4 | Cefalee provocata de o rahianestezie si o anestezie epidurala in timpul lauziei |  |
| O89.9 | Complicatiile unei anestezii in timpul lauziei, nespecificate |  |
| O90 | Complicatii ale lauziei, neclasificate altundeva |  |
| O90.9 | Complicatia puerperala, nespecificata | Mastita |
| P05 | Crestere lenta fetala si malnutritia fatului |  |
| P05.9 | Cresterea lenta a fatului, nespecificata |  |
| P08.0 | Copil exceptional de mare |  |
| P12.0 | Cefalohematom datorita traumatismului la nastere | Traumatism obstetric |
| P28.2 | Crize de cianoza a nou-nascutului |  |
| P37.51 | Candidoza neonatala gastrointestinala sau actuala | Candidoza neonatala |
| P37.52 | Candidoza neonatala invaziva | Candidoza diseminata / Candidoza neonatala / Sepsis neonatal |
| P39.1 | Conjunctivita si dacriocistita neonatala | Conjunctivita neonatala / Conjunctivita de includere |
| P60 | Coagularea intravasculara diseminata la fat si nou-nascut |  |
| P83.4 | Congestia sanului la nou-nascut |  |
| P90 | Convulsii ale nou-nascutului | Convulsii neonatale |
| P91.1 | Chist periventricular dobandit al nou-nascutului |  |
| P91.5 | Coma nou-nascutului | Conjunctivita neonatala / Acnee neonatala / Scleroedem neonatal |
| P96.5 | Complicatii ale procedurilor intrauterine, neclasificate altundeva |  |
| Q04.6 | Chist cerebral congenital | Chist pleural / Schizencefalie / Anevrism cerebral congenital |
| Q04.61 | Chist cerebral congenital unic |  |
| Q04.62 | Chisturi cerebrale congenitale multiple |  |
| Q12.2 | Coloboma cristalinului |  |
| Q13.0 | Coloboma irisului | Colobom ocular |
| Q20.3 | Comunicatie ventriculo-auriculara discordanta |  |
| Q20.5 | Comunicatia atrioventriculara discordanta | Transpozitie corectata de mari vase |
| Q25.1 | Coarctatia istmului aortic | Coarctatie de aorta |
| Q26.4 | Conexiune venoasa pulmonara aberanta, nespecificata | Drenaj venos pulmonar anormal total |
| Q26.5 | Conexiune venoasa portala aberanta |  |
| Q34.1 | Chist congenital al mediastinului |  |
| Q45.2 | Chist pancreatic congenital | Chist pancreatic / Chist splenic / Chist pericardic |
| Q50.1 | Chist ovarian in dezvoltare | Chist ovarian |
| Q50.10 | Chist ovarian in dezvoltare, nespecificat | Chist ovarian |
| Q50.11 | Chist ovarian in dezvoltare, unic | Chist ovarian |
| Q50.12 | Chist ovarian in dezvoltare, multiplu | Chist ovarian |
| Q50.4 | Chist embrionic al trompei Fallope | Chist irian |
| Q50.5 | Chist embrionic al ligamentului larg |  |
| Q51.6 | Chist embrionic al cervixului |  |
| Q54.4 | Chorga congenital | Cloaca persistenta / Cifoza congenitala |
| Q61.0 | Chist renal unic congenital | Chist splenic / Chist bronsogenic |
| Q64.41 | Chist al uracei | Persistenta de urac / Chist pleural |
| Q67.1 | Comprimarea fetei |  |
| Q67.41 | Cavitati in craniu |  |
| Q67.52 | Curba posturala congenitala a sirei spinarii |  |
| Q68.5 | Curbarea congenitala a oaselor lungi ale piciorului, nespecificata |  |
| Q71 | Corectarea defectelor membrelor superioare |  |
| Q71.4 | Corectarea longitudinala a defectelor radiusului | Aplazie radiala / Sindrom TAR / Arhinie / Agenezie de penis |
| Q71.5 | Corectarea longitudinala a defectelor cubitusului | Aplazie ulnara / Agenezie uterina |
| Q71.9 | Corectarea de defecte a membrului(lor) superior(oare), nespecificata |  |
| Q72 | Corectarea defectelor membrelor inferioare |  |
| Q72.4 | Corectarea longitudinala a defectelor femurului |  |
| Q72.5 | Corectarea longitudinala a defectelor tibiei | Displazie tibiala |
| Q72.6 | Corectarea longitudinala a defectelor peroneului | Absenta de perone / Agenezie de penis / Agenezie uterina / Atelie |
| Q72.9 | Corectarea defectelor la membrul inferior, nespecificata | Amputatie congenitala |
| Q73 | Corectarea defectelor unui membru nespecificat |  |
| Q73.80 | Corectarea defectelor unui membru(e) nespecificat(e), nespecificata |  |
| Q74.83 | Cresterea congenitala sub nivelul normal a membrului(lor) |  |
| Q75.02 | Craniosinostoza sagitala | Scafocefalie |
| Q75.06 | Craniu sub forma de frunza de trifoi | Coagulare intravasculara diseminata |
| Q76.63 | Coasta accesorie | Sindrom de coasta cervicala |
| Q77.82 | Condroplazia metafizara |  |
| Q89.23 | Chist gloso-tiroid persistent |  |
| Q89.24 | Chist gloso-tiroid |  |
| Q89.42 | Craniopagus |  |
| Q92.6 | Cromozomi extra markeri |  |
| Q93.2 | Cromozomi replasati cu inel sau dicentrici | Cromozom inel |
| Q99.0 | Chimera 46, XX/46, XY |  |
| Q99.2 | Cromozom X fragil | Sindrom fragile X |

## Existente (potrivire automată)

Candidații pentru sinonime adăugate ulterior (D6).

| Cod | Titlu CIM-10 | Afecțiune | Potrivire |
|---|---|---|---|
| A07.2 | Cryptosporidioza | Criptosporidioza | exact |
| A74.0 | Conjunctivita prin Chlamydia | Conjunctivita de includere | exact |
| A87.2 | Choriomeningita limfocitara | Corioencefalita limfocitara | exact |
| B30 | Conjunctivita virala | Conjunctivita virala | exact |
| B37 | Candidiaza | Candidoza | exact |
| B37.1 | Candidiaza pulmonara | Candidoza pulmonara | exact |
| B37.9 | Candidiaza, nespecificată | Candidoza orala | terminatii |
| B38 | Coccidioidomicoza | Coccidioidomikoza | exact |
| B38.0 | Coccidioidomicoza pulmonara acuta | Coccidioidomicoza pulmonara | temporal (G1) |
| B38.1 | Coccidioidomicoza pulmonara cronica | Coccidioidomicoza pulmonara | temporal (G1) |
| B38.2 | Coccidioidomicoza pulmonara, nespecificata | Coccidioidomicoza pulmonara | exact |
| B38.7 | Coccidioidomicoza diseminata | Coccidioidomikoza diseminata | exact |
| B45 | Criptococcoza | Criptococoza | exact |
| B45.0 | Criptococcoza pulmonara | Criptococoza pulmonara | exact |
| B45.2 | Criptococcoza cutanata | Criptococoza cutanata | exact |
| B66.1 | Clonorchiaza | Clonorhoza | exact |
| B69 | Cysticercoza | Cisticercoza | exact |
| B69.0 | Cysticercoza sistemului nervos central | Neurocisticercoza | exact |
| B81.1 | Capillariaza intestinala | Capilarioza | exact |
| C22.1 | Carcinomul canalului biliar intrahepatic | Colangiocarcinom | terminatii |
| D05 | Carcinom in situ al sanului | Carcinom in situ mamar | exact |
| D09.9 | Carcinom in situ, nespecificat | Carcinom in situ | exact |
| D65 | Coagularea intravasculara diseminata (sindromul de defibrinare) | Coagulare intravasculara diseminata | terminatii |
| D67 | Carenta ereditara prin lipsa factorului IX | Hemofilie B | exact |
| D68.1 | Carenta ereditara prin lipsa factorului XI | Hemofilie C | terminatii |
| D68.2 | Carenta ereditara prin lipsa altor factori de coagulare | Afibrinogenemie | terminatii |
| D89.1 | Crioglobulinemia | Crioglobulinemie | terminatii |
| E03.5 | Coma mixedematoasa | Coma mixedematoasa | exact |
| E15 | Coma hipoglicemica nondiabetica | Coma hipoglicemica | exact |
| E27.2 | Criza addisoniana | Insuficienta suprarenala acuta | exact |
| E51 | Carenta in tiamina | Deficit de tiamina | exact |
| E52 | Carenta in acid nicotinic (pelagra) | Pelagra | exact |
| E53.0 | Carenta in riboflavine | Deficit de riboflavina | exact |
| E53.1 | Carenta in piridoxina | Deficit de piridoxina | exact |
| E54 | Carenta de acid ascorbic | Deficit de vitamina C | exact |
| E55 | Carenta de vitamina D | Deficit de vitamina D | exact |
| E56.0 | Carenta de vitamina E | Deficit de vitamina E | exact |
| E56.1 | Carenta de vitamina K | Deficit de vitamina K | exact |
| E59 | Carenta alimentara de seleniu | Boala Keshan | exact |
| E60 | Carenta de zinc | Deficit de zinc | exact |
| E61.0 | Carenta de cupru | Deficit de cupru | exact |
| E61.1 | Carenta de fier | Deficit de fier | exact |
| E61.2 | Carenta de magneziu | Deficit de magneziu | exact |
| E61.3 | Carenta de mangan | Deficit de mangan | exact |
| E61.4 | Carenta de crom | Deficit de crom | exact |
| E61.5 | Carenta de molibden | Deficit de molibden | exact |
| E63.0 | Carenta de acizi grasi esentiali [EFA] | Deficit de acizi grasi esentiali | exact |
| F34.0 | Ciclotimie | Ciclotimie | exact |
| F51.5 | Cosmaruri | Cosmar recurent | exact |
| G44.2 | Cefalee de tensiune | Durere de cap | exact |
| G56.4 | Cauzalgia | Sindrom de durere regionala complexa | terminatii |
| H00.1 | Chalazion | Chalazion | exact |
| H10 | Conjunctivita | Conjunctivita | exact |
| H11.2 | Cicatrice conjuctivale | Simblefaron | exact |
| H25 | Cataracta senila | Cataracta | exact |
| H26.9 | Cataracta, nespecificata | Cataracta | exact |
| H30.0 | Chorioretinita focala | Chorioretinita | exact |
| H30.9 | Chorioretinita, nespecificata | Chorioretinita | exact |
| H53.6 | Cecitate nocturna | Nictalopie | exact |
| I02 | Coreea reumatica | Coreea Sydenham | exact |
| I11 | Cardiopatia hipertensiva | Cardiopatie hipertensiva | terminatii |
| I24.9 | Cardiopatia ischemica acuta, nespecificata | Boala coronariana | temporal (G1) |
| I25 | Cardiopatia ischemica cronica | Ischemie miocardica cronica | terminatii |
| I25.5 | Cardiomiopatie ischemica | Miocardiopatie ischemica | exact |
| I27.9 | Cardiopatia pulmonara, nespecificata | Cord pulmonar | temporal (G1) |
| I42 | Cardiomiopatia | Cardiomiopatie | terminatii |
| I42.0 | Cardiomiopatia cu dilatatie | Cardiomiopatie dilatativa | terminatii |
| I42.1 | Cardiomiopatia hipertrofica obstructiva | Cardiomiopatie hipertrofica | terminatii |
| I42.6 | Cardiomiopatia alcoolica | Cardiomiopatie alcoolica | terminatii |
| I43.1 | Cardiomiopatia in boli de metabolism | Amiloidoza ATTR | exact |
| I51.7 | Cardiomegalia | Cardiomegalie | terminatii |
| I51.9 | Cardiopatia, nespecificata | Cardiopatie | terminatii |
| J98.1 | Colaps pulmonar | Atelectazie pulmonara | terminatii |
| K02 | Carii dentare | Carie dentara | terminatii |
| K51 | Colita ulceroasa | Colita ulcerativa | exact |
| K51.9 | Colita ulcerativa, nespecificata | Colita ulcerativa | exact |
| K59.0 | Constipatia | Constipatie | terminatii |
| K70.0 | Ciroza alcoolica grasoasa a ficatului | Steatoza hepatica alcoolica | exact |
| K70.3 | Ciroza alcoolica a ficatului | Ciroza alcoolica | exact |
| K74.3 | Ciroza biliara primitiva | Ciroza biliara primitiva | exact |
| K80 | Colelitiaza | Litiaza biliara | exact |
| K81 | Colecistita | Colecistita | exact |
| K81.0 | Colecistita acuta | Colecistita | exact |
| K81.1 | Colecistita cronica | Colecistita | exact |
| L03 | Celulita | Celulita | exact |
| L03.0 | Celulita degetelor de la maini si picioare | Paronichie | terminatii |
| L05 | Chist pilonidal | Sinus pilonidal | exact |
| L05.9 | Chist pilonidal fara abces | Sinus pilonidal | exact |
| L72.1 | Chist trichodermic | Chist trichilemal | exact |
| L75.1 | Cromhidroza | Chromhidroza | exact |
| L81.1 | Chloasma | Cloasma | exact |
| L82 | Cheratoza seboreica | Cheratoza seboreica | exact |
| L91.0 | Cicatrice cheloida | Cheloid | exact |
| M16 | Coxartroza [artroza coapsei] | Coxartroza | exact |
| M16.9 | Coxartroza, nespecificata | Coxartroza | exact |
| M22.4 | Condromalacia rotulei | Condromalacia rotuliana | exact |
| M23.0 | Chist al meniscului | Chist de menisc | exact |
| M62.4 | Contractura musculara | Contractura musculara | exact |
| M75.0 | Capsulita rectractila a umarului | Sindrom de iesire toracica | exact |
| M85.4 | Chist osos solitar | Chist osos | exact |
| M85.5 | Chist anevrismal al osului | Chist osos anevrismal | exact |
| M91.2 | Coxa plana | Boala Legg-Calve-Perthes | exact |
| M94.2 | Condromalacia | Condromalacie | exact |
| N20.0 | Calculii rinichiului | Calculi renali | exact |
| N30 | Cistita | Cistita | exact |
| N30.0 | Cistita acuta | Cistita | exact |
| N30.1 | Cistita interstitiala (cronica) | Cistita interstitiala | exact |
| N81.1 | Cistocel | Cistocel | exact |
| N83.1 | Chist al corpului galben | Chist de corp luteu | exact |
| P08.2 | Copil nascut dupa termen, care nu e mare pentru varsta gestationala | Sarcina depasita | exact |
| P37.5 | Candidoza neonatala | Candidoza neonatala | exact |
| P37.50 | Candidoza neonatala, nespecificata | Candidoza neonatala | exact |
| Q04.60 | Chist cerebral congenital, nespecificat | Porencefalie | terminatii |
| Q12.0 | Cataracta congenitala | Cataracta | exact |
| Q26.2 | Conexiune venoasa pulmonara aberanta totala | Drenaj venos pulmonar anormal total | exact |
| Q26.3 | Conexiune venoasa pulmonara aberanta partiala | Drenaj venos pulmonar anormal partial | exact |
| Q44.4 | Chist al coledocului | Chist de coledoc | exact |
| Q75.0 | Craniosinostoza | Craniosinostoza | exact |
| Q75.01 | Craniosinostoza coronala | Scafocefalie | exact |
| Q75.04 | Craniosinostoza cu alte suturi multiple | Oxycefalie | terminatii |
| Q76.5 | Coasta cervicala | Sindrom de coasta cervicala | exact |
