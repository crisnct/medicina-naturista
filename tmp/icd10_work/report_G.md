# Litera G — raport CIM-10

- coduri CIM-10 cu titlul la litera G: **125**
- eliminate automat (P2): **36**
  - subzona de organ (D5): 32
  - dublura categoriei parinte (nespecificat): 2
  - asterisc (in alte boli): 2
- găsite automat în dicționar (P4.1–P4.3): **28**
- de decis manual (`nou` + `posibil`): **61**
- **afecțiuni adăugate: 24**

## Decizii manuale

- **Din `pending_by_letter.jsonl`:** `Ganglionita geniculata` (G51.1) re-verificată: nu există; e distinctă de `Sindrom Ramsay Hunt` (forma herpetică, B02.2, exclusă din G51.1). Adăugată cu titlul CIM-10 („Afecțiunea ganglionului geniculat”) ca prim sinonim.
- **Glomerulonefritele N00–N08 (D5):** categoriile de 3 caractere sunt sindroame clinice (la S, H, P, N, T), iar subdiviziunile .0–.8 (comune tuturor, pag. 287 din RoDRG) sunt tipuri histologice. Fiecare tip histologic consacrat a fost căutat o singură dată, nu pe fiecare combinație sindrom × histologie: `.0` anomalie glomerulară minoră → `Nefropatia cu leziuni minime`; `.1` leziuni focale și segmentare → `Glomeruloscleroza focal segmentara`; `.2` membranoasă → `Nefropatia membranoasa`; `.4` proliferativă endocapilară → `Glomerulonefrita` (postinfecțioasă); `.5` mezangiocapilară și `.6` boala cu depozit dens → `Glomerulonefrita membranoproliferativa`; `.7` extracapilară / în semilună → `Glomerulonefrita rapid progresiva`; `.8` „proliferativă NOS” și „sclerozantă difuză” (N18.90) → `Glomerulonefrita` (reziduale / stadiul final, G1). Singurul tip lipsă, `.3` proliferativă mezangială difuză, a fost adăugat: `Glomerulonefrita mezangioproliferativa` (N00.3–N07.3). N08 = asterisc (P2).
- **Existau sub alt nume:** gastroenteropatia cu agent Norwalk (`Infectie cu norovirus`), gomele, gangosa, goundou și ganglionul pianic (`Framboesia`, stadii tardive grupate D5), glaucomul primar cu unghi deschis (sinonim al `Glaucom`), cel cu unghi îngust (`Glaucom acut cu unghi inchis`), glaucomul secundar altor afecțiuni (`Glaucom secundar`), glosodinia / glosopiroza (`Lipa bucala`, sindromul gurii arzânde), gastroenterita radică (`Colita actinica`), gastroenterita eozinofilică (`Eozinofilie gastrointestinala`), gastrita hipertrofică gigantă (`Gastropatie hipertrofica`), granulomul central cu celule gigante (`Granulomatoza cu celule gigante`), granulomul de corp străin (`Granulom de la corpi straini`), granulomul periapical (`Absces dentar cronic`), granulomul corzii vocale (`Granulom laringian`), granulomul gingival piogen (`Granulom piogenic`), granulomul orbitei (`Pseudotumora orbitala`), granulomul eozinofilic D76.0 (`Histiocitoza cu celule Langerhans`), granulomatoza septică progresivă (`Boala granulomatoasa cronica`), gangrena fusospirochetală (`Stomatita gangrenoasa` / `Gingivita ulceronecrotica`), goma sifilitică (`Sifilis tertiar`), gușa uninodulară, toxică difuză, nodulară toxică și limfadenoidă (`Gusa cu nodul unic netoxic`, `Boala Graves`, `Gusa multinodulara toxica`, tiroidita Hashimoto), gâtul membranat (`Pterigium cervical`), glicogenoza cardiacă (`Glicogenoza tip II`), limba geografică / glosita migratorie (`Glosita geometrica`), găurile maculare (`Gaura maculara`), gaura retiniană fără dezlipire (`Dezlipire de retina`, „ruptură de retină”), guturaiul (`Raceala`, `Rinita alergica`), Gilles de la Tourette, gângăveala, galactozemia, gastroptoza, ginecomastia, gigantismul cerebral (`Sindrom Sotos`), gangliozidoza GM2 (`Boala Tay-Sachs`), gammapatia monoclonală (eliminată greșit de script ca „subzonă”, există).
- **Grupate în categoria lor (D5 / G1):** gripa cu/fără virus identificat cu pneumonie sau alte manifestări (J10–J11), gușa endemică difuză / multinodulară prin carență de iod (`Gusa endemica`), guta idiopatică, medicamentoasă și prin insuficiență renală (`Guta`), gonartroza primară / posttraumatică / bilaterală (`Gonartroza`, `Artroza posttraumatica`), gingivita acută / cronică, gastrita superficială / atrofică cronică, gândurile și actele obsesive F42.0 / F42.2 (`Tulburare obsesiv-compulsiva`), gangrena aterosclerotică (`Ateroscleroza obliteranta`), tipurile de gemeni uniți Q89.42–Q89.49 (craniopagus, toracopagus, xifopagus, pigopagus → `Gemeni uniti`), galactocelul puerperal (în `Galactocel`), greutatea mică pentru vârsta gestațională P05.0 (`Restrictie de crestere intrauterina`).
- **Nu sunt boli anume (G7 / P2):** subzonele de organ ale tumorilor (gingie, glandă, glob ocular, ganglioni limfatici), K05 și K29 ca titluri de categorie, „Glaucom în boli endocrine” (asterisc), reziduale (H40.5, K52.9, K14.9), greutatea foarte mică la naștere P07.0x (stare/măsurătoare, acoperită de `Nastere prematura`), gâfâitul nou-născutului (simptom), gigantismul constituțional (variantă a normalului), glandele salivare și suprarenale accesorii/ectopice (variante anatomice), gemenii ca sarcină multiplă (O33.7, P01.5 — factori), glaucomul traumatic obstetrical P15.3 și granulomul după mastoidectomie (leziune / complicație de procedură), „grăsimi” J69.1 (fragment rupt din titlu).
- **Variante de tip / cauză păstrate separat (G4):** glaucomul traumatic, uveitic și cortizonic (dicționarul are deja `Glaucom neovascular`, `Glaucom pigmentar`, `Glaucom exfoliativ`), gastrita alcoolică și eroziv-hemoragică (lângă `Gastrita de stres`, `Gastrita biliara` etc.), gastroenterita toxică și cea alergică/alimentară, guta saturnină, gușa dishormonogenetică și cea neonatală, granulomul periferic cu celule gigante (epulis), `Geotricoza` (forma generală, lângă `Pneumonie cu Geotrichum`), `Geaman acardiac` (secvența TRAP, distinctă de gemenii uniți).
- **Gastroduodenita** (K29.9) adăugată separat: e diagnosticul uzual al titlului K29, iar dicționarul are doar `Gastrita` și `Duodenita` separat.
- **Amânate la altă literă** (`pending_from_G.jsonl`): `Boala Grover` (B, L11.1), `Hipertensiune oculara` (H, H40.0), `Necroza pulpara` (N, K04.1 „gangrena pulpară”), `Resorbtie dentara` (R, K03.3 „granulom intern al pulpei”), `Sindrom Pendred` (S, E07.1), `Tulburare de rivalitate intre frati` (T, F93.3 „gelozie între frați”), `Xantom verucos` (X, K13.4). `Sindrom Gianotti-Crosti` (L44.4) era deja în așteptare de la A.
- **Sinonime insuficiente:** niciuna. „Granulomul eozinofilic al mucoasei bucale” (K13.4, ulcerul traumatic eozinofilic) nu a fost adăugat: denumirile lui reale sunt puține și instabile.
- **Corecturi la unirea literelor (coordonator):** scoasă `Granulom periferic cu celule gigante` (K06.8): e aceeași entitate cu `Epulis gigantocelular` de la E, care are deja sinonimele „granulom periferic cu celule gigante” / „peripheral giant cell granuloma”.

## Adăugate

| Nume canonic | Coduri | Sinonime |
|---|---|---|
| Galactocel | N64.8, O92.7 | chist lactat; chist de retentie lactata; galactocel puerperal; galactocele; milk cyst; lactocele |
| Galactoree | N64.3, O92.6 | galactoree neasociata cu nasterea; secretie lactata in afara alaptarii; scurgere de lapte din mamelon; galactorrhea; galactorrhea not associated with childbirth; galactorrhoea; inappropriate lactation |
| Ganglionita geniculata | G51.1 | afectiunea ganglionului geniculat; nevralgie geniculata; inflamatia ganglionului geniculat; nevralgie de ganglion geniculat; geniculate ganglionitis; geniculate neuralgia; nervus intermedius neuralgia |
| Gastrita alcoolica | K29.2 | gastrita etanolica; gastrita din alcoolism; gastropatie alcoolica; alcoholic gastritis; alcohol-induced gastritis; ethanol-induced gastritis |
| Gastrita eroziva | K29.0 | gastrita hemoragica acuta; gastrita eroziva acuta cu hemoragie; gastrita eroziv-hemoragica; gastrita hemoragica; acute hemorrhagic gastritis; erosive gastritis; acute erosive gastritis; hemorrhagic gastritis |
| Gastroduodenita | K29, K29.9 | gastrita si duodenita; inflamatie gastroduodenala; gastroduodenita cronica; gastroduodenitis; gastritis and duodenitis; chronic gastroduodenitis |
| Gastroenterita alergica | K52.2 | gastroenterite si colite alimentare si alergice; gastroenterita prin hipersensibilitate alimentara; enterocolita alergica; allergic and dietetic gastroenteritis and colitis; allergic gastroenteritis; food allergic gastroenteritis |
| Gastroenterita toxica | K52.1 | gastroenterite si colite toxice; gastroenterita medicamentoasa; enterocolita toxica; toxic gastroenteritis and colitis; toxic gastroenteritis; drug-induced gastroenteritis |
| Geaman acardiac | Q89.46 | secventa TRAP; sindrom de perfuzie arteriala inversata la gemeni; fat acardiac; acardiac twin; twin reversed arterial perfusion sequence; TRAP sequence; acardius |
| Gemeni uniti | Q89.4, Q89.42, Q89.43, Q89.44, Q89.45, Q89.49 | gemeni siamezi; gemeni conjugati; gemeni lipiti; conjoined twins; Siamese twins; conjoined twinning |
| Geminatie dentara | K00.2 | geminatia dintilor; dinti geminati; schizodontie; dental gemination; gemination of teeth; schizodontia |
| Geotricoza | B48.3 | geotrichoza; infectie cu Geotrichum; stomatita prin Geotrichum; geotrichosis; Geotrichum infection; Geotrichum candidum infection |
| Glaucom cortizonic | H40.6 | glaucom provocat de medicamente; glaucom indus de corticosteroizi; glaucom cortico-indus; glaucoma secondary to drugs; steroid-induced glaucoma; corticosteroid-induced glaucoma; drug-induced glaucoma |
| Glaucom traumatic | H40.3 | glaucom secundar unui traumatism ocular; glaucom posttraumatic; glaucom prin recesiunea unghiului; glaucoma secondary to eye trauma; traumatic glaucoma; angle recession glaucoma; post-traumatic glaucoma |
| Glaucom uveitic | H40.4 | glaucom secundar unei inflamatii a ochiului; glaucom inflamator; glaucom secundar uveitei; glaucoma secondary to eye inflammation; uveitic glaucoma; inflammatory glaucoma |
| Glomerulonefrita mezangioproliferativa | N00.3, N01.3, N02.3, N03.3, N04.3, N05.3, N06.3, N07.3 | glomerulonefrita proliferativa mezangiala difuza; glomerulonefrita mezangiala proliferativa; glomerulonefrita mezangiala; diffuse mesangial proliferative glomerulonephritis; mesangial proliferative glomerulonephritis; mesangioproliferative glomerulonephritis |
| Glosita romboida mediana | K14.2 | glosita romboidala mediana; atrofie papilara centrala a limbii; glossitis rhombica mediana; median rhomboid glossitis; central papillary atrophy of the tongue; glossitis rhomboidea mediana |
| Gongilonemiaza | B83.8 | gongylonemiaza; infectie cu Gongylonema; infectie cu Gongylonema pulchrum; gongylonemiasis; gongylonemosis; Gongylonema infection |
| Granulom actinic | L57.5 | granulom actinic O'Brien; granulom elastolitic anular cu celule gigante; granulom inelar actinic; actinic granuloma; annular elastolytic giant cell granuloma; O'Brien actinic granuloma |
| Granulom facial | L92.2 | granulom eosinofilic al pielii fetei; granulom facial eozinofilic; granulom eozinofilic al fetei; granuloma faciale; granuloma faciale eosinophilicum; facial granuloma with eosinophilia |
| Granulom letal al liniei mediane | M31.2 | granulom malign al liniei mediane; granulom malign centrofacial; reticuloza polimorfa; lethal midline granuloma; malignant midline granuloma; polymorphic reticulosis |
| Gusa dishormonogenetica | E07.1 | gusa datorita unei tulburari a sintezei hormonale; gusa familiala dishormonogenetica; dishormonogeneza tiroidiana; dyshormogenetic goiter; dyshormonogenetic goiter; thyroid dyshormonogenesis; familial dyshormonogenetic goiter |
| Gusa neonatala | P72.0 | gusa congenitala tranzitorie cu functionare normala; gusa congenitala tranzitorie; gusa a nou-nascutului; neonatal goiter; transient congenital goiter; newborn goiter |
| Guta saturnina | M10.1 | guta prin intoxicatia cu plumb; guta indusa de plumb; guta din saturnism; lead-induced gout; saturnine gout; lead gout |

## Decise manual, neadăugate

Titluri `nou` / `posibil` care nu au devenit afecțiuni noi: există sub alt nume, sunt variante ale unei categorii (D5), categorii generice sau nu sunt boli (G7). Coloana „Apropiat” e sugestia automată.

| Cod | Titlu CIM-10 | Apropiat |
|---|---|---|
| A08.1 | Gastro-enteropatia acuta prin agentul |  |
| A66.4 | Gomele si ulcerele pianice |  |
| A66.5 | Gangosa | Raceala |
| B00.2 | Gingivo-stomatita si faringo-amigdalita cu virusul herpetic | Amigdalita cu virus herpes simplex / Gingivostomatita herpetica / Faringita herpetica |
| E01.0 | Gusa difuza (endemica) legata de carenta de iod | Deficit de iod |
| E01.1 | Gusa multinodulara (endemica) legata de o carenta de iod | Deficit de iod / Gusa multinodulara netoxica |
| F42.0 | Ganduri predominant obsedante sau de meditare |  |
| F42.2 | Ganduri si acte obsedante mixte |  |
| H40.0 | Glaucomul la limita | Hipertensiune arteriala secundara / Hipertensiune arteriala pulmonara / Hipertensiune portala |
| H40.1 | Glaucom primar in unghi deschis | Glaucom |
| H40.2 | Glaucom primar in unghi ingust |  |
| H40.5 | Glaucom secundar altor afectiuni oculare |  |
| H42.0 | Glaucom in bolile endocrine, de nutritie si metabolism |  |
| J10 | Gripa datorita unui virus gripal identificat | Gripa cu virus identificat / Gripa fara virus identificat |
| J10.0 | Gripa cu pneumonie, virus gripal identificat (Bronho)pneumonia virala, virus gripal identificat | Gripa cu virus identificat / Gripa fara virus identificat / Pneumonie / Pneumonie cu virus influenza |
| J10.8 | Gripa cu alte manifestari, virus gripal identificat | Gripa cu virus identificat / Gripa fara virus identificat |
| J11 | Gripa, virus neidentificat | Gripa fara virus identificat / Gripa cu virus identificat |
| J11.0 | Gripa cu pneumonie, virus neidentificat (Bronho)pneumonia virala, nespecificata sau virus specific neidentificat | Gripa fara virus identificat / Pneumonie / Pneumonie cu virus influenza |
| J11.8 | Gripa cu alte manifestari, virus neidentificat | Gripa fara virus identificat |
| J85.0 | Gangrena si necroza pulmonara | Gangrena pulmonara |
| K05 | Gingivita si bolile periodontale |  |
| K10.1 | Granulom cu celule gigante, central | Granulomatoza cu celule gigante / Tumora cu celule gigante |
| K13.4 | Granulomul si leziunile pseudo-granuloase ale mucoasei bucale |  |
| K14.6 | Glosodinia |  |
| K52.0 | Gastroenterite si colite datorite iradierii |  |
| K52.9 | Gastroenterita si colita neinfectioase, nespecificate |  |
| L92.3 | Granulom datorita prezentei unui corp strain al pielii si tesutului celular subcutanat | Granulom de la corpi straini |
| M10.0 | Guta idiopatica | Rinita vasomotorie / Urticarie / Artrita gutoasa |
| M10.2 | Guta de origine medicamentoasa | Alergie medicamentoasa |
| M10.3 | Guta datorita deficientei functiei renale | Nefropatia gutoasa |
| M17.0 | Gonartroza primara, bilaterala |  |
| M17.2 | Gonartroza post-traumatica bilaterala |  |
| M60.2 | Granulom aparut datorita prezentei unui corp strain in tesutul conjunctiv, neclasificat altundeva | Granulom de la corpi straini |
| P05.0 | Greutate mica pentru varsta gestationala |  |
| P07.0 | Greutate la nastere foarte mica |  |
| P07.01 | Greutate la nastere foarte mica de 499g sau mai putin |  |
| P07.02 | Greutate la nastere foarte mica de 500 - 749g |  |
| P07.03 | Greutate la nastere foarte mica |  |
| P28.83 | Gafaitul la nou-nascut |  |
| Q18.3 | Gat membranat | Pterigium cervical |

## Existente (potrivire automată)

Candidații pentru sinonime adăugate ulterior (D6).

| Cod | Titlu CIM-10 | Afecțiune | Potrivire |
|---|---|---|---|
| A07.1 | Giardiaza [lambliaza] | Giardiaza | exact |
| A48.0 | Gangrena gazoasa | Gangrena gazoasa | exact |
| A58 | Granulom inghinal | Granulom inghinal | exact |
| B83.1 | Gnathostomiaza | Gnatostomoza | exact |
| E01.2 | Gusa (endemica) legata de carenta de iod, nespecificata | Gusa endemica | exact |
| E04.0 | Gusa difuza netoxica | Gusa difuza netoxica | exact |
| E04.2 | Gusa multinodulara netoxica | Gusa multinodulara netoxica | exact |
| E04.9 | Gusa netoxica, nespecificata | Gusa | exact |
| E75.0 | Gangliosidoza GM2 | Boala Tay-Sachs | exact |
| H40 | Glaucom | Glaucom | exact |
| J10.1 | Gripa cu alte manifestari respiratorii, virus gripal identificat | Gripa | exact |
| J11.1 | Gripa cu alte manifestari respiratorii, virus neidentificat | Gripa | exact |
| K05.0 | Gingivita acuta | Gingivita | temporal (G1) |
| K05.1 | Gingivita cronica | Gingivita | exact |
| K14.0 | Glosita | Glosita | exact |
| K29.3 | Gastrita superficiala cronica | Gastrita cronica neatrofica | exact |
| K29.4 | Gastrita atrofica cronica | Gastrita atrofica | temporal (G1) |
| K29.5 | Gastrita cronica, nespecificata | Gastrita | exact |
| K29.7 | Gastrita, nespecificata | Gastrita | exact |
| L92.0 | Granulom inelar | Granulom inelar | exact |
| L98.0 | Granulom piogenic | Granulom piogenic | exact |
| M10 | Guta | Guta | exact |
| M17 | Gonartroza [artroza genunchiului] | Gonartroza | exact |
| M17.9 | Gonartroza, nespecificata | Gonartroza | exact |
| M31.3 | Granulomatoza Wegener | Granulomatoza cu poliangiita | exact |
| M67.4 | Ganglion | Chist sinovial | exact |
| Q15.0 | Glaucom congenital | Glaucom congenital | exact |
| Q79.3 | Gastroschizis | Gastroschizis | exact |
