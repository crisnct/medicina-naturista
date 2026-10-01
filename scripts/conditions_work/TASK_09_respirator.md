# Sarcina 09 — Boli ale sistemului respirator (J00–J99)

Fisier de scris: `scripts/conditions_work/09_respirator.txt`
Fisier principal: `data/medical_conditions.txt` (cateva mii de linii — verifica fiecare candidat).

Contine deja (nu repeta): `Raceala`, `Sinuzita`, `Rinosinuzita`, `Faringita`, `Amigdalita` (+ acuta/cronica),
`Laringita`, `Crup`, `Traheita`, `Bronsita`, `Bronhopneumopatie obstructiva cronica`, `Astmul bronsic`,
`Emfizem pulmonar`, `Pneumonie`, `Pleurezie`, `Abces pulmonar`, `Polipi nazali`, `Rinita`, `Rinita alergica`,
`Apnee in somn`, `Tuse`, `Tuse convulsiva`, `Dispnee`, `Hemoragie nazala`, `Boala legionarilor`,
`Tuberculoza`, `Sarcoidoza`, `Sforait`, `Fibroza chistica`, `Deficit de alfa-1 antitripsina`,
`Insuficienta respiratorie` (poate exista deja), `Sughit`, `Pneumotorax` (poate exista), `Sindrom de detresa
respiratorie acuta` (poate exista), `Embolie pulmonara` (poate exista la circulator).

Adauga ce lipseste:

## Cai respiratorii superioare
faringita streptococica, faringita virala, faringita cronica, amigdalita cu streptococ betahemolitic,
amigdalita herpetica, amigdalita caseoasa, faringoamigdalita, epiglotita, laringita cronica,
laringotraheobronsita, laringospasm, edem laringian, granulom laringian, noduli vocali, polipi vocali,
disfonie, afonie, laringomalacie, stenoza laringiana, papilomatoza laringiana, abces peritonsilar (exista),
abces retrofaringian (exista), hipertrofie de amigdale, hipertrofie de adenOizi, adenoidita,
vegetatii adenoide, faringita herpetica, ulcer faringian, flegmon periamigdalian,
sindrom Lemierre (poate exista la infectioase).

## Gripa si pneumonii
gripa cu manifestari respiratorii, gripa cu manifestari digestive, bronhopneumonie, pneumonie lobara,
pneumonie atipica, pneumonie cu Mycoplasma, pneumonie pneumococica, pneumonie stafilococica,
pneumonie cu Klebsiella, pneumonie nosocomiala, pneumonie aspirativa, pneumonie interstitiala,
pneumonie lipoidica, pneumonie eozinofilica, pneumonie organizata criptogenica (BOOP),
insuficienta respiratorie acuta, insuficienta respiratorie cronica, atelectazie pulmonara,
infarct pulmonar, embolie pulmonara, hipertensiune pulmonara, cord pulmonar cronic, edem pulmonar,
hemoragie pulmonara, hemoptizie, congestie pulmonara, abces pulmonar (exista), gangrena pulmonara,
pleurezie purulenta (empiem — poate exista), sindrom de detresa respiratorie acuta.

## Boli obstructive si bronsice
bronsiolita, bronsiolita obliteranta, bronsiectazie, traheobronsomegalie, astm nealergic,
astm profesional, astm aspirinic, astm sever, status astmaticus, astm de efort, bronsospasm,
hiperreactivitate bronsica, sindrom de suprapozitie astm-BPOC, bronsita astmatica,
bronsita cronica obstructiva, traheobronsita, sindrom de tuse cu hiperreactivitate.

## Boli interstitiale si profesionale
fibroza pulmonara idiopatica, fibroza pulmonara interstitiala, silicoza, azbestoza, antracoza,
berilioza, sideroza, bisinoza, bagasoza, plamanul fermierului, plamanul crescatorului de porumbei,
pneumonita de hipersensibilitate, histiocitoza pulmonara cu celule Langerhans, limfangioleiomiomatoza,
proteinosis alveolară, pneumonie interstitiala desquamativa, boala pulmonara eozinofilica,
hemoragie alveolară, sindrom Goodpasture (poate exista), amiloidoza pulmonara, microlitiaza alveolară,
sindrom de detresa respiratorie a adultului, fibroelastoza pulmonara, calcinoza pulmonara.

## Pleura si mediastin
pleurezie uscata, pleurezie exudativa, chilotHorax, hemotorax, pneumotorax spontan,
pneumotorax traumatic, pneumotorax hipertensiv, hidrotorax, empiem pleural, fibrotorax,
placa pleurala, durere pleurala, chist pleural, tumora pleurala (mezoteliom — poate exista),
mediastinita, fibroza mediastinala, emfizem mediastinal, pneumomediastin, chist mediastinal,
tumora mediastinala.

## Nas si sinusuri
sinuzita maxilara, sinuzita frontala, sinuzita etmoidala, sinuzita sfenoidala, sinuzita fungica,
rinosinusita cronica, rinosinusita acuta, deviatie de sept nazal, perforatie de sept nazal,
rinita vasomotorie, rinita atrofica, ozena, rinita medicamentoasa, rinita de sarcina, rinita cronica,
rinita hiperplazica, rinosporidioza, rinoscleroza, atrezie de choana, sinuzita odontogena,
mucocel sinusal, piocel sinusal, polipoza nazala (exista), sinuzita alérgica fungica,
sindrom de sinus silviu, hemoragie nazala (exista), corpi straini nazali (nu adauga).

## Somn si alte boli respiratorii
apnee centrala in somn, sindrom de hipoventilatie alveolară, sindrom de hipoventilatie congenitala,
sindrom de apnee obstructiva (exista), răgușeală cronică, sindrom de tuse cronica, tuse psihogena,
hiperventilatie, tulburare de respiratie disfunctionala, sindrom de aspiratie recurenta,
insuficienta respiratorie (exista), sindrom de apnee in somn (exista), somnambulism (exista),
sindrom Pickwick, obezitate-hipoventilatie, respiratie Cheyne-Stokes, sindrom de apnee centrala
la altitudine, boala pulmonara obstructiva cronica (exista).
