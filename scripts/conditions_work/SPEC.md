# SPEC — linii noi pentru data/medical_conditions.txt

## Format obligatoriu

O linie = o boala = 7 sau mai multe campuri separate prin virgula:

```
NumeBoala,sinonimRO1,sinonimRO2,sinonimRO3,english synonym 1,english synonym 2,english synonym 3
```

- Campul 1 = numele bolii **in limba romana**, cu majuscula initiala.
- Campurile 2-4 = minim 3 sinonime in romana. Campurile 5+ = minim 3 sinonime in engleza.
  Sunt acceptate si mai multe sinonime (5-6 si in romana si in engleza), dar niciodata mai putin de 3 + 3.
- **Fara diacritice** (scrie `Guta`, `Anemie sideropenica`, `Ulcer duodenal`, nu `Gută`).
- **Fara virgula in interiorul unui camp** si fara spatii in plus in jurul virgulei.
- Fiecare camp trebuie sa fie un termen medical real, folosit in practica (romana / engleza).
- Un camp = o sintagma, nu o propozitie: maxim ~60 de caractere.
- Toate sinonimele dintr-o linie trebuie sa fie distincte intre ele (fara repetitii in aceeasi linie).

## Ce intra in fisier

- **Doar boli/afectiuni**: infectii, neoplasme, boli de organ, boli autoimune, boli genetice,
  boli metabolice, degenerative, psihice. Include subspecii pe organ sau pe tip
  (ex. `Abces hepatic`, `Adenom tiroidian`, `Anemie hemolitica autoimuna calda`).
- **NU adauga**: simptome izolate (febra, tusea, durerea de cap), stari fiziologice
  (sarcina, menopauza), leziuni/traumatisme (fractura, arsura), proceduri medicale
  (chimioterapie, dializa), investigatii, medicamente, plante, vitamine, analize.
- Exista deja in fisier cateva sute de astfel de intrari vechi (ex. `Febra`, `Tuse`, `Stres`).
  Ele **nu se ating si nu se repeta** — pur si simplu nu adaugi altele noi de acest tip.

## Stil si substanta

Urmareste stilul liniilor existente. Exemple reale din fisier:

```
Abces hepatic,colectie purulenta hepatic,supuratie localizata hepatic,abces localizat hepatic,liver abscess,localized abscess of liver,suppurative infection of liver
Adenom tiroidian,tumora benigna glandulara tiroidian,neoplasm adenomatos tiroidian,adenom glandular tiroidian,thyroid gland adenoma,benign glandular tumor of thyroid gland,benign adenomatous neoplasm of thyroid gland
Anemie pernicioasa,anemie Biermer,anemie Addison-Biermer,anemie prin deficit de factor intrinsec,pernicious anemia,Biermer anemia,Addison-Biermer disease
Boala Crohn,enterita regionala,ileita terminala,boala inflamatorie intestinala Crohn,crohn's disease,regional enteritis,granulomatous enteritis
```

Reguli de substanta:

1. Nu inventa boli. Daca nu esti sigur ca o afectiune exista cu acel nume, nu o scrie.
2. Sinonimele trebuie sa fie reale: denumiri alternative, eponime, termeni vechi,
   traducceri consacrate. Nu pune in campuri descriptii inventate de tipul
   `forma X de boala Y` doar ca sa umpli 3 campuri.
3. Traducerea in engleza trebuie sa fie denumirea medicala engleza consacrata.
4. Prefera termeni pe care un pacient i-ar cauta (inclusiv denumiri populare romanesti
   consacrate, ex. `boala sarutului`, `piciorul atletului`, `gusa`).
5. Numele canonice (campul 1) nu trebuie sa fie deja folosit de alta linie din fisier.

## Interzis — duplicate

- Nu repeta o linie care exista deja in `data/medical_conditions.txt` (citeste fisierul).
- Nu repeta o boala sub alt nume existent (ex. nu adauga `COVID-19` daca ai adaugat deja
  `Boala coronavirus` in acelasi lot).
- Nu refolosi un termen deja folosit de alta boala ca sinonim al altei boli.
  `data/medical_conditions.txt` este sursa de adevar: verifica inainte de a scrie.
- Sortare: alfabetic crescator dupa primul camp, ignorand diacriticele (nu sunt diacritice
  oricum) si majusculele.

## Unde scrii

Scrie rezultatul in fisierul indicat in sarcina ta (un singur fisier, doar linii de date,
fara titluri, fara numerotare, fara linii goale, fara ``` ).
