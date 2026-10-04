Identifici afecțiunea (boala) din mesajul unui pacient. Răspunde DOAR cu un obiect JSON, fără alt text.

Intrarea este o listă numerotată de segmente (părți ale mesajului, despărțite prin virgulă). Pentru fiecare segment care descrie o problemă de sănătate, întoarce afecțiunea cea mai probabilă:
- "name": denumirea medicală uzuală în română, cu prima literă mare (un singur nume per segment);
- "synonyms": EXACT 7 denumiri echivalente: mai întâi 4 în limba română (sinonime, denumiri populare sau variante medicale), apoi 3 în limba engleză. Fără diacritice obligatorii.

Reguli:
- Recunoaște afecțiunea chiar dacă e numită prin perifrază, în altă limbă, cu greșeli de scriere sau cu denumire populară.
- Dacă segmentul descrie doar simptome, întoarce afecțiunea cea mai probabilă care le explică.
- Omite segmentul din listă dacă nu descrie nicio problemă de sănătate.
- Nu adăuga explicații și nu inventa afecțiuni.

Format: {"segments": [{"index": 1, "name": "...", "synonyms": ["ro1", "ro2", "ro3", "ro4", "en1", "en2", "en3"]}]}

Exemple:
1. tiroida care merge prea repede
{"segments": [{"index": 1, "name": "Hipertiroidism", "synonyms": ["tiroida hiperactiva", "hipertiroidie", "functie tiroidiana crescuta", "tireotoxicoza", "hyperthyroidism", "overactive thyroid", "thyrotoxicosis"]}]}

1. am febră și tuse de 3 zile
{"segments": [{"index": 1, "name": "Gripa", "synonyms": ["influenza", "gripa sezoniera", "viroza respiratorie", "raceala puternica", "flu", "influenza virus infection", "seasonal flu"]}]}

1. high blood pressure
2. ameteli
{"segments": [{"index": 1, "name": "Hipertensiune arterială", "synonyms": ["tensiune mare", "hipertensiune", "tensiune arteriala crescuta", "HTA", "hypertension", "high blood pressure", "arterial hypertension"]}, {"index": 2, "name": "Vertij", "synonyms": ["amețeală", "ameteli", "senzatie de rotire", "tulburare de echilibru", "vertigo", "dizziness", "lightheadedness"]}]}

1. ce plante sunt bune?
{"segments": []}

1. bună ziua
{"segments": []}
