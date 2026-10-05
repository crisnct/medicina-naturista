# Litera S — raport CIM-10

- coduri CIM-10 cu titlul la litera S: **647**
- eliminate automat (P2): **96**
  - sechele: 32
  - dublura categoriei parinte (nespecificat): 30
  - subzona de organ (D5): 27
  - asterisc (in alte boli): 4
  - procedura: 2
  - agent cauzal, nu boala: 1
- găsite automat în dicționar (P4.1–P4.3): **208**
- de decis manual (`nou` + `posibil`): **343**
- **afecțiuni adăugate: 85**

## Decizii manuale

- **Potriviri automate greșite (lista `exista`):** `D46 Sindroame mielodisplazice` → `Spina bifida` — linia `Spina bifida` conține din greșeală termenii sindromului mielodisplazic („sindrom mielodisplazic”, „myelodysplastic syndrome(s)”, „mielodisplazie”), confuzie cu mielodisplazia spinală. Boala hematologică lipsește deci din dicționar; cum termenii sunt ocupați (G6) și linia veche nu se modifică (D6), a intrat în `pending_from_S.jsonl` ca `Neoplasm mielodisplazic` (denumirea OMS 2022, litera N). **De corectat ulterior** linia `Spina bifida`. Tot aici: `Sept nazal deviat` există, dar ca sinonim în `Decubit de cornet`; `Sindromul William` (Q87.84) e sinonim, ciudat, în `Sindrom Laurence-Moon` (`Sindrom Williams` există separat); `Q87.23 Sindromul rotulei fixe` e traducerea greșită a sindromului unghie-rotulă (există).
- **Existau sub alt nume (căutare manuală):** sepsisul cu Salmonella (`Bacteriemie cu Salmonella`), cu Candida (`Candidoza diseminata`), cu Listeria (`Listerioza`, „listerioza diseminata”), cu S. aureus (`Sepsis stafilococic`), cu streptococ de grup A/B/D (`Sepsis streptococic`); `Sancrul sifilitic` (`Sifilis primar`), `Sancrul moale` (`Sancroid`), șancrul pianic (`Framboesia`); sindromul de rubeolă congenitală (`Rubeola`); HLH asociat infecției (`Limfohistiocitoza hemofagocitara`, `Sindrom de activare macrofagica`); sindromul de oboseală postvirală (`Sindromul oboselii cronice`, `Encefalomielita`); sindromul postencefalitic (`Sechele de encefalita virala`); sindromul de ansă oarbă (`Sobrecarga bacteriana intestinala`); steatoreea pancreatică (`Insuficienta pancreatica exocrina`); stenoza infundibulară pulmonară (`Stenoza pulmonara`); sindromul Fanconi-de Toni-Debré, Lowe, Pyle, Pickwick, Kelly-Paterson, Imerslund, Conn, Schmidt, Münchausen, Kleine-Levin, Pierre Robin, Wolf-Hirschhorn, X fragil (toate prezente); sindromul copilului împiedicat (`Dispraxie`); sindromul umăr-mână (`Sindrom de durere regionala complexa`); sindromul Stokes-Adams (`Sincopa cardiaca`, „sincopa prin aritmie”); sindromul Hamman-Rich (inclus la J84.1 împreună cu `Fibroza pulmonara idiopatica`); sindromul ovarului rezidual (`Sindrom de ovar remanent`, „retained ovary syndrome”); sindromul de inel constrictor (`Sindrom de banda amniotica`); obstrucția/stenoza trompei Eustache (`Disfunctie de trompa Eustachio`); subluxația congenitală/șoldul instabil (`Luxatie congenitala de sold`); cretinismul mixedematos/neurologic/mixt.
- **Grupate în categoria lor (D5 / G1):** sifilisul pe stadii și localizări (A50.0–A50.7, A51.x, A52.x → `Sifilis congenital`, `Sifilis congenital tardiv`, `Sifilis primar`, `Sifilis secundar`, `Sifilis latent precoce/tardiv`, `Neurosifilis`; sifilisul în sarcină O98.1 → `Sifilis`); sarcomul Kaposi pe localizări (C46.x); sarcoidoza pe organe (D86.x, „plămân” e sinonim în `Sarcoidoza`); surditatea uni-/bilaterală (H90.x); stenozele valvulare „cu insuficiență” și reumatismale/nereumatismale (I05–I37); spina bifida după nivel (Q05.x); situs inversus abdominal/toracic; scoliozele infantilă/juvenilă/toracogenă/postiradiere; sepsisul neonatal după agent (P36.x → `Sepsis neonatal`, cu excepția celui existent cu streptococ de grup B); limfedemul postmastectomie (`Limfedem secundar`); splenomegalia congestivă (`Splenomegalie`); stenozele congenitale de arteră renală, bronhii, vena cavă, laringe; spondilita anchilozantă juvenilă (`Artrita juvenila asociata entezitei`); sângerarea ovulatorie (`Metroragie`); șocul obstetrical și cel post-avort (complicații); Klinefelter cu > 2 X (`Sindrom Klinefelter`); status epilepticus parțial complex (`Status epilepticus nonconvulsiv`).
- **Nu sunt boli anume (G7 / P2):** agenții B95.x („Streptococ…, cauza unor boli clasate la alte capitole”), sechelele, codurile-asterisc G46.x (sindroame vasculare cerebrale), M49.x, H19.0; scăderea vederii (H54), statura înaltă constituțională, sclerotica albastră și sclerodactilia (semne), erupția dentară, sub-/supraalimentarea nou-născutului, sarcina multiplă/gemelară (stare), sexul nedeterminat (rezidual), leziunile biomecanice M99.x, secreția hormonală ectopică NCA, „Sindroame de malformații congenitale…” (titluri de grup), localizările de tumori din lista încrucișată („Sacul lacrimal”, „Spate”, „Splina” etc.), ciupitul nasului, suptul degetului.
- **Variante păstrate separat (G4):** sepsisul după agent, ca în dicționar (`Sepsis stafilococic`/`streptococic` există): pneumococic, Haemophilus, anaerobi, gram-negativi, E. coli, Pseudomonas, Erysipelothrix, actinomicotic; `Strongiloidoza cutanata` (larva currens) față de cea diseminată; `Sclerodermie liniara` (lângă `Morfea`, `Sclerodermie limitata`); `Scolioza neuromusculara` (lângă idiopatică/congenitală); `Spondilolisteza congenitala` (lângă istmică/degenerativă); `Stenoza mitrala congenitala` (ca `Stenoza aortica congenitala`); `Salpingita eustachiana`; eponimele distincte de entitatea-mamă: `Sindrom Taussig-Bing` (subtip de ventricul drept cu dublă ieșire), `Sindrom scimitar` (subtip de drenaj venos pulmonar anormal parțial), `Sindrom Swyer` (lângă `Disgeneza gonadala`), `Sindrom Pendred` (lângă `Gusa`), `Sindrom McCune-Albright` (lângă `Displazie fibroasa`), `Sindrom Maffucci` (encondromatoză cu hemangioame), `Sindrom Fraser` (≠ `Sindrom Frasier`, lângă `Criptoftalmie`), `Sindrom Brown` (≠ `Sindrom Brown-Sequard`), `Sindrom Mendelson` (pneumonită chimică, ≠ pneumonia de aspirație bacteriană), `Sindrom Jeune` (termenul „distrofie toracica asfixianta” e deja, greșit, în `Nanism tanatofor`; am folosit „displazie toracica asfixianta”).
- **Sinonime insuficiente (2.4):** Tanapox, Yabapox, scarabiaza, sindromul Dhat, Lermoyez, Woakes, Cayler, Nélaton, Allen-Masters, „bebelușul bronzat”, scrotul bifid, sindromul megacistită-megaureter, stenoza congenitală de venă cavă, sinostoza humero-ulnară/humero-radială, schizofrenia cenestopată, schimbarea durabilă de personalitate după o experiență catastrofică/boală psihică (F62, și nume > 60 de caractere), sindromul de monofixare.
- **Amânate la altă literă (`pending_from_S.jsonl`):** `Neoplasm mielodisplazic` (N, D46), `Antrax septicemic` (A, A22.7), `Epilepsie partiala continua` (E, G40.5), `Fetopatie diabetica` (F, P70.0–P70.1), `Polimastie` (P, Q83.1), `Tulburare dezintegrativa a copilariei` (T, F84.3, sindromul Heller). Lăsate literei titlului (le vede alt pas): satiriaza/hipersexualitatea (F52.7, titlu la N), deficitul HLA clasa I / sindromul limfocitelor goale tip I (D81.6, titlu la D), sindromul instituțional (F94.2, titlu la T), condrodisplazia punctată/sindromul Conradi (Q77.3, titlu la C). Sifilisul nevenerian/endemic (A65, Bejel) nu l-am adăugat — e la B.
- **Din `pending_by_letter.jsonl`:** `Sindrom Gianotti-Crosti` (L44.4) și `Sindrom Carpenter` (Q87.01) — reverificate (lookup, G6), adăugate.
- **Risc la unire:** câteva eponime adăugate aici stau, în CIM-10, sub coduri cu titlul la altă literă (Pendred — E07.1 „Gușă…”, McCune-Albright — Q78.1 „Displazie fibroasă poliostotică”, Maffucci — Q78.4 „Encondromatoză”, trombocite gri — D69.1); dacă pașii D/E/G le pun ca sinonime ale titlului lor, apare conflict G6 la unire.
- **Amânate de la alte litere, adăugate la unire (coordonator, 13):** `Sindrom Vogt-Koyanagi-Harada` (H30.8; de la B); `Sarcom de parti moi` (C49; de la C); `Sarcom mastocitar` (C96.2; de la C); `Stenoza ureterala` (N13.5; de la C); `Sindrom fetal warfarinic` (Q86.2; de la D); `Sindrom Frohlich` (E23.6; de la D); `Stenoza de apeduct Sylvius` (Q03.0; de la M); `Sindrom fetal valproic` (Q86.81; de la M); `Stenoza de artera cerebrala` (I66; de la O); `Sarcina anembrionara` (O02.0; de la O); `Sindrom HHH` (E72.4; de la O); `Silicotuberculoza` (J65; de la P); `Sigmatism` (F80.8; de la V). Verificate față de dicționarul unit al tuturor literelor (G3, G6).

## Adăugate

| Nume canonic | Coduri | Sinonime |
|---|---|---|
| Sadomasochism | F65.5 | sado-masochism; algolagnie; tulburare sadomasochista; sexual sadomasochism; algolagnia; sadomasochistic disorder |
| Salpingita eustachiana | H68.0 | salpingita trompei Eustache; eustachita; tubita; eustachian salpingitis; eustachitis; eustachian tube inflammation |
| Sarcina anembrionara | O02.0 | ou anembrionar; sarcina anembrionica; sac gestational fara embrion; blighted ovum; anembryonic pregnancy; anembryonic gestation |
| Sarcocistoza | A07.8 | sarcosporidioza; infectie cu Sarcocystis; sarcocistoza intestinala; sarcocystosis; sarcosporidiosis; Sarcocystis infection |
| Sarcom de parti moi | C49 | tumora maligna a tesutului conjunctiv si a tesuturilor moi; sarcom de tesuturi moi; tumora maligna de parti moi; soft tissue sarcoma; malignant neoplasm of connective and soft tissue; malignant soft tissue tumor |
| Sarcom mastocitar | C96.2 | tumora maligna cu mastocite; mastocitom malign; sarcom cu mastocite; mast cell sarcoma; malignant mast cell neoplasm; malignant mastocytoma |
| Sarcom mieloid | C92.3 | clorom; sarcom granulocitar; tumora mieloida extramedulara; myeloid sarcoma; chloroma; granulocytic sarcoma |
| Sarcozinemie | E72.5 | sarcozinemia; hipersarcozinemie; deficit de sarcozin-dehidrogenaza; sarcosinemia; hypersarcosinemia; sarcosine dehydrogenase deficiency |
| Sclerodermie liniara | L94.1 | sclerodermia lineara; morfee liniara; sclerodermie in lovitura de sabie; linear scleroderma; linear morphea; en coup de sabre |
| Scolioza neuromusculara | M41.4 | scolioza paralitica; scolioza neuropata; scolioza neurogena; neuromuscular scoliosis; paralytic scoliosis; neuropathic scoliosis |
| Sepsis actinomicotic | A42.7 | septicemie actinomicotica; actinomicoza diseminata; actinomicoza septicemica; actinomycotic sepsis; disseminated actinomycosis; actinomycotic septicaemia |
| Sepsis cu anaerobi | A41.4 | sepsis datorita anaerobilor; septicemie cu anaerobi; sepsis anaerob; sepsis due to anaerobes; anaerobic sepsis; anaerobic septicaemia |
| Sepsis cu Erysipelothrix | A26.7 | septicemie cu Erysipelothrix; erizipeloid septicemic; infectie sistemica cu Erysipelothrix rhusiopathiae; Erysipelothrix sepsis; Erysipelothrix septicaemia; systemic Erysipelothrix infection |
| Sepsis cu Escherichia coli | A41.51 | sepsis datorita Escherichia coli; septicemie cu E. coli; sepsis colibacilar; sepsis due to Escherichia coli; E. coli sepsis; Escherichia coli septicaemia |
| Sepsis cu germeni gram-negativi | A41.5, A41.50, A41.58 | sepsis datorita organismelor gram-negative; septicemie gram-negativa; sepsis cu bacili gram-negativi; sepsis due to Gram-negative organisms; Gram-negative sepsis; Gram-negative septicaemia |
| Sepsis cu Haemophilus influenzae | A41.3 | sepsis datorita Haemophilus influenzae; septicemie cu Haemophilus influenzae; septicemie cu Haemophilus; sepsis due to Hemophilus influenzae; Haemophilus influenzae sepsis; Haemophilus influenzae septicaemia |
| Sepsis cu Pseudomonas | A41.52 | sepsis datorita Pseudomonas; septicemie cu Pseudomonas aeruginosa; sepsis piocianic; sepsis due to Pseudomonas; Pseudomonas sepsis; Pseudomonas aeruginosa septicaemia |
| Sepsis pneumococic | A40.3 | septicemie pneumococica; sepsis datorita Streptococcus pneumoniae; sepsis cu pneumococ; sepsis due to Streptococcus pneumoniae; pneumococcal sepsis; pneumococcal septicaemia |
| Sialectazie | K11.8 | sialectazia; dilatatie a canalelor salivare; ectazie ductala salivara; sialectasis; sialectasia; salivary duct ectasia |
| Sialometaplazie necrozanta | K11.8 | sialometaplazia necrozanta; sialometaplazie necrotica; metaplazie necrozanta a glandelor salivare; necrotizing sialometaplasia; necrotising sialometaplasia; necrotizing sialometaplasia of palate |
| Sigmatism | F80.8 | vorbire peltica; vorbire sasaita; vorbire sopotita; lisp; lisping; sigmatismus |
| Silicotuberculoza | J65 | pneumoconioza asociata cu tuberculoza; silicoza cu tuberculoza; tuberculoza silicotica; pneumoconiosis associated with tuberculosis; silicotuberculosis; silicotic tuberculosis |
| Sindrom Brown | H50.6 | sindromul tecii Brown; sindromul tecii tendonului oblic superior; sindrom de teaca a muschiului oblic superior; Brown syndrome; superior oblique tendon sheath syndrome; Brown tendon sheath syndrome |
| Sindrom Carpenter | Q87.01 | acrocefalopolisindactilie tip II; acrocefalopolisindactilie; sindromul Carpenter; Carpenter syndrome; acrocephalopolysyndactyly type II; acrocephalopolysyndactyly |
| Sindrom cervicobrahial | M53.1 | sindrom cervico-brahial; nevralgie cervicobrahiala; cervicobrahialgie; cervicobrachial syndrome; cervicobrachial neuralgia; cervicobrachialgia |
| Sindrom cervicocranian | M53.0 | sindrom cervico-cranian; sindrom simpatic cervical posterior; sindrom Barre-Lieou; cervicocranial syndrome; posterior cervical sympathetic syndrome; Barre-Lieou syndrome |
| Sindrom de bila ingrosata | P59.1 | sindromul bilei ingrosate; sindrom de dop biliar; colestaza neonatala prin bila ingrosata; inspissated bile syndrome; bile plug syndrome; inspissated bile plug |
| Sindrom de copil cenusiu | P93 | sindromul Grey din cauza cloramfenicolului; sindromul copilului cenusiu; sindrom cenusiu al nou-nascutului; gray baby syndrome; grey baby syndrome; gray syndrome of newborn |
| Sindrom de disfunctie reactiva a cailor aeriene | J68.3 | sindromul disfunctiei reactive a cailor respiratorii; astm indus de iritanti; astm indus de expunere acuta la iritanti; reactive airways dysfunction syndrome; RADS; irritant-induced asthma |
| Sindrom de durere lombara cu hematurie | N39.81 | sindromul hematuriei si durerii in lombe; sindrom hematurie-durere lombara; durere lombara cu hematurie; loin pain hematuria syndrome; loin pain-haematuria syndrome; LPHS |
| Sindrom de eunuc fertil | E23.0 | sindromul eunucoidismului fertil; sindrom Pasqualini; deficit izolat de LH; fertile eunuch syndrome; Pasqualini syndrome; isolated LH deficiency |
| Sindrom de la Chapelle | Q98.2 | sindrom Klinefelter cu cariotip 46 XX; sindromul barbatului XX; inversiune de sex 46 XX testiculara; Klinefelter syndrome male with 46 XX karyotype; XX male syndrome; 46 XX testicular disorder of sex development |
| Sindrom de membru fantoma | G54.6, G54.7 | sindromul membrului fantoma; durere de membru fantoma; membru fantoma dureros; phantom limb syndrome; phantom limb pain; phantom limb syndrome with pain |
| Sindrom de spate plat | M40.3 | sindromul spatelui plat; deformatie in spate plat; spate plat lombar; flatback syndrome; flat back deformity; fixed sagittal imbalance |
| Sindrom de trombocite gri | D69.1 | sindromul trombocitelor gri; sindromul plachetelor gri; deficit de granule alfa plachetare; gray platelet syndrome; grey platelet syndrome; platelet alpha-granule deficiency |
| Sindrom de unghie galbena | L60.5 | sindromul unghiei galbene; sindromul unghiilor galbene; sindrom unghii galbene si limfedem; yellow nail syndrome; yellow nail lymphedema syndrome; lymphedema with yellow nails |
| Sindrom dumping | K91.1 | sindromul dumping; sindrom de golire gastrica rapida; dumping postgastrectomie; dumping syndrome; rapid gastric emptying syndrome; postgastrectomy dumping |
| Sindrom Eisenmenger | Q21.8 | complex Eisenmenger; reactie Eisenmenger; fiziologie Eisenmenger; Eisenmenger syndrome; Eisenmenger complex; Eisenmenger physiology |
| Sindrom eutiroidian bolnav | E07.8 | sindromul disfunctiei eutiroidiene; sindrom de boala netiroidiana; sindromul T3 scazut; euthyroid sick syndrome; nonthyroidal illness syndrome; low T3 syndrome |
| Sindrom fetal valproic | Q86.81 | sindrom fetal la valproat; embriopatie valproica; malformatii congenitale datorite valproatului; fetal valproate syndrome; fetal valproate spectrum disorder; valproate embryopathy |
| Sindrom fetal warfarinic | Q86.2 | dismorfism datorita warfarinei; embriopatie warfarinica; embriopatie cumarinica; dysmorphism due to warfarin; fetal warfarin syndrome; warfarin embryopathy; coumarin embryopathy |
| Sindrom Fraser | Q87.03 | sindromul criptoftalmic; sindrom criptoftalmie-sindactilie; sindromul Fraser; Fraser syndrome; cryptophthalmos syndrome; cryptophthalmos-syndactyly syndrome |
| Sindrom Frohlich | E23.6 | distrofie adiposo-genitala; sindrom adipozogenital; boala Babinski-Frohlich; adiposogenital dystrophy; Frohlich syndrome; Babinski-Frohlich syndrome |
| Sindrom Gianotti-Crosti | L44.4 | acrodermatita papuloasa infantila; acrodermatita eritemato-papuloasa infantila; boala Gianotti-Crosti; Gianotti-Crosti syndrome; infantile papular acrodermatitis; papular acrodermatitis of childhood |
| Sindrom Hallermann-Streiff | Q87.05 | sindromul Hallerman-Streiff; sindrom Hallermann-Streiff-Francois; sindrom oculo-mandibulo-facial; Hallermann-Streiff syndrome; oculomandibulofacial syndrome; oculomandibulodyscephaly |
| Sindrom HHH | E72.4 | sindrom hiperornitinemie hiperamoniemie homocitrulinurie; deficit de translocaza a ornitinei; deficit de transportor mitocondrial al ornitinei; HHH syndrome; hyperornithinemia-hyperammonemia-homocitrullinuria syndrome; ornithine translocase deficiency; ORNT1 deficiency |
| Sindrom hidantoinic fetal | Q86.1 | sindromul hidantoinei fetale; sindrom fetal la fenitoina; embriopatie hidantoinica; fetal hydantoin syndrome; fetal phenytoin syndrome; hydantoin embryopathy |
| Sindrom Holt-Oram | Q87.21 | sindrom inima-mana; sindromul atrio-digital; displazie atriodigitala; Holt-Oram syndrome; heart-hand syndrome; atriodigital dysplasia |
| Sindrom Jeune | Q77.2 | sindromul coastei scurte; displazie toracica asfixianta; boala Jeune; short rib syndrome; Jeune syndrome; asphyxiating thoracic dysplasia |
| Sindrom MacLeod | J43.0 | sindrom Swyer-James; emfizem pulmonar unilateral; plaman hipertransparent unilateral; unilateral pulmonary emphysema; Swyer-James syndrome; unilateral hyperlucent lung |
| Sindrom Maffucci | Q78.4 | sindrom Maffucci-Kast; encondromatoza cu hemangioame multiple; discondroplazie cu hemangioame; Maffucci syndrome; Maffucci-Kast syndrome; enchondromatosis with multiple hemangiomas |
| Sindrom Marcus Gunn | Q07.81 | sindromul mandibulei tremurande; fenomenul Marcus Gunn; sincinezie mandibulo-palpebrala; Marcus Gunn jaw-winking syndrome; jaw-winking syndrome; Marcus Gunn phenomenon |
| Sindrom McCune-Albright | Q78.1 | sindromul Albright-McCune-Sternberg; displazie fibroasa poliostotica cu pubertate precoce; sindrom McCune-Albright-Sternberg; McCune-Albright syndrome; Albright-McCune-Sternberg syndrome; McCune-Albright-Sternberg syndrome |
| Sindrom Meckel-Gruber | Q61.9 | sindromul Meckel; disencefalie splanhnochistica; sindromul Gruber; Meckel-Gruber syndrome; Meckel syndrome; dysencephalia splanchnocystica |
| Sindrom Melkersson-Rosenthal | G51.2 | sindromul Melkersson; boala Melkersson-Rosenthal; sindrom Rossolimo-Melkersson-Rosenthal; Melkersson syndrome; Melkersson-Rosenthal syndrome; Melkersson-Rosenthal-Rossolimo syndrome |
| Sindrom Mendelson | J95.4, O29.0, O89.0 | pneumonita chimica de aspiratie; pneumonita de aspiratie acida; sindrom de aspiratie acida; Mendelson syndrome; chemical pneumonitis due to anesthesia; acid aspiration syndrome |
| Sindrom Pena-Shokeir | Q87.07 | sindromul Pena-Shokeir tip I; secventa de akinezie fetala; sindrom de akinezie fetala; Pena-Shokeir syndrome; fetal akinesia deformation sequence; fetal akinesia syndrome |
| Sindrom Pendred | E07.1 | sindromul Pendred; gusa cu surditate congenitala; gusa dishormonogenetica cu surditate; Pendred syndrome; goiter-deafness syndrome; deafness with goiter |
| Sindrom postlaminectomie | M96.1 | sindromul postlaminectomie; sindromul spatelui operat esuat; sindrom de chirurgie spinala esuata; postlaminectomy syndrome; failed back surgery syndrome; failed back syndrome |
| Sindrom scimitar | Q26.8 | sindromul venei scimitar; sindrom venolobar pulmonar congenital; sindromul plamanului hipogenetic; scimitar syndrome; congenital pulmonary venolobar syndrome; hypogenetic lung syndrome |
| Sindrom Swyer | Q97.3 | sex feminin cu cariotip 46 XY; disgenezie gonadala pura 46 XY; disgenezie gonadala completa XY; female with 46 XY karyotype; Swyer syndrome; 46 XY complete gonadal dysgenesis |
| Sindrom Taussig-Bing | Q20.1 | sindromul Taussig-Bing; anomalie Taussig-Bing; ventricul drept cu dubla iesire cu DSV subpulmonar; Taussig-Bing anomaly; Taussig-Bing syndrome; double outlet right ventricle with subpulmonary VSD |
| Sindrom Vogt-Koyanagi-Harada | H30.8 | boala Harada; boala Vogt-Koyanagi-Harada; sindrom uveomeningoencefalitic; Vogt-Koyanagi-Harada disease; Harada disease; uveomeningoencephalitic syndrome; VKH syndrome |
| Sindrom Wilson-Mikity | P27.0 | dismaturitate pulmonara; boala Wilson-Mikity; dismaturitate pulmonara a prematurului; Wilson-Mikity syndrome; pulmonary dysmaturity; Wilson-Mikity disease |
| Siringocel uretral | Q64.78 | siringocel uretral congenital; siringocel Cowper; chist de canal Cowper; urethral syringocele; Cowper syringocele; Cowper duct cyst |
| Splina ratacitoare | Q89.09 | splina ectopica; splina mobila; splenoptoza; wandering spleen; ectopic spleen; splenoptosis |
| Spondilolisteza congenitala | Q76.2, Q76.21, Q76.22 | spondilolisteza congenitala si spondiloliza; spondilolisteza displazica; spondiloliza congenitala; congenital spondylolisthesis; dysplastic spondylolisthesis; congenital spondylolysis |
| Spondilopatie traumatica | M48.3 | boala Kummell; osteonecroza vertebrala posttraumatica; boala Kummell-Verneuil; traumatic spondylopathy; Kummell disease; posttraumatic vertebral osteonecrosis |
| Stenoza de apeduct Sylvius | Q03.0 | malformatii ale apeductului Sylvius; stenoza apeductala congenitala; stenoza apeductului cerebral; malformations of aqueduct of Sylvius; aqueductal stenosis; congenital aqueductal stenosis |
| Stenoza de artera cerebrala | I66 | stenoza arterelor cerebrale; stenoza arteriala intracraniana; stenoza aterosclerotica intracraniana; cerebral artery stenosis; intracranial arterial stenosis; intracranial atherosclerotic stenosis; intracranial stenosis |
| Stenoza de col uterin | N88.2 | strictura si stenoza colului uterin; stenoza cervicala uterina; strictura de col uterin; stricture and stenosis of cervix uteri; uterine cervical stenosis; cervical os stenosis |
| Stenoza de duct salivar | K11.8 | stenoza canalului salivar; strictura ductului salivar; sialostenoza; salivary duct stenosis; salivary duct stricture; sialostenosis |
| Stenoza mitrala congenitala | Q23.2 | stenoza congenitala a valvei mitrale; valva mitrala in parasuta; inel supravalvular mitral; congenital mitral stenosis; congenital mitral valve stenosis; parachute mitral valve |
| Stenoza ureterala | N13.5 | strictura ureterala; ingustare ureterala; stenoza a ureterului; ureteral stricture; ureteric stricture; ureteral stenosis |
| Stenoza vaginala | N89.5 | strictura si atrezia vaginului; strictura vaginala; ingustare vaginala dobandita; stricture and atresia of vagina; vaginal stenosis; vaginal stricture |
| Stern bifid | Q76.72 | fisura sternala congenitala; despicatura sternala; stern despicat; bifid sternum; sternal cleft; cleft sternum |
| Stomac in clepsidra | K31.2 | stomac biloculat; stenoza mediogastrica; strictura in clepsidra a stomacului; hourglass stomach; hourglass stricture of stomach; bilocular stomach |
| Striuri angioide | H35.3 | striatii angioide ale maculei; striuri angioide retiniene; linii angioide; angioid streaks; angioid streaks of macula; Knapp streaks |
| Strongiloidoza cutanata | B78.1 | strongyloidiaza cutanata; larva currens; dermatita cu Strongyloides; cutaneous strongyloidiasis; Strongyloides dermatitis; cutaneous strongyloidosis |
| Stupoare disociativa | F44.2 | stupor disociativ; stupoare psihogena; stupoare isterica; dissociative stupor; psychogenic stupor; hysterical stupor |
| Suberoza | J67.3 | boala manipulatorilor de scoarta de pluta; plamanul muncitorilor cu pluta; pneumonita de hipersensibilitate la pluta; suberosis; cork worker's lung; cork handler's disease |
| Subinvolutie uterina | N85.3 | subinvolutia uterului; subinvolutie uterina postpartum; involutie uterina incompleta; subinvolution of uterus; uterine subinvolution; delayed uterine involution |
| Subluxatie atlantoaxiala recurenta | M43.3, M43.4 | subluxatia atlanto-axiala recurenta; instabilitate atlanto-axiala; subluxatie atlanto-axiala netraumatica; recurrent atlantoaxial subluxation; atlantoaxial instability; recurrent atlantoaxial dislocation |
| Surdomutitate | H91.3 | surdo-mutitate; surdomutism; mutitate prin surditate; deaf nonspeaking; deaf-mutism; deaf-muteness |
| Syngamoza | B83.3 | syngamiaza; singamoza; infestatie cu Syngamus laryngeus; syngamiasis; syngamosis; mammomonogamiasis |

## Decise manual, neadăugate

Titluri `nou` / `posibil` care nu au devenit afecțiuni noi: există sub alt nume, sunt variante ale unei categorii (D5), categorii generice sau nu sunt boli (G7). Coloana „Apropiat” e sugestia automată.

| Cod | Titlu CIM-10 | Apropiat |
|---|---|---|
| A02.1 | Sepsis cu Salmonella | Osteomielita cu Salmonella / Bacteriemie cu Salmonella |
| A02.9 | Salmonelloze, nespecificata | Salmoneloza |
| A03.0 | Shigelloza datorita Shigellei dyzenteriae |  |
| A03.1 | Shigelloza datorita Shigellei flexneri |  |
| A03.2 | Shigelloza datorita Shigellei boydii |  |
| A03.3 | Shigelloza datorita Shigellei sonnei |  |
| A22.7 | Septicemie carbunoasa |  |
| A32.7 | Sepsis listerian |  |
| A40.0 | Sepsis datorita unui streptococ, grupa A |  |
| A40.1 | Sepsis datorita unui streptococ, grupa B |  |
| A40.2 | Sepsis datorita unui streptococ, grupa D |  |
| A41.0 | Sepsis datorita stafilococului auriu |  |
| A41.1 | Sepsis datorita altor stafilococi, specificati |  |
| A41.2 | Sepsis datorita unui stafilococ nespecificat |  |
| A50.0 | Sifilis congenital precoce, simptomatic | Sifilis congenital |
| A50.1 | Sifilis congenital precoce, latent | Sifilis congenital / Sifilis latent precoce |
| A50.4 | Sifilis congenital nervos tardiv (neuro-sifilis juvenil) | Neurosifilis / Sifilis congenital / Sifilis congenital tardiv / Sifilis tertiar |
| A50.6 | Sifilis congenital tardiv, latent | Sifilis congenital / Sifilis congenital tardiv / Sifilis latent tardiv / Sifilis tertiar |
| A51 | Sifilis precoce | Sifilis congenital / Sifilis latent precoce |
| A51.0 | Sifilis genital primar |  |
| A51.1 | Sifilis anal primar | Sifilis primar |
| A51.2 | Sifilis primar, cu alte localizari |  |
| A51.3 | Sifilis secundar al pielii si mucoaselor |  |
| A51.5 | Sifilis recent, latent | Sifilis latent precoce |
| A52.1 | Sifilis nervos simptomatic | Neurosifilis |
| A52.2 | Sifilis nervos asimptomatic | Neurosifilis |
| A52.8 | Sifilis tardiv, latent | Sifilis latent tardiv / Sifilis tertiar |
| A65 | Sifilisul nevenerian |  |
| B08.4 | Stomatita veziculara cu exantem, prin enterovirus | Boala maini-picioare-gura |
| B17.0 | Suprainfectia acuta prin agent Delta la un purtator de hepatita | Hepatita D |
| B23.0 | Sindromul de infectie acuta prin HIV | Infectie acuta cu HIV / Sida / Tuberculoza asociata HIV |
| B37.7 | Sepsis prin Candida |  |
| B65.0 | Schistosomiaza prin Schistosoma haematobium [schistosomiaza urimara] | Schistosomiaza urinara / Schistosomiaza japoneza / Schistosomiaza intestinala / Pneumonie cu Schistosoma |
| B78.0 | Strongyloidiaza intestinala | Strongiloidoza / Tricostrongiloidoza |
| B95.0 | Streptococ, grupa A, cauza unor boli clasate la alte capitole |  |
| B95.1 | Streptococ, grupa B, cauza unor boli clasate la alte capitole |  |
| B95.2 | Streptococ, grupa D, cauza unor boli clasate la alte capitole |  |
| B95.3 | Streptococcus pneumoniae, cauza unor boli clasate la alte capitole |  |
| B95.41 | Streptococ, grupa C | Faringita cu streptococ de grup C |
| B95.42 | Streptococ, grupa G | Faringita cu streptococ de grup G |
| B95.48 | Streptococ, alta grupa specificata |  |
| B95.5 | Streptococ nespecificat drept cauza unor boli clasate la alte capitole |  |
| B95.6 | Staphilococcus aureus, cauza unor boli clasate la alte capitole |  |
| B95.8 | Stafilococ nespecificat drept cauza unor boli clasate la alte capitole |  |
| C46.0 | Sarcomul Kaposi al pielii | Sarcom cutanat / Sarcom Kaposi |
| C46.1 | Sarcomul Kaposi al tesuturilor moi | Sarcom Kaposi |
| C46.2 | Sarcomul Kaposi al palatului | Sarcom Kaposi |
| C46.3 | Sarcomul Kaposi al ganglionilor limfatici | Linfangiosarcom / Sarcom Kaposi |
| C46.7 | Sarcomul Kaposi cu alte localizari | Sarcom Kaposi |
| C46.8 | Sarcomul Kaposi la multiple organe | Sarcom Kaposi |
| D73.2 | Splenomegalia congestiva cronica |  |
| D76.2 | Sindromul hemofagocitar asociat unei infectii |  |
| D82.1 | Sindromul Di George | Sindrom DiGeorge |
| D82.4 | Sindromul hiperimunoglobulinei E [lgE] |  |
| D86.0 | Sarcoidoza plamanului |  |
| D86.1 | Sarcoidoza ganglionilor limfatici | Sarcoidoza ganglionara / Limfadenopatie |
| D86.2 | Sarcoidoza plamanului si a ganglionilor limfatici | Sarcoidoza ganglionara |
| D86.8 | Sarcoidoza cu alte localizari si combinate | Sarcoidoza oculara |
| E00.0 | Sindromul deficientei congenitale de iod de tip neurologic | Cretinism neurologic |
| E00.1 | Sindromul deficientei congenitale de iod de tip mixedematos |  |
| E00.2 | Sindromul deficientei congenitale de iod de tip mixt | Cretinism |
| E22.2 | Sindromul secretiei anormale a hormonului antidiuretic |  |
| E24.2 | Sindromul Cushing indus medicamentos | Sindrom Cushing iatrogen |
| E34.2 | Secretia hormonala ectopica, neclasificata altundeva |  |
| E34.4 | Statura inalta constitutionala |  |
| E67.2 | Sindrom de hipervitaminoza B6 | Hipervitaminoza B6 |
| E75.3 | Sfincolipidoza, nespecificata |  |
| E80.5 | Sindromul Crigler-Najjar | Sindrom Crigler-Najjar tip I / Sindrom Crigler-Najjar tip II |
| E87.7 | Supraincarcare cu lichide | Supraincarcare de fier |
| F04 | Sindromul amnezic organic, neindus de alcool si alte substante psiho-active |  |
| F07.1 | Sindrom postencefalitic | Sindrom posttrombotic |
| F45.4 | Sindrom dureros somatoform persistent | Tulburare de durere somatoforma |
| F48.1 | Sindrom de depersonalizare-derealizare | Depersonalizare |
| F55.5 | Steroizi sau hormoni |  |
| F59 | Sindroame comportamentale nespecificate asociate perturbarilor fiziologice si factorilor fizici |  |
| F62 | Schimbari durabile de personalitate, care nu pot fi atribuite unei leziuni si boli cerebrale |  |
| F62.0 | Schimbare durabila de personalitate dupa o experienta catastrofica |  |
| F62.1 | Schimbare durabila de personalitate dupa o boala psihiatrica |  |
| F62.9 | Schimbare durabila de personalitate, nespecificata |  |
| G40.5 | Sindroame epileptice in cazuri speciale | Epilepsie focala |
| G41.0 | Stare de "grand mal" epileptic | Status epilepticus |
| G41.1 | Stare de "petit mal" epileptic | Epilepsie absenta / Status epilepticus |
| G41.2 | Stare de "mal epileptic" partial complex |  |
| G41.9 | Stare de "mal epileptic", nespecificata | Status epilepticus |
| G43.2 | Stare de "mal migrenos" |  |
| G45.0 | Sindrom vertebro-bazilar | Insuficienta vertebrobazilara |
| G45.1 | Sindrom carotidian (emisferic) | Sindrom carcinoid / Boala coronariana microvasculara / Sincopa de sinus carotidian |
| G46 | Sindroame vasculare cerebrale in bolile cerebrovasculare (I60-I67†) |  |
| G46.0 | Sindromul arterei cerebrale mijlocii (I66.0†) |  |
| G46.1 | Sindromul arterei cerebrale anterioara (I66.1†) | Sindromul arterei spinale anterioare |
| G46.2 | Sindromul arterei cerebrale posterioara (I66.2†) |  |
| G46.3 | Sindroame vasculare de trunchi cerebral (I60-I67†) |  |
| G46.4 | Sindrom cerebelos vascular (I60-I67†) | Sindrom cerebelos |
| G46.5 | Sindrom lacunar motor pur (I60-I67†) |  |
| G46.6 | Sindrom lacunar senzitiv pur (I60-I67†) |  |
| G47.31 | Sindromul central al apneei de somn | Sindrom de apnee centrala / Sindrom de apnee centrala in somn / Apnee in somn / Sindrom de apnee in somn centrala la adult |
| G47.32 | Sindromul apneei de somn obstructive | Apnee in somn / Sindrom de apnee in somn la copil |
| G47.33 | Sindromul hipoventilatiei in timpul somnului | Sindrom de rezistenta a cailor aeriene superioare |
| G73.0 | Sindrom miastenic in bolile endrocrine |  |
| G83.9 | Sindrom paralitic, nespecificat | Stare vegetativa / Candidoza meningeana / Limfom primar al sistemului nervos central / Meningita criptocococica / Neurobruceloza / Neurocisticercoza |
| G93.3 | Sindromul de oboseala postvirala | Encefalomielita |
| G95.0 | Siringomielia si siringobulbia |  |
| H04.5 | Stenoza si insuficienta cailor lacrimale | Stenoza de cale lacrimala / Dacriolit |
| H49 | Strabism paralitic | Rabie paralitica |
| H54.2 | Scaderea vederii ambilor ochi |  |
| H54.5 | Scaderea vederii unui ochi |  |
| H59.0 | Sindromul corpului vitros dupa chirurgia cataractei |  |
| H61.3 | Stenoza dobandita a conductului auditiv extern | Stenoza de conduct auditiv extern / Atrezie de conduct auditiv extern / Polip auricular / Otita externa circumscrisa |
| H68 | Salpingita si obstructia trompei |  |
| H90 | Surditate de transmisie si neurosenzoriala | Surditate de transmisie / Surditate neurosenzoriala / Surditate mixta |
| H90.0 | Surditate bilaterala de transmisie | Surditate de transmisie |
| H90.1 | Surditate unilaterala de transmisie, fara alterarea auditiei celeilalte urechi | Surditate de transmisie |
| H90.3 | Surditate neurosensoriala bilaterala |  |
| H90.4 | Surditate neurosensoriala unilaterala fara alterarea auditiei celeilalte urechi |  |
| H90.6 | Surditate bilaterala mixta de transmisie si neurosensoriala | Surditate de transmisie / Surditate mixta |
| H90.7 | Surditate unilaterala mixta de transmisie si neurosensoriala fara alterarea auditiei celeilalte urechi | Surditate de transmisie / Surditate mixta |
| H90.8 | Surditate mixta de transmisie si neurosensoriala, nespecificata | Surditate de transmisie / Surditate mixta |
| I05.2 | Stenoza mitrala cu insuficienta | Insuficienta mitrala / Stenoza mitrala |
| I06.0 | Stenoza aortica reumatismala | Stenoza aortica |
| I06.2 | Stenoza aortica reumatismala cu insuficienta | Insuficienta aortica / Stenoza aortica |
| I07.2 | Stenoza tricuspida cu insuficienta | Stenoza tricuspidiana |
| I34.2 | Stenoza (valvei) mitrala nereumatismala | Stenoza mitrala |
| I35.2 | Stenoza si insuficienta (valva) aortica | Insuficienta aortica / Stenoza aortica |
| I36.0 | Stenoza nereumatismala (valva) tricuspida | Stenoza tricuspidiana |
| I36.2 | Stenoza nereumatismala cu insuficienta valvei tricuspide | Insuficienta tricuspidiana / Insuficienta tricuspidiana congenitala / Stenoza tricuspidiana |
| I37.2 | Stenoza valvei pulmonare cu insuficienta | Boala valvulara pulmonara / Sindrom de insuficienta respiratorie / Stenoza pulmonara |
| I45.6 | Sindrom de pre-excitatie | Sindrom de preexcitare |
| I46.0 | Stop cardiac cu resuscitare reusita | Stop cardiac |
| I77.1 | Stenoza arterelor | Stenoza carotidiana / Stenoza de artera bazilara / Stenoza de artera renala / Stenoza de artera vertebrala / Stenoza de artere pulmonare periferice |
| I97.2 | Sindromul limfedemului dupa mastectomie |  |
| J38.6 | Stenoza laringelui | Stenoza laringiana / Atrezie laringiana |
| J63.4 | Sideroza | Bromhidroza / Dermatita disidrozica / Hemosideroza |
| K00.7 | Sindromul de eruptie dentara |  |
| K11.2 | Sialoadenita | Sialadenita |
| K12 | Stomatite si afectiuni inrudite |  |
| K31.1 | Stenoza pilorica hipertrofica a adultului | Estenoza pilorica hipertrofica / Estenoza pilorica / Stenoza aortica |
| K58.0 | Sindromul intestinului iritabil cu diaree | Sindrom de intestin iritabil cu diaree / Sindromul intestinului iritabil |
| K62.4 | Strictura anusului si rectului | Estenoza anala |
| K74.1 | Scleroza hepatica | Ciroza hepatica / Necroza hepatica / Steatoza hepatica |
| K83.4 | Spasmul sfincterului Oddi | Disfunctie a sfincterului Oddi |
| K90.2 | Sindromul de ansa oarba, neclasificata altundeva |  |
| K90.3 | Steatoreea pancreatica |  |
| L21.0 | Seboreea capului | Leptospiroza anicterica |
| L90.6 | Striatii atrofice |  |
| L94.3 | Sclerodactilia |  |
| M07.2 | Spondilita psoriazica (L40.5†) |  |
| M08.1 | Spondilita anchilozanta juvenila | Spondilita anchilozanta |
| M12.2 | Sinovita villonodulara (pigmentara) |  |
| M22.1 | Subluxatia recidivanta a rotulei | Sindrom patelofemural |
| M30.3 | Sindromul ganglionilor limfatici muco-cutanati [Kawasaki] | Boala Kawasaki |
| M31.4 | Sindromul crosei aortice [Takayasu] | Arterita Takayasu |
| M34.0 | Scleroza sistemica progresiva | Sclerodermie |
| M34.1 | Sindromul CR(E)ST | Sindrom CREST / Sindrom metabolic |
| M34.2 | Scleroza sistemica datorita unui medicament sau unui produs chimic | Sclerodermie |
| M41.0 | Scolioza idiopatica infantila | Scolioza idiopatica |
| M41.1 | Scolioza idiopatica juvenila | Scolioza idiopatica / Osteoporoza idiopatica juvenila / Artrita idiopatica juvenila |
| M41.3 | Scolioza prin anomalie toracica |  |
| M46.1 | Sacro-ileita, neclasificata altundeva | Sacroiliita |
| M46.9 | Spondilopatia inflamatorie, nespecificata | Colita |
| M47.0 | Sindromul de compresiune a arterei vertebrale si spinale anterioare (G99.2*) | Sindromul arterei spinale anterioare |
| M48.0 | Stenoza canalului medular | Stenoza de conduct auditiv extern / Estenoza anala |
| M48.9 | Spondilopatia, nespecificata | Spondiloartrita seronegativa / Spondiloliza |
| M49.1 | Spondilita in bruceloza (A23.-†) | Bruceloza osoasa |
| M49.2 | Spondilita entero-bacteriana (A01-A04†) |  |
| M49.3 | Spondilopatia in alte boli infectioase si parazitare clasificate altundeva |  |
| M49.4 | Spondilopatia neuropatica |  |
| M62.3 | Sindromul de imobilitate (paraplegica) | Sindrom de hipermobilitate |
| M65 | Sinovita si tenosinovita |  |
| M67.0 | Scurtarea tendonului lui Achille (dobandita) |  |
| M67.3 | Sinovita tranzitorie | Sinovita tranzitorie de sold / Tiroidita silentioasa |
| M68.0 | Sinovita si tenosinovita in boli bacteriene clasificate altundeva |  |
| M70.0 | Sinovita crepitanta cronica a mainii si pumnului |  |
| M75.1 | Sindromul tecii rotatorului |  |
| M75.4 | Sindromul de lovire a umarului |  |
| M94.0 | Sindromul jonctiunii condro-costale [Tietze] | Sindrom Tietze |
| M96.5 | Scolioza dupa iradiere |  |
| M99.1 | Subluxatie complexa (vertebrala) |  |
| M99.2 | Stenoza canalului rahidian prin subluxatie |  |
| M99.3 | Stenoza osoasa a canalului rahidian |  |
| M99.4 | Stenoza canalului rahidian prin tesut conjunctiv |  |
| M99.5 | Stenoza canalului rahidian prin leziune discala |  |
| M99.6 | Stenoza osoasa si prin luxatie a orificiilor intervertebrale |  |
| M99.7 | Stenoza tesutului conjunctiv si discala la nivelul ferestrelor intervertebrale |  |
| N01 | Sindrom nefritic progresiv rapid |  |
| N29.0 | Sifilisul tardiv al rinichiului (A52.7†) | Sifilis tertiar |
| N35.0 | Strictura uretrala, post-traumatica | Strictura uretrala |
| N35.1 | Strictura uretrala post-infectioasa, neclasificata altundeva | Strictura uretrala |
| N70 | Salpingita si ooforita | Boala inflamatorie pelvina |
| N70.0 | Salpingita si ooforita acuta |  |
| N92.3 | Sangerarile ovulatiei |  |
| N92.4 | Sangerari excesive in perioada de premenopauza |  |
| N93.0 | Sangerari postcoitale si de contact | Sangerare postcoitala |
| N93.9 | Sangerare anormala a uterului si vaginului, nespecificata |  |
| N95.1 | Stari de menopauza si climacterice feminine |  |
| N95.3 | Stari asociate cu menopauza artificiala |  |
| O08.3 | Socul urmand avortului si sarcinii ectopice si molare |  |
| O26.5 | Sindrom de hipotensiune materna |  |
| O26.7 | Subluxatia simfisei (pubiene) in sarcina, nastere si lauzie |  |
| O26.82 | Sindromul tunelului carpal in sarcina |  |
| O30 | Sarcina multipla |  |
| O30.0 | Sarcina gemelara |  |
| O30.1 | Sarcina cu tripleti |  |
| O30.2 | Sarcina quadrupla |  |
| O43.0 | Sindromul transfuziei placentare |  |
| O75.1 | Socul in timpul sau dupa travaliu si nastere |  |
| O98.1 | Sifilisul complicand sarcina, nasterea si lauzia |  |
| P10.4 | Sfasiera a tentei creierului mic datorita traumatismului la nastere | Traumatism obstetric |
| P22 | Suferinta respiratorie a nou-nascutului |  |
| P24.9 | Sindrom de aspiratie in perioada neonatala, nespecificat | Sindrom de aspiratie neonatala / Pneumonie congenitala / Pneumonie prin aspiratie |
| P25 | Sindromul de infiltrare a aerului survenind in perioada perinatala |  |
| P28.82 | Stenoza subglotica dobandita la nou-nascut | Stenoza subglotica |
| P35.0 | Sindrom de rubeola congenitala | Rubeola / Sindrom congenital Zika |
| P36 | Sepsis bacterian la nou-nascut | Sepsis neonatal |
| P36.0 | Sepsis la nou-nascut cu streptococi, grupa B | Sepsis neonatal / Sepsis neonatal cu streptococ de grup B |
| P36.1 | Sepsis la nou-nascut cu alti streptococi si nespecificati | Sepsis neonatal |
| P36.2 | Sepsis la nou-nascut cu Staphylococcus aureus | Sepsis neonatal / Sepsis stafilococic |
| P36.3 | Sepsis la nou-nascut cu alti stafilococi si nespecificati | Sepsis neonatal |
| P36.4 | Sepsis la nou-nascut cu Escherichia coli | Sepsis neonatal |
| P36.5 | Sepsis la nou-nascut datorita anaerobilor | Sepsis neonatal |
| P70.0 | Sindromul copilului a carui mama are un diabet gestational | Diabet gestational |
| P70.1 | Sindromul copilului cu mama diabetica |  |
| P80.0 | Sindromul hipotermic al nou-nascutului | Hipotermie neonatala |
| P92.3 | Subalimentarea nou-nascutului |  |
| P92.4 | Supraalimentarea nou-nascutului |  |
| P96.1 | Simptome neonatale de privatiune datorita toxicomaniei mamei |  |
| P96.2 | Simptome de privatiune din cauza folosirii terapeutice a unor medicamente la nou-nascut |  |
| P96.4 | Sfarsitul sarcinii, fat si nou-nascut |  |
| Q05.0 | Spina bifida, cervicala, cu hidrocefalie | Spina bifida |
| Q05.1 | Spina bifida, toracica, cu hidrocefalie | Spina bifida |
| Q05.2 | Spina bifida, lombara, cu hidrocefalie | Spina bifida |
| Q05.3 | Spina bifida sacrala cu hidrocefalie | Spina bifida |
| Q05.4 | Spina bifida nespecificata cu hidrocefalie | Spina bifida |
| Q05.5 | Spina bifida cervicala fara hidrocefalie | Spina bifida |
| Q05.6 | Spina bifida, toracica fara hidrocefalie | Spina bifida |
| Q05.7 | Spina bifida lombara fara hidrocefalie | Spina bifida / Spina bifida oculta |
| Q05.8 | Spina bifida sacrala fara hidrocefalie | Spina bifida |
| Q07.0 | Sindrom Arnold-Chiari | Malformatie Arnold-Chiari / Sindrom Budd-Chiari |
| Q10.5 | Stenoza sau sclerozarea congenitala a canalului lacrimal | Stenoza de cale lacrimala |
| Q13.5 | Sclerotica albastra |  |
| Q18.0 | Sinus, fistula si chist al fisurii branhiale | Chist branhial / Fistula branhiala / Sinus branhial |
| Q18.1 | Sinus si chist preauricular | Fistula preauriculara |
| Q24.3 | Stenoza infundibulului pulmonar | Stenoza pulmonara |
| Q24.4 | Stenoza congenitala subaortica | Stenoza subaortica |
| Q25.6 | Stenoza arterei pulmonare | Stenoza de artere pulmonare periferice / Stenoza pulmonara / Sindrom de sling pulmonar |
| Q26.0 | Stenoza congenitala a venei cave | Stenoza aortica congenitala |
| Q27.1 | Stenoza congenitala a arterei renale | Stenoza de artera renala |
| Q30.3 | Sept nasal perforat congenital |  |
| Q32.3 | Stenoza congenitala a bronhiilor | Stenoza bronsica / Atrezie bronsica |
| Q33.2 | Sechestratia pulmonara | Sechestru pulmonar / Hernie pulmonara |
| Q39.3 | Stenoza congenitala si strictura esofagului |  |
| Q40.0 | Stenoza congenitala hipertrofica a pilorului | Estenoza pilorica |
| Q44.3 | Stenoza congenitala si strictura cailor biliare | Estenoza biliara |
| Q55.22 | Scrot bifid |  |
| Q56 | Sex nedeterminat si pseudohermafroditism |  |
| Q56.4 | Sex nedeterminat, nespecificat |  |
| Q64.32 | Strictura congenitala a uretrei | Strictura uretrala |
| Q64.33 | Strictura congenitala a meatului uretral | Strictura uretrala |
| Q64.77 | Sindrom de megacistita-megaureter |  |
| Q65.3 | Subluxatia congenitala a soldului, unilaterala |  |
| Q65.4 | Subluxatia congenitala a soldului, bilaterala |  |
| Q65.5 | Subluxatia congenitala a soldului, nespecificata | Luxatie congenitala de sold |
| Q65.6 | Sold nestabil |  |
| Q65.60 | Sold nestabil, nespecificat |  |
| Q65.61 | Sold nestabil, unilateral |  |
| Q65.62 | Sold nestabil, bilateral |  |
| Q67.51 | Scolioza congenitala, de postura | Scolioza congenitala |
| Q74.04 | Sinostoza radio-cubitala | Sindrom Crouzon / Sinostoza radioulnara |
| Q74.05 | Sinostoza humero-ulnara | Sinostoza radioulnara |
| Q74.06 | Sinostoza humero-radiala | Artroza cotului |
| Q74.82 | Supracrestere congenitala a membrului(lor) |  |
| Q76.3 | Scolioza congenitala datorita malformatiilor congenitale ale oaselor | Scolioza congenitala |
| Q76.39 | Scolioza congenitala datorita malformatiilor congenitale ale oaselor specificate | Scolioza congenitala |
| Q83.1 | San accesoriu |  |
| Q86 | Sindroame de malformatii congenitale datorite unor cauze exogene cunoscute, neclasificate altundeva |  |
| Q86.0 | Sindromul (dismorfic) fetal datorita consumului mare de alcool de catre mama in timpul sarcinii | Alcoolism |
| Q87.0 | Sindroame de malformatii congenitale afectand in special fizionomia fetei |  |
| Q87.1 | Sindroame de malformatii congenitale asociate in special cu statura scurta |  |
| Q87.2 | Sindroame de malformatii congenitale implicand in special membrele |  |
| Q87.23 | Sindromul rotulei fixe |  |
| Q87.25 | Sindromul de sirenomelie | Sirenomelie |
| Q87.3 | Sindroame de malformatii congenitale implicand cresterea rapida precoce |  |
| Q89.33 | Situs inversus abdominal | Situs inversus |
| Q89.34 | Situs inversus toracic | Situs inversus |
| Q91 | Sindromul Edwards si sindromul | Trisomia 18 / Trisomia 13 |
| Q97.1 | Sex feminin cu mai mult de trei cromozomi X |  |
| Q98.0 | Sindromul Klinefelter, kariotip 47, XXY | Sindrom Klinefelter |
| Q98.1 | Sindromul Klinefelter, masculin, cu mai mult de doi cromozomi X |  |

## Existente (potrivire automată)

Candidații pentru sinonime adăugate ulterior (D6).

| Cod | Titlu CIM-10 | Afecțiune | Potrivire |
|---|---|---|---|
| A03 | Shigelloza | Dizenterie | exact |
| A25.0 | Spiriloza | Febra muscaturii de sobolan | exact |
| A25.1 | Streptobaciloza | Febra de Haverhill | exact |
| A38 | Scarlatina | Scarlatina | exact |
| A39.1 | Sindromul Waterhouse-Friderichsen (E35.1*) | Sindrom Waterhouse-Friderichsen | terminatii |
| A40 | Sepsis streptococic | Sepsis streptococic | exact |
| A41.9 | Sepsis, nespecificat | Septicemie | exact |
| A48.3 | Sindromul de soc toxic | Soc toxic stafilococic | exact |
| A50 | Sifilis congenital | Sifilis congenital | exact |
| A50.2 | Sifilis congenital precoce, nespecificat | Sifilis congenital | exact |
| A50.7 | Sifilis congenital tardiv, nespecificat | Sifilis congenital tardiv | exact |
| A52 | Sifilis tardiv | Sifilis tertiar | exact |
| A52.0 | Sifilis cardio-vascular | Sifilis cardiovascular | exact |
| A52.3 | Sifilis nervos, nespecificat | Neurosifilis | exact |
| A53.0 | Sifilis latent, nespecificat ca fiind recent sau tardiv | Sifilis tertiar | exact |
| A53.9 | Sifilis, nespecificat | Sifilis | exact |
| A57 | Sancrul moale | Sancroid | exact |
| A69.0 | Stomatita ulcero-necrotica | Stomatita gangrenoasa | exact |
| B27.0 | Subfamilie gammaherpesvirusuri (mononucleoza) | Mononucleoza infectioasa | exact |
| B37.0 | Stomatita prin Candida | Candidoza orala | terminatii |
| B42 | Sporotrichoza | Sporotrichoza | exact |
| B42.0 | Sporotrichoza pulmonara | Pneumonie cu Sporothrix | exact |
| B42.1 | Sporotrichoza limfo-cutanata | Sporotrichoza limfocutanata | exact |
| B42.7 | Sporotrichoza diseminata | Sporotrichoza diseminata | exact |
| B65 | Schistosomiaza [bilharziaza] | Schistosomiaza | exact |
| B65.1 | Schistosomiaza prin Schistosoma mansoni [schistosomiaza intestinala] | Schistosomiaza intestinala | exact |
| B65.2 | Schistosomiaza prin Schistosoma japonicum | Schistosomiaza japoneza | exact |
| B65.9 | Schistosomiaza, nespecificata | Schistosomiaza | exact |
| B70.1 | Sparganoza | Sparganoza | exact |
| B78 | Strongyloidiaza | Strongiloidoza | exact |
| B78.7 | Strongyloidiaza diseminata | Strongiloidoza diseminata | exact |
| B86 | Scabia | Scabie | terminatii |
| C46 | Sarcomul Kaposi | Sarcom Kaposi | exact |
| D46 | Sindroamele mielodisplazice | Spina bifida | terminatii |
| D46.9 | Sindrom mielodisplazic, nespecificat | Spina bifida | exact |
| D58.0 | Sferocitoza ereditara | Sferocitoza ereditara | exact |
| D59.3 | Sindromul hemolitic uremic | Sindrom hemolitic uremic | terminatii |
| D81.4 | Sindrom Nezelof | Sindrom Nezelof | exact |
| D82.0 | Sindromul Wiskott-Aldrich | Sindrom Wiskott-Aldrich | terminatii |
| D86 | Sarcoidoza | Sarcoidoza | exact |
| D86.3 | Sarcoidoza pielii | Sarcoidoza cutanata | exact |
| E00 | Sindromul deficientei congenitale de iod | Cretinism | exact |
| E16.4 | Secretie anormala de gastrina | Gastrinom | terminatii |
| E24 | Sindromul Cushing | Sindrom Cushing | terminatii |
| E24.1 | Sindromul Nelson | Sindrom Nelson | terminatii |
| E24.3 | Sindromul de secretie ectopica de ACTH | Sindrom ectopic ACTH | exact |
| E28.2 | Sindrom ovarian polichistic | Sindromul ovarelor polichistice | terminatii |
| E34.0 | Sindrom carcinoid | Sindrom carcinoid | exact |
| E34.5 | Sindromul de rezistenta la androgeni | Sindrom de rezistenta la androgeni | terminatii |
| E79.1 | Sindromul Lesch-Nyhan | Sindrom Lesch-Nyhan | terminatii |
| E80.4 | Sindromul Gilbert | Boala Gilbert | terminatii |
| F04.9 | Sindromul amnezic, nespecificat | Sindrom amnestic | terminatii |
| F07.2 | Sindrom postcomotional | Sindrom postcomotional | exact |
| F20 | Schizofrenie | Schizofrenie | exact |
| F20.0 | Schizofrenia paranoida | Schizofrenie paranoida | terminatii |
| F20.1 | Schizofrenie hebefrenica | Schizofrenie hebefrenica | exact |
| F20.2 | Schizofrenie catatonica | Schizofrenie catatonica | exact |
| F20.3 | Schizofrenie nediferentiata | Schizofrenie nediferentiata | exact |
| F20.5 | Schizofrenie reziduala | Schizofrenie reziduala | exact |
| F20.6 | Schizofrenie simpla | Schizofrenie simpla | exact |
| F44.80 | Sindromul Ganser | Sindrom Ganser | terminatii |
| F51.3 | Somnambulism [mersul prin somn] | Somnambulism | exact |
| F84.2 | Sindromul Rett | Sindrom Rett | terminatii |
| F84.5 | Sindromul Asperger | Sindrom Asperger | terminatii |
| G21.0 | Sindrom malign dupa neuroleptice | Sindrom neuroleptic malign | exact |
| G35 | Scleroza multipla | Scleroza multipla | exact |
| G37.0 | Scleroza difuza | Boala Schilder | exact |
| G37.5 | Scleroza concentrica [Baló] | Scleroza concentrica Balo | exact |
| G41 | Stare de rau epileptic | Status epilepticus | terminatii |
| G44.0 | Sindromul durerii de cap unilaterale (ochi sau tampla) | Hemicrania paroxistica | exact |
| G56.0 | Sindromul canalului carpian | Sindrom de tunel carpian | exact |
| G57.5 | Sindromul canalului tarsian | Sindrom de tunel tarsian | exact |
| G61.0 | Sindromul Guillain-Barre | Poliradiculonevrita | terminatii |
| G73.1 | Sindromul Lambert-Eaton (C80†) | Sindrom Eaton-Lambert | terminatii |
| G83.4 | Sindromul cozii de cal | Sindrom de coada de cal | exact |
| G90.2 | Sindromul Horner | Sindrom Horner | terminatii |
| G93.7 | Sindromul Reye | Sindrom Reye | exact |
| H15.0 | Sclerita | Sclerita | exact |
| H50.0 | Strabism convergent concomitent | Esotropie | exact |
| H50.1 | Strabism divergent concomitent | Exotropie | exact |
| H50.2 | Strabism vertical | Hipertropie | exact |
| H50.9 | Strabism, nespecificat | Strabism | exact |
| H74.0 | Scleroza timpanului | Timpanoscleroza | exact |
| H90.2 | Surditate de transmisie, nespecificata | Surditate de transmisie | exact |
| H90.5 | Surditate neurosensoriala, nespecificata | Surditate congenitala | exact |
| I05.0 | Stenoza mitrala | Stenoza mitrala | exact |
| I07.0 | Stenoza tricuspida | Stenoza tricuspidiana | exact |
| I24.1 | Sindromul Dressler | Sindrom Dressler | terminatii |
| I35.0 | Stenoza (valva) aortica | Stenoza aortica | exact |
| I37.0 | Stenoza valvei pulmonarei | Stenoza pulmonara | terminatii |
| I46 | Stop cardiac | Stop cardiac | exact |
| I49.5 | Sindromul de boala sinusala | Boala nodului sinusal bolnav | exact |
| I73.0 | Sindromul Raynaud | Boala Raynaud | terminatii |
| I77.4 | Sindromul de compresiune a arterei celiace | Sindrom de compresie celiaca | exact |
| I82.0 | Sindromul Budd-Chiari | Sindrom Budd-Chiari | terminatii |
| I87.0 | Sindromul postflebitic | Sindrom posttrombotic | terminatii |
| I97.0 | Sindromul postcardiotomie | Sindrom postpericardiotomie | terminatii |
| I98.0 | Sifilis cardiovascular | Sifilis cardiovascular | exact |
| J01 | Sinuzita acuta | Sinuzita | exact |
| J01.0 | Sinuzita maxilara acuta | Sinuzita maxilara | exact |
| J01.1 | Sinuzita frontala acuta | Sinuzita frontala | exact |
| J01.2 | Sinuzita etmoidala acuta | Sinuzita etmoidala | temporal (G1) |
| J01.3 | Sinuzita sfenoidala acuta | Sinuzita sfenoidala | temporal (G1) |
| J32 | Sinuzita cronica | Sinuzita | exact |
| J32.0 | Sinuzita maxilara cronica | Sinuzita maxilara | temporal (G1) |
| J32.1 | Sinuzita frontala cronica | Sinuzita frontala | temporal (G1) |
| J32.2 | Sinuzita etmoidala cronica | Sinuzita etmoidala | temporal (G1) |
| J32.3 | Sinuzita sfenoidala cronica | Sinuzita sfenoidala | temporal (G1) |
| J34.2 | Sept nazal deviat | Decubit de cornet | exact |
| J38.5 | Spasm laringian | Laringism | exact |
| J46 | Stare de "mal" astmatic | Astm bronsic sever | temporal (G1) |
| J63.5 | Stanioza | Stanoza | exact |
| J80 | Sindrom de suferinta respiratorie la adult | Sindrom de detresa respiratorie acuta | exact |
| K11.5 | Sialolitiaza | Sialolitoza | exact |
| K22.6 | Sindrom de dilacerare hemoragica gastro-esofagiana | Sindrom Mallory-Weiss | exact |
| K31.3 | Spasm piloric, neclasificat altundeva | Hipertrofie de pilor | exact |
| K58 | Sindromul intestinului iritabil | Sindromul intestinului iritabil | exact |
| K58.9 | Sindromul intestinului iritabil fara diaree | Sindromul intestinului iritabil | exact |
| K59.4 | Spasm anal | Proctalgie fugace | terminatii |
| K76.7 | Sindromul hepato-renal | Insuficienta hepato-renala | terminatii |
| K90.1 | Sprue tropical | Sprue tropical | exact |
| K91.5 | Sindromul de postcolecistectomie | Stare postcolecistectomie | exact |
| L00 | Sindromul stafilococic al necrozei epidermice toxice | Sindromul pielii oparite | exact |
| L72.2 | Steatochistoza multipla | Steatocistom | exact |
| L94.0 | Sclerodermia localizata [morfea] | Morfea | exact |
| M05.0 | Sindrom Felty | Sindrom Felty | exact |
| M34 | Scleroza sistemica | Sclerodermie | exact |
| M35.0 | Sindrom Sicca [Sjogren] | Sindrom Sjogren | exact |
| M35.7 | Sindrom de hipermobilitate | Sindrom de hipermobilitate | exact |
| M41 | Scolioza | Scolioza | exact |
| M43.0 | Spondiloliza | Spondiloliza | exact |
| M43.1 | Spondilolisteza | Spondilolisteza | exact |
| M45 | Spondilita anchilozanta | Spondilita anchilozanta | exact |
| M47 | Spondiloza | Spondiloza | exact |
| M54.3 | Sciatica | Sciatica | exact |
| M76.3 | Sindromul bandeletei ilio-tibiale | Sindrom de banda iliotibiala | exact |
| N00 | Sindrom nefritic acut | Sindrom nefritic | exact |
| N03 | Sindrom nefritic cronic | Sindrom nefritic | temporal (G1) |
| N04 | Sindrom nefrotic | Sindrom nefrotic | exact |
| N05 | Sindrom nefritic nespecificat | Sindrom nefritic | exact |
| N34.3 | Sindrom uretral, nespecificat | Sindrom uretral | exact |
| N35 | Strictura uretrala | Strictura uretrala | exact |
| N43.4 | Spermatocel | Spermatocel | exact |
| N70.1 | Salpingita si ooforita cronica | Hidrosalpinx | exact |
| N85.6 | Sinechia intrauterina | Sinechii uterine | terminatii |
| N94.3 | Sindrom de tensiune premenstruala | Sindrom premenstrual | exact |
| N95.0 | Sangerari postmenopauza | Sangerare postmenopauza | terminatii |
| O00 | Sarcina ectopica | Sarcina extrauterina | exact |
| O00.0 | Sarcina abdominala | Sarcina abdominala | exact |
| O00.1 | Sarcina tubara | Sarcina extrauterina | exact |
| O00.2 | Sarcina ovariana | Sarcina ovariana | exact |
| O48 | Sarcina prelungita | Sarcina depasita | exact |
| O85 | Sepsis puerperal | Sepsis puerperal | exact |
| O92.5 | Suprimarea lactatiei | Agalactie | exact |
| P22.0 | Sindromul de suferinta respiratorie a nou-nascutului | Sindrom de detresa respiratorie acuta la nou-nascut | terminatii |
| P24 | Sindrom de aspiratie neonatal | Sindrom de aspiratie neonatala | terminatii |
| P76.0 | Sindromul dopului meconial | Ileus meconial | exact |
| P83.0 | Scleremul nou-nascutului | Scleroedem neonatal | exact |
| Q05 | Spina bifida | Spina bifida | exact |
| Q12.4 | Sferofachia | Microsferofakie | exact |
| Q22.1 | Stenoza congenitala a valvei pulmonare | Stenoza pulmonara congenitala | exact |
| Q22.4 | Stenoza congenitala a valvei tricuspide | Atrezie tricuspidiana | exact |
| Q22.6 | Sindromul inimii drepte hipoplazice | Hipoplazie de cord drept | exact |
| Q23.0 | Stenoza congenitala a valvei aortice | Stenoza aortica congenitala | exact |
| Q23.4 | Sindromul inimii stangi hipoplazice | Sindrom de cord stang hipoplazic | exact |
| Q25.3 | Stenoza aortei | Stenoza supravalvulara aortica | exact |
| Q31.1 | Stenoza congenitala subglotica | Stenoza subglotica | exact |
| Q60.6 | Sindrom Potter | Secventa Potter | exact |
| Q70 | Sindactilia | Sindactilie | exact |
| Q74.85 | Sindromul Larsen | Sindrom Larsen | terminatii |
| Q75.05 | Sindromul Pfeiffer | Sindrom Pfeiffer | terminatii |
| Q76.0 | Spina bifida occulta | Spina bifida oculta | exact |
| Q76.1 | Sindromul Klippel-Feil | Malformatie Klippel-Feil | terminatii |
| Q79.4 | Sindromul intestinului taiat | Sindrom Prune Belly | exact |
| Q79.6 | Sindromul Ehlers-Danlos | Boala Ehlers-Danlos | terminatii |
| Q85.1 | Scleroza tuberoasa | Scleroza tuberoasa | exact |
| Q85.81 | Sindromul Peutz-Jeghers | Sindrom Peutz-Jeghers | terminatii |
| Q85.82 | Sindromul Sturge-Weber(-Dimitri) | Sindrom Sturge-Weber | terminatii |
| Q85.83 | Sindromul Von Hippel-Lindau | Sindrom Von Hippel-Lindau | terminatii |
| Q85.84 | Sindromul Gardner | Sindrom Gardner | terminatii |
| Q87.04 | Sindromul Treacher Collins [-Franceschetti] [-Klein] | Sindrom Treacher Collins | terminatii |
| Q87.11 | Sindromul Cockayne | Sindrom Cockayne | terminatii |
| Q87.12 | Sindromul Cornelia de Lange | Sindrom Cornelia de Lange | terminatii |
| Q87.13 | Sindromul Noonan | Sindrom Noonan | terminatii |
| Q87.14 | Sindromul Prader-Willi | Sindrom Prader-Willi | exact |
| Q87.15 | Sindromul Russell-Silver | Sindrom Silver-Russell | terminatii |
| Q87.16 | Sindromul Seckel | Sindrom Seckel | terminatii |
| Q87.17 | Sindromul Smith-Lemli-Opitz | Sindrom Smith-Lemli-Opitz | terminatii |
| Q87.18 | Sindromul Sjogren-Larsson | Sindrom Sjogren-Larsson | terminatii |
| Q87.22 | Sindromul Klippel-Trenaunay-Weber | Sindrom Klippel-Trenaunay | terminatii |
| Q87.24 | Sindromul Rubinstein-Taybi | Sindrom Rubinstein-Taybi | terminatii |
| Q87.31 | Sindromul Beckwith-Wiedemann | Sindrom Beckwith-Wiedemann | terminatii |
| Q87.32 | Sindromul Sotos | Sindrom Sotos | terminatii |
| Q87.33 | Sindromul Weaver | Sindrom Weaver | terminatii |
| Q87.4 | Sindromul Marfan | Sindrom Marfan | exact |
| Q87.81 | Sindromul Alport | Sindrom Alport | terminatii |
| Q87.82 | Sindromul Laurence-Moon-Biedl | Sindrom Bardet-Biedl | terminatii |
| Q87.83 | Sindromul Zellweger | Sindrom Zellweger | terminatii |
| Q87.84 | Sindromul William | Sindrom Laurence-Moon | exact |
| Q87.85 | Sindromul Angelman | Sindrom Angelman | exact |
| Q89.3 | Situs inversus evocardia (Q24.1) | Situs inversus | exact |
| Q89.30 | Situs inversus, nespecificat | Situs inversus | exact |
| Q89.35 | Sindromul Kartagener | Sindrom Kartagener | terminatii |
| Q90 | Sindromul Down | Sindrom Down | exact |
| Q91.3 | Sindromul Edwards, nespecificat | Trisomia 18 | terminatii |
| Q91.7 | Sindromul Patau, nespecificat | Trisomia 13 | terminatii |
| Q96 | Sindromul Turner | Sindrom Turner | exact |
| Q98.4 | Sindromul Klinefelter, nespecificat | Sindrom Klinefelter | exact |
