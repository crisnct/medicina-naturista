# Sarcina 10 — Boli ale aparatului digestiv (K00–K93)

Fisier principal: `data/medical_conditions.txt` (804 linii in acest moment). Verifica fiecare candidat inainte de a-l scrie.

Contine deja (nu repeta): `Carie dentara`, `Gingivita`, `Parodontoza`, `Stomatita`, `Afte bucale`,
`Abces dentar`, `Abces periodontal`, `Bruxism`, `Acalazie`, `Reflux gastroesofagian`, `Hernie hiatala`,
`Gastrita`, `Ulcer gastric`, `Ulcer duodenal`, `Hiperaciditate gastrica`, `Dispepsie`, `Gastroenterita`,
`Enterocolita`, `Colita`, `Colita ulcerativa`, `Boala Crohn`, `Sindromul intestinului iritabil`,
`Diverticulita`, `Apendicita`, `Apendicita acuta`, `HemorOizi`, `Fisura anala`, `Fistula anala`,
`Ascita`, `Ciroza hepatica`, `Hepatita`, `Hepatita A/B/C`, `Steatoza hepatica`, `Colecistita`,
`Litiaza biliara`, `Colica biliara`, `Dischinezie biliara`, `Pancreatita`, `Insuficienta hepatica`,
`Sindrom de malabsorbtie`, `Boala celiaca`, `Intoleranta la lactoza`, `Intoleranta la fructoza`,
`Constipatie`, `Diaree`, `Colici abdominali`, `Meteorism`, `Greata`, `Varsaturi`, `Halitoza`,
`Helicobacter pylori`, `Giardiaza`, `Teniaza`, `Oxiuroza`, `Parazitoze intestinale`, `Dizenterie`,
`Colibaciloza`, `Salmoneloza`, `Ascaridioza`, `Hernie inghinala`, `Abces hepatic`, `Abces pancreatic`,
`Abces perianal`, `Abces pilonidal`, `Abces subfrenic`, `Abces pelvin`, `Abces intestinal`,
`Abces gastric`, `Abces splenic`, `Icter`, `Sindrom Reye`, `Purpura` (nu e digestiv).

Adauga ce lipseste:

## Cavitate bucala si glande salivare
glosita, glosita atrofica, glosita geometrica, leucoplazie orala, leucoplazie pilosa, lichen plan oral,
candidoza orala (daca lotul de infectioase o are, unificarea automata rezolva), stomatita herpetica,
gingivostomatita herpetica, gingivita ulceronecrotica, gingivita descuamativa, periimplantita,
mucozita orala, chist odontogen, chist radicular, tumora odontogena, ameloblastom, odontom,
granulom dentar, pulpită dentara, periodontita apicala, alveolita, cheilita, cheilita angulara,
queilitis actinica, macrocheilie, fisura labiala, palatoschizis, cheiloschizis, ranula, mucocel oral,
sialoadenita, sialolitiaza, parotidita bacteriana, sindrom Sjogren (daca lotul de reumatologie il are,
unificarea rezolva), xerostomia, hipersalivatie, disgeuzie, arsura bucala, sindrom de gura arzanda,
trismus (verifica sa nu fie deja in `Tetanos` ca sinonim), abces parafaringian (exista deja).

## Esofag
esofagita, esofagita de reflux, esofagita eozinofilica, esofagita caustica, esofag Barrett,
spasm esofagian difuz, esofagul ciocanului de vopsit, diverticul esofagian, diverticul Zenker,
stenoza esofagiana, varice esofagiene, ruptura esofagiana (sindrom Boerhaave), sindrom Mallory-Weiss,
inel Schatzki, web esofagian, disfagie, odinofagie, globus faringian, reflux laringofaringian,
boala de reflux neerosiv, esofagita medicamentoasa, perforatie esofagiana, acalazia (exista).

## Stomac si duoden
gastrita atrofica, gastrita autoimuna, gastrita eozinofilica, gastrita limfocitara,
gastrita granulomatoasa, gastropatie hipertrofica (boala Menetrier), boala ulceroasa,
ulcer peptic hemoragic, ulcer perforat, stenoza pilorica, stenoza pilorica hipertrofica infantila,
gastropareza, sindrom de dumping, sindrom postgastrectomie, bezoar, fitobezoar, tricobezoar,
volvulus gastric, dilatatie gastrica acuta, leziune Dieulafoy, ectazie vasculara gastrica,
reflux biliar, polip gastric, lipom gastric, GIST (daca lotul de neoplasme il are, unificarea rezolva),
gastrina, sindrom Zollinger-Ellison, VIPom, glucagonom, insulinom, gastrinom, somatostatinom.

## Intestin subtire si colon
enterita, ileita, jejunita, duodenita, enteropatia exudativa, enteropatia cu pierdere de proteine,
boala Whipple, sprue tropical, intoleranta la zaharuri, malabsorbtia de vitamine, sindromul de intestin
scurt, obstrucție intestinala, ileus paralitic, ocluzie intestinala, volvulus, intususceptie,
aderente intestinale, boala diverticulara, diverticuloza, megacolon, megacolon toxic, boala Hirschsprung,
dolicocolon, colita pseudomembranoasa, colita cu Clostridium difficile, colita ischemica,
colita microscopica, colita colagenoasa, colita limfocitara, colita de radiatii,
boala inflamatorie intestinala nedeterminata, proctita, proctosigmoidita, tiflita, cecita,
apendicita cronica, apendicita gangrenoasa, apendicita perforata, mucocel apendicular,
pseudomixom peritoneal, angiodisplazie intestinala, telangiectazie intestinala, hemoragie digestiva,
melena, hematochezie, ischemia mezenterica cronica, ischemia mezenterica acuta, trombOza de vena
mezenterica, linfangiektazie intestinala, pneumatoza intestinala, pneumoperitoneu, fistulă
entero-cutANATA, fistulă entero-vezicala, boala Behcet intestinala, enterita de radiatii,
colita colagenoasa, sindrom de intestin iritabil postinfectios, diaree cronica, diaree secretorie,
diaree osmotica, steatoree (poate fi la pancreas), sindrom de fermentatie.

## Rect si anus
trombOza hemoroidala, prolaps hemoroidal, abces ischiorectal, criptita, papilita anala,
prurit anal, incontinenta fecala, stenoza anala, boala pilonidala, sinus pilonidal, proctalgie fugax,
sindrom de durere anorectala, rectocel, hemoragie digestiva inferioara, fisura anala cronica,
ulcer rectal solitar, proctita ulceroasa, neoplasma anala, condiloame anale, hemoroidectomie
(NU — procedura), marisca cutanata anala, hemoragie de la fisura.

## Ficat
hepatita cronica, hepatita autoimuna, hepatita toxica, hepatita medicamentoasa, hepatita alcoolica,
hepatita fulminanta, ciroza biliara primara, colangita biliara primara, colangita sclerozanta primara,
colangita ascendenta, sindrom Budd-Chiari, trombOza de vena porta, hipertensiune portala,
encefalopatie hepatica, sindrom hepatorenal, sindrom hepatopulmonar, icter neonatal, icter hemolitic,
hiperbilirubinemie benigna (boala Gilbert), sindrom Dubin-Johnson, sindrom Rotor, colestaza,
colestaza de sarcina, colestaza benigna recidivanta, pelioza hepatica, hiperplazie nodulara focala,
hemangiom hepatic, chist hepatic, chist hidatic hepatic, fibroza hepatica, congestie hepatica pasiva,
ficat de soc, infarct hepatic, boala policistica hepatica, hepatomegalie, sindrom de liza tumorala
hepatica, insuficienta hepatica acuta, ciroza compensata, ciroza decompensata, ascita refractara,
peritonita bacteriana spontana, sindrom hepatorenal (acoperit), hepatita cu virus delta,
hepatita cu virus E, hepatita cu virus G, ciroza posthepatitica, hemocromatoza hepatica,
deficit de alfa-1 antitripsina (exista), boala Wilson (exista), porfirie hepatica (poate fi la endocrin),
sindrom Reye (exista), abces amibian hepatic, hidatidoza hepatica.

## Cai biliare si pancreas
coledocolitiaza, colangita, colangita acuta, colangita sclerozanta, colecistita alitiazica,
hidrocolecist, empiem vezicular, gangrena vezicii biliare, perforatie de vezica biliara,
polip vezicular, adenomioamatoza veziculara, sindrom postcolecistectomie, disfunctie de sfincter Oddi,
chist de coledoc, atrezie biliara, boala Caroli, colangită, colestaza extrahepatica, litiaza
intrahepatica, sindrom Mirizzi, fistulă biliaro-digestiva, ileus biliar, pancreatita autoimuna,
pancreatita ereditara, pseudochist pancreatic, calcificari pancreatice, litiaza pancreatica,
insuficienta pancreatica exocrina, insuficienta pancreatica endocrina, steatoree pancreatica,
fibroza pancreatica, atrofie pancreatica, necroza pancreatica, abces pancreatic (exista),
sindrom Zollinger-Ellison (acoperit), diaree pancreatica.

## Peritoneu si perete abdominal
peritonita tuberculoasa, peritonita sclerozanta, carcinoza peritoneală, ascita chiloasa,
hemoperitoneu, hernie incisionala, hernie femorala, hernie epigastrica, hernie lombara,
hernie obturatorie, hernie Spigelian, eventratie, diastazis al muschilor drepți,
dehiscență de perete abdominal, abces intraabdominal, scleroza peritoneală incapsulata,
chist de mezenter, trombOza de vene mezenterice, limfom mezenteric (neoplasm).
